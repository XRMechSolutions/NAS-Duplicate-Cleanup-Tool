from __future__ import annotations

import pytest

from duplicleaner.core.comparator import Comparator, IMAGEHASH_AVAILABLE
from duplicleaner.core.hasher import Hasher
from tests.conftest import make_file_record


def test_find_exact_duplicates_creates_group(fs_tree, test_db, test_drive) -> None:
    # Create two files with matching content hashes
    hasher = Hasher()
    dup1 = fs_tree.files["dup1"]
    dup2 = fs_tree.files["dup2"]

    hash1 = hasher.compute_full_hash(str(dup1))
    assert hash1 is not None

    for path in (dup1, dup2):
        record = make_file_record(path, test_drive.id, content_hash=hash1)
        test_db.add_file(record)

    comparator = Comparator(db=test_db)
    groups = comparator.find_exact_duplicates(drive_id=test_drive.id)

    assert groups == 1

    stats = test_db.get_statistics()
    assert stats["pending_duplicate_groups"] == 1

    with test_db.connection() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM duplicate_members").fetchone()
        assert row["cnt"] == 2


@pytest.mark.requires_imagehash
@pytest.mark.skipif(not IMAGEHASH_AVAILABLE, reason="imagehash not available")
def test_find_near_duplicates_groups_similar_images(fs_tree, test_db, test_drive) -> None:
    base = fs_tree.files["base_img"]
    near = fs_tree.files["near_img"]

    for path in (base, near):
        record = make_file_record(path, test_drive.id)
        test_db.add_file(record)

    comparator = Comparator(db=test_db)
    groups = comparator.find_near_duplicates(drive_id=test_drive.id, threshold=0.9)

    assert groups >= 1

    stats = test_db.get_statistics()
    assert stats["pending_duplicate_groups"] >= 1
