from __future__ import annotations

from pathlib import Path

from duplicleaner.core.scanner import ScanMode, Scanner


def test_scanner_counts_files(fs_tree, test_db, test_drive) -> None:
    scanner = Scanner(db=test_db, batch_size=2)
    result = scanner.scan(test_drive, mode=ScanMode.QUICK)

    assert result.errors == 0
    assert result.total_files == len(fs_tree.files)


def test_scanner_ignores_known_patterns(tmp_path: Path, test_db) -> None:
    # Build a tree with one ignored file
    from tests.fixtures.fs_builder import build_test_tree
    from duplicleaner.db.models import Drive

    fs_tree = build_test_tree(tmp_path / "dataset")
    ignored = fs_tree.root / "Thumbs.db"
    ignored.write_text("ignore me", encoding="utf-8")

    drive = Drive(id="D2", label="IgnoredDrive", path=str(fs_tree.root))
    test_db.add_drive(drive)

    scanner = Scanner(db=test_db)
    result = scanner.scan(drive, mode=ScanMode.QUICK)

    assert result.total_files == len(fs_tree.files)
    assert result.errors == 0


def test_quick_scan_tracks_unchanged(fs_tree, test_db, test_drive) -> None:
    scanner = Scanner(db=test_db, batch_size=2)
    first = scanner.scan(test_drive, mode=ScanMode.QUICK)

    assert first.total_files == len(fs_tree.files)

    second = scanner.scan(test_drive, mode=ScanMode.QUICK)

    assert second.new_files == 0
    assert second.modified_files == 0
    assert second.total_files == len(fs_tree.files)


def test_scanner_records_permission_error(tmp_path: Path, test_db, monkeypatch) -> None:
    from duplicleaner.db.models import Drive

    root = tmp_path / "perm_root"
    root.mkdir(parents=True, exist_ok=True)

    drive = Drive(id="D3", label="PermDrive", path=str(root))
    test_db.add_drive(drive)

    scanner = Scanner(db=test_db)

    def fail_scan(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(scanner, "_scan_directory", fail_scan)

    result = scanner.scan(drive, mode=ScanMode.QUICK)

    assert result.errors >= 1
    assert scanner.progress.permission_errors >= 1

def test_scanner_long_path_does_not_crash(tmp_path: Path, test_db) -> None:
    from tests.fixtures.fs_builder import build_test_tree
    from duplicleaner.db.models import Drive

    fs_tree = build_test_tree(tmp_path / "dataset", include_long_paths=True)
    drive = Drive(id="D4", label="LongPath", path=str(fs_tree.root))
    test_db.add_drive(drive)

    scanner = Scanner(db=test_db)
    result = scanner.scan(drive, mode=ScanMode.QUICK)

    assert result.total_files >= len(fs_tree.files)


def test_scanner_records_path_too_long(tmp_path: Path, test_db, monkeypatch) -> None:
    from duplicleaner.db.models import Drive
    import os

    root = tmp_path / "long_root"
    root.mkdir(parents=True, exist_ok=True)
    drive = Drive(id="D5", label="LongErr", path=str(root))
    test_db.add_drive(drive)

    scanner = Scanner(db=test_db)

    def fail_scandir(*args, **kwargs):
        raise OSError("name is too long")

    monkeypatch.setattr(os, "scandir", fail_scandir)

    # Call _scan_directory directly to exercise its error handling.
    list(scanner._scan_directory(str(root), str(root), drive, ScanMode.QUICK))

    assert scanner.progress.errors >= 1
    assert scanner.progress.other_errors >= 1
