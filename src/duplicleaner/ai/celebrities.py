"""Celebrity Face Identification for DupliCleaner.

Identifies celebrities and public figures among unknown faces using
cloud APIs (Amazon Rekognition) or a local celebrity embedding database.
"""

import json
import os
import struct
import threading
from dataclasses import dataclass, field
from io import BytesIO

from duplicleaner.db.models import CelebrityMatch, Face, Person
from duplicleaner.utils.config import get_config
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Optional dependency: boto3 for AWS Rekognition
BOTO3_AVAILABLE = False
try:
    import boto3

    BOTO3_AVAILABLE = True
except ImportError:
    pass

# Optional dependency: numpy for embedding similarity
NUMPY_AVAILABLE = False
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    pass


@dataclass
class CelebrityIdentification:
    """Result from a celebrity identification provider."""

    name: str = ""
    confidence: float = 0.0
    provider: str = ""
    external_id: str | None = None
    urls: list[dict[str, str]] = field(default_factory=list)
    known_for: str | None = None


@dataclass
class CelebrityProgress:
    """Progress tracking for celebrity identification."""

    total_faces: int = 0
    processed_faces: int = 0
    identified_faces: int = 0
    current_face: str = ""
    phase: str = "initializing"
    is_cancelled: bool = False

    @property
    def percent_complete(self) -> float:
        if self.total_faces == 0:
            return 0.0
        return (self.processed_faces / self.total_faces) * 100


