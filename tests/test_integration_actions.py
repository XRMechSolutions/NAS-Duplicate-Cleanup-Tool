from __future__ import annotations

from pathlib import Path

import pytest

from duplicleaner.core.actions import ActionEngine, ActionStatus


@pytest.mark.integration
def test_quarantine_and_undo(tmp_path: Path, test_db) -> None:
    source = tmp_path / "undo.txt"
    source.write_text("data", encoding="utf-8")
    quarantine = tmp_path / "quarantine"

    engine = ActionEngine(db=test_db, quarantine_folder=str(quarantine))
    result = engine.quarantine(str(source))

    assert result.status == ActionStatus.SUCCESS
    assert result.log_entry_id is not None
    assert not source.exists()

    undo = engine.undo_action(result.log_entry_id)
    assert undo.status == ActionStatus.SUCCESS
    assert source.exists()


@pytest.mark.integration
def test_move_and_undo(tmp_path: Path, test_db) -> None:
    """Test that undo reverses a move operation."""
    source = tmp_path / "original.txt"
    source.write_text("move me", encoding="utf-8")
    dest = tmp_path / "dest" / "moved.txt"

    engine = ActionEngine(db=test_db, quarantine_folder=str(tmp_path / "q"))
    result = engine.move_file(str(source), str(dest))

    assert result.status == ActionStatus.SUCCESS
    assert result.log_entry_id is not None
    assert not source.exists()
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "move me"

    undo = engine.undo_action(result.log_entry_id)
    assert undo.status == ActionStatus.SUCCESS
    assert source.exists()
    assert not dest.exists()
    assert source.read_text(encoding="utf-8") == "move me"


@pytest.mark.integration
def test_undo_already_undone(tmp_path: Path, test_db) -> None:
    """Test that undoing the same action twice fails gracefully."""
    source = tmp_path / "once.txt"
    source.write_text("once", encoding="utf-8")
    quarantine = tmp_path / "quarantine"

    engine = ActionEngine(db=test_db, quarantine_folder=str(quarantine))
    result = engine.quarantine(str(source))
    assert result.status == ActionStatus.SUCCESS

    undo1 = engine.undo_action(result.log_entry_id)
    assert undo1.status == ActionStatus.SUCCESS

    undo2 = engine.undo_action(result.log_entry_id)
    assert undo2.status == ActionStatus.FAILED
    assert "already been undone" in undo2.error_message


@pytest.mark.integration
def test_undo_nonexistent_entry(tmp_path: Path, test_db) -> None:
    """Test undo with an invalid log entry ID."""
    engine = ActionEngine(db=test_db, quarantine_folder=str(tmp_path / "q"))
    result = engine.undo_action(99999)
    assert result.status == ActionStatus.FAILED
    assert "not found" in result.error_message


@pytest.mark.integration
def test_delete_not_reversible(tmp_path: Path, test_db) -> None:
    """Test that permanent deletes are logged as non-reversible."""
    source = tmp_path / "delete_me.txt"
    source.write_text("gone", encoding="utf-8")

    engine = ActionEngine(db=test_db, quarantine_folder=str(tmp_path / "q"))
    result = engine.delete_permanently(str(source), confirm=True)
    assert result.status == ActionStatus.SUCCESS
    assert not source.exists()

    undo = engine.undo_action(result.log_entry_id)
    assert undo.status == ActionStatus.FAILED
    assert "not reversible" in undo.error_message


@pytest.mark.integration
def test_multi_step_undo_batch(tmp_path: Path, test_db) -> None:
    """Test undoing multiple actions in a batch."""
    quarantine = tmp_path / "quarantine"
    engine = ActionEngine(db=test_db, quarantine_folder=str(quarantine))

    files = []
    log_ids = []
    for i in range(3):
        f = tmp_path / f"batch_{i}.txt"
        f.write_text(f"data {i}", encoding="utf-8")
        files.append(f)

        result = engine.quarantine(str(f))
        assert result.status == ActionStatus.SUCCESS
        log_ids.append(result.log_entry_id)

    # All files should be gone
    for f in files:
        assert not f.exists()

    # Undo all in batch
    results = engine.undo_batch(log_ids)
    assert all(r.status == ActionStatus.SUCCESS for r in results)

    # All files should be restored
    for i, f in enumerate(files):
        assert f.exists()
        assert f.read_text(encoding="utf-8") == f"data {i}"


@pytest.mark.integration
def test_copy_and_undo(tmp_path: Path, test_db) -> None:
    """Test that undo removes a copied file."""
    source = tmp_path / "original.txt"
    source.write_text("copy me", encoding="utf-8")
    dest = tmp_path / "copied.txt"

    engine = ActionEngine(db=test_db, quarantine_folder=str(tmp_path / "q"))
    result = engine.copy_file(str(source), str(dest))

    assert result.status == ActionStatus.SUCCESS
    assert source.exists()
    assert dest.exists()

    undo = engine.undo_action(result.log_entry_id)
    assert undo.status == ActionStatus.SUCCESS
    assert source.exists()  # Original still there
    assert not dest.exists()  # Copy removed
