"""Data models for DupliCleaner.

Dataclasses representing database entities with type hints.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


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
    PET = "pet"
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
    last_scan: datetime | None = None
    total_space: int | None = None
    free_space: int | None = None
    file_count: int = 0
    is_network: bool = False
    created_at: datetime | None = None

    @property
    def used_space(self) -> int | None:
        """Calculate used space."""
        if self.total_space is not None and self.free_space is not None:
            return self.total_space - self.free_space
        return None

    @property
    def usage_percent(self) -> float | None:
        """Calculate usage percentage."""
        if self.total_space and self.total_space > 0:
            used = self.used_space
            if used is not None:
                return (used / self.total_space) * 100
        return None


@dataclass
class FileRecord:
    """Represents a scanned file."""

    id: int | None = None
    drive_id: str = ""
    path: str = ""
    filename: str = ""
    size: int = 0
    created: datetime | None = None
    modified: datetime | None = None
    file_type: str | None = None
    mime_type: str | None = None
    quick_hash: str | None = None
    content_hash: str | None = None
    perceptual_hash: str | None = None
    scan_date: datetime | None = None
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
    exif_date: datetime | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    location_name: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    orientation: int | None = None
    raw_exif: str | None = None  # JSON string

    @property
    def has_gps(self) -> bool:
        """Check if GPS coordinates are available."""
        return self.gps_lat is not None and self.gps_lon is not None

    @property
    def resolution(self) -> tuple[int, int] | None:
        """Get resolution as tuple."""
        if self.width and self.height:
            return (self.width, self.height)
        return None

    @property
    def megapixels(self) -> float | None:
        """Calculate megapixels."""
        if self.width and self.height:
            return (self.width * self.height) / 1_000_000
        return None


@dataclass
class DuplicateGroup:
    """Represents a group of duplicate files."""

    id: int | None = None
    match_type: MatchType = MatchType.EXACT
    similarity: float = 1.0
    file_count: int = 0
    total_size: int = 0
    wasted_size: int = 0
    status: GroupStatus = GroupStatus.PENDING
    created_at: datetime | None = None
    resolved_at: datetime | None = None

    # Populated when loading with members
    members: list["DuplicateMember"] = field(default_factory=list)


@dataclass
class DuplicateMember:
    """Represents a file in a duplicate group."""

    group_id: int
    file_id: int
    is_keeper: bool = False

    # Populated when loading with file info
    file: FileRecord | None = None


@dataclass
class Person:
    """Represents a person for face recognition."""

    id: int | None = None
    name: str | None = None
    birth_year: int | None = None
    notes: str | None = None
    is_favorite: bool = False
    is_hidden: bool = False  # Hidden/ignored persons (unknown faces user wants to hide)
    reference_photo_id: int | None = None
    created_at: datetime | None = None
    photo_count: int = 0
    identification_source: str = "manual"  # manual, rekognition, local_db

    @property
    def estimated_age(self) -> int | None:
        """Estimate current age from birth year."""
        if self.birth_year:
            return datetime.now().year - self.birth_year
        return None


@dataclass
class PersonRelationship:
    """Represents a relationship between two persons."""

    id: int | None = None
    person_a_id: int = 0
    person_b_id: int = 0
    relationship_type: str = ""  # parent, child, sibling, spouse, other
    confidence: str = "confirmed"  # confirmed, suggested, inferred
    created_at: datetime | None = None
    notes: str | None = None


@dataclass
class FamilyGroup:
    """Named family group containing multiple persons."""

    id: int | None = None
    name: str = ""
    created_at: datetime | None = None
    notes: str | None = None


@dataclass
class FamilyGroupMember:
    """Links a person to a family group with an optional role."""

    family_group_id: int = 0
    person_id: int = 0
    role: str | None = None  # father, mother, child, etc.


class CelebrityMatchStatus(Enum):
    """Status of a celebrity identification match."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


@dataclass
class CelebrityMatch:
    """A celebrity identification result for a detected face."""

    id: int | None = None
    face_id: int = 0
    person_id: int | None = None
    provider: str = ""  # 'rekognition', 'local_db'
    celebrity_name: str = ""
    confidence: float = 0.0
    external_id: str | None = None
    external_urls: str | None = None  # JSON list of {"label": ..., "url": ...}
    known_for: str | None = None
    status: str = "pending"  # pending, confirmed, rejected
    reviewed_at: datetime | None = None
    created_at: datetime | None = None

    def get_urls(self) -> list[dict[str, str]]:
        """Parse external_urls JSON to list of dicts."""
        if self.external_urls:
            import json
            try:
                return json.loads(self.external_urls)
            except json.JSONDecodeError:
                return []
        return []


