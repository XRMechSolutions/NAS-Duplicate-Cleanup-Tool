"""Simple status log panel for recent messages."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Deque

import dearpygui.dearpygui as dpg

from duplicleaner.ui.theme import get_status_color, get_accent_color, get_text_color

LEVELS = ["info", "warning", "error"]


class StatusLogPanel:
    """UI panel for recent status messages."""

    TAG_PANEL = "status_log_panel"
    TAG_LIST = "status_log_list"
    TAG_LIST_CONTAINER = "status_log_list_container"
    TAG_FILTER = "status_log_filter"
    TAG_STATUS = "status_log_status"
    TAG_COPY_SELECTED = "status_log_copy_selected"
    TAG_COPY_VISIBLE = "status_log_copy_visible"
    TAG_COPY_ALL = "status_log_copy_all"
    TAG_KEY_HANDLER = "status_log_key_handler"

    def __init__(self, parent: int | str, max_entries: int = 200):
        self.parent = parent
        self.max_entries = max_entries
        self._entries: Deque[tuple[str, str]] = deque(maxlen=max_entries)
        self._selected_entries: set[str] = set()
        self._visible_entries: list[str] = []
        self._last_selected: str | None = None

        # Theme cache for level colors
        self._level_themes: dict[tuple[int, int, int], str] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            with dpg.handler_registry(tag=self.TAG_KEY_HANDLER):
                dpg.add_key_press_handler(key=dpg.mvKey_C, callback=self._on_copy_shortcut)
                dpg.add_key_press_handler(key=dpg.mvKey_A, callback=self._on_select_all_shortcut)
            with dpg.group(horizontal=True):
                dpg.add_text("Status Log", color=get_accent_color())
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
                dpg.add_button(label="Copy Selected", tag=self.TAG_COPY_SELECTED, callback=self._copy_selected)
                dpg.add_button(label="Copy Visible", tag=self.TAG_COPY_VISIBLE, callback=self._copy_visible)
                dpg.add_button(label="Copy All", tag=self.TAG_COPY_ALL, callback=self._copy_all)
                dpg.add_button(label="Clear", callback=self.clear)
                dpg.add_spacer(width=10)
                dpg.add_text("", tag=self.TAG_STATUS, color=get_text_color("disabled"))

            dpg.add_separator()
            with dpg.child_window(height=400, border=True):
                with dpg.group(tag=self.TAG_LIST_CONTAINER):
                    dpg.add_text("")

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
        self._selected_entries.clear()
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

        self._visible_entries = filtered
        children = dpg.get_item_children(self.TAG_LIST_CONTAINER, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        if not filtered:
            dpg.add_text("No log entries.", parent=self.TAG_LIST_CONTAINER, color=get_text_color("disabled"))
            return

        for entry in filtered:
            # Determine color based on level tag in the entry
            color = get_status_color("info")
            if "[WARNING]" in entry:
                color = get_status_color("warning")
            elif "[ERROR]" in entry:
                color = get_status_color("error")

            sel = dpg.add_selectable(
                label=entry,
                parent=self.TAG_LIST_CONTAINER,
                default_value=entry in self._selected_entries,
                callback=self._on_entry_selected,
                user_data=entry,
                span_columns=True,
            )
            # Apply color to the selectable text
            dpg.bind_item_theme(sel, self._get_or_create_level_theme(color))

    def _on_entry_selected(self, sender, app_data, user_data) -> None:
        entry = user_data
        is_selected = dpg.get_value(sender)
        shift_down = self._is_shift_down()
        ctrl_down = self._is_ctrl_down()

        if shift_down and self._last_selected in self._visible_entries:
            start = self._visible_entries.index(self._last_selected)
            end = self._visible_entries.index(entry)
            if start > end:
                start, end = end, start
            range_entries = set(self._visible_entries[start:end + 1])
            if not ctrl_down:
                self._selected_entries.clear()
            self._selected_entries.update(range_entries)
            self._refresh_view()
        else:
            if is_selected:
                if not ctrl_down:
                    self._selected_entries.clear()
                self._selected_entries.add(entry)
            else:
                self._selected_entries.discard(entry)

        self._last_selected = entry

    def _export(self) -> None:
        """Export log to Desktop as text file."""
        try:
            export_path = Path.home() / "Desktop" / "status_log.txt"
            with open(export_path, "w", encoding="utf-8") as handle:
                for entry, _ in reversed(self._entries):
                    handle.write(entry + "\n")
            dpg.set_value(self.TAG_STATUS, f"Exported to {export_path}")
        except Exception:
            dpg.set_value(self.TAG_STATUS, "Export failed.")

    def _copy_selected(self) -> None:
        """Copy selected log lines to clipboard."""
        if not self._selected_entries:
            dpg.set_value(self.TAG_STATUS, "No entries selected.")
            return

        ordered = [entry for entry, _ in reversed(self._entries) if entry in self._selected_entries]
        dpg.set_clipboard_text("\n".join(ordered))
        dpg.set_value(self.TAG_STATUS, f"Copied {len(ordered)} entries.")

    def _copy_visible(self) -> None:
        """Copy visible (filtered) log lines to clipboard."""
        filter_val = dpg.get_value(self.TAG_FILTER)
        if filter_val == "Warnings":
            filtered = [entry for entry, lvl in self._entries if lvl == "warning"]
        elif filter_val == "Errors":
            filtered = [entry for entry, lvl in self._entries if lvl == "error"]
        elif filter_val == "Info":
            filtered = [entry for entry, lvl in self._entries if lvl == "info"]
        else:
            filtered = [entry for entry, _ in self._entries]

        if not filtered:
            dpg.set_value(self.TAG_STATUS, "No entries to copy.")
            return

        ordered = list(reversed(filtered))
        dpg.set_clipboard_text("\n".join(ordered))
        dpg.set_value(self.TAG_STATUS, f"Copied {len(ordered)} entries.")

    def _copy_all(self) -> None:
        """Copy all log lines to clipboard."""
        if not self._entries:
            dpg.set_value(self.TAG_STATUS, "No entries to copy.")
            return
        ordered = [entry for entry, _ in reversed(self._entries)]
        dpg.set_clipboard_text("\n".join(ordered))
        dpg.set_value(self.TAG_STATUS, f"Copied {len(ordered)} entries.")

    def _on_copy_shortcut(self) -> None:
        """Handle Ctrl+C for selected entries."""
        if not self._is_ctrl_down():
            return
        self._copy_selected()

    def _on_select_all_shortcut(self) -> None:
        """Handle Ctrl+A for selecting all visible entries."""
        if not self._is_ctrl_down():
            return
        if not self._visible_entries:
            return
        self._selected_entries = set(self._visible_entries)
        self._refresh_view()
        dpg.set_value(self.TAG_STATUS, f"Selected {len(self._visible_entries)} entries.")

    def _is_ctrl_down(self) -> bool:
        """Return True if either control key is pressed."""
        key = getattr(dpg, "mvKey_Control", None)
        if key is not None:
            return dpg.is_key_down(key)
        left = getattr(dpg, "mvKey_LControl", None)
        right = getattr(dpg, "mvKey_RControl", None)
        if left is None and right is None:
            return False
        return (left is not None and dpg.is_key_down(left)) or (right is not None and dpg.is_key_down(right))

    def _is_shift_down(self) -> bool:
        """Return True if either shift key is pressed."""
        key = getattr(dpg, "mvKey_Shift", None)
        if key is not None:
            return dpg.is_key_down(key)
        left = getattr(dpg, "mvKey_LShift", None)
        right = getattr(dpg, "mvKey_RShift", None)
        if left is None and right is None:
            return False
        return (left is not None and dpg.is_key_down(left)) or (right is not None and dpg.is_key_down(right))

    def _get_or_create_level_theme(self, color: tuple[int, int, int]) -> str:
        """Get or create a theme for a specific text color."""
        if color in self._level_themes:
            return self._level_themes[color]

        theme_tag = f"status_log_theme_{color[0]}_{color[1]}_{color[2]}"
        with dpg.theme(tag=theme_tag):
            with dpg.theme_component(dpg.mvSelectable):
                dpg.add_theme_color(dpg.mvThemeCol_Text, color)

        self._level_themes[color] = theme_tag
        return theme_tag

    def cleanup(self) -> None:
        """Clean up resources."""
        # Delete key handler registry
        if dpg.does_item_exist(self.TAG_KEY_HANDLER):
            try:
                dpg.delete_item(self.TAG_KEY_HANDLER)
            except Exception:
                pass

        # Delete level themes
        for theme_tag in self._level_themes.values():
            if dpg.does_item_exist(theme_tag):
                try:
                    dpg.delete_item(theme_tag)
                except Exception:
                    pass
        self._level_themes.clear()

        # Clear entries
        self._entries.clear()
        self._selected_entries.clear()
        self._visible_entries.clear()
