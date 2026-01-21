"""Configuration management for DupliCleaner.

Handles application settings with persistence to SQLite database.
Settings are loaded on startup and can be modified at runtime.
"""

import json
import sys
from dataclasses import dataclass, field, asdict
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

    # Hardware settings
    use_gpu: bool = True
    batch_size: int = 32
    max_concurrent_tasks: int = 4

    # Face recognition settings
    face_detection_threshold: float = 0.5
    face_recognition_threshold: float = 0.6
    face_clustering_threshold: float = 0.5
    face_model: str = "buffalo_l"  # InsightFace model

    # Scene/object detection settings
    scene_model: str = "ViT-L-14"  # CLIP model for scene classification
    object_model: str = "yolov8n"  # YOLOv8 model size (n/s/m/l/x)
    scene_confidence_threshold: float = 0.3
    object_confidence_threshold: float = 0.5

    # OCR settings
    ocr_enabled: bool = True
    ocr_languages: list[str] = field(default_factory=lambda: ["en"])

    # Summary generation settings
    summary_enabled: bool = True
    summary_provider: str = "local"  # local, openai, anthropic, google
    summary_model_local: str = "llava:13b"  # Ollama model for local
    summary_model_openai: str = "gpt-4-vision-preview"
    summary_model_anthropic: str = "claude-3-opus-20240229"
    summary_model_google: str = "gemini-pro-vision"
    summary_max_tokens: int = 500
    summary_temperature: float = 0.7

    # Quality analysis settings
    quality_analysis_enabled: bool = True

    # Auto-tagging settings
    auto_tag_enabled: bool = True
    auto_tag_confidence_threshold: float = 0.7

    # Processing preferences
    process_images: bool = True
    process_documents: bool = True
    process_videos: bool = False  # Video analysis is expensive
    max_image_dimension: int = 2048  # Resize large images for processing
    video_frame_interval: int = 30  # Extract 1 frame every N seconds
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
    backup: BackupPlanSettings = field(default_factory=BackupPlanSettings)

    # Runtime state (not persisted)
    first_run: bool = True
    database_path: str = ""

    def __post_init__(self) -> None:
        """Set default paths after initialization."""
        app_dir = get_app_data_dir()

        if not self.database_path:
            self.database_path = str(app_dir / "duplicleaner.db")

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
            "backup": asdict(self.backup),
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
        if "backup" in data:
            config.backup = BackupPlanSettings(**data["backup"])

        config.first_run = False
        return config

    def save_to_json(self, path: Optional[Path] = None) -> None:
        """Save config to JSON file (for debugging/export)."""
        if path is None:
            path = get_app_data_dir() / "config.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

        logger.debug(f"Config saved to {path}")

    @classmethod
    def load_from_json(cls, path: Optional[Path] = None) -> "Config":
        """Load config from JSON file."""
        if path is None:
            path = get_app_data_dir() / "config.json"

        if not path.exists():
            logger.info("No config file found, using defaults")
            return cls()

        try:
            with open(path, "r", encoding="utf-8") as f:
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
