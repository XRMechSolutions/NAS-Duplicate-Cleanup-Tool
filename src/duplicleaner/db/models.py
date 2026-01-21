"""Data models for DupliCleaner.

Dataclasses representing database entities with type hints.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class MatchType(Enum):
    """Type of duplicate match."""

    EXACT = "exact"
    NEAR = "near"


class GroupStatus(Enum):
    """Status of a duplicate group."""

    PENDING = "pending"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ActionType(Enum):
    """Type of file action."""

    DELETE = "delete"
    QUARANTINE = "quarantine"
    TRASH = "trash"
    LINK = "link"
    COPY = "copy"
    MOVE = "move"
    RESTORE = "restore"


class TagCategory(Enum):
    """Category of a tag."""

    PERSON = "person"
    PLACE = "place"
    ACTIVITY = "activity"
    OBJECT = "object"
    EVENT = "event"
    CUSTOM = "custom"


class TagSource(Enum):
    """Source of a file tag."""

    AI = "ai"
    USER = "user"
    EXIF = "exif"


@dataclass
class Drive:
    """Represents a registered drive or storage location."""

    id: str
    label: str
    path: str
    last_scan: Optional[datetime] = None
    total_space: Optional[int] = None
    free_space: Optional[int] = None
    file_count: int = 0
    is_network: bool = False
    created_at: Optional[datetime] = None

    @property
    def used_space(self) -> Optional[int]:
        """Calculate used space."""
        if self.total_space is not None and self.free_space is not None:
            return self.total_space - self.free_space
        return None

    @property
    def usage_percent(self) -> Optional[float]:
        """Calculate usage percentage."""
        if self.total_space and self.total_space > 0:
            used = self.used_space
            if used is not None:
                return (used / self.total_space) * 100
        return None


@dataclass
class FileRecord:
    """Represents a scanned file."""

    id: Optional[int] = None
    drive_id: str = ""
    path: str = ""
    filename: str = ""
    size: int = 0
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    file_type: Optional[str] = None
    mime_type: Optional[str] = None
    quick_hash: Optional[str] = None
    content_hash: Optional[str] = None
    perceptual_hash: Optional[str] = None
    scan_date: Optional[datetime] = None
    is_deleted: bool = False

    @property
    def is_image(self) -> bool:
        """Check if file is an image."""
        if self.file_type:
            return self.file_type.lower() in {
                ".jpg", ".jpeg", ".png", ".gif", ".bmp",
                ".tiff", ".tif", ".webp", ".heic", ".heif"
            }
        return False

    @property
    def is_video(self) -> bool:
        """Check if file is a video."""
        if self.file_type:
            return self.file_type.lower() in {
                ".mp4", ".avi", ".mov", ".mkv", ".wmv",
                ".flv", ".webm", ".m4v", ".mpg", ".mpeg"
            }
        return False

    @property
    def is_document(self) -> bool:
        """Check if file is a document."""
        if self.file_type:
            return self.file_type.lower() in {
                ".pdf", ".doc", ".docx", ".xls", ".xlsx",
                ".ppt", ".pptx", ".txt", ".rtf", ".odt"
            }
        return False


@dataclass
class FileMetadata:
    """Extended metadata for a file (EXIF, dimensions, etc.)."""

    file_id: int
    exif_date: Optional[datetime] = None
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    location_name: Optional[str] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    orientation: Optional[int] = None
    raw_exif: Optional[str] = None  # JSON string

    @property
    def has_gps(self) -> bool:
        """Check if GPS coordinates are available."""
        return self.gps_lat is not None and self.gps_lon is not None

    @property
    def resolution(self) -> Optional[tuple[int, int]]:
        """Get resolution as tuple."""
        if self.width and self.height:
            return (self.width, self.height)
        return None

    @property
    def megapixels(self) -> Optional[float]:
        """Calculate megapixels."""
        if self.width and self.height:
            return (self.width * self.height) / 1_000_000
        return None


@dataclass
class DuplicateGroup:
    """Represents a group of duplicate files."""

    id: Optional[int] = None
    match_type: MatchType = MatchType.EXACT
    similarity: float = 1.0
    file_count: int = 0
    total_size: int = 0
    wasted_size: int = 0
    status: GroupStatus = GroupStatus.PENDING
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    # Populated when loading with members
    members: list["DuplicateMember"] = field(default_factory=list)


@dataclass
class DuplicateMember:
    """Represents a file in a duplicate group."""

    group_id: int
    file_id: int
    is_keeper: bool = False

    # Populated when loading with file info
    file: Optional[FileRecord] = None


@dataclass
class Person:
    """Represents a person for face recognition."""

    id: Optional[int] = None
    name: Optional[str] = None
    birth_year: Optional[int] = None
    notes: Optional[str] = None
    is_favorite: bool = False
    reference_photo_id: Optional[int] = None
    created_at: Optional[datetime] = None
    photo_count: int = 0

    @property
    def estimated_age(self) -> Optional[int]:
        """Estimate current age from birth year."""
        if self.birth_year:
            return datetime.now().year - self.birth_year
        return None


@dataclass
class Face:
    """Represents a detected face in an image."""

    id: Optional[int] = None
    file_id: int = 0
    person_id: Optional[int] = None
    bbox_x: int = 0
    bbox_y: int = 0
    bbox_w: int = 0
    bbox_h: int = 0
    embedding: Optional[bytes] = None
    confidence: Optional[float] = None
    estimated_age: Optional[int] = None
    estimated_gender: Optional[str] = None
    created_at: Optional[datetime] = None

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Get bounding box as tuple (x, y, w, h)."""
        return (self.bbox_x, self.bbox_y, self.bbox_w, self.bbox_h)


