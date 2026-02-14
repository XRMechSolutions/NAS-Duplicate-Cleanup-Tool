from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from duplicleaner.core.resolver import ResolutionStrategy, Resolver
from duplicleaner.db.models import MatchType
from tests.conftest import make_file_record


def _make_file(path: Path, size: int, mtime: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"a" * size)
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))


def _seed_group(tmp_path: Path, test_db, test_drive):
    base = tmp_path / "resolver"
    f1 = base / "a.bin"
    f2 = base / "b.bin"
    f3 = base / "c.bin"

    _make_file(f1, 100, datetime.now() - timedelta(days=2))
    _make_file(f2, 200, datetime.now() - timedelta(days=1))
    _make_file(f3, 150, datetime.now())

    ids = []
    for f in (f1, f2, f3):
        record = make_file_record(f, test_drive.id)
        file_id = test_db.add_file(record)
        ids.append(file_id)

    group_id = test_db.create_duplicate_group(
        match_type=MatchType.EXACT,
        similarity=1.0,
        file_ids=ids,
    )
    return group_id, ids


def test_resolver_keep_newest(tmp_path: Path, test_db, test_drive) -> None:
    group_id, ids = _seed_group(tmp_path, test_db, test_drive)
    resolver = Resolver(db=test_db)
    resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_NEWEST)

    assert resolution is not None
    assert resolution.keeper_id == ids[2]


def test_resolver_keep_largest(tmp_path: Path, test_db, test_drive) -> None:
    group_id, ids = _seed_group(tmp_path, test_db, test_drive)
    resolver = Resolver(db=test_db)
    resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_LARGEST)

    assert resolution is not None
    assert resolution.keeper_id == ids[1]


def test_resolver_keep_shortest_path(tmp_path: Path, test_db, test_drive) -> None:
    base = tmp_path / "resolver_short"
    long_dir = base / ("long" * 10)
    short_file = base / "a.bin"
    long_file = long_dir / "b.bin"

    _make_file(short_file, 100, datetime.now())
    _make_file(long_file, 100, datetime.now())

    ids = []
    for f in (short_file, long_file):
        record = make_file_record(f, test_drive.id)
        file_id = test_db.add_file(record)
        ids.append(file_id)

    group_id = test_db.create_duplicate_group(
        match_type=MatchType.EXACT,
        similarity=1.0,
        file_ids=ids,
    )

    resolver = Resolver(db=test_db)
    resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_SHORTEST_PATH)

    assert resolution is not None
    assert resolution.keeper_id == ids[0]


def test_ignore_group_skips_resolution(tmp_path: Path, test_db, test_drive) -> None:
    group_id, _ = _seed_group(tmp_path, test_db, test_drive)
    resolver = Resolver(db=test_db)
    resolver.ignore_group(group_id)

    resolution = resolver.resolve_group(group_id, ResolutionStrategy.KEEP_LARGEST)
    assert resolution is None
