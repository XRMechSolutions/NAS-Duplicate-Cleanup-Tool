"""Database manager for DupliCleaner.

Handles SQLite database connections, schema initialization,
and provides methods for common database operations.
"""

import sqlite3
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

    def mark_file_deleted(self, file_id: int) -> None:
        """Mark a file as deleted."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE files SET is_deleted = TRUE WHERE id = ?",
                (file_id,)
            )

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
                   reference_photo_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    person.name, person.birth_year, person.notes,
                    person.is_favorite, person.reference_photo_id,
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

    def get_all_persons(self, named_only: bool = False) -> list[Person]:
        """Get all persons.

        Args:
            named_only: If True, only return persons with names
        """
        with self.connection() as conn:
            if named_only:
                rows = conn.execute(
                    "SELECT * FROM persons WHERE name IS NOT NULL ORDER BY name"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM persons ORDER BY name"
                ).fetchall()
            return [Person(**dict(row)) for row in rows]

    def update_person(self, person: Person) -> None:
        """Update a person's details."""
        if person.id is None:
            raise ValueError("Person ID is required for update")

        with self.connection() as conn:
            conn.execute(
                """UPDATE persons SET name = ?, birth_year = ?, notes = ?,
                   is_favorite = ?, reference_photo_id = ? WHERE id = ?""",
                (
                    person.name, person.birth_year, person.notes,
                    person.is_favorite, person.reference_photo_id, person.id
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

    def get_faces_for_person(self, person_id: int) -> list[Face]:
        """Get all faces for a person."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM faces WHERE person_id = ?", (person_id,)
            ).fetchall()
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

    def get_unassigned_faces(self, limit: int = 10000) -> list[Face]:
        """Get faces not assigned to any person."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM faces WHERE person_id IS NULL LIMIT ?",
                (limit,)
            ).fetchall()
            return [Face(**dict(row)) for row in rows]

    def get_all_faces(self, limit: int = 100000) -> list[Face]:
        """Get all faces."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM faces LIMIT ?", (limit,)
            ).fetchall()
            return [Face(**dict(row)) for row in rows]

    def get_face(self, face_id: int) -> Optional[Face]:
        """Get a face by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM faces WHERE id = ?", (face_id,)
            ).fetchone()
            if row:
                return Face(**dict(row))
            return None

    def update_person_photo_count(self, person_id: int) -> None:
        """Update photo count for a person."""
        with self.connection() as conn:
            conn.execute(
                """UPDATE persons SET photo_count = (
                    SELECT COUNT(DISTINCT file_id) FROM faces WHERE person_id = ?
                ) WHERE id = ?""",
                (person_id, person_id)
            )

    def delete_person(self, person_id: int) -> None:
        """Delete a person and unassign their faces."""
        with self.connection() as conn:
            # Unassign faces
            conn.execute(
                "UPDATE faces SET person_id = NULL WHERE person_id = ?",
                (person_id,)
            )
            # Delete person
            conn.execute(
                "DELETE FROM persons WHERE id = ?",
                (person_id,)
            )

    def get_face_count(self, person_id: Optional[int] = None) -> int:
        """Get count of faces, optionally for a specific person."""
        with self.connection() as conn:
            if person_id is not None:
                return conn.execute(
                    "SELECT COUNT(*) FROM faces WHERE person_id = ?",
                    (person_id,)
                ).fetchone()[0]
            else:
                return conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]

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
                "UPDATE scene_analysis SET objects = ? WHERE file_id = ?",
                (json.dumps(objects), file_id)
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
