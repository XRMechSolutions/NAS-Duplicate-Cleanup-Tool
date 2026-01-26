"""Database manager for DupliCleaner.

Handles SQLite database connections, schema initialization,
and provides methods for common database operations.
"""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

from duplicleaner.utils.logging import get_logger
from duplicleaner.utils.config import get_config
from duplicleaner.db.models import (
    Drive,
    FileRecord,
    FileMetadata,
    DuplicateGroup,
    DuplicateMember,
    Face,
    Person,
    Pet,
    PetDetection,
    PetAgeStage,
    SceneAnalysis,
    OCRResult,
    ActionLogEntry,
    AISummary,
    Tag,
    FileTag,
    MatchType,
    GroupStatus,
    ActionType,
    TagCategory,
    TagSource,
)

logger = get_logger(__name__)

# Explicit adapters/converters to avoid deprecated default datetime handling in sqlite3.
def _adapt_datetime(value: datetime) -> str:
    return value.isoformat(sep=" ")


def _convert_datetime(value: bytes) -> datetime:
    return datetime.fromisoformat(value.decode("utf-8"))


sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("TIMESTAMP", _convert_datetime)

# Singleton database instance
_database: Optional["Database"] = None


def get_database() -> "Database":
    """Get the singleton database instance.

    Returns:
        Database instance
    """
    global _database

    if _database is None:
        config = get_config()
        _database = Database(config.database_path)

    return _database


