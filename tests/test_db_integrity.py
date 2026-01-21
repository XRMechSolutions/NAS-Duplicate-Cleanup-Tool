from __future__ import annotations

from duplicleaner.db.models import MatchType

from tests.conftest import make_file_record


def test_resolve_duplicate_group_sets_keeper(tmp_path, test_db, test_drive) -> None:
    p1 = tmp_path / "a.bin"
    p2 = tmp_path / "b.bin"
    p1.write_text("same", encoding="utf-8")
    p2.write_text("same", encoding="utf-8")

    id1 = test_db.add_file(make_file_record(p1, test_drive.id))
    id2 = test_db.add_file(make_file_record(p2, test_drive.id))

    group_id = test_db.create_duplicate_group(
        match_type=MatchType.EXACT,
        similarity=1.0,
        file_ids=[id1, id2],
        keeper_id=id1,
    )

    test_db.resolve_duplicate_group(group_id, id2)

    with test_db.connection() as conn:
        rows = conn.execute(
            "SELECT file_id, is_keeper FROM duplicate_members WHERE group_id = ?",
            (group_id,),
        ).fetchall()

    keepers = [r["file_id"] for r in rows if r["is_keeper"]]
    assert keepers == [id2]
