from __future__ import annotations

import mimetypes
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

LOG_DIR = ROOT / ".test_artifacts" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("DUPLICLEANER_LOG_DIR", str(LOG_DIR))

import pytest  # noqa: E402

import duplicleaner.db.database as database_module  # noqa: E402
import duplicleaner.utils.config as config_module  # noqa: E402
from duplicleaner.db.database import Database  # noqa: E402
from duplicleaner.db.models import Drive, FileRecord  # noqa: E402
from tests.fixtures.fs_builder import FixturePaths, build_test_tree  # noqa: E402


@pytest.fixture
def fs_tree(tmp_path: Path) -> FixturePaths:
    """
    Create a deterministic filesystem tree under a temp directory.
    """
    return build_test_tree(tmp_path / "dataset")


@pytest.fixture(autouse=True)
def isolate_app_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Isolate config/database paths to a temp directory for all tests.
    """
    appdata = tmp_path / "appdata"
    appdata.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config_module, "get_app_data_dir", lambda: appdata)
    config_module._config = None
    database_module._database = None


@pytest.fixture
def test_db(tmp_path: Path) -> Database:
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def test_drive(fs_tree: FixturePaths, test_db: Database) -> Drive:
    drive = Drive(id="D1", label="TestDrive", path=str(fs_tree.root))
    test_db.add_drive(drive)
    return drive


def make_file_record(path: Path, drive_id: str, **overrides: object) -> FileRecord:
    stat_info = path.stat()
    mime_type, _ = mimetypes.guess_type(path.name)
    return FileRecord(
        drive_id=drive_id,
        path=str(path),
        filename=path.name,
        size=stat_info.st_size,
        created=datetime.fromtimestamp(stat_info.st_ctime),
        modified=datetime.fromtimestamp(stat_info.st_mtime),
        file_type=path.suffix.lower() or None,
        mime_type=mime_type,
        scan_date=datetime.now(),
        **overrides,
    )
