from __future__ import annotations

from pathlib import Path

from duplicleaner.core.organizer import ConflictResolution, Organizer, OrganizeSettings


def test_execute_copy_preserves_source(fs_tree, tmp_path: Path, test_db) -> None:
    source = fs_tree.root / "images"
    dest = tmp_path / "dest"

    settings = OrganizeSettings(move_files=False, dry_run=False)
    organizer = Organizer(db=test_db, settings=settings)
    preview = organizer.preview(str(source), str(dest))
    results = organizer.execute(str(source), str(dest), preview=preview)

    assert results
    assert all(Path(r.dest_path).exists() for r in results if r.success)
    assert all(Path(r.source_path).exists() for r in results if r.success)


def test_execute_conflict_add_sequence(fs_tree, tmp_path: Path, test_db) -> None:
    source = fs_tree.root / "images"
    dest = tmp_path / "dest"

    settings = OrganizeSettings(move_files=False, dry_run=False,
                               conflict_resolution=ConflictResolution.ADD_SEQUENCE)
    organizer = Organizer(db=test_db, settings=settings)
    preview = organizer.preview(str(source), str(dest))

    # Create a conflicting destination file for the first change
    first = preview.changes[0]
    conflict_path = Path(first.dest_path)
    conflict_path.parent.mkdir(parents=True, exist_ok=True)
    conflict_path.write_text("conflict", encoding="utf-8")

    results = organizer.execute(str(source), str(dest), preview=preview)

    # At least one file should be sequenced (e.g., _002)
    assert any("_002" in Path(r.dest_path).stem for r in results if r.success)
