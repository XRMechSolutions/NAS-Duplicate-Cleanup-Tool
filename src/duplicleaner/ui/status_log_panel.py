"""Simple status log panel for recent messages."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Deque

import dearpygui.dearpygui as dpg

LEVELS = ["info", "warning", "error"]
LEVEL_COLORS = {
    "info": (200, 200, 200),
    "warning": (255, 200, 100),
    "error": (255, 120, 120),
}


class StatusLogPanel:
    """UI panel for recent status messages."""

    TAG_PANEL = "status_log_panel"
    TAG_LIST = "status_log_list"
    TAG_FILTER = "status_log_filter"

    def __init__(self, parent: int | str, max_entries: int = 200):
        self.parent = parent
        self.max_entries = max_entries
        self._entries: Deque[tuple[str, str]] = deque(maxlen=max_entries)

        self._build_ui()

    def _build_ui(self) -> None:
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            with dpg.group(horizontal=True):
                dpg.add_text("Status Log", color=(150, 200, 255))
                dpg.add_spacer(width=10)
                dpg.add_text("Filter:")
                dpg.add_combo(
                    tag=self.TAG_FILTER,
                    items=["All", "Info", "Warnings", "Errors"],
                    default_value="All",
                    width=120,
                    callback=self._on_filter_change,
                )
                dpg.add_spacer(width=10)
                dpg.add_button(label="Export Log", callback=self._export)
                dpg.add_button(label="Clear", callback=self.clear)

            dpg.add_separator()
            with dpg.child_window(height=400, border=True):
                dpg.add_listbox(tag=self.TAG_LIST, items=[], num_items=18, width=-1)

    def add(self, message: str, level: str = "info") -> None:
        """Add a message to the log."""
        if level not in LEVELS:
            level = "info"
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] [{level.upper()}] {message}"
        self._entries.appendleft((entry, level))
        self._refresh_view()

    def clear(self) -> None:
        """Clear the log."""
        self._entries.clear()
        self._refresh_view()

    def _on_filter_change(self) -> None:
        self._refresh_view()

    def _refresh_view(self) -> None:
        filter_val = dpg.get_value(self.TAG_FILTER)
        if filter_val == "Warnings":
            filtered = [entry for entry, lvl in self._entries if lvl == "warning"]
        elif filter_val == "Errors":
            filtered = [entry for entry, lvl in self._entries if lvl == "error"]
        elif filter_val == "Info":
            filtered = [entry for entry, lvl in self._entries if lvl == "info"]
        else:
            filtered = [entry for entry, _ in self._entries]

        dpg.configure_item(self.TAG_LIST, items=filtered)

    def _export(self) -> None:
        """Export log to Desktop as text file."""
        try:
            export_path = Path.home() / "Desktop" / "status_log.txt"
            with open(export_path, "w", encoding="utf-8") as handle:
                for entry, _ in reversed(self._entries):
                    handle.write(entry + "\n")
        except Exception:
            pass
