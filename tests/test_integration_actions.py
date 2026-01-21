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
