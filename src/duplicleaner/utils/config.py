"""Configuration management for DupliCleaner.

Handles application settings with persistence to SQLite database.
Settings are loaded on startup and can be modified at runtime.
"""

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)

# Singleton config instance
_config: Optional["Config"] = None


def get_app_data_dir() -> Path:
    """Get the application data directory.

    Returns:
        Path to AppData/Local/DupliCleaner on Windows
    """
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "DupliCleaner"
    else:
        base = Path.home() / ".duplicleaner"

    try:
        base.mkdir(parents=True, exist_ok=True)
        return base
    except (PermissionError, FileNotFoundError):
        fallback = Path.cwd() / ".duplicleaner"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


@dataclass
class ScanSettings:
    """Settings for file scanning."""

    ignore_patterns: list[str] = field(default_factory=lambda: [
        "*.tmp", "*.temp", "~*", "Thumbs.db", ".DS_Store",
        "desktop.ini", "*.sys", "$RECYCLE.BIN", "System Volume Information"
    ])
    ignore_hidden: bool = True
    follow_symlinks: bool = False
    max_file_size_gb: float = 50.0  # Skip files larger than this


@dataclass
class HashSettings:
    """Settings for file hashing."""

    quick_hash_size_kb: int = 64  # Size of chunks for quick hash
    chunk_size_mb: int = 1  # Chunk size for streaming hash
    use_xxhash: bool = True  # Use xxHash for quick hash


@dataclass
class DuplicateSettings:
    """Settings for duplicate detection."""

    near_duplicate_threshold: float = 0.90  # 90% similarity
    match_across_formats: bool = True  # JPEG/PNG/HEIC as duplicates
    min_image_size: int = 100  # Skip images smaller than 100x100
    video_near_duplicate: bool = True  # Enable video near-duplicate detection
    video_keyframe_count: int = 8  # Max keyframes to extract per video
    video_similarity_threshold: float = 0.70  # 70% frame match for video duplicates


@dataclass
class ActionSettings:
    """Settings for file actions."""

    default_action: str = "quarantine"  # quarantine, trash, delete
    quarantine_folder: str = ""  # Empty = use default
    confirm_destructive: bool = True
    create_audit_log: bool = True


@dataclass
class AIModelConfig:
    """Configuration for a specific AI model."""

    provider: str = "local"  # local, openai, anthropic, google
    model_name: str = ""
    enabled: bool = True


