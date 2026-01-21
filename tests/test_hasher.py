from __future__ import annotations

from duplicleaner.core.hasher import Hasher, verify_file_hash
from tests.conftest import make_file_record


def test_quick_hash_matches_for_duplicates(fs_tree) -> None:
    hasher = Hasher()
    dup1 = fs_tree.files["dup1"]
    dup2 = fs_tree.files["dup2"]

    h1 = hasher.compute_quick_hash(str(dup1))
    h2 = hasher.compute_quick_hash(str(dup2))

    assert h1 is not None
    assert h1 == h2


def test_full_hash_matches_for_duplicates(fs_tree) -> None:
    hasher = Hasher()
    dup1 = fs_tree.files["dup1"]
    dup2 = fs_tree.files["dup2"]

    h1 = hasher.compute_full_hash(str(dup1))
    h2 = hasher.compute_full_hash(str(dup2))

    assert h1 is not None
    assert h1 == h2


def test_hash_single_file(fs_tree) -> None:
    hasher = Hasher()
    path = fs_tree.files["same_name_a"]
    quick_hash, full_hash = hasher.hash_single_file(str(path))

    assert quick_hash is not None
    assert full_hash is not None


def test_hash_files_updates_db(fs_tree, test_db, test_drive) -> None:
    # Add only the exact duplicates so they are grouped by size.
    for key in ("dup1", "dup2", "dup3"):
        record = make_file_record(fs_tree.files[key], test_drive.id)
        test_db.add_file(record)

    hasher = Hasher(db=test_db)
    result = hasher.hash_files(drive_id=test_drive.id)

    assert result.errors == 0
    assert result.duplicate_candidates == 3
    assert result.exact_duplicates == 2

    for key in ("dup1", "dup2", "dup3"):
        record = test_db.get_file_by_path(test_drive.id, str(fs_tree.files[key]))
        assert record is not None
        assert record.quick_hash
        assert record.content_hash


def test_verify_file_hash(fs_tree) -> None:
    path = fs_tree.files["same_name_a"]
    hasher = Hasher()
    expected = hasher.compute_full_hash(str(path))

    assert expected is not None
    assert verify_file_hash(str(path), expected, algorithm="sha256") is True


def test_full_hash_cancels_returns_none(fs_tree) -> None:
    hasher = Hasher()
    hasher.cancel()
    result = hasher.compute_full_hash(str(fs_tree.files["dup1"]))
    assert result is None
