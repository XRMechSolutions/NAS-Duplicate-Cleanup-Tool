from __future__ import annotations

from pathlib import Path

import pytest

from duplicleaner.core.actions import ActionEngine, ActionStatus
from duplicleaner.core.comparator import Comparator
from duplicleaner.core.hasher import Hasher
from duplicleaner.core.resolver import ResolutionStrategy, Resolver
from duplicleaner.core.scanner import ScanMode, Scanner
from duplicleaner.db.models import GroupStatus


@pytest.mark.integration
def test_scan_hash_compare_pipeline(fs_tree, test_db, test_drive, tmp_path: Path) -> None:
    scanner = Scanner(db=test_db, batch_size=3)
    scan_result = scanner.scan(test_drive, mode=ScanMode.QUICK)

    assert scan_result.errors == 0
    assert scan_result.total_files == len(fs_tree.files)

    hasher = Hasher(db=test_db)
    hash_result = hasher.hash_files(drive_id=test_drive.id)
    assert hash_result.errors == 0

    comparator = Comparator(db=test_db)
    groups = comparator.find_exact_duplicates(drive_id=test_drive.id)
    assert groups >= 1

    for key in ("dup1", "dup2", "dup3"):
        record = test_db.get_file_by_path(test_drive.id, str(fs_tree.files[key]))
        assert record is not None
        assert record.content_hash

    # Resolve one group and execute a quarantine action for a non-keeper
    resolver = Resolver(db=test_db)
    pending_groups = test_db.get_duplicate_groups(status=GroupStatus.PENDING, limit=1)
    assert pending_groups
    resolution = resolver.resolve_group(pending_groups[0].id, ResolutionStrategy.KEEP_LARGEST)
    assert resolution is not None
    assert resolver.apply_resolution(resolution)

    quarantine_dir = tmp_path / "quarantine"
    engine = ActionEngine(db=test_db, quarantine_folder=str(quarantine_dir))

    remove_path = resolution.remove_paths[0]
    result = engine.quarantine(remove_path)
    assert result.status == ActionStatus.SUCCESS
    assert result.log_entry_id is not None

    removed_file = test_db.get_file_by_path_any(remove_path)
    assert removed_file is not None
    test_db.mark_file_deleted(removed_file.id)
    removed_file = test_db.get_file(removed_file.id)
    assert removed_file is not None
    assert removed_file.is_deleted
