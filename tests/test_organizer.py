from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from duplicleaner.core.organizer import (
    DateFormat,
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
