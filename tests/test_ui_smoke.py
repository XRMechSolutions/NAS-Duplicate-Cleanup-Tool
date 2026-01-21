from __future__ import annotations

import pytest


@pytest.mark.requires_dearpygui
def test_dearpygui_context_smoke() -> None:
    try:
        import dearpygui.dearpygui as dpg
    except Exception:
        pytest.skip("Dear PyGui not available")

    dpg.create_context()
    dpg.destroy_context()
