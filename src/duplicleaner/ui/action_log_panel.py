"""Action Log Panel for DupliCleaner.

Dear PyGui UI component for viewing action history and managing undo operations.
"""

import csv
import json
import os
from collections.abc import Callable
from datetime import datetime, timedelta

import dearpygui.dearpygui as dpg

from duplicleaner.core.actions import ActionEngine, ActionResult, ActionStatus
from duplicleaner.db.database import get_database
from duplicleaner.db.models import ActionLogEntry, ActionType
from duplicleaner.ui.theme import get_accent_color, get_status_color, get_text_color
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


def format_size(size_bytes: int | None) -> str:
    """Format bytes as human readable size."""
    if size_bytes is None:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_timestamp(ts: datetime | None) -> str:
    """Format timestamp for display."""
    if ts is None:
        return "-"
    return ts.strftime("%Y-%m-%d %H:%M:%S")


class ActionLogPanel:
    """UI panel for viewing action history and undo operations."""

    # Tag constants
    TAG_PANEL = "action_log_panel"
    TAG_LOG_TABLE = "action_log_table"
    TAG_STATS = "action_log_stats"
    TAG_QUARANTINE_STATS = "quarantine_stats"
    TAG_UNDO_DIALOG = "undo_dialog"
    TAG_EXPORT_DIALOG = "export_dialog"
    TAG_EMPTY_QUARANTINE_DIALOG = "empty_quarantine_dialog"
    TAG_CLEAR_OLD_DIALOG = "clear_old_dialog"
    TAG_QUARANTINE_PANEL = "quarantine_panel"
    TAG_QUARANTINE_TABLE = "quarantine_table"

    # Action type display names
    ACTION_LABELS = {
        ActionType.DELETE: "Delete",
        ActionType.QUARANTINE: "Quarantine",
        ActionType.TRASH: "Trash",
        ActionType.LINK: "Link",
        ActionType.COPY: "Copy",
        ActionType.MOVE: "Move",
        ActionType.RESTORE: "Restore",
    }

    def __init__(
        self,
        parent: int | str,
        action_engine: ActionEngine | None = None,
        on_undo_complete: Callable[[ActionResult], None] | None = None,
        on_status_update: Callable[[str], None] | None = None,
    ):
        """Initialize the action log panel.

        Args:
            parent: Parent window/container tag
            action_engine: ActionEngine instance for undo operations
            on_undo_complete: Callback when undo is complete
        """
        self.parent = parent
        self.on_undo_complete = on_undo_complete
        self.on_status_update = on_status_update

        self.db = get_database()
        self.action_engine = action_engine

        # Current state
        self._entries: list[ActionLogEntry] = []
        self._selected_ids: set[int] = set()
        self._current_page = 0
        self._page_size = 100
        self._total_count = 0

        # Filters
        self._filter_type: ActionType | None = None
        self._filter_date_range: str = "All Time"
        self._filter_status: bool | None = None  # None=all, True=undone, False=not undone

        # Build UI
        self._build_ui()

    def set_action_engine(self, engine: ActionEngine) -> None:
        """Set the action engine for undo operations."""
        self.action_engine = engine

    def _build_ui(self) -> None:
        """Build the panel UI."""
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            # Header
            dpg.add_text("Action Log", color=get_accent_color())
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Statistics bar
            with dpg.group(horizontal=True, tag=self.TAG_STATS):
                dpg.add_text("Loading statistics...", tag="action_log_stats_text")

            dpg.add_spacer(height=10)

            # Filter bar
            with dpg.group(horizontal=True):
                dpg.add_text("Filter:")
                dpg.add_combo(
                    items=["All Actions", "Delete", "Quarantine", "Trash", "Move", "Copy", "Link", "Restore"],
                    default_value="All Actions",
                    width=120,
                    callback=self._on_filter_type_change,
                    tag="action_filter_type"
                )

                dpg.add_spacer(width=15)
                dpg.add_text("Date:")
                dpg.add_combo(
                    items=["All Time", "Today", "Last 7 Days", "Last 30 Days", "Last 90 Days"],
                    default_value="All Time",
                    width=120,
                    callback=self._on_filter_date_change,
                    tag="action_filter_date"
                )

                dpg.add_spacer(width=15)
                dpg.add_text("Status:")
                dpg.add_combo(
                    items=["All", "Active", "Undone"],
                    default_value="All",
                    width=100,
                    callback=self._on_filter_status_change,
                    tag="action_filter_status"
                )

                dpg.add_spacer(width=20)
                dpg.add_button(label="Refresh", callback=self._refresh_log)

            dpg.add_spacer(height=10)

            # Action buttons
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Undo Selected",
                    callback=self._on_undo_selected,
                    tag="btn_undo_selected"
                )
                dpg.add_button(
                    label="Export Log",
                    callback=self._show_export_dialog
                )
                dpg.add_button(
                    label="View Quarantine",
                    callback=self._show_quarantine_panel
                )
                dpg.add_button(
                    label="Clear Old Entries",
                    callback=self._on_clear_old
                )

            dpg.add_spacer(height=10)

            # Log table
            with dpg.table(
                tag=self.TAG_LOG_TABLE,
                header_row=True,
                borders_innerH=True,
                borders_outerH=True,
                borders_innerV=True,
                borders_outerV=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                row_background=True,
                scrollY=True,
                height=400,
            ):
                dpg.add_table_column(label="", width_fixed=True, init_width_or_weight=30)  # Checkbox
                dpg.add_table_column(label="Time", width_fixed=True, init_width_or_weight=140)
                dpg.add_table_column(label="Action", width_fixed=True, init_width_or_weight=80)
                dpg.add_table_column(label="Source Path", init_width_or_weight=250)
                dpg.add_table_column(label="Destination", init_width_or_weight=200)
                dpg.add_table_column(label="Size", width_fixed=True, init_width_or_weight=80)
                dpg.add_table_column(label="Status", width_fixed=True, init_width_or_weight=70)
                dpg.add_table_column(label="Undo", width_fixed=True, init_width_or_weight=60)

            dpg.add_spacer(height=10)

            # Pagination
            with dpg.group(horizontal=True):
                dpg.add_button(label="<< First", callback=self._on_first_page, tag="btn_first_page")
                dpg.add_button(label="< Prev", callback=self._on_prev_page, tag="btn_prev_page")
                dpg.add_text("Page 1 of 1", tag="page_info_text")
                dpg.add_button(label="Next >", callback=self._on_next_page, tag="btn_next_page")
                dpg.add_button(label="Last >>", callback=self._on_last_page, tag="btn_last_page")
                dpg.add_spacer(width=20)
                dpg.add_text("", tag="showing_count_text")

            dpg.add_spacer(height=15)

            # Quarantine section
            dpg.add_separator()
            dpg.add_text("Quarantine Folder", color=get_accent_color())
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True, tag=self.TAG_QUARANTINE_STATS):
                dpg.add_text("Loading quarantine info...", tag="quarantine_stats_text")

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Browse Quarantine", callback=self._on_browse_quarantine)
                dpg.add_button(label="Restore All", callback=self._on_restore_all_quarantine)
                dpg.add_button(label="Empty Quarantine", callback=self._show_empty_quarantine_dialog)

        # Create dialogs
        self._create_dialogs()

    def _create_dialogs(self) -> None:
        """Create modal dialogs."""
        # Undo confirmation dialog
        with dpg.window(
            label="Confirm Undo",
            tag=self.TAG_UNDO_DIALOG,
            modal=True,
            show=False,
            width=500,
            height=300,
            no_resize=True,
            pos=[200, 150],
        ):
            dpg.add_text("Are you sure you want to undo these actions?", tag="undo_dialog_text")
            dpg.add_spacer(height=10)
            dpg.add_text("This will:", color=get_status_color("warning"))
            dpg.add_text("", tag="undo_dialog_details", wrap=480)
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Confirm Undo", callback=self._confirm_undo)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_UNDO_DIALOG, show=False))

        # Export dialog
        with dpg.window(
            label="Export Action Log",
            tag=self.TAG_EXPORT_DIALOG,
            modal=True,
            show=False,
            width=400,
            height=200,
            no_resize=True,
            pos=[250, 200],
        ):
            dpg.add_text("Export Format:")
            dpg.add_radio_button(
                items=["CSV (Spreadsheet)", "JSON (Machine Readable)", "HTML (Report)"],
                default_value="CSV (Spreadsheet)",
                tag="export_format"
            )
            dpg.add_spacer(height=10)
            dpg.add_text("Include:")
            dpg.add_checkbox(label="Current filter only", default_value=True, tag="export_filtered")
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Export", callback=self._do_export)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_EXPORT_DIALOG, show=False))

        # Empty quarantine confirmation
        with dpg.window(
            label="Empty Quarantine",
            tag=self.TAG_EMPTY_QUARANTINE_DIALOG,
            modal=True,
            show=False,
            width=450,
            height=250,
            no_resize=True,
            pos=[225, 175],
        ):
            dpg.add_text("This will PERMANENTLY DELETE all quarantined files.", color=get_status_color("error"))
            dpg.add_spacer(height=10)
            dpg.add_text("", tag="empty_quarantine_info")
            dpg.add_spacer(height=10)
            dpg.add_text("This action CANNOT be undone.", color=get_status_color("warning"))
            dpg.add_spacer(height=10)
            dpg.add_text("Type 'DELETE' to confirm:")
            dpg.add_input_text(tag="confirm_delete_input", width=200)
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Empty Quarantine", callback=self._confirm_empty_quarantine)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_EMPTY_QUARANTINE_DIALOG, show=False))

        # Clear old entries dialog
        with dpg.window(
            label="Clear Old Entries",
            tag=self.TAG_CLEAR_OLD_DIALOG,
            modal=True,
            show=False,
            width=420,
            height=230,
            no_resize=True,
            pos=[240, 180],
        ):
            dpg.add_text("Delete action log entries older than:")
            dpg.add_combo(
                items=["30 days", "90 days", "180 days", "365 days"],
                default_value="90 days",
                width=140,
                tag="clear_old_age",
            )
            dpg.add_spacer(height=8)
            dpg.add_checkbox(
                label="Only delete entries already undone",
                default_value=True,
                tag="clear_old_reversed_only",
            )
            dpg.add_spacer(height=10)
            dpg.add_text("", tag="clear_old_preview", color=get_text_color("secondary"))
            dpg.add_spacer(height=15)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Delete Entries", callback=self._confirm_clear_old)
                dpg.add_button(label="Cancel", callback=lambda: dpg.configure_item(self.TAG_CLEAR_OLD_DIALOG, show=False))

        # Quarantine browser panel
        with dpg.window(
            label="Quarantine Browser",
            tag=self.TAG_QUARANTINE_PANEL,
            modal=False,
            show=False,
            width=900,
            height=500,
            no_resize=False,
            pos=[120, 120],
        ):
            dpg.add_text("Quarantine Items", color=get_accent_color())
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Refresh", callback=self._refresh_quarantine_panel)
                dpg.add_button(label="Restore Selected", callback=self._restore_selected_quarantine)
                dpg.add_button(label="Close", callback=lambda: dpg.configure_item(self.TAG_QUARANTINE_PANEL, show=False))
            dpg.add_spacer(height=8)
            with dpg.table(
                tag=self.TAG_QUARANTINE_TABLE,
                header_row=True,
                borders_innerH=True,
                borders_outerH=True,
                borders_innerV=True,
                borders_outerV=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                row_background=True,
                scrollY=True,
                height=380,
            ):
                dpg.add_table_column(label="", width_fixed=True, init_width_or_weight=30)
                dpg.add_table_column(label="Time", width_fixed=True, init_width_or_weight=140)
                dpg.add_table_column(label="Original Path", init_width_or_weight=280)
                dpg.add_table_column(label="Quarantine Path", init_width_or_weight=260)
                dpg.add_table_column(label="Size", width_fixed=True, init_width_or_weight=80)
                dpg.add_table_column(label="Restore", width_fixed=True, init_width_or_weight=80)

    def _on_filter_type_change(self, sender, app_data, user_data) -> None:
        """Handle action type filter change."""
        type_map = {
            "All Actions": None,
            "Delete": ActionType.DELETE,
            "Quarantine": ActionType.QUARANTINE,
            "Trash": ActionType.TRASH,
            "Move": ActionType.MOVE,
            "Copy": ActionType.COPY,
            "Link": ActionType.LINK,
            "Restore": ActionType.RESTORE,
        }
        self._filter_type = type_map.get(app_data)
        self._current_page = 0
        self._refresh_log()

    def _on_filter_date_change(self, sender, app_data, user_data) -> None:
        """Handle date filter change."""
        self._filter_date_range = app_data
        self._current_page = 0
        self._refresh_log()

    def _on_filter_status_change(self, sender, app_data, user_data) -> None:
        """Handle status filter change."""
        status_map = {
            "All": None,
            "Active": False,
            "Undone": True,
        }
        self._filter_status = status_map.get(app_data)
        self._current_page = 0
        self._refresh_log()

    def _get_date_filter(self) -> tuple[datetime | None, datetime | None]:
        """Get start/end dates from filter selection."""
        now = datetime.now()
        if self._filter_date_range == "Today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return start, None
        elif self._filter_date_range == "Last 7 Days":
            start = now - timedelta(days=7)
            return start, None
        elif self._filter_date_range == "Last 30 Days":
            start = now - timedelta(days=30)
            return start, None
        elif self._filter_date_range == "Last 90 Days":
            start = now - timedelta(days=90)
            return start, None
        else:
            return None, None

    def _refresh_log(self) -> None:
        """Refresh the action log display."""
        try:
            start_date, end_date = self._get_date_filter()

            # Get total count
            self._total_count = self.db.get_action_log_count(
                action_type=self._filter_type,
                start_date=start_date,
                end_date=end_date,
                reversed=self._filter_status,
            )

            # Get entries for current page
            self._entries = self.db.get_action_log(
                action_type=self._filter_type,
                start_date=start_date,
                end_date=end_date,
                reversed=self._filter_status,
                limit=self._page_size,
                offset=self._current_page * self._page_size,
            )

            # Clear selected
            self._selected_ids.clear()

            # Update statistics
            self._update_stats()

            # Update table
            self._update_table()

            # Update pagination
            self._update_pagination()

            # Update quarantine stats
            self._update_quarantine_stats()

        except Exception as e:
            logger.error(f"Error refreshing action log: {e}")
            dpg.set_value("action_log_stats_text", f"Error loading log: {e}")

    def _update_stats(self) -> None:
        """Update statistics display."""
        try:
            # Get overall stats
            total = self.db.get_action_log_count()
            delete_count = self.db.get_action_log_count(action_type=ActionType.DELETE)
            quarantine_count = self.db.get_action_log_count(action_type=ActionType.QUARANTINE)
            move_count = self.db.get_action_log_count(action_type=ActionType.MOVE)
            undone_count = self.db.get_action_log_count(reversed=True)

            stats_text = (
                f"Total: {total:,} actions | "
                f"Deleted: {delete_count:,} | "
                f"Quarantined: {quarantine_count:,} | "
                f"Moved: {move_count:,} | "
                f"Undone: {undone_count:,}"
            )
            dpg.set_value("action_log_stats_text", stats_text)

        except Exception as e:
            logger.error(f"Error updating stats: {e}")

    def _update_table(self) -> None:
        """Update the log table with current entries."""
        # Clear existing rows
        for child in dpg.get_item_children(self.TAG_LOG_TABLE, 1):
            dpg.delete_item(child)

        # Add rows
        for entry in self._entries:
            if entry.id is None:
                continue

            entry_id = entry.id
            with dpg.table_row(parent=self.TAG_LOG_TABLE):
                # Checkbox
                dpg.add_checkbox(
                    default_value=entry_id in self._selected_ids,
                    callback=lambda s, a, u: self._toggle_selection(u),
                    user_data=entry_id,
                )

                # Timestamp
                dpg.add_text(format_timestamp(entry.timestamp))

                # Action type with color
                action_label = self.ACTION_LABELS.get(entry.action_type, str(entry.action_type.value))
                color = self._get_action_color(entry.action_type)
                dpg.add_text(action_label, color=color)

                # Source path (truncated)
                source = entry.source_path
                if len(source) > 45:
                    source = "..." + source[-42:]
                dpg.add_text(source)

                # Destination (truncated)
                dest = entry.dest_path or "-"
                if len(dest) > 35:
                    dest = "..." + dest[-32:]
                dpg.add_text(dest)

                # Size
                dpg.add_text(format_size(entry.file_size))

                # Status
                if entry.reversed:
                    dpg.add_text("Undone", color=get_text_color("disabled"))
                else:
                    dpg.add_text("Active", color=get_status_color("success"))

                # Undo button
                if entry.reversible and not entry.reversed:
                    dpg.add_button(
                        label="Undo",
                        small=True,
                        callback=lambda s, a, u: self._on_undo_single(u),
                        user_data=entry_id,
                    )
                else:
                    dpg.add_text("-")

    def _get_action_color(self, action_type: ActionType) -> tuple[int, int, int]:
        """Get display color for action type."""
        colors = {
            ActionType.DELETE: (255, 100, 100),
            ActionType.QUARANTINE: (255, 200, 100),
            ActionType.TRASH: (255, 150, 100),
            ActionType.MOVE: (100, 200, 255),
            ActionType.COPY: (100, 255, 200),
            ActionType.LINK: (200, 150, 255),
            ActionType.RESTORE: (100, 255, 100),
        }
        return colors.get(action_type, (200, 200, 200))

    def _toggle_selection(self, entry_id: int) -> None:
        """Toggle selection of an entry."""
        if entry_id in self._selected_ids:
            self._selected_ids.remove(entry_id)
        else:
            self._selected_ids.add(entry_id)

    def _update_pagination(self) -> None:
        """Update pagination controls."""
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        current = self._current_page + 1

        dpg.set_value("page_info_text", f"Page {current} of {total_pages}")

        # Calculate showing range
        start_idx = self._current_page * self._page_size + 1
        end_idx = min(start_idx + len(self._entries) - 1, self._total_count)
        if end_idx >= start_idx:
            dpg.set_value("showing_count_text", f"Showing {start_idx:,}-{end_idx:,} of {self._total_count:,}")
        else:
            dpg.set_value("showing_count_text", "No entries")

        # Enable/disable buttons
        dpg.configure_item("btn_first_page", enabled=self._current_page > 0)
        dpg.configure_item("btn_prev_page", enabled=self._current_page > 0)
        dpg.configure_item("btn_next_page", enabled=current < total_pages)
        dpg.configure_item("btn_last_page", enabled=current < total_pages)

    def _on_first_page(self) -> None:
        """Go to first page."""
        self._current_page = 0
        self._refresh_log()

    def _on_prev_page(self) -> None:
        """Go to previous page."""
        if self._current_page > 0:
            self._current_page -= 1
            self._refresh_log()

    def _on_next_page(self) -> None:
        """Go to next page."""
        total_pages = (self._total_count + self._page_size - 1) // self._page_size
        if self._current_page < total_pages - 1:
            self._current_page += 1
            self._refresh_log()

    def _on_last_page(self) -> None:
        """Go to last page."""
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        self._current_page = total_pages - 1
        self._refresh_log()

    def _update_quarantine_stats(self) -> None:
        """Update quarantine folder statistics."""
        if not self.action_engine:
            dpg.set_value("quarantine_stats_text", "Action engine not configured")
            return

        try:
            stats = self.action_engine.get_quarantine_stats()
            text = (
                f"Files: {stats['total_files']:,} | "
                f"Size: {format_size(stats['total_size'])} | "
                f"Location: {self.action_engine.quarantine_folder}"
            )
            dpg.set_value("quarantine_stats_text", text)
        except Exception as e:
            logger.error(f"Error getting quarantine stats: {e}")
            dpg.set_value("quarantine_stats_text", f"Error: {e}")

    def _on_undo_single(self, entry_id: int) -> None:
        """Undo a single action."""
        self._selected_ids = {entry_id}
        self._on_undo_selected()

    def _on_undo_selected(self) -> None:
        """Show undo confirmation for selected entries."""
        if not self._selected_ids:
            logger.warning("No entries selected for undo")
            return

        if not self.action_engine:
            logger.error("Action engine not configured")
            return

        # Get details of selected entries
        entries = []
        for entry_id in self._selected_ids:
            entry = self.db.get_action_log_by_id(entry_id)
            if entry and entry.reversible and not entry.reversed:
                entries.append(entry)

        if not entries:
            logger.warning("No reversible entries selected")
            return

        # Build details text
        details = []
        for entry in entries[:10]:  # Show first 10
            action_label = self.ACTION_LABELS.get(entry.action_type, str(entry.action_type.value))
            source = entry.source_path
            if len(source) > 50:
                source = "..." + source[-47:]
            details.append(f"- {action_label}: {source}")

        if len(entries) > 10:
            details.append(f"  ... and {len(entries) - 10} more")

        dpg.set_value("undo_dialog_text", f"Undo {len(entries)} action(s)?")
        dpg.set_value("undo_dialog_details", "\n".join(details))
        dpg.configure_item(self.TAG_UNDO_DIALOG, show=True)

    def _confirm_undo(self) -> None:
        """Execute undo for selected entries."""
        dpg.configure_item(self.TAG_UNDO_DIALOG, show=False)

        if not self.action_engine:
            return

        if self.on_status_update:
            self.on_status_update("Undoing actions...")

        results = self.action_engine.undo_batch(list(self._selected_ids))

        # Count results
        success = sum(1 for r in results if r.status == ActionStatus.SUCCESS)
        failed = sum(1 for r in results if r.status == ActionStatus.FAILED)

        logger.info(f"Undo complete: {success} successful, {failed} failed")
        if self.on_status_update:
            self.on_status_update(f"Undo complete: {success} OK, {failed} failed")

        # Callback
        if self.on_undo_complete:
            for result in results:
                self.on_undo_complete(result)

        # Refresh
        self._refresh_log()

    def _show_export_dialog(self) -> None:
        """Show export options dialog."""
        dpg.configure_item(self.TAG_EXPORT_DIALOG, show=True)

    def _do_export(self) -> None:
        """Execute export."""
        dpg.configure_item(self.TAG_EXPORT_DIALOG, show=False)

        format_selection = dpg.get_value("export_format")
        filtered_only = dpg.get_value("export_filtered")

        # Get entries
        if filtered_only:
            start_date, end_date = self._get_date_filter()
            entries = self.db.get_action_log(
                action_type=self._filter_type,
                start_date=start_date,
                end_date=end_date,
                reversed=self._filter_status,
                limit=100000,  # Large limit for export
            )
        else:
            entries = self.db.get_action_log(limit=100000)

        # Determine format and export
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")

        if "CSV" in format_selection:
            filepath = os.path.join(desktop, f"duplicleaner_log_{timestamp}.csv")
            self._export_csv(entries, filepath)
        elif "JSON" in format_selection:
            filepath = os.path.join(desktop, f"duplicleaner_log_{timestamp}.json")
            self._export_json(entries, filepath)
        else:  # HTML
            filepath = os.path.join(desktop, f"duplicleaner_log_{timestamp}.html")
            self._export_html(entries, filepath)

        logger.info(f"Exported {len(entries)} entries to {filepath}")

    def _export_csv(self, entries: list[ActionLogEntry], filepath: str) -> None:
        """Export entries to CSV."""
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Action", "Source Path", "Destination", "Size", "Hash", "Reversible", "Reversed"])
            for entry in entries:
                writer.writerow([
                    format_timestamp(entry.timestamp),
                    entry.action_type.value,
                    entry.source_path,
                    entry.dest_path or "",
                    entry.file_size or "",
                    entry.file_hash or "",
                    entry.reversible,
                    entry.reversed,
                ])

    def _export_json(self, entries: list[ActionLogEntry], filepath: str) -> None:
        """Export entries to JSON."""
        data = []
        for entry in entries:
            data.append({
                "id": entry.id,
                "timestamp": format_timestamp(entry.timestamp),
                "action_type": entry.action_type.value,
                "source_path": entry.source_path,
                "dest_path": entry.dest_path,
                "file_size": entry.file_size,
                "file_hash": entry.file_hash,
                "reversible": entry.reversible,
                "reversed": entry.reversed,
                "metadata": entry.metadata,
            })

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _export_html(self, entries: list[ActionLogEntry], filepath: str) -> None:
        """Export entries to HTML report."""
        html = [
            "<!DOCTYPE html>",
            "<html><head>",
            "<title>DupliCleaner Action Log</title>",
            "<style>",
            "body { font-family: Arial, sans-serif; margin: 20px; }",
            "h1 { color: #333; }",
            "table { border-collapse: collapse; width: 100%; }",
            "th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }",
            "th { background-color: #4CAF50; color: white; }",
            "tr:nth-child(even) { background-color: #f2f2f2; }",
            ".delete { color: #ff4444; }",
            ".quarantine { color: #ff9900; }",
            ".move { color: #4488ff; }",
            ".restore { color: #44ff44; }",
            "</style>",
            "</head><body>",
            "<h1>DupliCleaner Action Log</h1>",
            f"<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>",
            f"<p>Total entries: {len(entries)}</p>",
            "<table>",
            "<tr><th>Time</th><th>Action</th><th>Source</th><th>Destination</th><th>Size</th><th>Status</th></tr>",
        ]

        for entry in entries:
            action_class = entry.action_type.value.lower()
            status = "Undone" if entry.reversed else "Active"
            html.append(
                f"<tr>"
                f"<td>{format_timestamp(entry.timestamp)}</td>"
                f"<td class='{action_class}'>{entry.action_type.value.title()}</td>"
                f"<td>{entry.source_path}</td>"
                f"<td>{entry.dest_path or '-'}</td>"
                f"<td>{format_size(entry.file_size)}</td>"
                f"<td>{status}</td>"
                f"</tr>"
            )

        html.extend(["</table>", "</body></html>"])

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(html))

    def _show_quarantine_panel(self) -> None:
        """Show quarantine folder details."""
        if not self.action_engine:
            return

        self._refresh_quarantine_panel()
        dpg.configure_item(self.TAG_QUARANTINE_PANEL, show=True)

    def _on_browse_quarantine(self) -> None:
        """Open quarantine folder in file explorer."""
        if not self.action_engine:
            return

        folder = self.action_engine.quarantine_folder
        if os.path.exists(folder):
            os.startfile(folder)
        else:
            logger.warning(f"Quarantine folder does not exist: {folder}")

    def _on_restore_all_quarantine(self) -> None:
        """Restore all quarantined files."""
        # Get all quarantine actions that haven't been undone
        entries = self.db.get_action_log(
            action_type=ActionType.QUARANTINE,
            reversed=False,
            limit=100000,
        )

        if not entries:
            logger.info("No quarantined files to restore")
            return

        # Select all for undo
        self._selected_ids = {e.id for e in entries if e.id is not None}
        self._on_undo_selected()

    def _show_empty_quarantine_dialog(self) -> None:
        """Show confirmation dialog for emptying quarantine."""
        if not self.action_engine:
            return

        stats = self.action_engine.get_quarantine_stats()
        info_text = (
            f"Files to delete: {stats['total_files']:,}\n"
            f"Space to recover: {format_size(stats['total_size'])}"
        )
        dpg.set_value("empty_quarantine_info", info_text)
        dpg.set_value("confirm_delete_input", "")
        dpg.configure_item(self.TAG_EMPTY_QUARANTINE_DIALOG, show=True)

    def _confirm_empty_quarantine(self) -> None:
        """Execute empty quarantine if confirmed."""
        confirm_text = dpg.get_value("confirm_delete_input")
        if confirm_text != "DELETE":
            logger.warning("Empty quarantine not confirmed - wrong text")
            return

        dpg.configure_item(self.TAG_EMPTY_QUARANTINE_DIALOG, show=False)

        if self.action_engine:
            deleted = self.action_engine.empty_quarantine(confirm=True)
            logger.info(f"Emptied quarantine: {deleted} files deleted")
            self._update_quarantine_stats()

    def _on_clear_old(self) -> None:
        """Open clear-old-entries dialog."""
        dpg.set_value("clear_old_preview", "")
        dpg.configure_item(self.TAG_CLEAR_OLD_DIALOG, show=True)

    def _confirm_clear_old(self) -> None:
        """Delete old action log entries based on dialog selection."""
        age_value = dpg.get_value("clear_old_age")
        reversed_only = bool(dpg.get_value("clear_old_reversed_only"))
        days_map = {
            "30 days": 30,
            "90 days": 90,
            "180 days": 180,
            "365 days": 365,
        }
        days = days_map.get(age_value, 90)
        cutoff = datetime.now() - timedelta(days=days)

        deleted = self.db.delete_action_log_before(cutoff, only_reversed=reversed_only)
        dpg.configure_item(self.TAG_CLEAR_OLD_DIALOG, show=False)
        if self.on_status_update:
            scope = "undone entries" if reversed_only else "all entries"
            self.on_status_update(f"Deleted {deleted} {scope} older than {days} days.")
        self._refresh_log()

    def _refresh_quarantine_panel(self) -> None:
        """Populate the quarantine browser table."""
        if not dpg.does_item_exist(self.TAG_QUARANTINE_TABLE):
            return

        self._selected_ids.clear()

        # Clear existing rows
        for child in dpg.get_item_children(self.TAG_QUARANTINE_TABLE, 1):
            dpg.delete_item(child)

        entries = self.db.get_action_log(
            action_type=ActionType.QUARANTINE,
            reversed=False,
            limit=100000,
        )

        for entry in entries:
            if entry.id is None:
                continue
            with dpg.table_row(parent=self.TAG_QUARANTINE_TABLE):
                dpg.add_checkbox(
                    default_value=False,
                    callback=lambda s, a, u: self._toggle_selection(u),
                    user_data=entry.id,
                )
                dpg.add_text(format_timestamp(entry.timestamp))
                dpg.add_text(entry.source_path)
                dpg.add_text(entry.dest_path or "-")
                dpg.add_text(format_size(entry.file_size))
                if entry.reversible and not entry.reversed:
                    dpg.add_button(
                        label="Restore",
                        small=True,
                        callback=lambda s, a, u: self._on_undo_single(u),
                        user_data=entry.id,
                    )
                else:
                    dpg.add_text("-")

    def _restore_selected_quarantine(self) -> None:
        """Restore selected quarantine items using undo."""
        if not self._selected_ids:
            if self.on_status_update:
                self.on_status_update("Select one or more quarantine entries to restore.")
            return
        self._on_undo_selected()

    def refresh(self) -> None:
        """Public method to refresh the panel."""
        self._refresh_log()
