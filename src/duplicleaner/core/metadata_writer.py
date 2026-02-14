"""Metadata writer for embedding AI data into image files.

Writes face names, tags, summaries, and quality scores back into image
metadata (EXIF/IPTC/XMP) so the data travels with the file.

Uses piexif for basic EXIF writes (pure Python) and exiftool subprocess
for full XMP/IPTC/MWG face region support when available.
"""

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Check for piexif
try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

# Check for exiftool on PATH
_exiftool_path: str | None = None


def _find_exiftool() -> str | None:
    """Find exiftool executable."""
    global _exiftool_path
    if _exiftool_path is not None:
        return _exiftool_path if _exiftool_path else None
    path = shutil.which("exiftool")
    _exiftool_path = path or ""
    if path:
        logger.info("Found exiftool at: %s", path)
    else:
        logger.debug("exiftool not found on PATH")
    return path


HAS_EXIFTOOL = _find_exiftool() is not None


@dataclass
class FaceRegion:
    """A face region to write into MWG metadata."""
    name: str
    x: float  # center x, normalized 0-1
    y: float  # center y, normalized 0-1
    w: float  # width, normalized 0-1
    h: float  # height, normalized 0-1


@dataclass
class MetadataPayload:
    """Data to write into an image file's metadata."""
    summary: str | None = None
    keywords: list[str] = field(default_factory=list)
    face_regions: list[FaceRegion] = field(default_factory=list)
    person_names: list[str] = field(default_factory=list)
    quality_rating: int | None = None  # 1-5 star rating
    hierarchical_tags: list[str] = field(default_factory=list)  # "AI|Scene|Beach"


@dataclass
class WriteResult:
    """Result of a metadata write operation."""
    success: bool
    file_path: str
    method: str  # "exiftool" or "piexif"
    fields_written: list[str] = field(default_factory=list)
    error: str | None = None


def bbox_to_mwg(
    bbox_x: int, bbox_y: int, bbox_w: int, bbox_h: int,
    image_width: int, image_height: int,
) -> FaceRegion:
    """Convert pixel bbox (x, y, w, h) to MWG normalized face region.

    Face bboxes in DupliCleaner are in oriented (displayed) coordinates,
    which is correct for MWG regions.

    Args:
        bbox_x, bbox_y: Top-left corner in pixels
        bbox_w, bbox_h: Width and height in pixels
        image_width, image_height: Image dimensions in pixels

    Returns:
        FaceRegion with normalized center+size coordinates
    """
    center_x = (bbox_x + bbox_w / 2) / image_width
    center_y = (bbox_y + bbox_h / 2) / image_height
    norm_w = bbox_w / image_width
    norm_h = bbox_h / image_height
    return FaceRegion(
        name="",
        x=round(center_x, 6),
        y=round(center_y, 6),
        w=round(norm_w, 6),
        h=round(norm_h, 6),
    )


