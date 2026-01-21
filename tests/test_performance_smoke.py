from __future__ import annotations

import pytest
import time

from duplicleaner.core.scanner import ScanMode, Scanner
from duplicleaner.db.models import Drive
from tests.fixtures.fs_builder import build_test_tree


@pytest.mark.slow
def test_scan_large_tree_smoke(tmp_path, test_db) -> None:
    fs_tree = build_test_tree(tmp_path / "dataset", extra_files=5000)
    drive = Drive(id="D_PERF", label="PerfDrive", path=str(fs_tree.root))
    test_db.add_drive(drive)

    scanner = Scanner(db=test_db, batch_size=500)
    start = time.perf_counter()
    result = scanner.scan(drive, mode=ScanMode.QUICK)
    elapsed = time.perf_counter() - start

    assert result.total_files >= len(fs_tree.files) + 5000
    assert elapsed < 30.0