@dataclass
class SceneAnalysis:
    """AI analysis results for an image."""

    file_id: int
    categories: Optional[str] = None  # JSON string
    objects: Optional[str] = None  # JSON string
    quality_score: Optional[float] = None
    blur_score: Optional[float] = None
    exposure_score: Optional[float] = None
    clip_embedding: Optional[bytes] = None
    analyzed_at: Optional[datetime] = None


@dataclass
class OCRResult:
    """OCR extraction results."""

    file_id: int
    extracted_text: Optional[str] = None
    confidence: Optional[float] = None
    language: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class ActionLogEntry:
    """Record of a file action for audit and undo."""

    id: Optional[int] = None
    timestamp: Optional[datetime] = None
    action_type: ActionType = ActionType.MOVE
    source_path: str = ""
    dest_path: Optional[str] = None
    file_hash: Optional[str] = None
    file_size: Optional[int] = None
    reversible: bool = True
    reversed: bool = False
    metadata: Optional[str] = None  # JSON string


@dataclass
class Thumbnail:
    """Cached thumbnail for a file."""

    file_id: int
    thumbnail: bytes
    width: int
    height: int
    created_at: Optional[datetime] = None


class PetAgeStage(Enum):
    """Life stage of a pet."""

    BABY = "baby"  # puppy, kitten
    YOUNG = "young"
    ADULT = "adult"
    SENIOR = "senior"


@dataclass
class Pet:
    """Represents a pet for recognition/tracking."""

    id: Optional[int] = None
    name: Optional[str] = None
    species: Optional[str] = None  # dog, cat, bird, etc.
    breed: Optional[str] = None
    birth_year: Optional[int] = None
    color_pattern: Optional[str] = None  # Description of markings
    notes: Optional[str] = None
    is_favorite: bool = False
    reference_photo_id: Optional[int] = None
    created_at: Optional[datetime] = None
    photo_count: int = 0

    @property
    def estimated_age(self) -> Optional[int]:
        """Estimate current age from birth year."""
        if self.birth_year:
            return datetime.now().year - self.birth_year
        return None


@dataclass
class PetDetection:
    """Represents a detected pet in an image."""

    id: Optional[int] = None
    file_id: int = 0
    pet_id: Optional[int] = None
    species: str = ""
    breed: Optional[str] = None
    bbox_x: int = 0
    bbox_y: int = 0
    bbox_w: int = 0
    bbox_h: int = 0
    embedding: Optional[bytes] = None
    confidence: Optional[float] = None
    color_histogram: Optional[bytes] = None
    estimated_age_stage: Optional[PetAgeStage] = None
    created_at: Optional[datetime] = None

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Get bounding box as tuple (x, y, w, h)."""
        return (self.bbox_x, self.bbox_y, self.bbox_w, self.bbox_h)


@dataclass
class AISummary:
    """AI-generated content summary for a file."""

    file_id: int
    summary: Optional[str] = None  # Natural language description
    summary_model: Optional[str] = None  # Model used to generate summary
    people_mentioned: Optional[str] = None  # JSON: ["Emma", "Dad"]
    activities: Optional[str] = None  # JSON: ["playing", "swimming"]
    mood_atmosphere: Optional[str] = None  # "joyful", "serene"
    time_of_day: Optional[str] = None  # "sunset", "morning"
    season_weather: Optional[str] = None  # "summer", "sunny"
    document_type: Optional[str] = None  # "invoice", "receipt", "letter"
    document_summary: Optional[str] = None  # Key info from documents
    key_entities: Optional[str] = None  # JSON: extracted names, dates, amounts
    generated_at: Optional[datetime] = None
    user_edited: bool = False

    def get_people_list(self) -> list[str]:
        """Parse people_mentioned JSON to list."""
        if self.people_mentioned:
            import json
            try:
                return json.loads(self.people_mentioned)
            except json.JSONDecodeError:
                return []
        return []

    def get_activities_list(self) -> list[str]:
        """Parse activities JSON to list."""
        if self.activities:
            import json
            try:
                return json.loads(self.activities)
            except json.JSONDecodeError:
                return []
        return []

    def get_key_entities_dict(self) -> dict:
        """Parse key_entities JSON to dict."""
        if self.key_entities:
            import json
            try:
                return json.loads(self.key_entities)
            except json.JSONDecodeError:
                return {}
        return {}


@dataclass
class Tag:
    """A searchable tag for categorizing files."""

    id: Optional[int] = None
    name: str = ""
    category: Optional[TagCategory] = None
    is_system: bool = False
    created_at: Optional[datetime] = None


@dataclass
class FileTag:
    """Association between a file and a tag."""

    file_id: int
    tag_id: int
    confidence: Optional[float] = None  # AI confidence or 1.0 for user tags
    source: TagSource = TagSource.USER
    created_at: Optional[datetime] = None

    # Populated when loading with tag info
    tag: Optional[Tag] = None
