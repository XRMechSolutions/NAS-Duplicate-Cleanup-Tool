from __future__ import annotations

import pytest

from duplicleaner.core.comparator import Comparator
from duplicleaner.core.hasher import Hasher
from duplicleaner.core.scanner import ScanMode, Scanner


@pytest.mark.integration
def test_scan_hash_compare_pipeline(fs_tree, test_db, test_drive) -> None:
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
