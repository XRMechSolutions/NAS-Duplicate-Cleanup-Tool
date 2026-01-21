from __future__ import annotations


def test_db_schema_tables_present(test_db) -> None:
    expected = {
        "schema_version",
        "settings",
        "drives",
        "files",
        "file_metadata",
        "thumbnails",
        "duplicate_groups",
        "duplicate_members",
        "persons",
        "faces",
        "scene_analysis",
        "ocr_results",
        "ai_summaries",
        "tags",
        "file_tags",
        "pets",
        "pet_detections",
        "action_log",
        "ai_summaries_fts",
        "ocr_fts",
    }

    with test_db.connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
        ).fetchall()
        names = {row["name"] for row in rows}

    assert expected.issubset(names)