@dataclass
class AISettings:
    """Settings for AI features."""

    enabled: bool = True
    models_directory: str = ""  # Empty = use default
    dependency_variant: str = "cpu"  # gpu, cpu

    # Hardware settings
    use_gpu: bool = False
    batch_size: int = 32
    max_concurrent_tasks: int = 4

    # Face recognition settings
    face_detection_threshold: float = 0.5
    face_recognition_threshold: float = 0.6
    face_clustering_threshold: float = 0.5
    face_model: str = "buffalo_l"  # InsightFace model
    min_cluster_photos: int = 1  # Minimum photos to show cluster (1 = show all)
    filter_by_min_photos: bool = False  # Enable/disable min photos filter

    # Scene/object detection settings
    scene_model: str = "ViT-L-14"  # CLIP model for scene classification
    object_model: str = "yolov8n"  # YOLOv8 model size (n/s/m/l/x)
    scene_confidence_threshold: float = 0.3
    object_confidence_threshold: float = 0.5

    # Pet detection settings
    pet_detection_threshold: float = 0.65  # Higher threshold to reduce false positives
    pets_only_mode: bool = True  # Only detect common pets (dog, cat, bird), not wild animals

    # OCR settings
    ocr_enabled: bool = True
    ocr_languages: list[str] = field(default_factory=lambda: ["en"])

    # Summary generation settings
    summary_enabled: bool = True
    summary_provider: str = "local"  # local, lmstudio, openai, anthropic, google
    summary_model_local: str = "llava:13b"  # Ollama model for local
    summary_model_lmstudio: str = ""  # LMStudio model (empty = use currently loaded model)
    lmstudio_base_url: str = "http://localhost:1234/v1"  # LMStudio API base URL
    summary_model_openai: str = "gpt-4-vision-preview"
    summary_model_anthropic: str = "claude-3-opus-20240229"
    summary_model_google: str = "gemini-pro-vision"
    summary_max_tokens: int = 500
    summary_temperature: float = 0.7
    metadata_location_lookup: bool = False
    metadata_location_level: str = "city"
    audio_whisper_model: str = "base"
    audio_whisper_device: str = "cpu"
    audio_whisper_compute_type: str = "int8"
    analysis_include_images: bool = True
    analysis_include_documents: bool = True
    analysis_include_data_files: bool = False
    analysis_include_metadata: bool = True
    analysis_include_scenes: bool = True
    analysis_include_objects: bool = True
    analysis_include_ocr: bool = True
    analysis_include_summaries: bool = False
    analysis_include_audio: bool = False
    analysis_doc_extensions: list[str] = field(default_factory=lambda: [
        ".txt", ".md", ".pdf", ".rtf", ".docx", ".odt", ".pptx", ".xlsx"
    ])
    analysis_data_extensions: list[str] = field(default_factory=lambda: [
        ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".ini", ".log"
    ])
    analysis_scan_before_full: bool = True
    analysis_reanalyze_existing: bool = False
    analysis_batch_limit: int = 200

    # Metadata writing settings
    metadata_tag_prefix: str = "AI"  # Prefix for hierarchical tags (e.g., "AI|Scene|Beach")
    metadata_backup: bool = True  # Create backup before writing
    metadata_include_summary: bool = True  # Write AI summary to description fields
    metadata_include_tags: bool = True  # Write tags as keywords
    metadata_include_faces: bool = True  # Write face names and MWG regions
    metadata_include_quality: bool = True  # Write quality score as star rating
    analysis_background_during_scan: bool = True
    hash_background_during_scan: bool = True

    # PDF extraction settings
    pdf_extract_pages: bool = True  # Extract PDF pages to persistent JPEGs

    # Quality analysis settings
    quality_analysis_enabled: bool = True

    # Auto-tagging settings
    auto_tag_enabled: bool = True
    auto_tag_confidence_threshold: float = 0.7

    # Processing preferences
    process_images: bool = True
    process_documents: bool = True
    process_videos: bool = True  # Extract frames and summarize with vision model
    max_image_dimension: int = 2048  # Resize large images for processing
    video_frame_interval: int = 30  # Extract 1 frame every N seconds
    # Celebrity identification settings
    celebrity_enabled: bool = False  # Off by default
    celebrity_provider: str = "rekognition"  # 'rekognition', 'local_db'
    celebrity_auto_confirm_threshold: float = 0.95  # Auto-confirm above this
    celebrity_min_confidence: float = 0.70  # Minimum to show in review queue

    downloaded_models: dict[str, bool] = field(default_factory=lambda: {
        "faces": False,
        "clip": False,
        "yolo": False,
        "ocr": False,
    })

    def get_summary_model(self) -> str:
        """Get the appropriate summary model based on provider."""
        if self.summary_provider == "openai":
            return self.summary_model_openai
        elif self.summary_provider == "anthropic":
            return self.summary_model_anthropic
        elif self.summary_provider == "google":
            return self.summary_model_google
        elif self.summary_provider == "lmstudio":
            return self.summary_model_lmstudio
        else:
            return self.summary_model_local


@dataclass
class UISettings:
    """Settings for the user interface."""

    theme: str = "dark"  # dark, light
    thumbnail_size: int = 150
    show_hidden_files: bool = False
    confirm_exit: bool = True
    window_width: int = 1400
    window_height: int = 900


@dataclass
class VersioningSettings:
    """Settings for document version tracking."""

    tracked_folders: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=lambda: [
        "*.tmp", "*.bak", "*.swp", "~*", "Thumbs.db", ".DS_Store", "*.lock", "*.log"
    ])
    include_subfolders: bool = True
    auto_commit_mode: str = "on_save"  # on_save, interval, daily, manual
    auto_commit_interval_minutes: int = 5
    auto_commit_daily_time: str = "00:00"
    max_file_size_mb: float = 50.0


@dataclass
class WatchFolderEntry:
    """Configuration for a single watched folder."""

    path: str = ""
    enabled: bool = True
    poll_interval_seconds: int = 60
    debounce_seconds: int = 60
    auto_scan: bool = True
    auto_organize: bool = False
    auto_ai_analysis: bool = False
    organize_format: str = "YYYY/MM"
    organize_by_location: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WatchFolderEntry":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class WatchSettings:
    """Settings for folder watching and auto-organization."""

    watch_folders: list[WatchFolderEntry] = field(default_factory=list)
    global_enabled: bool = False  # Master on/off toggle
    default_poll_interval: int = 60
    default_debounce: int = 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "watch_folders": [wf.to_dict() for wf in self.watch_folders],
            "global_enabled": self.global_enabled,
            "default_poll_interval": self.default_poll_interval,
            "default_debounce": self.default_debounce,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WatchSettings":
        folders = [WatchFolderEntry.from_dict(wf) for wf in data.get("watch_folders", [])]
        return cls(
            watch_folders=folders,
            global_enabled=data.get("global_enabled", False),
            default_poll_interval=data.get("default_poll_interval", 60),
            default_debounce=data.get("default_debounce", 60),
        )


