from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_documentation_chapters_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    panel_path = root / "src" / "duplicleaner" / "ui" / "documentation_panel.py"
    spec = spec_from_file_location("documentation_panel", panel_path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    docs_dir = root / "docs"
    panel = module.DocumentationPanel(parent="dummy", docs_dir=docs_dir)
    chapters = panel._build_chapters()

    missing = [name for name, path in chapters.items() if not path.exists()]
    assert missing == []
