"""Storage analytics for DupliCleaner.

Computes storage breakdowns, duplicate waste analysis, and file age
distribution from the database.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TypeBreakdown:
    """Storage breakdown by file type."""
    extension: str
    count: int
    total_size: int
    percentage: float = 0.0


@dataclass
class YearBreakdown:
    """Storage breakdown by year."""
    year: int
    count: int
    total_size: int


@dataclass
class QuickWin:
    """A quick-win space recovery opportunity."""
    category: str
    description: str
    file_count: int
    recoverable_bytes: int


@dataclass
class StorageReport:
    """Complete storage analytics report."""
    total_files: int = 0
    total_size: int = 0
    type_breakdown: list[TypeBreakdown] = field(default_factory=list)
    year_breakdown: list[YearBreakdown] = field(default_factory=list)
    duplicate_waste: int = 0
    duplicate_groups: int = 0
    at_risk_files: int = 0
    at_risk_size: int = 0
    quick_wins: list[QuickWin] = field(default_factory=list)
    computed_at: datetime | None = None


def compute_storage_report(db: "Database") -> StorageReport:
    """Compute a full storage analytics report from the database.

    Args:
        db: Database instance

    Returns:
        StorageReport with all breakdowns
    """
    report = StorageReport(computed_at=datetime.now())

    with db.connection() as conn:
        # Total files and size
        row = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total "
            "FROM files WHERE is_deleted = FALSE"
        ).fetchone()
        report.total_files = row["cnt"]
        report.total_size = row["total"]

        # Type breakdown
        type_rows = conn.execute(
            """SELECT COALESCE(file_type, '(none)') as ext,
                      COUNT(*) as cnt,
                      COALESCE(SUM(size), 0) as total
               FROM files WHERE is_deleted = FALSE
               GROUP BY file_type ORDER BY total DESC"""
        ).fetchall()

        for tr in type_rows:
            pct = (tr["total"] / report.total_size * 100) if report.total_size > 0 else 0
            report.type_breakdown.append(TypeBreakdown(
                extension=tr["ext"],
                count=tr["cnt"],
                total_size=tr["total"],
                percentage=round(pct, 1),
            ))

        # Year breakdown (by modified date)
        year_rows = conn.execute(
            """SELECT CAST(strftime('%Y', modified) AS INTEGER) as yr,
                      COUNT(*) as cnt,
                      COALESCE(SUM(size), 0) as total
               FROM files
               WHERE is_deleted = FALSE AND modified IS NOT NULL
               GROUP BY yr ORDER BY yr DESC"""
        ).fetchall()

        for yr in year_rows:
            if yr["yr"] and yr["yr"] > 1980:
                report.year_breakdown.append(YearBreakdown(
                    year=yr["yr"],
                    count=yr["cnt"],
                    total_size=yr["total"],
                ))

        # Duplicate waste
        dup_row = conn.execute(
            """SELECT COUNT(*) as cnt, COALESCE(SUM(wasted_size), 0) as waste
               FROM duplicate_groups WHERE status = 'pending'"""
        ).fetchone()
        report.duplicate_groups = dup_row["cnt"]
        report.duplicate_waste = dup_row["waste"]

        # At-risk files (files with content_hash that exist on only one drive)
        risk_row = conn.execute(
            """SELECT COUNT(*) as cnt, COALESCE(SUM(f.size), 0) as total
               FROM files f
               WHERE f.is_deleted = FALSE
                 AND f.content_hash IS NOT NULL
                 AND f.content_hash IN (
                     SELECT content_hash FROM files
                     WHERE is_deleted = FALSE AND content_hash IS NOT NULL
                     GROUP BY content_hash
                     HAVING COUNT(DISTINCT drive_id) = 1
                 )"""
        ).fetchone()
        report.at_risk_files = risk_row["cnt"]
        report.at_risk_size = risk_row["total"]

        # Quick wins
        # 1. Exact duplicates
        if report.duplicate_waste > 0:
            report.quick_wins.append(QuickWin(
                category="Exact Duplicates",
                description="Identical files that can be safely deduplicated",
                file_count=report.duplicate_groups,
                recoverable_bytes=report.duplicate_waste,
            ))

        # 2. Temp/cache files
        temp_row = conn.execute(
            """SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total
               FROM files
               WHERE is_deleted = FALSE
                 AND (file_type IN ('.tmp', '.temp', '.bak', '.cache', '.log')
                      OR filename IN ('Thumbs.db', 'desktop.ini', '.DS_Store'))"""
        ).fetchone()
        if temp_row["cnt"] > 0:
            report.quick_wins.append(QuickWin(
                category="Temporary Files",
                description="Cache files, temp files, and system metadata",
                file_count=temp_row["cnt"],
                recoverable_bytes=temp_row["total"],
            ))

        # 3. Very large files (>1GB)
        large_row = conn.execute(
            """SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total
               FROM files
               WHERE is_deleted = FALSE AND size > 1073741824"""
        ).fetchone()
        if large_row["cnt"] > 0:
            report.quick_wins.append(QuickWin(
                category="Very Large Files",
                description="Files larger than 1 GB that may warrant review",
                file_count=large_row["cnt"],
                recoverable_bytes=large_row["total"],
            ))

    logger.info(
        "Storage report computed: %d files, %d type categories, %d year ranges",
        report.total_files, len(report.type_breakdown), len(report.year_breakdown),
    )
    return report