@dataclass
class BackupPlanSettings:
    """Settings for backup plans."""

    source_path: str = ""
    target_drive_ids: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=lambda: [
        "*/Library/*",
        "*/Temp/*",
        "*/tmp/*",
        "*/Build/*",
        "*/Builds/*",
        "*/bin/*",
        "*/obj/*",
        "*/.gradle/*",
        "*/.idea/*",
        "*/.vs/*",
        "*/DerivedDataCache/*",
        "*/Intermediate/*",
        "*/Binaries/*",
        "*/node_modules/*",
    ])


@dataclass
class Config:
    """Main configuration container."""

    scan: ScanSettings = field(default_factory=ScanSettings)
    hash: HashSettings = field(default_factory=HashSettings)
    duplicates: DuplicateSettings = field(default_factory=DuplicateSettings)
    actions: ActionSettings = field(default_factory=ActionSettings)
    ai: AISettings = field(default_factory=AISettings)
    ui: UISettings = field(default_factory=UISettings)
    versioning: VersioningSettings = field(default_factory=VersioningSettings)
    watch: WatchSettings = field(default_factory=WatchSettings)
    backup: BackupPlanSettings = field(default_factory=BackupPlanSettings)

    # Runtime state (not persisted)
    first_run: bool = True
    database_path: str = ""
    active_database: str = ""

    def __post_init__(self) -> None:
        """Set default paths after initialization."""
        app_dir = get_app_data_dir()

        if self.active_database:
            self.database_path = str(app_dir / self.active_database)
        elif not self.database_path:
            self.database_path = str(app_dir / "duplicleaner.db")
            self.active_database = "duplicleaner.db"
        else:
            self.active_database = Path(self.database_path).name

        if not self.actions.quarantine_folder:
            quarantine = app_dir / "quarantine"
            quarantine.mkdir(exist_ok=True)
            self.actions.quarantine_folder = str(quarantine)

        if not self.ai.models_directory:
            models = app_dir / "models"
            models.mkdir(exist_ok=True)
            self.ai.models_directory = str(models)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for persistence."""
        return {
            "scan": asdict(self.scan),
            "hash": asdict(self.hash),
            "duplicates": asdict(self.duplicates),
            "actions": asdict(self.actions),
            "ai": asdict(self.ai),
            "ui": asdict(self.ui),
            "versioning": asdict(self.versioning),
            "watch": self.watch.to_dict(),
            "backup": asdict(self.backup),
            "active_database": self.active_database,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create config from dictionary."""
        config = cls()

        if "scan" in data:
            config.scan = ScanSettings(**data["scan"])
        if "hash" in data:
            config.hash = HashSettings(**data["hash"])
        if "duplicates" in data:
            config.duplicates = DuplicateSettings(**data["duplicates"])
        if "actions" in data:
            config.actions = ActionSettings(**data["actions"])
        if "ai" in data:
            config.ai = AISettings(**data["ai"])
        if "ui" in data:
            config.ui = UISettings(**data["ui"])
        if "versioning" in data:
            config.versioning = VersioningSettings(**data["versioning"])
        if "watch" in data:
            config.watch = WatchSettings.from_dict(data["watch"])
        if "backup" in data:
            config.backup = BackupPlanSettings(**data["backup"])

        config.active_database = data.get("active_database", "")
        config.first_run = False
        return config

    def save_to_json(self, path: Path | None = None) -> None:
        """Save config to JSON file (for debugging/export)."""
        if path is None:
            path = get_app_data_dir() / "config.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

        logger.debug(f"Config saved to {path}")

    @classmethod
    def load_from_json(cls, path: Path | None = None) -> "Config":
        """Load config from JSON file."""
        if path is None:
            path = get_app_data_dir() / "config.json"

        if not path.exists():
            logger.info("No config file found, using defaults")
            return cls()

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}, using defaults")
            return cls()


def get_config() -> Config:
    """Get the global configuration instance.

    Returns:
        The singleton Config instance
    """
    global _config

    if _config is None:
        _config = Config.load_from_json()

    return _config


def save_config() -> None:
    """Save the current configuration."""
    global _config

    if _config is not None:
        _config.save_to_json()


def reset_config() -> Config:
    """Reset configuration to defaults.

    Returns:
        New default Config instance
    """
    global _config
    _config = Config()
    return _config
