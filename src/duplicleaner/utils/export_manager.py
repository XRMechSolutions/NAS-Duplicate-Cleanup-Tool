"""Export utilities for DupliCleaner.

Shared export logic for CSV, JSON, and HTML output across all panels.
"""

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


def get_default_export_dir() -> Path:
    """Get the default export directory (Desktop)."""
    return Path.home() / "Desktop"


def get_timestamped_filename(prefix: str, extension: str) -> str:
    """Generate a timestamped filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"duplicleaner_{prefix}_{timestamp}.{extension}"


def export_csv(
    rows: list[dict[str, Any]],
    filepath: Path,
    columns: list[str] | None = None,
) -> int:
    """Export data to CSV.

    Args:
        rows: List of dicts to export
        filepath: Output file path
        columns: Column names (keys) to include. If None, uses all keys from first row.

    Returns:
        Number of rows written
    """
    if not rows:
        filepath.write_text("No data to export.\n", encoding="utf-8")
        return 0

    if columns is None:
        columns = list(rows[0].keys())

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    logger.info("Exported %d rows to CSV: %s", len(rows), filepath)
    return len(rows)


def export_json(
    data: Any,
    filepath: Path,
    indent: int = 2,
) -> None:
    """Export data to JSON.

    Args:
        data: Data to serialize (must be JSON-serializable)
        filepath: Output file path
        indent: JSON indentation level
    """
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, default=str, ensure_ascii=False)

    logger.info("Exported JSON to: %s", filepath)


def export_html(
    title: str,
    sections: list[dict[str, Any]],
    filepath: Path,
    summary_stats: dict[str, Any] | None = None,
) -> None:
    """Export data as styled HTML report.

    Args:
        title: Report title
        sections: List of dicts with keys: 'heading', 'columns', 'rows'
        filepath: Output file path
        summary_stats: Optional key-value stats to show at top
    """
    buf = io.StringIO()
    buf.write("<!DOCTYPE html>\n<html><head>\n")
    buf.write(f"<title>{title}</title>\n")
    buf.write("<style>\n")
    buf.write("body { font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #1a1a2e; color: #e0e0e0; }\n")
    buf.write("h1 { color: #4fc3f7; border-bottom: 2px solid #4fc3f7; padding-bottom: 8px; }\n")
    buf.write("h2 { color: #81c784; margin-top: 30px; }\n")
    buf.write("table { border-collapse: collapse; width: 100%; margin: 10px 0; }\n")
    buf.write("th { background: #2a2a4a; color: #4fc3f7; padding: 8px 12px; text-align: left; border: 1px solid #3a3a5a; }\n")
    buf.write("td { padding: 6px 12px; border: 1px solid #3a3a5a; }\n")
    buf.write("tr:nth-child(even) { background: #1e1e3a; }\n")
    buf.write("tr:hover { background: #2a2a4a; }\n")
    buf.write(".stats { display: flex; gap: 20px; flex-wrap: wrap; margin: 15px 0; }\n")
    buf.write(".stat-card { background: #2a2a4a; padding: 12px 20px; border-radius: 6px; border-left: 3px solid #4fc3f7; }\n")
    buf.write(".stat-value { font-size: 1.4em; font-weight: bold; color: #4fc3f7; }\n")
    buf.write(".stat-label { font-size: 0.85em; color: #aaa; }\n")
    buf.write(".footer { margin-top: 40px; padding-top: 10px; border-top: 1px solid #3a3a5a; color: #666; font-size: 0.8em; }\n")
    buf.write("</style>\n</head>\n<body>\n")

    buf.write(f"<h1>{title}</h1>\n")
    buf.write(f"<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>\n")

    if summary_stats:
        buf.write('<div class="stats">\n')
        for label, value in summary_stats.items():
            buf.write(f'<div class="stat-card"><div class="stat-value">{value}</div>')
            buf.write(f'<div class="stat-label">{label}</div></div>\n')
        buf.write("</div>\n")

    for section in sections:
        heading = section.get("heading", "")
        columns = section.get("columns", [])
        rows = section.get("rows", [])

        if heading:
            buf.write(f"<h2>{heading}</h2>\n")

        if columns and rows:
            buf.write("<table>\n<thead><tr>\n")
            for col in columns:
                buf.write(f"<th>{col}</th>\n")
            buf.write("</tr></thead>\n<tbody>\n")

            for row in rows:
                buf.write("<tr>\n")
                for col in columns:
                    val = row.get(col, "")
                    buf.write(f"<td>{val}</td>\n")
                buf.write("</tr>\n")

            buf.write("</tbody></table>\n")
        elif not rows:
            buf.write("<p>No data available.</p>\n")

    buf.write('<div class="footer">DupliCleaner Report</div>\n')
    buf.write("</body></html>\n")

    filepath.write_text(buf.getvalue(), encoding="utf-8")
    logger.info("Exported HTML report to: %s", filepath)


def generate_unified_report(
    db: "Database",
    filepath: Path,
    include_storage: bool = True,
    include_duplicates: bool = True,
    include_persons: bool = True,
    include_actions: bool = True,
) -> str:
    """Generate a unified HTML report combining data from all panels.

    Args:
        db: Database instance
        filepath: Output file path
        include_storage: Include storage overview section
        include_duplicates: Include duplicate summary section
        include_persons: Include face/person summary section
        include_actions: Include action history section

    Returns:
        Path to the generated report
    """
    from duplicleaner.db.models import GroupStatus, MatchType

    sections = []
    summary_stats: dict[str, Any] = {}

    # Storage overview
    if include_storage:
        try:
            with db.connection() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total FROM files WHERE is_deleted = FALSE"
                ).fetchone()
                file_count = row["cnt"]
                total_size = row["total"]

                type_rows = conn.execute(
                    """SELECT file_type, COUNT(*) as cnt, COALESCE(SUM(size), 0) as total
                       FROM files WHERE is_deleted = FALSE AND file_type IS NOT NULL
                       GROUP BY file_type ORDER BY total DESC LIMIT 20"""
                ).fetchall()

            summary_stats["Total Files"] = f"{file_count:,}"
            summary_stats["Total Size"] = format_size(total_size)

            if type_rows:
                type_data = []
                for tr in type_rows:
                    type_data.append({
                        "Extension": tr["file_type"],
                        "Count": f"{tr['cnt']:,}",
                        "Size": format_size(tr["total"]),
                    })
                sections.append({
                    "heading": "Storage by File Type",
                    "columns": ["Extension", "Count", "Size"],
                    "rows": type_data,
                })
        except Exception as exc:
            logger.warning("Failed to gather storage data: %s", exc)

    # Duplicates summary
    if include_duplicates:
        try:
            with db.connection() as conn:
                pending = conn.execute(
                    "SELECT COUNT(*) as cnt, COALESCE(SUM(wasted_size), 0) as waste FROM duplicate_groups WHERE status = 'pending'"
                ).fetchone()
                resolved = conn.execute(
                    "SELECT COUNT(*) as cnt FROM duplicate_groups WHERE status = 'resolved'"
                ).fetchone()
                exact = conn.execute(
                    "SELECT COUNT(*) as cnt FROM duplicate_groups WHERE match_type = 'exact'"
                ).fetchone()
                near = conn.execute(
                    "SELECT COUNT(*) as cnt FROM duplicate_groups WHERE match_type = 'near'"
                ).fetchone()

            summary_stats["Pending Groups"] = f"{pending['cnt']:,}"
            summary_stats["Recoverable Space"] = format_size(pending["waste"])

            dup_rows = [
                {"Category": "Exact match groups", "Count": f"{exact['cnt']:,}"},
                {"Category": "Near-duplicate groups", "Count": f"{near['cnt']:,}"},
                {"Category": "Pending groups", "Count": f"{pending['cnt']:,}"},
                {"Category": "Resolved groups", "Count": f"{resolved['cnt']:,}"},
                {"Category": "Recoverable space", "Count": format_size(pending["waste"])},
            ]
            sections.append({
                "heading": "Duplicate Analysis",
                "columns": ["Category", "Count"],
                "rows": dup_rows,
            })

            # Top 20 largest duplicate groups
            top_groups = db.get_duplicate_groups(status=GroupStatus.PENDING, limit=20)
            if top_groups:
                top_rows = []
                for g in top_groups:
                    top_rows.append({
                        "Group": g.id,
                        "Type": g.match_type.value,
                        "Files": g.file_count,
                        "Wasted": format_size(g.wasted_size),
                        "Status": g.status.value,
                    })
                sections.append({
                    "heading": "Top 20 Largest Duplicate Groups",
                    "columns": ["Group", "Type", "Files", "Wasted", "Status"],
                    "rows": top_rows,
                })
        except Exception as exc:
            logger.warning("Failed to gather duplicate data: %s", exc)

    # Persons / faces
    if include_persons:
        try:
            persons = db.get_all_persons(include_hidden=False)
            named = [p for p in persons if p.name]
            unnamed = [p for p in persons if not p.name]

            summary_stats["Named Persons"] = f"{len(named):,}"
            summary_stats["Total Faces"] = f"{len(persons):,}"

            if named:
                person_rows = []
                for p in sorted(named, key=lambda x: x.photo_count, reverse=True)[:50]:
                    person_rows.append({
                        "Name": p.name,
                        "Photos": f"{p.photo_count:,}",
                        "Source": p.identification_source,
                        "Notes": p.notes or "",
                    })
                sections.append({
                    "heading": "Named Persons",
                    "columns": ["Name", "Photos", "Source", "Notes"],
                    "rows": person_rows,
                })
        except Exception as exc:
            logger.warning("Failed to gather person data: %s", exc)

    # Action history
    if include_actions:
        try:
            entries = db.get_action_log(limit=100)
            if entries:
                action_rows = []
                for e in entries:
                    action_rows.append({
                        "Date": str(e.timestamp)[:19] if e.timestamp else "",
                        "Action": e.action_type.value if e.action_type else "",
                        "Source": e.source_path,
                        "Size": format_size(e.file_size),
                        "Reversible": "Yes" if e.reversible else "No",
                        "Reversed": "Yes" if e.reversed else "",
                    })
                sections.append({
                    "heading": f"Recent Actions ({len(entries)})",
                    "columns": ["Date", "Action", "Source", "Size", "Reversible", "Reversed"],
                    "rows": action_rows,
                })
        except Exception as exc:
            logger.warning("Failed to gather action data: %s", exc)

    export_html(
        "DupliCleaner - Summary Report",
        sections,
        filepath,
        summary_stats=summary_stats,
    )

    return str(filepath)


def format_size(size_bytes: int | None) -> str:
    """Format bytes as human-readable size."""
    if size_bytes is None:
        return "N/A"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
