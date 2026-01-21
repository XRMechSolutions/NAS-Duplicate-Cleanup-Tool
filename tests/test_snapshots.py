from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from duplicleaner.core.organizer import Organizer
from duplicleaner.core.resolver import ResolutionStrategy, Resolver
from duplicleaner.db.models import MatchType

from tests.conftest import make_file_record


SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def _load_snapshot(name: str) -> dict:
    path = SNAPSHOT_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_snapshot_organizer_preview(fs_tree, tmp_path: Path, test_db, monkeypatch) -> None:
    organizer = Organizer(db=test_db)
    # Normalize file dates for deterministic folder structure
    fixed_ts = 1577923200  # 2020-01-02 00:00:00 UTC
    for path in (
        fs_tree.files["base_img"],
        fs_tree.files["dup_img"],
        fs_tree.files["near_img"],
        fs_tree.files["no_exif"],
    ):
        os.utime(path, (fixed_ts, fixed_ts))

    original_extract = organizer.extract_date

    def stable_extract(file_path: str):
        name = Path(file_path).name
        if name in {"base.jpg", "base_copy.jpg"}:
            return original_extract(file_path)
        return (datetime(2020, 1, 2, 0, 0, 0), "file")

    monkeypatch.setattr(organizer, "extract_date", stable_extract)

    preview = organizer.preview(str(fs_tree.root / "images"), str(tmp_path / "dest"))

    data = {
        "total_files": preview.total_files,
        "files_to_move": preview.files_to_move,
        "files_to_rename": preview.files_to_rename,
        "folders_to_create": preview.folders_to_create,
        "folders": dict(sorted(preview.folders.items())),
    }

    expected = _load_snapshot("organizer_preview.json")
    assert data == expected


def test_snapshot_resolver_preview(tmp_path: Path, test_db, test_drive) -> None:
    p1 = tmp_path / "a.bin"
    p2 = tmp_path / "long" / "b.bin"
    p3 = tmp_path / "longer" / "c.bin"
    p2.parent.mkdir(parents=True, exist_ok=True)
    p3.parent.mkdir(parents=True, exist_ok=True)
    p1.write_text("same", encoding="utf-8")
    p2.write_text("same", encoding="utf-8")
    p3.write_text("same", encoding="utf-8")

    ids = []
    for p in (p1, p2, p3):
        ids.append(test_db.add_file(make_file_record(p, test_drive.id)))

    group_id = test_db.create_duplicate_group(
        match_type=MatchType.EXACT,
        similarity=1.0,
        file_ids=ids,
    )

    resolver = Resolver(db=test_db)
    preview = resolver.preview_resolution(ResolutionStrategy.KEEP_SHORTEST_PATH, [group_id])

    data = {
        "groups_affected": preview.groups_affected,
        "files_to_keep": preview.files_to_keep,
        "files_to_remove": preview.files_to_remove,
        "space_to_recover": preview.space_to_recover,
        "keeper_basenames": sorted(Path(r.keeper_path).name for r in preview.resolutions),
        "remove_basenames": sorted(
            name for r in preview.resolutions for name in [Path(p).name for p in r.remove_paths]
        ),
    }

    expected = _load_snapshot("resolver_preview.json")
    assert data == expected