def write_metadata_exiftool(
    file_path: str | Path,
    payload: MetadataPayload,
    backup: bool = True,
    dry_run: bool = False,
) -> WriteResult:
    """Write metadata using exiftool subprocess.

    This is the most robust method, supporting EXIF, IPTC, XMP, and MWG
    face regions across all image formats.

    Args:
        file_path: Path to the image file
        payload: Metadata to write
        backup: Create backup before writing (exiftool -overwrite_original to skip)
        dry_run: If True, return what would be written without modifying

    Returns:
        WriteResult with success status and details
    """
    exiftool = _find_exiftool()
    if not exiftool:
        return WriteResult(
            success=False,
            file_path=str(file_path),
            method="exiftool",
            error="exiftool not found on PATH",
        )

    file_path = Path(file_path)
    if not file_path.exists():
        return WriteResult(
            success=False,
            file_path=str(file_path),
            method="exiftool",
            error="File not found",
        )

    args = [exiftool]
    fields_written = []

    if not backup:
        args.append("-overwrite_original")

    # Summary -> multiple fields for maximum compatibility
    if payload.summary:
        # Truncate to reasonable lengths per field
        short_summary = payload.summary[:2000]
        args.extend([f"-ImageDescription={short_summary}"])
        args.extend([f"-IPTC:Caption-Abstract={short_summary}"])
        args.extend([f"-XMP:Description={short_summary}"])
        fields_written.extend(["ImageDescription", "IPTC:Caption-Abstract", "XMP:Description"])

    # Keywords -> IPTC Keywords + XMP Subject
    for kw in payload.keywords:
        args.extend([f"-IPTC:Keywords+={kw}"])
        args.extend([f"-XMP:Subject+={kw}"])
    if payload.keywords:
        fields_written.extend(["IPTC:Keywords", "XMP:Subject"])

    # Hierarchical tags -> Lightroom format
    for tag in payload.hierarchical_tags:
        args.extend([f"-XMP:HierarchicalSubject+={tag}"])
    if payload.hierarchical_tags:
        fields_written.append("XMP:HierarchicalSubject")

    # Person names
    for name in payload.person_names:
        args.extend([f"-XMP:PersonInImage+={name}"])
    if payload.person_names:
        fields_written.append("XMP:PersonInImage")

    # Quality rating -> XMP Rating (1-5)
    if payload.quality_rating is not None:
        rating = max(1, min(5, payload.quality_rating))
        args.extend([f"-XMP:Rating={rating}"])
        fields_written.append("XMP:Rating")

    # Face regions using MWG standard
    if payload.face_regions:
        # exiftool handles MWG regions via structured tags
        for i, face in enumerate(payload.face_regions):
            args.extend([
                f"-RegionName={face.name}",
                f"-RegionType=Face",
                f"-RegionAreaX={face.x}",
                f"-RegionAreaY={face.y}",
                f"-RegionAreaW={face.w}",
                f"-RegionAreaH={face.h}",
                f"-RegionAreaUnit=normalized",
            ])
        fields_written.append("MWG:Regions")

    if not fields_written:
        return WriteResult(
            success=True,
            file_path=str(file_path),
            method="exiftool",
            fields_written=[],
        )

    if dry_run:
        return WriteResult(
            success=True,
            file_path=str(file_path),
            method="exiftool (dry run)",
            fields_written=fields_written,
        )

    args.append(str(file_path))

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return WriteResult(
                success=False,
                file_path=str(file_path),
                method="exiftool",
                fields_written=fields_written,
                error=result.stderr.strip(),
            )

        logger.info("Wrote metadata to %s via exiftool: %s", file_path.name, fields_written)
        return WriteResult(
            success=True,
            file_path=str(file_path),
            method="exiftool",
            fields_written=fields_written,
        )

    except subprocess.TimeoutExpired:
        return WriteResult(
            success=False,
            file_path=str(file_path),
            method="exiftool",
            error="exiftool timed out after 30s",
        )
    except Exception as exc:
        return WriteResult(
            success=False,
            file_path=str(file_path),
            method="exiftool",
            error=str(exc),
        )


def write_metadata_piexif(
    file_path: str | Path,
    payload: MetadataPayload,
    dry_run: bool = False,
) -> WriteResult:
    """Write EXIF metadata using piexif (JPEG only, EXIF fields only).

    Fallback for when exiftool is not available. Only supports basic EXIF
    fields (ImageDescription, UserComment, XPKeywords). Does not support
    IPTC, XMP, or MWG face regions.

    Args:
        file_path: Path to the JPEG file
        payload: Metadata to write
        dry_run: If True, return what would be written without modifying

    Returns:
        WriteResult with success status and details
    """
    if not HAS_PIEXIF:
        return WriteResult(
            success=False,
            file_path=str(file_path),
            method="piexif",
            error="piexif not installed",
        )

    file_path = Path(file_path)
    if not file_path.exists():
        return WriteResult(
            success=False,
            file_path=str(file_path),
            method="piexif",
            error="File not found",
        )

    if file_path.suffix.lower() not in (".jpg", ".jpeg"):
        return WriteResult(
            success=False,
            file_path=str(file_path),
            method="piexif",
            error="piexif only supports JPEG files",
        )

    fields_written = []

    try:
        # Read existing EXIF to preserve it
        try:
            exif_dict = piexif.load(str(file_path))
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

        # Summary -> ImageDescription (0th IFD)
        if payload.summary:
            short = payload.summary[:2000]
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = short.encode("utf-8")
            fields_written.append("ImageDescription")

            # UserComment in Exif IFD (supports longer text)
            user_comment = b"ASCII\x00\x00\x00" + payload.summary[:8000].encode("utf-8")
            exif_dict["Exif"][piexif.ExifIFD.UserComment] = user_comment
            fields_written.append("UserComment")

        # Keywords -> XPKeywords (Windows)
        if payload.keywords:
            kw_text = ";".join(payload.keywords)
            exif_dict["0th"][piexif.ImageIFD.XPKeywords] = kw_text.encode("utf-16le")
            fields_written.append("XPKeywords")

        # Person names -> XPSubject
        if payload.person_names:
            subj_text = "; ".join(payload.person_names)
            exif_dict["0th"][piexif.ImageIFD.XPSubject] = subj_text.encode("utf-16le")
            fields_written.append("XPSubject")

        if not fields_written:
            return WriteResult(
                success=True,
                file_path=str(file_path),
                method="piexif",
                fields_written=[],
            )

        if dry_run:
            return WriteResult(
                success=True,
                file_path=str(file_path),
                method="piexif (dry run)",
                fields_written=fields_written,
            )

        # Write back
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(file_path))

        logger.info("Wrote metadata to %s via piexif: %s", file_path.name, fields_written)
        return WriteResult(
            success=True,
            file_path=str(file_path),
            method="piexif",
            fields_written=fields_written,
        )

    except Exception as exc:
        return WriteResult(
            success=False,
            file_path=str(file_path),
            method="piexif",
            error=str(exc),
        )


