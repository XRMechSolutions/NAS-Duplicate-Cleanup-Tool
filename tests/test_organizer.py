from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from duplicleaner.core.organizer import (
    BurstHandling,
    DateFormat,
    LivePhotoHandling,
    OrganizeSettings,
    Organizer,
)


def test_extract_date_prefers_exif(fs_tree) -> None:
    organizer = Organizer()
    date, source = organizer.extract_date(str(fs_tree.files["base_img"]))

    assert source == "exif"
    assert date == datetime(2022, 8, 9, 10, 11, 12)


def test_extract_date_falls_back_to_file(fs_tree) -> None:
    organizer = Organizer()
    date, source = organizer.extract_date(str(fs_tree.files["no_exif"]))

    assert source == "file"
    assert date is not None


def test_generate_folder_path_and_filename() -> None:
    settings = OrganizeSettings(date_format=DateFormat.YYYY_MM_MONTH)
    organizer = Organizer(settings=settings)
    date = datetime(2024, 1, 15, 14, 30, 22)

    folder = organizer.generate_folder_path(date)
    assert folder == "2024/01-January"

    organizer.settings.rename_pattern = "{date}_{location}_{seq}"
    name = organizer.generate_filename("photo.jpg", date, location=None, sequence=1)
    assert name == "2024-01-15_001.jpg"


def test_preview_builds_changes(fs_tree, tmp_path: Path) -> None:
    organizer = Organizer()
    source = fs_tree.root / "images"
    dest = tmp_path / "dest"

    preview = organizer.preview(str(source), str(dest))

    assert preview.total_files == 4
    assert preview.files_to_move == 4
    assert preview.files_to_rename > 0
    assert preview.folders_to_create >= 1


def test_detect_bursts() -> None:
    organizer = Organizer()
    base = datetime(2024, 1, 1, 10, 0, 0)
    files = [
        ("a.jpg", base),
        ("b.jpg", base + timedelta(seconds=1)),
        ("c.jpg", base + timedelta(seconds=2)),
        ("d.jpg", base + timedelta(seconds=10)),
    ]

    bursts = organizer.detect_bursts(files)

    assert len(bursts) == 1
    assert bursts[0] == ["a.jpg", "b.jpg", "c.jpg"]


def test_detect_events() -> None:
    organizer = Organizer()
    base = datetime(2024, 1, 1, 10, 0, 0)
    files = [
        ("a.jpg", base),
        ("b.jpg", base + timedelta(hours=1)),
        ("c.jpg", base + timedelta(hours=6)),
        ("d.jpg", base + timedelta(hours=7)),
    ]

    events = organizer.detect_events(files)

    assert len(events) == 2
    assert events[0][2] == ["a.jpg", "b.jpg"]
    assert events[1][2] == ["c.jpg", "d.jpg"]


def test_detect_live_photos(tmp_path: Path) -> None:
    """Test Live Photo detection (matching image + video pairs)."""
    organizer = Organizer()

    # Create test files with matching names
    (tmp_path / "IMG_0001.jpg").touch()
    (tmp_path / "IMG_0001.mov").touch()
    (tmp_path / "IMG_0002.heic").touch()
    (tmp_path / "IMG_0002.mp4").touch()
    (tmp_path / "IMG_0003.jpg").touch()  # No matching video

    files = [str(f) for f in tmp_path.iterdir()]
    live_photos = organizer.detect_live_photos(files)

    assert len(live_photos) == 2
    # Each tuple should have (image_path, video_path)
    stems = {(Path(img).stem.lower(), Path(vid).stem.lower()) for img, vid in live_photos}
    assert ("img_0001", "img_0001") in stems
    assert ("img_0002", "img_0002") in stems


def test_detect_live_photos_different_folders(tmp_path: Path) -> None:
    """Live Photos must be in the same folder to be detected."""
    organizer = Organizer()

    folder1 = tmp_path / "folder1"
    folder2 = tmp_path / "folder2"
    folder1.mkdir()
    folder2.mkdir()

    (folder1 / "IMG_0001.jpg").touch()
    (folder2 / "IMG_0001.mov").touch()  # Different folder

    files = [str(folder1 / "IMG_0001.jpg"), str(folder2 / "IMG_0001.mov")]
    live_photos = organizer.detect_live_photos(files)

    assert len(live_photos) == 0