class Database:
    """SQLite database manager."""

    def __init__(self, db_path: str):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except (PermissionError, FileNotFoundError):
            fallback_dir = Path.cwd() / ".duplicleaner"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = fallback_dir / "duplicleaner.db"

        self._connection: Optional[sqlite3.Connection] = None
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema."""
        schema_path = Path(__file__).parent / "schema.sql"

        try:
            with self.connection() as conn:
                if schema_path.exists():
                    with open(schema_path, "r", encoding="utf-8") as f:
                        conn.executescript(f.read())
                    logger.info(f"Database initialized at {self.db_path}")
                else:
                    logger.warning(f"Schema file not found at {schema_path}")

                # Run migrations for existing databases
                self._run_migrations(conn)
        except sqlite3.OperationalError as exc:
            if "readonly" not in str(exc).lower():
                raise
            fallback_dir = Path.cwd() / ".duplicleaner"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = fallback_dir / "duplicleaner.db"
            with self.connection() as conn:
                if schema_path.exists():
                    with open(schema_path, "r", encoding="utf-8") as f:
                        conn.executescript(f.read())
                    logger.info(f"Database initialized at {self.db_path}")
                # Run migrations for fallback path too
                self._run_migrations(conn)

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """Run database migrations for schema changes.

        Adds new columns to existing tables if they don't exist.
        """
        # Migration: Add is_hidden column to persons table
        try:
            conn.execute("SELECT is_hidden FROM persons LIMIT 1")
        except sqlite3.OperationalError:
            # Column doesn't exist, add it
            conn.execute("ALTER TABLE persons ADD COLUMN is_hidden BOOLEAN DEFAULT FALSE")
            logger.info("Migration: Added is_hidden column to persons table")

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection context manager.

        Yields:
            SQLite connection with row factory set
        """
        conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ==========================================================================
    # Settings
    # ==========================================================================

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a setting value."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Set a setting value."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO settings (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
                (key, value, datetime.now(), value, datetime.now())
            )

    # ==========================================================================
    # Scan State
    # ==========================================================================

    def set_scan_state(self, drive_id: str, state: dict) -> None:
        """Persist scan state for a drive."""
        import json
        self.set_setting(f"scan_state:{drive_id}", json.dumps(state))

    def get_scan_state(self, drive_id: str) -> Optional[dict]:
        """Get persisted scan state for a drive."""
        import json
        value = self.get_setting(f"scan_state:{drive_id}")
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    def clear_scan_state(self, drive_id: str) -> None:
        """Clear persisted scan state for a drive."""
        with self.connection() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (f"scan_state:{drive_id}",))

    # ==========================================================================
    # Drives
    # ==========================================================================

    def add_drive(self, drive: Drive) -> None:
        """Add or update a drive."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO drives (id, label, path, last_scan, total_space,
                   free_space, file_count, is_network, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                   label = ?, path = ?, last_scan = ?, total_space = ?,
                   free_space = ?, file_count = ?, is_network = ?""",
                (
                    drive.id, drive.label, drive.path, drive.last_scan,
                    drive.total_space, drive.free_space, drive.file_count,
                    drive.is_network, drive.created_at or datetime.now(),
                    drive.label, drive.path, drive.last_scan, drive.total_space,
                    drive.free_space, drive.file_count, drive.is_network
                )
            )

    def get_drive(self, drive_id: str) -> Optional[Drive]:
        """Get a drive by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM drives WHERE id = ?", (drive_id,)
            ).fetchone()

            if row:
                return Drive(**dict(row))
            return None

    def get_all_drives(self) -> list[Drive]:
        """Get all registered drives."""
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM drives ORDER BY label").fetchall()
            return [Drive(**dict(row)) for row in rows]

    def remove_drive(self, drive_id: str) -> None:
        """Remove a drive and all its files."""
        with self.connection() as conn:
            conn.execute("DELETE FROM drives WHERE id = ?", (drive_id,))

    def update_drive_stats(
        self,
        drive_id: str,
        total_space: int,
        free_space: int,
        file_count: int
    ) -> None:
        """Update drive statistics."""
        with self.connection() as conn:
            conn.execute(
                """UPDATE drives SET total_space = ?, free_space = ?,
                   file_count = ?, last_scan = ? WHERE id = ?""",
                (total_space, free_space, file_count, datetime.now(), drive_id)
            )

    # ==========================================================================
    # Files
    # ==========================================================================

    def add_file(self, file: FileRecord) -> int:
        """Add or update a file record.

        Returns:
            File ID
        """
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO files (drive_id, path, filename, size, created,
                   modified, file_type, mime_type, quick_hash, content_hash,
                   perceptual_hash, scan_date, is_deleted)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(drive_id, path) DO UPDATE SET
                   filename = ?, size = ?, created = ?, modified = ?,
                   file_type = ?, mime_type = ?, quick_hash = ?, content_hash = ?,
                   perceptual_hash = ?, scan_date = ?, is_deleted = ?
                   RETURNING id""",
                (
                    file.drive_id, file.path, file.filename, file.size,
                    file.created, file.modified, file.file_type, file.mime_type,
                    file.quick_hash, file.content_hash, file.perceptual_hash,
                    file.scan_date or datetime.now(), file.is_deleted,
                    file.filename, file.size, file.created, file.modified,
                    file.file_type, file.mime_type, file.quick_hash, file.content_hash,
                    file.perceptual_hash, file.scan_date or datetime.now(), file.is_deleted
                )
            )
            row = cursor.fetchone()
            return row[0]

    def add_files_batch(self, files: list[FileRecord]) -> None:
        """Add multiple files in a batch."""
        with self.connection() as conn:
            conn.executemany(
                """INSERT INTO files (drive_id, path, filename, size, created,
                   modified, file_type, mime_type, scan_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(drive_id, path) DO UPDATE SET
                   size = ?, modified = ?, scan_date = ?""",
                [
                    (
                        f.drive_id, f.path, f.filename, f.size, f.created,
                        f.modified, f.file_type, f.mime_type,
                        f.scan_date or datetime.now(),
                        f.size, f.modified, f.scan_date or datetime.now()
                    )
                    for f in files
                ]
            )

    def get_file(self, file_id: int) -> Optional[FileRecord]:
        """Get a file by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE id = ?", (file_id,)
            ).fetchone()

            if row:
                return FileRecord(**dict(row))
            return None

    def get_file_by_path(self, drive_id: str, path: str) -> Optional[FileRecord]:
        """Get a file by drive and path."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE drive_id = ? AND path = ?",
                (drive_id, path)
            ).fetchone()

            if row:
                return FileRecord(**dict(row))
            return None

    def get_file_by_path_any(self, path: str) -> Optional[FileRecord]:
        """Get a file by path across all drives."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE path = ? AND is_deleted = FALSE",
                (path,)
            ).fetchone()

            if row:
                return FileRecord(**dict(row))
            return None

    def get_files_by_size(self, size: int) -> list[FileRecord]:
        """Get all files with a specific size."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE size = ? AND is_deleted = FALSE",
                (size,)
            ).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_files_by_hash(self, content_hash: str) -> list[FileRecord]:
        """Get all files with a specific content hash."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE content_hash = ? AND is_deleted = FALSE",
                (content_hash,)
            ).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_files_by_path_prefix(self, drive_id: str, path_prefix: str) -> list[FileRecord]:
        """Get files under a path prefix for a drive."""
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM files
                   WHERE drive_id = ? AND path LIKE ? AND is_deleted = FALSE""",
                (drive_id, f"{path_prefix}%")
            ).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_hashes_for_drive(
        self,
        drive_id: str,
        path_prefix: Optional[str] = None,
    ) -> set[str]:
        """Get distinct content hashes for a drive (optionally filtered by path prefix)."""
        with self.connection() as conn:
            if path_prefix:
                rows = conn.execute(
                    """SELECT DISTINCT content_hash FROM files
                       WHERE drive_id = ? AND path LIKE ? AND content_hash IS NOT NULL
                       AND is_deleted = FALSE""",
                    (drive_id, f"{path_prefix}%")
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT DISTINCT content_hash FROM files
                       WHERE drive_id = ? AND content_hash IS NOT NULL
                       AND is_deleted = FALSE""",
                    (drive_id,)
                ).fetchall()
            return {row[0] for row in rows if row[0]}

    def get_path_stats_like(
        self,
        like_pattern: str,
        drive_id: Optional[str] = None,
    ) -> tuple[int, int]:
        """Get count and total size for paths matching a LIKE pattern."""
        with self.connection() as conn:
            if drive_id:
                row = conn.execute(
                    """SELECT COUNT(*) as cnt, SUM(size) as total
                       FROM files
                       WHERE drive_id = ? AND path LIKE ? AND is_deleted = FALSE""",
                    (drive_id, like_pattern)
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT COUNT(*) as cnt, SUM(size) as total
                       FROM files
                       WHERE path LIKE ? AND is_deleted = FALSE""",
                    (like_pattern,)
                ).fetchone()
            return (row["cnt"] or 0, row["total"] or 0)

    def get_content_hash_groups(
        self,
        min_drives: int = 1,
        max_drives: Optional[int] = None,
        limit: int = 10000,
    ) -> list[tuple[str, int, int, int]]:
        """Get grouped content hashes with drive counts.

        Returns:
            List of (content_hash, size, file_count, drive_count)
        """
        with self.connection() as conn:
            query = """
                SELECT content_hash,
                       MAX(size) AS size,
                       COUNT(*) AS file_count,
                       COUNT(DISTINCT drive_id) AS drive_count
                FROM files
                WHERE content_hash IS NOT NULL AND is_deleted = FALSE
                GROUP BY content_hash
                HAVING drive_count >= ?
            """
            params: list[Any] = [min_drives]

            if max_drives is not None:
                query += " AND drive_count <= ?"
                params.append(max_drives)

            query += " ORDER BY drive_count ASC, file_count DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [(row[0], row[1], row[2], row[3]) for row in rows]

    def get_files_needing_hash(self, drive_id: Optional[str] = None) -> list[FileRecord]:
        """Get files that need hashing (grouped by size > 1)."""
        with self.connection() as conn:
            query = """
                SELECT f.* FROM files f
                INNER JOIN (
                    SELECT size FROM files
                    WHERE content_hash IS NULL AND is_deleted = FALSE
                    GROUP BY size HAVING COUNT(*) > 1
                ) sizes ON f.size = sizes.size
                WHERE f.content_hash IS NULL AND f.is_deleted = FALSE
            """
            if drive_id:
                query += " AND f.drive_id = ?"
                rows = conn.execute(query, (drive_id,)).fetchall()
            else:
                rows = conn.execute(query).fetchall()

            return [FileRecord(**dict(row)) for row in rows]

    def get_content_hash_counts(self) -> tuple[int, int]:
        """Return total files and count with content hashes."""
        with self.connection() as conn:
            row = conn.execute(
                """SELECT COUNT(*) as total,
                          SUM(CASE WHEN content_hash IS NOT NULL THEN 1 ELSE 0 END) as hashed
                   FROM files WHERE is_deleted = FALSE"""
            ).fetchone()
            total = row["total"] or 0
            hashed = row["hashed"] or 0
            return total, hashed

    def get_files_by_type(
        self,
        extensions: list[str],
        drive_id: Optional[str] = None,
        limit: int = 100000,
    ) -> list[FileRecord]:
        """Get files by file type extension.

        Args:
            extensions: List of extensions to match (e.g., ['.jpg', '.png'])
            drive_id: Optional drive filter
            limit: Maximum files to return

        Returns:
            List of FileRecord objects
        """
        with self.connection() as conn:
            # Build query with multiple OR conditions for extensions
            placeholders = ", ".join("?" for _ in extensions)
            query = f"""
                SELECT * FROM files
                WHERE is_deleted = FALSE
                AND LOWER(file_type) IN ({placeholders})
            """
            params: list[Any] = [ext.lower() for ext in extensions]

            if drive_id:
                query += " AND drive_id = ?"
                params.append(drive_id)

            query += " LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def update_file_hash(
        self,
        file_id: int,
        quick_hash: Optional[str] = None,
        content_hash: Optional[str] = None,
        perceptual_hash: Optional[str] = None
    ) -> None:
        """Update hash values for a file."""
        updates = []
        params = []

        if quick_hash is not None:
            updates.append("quick_hash = ?")
            params.append(quick_hash)
        if content_hash is not None:
            updates.append("content_hash = ?")
            params.append(content_hash)
        if perceptual_hash is not None:
            updates.append("perceptual_hash = ?")
            params.append(perceptual_hash)

        if updates:
            params.append(file_id)
            with self.connection() as conn:
                conn.execute(
                    f"UPDATE files SET {', '.join(updates)} WHERE id = ?",
                    params
                )

    def update_file_scan_date(self, file_id: int, scan_date: Optional[datetime] = None) -> None:
        """Update scan date (and undelete) for a file."""
        if scan_date is None:
            scan_date = datetime.now()
        with self.connection() as conn:
            conn.execute(
                "UPDATE files SET scan_date = ?, is_deleted = FALSE WHERE id = ?",
                (scan_date, file_id)
            )

    def mark_files_deleted_before_scan(
        self,
        drive_id: str,
        scan_start: datetime,
    ) -> int:
        """Mark files as deleted if not seen in the current scan."""
        with self.connection() as conn:
            cursor = conn.execute(
                """UPDATE files
                   SET is_deleted = TRUE
                   WHERE drive_id = ?
                     AND is_deleted = FALSE
                     AND (scan_date IS NULL OR scan_date < ?)""",
                (drive_id, scan_start),
            )
            return cursor.rowcount if cursor.rowcount is not None else 0

    def reset_deleted_flags(self, drive_id: str, touch_scan_date: bool = True) -> int:
        """Clear deleted flags for a drive and optionally refresh scan_date."""
        with self.connection() as conn:
            if touch_scan_date:
                cursor = conn.execute(
                    "UPDATE files SET is_deleted = FALSE, scan_date = ? WHERE drive_id = ?",
                    (datetime.now(), drive_id),
                )
            else:
                cursor = conn.execute(
                    "UPDATE files SET is_deleted = FALSE WHERE drive_id = ?",
                    (drive_id,),
                )
            return cursor.rowcount if cursor.rowcount is not None else 0

    def mark_file_deleted(self, file_id: int) -> None:
        """Mark a file as deleted."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE files SET is_deleted = TRUE WHERE id = ?",
                (file_id,)
            )

    def mark_files_deleted_not_in_ids(
        self,
        drive_id: str,
        seen_file_ids: list[int],
        batch_size: int = 1000,
    ) -> int:
        """Mark files as deleted when missing from the latest scan.

        Args:
            drive_id: Drive whose files are being reconciled
            seen_file_ids: File IDs observed during the scan
            batch_size: Insert batch size for temp table

        Returns:
            Count of files marked deleted
        """
        with self.connection() as conn:
            conn.execute("DROP TABLE IF EXISTS temp_seen_files")
            conn.execute("CREATE TEMP TABLE temp_seen_files (id INTEGER PRIMARY KEY)")

            if seen_file_ids:
                for i in range(0, len(seen_file_ids), batch_size):
                    chunk = seen_file_ids[i:i + batch_size]
                    conn.executemany(
                        "INSERT OR IGNORE INTO temp_seen_files (id) VALUES (?)",
                        [(file_id,) for file_id in chunk]
                    )

            cursor = conn.execute(
                """
                UPDATE files
                SET is_deleted = TRUE
                WHERE drive_id = ?
                  AND is_deleted = FALSE
                  AND id NOT IN (SELECT id FROM temp_seen_files)
                """,
                (drive_id,),
            )
            deleted_count = cursor.rowcount if cursor.rowcount is not None else 0

            conn.execute("DROP TABLE IF EXISTS temp_seen_files")
            return deleted_count

    def mark_faces_analyzed(
        self,
        file_id: int,
        faces_found: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Record that face analysis has been run for a file."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO file_ai_status (file_id, faces_analyzed, faces_found, faces_error, faces_updated_at)
                   VALUES (?, TRUE, ?, ?, ?)
                   ON CONFLICT(file_id) DO UPDATE SET
                       faces_analyzed = TRUE,
                       faces_found = ?,
                       faces_error = ?,
                       faces_updated_at = ?""",
                (
                    file_id,
                    faces_found,
                    error,
                    datetime.now(),
                    faces_found,
                    error,
                    datetime.now(),
                )
            )

    def is_faces_analyzed(self, file_id: int) -> bool:
        """Return True if face analysis has been recorded for a file."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT faces_analyzed FROM file_ai_status WHERE file_id = ?",
                (file_id,),
            ).fetchone()
            if not row:
                return False
            return bool(row["faces_analyzed"])

    def get_image_files_missing_face_analysis(
        self,
        limit: int = 200,
        drive_id: Optional[str] = None,
    ) -> list[FileRecord]:
        """Get image files that have not been processed for face analysis."""
        extensions = [".jpg", ".jpeg", ".png", ".heic", ".webp"]
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT f.* FROM files f
            LEFT JOIN file_ai_status s ON s.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND (s.faces_analyzed IS NULL OR s.faces_analyzed = FALSE)
        """
        params: list[Any] = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " LIMIT ?"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def backfill_face_status_from_existing_faces(
        self,
        drive_id: Optional[str] = None,
    ) -> int:
        """Mark files with existing faces as already analyzed."""
        query = """
            INSERT INTO file_ai_status (file_id, faces_analyzed, faces_found, faces_updated_at)
            SELECT f.id, TRUE, COUNT(fc.id), ?
            FROM files f
            JOIN faces fc ON fc.file_id = f.id
            LEFT JOIN file_ai_status s ON s.file_id = f.id
            WHERE s.file_id IS NULL
        """
        params: list[Any] = [datetime.now()]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " GROUP BY f.id"

        with self.connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.rowcount if cursor.rowcount is not None else 0

    def get_file_count(self, drive_id: Optional[str] = None) -> int:
        """Get total file count."""
        with self.connection() as conn:
            if drive_id:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM files WHERE drive_id = ? AND is_deleted = FALSE",
                    (drive_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM files WHERE is_deleted = FALSE"
                ).fetchone()
            return row["cnt"]

    # ==========================================================================
    # File Metadata
    # ==========================================================================

    def add_file_metadata(self, metadata: FileMetadata) -> None:
        """Add or update file metadata."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO file_metadata (file_id, exif_date, gps_lat, gps_lon,
                   location_name, camera_make, camera_model, width, height,
                   duration_seconds, orientation, raw_exif)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(file_id) DO UPDATE SET
                   exif_date = ?, gps_lat = ?, gps_lon = ?, location_name = ?,
                   camera_make = ?, camera_model = ?, width = ?, height = ?,
                   duration_seconds = ?, orientation = ?, raw_exif = ?""",
                (
                    metadata.file_id, metadata.exif_date, metadata.gps_lat,
                    metadata.gps_lon, metadata.location_name, metadata.camera_make,
                    metadata.camera_model, metadata.width, metadata.height,
                    metadata.duration_seconds, metadata.orientation, metadata.raw_exif,
                    metadata.exif_date, metadata.gps_lat, metadata.gps_lon,
                    metadata.location_name, metadata.camera_make, metadata.camera_model,
                    metadata.width, metadata.height, metadata.duration_seconds,
                    metadata.orientation, metadata.raw_exif
                )
            )

    def get_file_metadata(self, file_id: int) -> Optional[FileMetadata]:
        """Get metadata for a file."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM file_metadata WHERE file_id = ?", (file_id,)
            ).fetchone()

            if row:
                return FileMetadata(**dict(row))
            return None

    def get_files_by_extensions_after_id(
        self,
        extensions: list[str],
        last_id: int = 0,
        drive_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[FileRecord]:
        """Get files with given extensions after an ID for paging."""
        if not extensions:
            return []
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT f.* FROM files f
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND f.id > ?
        """
        params: list[Any] = [ext.lower() for ext in extensions]
        params.append(last_id)
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " ORDER BY f.id LIMIT ?"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_files_missing_metadata_by_extensions(
        self,
        extensions: list[str],
        limit: int = 200,
        drive_id: Optional[str] = None,
    ) -> list[FileRecord]:
        """Get files without extracted metadata for provided extensions."""
        if not extensions:
            return []
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT f.* FROM files f
            LEFT JOIN file_metadata m ON m.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND m.file_id IS NULL
        """
        params: list[Any] = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " LIMIT ?"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_files_missing_ocr_by_extensions(
        self,
        extensions: list[str],
        limit: int = 200,
        drive_id: Optional[str] = None,
    ) -> list[FileRecord]:
        """Get files missing OCR/text extraction for provided extensions."""
        if not extensions:
            return []
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT f.* FROM files f
            LEFT JOIN ocr_results o ON o.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND o.file_id IS NULL
        """
        params: list[Any] = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " LIMIT ?"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_files_missing_summaries_by_extensions(
        self,
        extensions: list[str],
        limit: int = 200,
        drive_id: Optional[str] = None,
    ) -> list[FileRecord]:
        """Get files missing AI summaries for provided extensions."""
        if not extensions:
            return []
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT f.* FROM files f
            LEFT JOIN ai_summaries a ON a.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND a.file_id IS NULL
        """
        params: list[Any] = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " LIMIT ?"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_image_files_missing_metadata(
        self,
        limit: int = 200,
        drive_id: Optional[str] = None,
    ) -> list[FileRecord]:
        """Get image files without extracted metadata."""
        extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif"]
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT f.* FROM files f
            LEFT JOIN file_metadata m ON m.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND m.file_id IS NULL
        """
        params: list[Any] = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " LIMIT ?"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_image_files_missing_scene_analysis(
        self,
        limit: int = 200,
        drive_id: Optional[str] = None,
    ) -> list[FileRecord]:
        """Get image files missing scene analysis."""
        extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif"]
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT f.* FROM files f
            LEFT JOIN scene_analysis s ON s.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND s.file_id IS NULL
        """
        params: list[Any] = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " LIMIT ?"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_image_files_missing_scene_objects(
        self,
        limit: int = 200,
        drive_id: Optional[str] = None,
    ) -> list[FileRecord]:
        """Get image files with scene analysis but missing object labels."""
        extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif"]
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT f.* FROM files f
            LEFT JOIN scene_analysis s ON s.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND (s.file_id IS NULL OR s.objects IS NULL OR s.objects = '' OR s.objects = '[]')
        """
        params: list[Any] = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " LIMIT ?"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_image_files_missing_ocr(
        self,
        limit: int = 200,
        drive_id: Optional[str] = None,
    ) -> list[FileRecord]:
        """Get image files missing OCR text."""
        extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif"]
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT f.* FROM files f
            LEFT JOIN ocr_results o ON o.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND o.file_id IS NULL
        """
        params: list[Any] = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " LIMIT ?"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_image_files_missing_summaries(
        self,
        limit: int = 200,
        drive_id: Optional[str] = None,
    ) -> list[FileRecord]:
        """Get image files missing AI summaries."""
        extensions = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif"]
        placeholders = ", ".join("?" for _ in extensions)
        query = f"""
            SELECT f.* FROM files f
            LEFT JOIN ai_summaries a ON a.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND LOWER(f.file_type) IN ({placeholders})
              AND a.file_id IS NULL
        """
        params: list[Any] = [ext.lower() for ext in extensions]
        if drive_id:
            query += " AND f.drive_id = ?"
            params.append(drive_id)
        query += " LIMIT ?"
        params.append(limit)

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    # ==========================================================================
    # Duplicate Groups
    # ==========================================================================

    def create_duplicate_group(
        self,
        match_type: MatchType,
        similarity: float,
        file_ids: list[int],
        keeper_id: Optional[int] = None
    ) -> int:
        """Create a duplicate group with members.

        Returns:
            Group ID
        """
        with self.connection() as conn:
            # Get file sizes for calculation
            rows = conn.execute(
                f"SELECT id, size FROM files WHERE id IN ({','.join('?' * len(file_ids))})",
                file_ids
            ).fetchall()

            total_size = sum(row["size"] for row in rows)
            wasted_size = total_size - min(row["size"] for row in rows)

            cursor = conn.execute(
                """INSERT INTO duplicate_groups (match_type, similarity, file_count,
                   total_size, wasted_size, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    match_type.value, similarity, len(file_ids),
                    total_size, wasted_size, GroupStatus.PENDING.value, datetime.now()
                )
            )
            group_id = cursor.fetchone()[0]

            # Add members
            for file_id in file_ids:
                is_keeper = file_id == keeper_id
                conn.execute(
                    "INSERT INTO duplicate_members (group_id, file_id, is_keeper) VALUES (?, ?, ?)",
                    (group_id, file_id, is_keeper)
                )

            return group_id

    def get_duplicate_group(self, group_id: int, include_files: bool = False) -> Optional[DuplicateGroup]:
        """Get a duplicate group by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM duplicate_groups WHERE id = ?", (group_id,)
            ).fetchone()

            if not row:
                return None

            data = dict(row)
            data["match_type"] = MatchType(data["match_type"])
            data["status"] = GroupStatus(data["status"])
            group = DuplicateGroup(**data)

            if include_files:
                member_rows = conn.execute(
                    """SELECT dm.*, f.* FROM duplicate_members dm
                       JOIN files f ON dm.file_id = f.id
                       WHERE dm.group_id = ?""",
                    (group_id,)
                ).fetchall()

                for mrow in member_rows:
                    mdata = dict(mrow)
                    file = FileRecord(
                        id=mdata["file_id"],
                        drive_id=mdata["drive_id"],
                        path=mdata["path"],
                        filename=mdata["filename"],
                        size=mdata["size"],
                        created=mdata["created"],
                        modified=mdata["modified"],
                        file_type=mdata["file_type"],
                        content_hash=mdata["content_hash"],
                    )
                    member = DuplicateMember(
                        group_id=group_id,
                        file_id=mdata["file_id"],
                        is_keeper=mdata["is_keeper"],
                        file=file
                    )
                    group.members.append(member)

            return group

    def get_duplicate_groups(
        self,
        status: Optional[GroupStatus] = None,
        match_type: Optional[MatchType] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[DuplicateGroup]:
        """Get duplicate groups with optional filters."""
        with self.connection() as conn:
            query = "SELECT * FROM duplicate_groups WHERE 1=1"
            params: list[Any] = []

            if status:
                query += " AND status = ?"
                params.append(status.value)
            if match_type:
                query += " AND match_type = ?"
                params.append(match_type.value)

            query += " ORDER BY wasted_size DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            groups = []

            for row in rows:
                data = dict(row)
                data["match_type"] = MatchType(data["match_type"])
                data["status"] = GroupStatus(data["status"])
                groups.append(DuplicateGroup(**data))

            return groups

    def get_duplicate_group_counts(self) -> dict[GroupStatus, int]:
        """Get counts of duplicate groups by status."""
        counts = {
            GroupStatus.PENDING: 0,
            GroupStatus.RESOLVED: 0,
            GroupStatus.IGNORED: 0,
        }
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM duplicate_groups GROUP BY status"
            ).fetchall()
            for row in rows:
                try:
                    status = GroupStatus(row["status"])
                except ValueError:
                    continue
                counts[status] = row["cnt"]
        return counts

    def resolve_duplicate_group(self, group_id: int, keeper_id: int) -> None:
        """Mark a group as resolved with the keeper file."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE duplicate_members SET is_keeper = FALSE WHERE group_id = ?",
                (group_id,)
            )
            conn.execute(
                "UPDATE duplicate_members SET is_keeper = TRUE WHERE group_id = ? AND file_id = ?",
                (group_id, keeper_id)
            )
            conn.execute(
                "UPDATE duplicate_groups SET status = ?, resolved_at = ? WHERE id = ?",
                (GroupStatus.RESOLVED.value, datetime.now(), group_id)
            )

    # ==========================================================================
    # Action Log
    # ==========================================================================

    def log_action(self, entry: ActionLogEntry) -> int:
        """Log a file action.

        Returns:
            Log entry ID
        """
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO action_log (timestamp, action_type, source_path,
                   dest_path, file_hash, file_size, reversible, reversed, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    entry.timestamp or datetime.now(),
                    entry.action_type.value,
                    entry.source_path,
                    entry.dest_path,
                    entry.file_hash,
                    entry.file_size,
                    entry.reversible,
                    entry.reversed,
                    entry.metadata
                )
            )
            return cursor.fetchone()[0]

    def get_action_log(
        self,
        action_type: Optional[ActionType] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        reversed: Optional[bool] = None,
        path_contains: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[ActionLogEntry]:
        """Get action log entries with filtering.

        Args:
            action_type: Filter by action type
            start_date: Filter entries after this date
            end_date: Filter entries before this date
            reversed: Filter by reversed status (True/False/None for all)
            path_contains: Filter by source path containing string
            limit: Maximum entries to return
            offset: Skip this many entries

        Returns:
            List of ActionLogEntry objects
        """
        with self.connection() as conn:
            query = "SELECT * FROM action_log WHERE 1=1"
            params: list[Any] = []

            if action_type:
                query += " AND action_type = ?"
                params.append(action_type.value)

            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)

            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)

            if reversed is not None:
                query += " AND reversed = ?"
                params.append(reversed)

            if path_contains:
                query += " AND (source_path LIKE ? OR dest_path LIKE ?)"
                params.append(f"%{path_contains}%")
                params.append(f"%{path_contains}%")

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            rows = conn.execute(query, params).fetchall()
            entries = []

            for row in rows:
                data = dict(row)
                data["action_type"] = ActionType(data["action_type"])
                entries.append(ActionLogEntry(**data))

            return entries

    def get_action_log_count(
        self,
        action_type: Optional[ActionType] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        reversed: Optional[bool] = None,
    ) -> int:
        """Get total count of action log entries matching filters."""
        with self.connection() as conn:
            query = "SELECT COUNT(*) FROM action_log WHERE 1=1"
            params: list[Any] = []

            if action_type:
                query += " AND action_type = ?"
                params.append(action_type.value)

            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)

            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)

            if reversed is not None:
                query += " AND reversed = ?"
                params.append(reversed)

            return conn.execute(query, params).fetchone()[0]

    def get_action_log_by_id(self, action_id: int) -> Optional[ActionLogEntry]:
        """Get a single action log entry by ID.

        Args:
            action_id: ID of the action log entry

        Returns:
            ActionLogEntry or None if not found
        """
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM action_log WHERE id = ?",
                (action_id,)
            ).fetchone()

            if row:
                data = dict(row)
                data["action_type"] = ActionType(data["action_type"])
                return ActionLogEntry(**data)
            return None

    def mark_action_reversed(self, action_id: int) -> None:
        """Mark an action as reversed/undone."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE action_log SET reversed = TRUE WHERE id = ?",
                (action_id,)
            )

    # ==========================================================================
    # Persons and Faces
    # ==========================================================================

    def add_person(self, person: Person) -> int:
        """Add a new person.

        Args:
            person: Person object to add

        Returns:
            Person ID
        """
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO persons (name, birth_year, notes, is_favorite,
                   is_hidden, reference_photo_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    person.name, person.birth_year, person.notes,
                    person.is_favorite, person.is_hidden, person.reference_photo_id,
                    person.created_at or datetime.now()
                )
            )
            return cursor.fetchone()[0]

    def get_person(self, person_id: int) -> Optional[Person]:
        """Get a person by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM persons WHERE id = ?", (person_id,)
            ).fetchone()

            if row:
                return Person(**dict(row))
            return None

    def get_all_persons(
        self,
        named_only: bool = False,
        include_hidden: bool = False,
    ) -> list[Person]:
        """Get all persons.

        Args:
            named_only: If True, only return persons with names
            include_hidden: If True, include hidden/ignored persons
        """
        with self.connection() as conn:
            conditions = []
            if named_only:
                conditions.append("name IS NOT NULL")
            if not include_hidden:
                conditions.append("(is_hidden = FALSE OR is_hidden IS NULL)")

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"SELECT * FROM persons {where_clause} ORDER BY name"
            rows = conn.execute(query).fetchall()
            return [Person(**dict(row)) for row in rows]

    def update_person(self, person: Person) -> None:
        """Update a person's details."""
        if person.id is None:
            raise ValueError("Person ID is required for update")

        with self.connection() as conn:
            conn.execute(
                """UPDATE persons SET name = ?, birth_year = ?, notes = ?,
                   is_favorite = ?, is_hidden = ?, reference_photo_id = ? WHERE id = ?""",
                (
                    person.name, person.birth_year, person.notes,
                    person.is_favorite, person.is_hidden, person.reference_photo_id, person.id
                )
            )

    def update_person_name(self, person_id: int, name: str) -> None:
        """Update a person's name."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE persons SET name = ? WHERE id = ?",
                (name, person_id)
            )

    def get_favorite_persons(self) -> list[Person]:
        """Get all favorite persons."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM persons WHERE is_favorite = TRUE ORDER BY name"
            ).fetchall()
            return [Person(**dict(row)) for row in rows]

    def get_hidden_persons(self) -> list[Person]:
        """Get all hidden/ignored persons."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM persons WHERE is_hidden = TRUE ORDER BY name"
            ).fetchall()
            return [Person(**dict(row)) for row in rows]

    def get_hidden_person_count(self) -> int:
        """Get count of hidden persons."""
        with self.connection() as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM persons WHERE is_hidden = TRUE"
            ).fetchone()
            return result[0] if result else 0

    def set_person_hidden(self, person_id: int, hidden: bool) -> None:
        """Set a person's hidden status.

        Args:
            person_id: Person ID
            hidden: True to hide, False to restore
        """
        with self.connection() as conn:
            conn.execute(
                "UPDATE persons SET is_hidden = ? WHERE id = ?",
                (hidden, person_id)
            )

    def create_hidden_person_from_cluster(
        self,
        cluster_face_ids: list[int],
    ) -> int:
        """Create a hidden person from a cluster of faces.

        Creates a person named 'Unknown #N' with is_hidden=True
        and assigns all provided faces to it.

        Args:
            cluster_face_ids: List of face IDs to assign to the hidden person

        Returns:
            The new person's ID
        """
        with self.connection() as conn:
            # Get the next unknown number
            result = conn.execute(
                "SELECT COUNT(*) FROM persons WHERE name LIKE 'Unknown #%'"
            ).fetchone()
            next_num = (result[0] if result else 0) + 1

            # Create hidden person
            cursor = conn.execute(
                """INSERT INTO persons (name, is_hidden, created_at, photo_count)
                   VALUES (?, TRUE, ?, ?) RETURNING id""",
                (f"Unknown #{next_num}", datetime.now(), len(cluster_face_ids))
            )
            person_id = cursor.fetchone()[0]

            # Assign faces
            for face_id in cluster_face_ids:
                conn.execute(
                    "UPDATE faces SET person_id = ? WHERE id = ?",
                    (person_id, face_id)
                )

            return person_id

    def delete_person(self, person_id: int) -> int:
        """Delete a person and unassign their faces.

        Faces are unassigned (person_id set to NULL), not deleted.

        Args:
            person_id: Person ID to delete

        Returns:
            Number of faces unassigned
        """
        with self.connection() as conn:
            # Count faces first (more reliable than rowcount)
            face_count = conn.execute(
                "SELECT COUNT(*) FROM faces WHERE person_id = ?",
                (person_id,)
            ).fetchone()[0]

            # Unassign faces
            conn.execute(
                "UPDATE faces SET person_id = NULL WHERE person_id = ?",
                (person_id,)
            )

            # Delete the person
            conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))

            return face_count

    def add_face(self, face: Face) -> int:
        """Add a detected face.

        Returns:
            Face ID
        """
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO faces (file_id, person_id, bbox_x, bbox_y, bbox_w, bbox_h,
                   embedding, confidence, estimated_age, estimated_gender, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    face.file_id, face.person_id, face.bbox_x, face.bbox_y,
                    face.bbox_w, face.bbox_h, face.embedding, face.confidence,
                    face.estimated_age, face.estimated_gender,
                    face.created_at or datetime.now()
                )
            )
            return cursor.fetchone()[0]

    def get_faces_for_file(self, file_id: int) -> list[Face]:
        """Get all faces in a file."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM faces WHERE file_id = ?", (file_id,)
            ).fetchall()
            return [Face(**dict(row)) for row in rows]

    def delete_faces_for_file(self, file_id: int) -> int:
        """Delete all faces for a file."""
        with self.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM faces WHERE file_id = ?",
                (file_id,),
            )
            return cursor.rowcount if cursor.rowcount is not None else 0

    def get_faces_for_person(self, person_id: int, limit: int = 10000) -> list[Face]:
        """Get all faces for a person.

        Args:
            person_id: Person ID to get faces for
            limit: Maximum number of faces to return

        Returns:
            List of Face objects
        """
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM faces WHERE person_id = ? LIMIT ?",
                (person_id, limit)
            ).fetchall()
            return [Face(**dict(row)) for row in rows]

    def unassign_face_from_person(self, face_id: int) -> bool:
        """Unassign a face from its person.

        Args:
            face_id: Face ID to unassign

        Returns:
            True if face was unassigned, False if face not found
        """
        with self.connection() as conn:
            # Get the current person_id before unassigning
            row = conn.execute(
                "SELECT person_id FROM faces WHERE id = ?",
                (face_id,)
            ).fetchone()
            if not row or not row[0]:
                return False

            old_person_id = row[0]

            # Unassign the face
            cursor = conn.execute(
                "UPDATE faces SET person_id = NULL WHERE id = ?",
                (face_id,)
            )

            if cursor.rowcount > 0:
                # Update old person's photo count
                conn.execute(
                    """UPDATE persons SET photo_count = (
                        SELECT COUNT(DISTINCT file_id) FROM faces WHERE person_id = ?
                    ) WHERE id = ?""",
                    (old_person_id, old_person_id)
                )
                return True
            return False

    def get_faces_by_ids(self, face_ids: list[int]) -> list[Face]:
        """Get faces by a list of IDs."""
        if not face_ids:
            return []
        placeholders = ", ".join("?" for _ in face_ids)
        query = f"SELECT * FROM faces WHERE id IN ({placeholders})"
        with self.connection() as conn:
            rows = conn.execute(query, face_ids).fetchall()
            return [Face(**dict(row)) for row in rows]

    def assign_face_to_person(self, face_id: int, person_id: int) -> None:
        """Assign a face to a person."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE faces SET person_id = ? WHERE id = ?",
                (person_id, face_id)
            )
            # Update person photo count
            conn.execute(
                """UPDATE persons SET photo_count = (
                    SELECT COUNT(DISTINCT file_id) FROM faces WHERE person_id = ?
                ) WHERE id = ?""",
                (person_id, person_id)
            )

    def get_unassigned_faces(
        self,
        limit: int = 10000,
        min_confidence: Optional[float] = None,
    ) -> list[Face]:
        """Get faces not assigned to any person."""
        query = "SELECT * FROM faces WHERE person_id IS NULL"
        params: list[Any] = []
        if min_confidence is not None:
            query += " AND confidence >= ?"
            params.append(min_confidence)
        query += " LIMIT ?"
        params.append(limit)
        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Face(**dict(row)) for row in rows]

    def get_all_faces(self, limit: int = 100000) -> list[Face]:
        """Get all faces."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM faces LIMIT ?", (limit,)
            ).fetchall()
            return [Face(**dict(row)) for row in rows]

    def add_face_blacklist(self, file_id: int, reason: Optional[str] = None) -> None:
        """Blacklist a file from future face detection."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO face_blacklist (file_id, reason, created_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(file_id) DO UPDATE SET
                       reason = ?,
                       created_at = ?""",
                (file_id, reason, datetime.now(), reason, datetime.now()),
            )

    def is_face_blacklisted(self, file_id: int) -> bool:
        """Check if a file is blacklisted for face detection."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM face_blacklist WHERE file_id = ?",
                (file_id,),
            ).fetchone()
            return row is not None

    def create_face_cluster_run(self, method: str = "auto") -> int:
        """Create a new face cluster run."""
        with self.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO face_cluster_runs (method, created_at) VALUES (?, ?) RETURNING id",
                (method, datetime.now()),
            )
            return cursor.fetchone()[0]

    def get_latest_face_cluster_run(self) -> Optional[tuple[int, str]]:
        """Get the most recent face cluster run."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT id, method FROM face_cluster_runs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return (row["id"], row["method"])

    def clear_face_clusters_for_run(self, run_id: int) -> None:
        """Delete clusters and members for a run."""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM face_clusters WHERE run_id = ?",
                (run_id,),
            )

    def create_face_cluster(self, run_id: int, method: str = "auto") -> int:
        """Create a cluster for a run."""
        with self.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO face_clusters (run_id, method, created_at) VALUES (?, ?, ?) RETURNING id",
                (run_id, method, datetime.now()),
            )
            return cursor.fetchone()[0]

    def add_face_cluster_members(self, cluster_id: int, face_ids: list[int]) -> None:
        """Add faces to a cluster."""
        if not face_ids:
            return
        with self.connection() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO face_cluster_members (cluster_id, face_id) VALUES (?, ?)",
                [(cluster_id, face_id) for face_id in face_ids],
            )

    def save_face_clusters(self, run_id: int, clusters: list[list[int]], method: str = "auto") -> None:
        """Save clusters for a run, replacing any existing clusters for that run."""
        with self.connection() as conn:
            conn.execute("DELETE FROM face_clusters WHERE run_id = ?", (run_id,))
            for face_ids in clusters:
                cursor = conn.execute(
                    "INSERT INTO face_clusters (run_id, method, created_at) VALUES (?, ?, ?) RETURNING id",
                    (run_id, method, datetime.now()),
                )
                cluster_id = cursor.fetchone()[0]
                conn.executemany(
                    "INSERT OR IGNORE INTO face_cluster_members (cluster_id, face_id) VALUES (?, ?)",
                    [(cluster_id, fid) for fid in face_ids],
                )

    def get_face_clusters_for_run(self, run_id: int) -> list[tuple[int, list[int]]]:
        """Get clusters and members for a run."""
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT c.id as cluster_id, m.face_id
                   FROM face_clusters c
                   JOIN face_cluster_members m ON m.cluster_id = c.id
                   WHERE c.run_id = ?
                   ORDER BY c.id""",
                (run_id,),
            ).fetchall()
        clusters: dict[int, list[int]] = {}
        for row in rows:
            clusters.setdefault(row["cluster_id"], []).append(row["face_id"])
        return [(cid, face_ids) for cid, face_ids in clusters.items()]

    def move_faces_to_new_cluster(
        self,
        run_id: int,
        face_ids: list[int],
        from_cluster_id: int,
        method: str = "manual",
    ) -> Optional[int]:
        """Move faces to a new cluster and record history."""
        if not face_ids:
            return None
        with self.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO face_clusters (run_id, method, created_at) VALUES (?, ?, ?) RETURNING id",
                (run_id, method, datetime.now()),
            )
            new_cluster_id = cursor.fetchone()[0]
            conn.executemany(
                "INSERT OR IGNORE INTO face_cluster_members (cluster_id, face_id) VALUES (?, ?)",
                [(new_cluster_id, fid) for fid in face_ids],
            )
            conn.executemany(
                "DELETE FROM face_cluster_members WHERE cluster_id = ? AND face_id = ?",
                [(from_cluster_id, fid) for fid in face_ids],
            )
            conn.execute(
                """INSERT INTO face_cluster_history (action, from_cluster_id, to_cluster_id, face_ids, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                ("split", from_cluster_id, new_cluster_id, json.dumps(face_ids), datetime.now()),
            )
            return new_cluster_id

    def delete_faces_for_drive(self, drive_id: str) -> int:
        """Delete all faces for a drive."""
        with self.connection() as conn:
            cursor = conn.execute(
                """DELETE FROM faces
                   WHERE file_id IN (SELECT id FROM files WHERE drive_id = ?)""",
                (drive_id,),
            )
            return cursor.rowcount if cursor.rowcount is not None else 0

    def delete_all_faces(self) -> int:
        """Delete all face detections."""
        with self.connection() as conn:
            cursor = conn.execute("DELETE FROM faces")
            return cursor.rowcount if cursor.rowcount is not None else 0

    def delete_unassigned_faces(self, drive_id: Optional[str] = None) -> int:
        """Delete faces without a person assignment."""
        with self.connection() as conn:
            if drive_id:
                cursor = conn.execute(
                    """DELETE FROM faces
                       WHERE person_id IS NULL
                         AND file_id IN (SELECT id FROM files WHERE drive_id = ?)""",
                    (drive_id,),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM faces WHERE person_id IS NULL"
                )
            return cursor.rowcount if cursor.rowcount is not None else 0

    def delete_low_confidence_faces(
        self,
        min_confidence: float,
        drive_id: Optional[str] = None,
    ) -> int:
        """Delete faces below a confidence threshold."""
        with self.connection() as conn:
            if drive_id:
                cursor = conn.execute(
                    """DELETE FROM faces
                       WHERE confidence < ?
                         AND file_id IN (SELECT id FROM files WHERE drive_id = ?)""",
                    (min_confidence, drive_id),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM faces WHERE confidence < ?",
                    (min_confidence,),
                )
            return cursor.rowcount if cursor.rowcount is not None else 0

    def get_face(self, face_id: int) -> Optional[Face]:
        """Get a face by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM faces WHERE id = ?", (face_id,)
            ).fetchone()
            if row:
                return Face(**dict(row))
            return None

    def update_face_bbox(self, face_id: int, x: int, y: int, w: int, h: int) -> None:
        """Update bounding box for a face."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE faces SET bbox_x = ?, bbox_y = ?, bbox_w = ?, bbox_h = ? WHERE id = ?",
                (x, y, w, h, face_id),
            )

    def update_person_photo_count(self, person_id: int) -> None:
        """Update photo count for a person."""
        with self.connection() as conn:
            conn.execute(
                """UPDATE persons SET photo_count = (
                    SELECT COUNT(DISTINCT file_id) FROM faces WHERE person_id = ?
                ) WHERE id = ?""",
                (person_id, person_id)
            )

    def get_face_count(
        self,
        person_id: Optional[int] = None,
        min_confidence: Optional[float] = None,
    ) -> int:
        """Get count of faces, optionally for a specific person."""
        with self.connection() as conn:
            if person_id is not None:
                query = "SELECT COUNT(*) FROM faces WHERE person_id = ?"
                params: list[Any] = [person_id]
                if min_confidence is not None:
                    query += " AND confidence >= ?"
                    params.append(min_confidence)
                return conn.execute(query, params).fetchone()[0]
            if min_confidence is not None:
                return conn.execute(
                    "SELECT COUNT(*) FROM faces WHERE confidence >= ?",
                    (min_confidence,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]

    def get_face_count_for_drive(self, drive_id: str) -> int:
        """Get count of faces for a specific drive."""
        with self.connection() as conn:
            return conn.execute(
                """SELECT COUNT(*) FROM faces f
                   JOIN files fi ON f.file_id = fi.id
                   WHERE fi.drive_id = ?""",
                (drive_id,)
            ).fetchone()[0]

    def get_low_confidence_face_count(
        self,
        threshold: float,
        drive_id: Optional[str] = None,
    ) -> int:
        """Get count of faces below the confidence threshold."""
        with self.connection() as conn:
            if drive_id:
                return conn.execute(
                    """SELECT COUNT(*) FROM faces f
                       JOIN files fi ON f.file_id = fi.id
                       WHERE f.confidence < ? AND fi.drive_id = ?""",
                    (threshold, drive_id)
                ).fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM faces WHERE confidence < ?",
                (threshold,)
            ).fetchone()[0]

    # ==========================================================================
    # Scene Analysis
    # ==========================================================================

    def add_scene_analysis(self, analysis: SceneAnalysis) -> None:
        """Add or update scene analysis."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO scene_analysis (file_id, categories, objects,
                   quality_score, blur_score, exposure_score, clip_embedding, analyzed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(file_id) DO UPDATE SET
                   categories = ?, objects = ?, quality_score = ?, blur_score = ?,
                   exposure_score = ?, clip_embedding = ?, analyzed_at = ?""",
                (
                    analysis.file_id, analysis.categories, analysis.objects,
                    analysis.quality_score, analysis.blur_score,
                    analysis.exposure_score, analysis.clip_embedding,
                    analysis.analyzed_at or datetime.now(),
                    analysis.categories, analysis.objects, analysis.quality_score,
                    analysis.blur_score, analysis.exposure_score,
                    analysis.clip_embedding, analysis.analyzed_at or datetime.now()
                )
            )

    def get_scene_analysis(self, file_id: int) -> Optional[SceneAnalysis]:
        """Get scene analysis for a file."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM scene_analysis WHERE file_id = ?", (file_id,)
            ).fetchone()

            if row:
                return SceneAnalysis(**dict(row))
            return None

    def get_all_scene_analyses_with_embeddings(
        self, limit: int = 100000
    ) -> list[tuple[int, Optional[bytes], Optional[str]]]:
        """Get all scene analyses with embeddings for search.

        Returns:
            List of (file_id, clip_embedding, categories) tuples
        """
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT file_id, clip_embedding, categories FROM scene_analysis LIMIT ?",
                (limit,)
            ).fetchall()
            return [(row[0], row[1], row[2]) for row in rows]

    def update_scene_objects(self, file_id: int, objects: list[str]) -> None:
        """Update detected objects for a scene analysis."""
        import json
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO scene_analysis (file_id, objects, analyzed_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(file_id) DO UPDATE SET objects = ?""",
                (file_id, json.dumps(objects), datetime.now(), json.dumps(objects))
            )

    def update_scene_quality(
        self,
        file_id: int,
        quality_score: float,
        blur_score: float,
        exposure_score: float,
    ) -> None:
        """Update quality scores for a scene analysis."""
        with self.connection() as conn:
            conn.execute(
                """UPDATE scene_analysis
                   SET quality_score = ?, blur_score = ?, exposure_score = ?
                   WHERE file_id = ?""",
                (quality_score, blur_score, exposure_score, file_id)
            )

    # ==========================================================================
    # OCR
    # ==========================================================================

    def add_ocr_result(self, result: OCRResult) -> None:
        """Add or update OCR results for a file."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO ocr_results (file_id, extracted_text, confidence, language, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(file_id) DO UPDATE SET
                   extracted_text = ?, confidence = ?, language = ?, created_at = ?""",
                (
                    result.file_id, result.extracted_text, result.confidence,
                    result.language, result.created_at or datetime.now(),
                    result.extracted_text, result.confidence, result.language,
                    result.created_at or datetime.now()
                )
            )

    def get_ocr_result(self, file_id: int) -> Optional[OCRResult]:
        """Get OCR result for a file."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM ocr_results WHERE file_id = ?", (file_id,)
            ).fetchone()

            if row:
                return OCRResult(**dict(row))
            return None

    def search_ocr_text(self, query: str, limit: int = 100) -> list[tuple[int, str]]:
        """Search OCR text using full-text search.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of (file_id, text snippet) tuples
        """
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT file_id, snippet(ocr_fts, 0, '<b>', '</b>', '...', 32)
                   FROM ocr_fts
                   WHERE ocr_fts MATCH ?
                   LIMIT ?""",
                (query, limit)
            ).fetchall()
            return [(row[0], row[1]) for row in rows]

    # ==========================================================================
    # Pets
    # ==========================================================================

    def add_pet(self, pet: Pet) -> int:
        """Add a new pet.

        Returns:
            Pet ID
        """
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO pets (name, species, breed, birth_year, color_pattern,
                   notes, is_favorite, reference_photo_id, created_at, photo_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    pet.name, pet.species, pet.breed, pet.birth_year,
                    pet.color_pattern, pet.notes, pet.is_favorite,
                    pet.reference_photo_id, pet.created_at or datetime.now(),
                    pet.photo_count
                )
            )
            return cursor.fetchone()[0]

    def get_pet(self, pet_id: int) -> Optional[Pet]:
        """Get a pet by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM pets WHERE id = ?", (pet_id,)
            ).fetchone()
            if row:
                return Pet(**dict(row))
            return None

    def get_all_pets(self) -> list[Pet]:
        """Get all pets."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM pets ORDER BY name"
            ).fetchall()
            return [Pet(**dict(row)) for row in rows]

    def update_pet(self, pet: Pet) -> None:
        """Update a pet."""
        if pet.id is None:
            return
        with self.connection() as conn:
            conn.execute(
                """UPDATE pets SET name = ?, species = ?, breed = ?, birth_year = ?,
                   color_pattern = ?, notes = ?, is_favorite = ?, reference_photo_id = ?
                   WHERE id = ?""",
                (
                    pet.name, pet.species, pet.breed, pet.birth_year,
                    pet.color_pattern, pet.notes, pet.is_favorite,
                    pet.reference_photo_id, pet.id
                )
            )

    def delete_pet(self, pet_id: int) -> None:
        """Delete a pet and unassign detections."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE pet_detections SET pet_id = NULL WHERE pet_id = ?",
                (pet_id,)
            )
            conn.execute("DELETE FROM pets WHERE id = ?", (pet_id,))

    def update_pet_photo_count(self, pet_id: int) -> None:
        """Update photo count for a pet."""
        with self.connection() as conn:
            conn.execute(
                """UPDATE pets SET photo_count = (
                    SELECT COUNT(DISTINCT file_id) FROM pet_detections WHERE pet_id = ?
                ) WHERE id = ?""",
                (pet_id, pet_id)
            )

    def add_pet_detection(self, detection: PetDetection) -> int:
        """Add a pet detection.

        Returns:
            Detection ID
        """
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO pet_detections (file_id, pet_id, species, breed,
                   bbox_x, bbox_y, bbox_w, bbox_h, embedding, confidence,
                   color_histogram, estimated_age_stage, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    detection.file_id, detection.pet_id, detection.species,
                    detection.breed, detection.bbox_x, detection.bbox_y,
                    detection.bbox_w, detection.bbox_h, detection.embedding,
                    detection.confidence, detection.color_histogram,
                    detection.estimated_age_stage.value if detection.estimated_age_stage else None,
                    detection.created_at or datetime.now()
                )
            )
            return cursor.fetchone()[0]

    def get_pet_detections_for_file(self, file_id: int) -> list[PetDetection]:
        """Get all pet detections in a file."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM pet_detections WHERE file_id = ?", (file_id,)
            ).fetchall()
            detections = []
            for row in rows:
                data = dict(row)
                if data.get("estimated_age_stage"):
                    data["estimated_age_stage"] = PetAgeStage(data["estimated_age_stage"])
                detections.append(PetDetection(**data))
            return detections

    def get_pet_detections_for_pet(self, pet_id: int) -> list[PetDetection]:
        """Get all detections for a pet."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM pet_detections WHERE pet_id = ?", (pet_id,)
            ).fetchall()
            detections = []
            for row in rows:
                data = dict(row)
                if data.get("estimated_age_stage"):
                    data["estimated_age_stage"] = PetAgeStage(data["estimated_age_stage"])
                detections.append(PetDetection(**data))
            return detections

    def get_unassigned_pet_detections(self, limit: int = 10000) -> list[PetDetection]:
        """Get pet detections not assigned to any pet."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM pet_detections WHERE pet_id IS NULL LIMIT ?",
                (limit,)
            ).fetchall()
            detections = []
            for row in rows:
                data = dict(row)
                if data.get("estimated_age_stage"):
                    data["estimated_age_stage"] = PetAgeStage(data["estimated_age_stage"])
                detections.append(PetDetection(**data))
            return detections

    def assign_pet_detection_to_pet(self, detection_id: int, pet_id: int) -> None:
        """Assign a pet detection to a pet."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE pet_detections SET pet_id = ? WHERE id = ?",
                (pet_id, detection_id)
            )

    def get_pet_detection_count(self, pet_id: Optional[int] = None) -> int:
        """Get count of pet detections."""
        with self.connection() as conn:
            if pet_id is not None:
                return conn.execute(
                    "SELECT COUNT(*) FROM pet_detections WHERE pet_id = ?",
                    (pet_id,)
                ).fetchone()[0]
            else:
                return conn.execute("SELECT COUNT(*) FROM pet_detections").fetchone()[0]

    # ==========================================================================
    # Statistics
    # ==========================================================================

    def get_statistics(self) -> dict[str, Any]:
        """Get database statistics."""
        with self.connection() as conn:
            stats = {}

            # File counts
            row = conn.execute(
                "SELECT COUNT(*) as total, SUM(size) as total_size FROM files WHERE is_deleted = FALSE"
            ).fetchone()
            stats["total_files"] = row["total"]
            stats["total_size"] = row["total_size"] or 0

            # Duplicate stats
            row = conn.execute(
                "SELECT COUNT(*) as groups, SUM(wasted_size) as wasted FROM duplicate_groups WHERE status = 'pending'"
            ).fetchone()
            stats["pending_duplicate_groups"] = row["groups"]
            stats["wasted_space"] = row["wasted"] or 0

            # Drive count
            row = conn.execute("SELECT COUNT(*) as cnt FROM drives").fetchone()
            stats["drive_count"] = row["cnt"]

            # Face stats
            row = conn.execute("SELECT COUNT(*) as cnt FROM faces").fetchone()
            stats["total_faces"] = row["cnt"]

            row = conn.execute("SELECT COUNT(*) as cnt FROM persons WHERE name IS NOT NULL").fetchone()
            stats["named_persons"] = row["cnt"]

            # AI summary stats
            row = conn.execute("SELECT COUNT(*) as cnt FROM ai_summaries").fetchone()
            stats["ai_summaries"] = row["cnt"]

            # Tag stats
            row = conn.execute("SELECT COUNT(*) as cnt FROM tags").fetchone()
            stats["total_tags"] = row["cnt"]

            return stats

    # ==========================================================================
    # AI Summaries
    # ==========================================================================

    def add_ai_summary(self, summary: AISummary) -> None:
        """Add or update an AI summary for a file."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO ai_summaries (file_id, summary, summary_model,
                   people_mentioned, activities, mood_atmosphere, time_of_day,
                   season_weather, document_type, document_summary, key_entities,
                   generated_at, user_edited)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(file_id) DO UPDATE SET
                   summary = ?, summary_model = ?, people_mentioned = ?,
                   activities = ?, mood_atmosphere = ?, time_of_day = ?,
                   season_weather = ?, document_type = ?, document_summary = ?,
                   key_entities = ?, generated_at = ?, user_edited = ?""",
                (
                    summary.file_id, summary.summary, summary.summary_model,
                    summary.people_mentioned, summary.activities,
                    summary.mood_atmosphere, summary.time_of_day,
                    summary.season_weather, summary.document_type,
                    summary.document_summary, summary.key_entities,
                    summary.generated_at or datetime.now(), summary.user_edited,
                    summary.summary, summary.summary_model, summary.people_mentioned,
                    summary.activities, summary.mood_atmosphere, summary.time_of_day,
                    summary.season_weather, summary.document_type,
                    summary.document_summary, summary.key_entities,
                    summary.generated_at or datetime.now(), summary.user_edited
                )
            )

    def get_ai_summary(self, file_id: int) -> Optional[AISummary]:
        """Get AI summary for a file."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM ai_summaries WHERE file_id = ?", (file_id,)
            ).fetchone()

            if row:
                return AISummary(**dict(row))
            return None

    def search_summaries(self, query: str, limit: int = 100) -> list[tuple[int, str]]:
        """Search AI summaries using full-text search.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of (file_id, summary snippet) tuples
        """
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT file_id, snippet(ai_summaries_fts, 0, '<b>', '</b>', '...', 32)
                   FROM ai_summaries_fts
                   WHERE ai_summaries_fts MATCH ?
                   LIMIT ?""",
                (query, limit)
            ).fetchall()
            return [(row[0], row[1]) for row in rows]

    def get_files_needing_summary(
        self,
        file_type: Optional[str] = None,
        limit: int = 100
    ) -> list[FileRecord]:
        """Get files that don't have AI summaries yet.

        Args:
            file_type: Filter by file type (e.g., '.jpg', '.pdf')
            limit: Maximum results
        """
        with self.connection() as conn:
            query = """
                SELECT f.* FROM files f
                LEFT JOIN ai_summaries a ON f.id = a.file_id
                WHERE a.file_id IS NULL AND f.is_deleted = FALSE
            """
            params: list[Any] = []

            if file_type:
                query += " AND f.file_type = ?"
                params.append(file_type)

            query += " LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    # ==========================================================================
    # Tags
    # ==========================================================================

    def add_tag(self, tag: Tag) -> int:
        """Add a new tag.

        Returns:
            Tag ID
        """
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO tags (name, category, is_system, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET category = ?, is_system = ?
                   RETURNING id""",
                (
                    tag.name, tag.category.value if tag.category else None,
                    tag.is_system, tag.created_at or datetime.now(),
                    tag.category.value if tag.category else None, tag.is_system
                )
            )
            return cursor.fetchone()[0]

    def get_tag(self, tag_id: int) -> Optional[Tag]:
        """Get a tag by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM tags WHERE id = ?", (tag_id,)
            ).fetchone()

            if row:
                data = dict(row)
                if data.get("category"):
                    data["category"] = TagCategory(data["category"])
                return Tag(**data)
            return None

    def get_tag_by_name(self, name: str) -> Optional[Tag]:
        """Get a tag by name."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM tags WHERE name = ?", (name,)
            ).fetchone()

            if row:
                data = dict(row)
                if data.get("category"):
                    data["category"] = TagCategory(data["category"])
                return Tag(**data)
            return None

    def get_all_tags(self, category: Optional[TagCategory] = None) -> list[Tag]:
        """Get all tags, optionally filtered by category."""
        with self.connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM tags WHERE category = ? ORDER BY name",
                    (category.value,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tags ORDER BY category, name"
                ).fetchall()

            tags = []
            for row in rows:
                data = dict(row)
                if data.get("category"):
                    data["category"] = TagCategory(data["category"])
                tags.append(Tag(**data))
            return tags

    def get_or_create_tag(
        self,
        name: str,
        category: Optional[TagCategory] = None,
        is_system: bool = False
    ) -> int:
        """Get a tag by name, creating it if it doesn't exist.

        Returns:
            Tag ID
        """
        existing = self.get_tag_by_name(name)
        if existing:
            return existing.id

        return self.add_tag(Tag(
            name=name,
            category=category,
            is_system=is_system
        ))

    def delete_tag(self, tag_id: int) -> None:
        """Delete a tag (and all file associations)."""
        with self.connection() as conn:
            conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

    # ==========================================================================
    # File Tags
    # ==========================================================================

    def add_file_tag(self, file_tag: FileTag) -> None:
        """Add a tag to a file."""
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO file_tags (file_id, tag_id, confidence, source, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(file_id, tag_id) DO UPDATE SET
                   confidence = ?, source = ?""",
                (
                    file_tag.file_id, file_tag.tag_id, file_tag.confidence,
                    file_tag.source.value, file_tag.created_at or datetime.now(),
                    file_tag.confidence, file_tag.source.value
                )
            )

    def add_file_tags_batch(
        self,
        file_id: int,
        tag_names: list[str],
        category: Optional[TagCategory] = None,
        source: TagSource = TagSource.AI,
        confidence: float = 1.0
    ) -> None:
        """Add multiple tags to a file at once.

        Creates tags if they don't exist.
        """
        for name in tag_names:
            tag_id = self.get_or_create_tag(name, category)
            self.add_file_tag(FileTag(
                file_id=file_id,
                tag_id=tag_id,
                confidence=confidence,
                source=source
            ))

    def get_file_tags(self, file_id: int) -> list[FileTag]:
        """Get all tags for a file."""
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT ft.*, t.name, t.category, t.is_system
                   FROM file_tags ft
                   JOIN tags t ON ft.tag_id = t.id
                   WHERE ft.file_id = ?
                   ORDER BY t.category, t.name""",
                (file_id,)
            ).fetchall()

            file_tags = []
            for row in rows:
                data = dict(row)
                tag = Tag(
                    id=data["tag_id"],
                    name=data["name"],
                    category=TagCategory(data["category"]) if data.get("category") else None,
                    is_system=data["is_system"]
                )
                file_tag = FileTag(
                    file_id=data["file_id"],
                    tag_id=data["tag_id"],
                    confidence=data["confidence"],
                    source=TagSource(data["source"]) if data.get("source") else TagSource.USER,
                    created_at=data["created_at"],
                    tag=tag
                )
                file_tags.append(file_tag)

            return file_tags

    def get_files_by_tag(
        self,
        tag_id: int,
        min_confidence: float = 0.0,
        limit: int = 100
    ) -> list[FileRecord]:
        """Get files with a specific tag.

        Args:
            tag_id: Tag ID
            min_confidence: Minimum confidence threshold
            limit: Maximum results
        """
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT f.* FROM files f
                   JOIN file_tags ft ON f.id = ft.file_id
                   WHERE ft.tag_id = ? AND ft.confidence >= ? AND f.is_deleted = FALSE
                   ORDER BY ft.confidence DESC
                   LIMIT ?""",
                (tag_id, min_confidence, limit)
            ).fetchall()
            return [FileRecord(**dict(row)) for row in rows]

    def get_files_by_tag_name(
        self,
        tag_name: str,
        min_confidence: float = 0.0,
        limit: int = 100
    ) -> list[FileRecord]:
        """Get files with a tag by name.

        Args:
            tag_name: Tag name
            min_confidence: Minimum confidence threshold
            limit: Maximum results
        """
        tag = self.get_tag_by_name(tag_name)
        if not tag:
            return []
        return self.get_files_by_tag(tag.id, min_confidence, limit)

    def remove_file_tag(self, file_id: int, tag_id: int) -> None:
        """Remove a tag from a file."""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM file_tags WHERE file_id = ? AND tag_id = ?",
                (file_id, tag_id)
            )

    def get_popular_tags(self, limit: int = 50) -> list[tuple[Tag, int]]:
        """Get most popular tags by file count.

        Returns:
            List of (tag, count) tuples
        """
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT t.*, COUNT(ft.file_id) as cnt
                   FROM tags t
                   JOIN file_tags ft ON t.id = ft.tag_id
                   GROUP BY t.id
                   ORDER BY cnt DESC
                   LIMIT ?""",
                (limit,)
            ).fetchall()

            results = []
            for row in rows:
                data = dict(row)
                cnt = data.pop("cnt")
                if data.get("category"):
                    data["category"] = TagCategory(data["category"])
                results.append((Tag(**data), cnt))

            return results

    # ==========================================================================
    # Combined Search
    # ==========================================================================

    def search_files(
        self,
        query: str,
        search_summaries: bool = True,
        search_ocr: bool = True,
        search_tags: bool = True,
        limit: int = 100
    ) -> list[tuple[FileRecord, str]]:
        """Search files by content, summaries, OCR text, and tags.

        Args:
            query: Search query
            search_summaries: Include AI summaries
            search_ocr: Include OCR text
            search_tags: Include tag names
            limit: Maximum results

        Returns:
            List of (file, match_source) tuples
        """
        results: dict[int, tuple[FileRecord, str]] = {}

        with self.connection() as conn:
            # Search AI summaries
            if search_summaries:
                rows = conn.execute(
                    """SELECT DISTINCT f.* FROM files f
                       JOIN ai_summaries_fts fts ON f.id = fts.rowid
                       WHERE ai_summaries_fts MATCH ? AND f.is_deleted = FALSE
                       LIMIT ?""",
                    (query, limit)
                ).fetchall()
                for row in rows:
                    file = FileRecord(**dict(row))
                    if file.id not in results:
                        results[file.id] = (file, "summary")

            # Search OCR text
            if search_ocr:
                rows = conn.execute(
                    """SELECT DISTINCT f.* FROM files f
                       JOIN ocr_fts fts ON f.id = fts.rowid
                       WHERE ocr_fts MATCH ? AND f.is_deleted = FALSE
                       LIMIT ?""",
                    (query, limit)
                ).fetchall()
                for row in rows:
                    file = FileRecord(**dict(row))
                    if file.id not in results:
                        results[file.id] = (file, "ocr")

            # Search tags
            if search_tags:
                rows = conn.execute(
                    """SELECT DISTINCT f.* FROM files f
                       JOIN file_tags ft ON f.id = ft.file_id
                       JOIN tags t ON ft.tag_id = t.id
                       WHERE t.name LIKE ? AND f.is_deleted = FALSE
                       LIMIT ?""",
                    (f"%{query}%", limit)
                ).fetchall()
                for row in rows:
                    file = FileRecord(**dict(row))
                    if file.id not in results:
                        results[file.id] = (file, "tag")

        return list(results.values())[:limit]
