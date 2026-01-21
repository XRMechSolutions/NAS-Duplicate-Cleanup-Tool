"""Database module for DupliCleaner."""

from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import (
    Drive,
    FileRecord,
    FileMetadata,
    DuplicateGroup,
    DuplicateMember,
    Face,
    Person,
    SceneAnalysis,
    OCRResult,
    ActionLogEntry,
)

__all__ = [
    "Database",
    "get_database",
    "Drive",
    "FileRecord",
    "FileMetadata",
    "DuplicateGroup",
    "DuplicateMember",
    "Face",
    "Person",
    "SceneAnalysis",
    "OCRResult",
    "ActionLogEntry",
]
