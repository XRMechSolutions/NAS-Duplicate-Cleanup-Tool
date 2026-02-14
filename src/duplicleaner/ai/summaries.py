"""AI summary generation for images and documents.

Supports OpenAI, Anthropic, local Ollama, and LMStudio endpoints.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from duplicleaner.db.database import Database
from duplicleaner.db.models import AISummary, FileRecord, TagCategory, TagSource
from duplicleaner.utils.config import get_config
from duplicleaner.utils.keystore import AIProvider, get_keystore
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SummaryProgress:
    """Progress tracking for summary generation."""
    total_files: int = 0
    processed_files: int = 0
    current_file: str = ""
    phase: str = "initializing"

    @property
    def percent_complete(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


class SummaryEngine:
    """Generate AI summaries for images."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.config = get_config()
        self.keystore = get_keystore()
        self.progress = SummaryProgress()
        self._cached_lmstudio_model: str | None = None

    def _get_lmstudio_loaded_model(self, base_url: str, force: bool = False) -> str | None:
        """Query LM Studio to get the currently loaded model identifier.

        Caches the result so batch runs don't query /api/v1/models per file.
        Pass force=True to refresh the cache.
        """
        if self._cached_lmstudio_model and not force:
            return self._cached_lmstudio_model
        try:
            models_url = f"{base_url}/api/v1/models"
            req = urllib.request.Request(models_url, method="GET")

            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            # LM Studio 0.4+ API format: {"models": [{...}, {...}]}
            if "models" in result and isinstance(result["models"], list):
                # Find models with loaded_instances
                for model in result["models"]:
                    if isinstance(model, dict):
                        loaded_instances = model.get("loaded_instances", [])
                        if loaded_instances and len(loaded_instances) > 0:
                            # Use the 'key' field as the model identifier
                            model_key = model.get("key")
                            if model_key:
                                logger.debug("Detected loaded LMStudio model: %s", model_key)
                                self._cached_lmstudio_model = model_key
                                return model_key

            # Fallback: check older API format {"data": [...]}
            if "data" in result and isinstance(result["data"], list) and len(result["data"]) > 0:
                model_id = result["data"][0].get("id")
                if model_id:
                    logger.debug("Detected loaded LMStudio model: %s", model_id)
                    self._cached_lmstudio_model = model_id
                    return model_id

            logger.warning("No loaded models found in LMStudio. Make sure a model is loaded and server is started.")
            return None

        except Exception as exc:
            logger.warning("Failed to query LMStudio loaded models: %s", exc)
            return None

    def is_available(self) -> bool:
        provider = self.config.ai.summary_provider
        if provider == "local":
            return True
        if provider == "lmstudio":
            return True
        if provider == "openai":
            return self.keystore.has_key(AIProvider.OPENAI)
        if provider == "anthropic":
            return self.keystore.has_key(AIProvider.ANTHROPIC)
        if provider == "google":
            return self.keystore.has_key(AIProvider.GOOGLE)
        return False

    def analyze_file(self, file_record: FileRecord) -> AISummary | None:
        if not file_record.id:
            return None

        ext = (file_record.file_type or "").lower()
        doc_exts = set(self.config.ai.analysis_doc_extensions)
        data_exts = set(self.config.ai.analysis_data_extensions)

        if file_record.is_image:
            summary_text = self._generate_summary(file_record.path, file_id=file_record.id)
            if not summary_text:
                return None

            # Collect people and pet names for metadata storage
            face_annotations = self._get_face_annotations(file_record.id) if file_record.id else []
            people_list = [name for name, _bbox in face_annotations if name != "Unknown"]
            pet_annotations = self._get_pet_annotations(file_record.id) if file_record.id else []
            pets_list = [name for name, _species, _bbox in pet_annotations]

            summary = AISummary(
                file_id=file_record.id,
                summary=summary_text,
                summary_model=self.config.ai.get_summary_model(),
                people_mentioned=json.dumps(people_list) if people_list else None,
                pets_mentioned=json.dumps(pets_list) if pets_list else None,
                generated_at=datetime.now(),
                user_edited=False,
            )
            self.db.add_ai_summary(summary)

            # Auto-tag file with pet names for search
            if pets_list:
                try:
                    self.db.add_file_tags_batch(
                        file_record.id, pets_list,
                        category=TagCategory.PET,
                        source=TagSource.AI,
                    )
                except Exception as tag_err:
                    logger.warning("Failed to auto-tag pets: %s", tag_err)

            return summary

        if ext in doc_exts or ext in data_exts or file_record.is_document:
            text = self._get_document_text(file_record.id)
            if not text:
                return None
            doc_summary = self._generate_text_summary(text, file_path=file_record.path)
            if not doc_summary:
                return None
            summary = AISummary(
                file_id=file_record.id,
                document_summary=doc_summary,
                summary_model=self.config.ai.get_summary_model(),
                generated_at=datetime.now(),
                user_edited=False,
            )
            self.db.add_ai_summary(summary)
            return summary

        return None

    def analyze_batch(self, file_records: list[FileRecord]) -> int:
        self.progress = SummaryProgress(
            total_files=len(file_records),
            phase="summarizing",
        )
        generated = 0
        for i, file_record in enumerate(file_records):
            self.progress.processed_files = i + 1
            self.progress.current_file = file_record.path
            if self.analyze_file(file_record):
                generated += 1
        self.progress.phase = "complete"
        return generated

    # Local models (LM Studio, Ollama) work best with smaller images.
    # Cloud APIs can handle larger dimensions.
    LOCAL_MAX_IMAGE_DIM = 1024

    def _get_face_annotations(
        self, file_id: int,
    ) -> list[tuple[str, tuple[int, int, int, int]]]:
        """Get identified face names and bounding boxes for a file.

        Returns list of (name, (x, y, w, h)) tuples. Hidden/ignored persons
        are excluded. Unassigned faces are included as "Unknown".
        """
        try:
            faces = self.db.get_faces_for_file(file_id)
        except Exception as exc:
            logger.warning("Failed to get faces for file %d: %s", file_id, exc)
            return []

        logger.info(
            "Face annotations for file %d: %d face(s) found",
            file_id, len(faces),
        )

        annotations: list[tuple[str, tuple[int, int, int, int]]] = []
        for face in faces:
            bbox = (face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h)
            if face.person_id:
                person = self.db.get_person(face.person_id)
                if person and person.is_hidden:
                    logger.debug("Skipping hidden person %d", face.person_id)
                    continue
                name = person.name if person and person.name else "Unknown"
                logger.info(
                    "Face %s -> person_id=%s, name='%s', bbox=%s",
                    face.id, face.person_id, name, bbox,
                )
            else:
                name = "Unknown"
                logger.debug("Face %s has no person_id", face.id)
            annotations.append((name, bbox))
        return annotations

    def _get_pet_annotations(
        self, file_id: int,
    ) -> list[tuple[str, str, tuple[int, int, int, int]]]:
        """Get identified pet names, species, and bounding boxes for a file.

        Returns list of (name, species, (x, y, w, h)) tuples.
        Only includes assigned detections with named pets.
        """
        try:
            detections = self.db.get_pet_detections_for_file(file_id)
        except Exception as exc:
            logger.warning("Failed to get pet detections for file %d: %s", file_id, exc)
            return []

        annotations: list[tuple[str, str, tuple[int, int, int, int]]] = []
        for detection in detections:
            bbox = (detection.bbox_x, detection.bbox_y, detection.bbox_w, detection.bbox_h)
            if detection.pet_id:
                pet = self.db.get_pet(detection.pet_id)
                if pet and pet.name:
                    species = pet.species or detection.species or ""
                    annotations.append((pet.name, species, bbox))
        return annotations

    @staticmethod
    def _transform_point(
        pt: tuple[float, float],
        orientation: int,
        width: int,
        height: int,
    ) -> tuple[float, float]:
        """Map a point from raw image coords to EXIF-oriented coords."""
        x, y = pt
        if orientation == 1:
            return (x, y)
        if orientation == 2:
            return (width - x, y)
        if orientation == 3:
            return (width - x, height - y)
        if orientation == 4:
            return (x, height - y)
        if orientation == 5:
            return (y, x)
        if orientation == 6:
            return (height - y, x)
        if orientation == 7:
            return (height - y, width - x)
        if orientation == 8:
            return (y, width - x)
        return (x, y)

    @staticmethod
    def _orient_bbox(
        bbox: tuple[int, int, int, int],
        orientation: int,
        raw_w: int,
        raw_h: int,
    ) -> tuple[int, int, int, int]:
        """Transform a raw bbox into EXIF-oriented image coordinates."""
        x, y, bw, bh = bbox
        corners = [(x, y), (x + bw, y), (x, y + bh), (x + bw, y + bh)]
        mapped = [
            SummaryEngine._transform_point(pt, orientation, raw_w, raw_h)
            for pt in corners
        ]
        xs = [p[0] for p in mapped]
        ys = [p[1] for p in mapped]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return (int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y))

    @staticmethod
    def _draw_face_labels(
        img,  # PIL Image (already EXIF-transposed, RGB)
        annotations: list[tuple[str, tuple[int, int, int, int]]],
        orientation: int,
        raw_w: int,
        raw_h: int,
    ):
        """Draw labeled bounding boxes on the image for identified faces.

        Returns a new PIL Image with annotations drawn.
        """
        from PIL import ImageDraw, ImageFont

        img = img.copy()
        draw = ImageDraw.Draw(img)

        # Try to get a readable font; fall back to default
        font_size = max(14, min(img.width, img.height) // 40)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()

        for name, bbox in annotations:
            # Transform bbox from raw coords to oriented coords
            ox, oy, ow, oh = SummaryEngine._orient_bbox(
                bbox, orientation, raw_w, raw_h,
            )

            # Scale bbox if image was resized (bbox is in original pixel coords)
            # The image passed here has already been resized by _load_image_base64,
            # so we need to know the oriented dimensions to compute the scale factor.
            if orientation in (5, 6, 7, 8):
                oriented_w, oriented_h = raw_h, raw_w
            else:
                oriented_w, oriented_h = raw_w, raw_h

            sx = img.width / oriented_w if oriented_w else 1.0
            sy = img.height / oriented_h if oriented_h else 1.0

            x1 = int(ox * sx)
            y1 = int(oy * sy)
            x2 = int((ox + ow) * sx)
            y2 = int((oy + oh) * sy)

            # Draw box
            box_color = (0, 200, 0) if name != "Unknown" else (200, 200, 0)
            draw.rectangle([x1, y1, x2, y2], outline=box_color, width=2)

            # Draw name label background + text above the box
            if name != "Unknown":
                text_bbox = draw.textbbox((0, 0), name, font=font)
                tw = text_bbox[2] - text_bbox[0]
                th = text_bbox[3] - text_bbox[1]
                label_y = max(0, y1 - th - 4)
                draw.rectangle(
                    [x1, label_y, x1 + tw + 6, label_y + th + 4],
                    fill=box_color,
                )
                draw.text((x1 + 3, label_y + 2), name, fill=(0, 0, 0), font=font)

        return img

    def _generate_summary(
        self, image_path: str, *, file_id: int | None = None,
        original_path: str | None = None,
    ) -> str | None:
        provider = self.config.ai.summary_provider
        model = self.config.ai.get_summary_model()

        # Look up identified faces to enrich the prompt and annotate the image
        face_annotations = self._get_face_annotations(file_id) if file_id else []
        named_people = [name for name, _bbox in face_annotations if name != "Unknown"]

        # Look up identified pets
        pet_annotations = self._get_pet_annotations(file_id) if file_id else []
        named_pets = [(name, species) for name, species, _bbox in pet_annotations]

        context_path = original_path or image_path
        logger.info(
            "Summary for file_id=%s, path=%s: %d face annotations, %d pet annotations",
            file_id, context_path, len(face_annotations), len(pet_annotations),
        )

        # Include file path for folder-name context (e.g. "Vacation 2024", "Birthday")
        path_context = f"File path: {context_path}\n"

        # Build context about identified entities
        context_parts = []
        if named_people:
            names_str = ", ".join(named_people)
            context_parts.append(
                f"The following people have been identified: {names_str}. "
                "Their faces are marked with labeled boxes in the image. "
                "Please refer to them by name."
            )
        if named_pets:
            pets_str = ", ".join(
                f"{name} the {species}" if species else name
                for name, species in named_pets
            )
            context_parts.append(
                f"The following pets have been identified: {pets_str}. "
                "Please refer to them by name."
            )

        if context_parts:
            prompt = (
                path_context
                + " ".join(context_parts) + " "
                "Describe this image in 2-3 sentences. Include: "
                "1) Overall contents and setting, "
                "2) What the identified people/pets are doing (use their names), "
                "3) Key points or notable elements. "
                "You may use context from the folder names and file name to enrich your description, "
                "but do not mention the file path itself."
            )
        else:
            prompt = (
                path_context
                + "Describe this image in 2-3 sentences. Include: "
                "1) Overall contents and setting, "
                "2) Key points or notable elements, "
                "3) Any people visible (mention if you can identify characteristics but not specific identities). "
                "You may use context from the folder names and file name to enrich your description, "
                "but do not mention the file path itself."
            )

        # Use smaller images for local models to avoid processing failures
        max_dim = None
        if provider in ("lmstudio", "local"):
            max_dim = self.LOCAL_MAX_IMAGE_DIM

        image_b64, media_type = self._load_image_base64(
            image_path, max_dim=max_dim, face_annotations=face_annotations,
        )
        if not image_b64:
            logger.warning("Could not load image for summary: %s", image_path)
            return None

        result = None
        if provider == "local":
            result = self._summarize_ollama(model, prompt, image_b64)
        elif provider == "lmstudio":
            result = self._summarize_lmstudio(model, prompt, image_b64, media_type)
        elif provider == "openai":
            key = self.keystore.get_key(AIProvider.OPENAI)
            if not key:
                return None
            result = self._summarize_openai(model, key, prompt, image_b64, media_type)
        elif provider == "anthropic":
            key = self.keystore.get_key(AIProvider.ANTHROPIC)
            if not key:
                return None
            result = self._summarize_anthropic(model, key, prompt, image_b64, media_type)
        else:
            logger.warning("Unsupported summary provider: %s", provider)
            return None

        if not result:
            logger.warning("Summary generation returned empty for: %s", image_path)
        return result

    def _get_document_text(self, file_id: int) -> str | None:
        result = self.db.get_ocr_result(file_id)
        if not result or not result.extracted_text:
            return None
        return result.extracted_text

    def _generate_text_summary(self, text: str, *, file_path: str = "") -> str | None:
        provider = self.config.ai.summary_provider
        model = self.config.ai.get_summary_model()
        path_context = f"File path: {file_path}\n" if file_path else ""
        prompt = (
            path_context
            + "Summarize this document in 2-3 sentences. Include: "
            "1) Overall contents and purpose, "
            "2) Key points or main takeaways, "
            "3) Any people or entities mentioned. "
            "You may use context from the folder names and file name to enrich your summary, "
            "but do not mention the file path itself."
        )
        snippet = text[:8000]

        if provider == "local":
            return self._summarize_ollama_text(model, prompt, snippet)
        if provider == "lmstudio":
            return self._summarize_lmstudio_text(model, prompt, snippet)
        if provider == "openai":
            key = self.keystore.get_key(AIProvider.OPENAI)
            if not key:
                return None
            return self._summarize_openai_text(model, key, prompt, snippet)
        if provider == "anthropic":
            key = self.keystore.get_key(AIProvider.ANTHROPIC)
            if not key:
                return None
            return self._summarize_anthropic_text(model, key, prompt, snippet)

        return None

    # Formats that LM Studio / llama.cpp can decode natively via stb_image
    _NATIVE_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/bmp"}

    def _load_image_base64(
        self,
        image_path: str,
        *,
        max_dim: int | None = None,
        face_annotations: list[tuple[str, tuple[int, int, int, int]]] | None = None,
    ) -> tuple[str | None, str]:
        """Load image and return as base64.

        Args:
            image_path: Path to the image file.
            max_dim: Override for maximum pixel dimension.  Falls back
                     to ``config.ai.max_image_dimension`` when *None*.
            face_annotations: Optional face name/bbox pairs to draw on image.

        For JPEG/PNG files that are already within the size limit, the
        raw file bytes are sent directly -- no re-encoding through PIL.
        This avoids edge cases where PIL's output confuses stb_image.

        For HEIC, BMP, TIFF, WebP, oversized images, or images needing
        rotation, PIL is used to convert to PNG.
        """
        try:
            import io

            from PIL import Image, ImageOps

            limit = max_dim or self.config.ai.max_image_dimension
            original_mime = mimetypes.guess_type(image_path)[0] or ""
            has_annotations = bool(face_annotations)

            # --- Fast path: send raw bytes for JPEG/PNG under size limit ---
            # Skip fast path when we need to draw face annotations
            if original_mime in ("image/jpeg", "image/png") and not has_annotations:
                img = Image.open(image_path)
                img.load()

                # Check if we can skip PIL re-encoding
                needs_processing = False
                if img.width > limit or img.height > limit:
                    needs_processing = True

                # Check EXIF orientation (anything other than 1/None means rotated)
                exif = img.getexif()
                orientation = exif.get(0x0112)  # EXIF Orientation tag
                if orientation and orientation != 1:
                    needs_processing = True

                if not needs_processing:
                    # Read raw bytes directly -- no PIL re-encoding
                    with open(image_path, "rb") as f:
                        raw_bytes = f.read()
                    encoded = base64.b64encode(raw_bytes).decode("utf-8")
                    logger.debug(
                        "Image raw: %dx%d %s (%.1f KB payload): %s",
                        img.width, img.height, original_mime,
                        len(raw_bytes) / 1024, image_path,
                    )
                    return encoded, original_mime

            # --- Slow path: PIL conversion needed ---
            img = Image.open(image_path)
            try:
                img.load()
            except Exception as load_exc:
                logger.warning("Corrupt or unreadable image (load failed): %s -- %s", image_path, load_exc)
                return None, "image/jpeg"

            # Capture raw dimensions and EXIF orientation before transpose
            raw_w, raw_h = img.size
            exif = img.getexif()
            orientation = exif.get(0x0112, 1) or 1

            # Auto-rotate based on EXIF orientation tag
            img = ImageOps.exif_transpose(img)

            # Convert palette/RGBA modes
            if img.mode in ("P", "PA"):
                img = img.convert("RGBA")
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Resize if needed
            if img.width > limit or img.height > limit:
                img.thumbnail((limit, limit), Image.LANCZOS)
                logger.debug("Resized image to %dx%d: %s", img.width, img.height, image_path)

            # Draw face labels on the image
            if has_annotations:
                img = self._draw_face_labels(
                    img, face_annotations, orientation, raw_w, raw_h,
                )

            # Save as PNG -- avoids JPEG-specific encoding quirks that
            # can trip up stb_image in some llama.cpp builds.
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            payload_bytes = buf.getvalue()
            encoded = base64.b64encode(payload_bytes).decode("utf-8")
            logger.debug(
                "Image converted: %dx%d PNG (%.1f KB payload): %s",
                img.width, img.height,
                len(payload_bytes) / 1024, image_path,
            )
            return encoded, "image/png"

        except Exception as exc:
            logger.warning("Failed to load image for summary: %s", exc)
            return None, "image/jpeg"

    @staticmethod
    def _extract_lmstudio_output(result: dict) -> str | None:
        """Extract text content from an LMStudio v1 API response.

        The v1 API returns 'output' as a list of message objects:
            {"output": [{"type": "message", "content": "..."}]}
        Older versions may return a plain string or use 'response'/'message' keys.
        """
        output = result.get("output")
        if output is not None:
            if isinstance(output, list):
                for item in output:
                    if isinstance(item, dict):
                        content = item.get("content")
                        if content and isinstance(content, str):
                            return content.strip()
                logger.warning("LMStudio output list had no usable content: %s", output)
                return None
            if isinstance(output, str):
                return output.strip() or None

        # Fallback keys for older API versions
        for key in ("response", "message"):
            val = result.get(key)
            if val and isinstance(val, str):
                return val.strip()

        return None

    def _summarize_openai(
        self,
        model: str,
        api_key: str,
        prompt: str,
        image_b64: str,
        media_type: str,
    ) -> str | None:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}},
                    ],
                }
            ],
            "max_tokens": self.config.ai.summary_max_tokens,
            "temperature": self.config.ai.summary_temperature,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("OpenAI summary failed: %s", exc)
            return None

    def _summarize_anthropic(
        self,
        model: str,
        api_key: str,
        prompt: str,
        image_b64: str,
        media_type: str,
    ) -> str | None:
        payload = {
            "model": model,
            "max_tokens": self.config.ai.summary_max_tokens,
            "temperature": self.config.ai.summary_temperature,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    ],
                }
            ],
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            content = result.get("content", [])
            if content:
                return content[0].get("text", "").strip() or None
            return None
        except Exception as exc:
            logger.warning("Anthropic summary failed: %s", exc)
            return None

    def _summarize_ollama(
        self,
        model: str,
        prompt: str,
        image_b64: str,
    ) -> str | None:
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return str(result.get("response", "")).strip() or None
        except Exception as exc:
            logger.warning("Local summary failed: %s", exc)
            return None

    def _summarize_lmstudio(
        self,
        model: str,
        prompt: str,
        image_b64: str,
        media_type: str,
    ) -> str | None:
        """LMStudio vision model image analysis.

        Uses the OpenAI-compatible /v1/chat/completions endpoint for
        images. The native /api/v1/chat has a known issue where image
        processing fails and can crash the model's inference channel.
        """
        import time

        base_url = self.config.ai.lmstudio_base_url.rstrip("/")

        # Remove /v1 suffix if present to get base URL
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]

        # If no model specified, get the currently loaded model
        if not model:
            model = self._get_lmstudio_loaded_model(base_url)
            if not model:
                logger.warning("No model loaded in LMStudio and none specified in config")
                return None

        data_url = f"data:{media_type};base64,{image_b64}"

        # OpenAI-compatible /v1/chat/completions -- reliable for vision
        url = f"{base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "max_tokens": self.config.ai.summary_max_tokens,
            "temperature": self.config.ai.summary_temperature,
        }
        data = json.dumps(payload).encode("utf-8")

        max_retries = 2
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read().decode("utf-8"))

                text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if text:
                    return text

                logger.warning("Unexpected LMStudio response: %s", list(result.keys()))
                return None

            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8") if exc.fp else "No error details"
                if exc.code == 500 and attempt < max_retries - 1:
                    logger.info(
                        "LMStudio HTTP 500, retrying in 3s (attempt %d/%d, payload: %.1f KB)",
                        attempt + 1, max_retries, len(data) / 1024,
                    )
                    time.sleep(3)
                    continue
                logger.warning(
                    "LMStudio summary failed (HTTP %s): %s | URL: %s | model: %s | payload: %.1f KB",
                    exc.code, error_body, url,
                    model or "(using loaded model)",
                    len(data) / 1024,
                )
                return None
            except Exception as exc:
                logger.warning("LMStudio summary failed: %s", exc)
                return None

        return None

    def _summarize_openai_text(
        self,
        model: str,
        api_key: str,
        prompt: str,
        text: str,
    ) -> str | None:
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": f"{prompt}\n\n{text}"},
            ],
            "max_tokens": self.config.ai.summary_max_tokens,
            "temperature": self.config.ai.summary_temperature,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("OpenAI text summary failed: %s", exc)
            return None

    def _summarize_anthropic_text(
        self,
        model: str,
        api_key: str,
        prompt: str,
        text: str,
    ) -> str | None:
        payload = {
            "model": model,
            "max_tokens": self.config.ai.summary_max_tokens,
            "temperature": self.config.ai.summary_temperature,
            "messages": [
                {"role": "user", "content": f"{prompt}\n\n{text}"},
            ],
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            content = result.get("content", [])
            if content:
                return content[0].get("text", "").strip() or None
            return None
        except Exception as exc:
            logger.warning("Anthropic text summary failed: %s", exc)
            return None

    def _summarize_ollama_text(
        self,
        model: str,
        prompt: str,
        text: str,
    ) -> str | None:
        payload = {
            "model": model,
            "prompt": f"{prompt}\n\n{text}",
            "stream": False,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return str(result.get("response", "")).strip() or None
        except Exception as exc:
            logger.warning("Local text summary failed: %s", exc)
            return None

    def _summarize_lmstudio_text(
        self,
        model: str,
        prompt: str,
        text: str,
    ) -> str | None:
        """LMStudio native v1 API for text summarization."""
        base_url = self.config.ai.lmstudio_base_url.rstrip("/")

        # Remove /v1 suffix if present
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]

        url = f"{base_url}/api/v1/chat"

        # If no model specified, get the currently loaded model
        if not model:
            model = self._get_lmstudio_loaded_model(base_url)
            if not model:
                logger.warning("No model loaded in LMStudio and none specified in config")
                return None

        payload = {
            "model": model,
            "input": [
                {
                    "type": "text",
                    "content": f"{prompt}\n\n{text}"
                }
            ],
            "max_output_tokens": self.config.ai.summary_max_tokens,
            "temperature": self.config.ai.summary_temperature,
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            # Extract from native v1 API response
            text = self._extract_lmstudio_output(result)
            if text:
                return text

            logger.warning("Unexpected LMStudio text response format: %s", list(result.keys()))
            return None

        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode('utf-8') if exc.fp else "No error details"
            logger.warning("LMStudio text summary failed (HTTP %s): %s", exc.code, error_body)
            return None
        except Exception as exc:
            logger.warning("LMStudio text summary failed: %s", exc)
            return None

    def summarize_video_frame(
        self,
        image_b64: str,
        media_type: str,
        frame_number: int,
        total_frames: int,
        *,
        file_path: str = "",
    ) -> str | None:
        """Send a single video frame to the vision model for description."""
        provider = self.config.ai.summary_provider
        model = self.config.ai.get_summary_model()
        path_context = f"File path: {file_path}\n" if file_path else ""
        prompt = (
            path_context
            + f"This is frame {frame_number} of {total_frames} from a video. "
            "Describe what you see in 1-2 sentences: the setting, actions, "
            "people, and notable objects."
        )

        if provider == "local":
            return self._summarize_ollama(model, prompt, image_b64)
        if provider == "lmstudio":
            return self._summarize_lmstudio(model, prompt, image_b64, media_type)
        if provider == "openai":
            key = self.keystore.get_key(AIProvider.OPENAI)
            if not key:
                return None
            return self._summarize_openai(model, key, prompt, image_b64, media_type)
        if provider == "anthropic":
            key = self.keystore.get_key(AIProvider.ANTHROPIC)
            if not key:
                return None
            return self._summarize_anthropic(model, key, prompt, image_b64, media_type)

        return None

    def summarize_video_combined(
        self, frame_descriptions: str, *, file_path: str = "",
    ) -> str | None:
        """Combine per-frame descriptions into a cohesive video summary."""
        prompt = (
            "Below are descriptions of individual frames extracted from a video. "
            "Write a concise 2-3 sentence summary of the entire video based on "
            "these frame descriptions. Focus on what happens, who is present, "
            "and the overall setting.\n\n"
        )
        return self._generate_text_summary(prompt + frame_descriptions, file_path=file_path)