class CelebrityIdentifier:
    """Identify celebrities in face crops using cloud or local methods."""

    def __init__(self, db) -> None:
        """Initialize the celebrity identifier.

        Args:
            db: Database instance
        """
        self.db = db
        self.config = get_config()
        self._rekognition_client = None
        self._local_db_loaded = False
        self._local_embeddings: list[dict] = []  # [{name, embedding, ...}]

    def is_available(self) -> bool:
        """Check if any celebrity identification provider is configured."""
        provider = self.config.ai.celebrity_provider

        if provider == "rekognition":
            if not BOTO3_AVAILABLE:
                return False
            from duplicleaner.utils.keystore import AIProvider, get_keystore
            return get_keystore().has_key(AIProvider.AWS)

        if provider == "local_db":
            db_path = self._get_local_db_path()
            return db_path is not None and os.path.exists(db_path)

        return False

    def get_provider_status(self) -> str:
        """Get a human-readable status of the current provider."""
        provider = self.config.ai.celebrity_provider

        if provider == "rekognition":
            if not BOTO3_AVAILABLE:
                return "boto3 not installed (pip install boto3)"
            from duplicleaner.utils.keystore import AIProvider, get_keystore
            if not get_keystore().has_key(AIProvider.AWS):
                return "AWS credentials not configured"
            return "Ready"

        if provider == "local_db":
            db_path = self._get_local_db_path()
            if db_path is None or not os.path.exists(db_path):
                return "Local celebrity database not found"
            return "Ready"

        return f"Unknown provider: {provider}"

    def identify_faces(
        self,
        faces: list[Face],
        provider: str | None = None,
        progress_callback=None,
        cancel_event: threading.Event | None = None,
    ) -> list[CelebrityMatch]:
        """Identify celebrities among a list of faces.

        Args:
            faces: Unassigned faces to identify
            provider: Override provider (None = use config default)
            progress_callback: Callable receiving CelebrityProgress
            cancel_event: Threading event for cancellation

        Returns:
            List of CelebrityMatch objects saved to the database
        """
        if not faces:
            return []

        active_provider = provider or self.config.ai.celebrity_provider
        min_confidence = self.config.ai.celebrity_min_confidence
        auto_threshold = self.config.ai.celebrity_auto_confirm_threshold

        progress = CelebrityProgress(
            total_faces=len(faces),
            phase="identifying",
        )
        results: list[CelebrityMatch] = []

        for face in faces:
            if cancel_event and cancel_event.is_set():
                progress.is_cancelled = True
                break

            progress.current_face = f"Face #{face.id}"
            if progress_callback:
                progress_callback(progress)

            identification = None

            if active_provider == "rekognition":
                image_bytes = self._crop_face_to_bytes(face)
                if image_bytes:
                    identification = self._identify_via_rekognition(face, image_bytes)
            elif active_provider == "local_db":
                identification = self._identify_via_local_db(face)

            if identification and identification.confidence >= min_confidence:
                # Determine initial status
                status = "pending"
                if identification.confidence >= auto_threshold:
                    status = "confirmed"

                match = CelebrityMatch(
                    face_id=face.id,
                    provider=identification.provider,
                    celebrity_name=identification.name,
                    confidence=identification.confidence,
                    external_id=identification.external_id,
                    external_urls=json.dumps(identification.urls) if identification.urls else None,
                    known_for=identification.known_for,
                    status=status,
                )
                match_id = self.db.add_celebrity_match(match)
                match.id = match_id

                # Auto-confirm high-confidence matches
                if status == "confirmed":
                    person_id = self._find_or_create_person(
                        identification.name, active_provider
                    )
                    if person_id:
                        self.db.assign_face_to_person(face.id, person_id)
                        self.db.update_celebrity_match_status(
                            match_id, "confirmed", person_id
                        )
                        match.person_id = person_id
                        match.status = "confirmed"

                results.append(match)
                progress.identified_faces += 1

            progress.processed_faces += 1
            if progress_callback:
                progress_callback(progress)

        progress.phase = "complete"
        if progress_callback:
            progress_callback(progress)

        logger.info(
            "Celebrity identification complete: %d/%d faces identified (%s)",
            progress.identified_faces,
            progress.total_faces,
            active_provider,
        )
        return results

    def _identify_via_rekognition(
        self, face: Face, image_bytes: bytes
    ) -> CelebrityIdentification | None:
        """Send face crop to AWS Rekognition RecognizeCelebrities."""
        if not BOTO3_AVAILABLE:
            return None

        try:
            client = self._get_rekognition_client()
            if client is None:
                return None

            response = client.recognize_celebrities(
                Image={"Bytes": image_bytes}
            )

            celebrities = response.get("CelebrityFaces", [])
            if not celebrities:
                return None

            # Take the highest-confidence match
            best = max(celebrities, key=lambda c: c.get("MatchConfidence", 0))

            urls = []
            for url in best.get("Urls", []):
                urls.append({"label": "Reference", "url": url})

            return CelebrityIdentification(
                name=best.get("Name", ""),
                confidence=best.get("MatchConfidence", 0) / 100.0,
                provider="rekognition",
                external_id=best.get("Id"),
                urls=urls,
                known_for=best.get("KnownGender", {}).get("Type"),
            )

        except Exception as exc:
            logger.warning("Rekognition celebrity detection failed: %s", exc)
            return None

    def _identify_via_local_db(self, face: Face) -> CelebrityIdentification | None:
        """Match face embedding against local celebrity embedding database."""
        if not NUMPY_AVAILABLE:
            logger.warning("numpy not available for local celebrity matching")
            return None

        if not face.embedding:
            return None

        if not self._local_db_loaded:
            if not self._load_local_celebrity_db():
                return None

        if not self._local_embeddings:
            return None

        # Deserialize face embedding
        face_emb = self._deserialize_embedding(face.embedding)
        if face_emb is None:
            return None

        face_emb_norm = face_emb / np.linalg.norm(face_emb)

        best_name = ""
        best_sim = 0.0
        best_entry = None

        for entry in self._local_embeddings:
            ref_emb = entry["embedding"]
            ref_norm = ref_emb / np.linalg.norm(ref_emb)
            similarity = float(np.dot(face_emb_norm, ref_norm))

            if similarity > best_sim:
                best_sim = similarity
                best_name = entry["name"]
                best_entry = entry

        if best_sim < self.config.ai.celebrity_min_confidence:
            return None

        urls = []
        if best_entry and best_entry.get("external_url"):
            urls.append({"label": "Reference", "url": best_entry["external_url"]})

        return CelebrityIdentification(
            name=best_name,
            confidence=best_sim,
            provider="local_db",
            external_id=best_entry.get("external_id") if best_entry else None,
            urls=urls,
        )

    def _crop_face_to_bytes(self, face: Face) -> bytes | None:
        """Crop face from source image and return as JPEG bytes.

        Uses EXIF-aware orientation. Bboxes are in oriented coordinate
        space (per OpenCV auto-rotation behavior).
        """
        try:
            from PIL import Image, ImageOps
        except ImportError:
            logger.warning("PIL not available for face cropping")
            return None

        file_record = self.db.get_file(face.file_id)
        if not file_record or not os.path.exists(file_record.path):
            return None

        try:
            raw_image = Image.open(file_record.path)
            image = ImageOps.exif_transpose(raw_image).convert("RGB")

            # Bboxes are in oriented coordinate space
            x, y, w, h = face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h

            # Add 20% padding on each side for context
            pad_x = int(w * 0.2)
            pad_y = int(h * 0.2)
            left = max(0, x - pad_x)
            top = max(0, y - pad_y)
            right = min(image.width, x + w + pad_x)
            bottom = min(image.height, y + h + pad_y)

            if right <= left or bottom <= top:
                return None

            cropped = image.crop((left, top, right, bottom))

            buf = BytesIO()
            cropped.save(buf, format="JPEG", quality=90)
            return buf.getvalue()

        except Exception as exc:
            logger.warning("Failed to crop face %d: %s", face.id or 0, exc)
            return None

    def _get_rekognition_client(self):
        """Get or create a boto3 Rekognition client."""
        if self._rekognition_client is not None:
            return self._rekognition_client

        if not BOTO3_AVAILABLE:
            return None

        from duplicleaner.utils.keystore import AIProvider, get_keystore

        creds_json = get_keystore().get_key(AIProvider.AWS)
        if not creds_json:
            logger.warning("AWS credentials not configured")
            return None

        try:
            creds = json.loads(creds_json)
            self._rekognition_client = boto3.client(
                "rekognition",
                aws_access_key_id=creds.get("access_key"),
                aws_secret_access_key=creds.get("secret_key"),
                region_name=creds.get("region", "us-east-1"),
            )
            return self._rekognition_client
        except Exception as exc:
            logger.error("Failed to create Rekognition client: %s", exc)
            return None

    def _get_local_db_path(self) -> str | None:
        """Get the path to the local celebrity embedding database."""
        models_dir = self.config.ai.models_directory
        if not models_dir:
            from duplicleaner.utils.config import get_app_data_dir
            models_dir = str(get_app_data_dir() / "models")

        db_path = os.path.join(models_dir, "celebrity_embeddings.db")
        return db_path

    def _load_local_celebrity_db(self) -> bool:
        """Load local celebrity embeddings from SQLite file."""
        import sqlite3

        db_path = self._get_local_db_path()
        if db_path is None or not os.path.exists(db_path):
            logger.warning("Local celebrity database not found at %s", db_path)
            return False

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT name, embedding, external_id, external_url FROM celebrities"
            ).fetchall()
            conn.close()

            self._local_embeddings = []
            for row in rows:
                emb = self._deserialize_embedding(row["embedding"])
                if emb is not None:
                    self._local_embeddings.append({
                        "name": row["name"],
                        "embedding": emb,
                        "external_id": row["external_id"],
                        "external_url": row["external_url"],
                    })

            self._local_db_loaded = True
            logger.info(
                "Loaded %d celebrity embeddings from local database",
                len(self._local_embeddings),
            )
            return True

        except Exception as exc:
            logger.error("Failed to load local celebrity database: %s", exc)
            return False

    def _deserialize_embedding(self, data: bytes) -> "np.ndarray | None":
        """Deserialize a face embedding from bytes to numpy array."""
        if not NUMPY_AVAILABLE or data is None:
            return None

        try:
            # InsightFace embeddings are 512 float32 values
            num_floats = len(data) // 4
            values = struct.unpack(f"{num_floats}f", data)
            return np.array(values, dtype=np.float32)
        except Exception:
            return None

    def confirm_match(self, match_id: int) -> int | None:
        """Confirm a celebrity match: create/find Person, assign face.

        Returns:
            person_id if successful, None otherwise
        """
        match = self.db.get_celebrity_match(match_id)
        if not match:
            logger.warning("Celebrity match %d not found", match_id)
            return None

        person_id = self._find_or_create_person(
            match.celebrity_name, match.provider
        )
        if person_id is None:
            return None

        self.db.assign_face_to_person(match.face_id, person_id)
        self.db.update_celebrity_match_status(match_id, "confirmed", person_id)
        self.db.update_person_photo_count(person_id)

        logger.info(
            "Confirmed celebrity match: %s (face %d -> person %d)",
            match.celebrity_name,
            match.face_id,
            person_id,
        )
        return person_id

    def reject_match(self, match_id: int) -> None:
        """Reject a celebrity match."""
        self.db.update_celebrity_match_status(match_id, "rejected")
        logger.info("Rejected celebrity match %d", match_id)

    def get_pending_matches(self) -> list[CelebrityMatch]:
        """Get all matches awaiting user review."""
        return self.db.get_pending_celebrity_matches()

    def _find_or_create_person(
        self, name: str, source: str
    ) -> int | None:
        """Find an existing person by name or create a new one.

        Case-insensitive name matching to avoid duplicates.

        Returns:
            person_id
        """
        # Search for existing person with same name (case-insensitive)
        all_persons = self.db.get_all_persons(named_only=True, include_hidden=False)
        for person in all_persons:
            if person.name and person.name.lower() == name.lower():
                return person.id

        # Create new person
        new_person = Person(
            name=name,
            identification_source=source,
        )
        person_id = self.db.add_person(new_person)
        logger.info("Created new person '%s' from %s (id=%d)", name, source, person_id)
        return person_id
