from __future__ import annotations

from pathlib import Path

from duplicleaner.core.actions import ActionEngine, ActionStatus, PendingAction
from duplicleaner.db.models import ActionType


def test_quarantine_moves_file_and_logs(tmp_path: Path, test_db) -> None:
    source = tmp_path / "src.txt"
    source.write_text("data", encoding="utf-8")
    quarantine = tmp_path / "quarantine"

    engine = ActionEngine(db=test_db, quarantine_folder=str(quarantine), dry_run=False)
    result = engine.quarantine(str(source))

    assert result.status == ActionStatus.SUCCESS
    assert result.log_entry_id is not None
    assert not source.exists()
    assert result.action.dest_path is not None
    assert Path(result.action.dest_path).exists()


def test_delete_requires_confirm(tmp_path: Path, test_db) -> None:
    source = tmp_path / "delete.txt"
    source.write_text("data", encoding="utf-8")

    engine = ActionEngine(db=test_db)
    result = engine.delete_permanently(str(source), confirm=False)

    assert result.status == ActionStatus.FAILED
    assert source.exists()


def test_copy_file_no_overwrite(tmp_path: Path, test_db) -> None:
    source = tmp_path / "src.txt"
    dest = tmp_path / "dest.txt"
    source.write_text("data", encoding="utf-8")
    dest.write_text("existing", encoding="utf-8")

    engine = ActionEngine(db=test_db)
    result = engine.copy_file(str(source), str(dest), overwrite=False)

    assert result.status == ActionStatus.FAILED


def test_move_file_moves_and_logs(tmp_path: Path, test_db) -> None:
    source = tmp_path / "move.txt"
    dest = tmp_path / "moved.txt"
    source.write_text("data", encoding="utf-8")

    engine = ActionEngine(db=test_db)
    result = engine.move_file(str(source), str(dest))

    assert result.status == ActionStatus.SUCCESS
    assert result.log_entry_id is not None
    assert dest.exists()
    assert not source.exists()


def test_execute_pending_requires_confirm_delete(tmp_path: Path, test_db) -> None:
    source = tmp_path / "delete_pending.txt"
    source.write_text("data", encoding="utf-8")

    engine = ActionEngine(db=test_db)
    engine.add_pending(PendingAction(ActionType.DELETE, str(source)))

    results = engine.execute_pending(confirm_delete=False)
    assert results == []
    assert source.exists()


def test_protected_path_detection(test_db) -> None:
    engine = ActionEngine(db=test_db)
    assert engine._is_protected_path("C:\\Windows\\System32\\kernel32.dll") is True
    assert engine._is_protected_path("C:\\Somewhere\\safe.txt") is False


def test_move_file_failure_reports_error(tmp_path: Path, test_db, monkeypatch) -> None:
    source = tmp_path / "move_fail.txt"
    dest = tmp_path / "dest.txt"
    source.write_text("data", encoding="utf-8")

    engine = ActionEngine(db=test_db)

    def fail_move(*args, **kwargs):
        raise OSError("move failed")

    monkeypatch.setattr("duplicleaner.core.actions.shutil.move", fail_move)

    result = engine.move_file(str(source), str(dest))

    assert result.status == ActionStatus.FAILED
    assert "move failed" in (result.error_message or "")


def test_execute_pending_cancel(tmp_path: Path, test_db, monkeypatch) -> None:
    source1 = tmp_path / "cancel1.txt"
    source2 = tmp_path / "cancel2.txt"
    dest1 = tmp_path / "dest1.txt"
    dest2 = tmp_path / "dest2.txt"
    source1.write_text("data1", encoding="utf-8")
    source2.write_text("data2", encoding="utf-8")

    engine = ActionEngine(db=test_db)
    engine.add_pending(PendingAction(ActionType.COPY, str(source1), str(dest1)))
    engine.add_pending(PendingAction(ActionType.COPY, str(source2), str(dest2)))

    call_count = {"n": 0}

    def wrapped_execute(action, confirm_delete):
        call_count["n"] += 1
        if call_count["n"] == 1:
            engine.cancel()
        return ActionEngine._execute_single(engine, action, confirm_delete)

    monkeypatch.setattr(engine, "_execute_single", wrapped_execute)

    results = engine.execute_pending(confirm_delete=False)

    assert any(r.status == ActionStatus.CANCELLED for r in results)
    assert engine.progress.is_cancelled is True