def test_preview_with_burst_subfolder(tmp_path: Path) -> None:
    """Test that burst photos are organized into subfolders when enabled."""
    import struct

    # Create source directory with burst-like photos
    source = tmp_path / "source"
    source.mkdir()

    # Create minimal JPEG files with EXIF dates close together (burst)
    base_time = datetime(2024, 1, 15, 10, 0, 0)

    for i in range(4):
        img_path = source / f"burst_{i}.jpg"
        # Create a minimal valid JPEG
        with open(img_path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
            f.write(b"\xff\xd9")

    dest = tmp_path / "dest"

    settings = OrganizeSettings(burst_handling=BurstHandling.SUBFOLDER)
    organizer = Organizer(settings=settings)

    # Mock extract_date to return burst-like timestamps
    original_extract = organizer.extract_date
    call_count = [0]

    def mock_extract(path):
        idx = call_count[0]
        call_count[0] += 1
        # First 3 files are within 2 seconds (burst), 4th is separate
        if idx < 3:
            return base_time + timedelta(seconds=idx), "exif"
        return base_time + timedelta(seconds=10), "exif"

    organizer.extract_date = mock_extract

    preview = organizer.preview(str(source), str(dest))

    # Should detect 1 burst group with 3 files
    assert preview.bursts_detected == 1

    # Files in burst should have burst_group set
    burst_files = [c for c in preview.changes if c.burst_group is not None]
    assert len(burst_files) == 3

    # Burst files should go to Burst_001 subfolder
    for change in burst_files:
        assert "Burst_001" in change.dest_path


def test_preview_with_live_photo_video_subfolder(tmp_path: Path) -> None:
    """Test that Live Photo videos are organized into subfolders when enabled."""
    source = tmp_path / "source"
    source.mkdir()

    # Create matching image + video pair
    (source / "IMG_0001.jpg").write_bytes(
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    )
    (source / "IMG_0001.mov").write_bytes(b"\x00\x00\x00\x00ftyp")

    dest = tmp_path / "dest"

    settings = OrganizeSettings(live_photo_handling=LivePhotoHandling.VIDEO_SUBFOLDER)
    organizer = Organizer(settings=settings)

    # Mock extract_date
    organizer.extract_date = lambda path: (datetime(2024, 1, 15), "file")

    preview = organizer.preview(str(source), str(dest))

    # Should detect 1 Live Photo pair
    assert preview.live_photos_detected == 1

    # Both files should be marked as live photos
    live_photo_files = [c for c in preview.changes if c.is_live_photo]
    assert len(live_photo_files) == 2

    # Video should go to LivePhoto_Videos subfolder
    video_changes = [c for c in preview.changes if c.source_path.endswith(".mov")]
    assert len(video_changes) == 1
    assert "LivePhoto_Videos" in video_changes[0].dest_path

    # Image should NOT go to LivePhoto_Videos subfolder
    image_changes = [c for c in preview.changes if c.source_path.endswith(".jpg")]
    assert len(image_changes) == 1
    assert "LivePhoto_Videos" not in image_changes[0].dest_path


def test_location_level_city_only() -> None:
    """Test that location_level='city' returns only the city name from cache."""
    settings = OrganizeSettings(location_level="city")
    organizer = Organizer(settings=settings)

    # Pre-populate the cache (simulates a previous geocoding result)
    organizer._location_cache[(40.7128, -74.0060)] = "New_York"

    result = organizer.get_location_name(40.7128, -74.0060)
    assert result == "New_York"


def test_location_level_city_country() -> None:
    """Test that location_level='city_country' returns city and country from cache."""
    settings = OrganizeSettings(location_level="city_country")
    organizer = Organizer(settings=settings)

    # Pre-populate the cache
    organizer._location_cache[(48.8566, 2.3522)] = "Paris_France"

    result = organizer.get_location_name(48.8566, 2.3522)
    assert result == "Paris_France"


def test_location_level_full() -> None:
    """Test that location_level='full' returns city, state, and country from cache."""
    settings = OrganizeSettings(location_level="full")
    organizer = Organizer(settings=settings)

    # Pre-populate the cache
    organizer._location_cache[(34.0522, -118.2437)] = "Los_Angeles_California_United_States"

    result = organizer.get_location_name(34.0522, -118.2437)
    assert result == "Los_Angeles_California_United_States"


def test_preview_stats_include_burst_and_live_counts(tmp_path: Path) -> None:
    """Test that preview stats include burst and live photo counts."""
    source = tmp_path / "source"
    source.mkdir()

    # Create files
    (source / "IMG_0001.jpg").write_bytes(
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    )
    (source / "IMG_0001.mov").write_bytes(b"\x00\x00\x00\x00ftyp")
    for i in range(3):
        (source / f"burst_{i}.jpg").write_bytes(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        )

    dest = tmp_path / "dest"

    settings = OrganizeSettings(
        burst_handling=BurstHandling.SUBFOLDER,
        live_photo_handling=LivePhotoHandling.VIDEO_SUBFOLDER,
    )
    organizer = Organizer(settings=settings)

    # Mock extract_date to return burst-like timestamps
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    call_count = [0]

    def mock_extract(path):
        idx = call_count[0]
        call_count[0] += 1
        if "burst" in path:
            # Burst files within 2 seconds
            return base_time + timedelta(seconds=idx % 3), "exif"
        return base_time, "file"

    organizer.extract_date = mock_extract

    preview = organizer.preview(str(source), str(dest))

    # Should have detected 1 live photo pair
    assert preview.live_photos_detected == 1

    # Should have detected 1 burst group (3 burst files)
    assert preview.bursts_detected == 1