@dataclass
class Face:
    """Represents a detected face in an image."""

    id: int | None = None
    file_id: int = 0
    person_id: int | None = None
    bbox_x: int = 0
    bbox_y: int = 0
    bbox_w: int = 0
    bbox_h: int = 0
    embedding: bytes | None = None
    confidence: float | None = None
    estimated_age: int | None = None
    estimated_gender: str | None = None
    page_number: int | None = None  # PDF page number (0-indexed), None for images
    created_at: datetime | None = None

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Get bounding box as tuple (x, y, w, h)."""
        return (self.bbox_x, self.bbox_y, self.bbox_w, self.bbox_h)


@dataclass
class SceneAnalysis:
    """AI analysis results for an image."""

    file_id: int
    categories: str | None = None  # JSON string
    objects: str | None = None  # JSON string
    quality_score: float | None = None
    blur_score: float | None = None
    exposure_score: float | None = None
    clip_embedding: bytes | None = None
    analyzed_at: datetime | None = None


@dataclass
class OCRResult:
    """OCR extraction results."""

    file_id: int
    extracted_text: str | None = None
    confidence: float | None = None
    language: str | None = None
    created_at: datetime | None = None


@dataclass
class ActionLogEntry:
    """Record of a file action for audit and undo."""

    id: int | None = None
    timestamp: datetime | None = None
    action_type: ActionType = ActionType.MOVE
    source_path: str = ""
    dest_path: str | None = None
    file_hash: str | None = None
    file_size: int | None = None
    reversible: bool = True
    reversed: bool = False
    metadata: str | None = None  # JSON string


@dataclass
class Thumbnail:
    """Cached thumbnail for a file."""

    file_id: int
    thumbnail: bytes
    width: int
    height: int
    created_at: datetime | None = None


class PetAgeStage(Enum):
    """Life stage of a pet."""

    BABY = "baby"  # puppy, kitten
    YOUNG = "young"
    ADULT = "adult"
    SENIOR = "senior"


@dataclass
class Pet:
    """Represents a pet for recognition/tracking."""

    id: int | None = None
    name: str | None = None
    species: str | None = None  # dog, cat, bird, etc.
    breed: str | None = None
    birth_year: int | None = None
    color_pattern: str | None = None  # Description of markings
    notes: str | None = None
    is_favorite: bool = False
    reference_photo_id: int | None = None
    created_at: datetime | None = None
    photo_count: int = 0

    @property
    def estimated_age(self) -> int | None:
        """Estimate current age from birth year."""
        if self.birth_year:
            return datetime.now().year - self.birth_year
        return None


@dataclass
class PetDetection:
    """Represents a detected pet in an image."""

    id: int | None = None
    file_id: int = 0
    pet_id: int | None = None
    species: str = ""
    breed: str | None = None
    bbox_x: int = 0
    bbox_y: int = 0
    bbox_w: int = 0
    bbox_h: int = 0
    embedding: bytes | None = None
    confidence: float | None = None
    color_histogram: bytes | None = None
    estimated_age_stage: PetAgeStage | None = None
    created_at: datetime | None = None

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Get bounding box as tuple (x, y, w, h)."""
        return (self.bbox_x, self.bbox_y, self.bbox_w, self.bbox_h)


@dataclass
class AISummary:
    """AI-generated content summary for a file."""

    file_id: int
    summary: str | None = None  # Natural language description
    summary_model: str | None = None  # Model used to generate summary
    people_mentioned: str | None = None  # JSON: ["Emma", "Dad"]
    pets_mentioned: str | None = None  # JSON: ["Max", "Whiskers"]
    activities: str | None = None  # JSON: ["playing", "swimming"]
    mood_atmosphere: str | None = None  # "joyful", "serene"
    time_of_day: str | None = None  # "sunset", "morning"
    season_weather: str | None = None  # "summer", "sunny"
    document_type: str | None = None  # "invoice", "receipt", "letter"
    document_summary: str | None = None  # Key info from documents
    key_entities: str | None = None  # JSON: extracted names, dates, amounts
    generated_at: datetime | None = None
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

    def get_pets_list(self) -> list[str]:
        """Parse pets_mentioned JSON to list."""
        if self.pets_mentioned:
            import json
            try:
                return json.loads(self.pets_mentioned)
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

    id: int | None = None
    name: str = ""
    category: TagCategory | None = None
    is_system: bool = False
    created_at: datetime | None = None


@dataclass
class FileTag:
    """Association between a file and a tag."""

    file_id: int
    tag_id: int
    confidence: float | None = None  # AI confidence or 1.0 for user tags
    source: TagSource = TagSource.USER
    created_at: datetime | None = None

    # Populated when loading with tag info
    tag: Tag | None = None


@dataclass
class CorruptFile:
    """A file detected as corrupt during scanning."""

    id: int | None = None
    file_id: int = 0
    corruption_type: str = ""  # truncated, extraneous_data, invalid_markers, unknown
    severity: str = "medium"  # low, medium, high
    detected_at: datetime | None = None

    # Populated when loading with file info
    file: FileRecord | None = None


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt on a corrupt file."""

    id: int | None = None
    file_id: int = 0
    strategy_used: str = ""
    success: bool = False
    pixel_recovery_pct: float | None = None
    recovered_path: str | None = None
    attempted_at: datetime | None = None
