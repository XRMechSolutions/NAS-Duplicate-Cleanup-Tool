from __future__ import annotations

import pytest

from duplicleaner.core.comparator import IMAGEHASH_AVAILABLE, Comparator
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


# === Video Near-Duplicate Tests ===


@pytest.mark.requires_imagehash
@pytest.mark.skipif(not IMAGEHASH_AVAILABLE, reason="imagehash not available")
class TestVideoFrameComparison:
    """Tests for video near-duplicate detection logic."""

    def test_identical_frame_hashes_score_1(self, test_db) -> None:
        """Two videos with identical frame hashes should score 1.0."""
        comparator = Comparator(db=test_db)

        frames = [
            {"frame_index": 0, "timestamp_sec": 0.0, "phash": "f0f0f0f0f0f0f0f0", "dhash": "a0a0a0a0a0a0a0a0"},
            {"frame_index": 1, "timestamp_sec": 1.0, "phash": "0f0f0f0f0f0f0f0f", "dhash": "b0b0b0b0b0b0b0b0"},
        ]

        score = comparator.compare_video_frame_hashes(frames, frames)
        assert score == pytest.approx(1.0)

    def test_completely_different_frame_hashes_score_low(self, test_db) -> None:
        """Two videos with very different frames should have low similarity."""
        comparator = Comparator(db=test_db)

        frames_a = [
            {"frame_index": 0, "timestamp_sec": 0.0, "phash": "0000000000000000", "dhash": "0000000000000000"},
        ]
        frames_b = [
            {"frame_index": 0, "timestamp_sec": 0.0, "phash": "ffffffffffffffff", "dhash": "ffffffffffffffff"},
        ]

        score = comparator.compare_video_frame_hashes(frames_a, frames_b)
        assert score < 0.5

    def test_empty_frames_return_zero(self, test_db) -> None:
        """Empty frame lists should return 0.0 similarity."""
        comparator = Comparator(db=test_db)
        assert comparator.compare_video_frame_hashes([], []) == 0.0
        assert comparator.compare_video_frame_hashes(
            [{"frame_index": 0, "timestamp_sec": 0.0, "phash": "f0f0f0f0f0f0f0f0"}],
            [],
        ) == 0.0

    def test_store_and_retrieve_video_frame_hashes(self, test_db, fs_tree, test_drive) -> None:
        """Test storing and retrieving video frame hashes in the database."""
        # Create a fake video record
        import mimetypes
        from datetime import datetime
        from duplicleaner.db.models import FileRecord

        video_path = fs_tree.files["dup1"]  # use any existing file
        record = FileRecord(
            drive_id=test_drive.id,
            path=str(video_path),
            filename="test.mp4",
            size=1000,
            file_type=".mp4",
            mime_type="video/mp4",
            scan_date=datetime.now(),
        )
        file_id = test_db.add_file(record)

        frames = [
            {"frame_index": 0, "timestamp_sec": 0.0, "phash": "aabbccdd11223344", "dhash": "1122334455667788"},
            {"frame_index": 1, "timestamp_sec": 5.0, "phash": "eeff00112233aabb", "dhash": "99aabbccddeeff00"},
        ]

        test_db.store_video_frame_hashes(file_id, frames)
        stored = test_db.get_video_frame_hashes(file_id)

        assert len(stored) == 2
        assert stored[0]["frame_index"] == 0
        assert stored[0]["phash"] == "aabbccdd11223344"
        assert stored[1]["timestamp_sec"] == 5.0

    def test_video_near_duplicate_detection_pipeline(self, test_db, fs_tree, test_drive) -> None:
        """Test the full pipeline: store frame hashes, then find near-duplicate videos."""
        from datetime import datetime
        from duplicleaner.db.models import FileRecord

        video_path_a = fs_tree.files["dup1"]
        video_path_b = fs_tree.files["dup2"]

        # Register two "video" files
        id_a = test_db.add_file(FileRecord(
            drive_id=test_drive.id,
            path=str(video_path_a),
            filename="clip_a.mp4",
            size=5000,
            file_type=".mp4",
            mime_type="video/mp4",
            scan_date=datetime.now(),
        ))
        id_b = test_db.add_file(FileRecord(
            drive_id=test_drive.id,
            path=str(video_path_b),
            filename="clip_b.mp4",
            size=5000,
            file_type=".mp4",
            mime_type="video/mp4",
            scan_date=datetime.now(),
        ))

        # Store identical frame hashes for both (simulating duplicate videos)
        identical_frames = [
            {"frame_index": 0, "timestamp_sec": 0.0, "phash": "f0f0f0f0f0f0f0f0", "dhash": "a0a0a0a0a0a0a0a0"},
            {"frame_index": 1, "timestamp_sec": 2.0, "phash": "0f0f0f0f0f0f0f0f", "dhash": "b0b0b0b0b0b0b0b0"},
        ]
        test_db.store_video_frame_hashes(id_a, identical_frames)
        test_db.store_video_frame_hashes(id_b, identical_frames)

        # The find_video_near_duplicates method will try to extract frames
        # from the actual files (which aren't real videos), but since we've
        # already stored frame hashes, it should find and compare them.
        comparator = Comparator(db=test_db)
        groups = comparator.find_video_near_duplicates(
            drive_id=test_drive.id, threshold=0.7
        )

        assert groups >= 1

    def test_different_video_hashes_no_group(self, test_db, fs_tree, test_drive) -> None:
        """Two videos with very different frames should not form a group."""
        from datetime import datetime
        from duplicleaner.db.models import FileRecord

        id_a = test_db.add_file(FileRecord(
            drive_id=test_drive.id,
            path=str(fs_tree.files["dup1"]),
            filename="unrelated_a.mp4",
            size=5000, file_type=".mp4",
            scan_date=datetime.now(),
        ))
        id_b = test_db.add_file(FileRecord(
            drive_id=test_drive.id,
            path=str(fs_tree.files["dup2"]),
            filename="unrelated_b.mp4",
            size=5000, file_type=".mp4",
            scan_date=datetime.now(),
        ))

        test_db.store_video_frame_hashes(id_a, [
            {"frame_index": 0, "timestamp_sec": 0.0, "phash": "0000000000000000", "dhash": "0000000000000000"},
        ])
        test_db.store_video_frame_hashes(id_b, [
            {"frame_index": 0, "timestamp_sec": 0.0, "phash": "ffffffffffffffff", "dhash": "ffffffffffffffff"},
        ])

        comparator = Comparator(db=test_db)
        groups = comparator.find_video_near_duplicates(
            drive_id=test_drive.id, threshold=0.7
        )
        assert groups == 0