def write_metadata(
    file_path: str | Path,
    payload: MetadataPayload,
    prefer_exiftool: bool = True,
    backup: bool = True,
    dry_run: bool = False,
) -> WriteResult:
    """Write metadata to an image file using the best available method.

    Tries exiftool first (most robust), falls back to piexif for JPEG files.

    Args:
        file_path: Path to the image file
        payload: Metadata to write
        prefer_exiftool: Try exiftool first if available
        backup: Create backup before writing (exiftool only)
        dry_run: Preview what would be written without modifying

    Returns:
        WriteResult with success status and details
    """
    if prefer_exiftool and _find_exiftool():
        return write_metadata_exiftool(file_path, payload, backup=backup, dry_run=dry_run)
    return write_metadata_piexif(file_path, payload, dry_run=dry_run)


def build_payload_for_file(
    db: "Database",
    file_id: int,
    include_summary: bool = True,
    include_tags: bool = True,
    include_faces: bool = True,
    include_quality: bool = True,
    tag_prefix: str = "AI",
) -> MetadataPayload:
    """Build a MetadataPayload from database data for a given file.

    Gathers AI summaries, tags, face names, quality scores, etc. from the
    database and constructs a payload suitable for writing to the file.

    Args:
        db: Database instance
        file_id: File ID to gather data for
        include_summary: Include AI summary text
        include_tags: Include tags as keywords
        include_faces: Include face names and regions
        include_quality: Include quality score as star rating
        tag_prefix: Prefix for hierarchical tags (e.g., "AI")

    Returns:
        MetadataPayload ready for writing
    """
    payload = MetadataPayload()
    file_record = db.get_file(file_id)
    if not file_record:
        return payload

    # AI Summary
    if include_summary:
        try:
            with db.connection() as conn:
                row = conn.execute(
                    "SELECT summary, quality_score FROM ai_summaries WHERE file_id = ?",
                    (file_id,),
                ).fetchone()
                if row and row["summary"]:
                    payload.summary = row["summary"]
                if row and row["quality_score"] is not None and include_quality:
                    # Map 0-100 quality score to 1-5 stars
                    score = row["quality_score"]
                    if score >= 80:
                        payload.quality_rating = 5
                    elif score >= 60:
                        payload.quality_rating = 4
                    elif score >= 40:
                        payload.quality_rating = 3
                    elif score >= 20:
                        payload.quality_rating = 2
                    else:
                        payload.quality_rating = 1
        except Exception as exc:
            logger.debug("Failed to get AI summary for file %d: %s", file_id, exc)

    # Tags
    if include_tags:
        try:
            with db.connection() as conn:
                rows = conn.execute(
                    """SELECT t.name, t.category FROM file_tags ft
                       JOIN tags t ON ft.tag_id = t.id
                       WHERE ft.file_id = ?""",
                    (file_id,),
                ).fetchall()
                for row in rows:
                    name = row["name"]
                    category = row["category"] or "general"
                    payload.keywords.append(name)
                    if tag_prefix:
                        payload.hierarchical_tags.append(f"{tag_prefix}|{category.title()}|{name}")
        except Exception as exc:
            logger.debug("Failed to get tags for file %d: %s", file_id, exc)

    # Scene categories as tags
    if include_tags:
        try:
            with db.connection() as conn:
                row = conn.execute(
                    "SELECT categories, objects FROM scene_analysis WHERE file_id = ?",
                    (file_id,),
                ).fetchone()
                if row:
                    if row["categories"]:
                        cats = json.loads(row["categories"])
                        if isinstance(cats, dict):
                            for cat_name in cats:
                                payload.keywords.append(cat_name)
                                if tag_prefix:
                                    payload.hierarchical_tags.append(f"{tag_prefix}|Scene|{cat_name}")
                    if row["objects"]:
                        objs = json.loads(row["objects"])
                        if isinstance(objs, list):
                            for obj_name in objs:
                                payload.keywords.append(str(obj_name))
                                if tag_prefix:
                                    payload.hierarchical_tags.append(f"{tag_prefix}|Object|{obj_name}")
        except Exception as exc:
            logger.debug("Failed to get scene data for file %d: %s", file_id, exc)

    # Faces
    if include_faces:
        try:
            # Get image dimensions for MWG normalization
            metadata = db.get_file_metadata(file_id)
            img_w = metadata.width if metadata and metadata.width else None
            img_h = metadata.height if metadata and metadata.height else None

            with db.connection() as conn:
                rows = conn.execute(
                    """SELECT f.bbox_x, f.bbox_y, f.bbox_w, f.bbox_h,
                              p.name
                       FROM faces f
                       LEFT JOIN persons p ON f.person_id = p.id
                       WHERE f.file_id = ?""",
                    (file_id,),
                ).fetchall()

                for row in rows:
                    name = row["name"] or "Unknown"
                    if name != "Unknown":
                        payload.person_names.append(name)
                        payload.keywords.append(name)
                        if tag_prefix:
                            payload.hierarchical_tags.append(f"{tag_prefix}|People|{name}")

                    # Add MWG face region if we have image dimensions
                    if img_w and img_h:
                        region = bbox_to_mwg(
                            row["bbox_x"], row["bbox_y"],
                            row["bbox_w"], row["bbox_h"],
                            img_w, img_h,
                        )
                        region.name = name
                        payload.face_regions.append(region)
        except Exception as exc:
            logger.debug("Failed to get face data for file %d: %s", file_id, exc)

    # Pet names as keywords
    if include_tags:
        try:
            with db.connection() as conn:
                rows = conn.execute(
                    """SELECT pt.name FROM pet_detections pd
                       JOIN pets pt ON pd.pet_id = pt.id
                       WHERE pd.file_id = ? AND pt.name IS NOT NULL""",
                    (file_id,),
                ).fetchall()
                for row in rows:
                    pet_name = row["name"]
                    payload.keywords.append(pet_name)
                    if tag_prefix:
                        payload.hierarchical_tags.append(f"{tag_prefix}|Pets|{pet_name}")
        except Exception as exc:
            logger.debug("Failed to get pet data for file %d: %s", file_id, exc)

    # Deduplicate keywords
    payload.keywords = list(dict.fromkeys(payload.keywords))
    payload.hierarchical_tags = list(dict.fromkeys(payload.hierarchical_tags))
    payload.person_names = list(dict.fromkeys(payload.person_names))

    return payload


def preview_metadata_for_file(db: "Database", file_id: int, tag_prefix: str = "AI") -> dict[str, Any]:
    """Preview what metadata would be written for a file.

    Returns a human-readable dict of field names to values.
    """
    payload = build_payload_for_file(db, file_id, tag_prefix=tag_prefix)

    preview: dict[str, Any] = {}
    if payload.summary:
        preview["Description"] = payload.summary[:200] + ("..." if len(payload.summary) > 200 else "")
    if payload.keywords:
        preview["Keywords"] = ", ".join(payload.keywords)
    if payload.person_names:
        preview["People"] = ", ".join(payload.person_names)
    if payload.face_regions:
        preview["Face Regions"] = f"{len(payload.face_regions)} face(s) with bounding boxes"
    if payload.quality_rating:
        preview["Rating"] = f"{payload.quality_rating}/5 stars"
    if payload.hierarchical_tags:
        preview["Hierarchical Tags"] = f"{len(payload.hierarchical_tags)} tags"

    return preview
