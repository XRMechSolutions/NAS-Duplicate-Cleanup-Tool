"""Database module for DupliCleaner."""

from duplicleaner.db.database import Database, get_database
from duplicleaner.db.models import (
    ActionLogEntry,
    Drive,
    DuplicateGroup,
    DuplicateMember,
    Face,
    FamilyGroup,
    FamilyGroupMember,
    FileMetadata,
    FileRecord,
    OCRResult,
    Person,
    PersonRelationship,
    SceneAnalysis,
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
    "FamilyGroup",
    "FamilyGroupMember",
    "Person",
    "PersonRelationship",
    "SceneAnalysis",
    "OCRResult",
    "ActionLogEntry",
]
