"""Duplicates Panel for DupliCleaner.

Dear PyGui UI component for reviewing and resolving duplicate files.
"""

import os
import subprocess
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import dearpygui.dearpygui as dpg

try:
    import numpy as np
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import contextlib

from duplicleaner.core.actions import ActionEngine, ActionStatus
from duplicleaner.core.comparator import Comparator
from duplicleaner.core.organizer import Organizer
from duplicleaner.core.resolver import ResolutionStrategy, Resolver, get_strategy_description
from duplicleaner.db.database import get_database
from duplicleaner.db.models import DuplicateGroup, GroupStatus, MatchType
from duplicleaner.ui.theme import get_accent_color, get_status_color, get_text_color
from duplicleaner.ui.tooltips import DUPLICATE_TOOLTIPS, add_tooltip
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class DuplicatesPanel:
    """UI panel for duplicate file review and resolution."""

    # Tag constants
    TAG_PANEL = "duplicates_panel"
    TAG_STATS = "dup_stats"
    TAG_GROUP_LIST = "dup_group_list"
    TAG_DETAILS_PANEL = "dup_details"
    TAG_STRATEGY_COMBO = "dup_strategy"
    TAG_STRATEGY_DRIVE = "dup_strategy_drive"
    TAG_PREVIEW_DIALOG = "dup_preview_dialog"
    TAG_COMPARISON_DIALOG = "dup_comparison_dialog"
    TAG_CONFIRM_DIALOG = "dup_confirm_dialog"
    TAG_CONFIRM_CONTENT = "dup_confirm_content"
    TAG_CONFIRM_ACTION_TYPE = "dup_confirm_action_type"
    TAG_STATUS_FILTER = "dup_status_filter"
    TAG_PREVIEW_BUTTON = "dup_preview_btn"
    TAG_APPLY_SELECTED_BUTTON = "dup_apply_selected_btn"
    TAG_APPLY_ALL_BUTTON = "dup_apply_all_btn"
    TAG_QUARANTINE_LINK = "dup_quarantine_link"
    TAG_GROUP_CONTEXT_MENU = "dup_group_context_menu"
    TAG_FILE_CONTEXT_MENU = "dup_file_context_menu"
    TAG_EXPORT_DIALOG = "dup_export_dialog"
    TAG_EXPORT_FORMAT = "dup_export_format"
    TAG_EXPORT_SCOPE = "dup_export_scope"

    # Image file extensions for preview
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic', '.heif'}

    # Thumbnail size for previews
    THUMBNAIL_SIZE = 150

    def __init__(
        self,
        parent: int | str,
        action_engine: ActionEngine | None = None,
        on_status_update: Callable[[str], None] | None = None,
    ):
        """Initialize the duplicates panel.

        Args:
            parent: Parent window/container tag
            action_engine: ActionEngine for file operations (quarantine, trash, delete)
            on_status_update: Callback for status updates
        """
        self.parent = parent
        self.action_engine = action_engine
        self.on_status_update = on_status_update

        self.db = get_database()
        self.resolver = Resolver()
        self.comparator = Comparator()

        # Pending action state for confirmation dialog
        self._pending_action_type: str | None = None  # "quarantine", "trash", or "delete"
        self._pending_file_ids: list[int] = []

        # Current state
        self._current_groups: list[DuplicateGroup] = []
        self._selected_group_id: int | None = None
        self._selected_group_ids: set[int] = set()
        self._group_checkbox_tags: dict[int, str] = {}
        self._group_active_tags: dict[int, str] = {}
        self._filter_type: MatchType | None = None
        self._filter_status: GroupStatus | None = GroupStatus.PENDING
        self._filter_drive: str | None = None
        self._filter_scope: str = "all"
        self._preferred_drive_id: str | None = None
        self._drive_label_map: dict[str, str] = {}

        # Texture cache for image previews {file_path: texture_tag}
        self._texture_cache: dict[str, str] = {}
        self._texture_counter = 0
        self._max_texture_cache_size = 100  # Limit cache to prevent memory issues

        # Thread tracking
        self._action_thread: threading.Thread | None = None
        self._detection_thread: threading.Thread | None = None
        self._operation_in_progress = False

        # Comparison dialog state
        self._comparison_keep_checks: dict[int, str] = {}  # file_id -> checkbox tag
        self._comparison_file_ids: list[int] = []  # all file IDs in current comparison
        self._comparison_group_id: int | None = None

        # Context menu state
        self._context_menu_shown = False
        self._context_menu_open_time = 0.0
        self._ctx_group_id: int | None = None
        self._ctx_file_path: str | None = None
        self._ctx_file_id: int | None = None
        self._group_row_handler_registries: list[int | str] = []
        self._file_detail_handler_registries: list[int | str] = []

        # Build UI
        self._build_ui()

    def _get_quarantine_folder(self) -> str:
        if self.action_engine and self.action_engine.quarantine_folder:
            return self.action_engine.quarantine_folder
        return os.path.join(os.path.expanduser("~"), "DupliCleaner_Quarantine")

    def _on_open_quarantine_folder(self) -> None:
        folder = self._get_quarantine_folder()
        if not os.path.exists(folder):
            if self.on_status_update:
                self.on_status_update(f"Quarantine folder not found: {folder}")
            return
        try:
            os.startfile(folder)
        except Exception as exc:
            logger.warning("Failed to open quarantine folder: %s", exc)
            if self.on_status_update:
                self.on_status_update("Failed to open quarantine folder.")

    def _build_ui(self) -> None:
        """Build the panel UI."""
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            # Header with stats
            dpg.add_text("Duplicate Files", color=get_accent_color())
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Statistics bar
            with dpg.group(horizontal=True, tag=self.TAG_STATS):
                dpg.add_text("Loading statistics...", tag="dup_stats_text")

            dpg.add_spacer(height=10)

            # Filter and action bar
            with dpg.group(horizontal=True):
                dpg.add_text("Filter:")
                filter_type = dpg.add_combo(
                    items=["All", "Exact Matches", "Near Duplicates"],
                    default_value="All",
                    width=150,
                    callback=self._on_filter_type_change,
                    tag="filter_type_combo"
                )
                add_tooltip(filter_type, DUPLICATE_TOOLTIPS["filter_type"])

                dpg.add_spacer(width=20)
                dpg.add_text("Status:")
                status_filter = dpg.add_combo(
                    items=["Pending", "Resolved", "Ignored", "All"],
                    default_value="Pending",
                    width=120,
                    callback=self._on_filter_status_change,
                    tag=self.TAG_STATUS_FILTER
                )
                add_tooltip(status_filter, DUPLICATE_TOOLTIPS["filter_status"])

                dpg.add_spacer(width=20)
                dpg.add_text("Scope:")
                scope_combo = dpg.add_combo(
                    items=["All Groups", "Cross-Drive Only", "Single-Drive Only"],
                    default_value="All Groups",
                    width=160,
                    callback=self._on_filter_scope_change,
                    tag="filter_scope_combo"
                )
                add_tooltip(scope_combo, DUPLICATE_TOOLTIPS["filter_scope"])

                dpg.add_spacer(width=20)
                dpg.add_text("Drive:")
                drive_combo = dpg.add_combo(
                    items=["All Drives"],
                    default_value="All Drives",
                    width=150,
                    callback=self._on_filter_drive_change,
                    tag="filter_drive_combo"
                )
                add_tooltip(drive_combo, DUPLICATE_TOOLTIPS["filter_drive"])

                dpg.add_spacer(width=20)
                refresh_btn = dpg.add_button(label="Refresh", callback=self._refresh_groups)
                add_tooltip(refresh_btn, DUPLICATE_TOOLTIPS["refresh"])
                find_btn = dpg.add_button(label="Find Duplicates", callback=self._on_find_duplicates)
                add_tooltip(find_btn, DUPLICATE_TOOLTIPS["find_duplicates"])

                dpg.add_spacer(width=20)
                select_all_btn = dpg.add_button(label="Select All", callback=self._select_all_groups)
                add_tooltip(select_all_btn, DUPLICATE_TOOLTIPS["select_all"])
                select_none_btn = dpg.add_button(label="Select None", callback=self._deselect_all_groups)
                add_tooltip(select_none_btn, DUPLICATE_TOOLTIPS["select_none"])
                unignore_btn = dpg.add_button(label="Unignore Selected", callback=self._on_unignore_selected)
                add_tooltip(unignore_btn, DUPLICATE_TOOLTIPS["unignore_selected"])
                dpg.add_spacer(width=20)
                export_btn = dpg.add_button(label="Export", callback=self._show_export_dialog)
                add_tooltip(export_btn, "Export duplicate groups to CSV, JSON, or HTML.")

            dpg.add_spacer(height=10)

            # Main content area - split into list and details
            with dpg.group(horizontal=True):
                # Left side - group list
                with dpg.child_window(width=600, height=400, border=True):
                    dpg.add_text("Duplicate Groups", color=get_text_color("secondary"))
                    dpg.add_separator()

                    # Table for groups
                    with dpg.table(
                        tag=self.TAG_GROUP_LIST,
                        header_row=True,
                        borders_innerH=True,
                        borders_outerH=True,
                        borders_innerV=True,
                        borders_outerV=True,
                        resizable=True,
                        policy=dpg.mvTable_SizingStretchProp,
                        row_background=True,
                        scrollY=True,
                        height=350,
                    ):
                        dpg.add_table_column(label="Select", width_fixed=True, init_width_or_weight=55)
                        dpg.add_table_column(label="Active", width_fixed=True, init_width_or_weight=50)
                        dpg.add_table_column(label="Type", width_fixed=True, init_width_or_weight=60)
                        dpg.add_table_column(label="Files", width_fixed=True, init_width_or_weight=50)
                        dpg.add_table_column(label="Sample Name", init_width_or_weight=200)
                        dpg.add_table_column(label="Wasted", width_fixed=True, init_width_or_weight=80)
                        dpg.add_table_column(label="Status", width_fixed=True, init_width_or_weight=80)

                # Right side - group details
                with dpg.child_window(width=-1, height=400, border=True, tag=self.TAG_DETAILS_PANEL):
                    dpg.add_text("Select a group to view details", tag="details_placeholder")

            dpg.add_spacer(height=10)

            # Resolution controls
            dpg.add_separator()
            dpg.add_text("Resolution", color=get_accent_color())
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_text("Strategy:")
                strategy_combo = dpg.add_combo(
                    items=[
                        "Keep Newest",
                        "Keep Oldest",
                        "Keep Largest",
                        "Keep Best Quality",
                        "Keep Best Format",
                        "Keep Shortest Path",
                        "Keep on Drive...",
                        "Manual",
                    ],
                    default_value="Keep Largest",
                    width=200,
                    tag=self.TAG_STRATEGY_COMBO,
                    callback=self._on_strategy_change,
                )
                add_tooltip(strategy_combo, DUPLICATE_TOOLTIPS["strategy"])

                dpg.add_spacer(width=10)
                dpg.add_text("Drive:")
                strategy_drive = dpg.add_combo(
                    items=["Select Drive"],
                    default_value="Select Drive",
                    width=180,
                    tag=self.TAG_STRATEGY_DRIVE,
                    callback=self._on_strategy_drive_change,
                )
                add_tooltip(strategy_drive, DUPLICATE_TOOLTIPS["strategy_drive"])

                dpg.add_spacer(width=20)
                preview_btn = dpg.add_button(
                    label="Preview",
                    callback=self._on_preview_resolution,
                    tag=self.TAG_PREVIEW_BUTTON,
                )
                add_tooltip(preview_btn, DUPLICATE_TOOLTIPS["preview"])
                apply_selected_btn = dpg.add_button(
                    label="Set Keepers (Selected)",
                    callback=self._on_apply_to_selected,
                    tag=self.TAG_APPLY_SELECTED_BUTTON,
                )
                add_tooltip(apply_selected_btn, DUPLICATE_TOOLTIPS["apply_selected"])
                apply_all_btn = dpg.add_button(
                    label="Set Keepers (All Pending)",
                    callback=self._on_apply_to_all,
                    tag=self.TAG_APPLY_ALL_BUTTON,
                )
                add_tooltip(apply_all_btn, DUPLICATE_TOOLTIPS["apply_all"])

            dpg.add_spacer(height=10)

            # Action buttons for selected files - with clear labels
            dpg.add_text(
                "Actions (removes non-keeper files from selected groups):",
                color=get_text_color("secondary")
            )
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                quarantine_btn = dpg.add_button(
                    label="Quarantine",
                    callback=self._on_quarantine_selected,
                    tag="btn_quarantine"
                )
                add_tooltip(quarantine_btn, DUPLICATE_TOOLTIPS["quarantine"])
                dpg.add_text("(Recommended)", color=get_status_color("success"))
                dpg.add_spacer(width=10)
                trash_btn = dpg.add_button(
                    label="Send to Trash",
                    callback=self._on_trash_selected,
                    tag="btn_trash"
                )
                add_tooltip(trash_btn, DUPLICATE_TOOLTIPS["trash"])
                dpg.add_spacer(width=10)
                delete_btn = dpg.add_button(
                    label="Delete Permanently",
                    callback=self._on_delete_selected,
                    tag="btn_delete"
                )
                add_tooltip(delete_btn, DUPLICATE_TOOLTIPS["delete"])
                dpg.add_spacer(width=20)
                ignore_btn = dpg.add_button(label="Ignore Group", callback=self._on_ignore_group)
                add_tooltip(ignore_btn, DUPLICATE_TOOLTIPS["ignore_group"])
                clear_btn = dpg.add_button(label="Clear Selections", callback=self._on_clear_selections)
                add_tooltip(clear_btn, DUPLICATE_TOOLTIPS["clear_selections"])
                dpg.add_spacer(width=20)
                undo_btn = dpg.add_button(label="Undo Last", callback=self._on_undo_last)
                add_tooltip(undo_btn, ("Undo the most recent quarantine/trash/delete action.",))

            # Help text for actions
            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Quarantine folder:", color=get_text_color("disabled"))
                quarantine_path = self._get_quarantine_folder()
                link = dpg.add_button(
                    label=quarantine_path,
                    tag=self.TAG_QUARANTINE_LINK,
                    callback=self._on_open_quarantine_folder,
                )
                add_tooltip(link, "Open the quarantine folder in Explorer.")
            dpg.add_text(
                "Quarantine is recoverable. Trash sends to Recycle Bin. Delete is permanent.",
                color=get_text_color("disabled"),
                wrap=700,
            )

        # Create dialogs
        self._create_preview_dialog()
        self._create_comparison_dialog()
        self._create_confirm_dialog()
        self._create_export_dialog()

        # Context menus
        self._create_context_menus()

        # Initial refresh
        self._refresh_groups()
        self._update_stats()
        self._populate_drive_filter()
        self._on_strategy_change(None, None, None)

    def _center_dialog(self, dialog_tag: str, width: int, height: int) -> None:
        """Center a dialog on the main viewport."""
        try:
            viewport_width = dpg.get_viewport_width()
            viewport_height = dpg.get_viewport_height()
            x = (viewport_width - width) // 2
            y = (viewport_height - height) // 2
            dpg.set_item_pos(dialog_tag, [max(0, x), max(0, y)])
        except Exception:
            pass  # Ignore positioning errors

    def _create_preview_dialog(self) -> None:
        """Create the resolution preview dialog."""
        with dpg.window(
            tag=self.TAG_PREVIEW_DIALOG,
            label="Resolution Preview",
            modal=True,
            show=False,
            width=600,
            height=400,
            no_resize=True,
            no_move=False,
        ):
            dpg.add_text("Resolution Preview", color=get_accent_color())
            dpg.add_separator()
            dpg.add_spacer(height=10)

            dpg.add_text("", tag="preview_summary")
            dpg.add_spacer(height=10)

            with dpg.child_window(height=250, border=True, tag="preview_details"):
                dpg.add_text("Loading preview...")

            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Confirm", callback=self._on_confirm_preview, width=100)
                dpg.add_button(label="Cancel", callback=self._on_cancel_preview, width=100)

    def _create_comparison_dialog(self) -> None:
        """Create the side-by-side image comparison dialog."""
        with dpg.window(
            tag=self.TAG_COMPARISON_DIALOG,
            label="Compare Duplicates",
            modal=True,
            show=False,
            width=950,
            height=750,
            no_resize=False,
            no_move=False,
        ):
            dpg.add_text("Side-by-Side Comparison", color=get_accent_color())
            dpg.add_text(
                "Check the files you want to KEEP, then use the action buttons below.",
                color=get_text_color("secondary"),
                tag="comparison_hint"
            )
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Container for images - will be populated dynamically
            with dpg.child_window(
                height=-80,
                border=True,
                tag="comparison_content",
                horizontal_scrollbar=True
            ):
                dpg.add_text("Loading comparison...")

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True, tag="comparison_actions"):
                dpg.add_button(
                    label="Quarantine Unchecked",
                    callback=lambda: self._comparison_action("quarantine"),
                    width=150,
                    tag="comparison_btn_quarantine"
                )
                dpg.add_button(
                    label="Trash Unchecked",
                    callback=lambda: self._comparison_action("trash"),
                    width=120,
                    tag="comparison_btn_trash"
                )
                dpg.add_button(
                    label="Delete Unchecked",
                    callback=lambda: self._comparison_action("delete"),
                    width=120,
                    tag="comparison_btn_delete"
                )
                dpg.add_spacer(width=20)
                dpg.add_button(
                    label="Close",
                    callback=lambda: dpg.hide_item(self.TAG_COMPARISON_DIALOG),
                    width=80
                )

    def _create_confirm_dialog(self) -> None:
        """Create the action confirmation dialog."""
        with dpg.window(
            tag=self.TAG_CONFIRM_DIALOG,
            label="Confirm Action",
            modal=True,
            show=False,
            width=550,
            height=350,
            no_resize=True,
            no_move=False,
        ):
            dpg.add_text("Confirm Action", color=get_accent_color())
            dpg.add_separator()
            dpg.add_spacer(height=10)

            # Action type indicator
            dpg.add_text("", tag=self.TAG_CONFIRM_ACTION_TYPE)
            dpg.add_spacer(height=10)

            # Content area showing files to be affected
            with dpg.child_window(height=200, border=True, tag=self.TAG_CONFIRM_CONTENT):
                dpg.add_text("Loading...")

            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Confirm",
                    callback=self._on_confirm_action,
                    width=100,
                    tag="confirm_action_btn"
                )
                dpg.add_button(
                    label="Cancel",
                    callback=self._on_cancel_action,
                    width=100
                )

    def _show_confirm_dialog(self, action_type: str, file_ids: list[int]) -> None:
        """Show confirmation dialog for an action.

        Args:
            action_type: "quarantine", "trash", or "delete"
            file_ids: List of file IDs to act on
        """
        self._pending_action_type = action_type
        self._pending_file_ids = file_ids

        # Get file info for display
        files = []
        total_size = 0
        for file_id in file_ids:
            file = self.db.get_file(file_id)
            if file:
                files.append(file)
                total_size += file.size

        # Clear content
        children = dpg.get_item_children(self.TAG_CONFIRM_CONTENT, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        # Set action type text with appropriate color
        action_colors = {
            "quarantine": (100, 200, 100),  # Green - safest
            "trash": (200, 200, 100),  # Yellow - reversible
            "delete": (255, 100, 100),  # Red - permanent
        }
        action_labels = {
            "quarantine": "QUARANTINE - Move to ~/DupliCleaner_Quarantine (recoverable)",
            "trash": "SEND TO TRASH - Move to Recycle Bin (can restore)",
            "delete": "DELETE PERMANENTLY - Cannot be undone!",
        }

        dpg.set_value(self.TAG_CONFIRM_ACTION_TYPE, action_labels.get(action_type, action_type))
        dpg.configure_item(
            self.TAG_CONFIRM_ACTION_TYPE,
            color=action_colors.get(action_type, (200, 200, 200))
        )

        # Add file list
        size_mb = total_size / (1024 * 1024)
        dpg.add_text(
            f"Files to remove: {len(files)} ({size_mb:.1f} MB)",
            parent=self.TAG_CONFIRM_CONTENT
        )
        dpg.add_spacer(height=5, parent=self.TAG_CONFIRM_CONTENT)

        for file in files[:10]:  # Show first 10
            size_kb = file.size / 1024
            size_str = f"{size_kb / 1024:.1f} MB" if size_kb >= 1024 else f"{size_kb:.0f} KB"
            dpg.add_text(
                f"  {file.filename} ({size_str})",
                parent=self.TAG_CONFIRM_CONTENT,
                color=get_text_color("secondary")
            )

        if len(files) > 10:
            dpg.add_text(
                f"  ... and {len(files) - 10} more files",
                parent=self.TAG_CONFIRM_CONTENT,
                color=get_text_color("disabled")
            )

        # Warn about Live Photo orphaning
        live_photo_warnings = []
        for file in files:
            info = self._get_live_photo_info(file.path)
            if info and "Live Photo" in info:
                live_photo_warnings.append(file.filename)
        if live_photo_warnings:
            dpg.add_spacer(height=5, parent=self.TAG_CONFIRM_CONTENT)
            dpg.add_text(
                f"Warning: {len(live_photo_warnings)} file(s) are part of Live Photo pairs. "
                "Removing them may orphan their paired photo/video.",
                parent=self.TAG_CONFIRM_CONTENT,
                color=(255, 200, 100),
                wrap=500,
            )

        # Update confirm button color based on action
        if action_type == "delete":
            # Make delete button red
            dpg.configure_item("confirm_action_btn", label="Delete Permanently")
        else:
            dpg.configure_item("confirm_action_btn", label="Confirm")

        dpg.show_item(self.TAG_CONFIRM_DIALOG)
        self._center_dialog(self.TAG_CONFIRM_DIALOG, 550, 350)

    def _on_confirm_action(self) -> None:
        """Handle confirmation of the action."""
        dpg.hide_item(self.TAG_CONFIRM_DIALOG)

        if self._operation_in_progress:
            if self.on_status_update:
                self.on_status_update("An operation is already in progress.")
            return

        if not self.action_engine:
            logger.error("No ActionEngine available")
            if self.on_status_update:
                self.on_status_update("Error: Action engine not initialized")
            return

        if not self._pending_file_ids:
            return

        action_type = self._pending_action_type
        file_ids = self._pending_file_ids

        # Clear pending state
        self._pending_action_type = None
        self._pending_file_ids = []

        self._operation_in_progress = True
        self._set_buttons_enabled(False)

        # Execute actions in background thread
        def execute_actions():
            success_count = 0
            fail_count = 0

            try:
                for file_id in file_ids:
                    file = self.db.get_file(file_id)
                    if not file:
                        fail_count += 1
                        continue

                    try:
                        if action_type == "quarantine":
                            result = self.action_engine.quarantine(file.path)
                        elif action_type == "trash":
                            result = self.action_engine.send_to_trash(file.path)
                        elif action_type == "delete":
                            result = self.action_engine.delete_permanently(file.path, confirm=True)
                        else:
                            logger.error(f"Unknown action type: {action_type}")
                            fail_count += 1
                            continue

                        if result.status == ActionStatus.SUCCESS:
                            success_count += 1
                            # Mark file as removed in database
                            self.db.mark_file_deleted(file_id)
                        else:
                            fail_count += 1
                            logger.error(f"Action failed for {file.path}: {result.error_message}")

                    except Exception as e:
                        fail_count += 1
                        logger.error(f"Error processing {file.path}: {e}")

                # Update UI
                if self.on_status_update:
                    action_label = {"quarantine": "quarantined", "trash": "sent to trash", "delete": "deleted"}
                    self.on_status_update(
                        f"{action_label.get(action_type, 'processed')} {success_count} files"
                        + (f", {fail_count} failed" if fail_count > 0 else "")
                    )

                # Refresh the groups list
                self._refresh_groups()
                self._update_stats()
            finally:
                self._operation_in_progress = False
                self._set_buttons_enabled(True)

        self._action_thread = threading.Thread(target=execute_actions, daemon=True)
        self._action_thread.start()

    def _on_cancel_action(self) -> None:
        """Handle cancellation of the action."""
        dpg.hide_item(self.TAG_CONFIRM_DIALOG)
        self._pending_action_type = None
        self._pending_file_ids = []

    def _show_comparison_dialog(self, group_id: int) -> None:
        """Show the comparison dialog for a duplicate group.

        Supports any number of files in a grid layout (3 columns).
        Each file has a checkbox to mark it as a keeper.
        """
        # Clear existing content
        children = dpg.get_item_children("comparison_content", slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        # Reset comparison state
        self._comparison_keep_checks = {}
        self._comparison_file_ids = []
        self._comparison_group_id = group_id

        group = self.db.get_duplicate_group(group_id, include_files=True)
        if not group:
            dpg.add_text("Group not found", parent="comparison_content")
            dpg.show_item(self.TAG_COMPARISON_DIALOG)
            self._center_dialog(self.TAG_COMPARISON_DIALOG, 950, 750)
            return

        # Get comparable files (images and videos)
        image_files = [
            member.file for member in group.members
            if member.file and (self._is_image_file(member.file.path) or self._is_video_file(member.file.path))
        ]

        if not image_files:
            dpg.add_text("No images or videos to compare", parent="comparison_content")
            dpg.show_item(self.TAG_COMPARISON_DIALOG)
            self._center_dialog(self.TAG_COMPARISON_DIALOG, 950, 750)
            return

        # Store file IDs for action
        self._comparison_file_ids = [f.id for f in image_files]

        # Determine grid columns based on file count
        n_files = len(image_files)
        if n_files <= 2:
            n_cols = n_files
            thumb_size = 300
        elif n_files <= 4:
            n_cols = 2
            thumb_size = 280
        elif n_files <= 9:
            n_cols = 3
            thumb_size = 240
        else:
            n_cols = 4
            thumb_size = 200

        # Find best quality file for default selection
        best_file_id = None
        best_score = -1
        for file in image_files:
            analysis = self.db.get_scene_analysis(file.id)
            if analysis and analysis.quality_score is not None and analysis.quality_score > best_score:
                best_score = analysis.quality_score
                best_file_id = file.id

        # Render grid rows
        for row_start in range(0, n_files, n_cols):
            row_files = image_files[row_start:row_start + n_cols]
            with dpg.group(horizontal=True, parent="comparison_content"):
                for file in row_files:
                    with dpg.child_window(width=thumb_size + 30, border=True, height=-1, autosize_y=True):
                        # Keep checkbox
                        cb_tag = f"cmp_keep_{file.id}"
                        is_best = (file.id == best_file_id)
                        dpg.add_checkbox(
                            label="KEEP" + (" (Best)" if is_best else ""),
                            tag=cb_tag,
                            default_value=is_best,
                        )
                        self._comparison_keep_checks[file.id] = cb_tag

                        # Thumbnail or video info
                        if self._is_image_file(file.path):
                            texture_tag = self._load_image_texture(file.path, size=thumb_size)
                            if texture_tag:
                                dpg.add_image(texture_tag)
                            else:
                                dpg.add_text("[Preview unavailable]", color=get_text_color("disabled"))
                        elif self._is_video_file(file.path):
                            dpg.add_text("[VIDEO]", color=get_accent_color())
                            vid_meta = self.db.get_file_metadata(file.id)
                            if vid_meta:
                                if vid_meta.duration_seconds:
                                    mins = int(vid_meta.duration_seconds // 60)
                                    secs = int(vid_meta.duration_seconds % 60)
                                    dpg.add_text(f"Duration: {mins}:{secs:02d}", color=get_text_color("secondary"))
                                if vid_meta.width and vid_meta.height:
                                    dpg.add_text(f"{vid_meta.width}x{vid_meta.height}", color=get_text_color("secondary"))

                        dpg.add_spacer(height=3)

                        # Filename
                        dpg.add_text(file.filename, wrap=thumb_size)

                        # Size
                        size_kb = file.size / 1024
                        if size_kb >= 1024:
                            size_str = f"{size_kb / 1024:.1f} MB"
                        else:
                            size_str = f"{size_kb:.0f} KB"
                        dpg.add_text(f"Size: {size_str}", color=get_text_color("secondary"))

                        # Dimensions
                        dims = self._get_image_dimensions(file.path)
                        if dims:
                            dpg.add_text(f"{dims[0]} x {dims[1]}", color=get_text_color("secondary"))

                        # Modified date
                        if file.modified:
                            dpg.add_text(
                                file.modified.strftime('%Y-%m-%d'),
                                color=get_text_color("secondary")
                            )

                        # EXIF metadata
                        metadata = self.db.get_file_metadata(file.id)
                        if metadata:
                            if metadata.camera_make or metadata.camera_model:
                                camera = " ".join(filter(None, [metadata.camera_make, metadata.camera_model]))
                                dpg.add_text(f"Camera: {camera}", color=get_text_color("disabled"), wrap=thumb_size)
                            if metadata.exif_date:
                                dpg.add_text(f"Taken: {metadata.exif_date.strftime('%Y-%m-%d %H:%M')}", color=get_text_color("disabled"))
                            if metadata.location_name:
                                dpg.add_text(f"Location: {metadata.location_name}", color=get_text_color("disabled"), wrap=thumb_size)

                        # Quality scores
                        analysis = self.db.get_scene_analysis(file.id)
                        if analysis and analysis.quality_score is not None:
                            score = analysis.quality_score
                            q_color = get_status_color("success") if score >= 80 else get_status_color("warning") if score >= 50 else get_status_color("error")
                            parts = [f"Quality: {score:.0f}"]
                            if analysis.blur_score is not None:
                                parts.append(f"Blur: {analysis.blur_score:.0f}")
                            if analysis.exposure_score is not None:
                                parts.append(f"Exp: {analysis.exposure_score:.0f}")
                            dpg.add_text(" | ".join(parts), color=q_color)

                        # Action buttons
                        dpg.add_spacer(height=3)
                        with dpg.group(horizontal=True):
                            dpg.add_button(
                                label="Open",
                                callback=lambda s, a, u: self._open_file(u),
                                user_data=file.path,
                                width=50
                            )
                            dpg.add_button(
                                label="Explorer",
                                callback=lambda s, a, u: self._open_in_explorer(u),
                                user_data=file.path,
                                width=60
                            )

        # Show dialog
        dpg.show_item(self.TAG_COMPARISON_DIALOG)
        self._center_dialog(self.TAG_COMPARISON_DIALOG, 950, 750)

    def _comparison_action(self, action_type: str) -> None:
        """Execute action on unchecked files in the comparison dialog.

        Files with the KEEP checkbox checked are kept; all others are acted on.
        """
        if not self._comparison_file_ids:
            return

        # Collect unchecked file IDs
        unchecked_ids = []
        kept_count = 0
        for file_id, cb_tag in self._comparison_keep_checks.items():
            try:
                if dpg.get_value(cb_tag):
                    kept_count += 1
                else:
                    unchecked_ids.append(file_id)
            except Exception:
                pass

        if not unchecked_ids:
            if self.on_status_update:
                self.on_status_update("No files to remove - all are checked as KEEP")
            return

        if kept_count == 0:
            if self.on_status_update:
                self.on_status_update("You must keep at least one file")
            return

        # Hide comparison, show confirmation
        dpg.hide_item(self.TAG_COMPARISON_DIALOG)
        self._show_confirm_dialog(action_type, unchecked_ids)

    def _update_stats(self) -> None:
        """Update the statistics display."""
        stats = self.db.get_statistics()
        counts = self.db.get_duplicate_group_counts()

        pending_groups = counts.get(GroupStatus.PENDING, 0)
        resolved_groups = counts.get(GroupStatus.RESOLVED, 0)
        ignored_groups = counts.get(GroupStatus.IGNORED, 0)
        wasted_space = stats.get("wasted_space", 0)
        wasted_gb = wasted_space / (1024 ** 3)

        text = (
            f"Pending: {pending_groups:,} | Resolved: {resolved_groups:,} | "
            f"Ignored: {ignored_groups:,} | Potential Space Savings: {wasted_gb:.1f} GB"
        )

        dpg.set_value("dup_stats_text", text)

    def _populate_drive_filter(self) -> None:
        """Populate the drive filter combo box."""
        drives = self.db.get_all_drives()
        self._drive_label_map = {d.label: d.id for d in drives}
        filter_items = ["All Drives"] + [d.label for d in drives]
        dpg.configure_item("filter_drive_combo", items=filter_items)

        strategy_items = ["Select Drive"] + [d.label for d in drives]
        dpg.configure_item(self.TAG_STRATEGY_DRIVE, items=strategy_items)
        if self._preferred_drive_id:
            selected_label = next(
                (label for label, drive_id in self._drive_label_map.items()
                 if drive_id == self._preferred_drive_id),
                None
            )
            if selected_label:
                dpg.set_value(self.TAG_STRATEGY_DRIVE, selected_label)
            else:
                self._preferred_drive_id = None
                dpg.set_value(self.TAG_STRATEGY_DRIVE, "Select Drive")
        else:
            dpg.set_value(self.TAG_STRATEGY_DRIVE, "Select Drive")

    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp'}

    def _is_image_file(self, file_path: str) -> bool:
        """Check if a file is an image (or PDF) based on extension."""
        ext = Path(file_path).suffix.lower()
        return ext in self.IMAGE_EXTENSIONS or ext == '.pdf'

    def _is_video_file(self, file_path: str) -> bool:
        """Check if a file is a video based on extension."""
        ext = Path(file_path).suffix.lower()
        return ext in self.VIDEO_EXTENSIONS

    def _load_image_texture(self, file_path: str, size: int = None) -> str | None:
        """Load an image file as a Dear PyGui texture.

        Args:
            file_path: Path to the image file
            size: Thumbnail size (uses THUMBNAIL_SIZE if not specified)

        Returns:
            Texture tag or None if failed
        """
        if not HAS_PIL:
            return None

        if not os.path.exists(file_path):
            return None

        # Check cache
        cache_key = f"{file_path}_{size or self.THUMBNAIL_SIZE}"
        if cache_key in self._texture_cache:
            return self._texture_cache[cache_key]

        # Evict oldest entries if cache is full
        if len(self._texture_cache) >= self._max_texture_cache_size:
            # Remove oldest quarter of the cache
            keys_to_remove = list(self._texture_cache.keys())[:self._max_texture_cache_size // 4]
            for key in keys_to_remove:
                old_tag = self._texture_cache.pop(key, None)
                if old_tag and dpg.does_item_exist(old_tag):
                    with contextlib.suppress(Exception):
                        dpg.delete_item(old_tag)

        try:
            size = size or self.THUMBNAIL_SIZE

            # Load and resize image
            if file_path.lower().endswith('.pdf'):
                from duplicleaner.ui.files_panel import _render_pdf_page
                img = _render_pdf_page(file_path, page_num=0)
                if img is None:
                    return None
            else:
                img = Image.open(file_path)
                img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)

            # Convert to RGBA
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # Get dimensions
            width, height = img.size

            # Convert to numpy array and normalize to 0-1 float
            data = np.array(img).astype(np.float32) / 255.0
            data = data.flatten().tolist()

            # Create unique texture tag
            self._texture_counter += 1
            texture_tag = f"dup_texture_{self._texture_counter}"

            # Create texture registry if needed
            if not dpg.does_item_exist("dup_texture_registry"):
                dpg.add_texture_registry(tag="dup_texture_registry")

            # Add static texture
            dpg.add_static_texture(
                width=width,
                height=height,
                default_value=data,
                tag=texture_tag,
                parent="dup_texture_registry"
            )

            self._texture_cache[cache_key] = texture_tag
            return texture_tag

        except Exception as e:
            logger.debug(f"Failed to load image texture for {file_path}: {e}")
            return None

    def _open_in_explorer(self, file_path: str) -> None:
        """Open Windows Explorer with the file selected."""
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            if self.on_status_update:
                self.on_status_update(f"File not found: {os.path.basename(file_path)}")
            return

        try:
            # Use explorer /select to highlight the file
            subprocess.run(['explorer', '/select,', file_path], check=False)
        except Exception as e:
            logger.error(f"Failed to open Explorer: {e}")
            if self.on_status_update:
                self.on_status_update("Failed to open file in Explorer.")

    def _open_file(self, file_path: str) -> None:
        """Open a file with its default application."""
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            if self.on_status_update:
                self.on_status_update(f"File not found: {os.path.basename(file_path)}")
            return

        try:
            os.startfile(file_path)
        except Exception as e:
            logger.error(f"Failed to open file: {e}")
            if self.on_status_update:
                self.on_status_update(f"Failed to open file: {os.path.basename(file_path)}")

    def _get_live_photo_info(self, file_path: str) -> str | None:
        """Check if a file is part of a Live Photo pair or is a Motion Photo.

        Returns a status string, or None if not a Live Photo.
        """
        p = Path(file_path)
        ext = p.suffix.lower()

        # Check for embedded Motion Photo (Samsung/Google)
        if ext in {'.jpg', '.jpeg'}:
            video_offset = Organizer.detect_motion_photo(file_path)
            if video_offset is not None:
                # Calculate embedded video size
                try:
                    file_size = p.stat().st_size
                    video_size = file_size - video_offset
                    size_mb = video_size / (1024 * 1024)
                    return f"Motion Photo (embedded {size_mb:.1f} MB video)"
                except Exception:
                    return "Motion Photo (embedded video)"

        # Check for Live Photo pair (matching image+video by stem)
        image_exts = {'.jpg', '.jpeg', '.heic', '.heif', '.png'}
        video_exts = {'.mov', '.mp4'}

        if ext in image_exts:
            # Look for matching video
            for vext in video_exts:
                partner = p.with_suffix(vext)
                if partner.exists():
                    try:
                        size_mb = partner.stat().st_size / (1024 * 1024)
                        return f"Live Photo (video: {partner.name}, {size_mb:.1f} MB)"
                    except Exception:
                        return f"Live Photo (video: {partner.name})"
        elif ext in video_exts:
            # Look for matching image
            for iext in image_exts:
                partner = p.with_suffix(iext)
                if partner.exists():
                    return f"Live Photo video (photo: {partner.name})"

        return None

    def _get_image_dimensions(self, file_path: str) -> tuple[int, int] | None:
        """Get image dimensions without loading the full image."""
        if not HAS_PIL:
            return None

        try:
            with Image.open(file_path) as img:
                img = ImageOps.exif_transpose(img)
                return img.size
        except Exception:
            return None

    def _refresh_groups(self) -> None:
        """Refresh the duplicate groups list."""
        # Clean up old handler registries
        for hr in self._group_row_handler_registries:
            try:
                if dpg.does_item_exist(hr):
                    dpg.delete_item(hr)
            except Exception:
                pass
        self._group_row_handler_registries.clear()

        # Clear existing rows
        children = dpg.get_item_children(self.TAG_GROUP_LIST, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        self._group_checkbox_tags.clear()
        self._group_active_tags.clear()

        # Get groups with filters
        match_type = self._filter_type
        status = self._filter_status

        groups = self.db.get_duplicate_groups(
            status=status,
            match_type=match_type,
            limit=500
        )

        if self._filter_scope != "all" or self._filter_drive:
            groups = self._apply_scope_filter(groups)

        self._current_groups = groups
        visible_group_ids = {group.id for group in groups if group.id is not None}
        self._selected_group_ids = {gid for gid in self._selected_group_ids if gid in visible_group_ids}

        if not groups:
            with dpg.table_row(parent=self.TAG_GROUP_LIST):
                dpg.add_text("")
                dpg.add_text("")
                dpg.add_text("No duplicates found.")
                dpg.add_text("")
                dpg.add_text("Scan drives and click 'Find Duplicates'")
                dpg.add_text("")
                dpg.add_text("")
            return

        # Add rows
        for group in groups:
            # Load full group data
            full_group = self.db.get_duplicate_group(group.id, include_files=True)
            if not full_group:
                continue

            # Get sample filename
            sample_name = "Unknown"
            if full_group.members and full_group.members[0].file:
                sample_name = full_group.members[0].file.filename

            # Format wasted space
            wasted_kb = group.wasted_size / 1024
            if wasted_kb >= 1024:
                wasted_str = f"{wasted_kb / 1024:.1f} MB"
            else:
                wasted_str = f"{wasted_kb:.0f} KB"

            # Type indicator
            type_str = "Exact" if group.match_type == MatchType.EXACT else f"~{int(group.similarity * 100)}%"

            # Status
            status_str = group.status.value.title()

            with dpg.table_row(parent=self.TAG_GROUP_LIST):
                checkbox_tag = f"dup_group_select_{group.id}"
                self._group_checkbox_tags[group.id] = checkbox_tag
                dpg.add_checkbox(
                    tag=checkbox_tag,
                    default_value=group.id in self._selected_group_ids,
                    callback=self._on_group_checkbox_toggled,
                    user_data=group.id,
                )
                active_tag = f"dup_group_active_{group.id}"
                self._group_active_tags[group.id] = active_tag
                dpg.add_text(
                    "*" if group.id == self._selected_group_id else "",
                    tag=active_tag,
                    color=get_status_color("success"),
                )
                type_sel = dpg.add_selectable(
                    label=type_str,
                    callback=lambda s, a, u: self._on_group_selected(u),
                    user_data=group.id,
                    span_columns=False,
                )
                with dpg.item_handler_registry() as hr:
                    dpg.add_item_clicked_handler(
                        button=dpg.mvMouseButton_Right,
                        callback=self._show_group_context_menu,
                        user_data=group.id,
                    )
                dpg.bind_item_handler_registry(type_sel, hr)
                self._group_row_handler_registries.append(hr)

                dpg.add_text(str(group.file_count))
                name_sel = dpg.add_selectable(
                    label=sample_name[:30] + "..." if len(sample_name) > 30 else sample_name,
                    callback=lambda s, a, u: self._on_group_selected(u),
                    user_data=group.id,
                    span_columns=False,
                )
                with dpg.item_handler_registry() as hr2:
                    dpg.add_item_clicked_handler(
                        button=dpg.mvMouseButton_Right,
                        callback=self._show_group_context_menu,
                        user_data=group.id,
                    )
                dpg.bind_item_handler_registry(name_sel, hr2)
                self._group_row_handler_registries.append(hr2)

                dpg.add_text(wasted_str)
                dpg.add_text(status_str)

        self._update_stats()

    def _on_group_selected(self, group_id: int) -> None:
        """Handle group selection."""
        previous_id = self._selected_group_id
        self._selected_group_id = group_id
        self._set_active_group_indicator(previous_id, False)
        self._set_active_group_indicator(group_id, True)
        self._show_group_details(group_id)

    def _set_active_group_indicator(self, group_id: int | None, is_active: bool) -> None:
        """Update active indicator for a group row."""
        if not group_id:
            return
        tag = self._group_active_tags.get(group_id)
        if tag and dpg.does_item_exist(tag):
            dpg.set_value(tag, "*" if is_active else "")

    def _show_group_details(self, group_id: int) -> None:
        """Show details for a selected group."""
        # Clean up old file detail handler registries
        for hr in self._file_detail_handler_registries:
            try:
                if dpg.does_item_exist(hr):
                    dpg.delete_item(hr)
            except Exception:
                pass
        self._file_detail_handler_registries.clear()

        # Clear existing details
        children = dpg.get_item_children(self.TAG_DETAILS_PANEL, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        group = self.db.get_duplicate_group(group_id, include_files=True)
        if not group:
            dpg.add_text("Group not found", parent=self.TAG_DETAILS_PANEL)
            return

        # Check if this is an image or video group
        is_image_group = any(
            member.file and self._is_image_file(member.file.path)
            for member in group.members
        )
        is_video_group = any(
            member.file and self._is_video_file(member.file.path)
            for member in group.members
        )

        # Header
        match_type = "Exact Match" if group.match_type == MatchType.EXACT else f"Near Match ({group.similarity:.0%})"
        dpg.add_text(f"Group #{group.id} - {match_type}", parent=self.TAG_DETAILS_PANEL, color=get_accent_color())
        dpg.add_text(f"Status: {group.status.value.title()}", parent=self.TAG_DETAILS_PANEL, color=get_text_color("secondary"))
        dpg.add_separator(parent=self.TAG_DETAILS_PANEL)
        dpg.add_spacer(height=5, parent=self.TAG_DETAILS_PANEL)

        if group.status == GroupStatus.IGNORED:
            dpg.add_text("This group is ignored and will not be processed.", parent=self.TAG_DETAILS_PANEL)
            dpg.add_button(
                label="Unignore Group",
                callback=lambda: self._on_unignore_group(group.id),
                parent=self.TAG_DETAILS_PANEL
            )
            dpg.add_spacer(height=5, parent=self.TAG_DETAILS_PANEL)

        # AI Recommendation
        recommendation = self.resolver.get_recommendation(group_id)
        if recommendation:
            keeper, reasons = recommendation
            dpg.add_text("Recommended: Keep", parent=self.TAG_DETAILS_PANEL, color=get_status_color("success"))
            dpg.add_text(f"  {keeper.filename}", parent=self.TAG_DETAILS_PANEL)
            for reason in reasons[:3]:
                dpg.add_text(f"    - {reason}", parent=self.TAG_DETAILS_PANEL, color=get_text_color("disabled"))
            dpg.add_spacer(height=5, parent=self.TAG_DETAILS_PANEL)

        # Compare button for image/video groups
        if (is_image_group or is_video_group) and len(group.members) >= 2:
            with dpg.group(horizontal=True, parent=self.TAG_DETAILS_PANEL):
                dpg.add_button(
                    label="Compare Side-by-Side",
                    callback=lambda: self._show_comparison_dialog(group_id),
                )
                dpg.add_spacer(width=10)
                dpg.add_button(
                    label="Keep Best Quality",
                    callback=lambda s, a, u: self._on_keep_best_quality(u),
                    user_data=group_id,
                )
                dpg.add_spacer(width=10)
                dpg.add_button(
                    label="Keep Best Format",
                    callback=lambda s, a, u: self._on_keep_best_format(u),
                    user_data=group_id,
                )
            dpg.add_spacer(height=5, parent=self.TAG_DETAILS_PANEL)

        # File list header
        dpg.add_text(f"Files ({group.file_count}):", parent=self.TAG_DETAILS_PANEL)
        dpg.add_text(
            "Select one keeper per group. Selecting a new keeper will replace the current one.",
            parent=self.TAG_DETAILS_PANEL,
            color=get_text_color("disabled"),
            wrap=500,
        )
        dpg.add_spacer(height=5, parent=self.TAG_DETAILS_PANEL)

        for member in group.members:
            if not member.file:
                continue

            file = member.file
            is_keeper = bool(member.is_keeper)

            # Container for this file entry
            with dpg.group(parent=self.TAG_DETAILS_PANEL):
                # Top row: checkbox, keeper indicator, and action buttons
                with dpg.group(horizontal=True):
                    # Checkbox for keeper selection
                    dpg.add_checkbox(
                        default_value=is_keeper,
                        callback=lambda s, a, u: self._on_keeper_toggled(u[0], u[1], a),
                        user_data=(group_id, file.id),
                        enabled=(group.status == GroupStatus.PENDING and not is_keeper),
                    )

                    # Keeper indicator
                    if is_keeper:
                        dpg.add_text("[KEEP]", color=get_status_color("success"))
                    else:
                        dpg.add_text("[    ]", color=get_text_color("disabled"))

                    # Filename (with right-click context menu)
                    fname_sel = dpg.add_selectable(
                        label=file.filename,
                        span_columns=False,
                    )
                    with dpg.item_handler_registry() as hr:
                        dpg.add_item_clicked_handler(
                            button=dpg.mvMouseButton_Right,
                            callback=self._show_file_context_menu,
                            user_data=(file.id, file.path),
                        )
                    dpg.bind_item_handler_registry(fname_sel, hr)
                    self._file_detail_handler_registries.append(hr)

                    dpg.add_spacer(width=10)

                    # Action buttons
                    dpg.add_button(
                        label="Open",
                        callback=lambda s, a, u: self._open_file(u),
                        user_data=file.path,
                        width=50
                    )
                    dpg.add_button(
                        label="Show in Explorer",
                        callback=lambda s, a, u: self._open_in_explorer(u),
                        user_data=file.path,
                        width=110
                    )

                # Image/video preview and details side by side
                with dpg.group(horizontal=True):
                    # Image preview (if applicable)
                    if self._is_image_file(file.path):
                        texture_tag = self._load_image_texture(file.path)
                        if texture_tag:
                            dpg.add_image(texture_tag)
                            dpg.add_spacer(width=10)

                    # File details column
                    with dpg.group():
                        # Size
                        size_kb = file.size / 1024
                        if size_kb >= 1024:
                            size_str = f"{size_kb / 1024:.1f} MB"
                        else:
                            size_str = f"{size_kb:.0f} KB"
                        dpg.add_text(f"Size: {size_str}", color=get_text_color("secondary"))

                        # Dimensions for images
                        if self._is_image_file(file.path):
                            dims = self._get_image_dimensions(file.path)
                            if dims:
                                dpg.add_text(f"Dimensions: {dims[0]} x {dims[1]}", color=get_text_color("secondary"))

                        # Video metadata
                        if self._is_video_file(file.path):
                            metadata = self.db.get_file_metadata(file.id)
                            if metadata:
                                if metadata.duration_seconds:
                                    mins = int(metadata.duration_seconds // 60)
                                    secs = int(metadata.duration_seconds % 60)
                                    dpg.add_text(f"Duration: {mins}:{secs:02d}", color=get_text_color("secondary"))
                                if metadata.width and metadata.height:
                                    dpg.add_text(f"Resolution: {metadata.width}x{metadata.height}", color=get_text_color("secondary"))

                        # Modified date
                        if file.modified:
                            dpg.add_text(f"Modified: {file.modified.strftime('%Y-%m-%d %H:%M')}", color=get_text_color("secondary"))

                        # Full path (with copy hint)
                        dpg.add_text(f"Path: {file.path}", color=get_text_color("disabled"), wrap=400)

                        # Quality score badge
                        analysis = self.db.get_scene_analysis(file.id)
                        if analysis and analysis.quality_score is not None:
                            score = analysis.quality_score
                            if score >= 80:
                                q_color = get_status_color("success")
                            elif score >= 50:
                                q_color = get_status_color("warning")
                            else:
                                q_color = get_status_color("error")
                            stars = int(round(score / 20))
                            star_str = "*" * stars + "-" * (5 - stars)
                            dpg.add_text(f"Quality: {score:.0f}/100 [{star_str}]", color=q_color)

                        # Format badge
                        fmt_label = Resolver.get_format_label(file.file_type)
                        if fmt_label:
                            ext = (file.file_type or "").upper().lstrip('.')
                            dpg.add_text(f"Format: {ext} ({fmt_label})", color=get_text_color("secondary"))

                        # Live Photo / Motion Photo indicator
                        live_info = self._get_live_photo_info(file.path)
                        if live_info:
                            dpg.add_text(live_info, color=(100, 200, 255))

                dpg.add_separator()
                dpg.add_spacer(height=5)

    def _on_keeper_toggled(self, group_id: int, file_id: int, is_keeper: bool) -> None:
        """Handle keeper checkbox toggle."""
        group = self.db.get_duplicate_group(group_id)
        if group and group.status != GroupStatus.PENDING:
            if self.on_status_update:
                self.on_status_update("Keeper selection is only available for pending groups.")
            return

        if is_keeper:
            # Mark this file as keeper
            self.db.resolve_duplicate_group(group_id, file_id)
            logger.info(f"Set keeper for group {group_id}: file {file_id}")

        # Refresh details
        self._show_group_details(group_id)

    def _on_filter_type_change(self, sender, app_data, user_data) -> None:
        """Handle filter type change."""
        filter_val = dpg.get_value("filter_type_combo")

        if filter_val == "Exact Matches":
            self._filter_type = MatchType.EXACT
        elif filter_val == "Near Duplicates":
            self._filter_type = MatchType.NEAR
        else:
            self._filter_type = None

        self._refresh_groups()

    def _on_filter_status_change(self, sender, app_data, user_data) -> None:
        """Handle status filter change."""
        status_val = dpg.get_value(self.TAG_STATUS_FILTER)
        if status_val == "Pending":
            self._filter_status = GroupStatus.PENDING
        elif status_val == "Resolved":
            self._filter_status = GroupStatus.RESOLVED
        elif status_val == "Ignored":
            self._filter_status = GroupStatus.IGNORED
        else:
            self._filter_status = None

        self._refresh_groups()

    def _on_filter_drive_change(self, sender, app_data, user_data) -> None:
        """Handle drive filter change."""
        drive_label = dpg.get_value("filter_drive_combo")
        if drive_label == "All Drives":
            self._filter_drive = None
        else:
            self._filter_drive = self._drive_label_map.get(drive_label)
        self._refresh_groups()

    def _on_filter_scope_change(self, sender, app_data, user_data) -> None:
        """Handle cross-drive scope filter change."""
        scope = dpg.get_value("filter_scope_combo")
        if scope == "Cross-Drive Only":
            self._filter_scope = "cross"
        elif scope == "Single-Drive Only":
            self._filter_scope = "single"
        else:
            self._filter_scope = "all"
        self._refresh_groups()

    def _on_group_checkbox_toggled(self, sender, app_data, user_data) -> None:
        """Handle selection checkbox toggle for a group."""
        group_id = user_data
        if app_data:
            self._selected_group_ids.add(group_id)
        else:
            self._selected_group_ids.discard(group_id)

    def _select_all_groups(self) -> None:
        """Select all visible groups."""
        self._selected_group_ids = {group.id for group in self._current_groups if group.id is not None}
        for group_id, tag in self._group_checkbox_tags.items():
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, group_id in self._selected_group_ids)

    def _deselect_all_groups(self) -> None:
        """Clear selection for all visible groups."""
        self._selected_group_ids.clear()
        for tag in self._group_checkbox_tags.values():
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, False)

    def _apply_scope_filter(self, groups: list[DuplicateGroup]) -> list[DuplicateGroup]:
        """Filter groups based on drive scope selection."""
        filtered: list[DuplicateGroup] = []

        for group in groups:
            full_group = self.db.get_duplicate_group(group.id, include_files=True)
            if not full_group:
                continue

            drive_ids = set()
            for member in full_group.members:
                if member.file:
                    drive_ids.add(member.file.drive_id)

            is_cross_drive = len(drive_ids) > 1
            if self._filter_scope == "cross" and not is_cross_drive:
                continue
            if self._filter_scope == "single" and is_cross_drive:
                continue
            if self._filter_drive and self._filter_drive not in drive_ids:
                continue

            filtered.append(group)

        return filtered

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable action buttons during operations."""
        buttons = [
            "filter_type_combo",
            self.TAG_STATUS_FILTER,
            "filter_scope_combo",
            "filter_drive_combo",
            self.TAG_STRATEGY_COMBO,
            self.TAG_STRATEGY_DRIVE,
            self.TAG_PREVIEW_BUTTON,
            self.TAG_APPLY_SELECTED_BUTTON,
            self.TAG_APPLY_ALL_BUTTON,
            "btn_quarantine",
            "btn_trash",
            "btn_delete",
        ]
        for btn in buttons:
            if dpg.does_item_exist(btn):
                dpg.configure_item(btn, enabled=enabled)

    def _on_find_duplicates(self) -> None:
        """Handle find duplicates button click."""
        if self._operation_in_progress:
            if self.on_status_update:
                self.on_status_update("An operation is already in progress.")
            return

        logger.info("Starting duplicate detection")
        if self.on_status_update:
            self.on_status_update("Finding duplicates...")

        self._operation_in_progress = True
        self._set_buttons_enabled(False)

        # Run in background thread
        def run_detection():
            try:
                total_files, hashed_files = self.db.get_content_hash_counts()
                if total_files > 0 and hashed_files == 0 and self.on_status_update:
                    self.on_status_update("No content hashes found. Run a deep scan or Generate Hashes first.")

                result = self.comparator.find_all_duplicates()
                logger.info(f"Found {result.exact_groups} exact and {result.near_groups} near-duplicate groups")

                # Refresh UI
                self._refresh_groups()
                self._update_stats()

            except Exception as e:
                logger.error(f"Error finding duplicates: {e}")
            finally:
                self._operation_in_progress = False
                self._set_buttons_enabled(True)
                if self.on_status_update:
                    self.on_status_update("Duplicate scan complete.")

        self._detection_thread = threading.Thread(target=run_detection, daemon=True)
        self._detection_thread.start()

    def _get_selected_strategy(self) -> ResolutionStrategy:
        """Get the currently selected resolution strategy."""
        strategy_map = {
            "Keep Newest": ResolutionStrategy.KEEP_NEWEST,
            "Keep Oldest": ResolutionStrategy.KEEP_OLDEST,
            "Keep Largest": ResolutionStrategy.KEEP_LARGEST,
            "Keep Best Quality": ResolutionStrategy.KEEP_BEST_QUALITY,
            "Keep Best Format": ResolutionStrategy.KEEP_BEST_FORMAT,
            "Keep Shortest Path": ResolutionStrategy.KEEP_SHORTEST_PATH,
            "Keep on Drive...": ResolutionStrategy.KEEP_ON_DRIVE,
            "Manual": ResolutionStrategy.MANUAL,
        }

        selected = dpg.get_value(self.TAG_STRATEGY_COMBO)
        return strategy_map.get(selected, ResolutionStrategy.KEEP_LARGEST)

    def _on_strategy_change(self, sender, app_data, user_data) -> None:
        """Handle strategy selection changes."""
        strategy = self._get_selected_strategy()
        enable_drive = strategy == ResolutionStrategy.KEEP_ON_DRIVE
        if dpg.does_item_exist(self.TAG_STRATEGY_DRIVE):
            dpg.configure_item(self.TAG_STRATEGY_DRIVE, enabled=enable_drive)

        if strategy == ResolutionStrategy.MANUAL and self.on_status_update:
            self.on_status_update("Manual strategy selected. Choose keepers per group.")

    def _on_strategy_drive_change(self, sender, app_data, user_data) -> None:
        """Handle preferred drive selection for strategy."""
        label = dpg.get_value(self.TAG_STRATEGY_DRIVE)
        if label == "Select Drive":
            self._preferred_drive_id = None
        else:
            self._preferred_drive_id = self._drive_label_map.get(label)

    def _on_preview_resolution(self) -> None:
        """Handle preview button click."""
        strategy = self._get_selected_strategy()

        if strategy == ResolutionStrategy.MANUAL:
            if self.on_status_update:
                self.on_status_update("Manual strategy does not generate a preview. Select keepers in each group.")
            return

        if strategy == ResolutionStrategy.KEEP_ON_DRIVE and not self._preferred_drive_id:
            if self.on_status_update:
                self.on_status_update("Select a preferred drive for 'Keep on Drive'.")
            return

        group_ids = self._get_target_group_ids(prefer_selected=True)
        preview = self.resolver.preview_resolution(
            strategy,
            group_ids=group_ids if group_ids else None,
            preferred_drive_id=self._preferred_drive_id,
        )

        # Update preview dialog
        summary = f"Strategy: {get_strategy_description(strategy)}\n\n"
        summary += f"Groups affected: {preview.groups_affected:,}\n"
        summary += f"Files to keep: {preview.files_to_keep:,}\n"
        summary += f"Files to remove: {preview.files_to_remove:,}\n"
        summary += f"Space to recover: {preview.space_to_recover / (1024**3):.2f} GB"

        dpg.set_value("preview_summary", summary)

        # Clear and populate details
        children = dpg.get_item_children("preview_details", slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        if preview.by_file_type:
            dpg.add_text("By file type:", parent="preview_details")
            for ftype, (count, size) in sorted(preview.by_file_type.items(), key=lambda x: -x[1][1]):
                size_mb = size / (1024 * 1024)
                dpg.add_text(f"  {ftype}: {count:,} files ({size_mb:.1f} MB)", parent="preview_details")

        # Show dialog
        dpg.show_item(self.TAG_PREVIEW_DIALOG)
        self._center_dialog(self.TAG_PREVIEW_DIALOG, 600, 400)

    def _on_confirm_preview(self) -> None:
        """Handle preview confirm."""
        dpg.hide_item(self.TAG_PREVIEW_DIALOG)

        strategy = self._get_selected_strategy()
        success, failed = self.resolver.apply_all_resolutions(strategy)

        logger.info(f"Applied resolution: {success} successful, {failed} failed")
        self._refresh_groups()
        self._update_stats()

    def _on_cancel_preview(self) -> None:
        """Handle preview cancel."""
        dpg.hide_item(self.TAG_PREVIEW_DIALOG)

    def _on_apply_to_selected(self) -> None:
        """Apply strategy to selected group."""
        strategy = self._get_selected_strategy()
        if strategy == ResolutionStrategy.MANUAL:
            if self.on_status_update:
                self.on_status_update("Manual strategy selected. Choose keepers in each group.")
            return
        if strategy == ResolutionStrategy.KEEP_ON_DRIVE and not self._preferred_drive_id:
            if self.on_status_update:
                self.on_status_update("Select a preferred drive for 'Keep on Drive'.")
            return

        group_ids = self._get_target_group_ids(prefer_selected=True)
        if not group_ids:
            if self.on_status_update:
                self.on_status_update("Select one or more pending groups first.")
            return

        success, failed = self.resolver.apply_all_resolutions(
            strategy,
            group_ids=group_ids,
            preferred_drive_id=self._preferred_drive_id,
        )
        if self.on_status_update:
            self.on_status_update(
                f"Applied strategy to {success} groups"
                + (f", {failed} failed" if failed else "")
            )
        self._refresh_groups()
        if self._selected_group_id:
            self._show_group_details(self._selected_group_id)

    def _on_apply_to_all(self) -> None:
        """Apply strategy to all pending groups."""
        strategy = self._get_selected_strategy()
        if strategy == ResolutionStrategy.MANUAL:
            if self.on_status_update:
                self.on_status_update("Manual strategy selected. Choose keepers in each group.")
            return
        if strategy == ResolutionStrategy.KEEP_ON_DRIVE and not self._preferred_drive_id:
            if self.on_status_update:
                self.on_status_update("Select a preferred drive for 'Keep on Drive'.")
            return

        group_ids = self._get_filtered_pending_group_ids()
        if not group_ids:
            if self.on_status_update:
                self.on_status_update("No pending groups in the current view.")
            return

        success, failed = self.resolver.apply_all_resolutions(
            strategy,
            group_ids=group_ids,
            preferred_drive_id=self._preferred_drive_id,
        )
        if self.on_status_update:
            self.on_status_update(
                f"Applied strategy to {success} groups"
                + (f", {failed} failed" if failed else "")
            )
        self._refresh_groups()
        if self._selected_group_id:
            self._show_group_details(self._selected_group_id)

    def _get_target_group_ids(self, prefer_selected: bool = True) -> list[int]:
        """Return pending group IDs based on selection state."""
        if prefer_selected and self._selected_group_ids:
            group_ids = list(self._selected_group_ids)
        elif self._selected_group_id:
            group_ids = [self._selected_group_id]
        else:
            return []

        return self._filter_pending_group_ids(group_ids)

    def _get_filtered_pending_group_ids(self) -> list[int]:
        """Return pending group IDs from current filtered view."""
        return [
            group.id for group in self._current_groups
            if group.id is not None and group.status == GroupStatus.PENDING
        ]

    def _filter_pending_group_ids(self, group_ids: list[int]) -> list[int]:
        """Filter group IDs down to pending-only and report skipped groups."""
        pending_ids: list[int] = []
        skipped = 0
        for group_id in group_ids:
            group = self.db.get_duplicate_group(group_id)
            if not group:
                continue
            if group.status != GroupStatus.PENDING:
                skipped += 1
                continue
            pending_ids.append(group_id)

        if skipped and self.on_status_update:
            self.on_status_update(f"Skipped {skipped} non-pending group(s).")

        return pending_ids

    def _get_files_to_remove(self) -> tuple[list[int], str | None]:
        """Get list of file IDs to remove from the selected group.

        Returns:
            Tuple of (file_ids, error_message). If error, file_ids is empty.
        """
        group_ids = self._get_target_group_ids(prefer_selected=True)
        if not group_ids:
            return [], "No pending group selected. Select one or more pending groups first."

        remove_ids: list[int] = []
        groups_missing_keeper = 0

        for group_id in group_ids:
            group = self.db.get_duplicate_group(group_id, include_files=True)
            if not group:
                continue

            # Check if a keeper is selected
            has_keeper = any(m.is_keeper for m in group.members)
            if not has_keeper:
                groups_missing_keeper += 1
                continue

            # Get non-keeper files
            remove_ids.extend([m.file_id for m in group.members if not m.is_keeper])

        if groups_missing_keeper:
            return [], (
                f"{groups_missing_keeper} selected group(s) have no keeper. "
                "Select a keeper before removing others."
            )

        if not remove_ids:
            return [], "No files to remove (all selected files are marked as keepers)."

        return remove_ids, None

    def _on_delete_selected(self) -> None:
        """Handle permanent delete button - shows confirmation first."""
        remove_ids, error = self._get_files_to_remove()
        if error:
            if self.on_status_update:
                self.on_status_update(error)
            return

        self._show_confirm_dialog("delete", remove_ids)

    def _on_trash_selected(self) -> None:
        """Handle send to trash button - shows confirmation first."""
        remove_ids, error = self._get_files_to_remove()
        if error:
            if self.on_status_update:
                self.on_status_update(error)
            return

        self._show_confirm_dialog("trash", remove_ids)

    def _on_quarantine_selected(self) -> None:
        """Handle quarantine button - shows confirmation first."""
        remove_ids, error = self._get_files_to_remove()
        if error:
            if self.on_status_update:
                self.on_status_update(error)
            return

        self._show_confirm_dialog("quarantine", remove_ids)

    def _on_ignore_group(self) -> None:
        """Handle ignore group button."""
        if not self._selected_group_id:
            return
        group = self.db.get_duplicate_group(self._selected_group_id)
        if group and group.status == GroupStatus.IGNORED:
            self.resolver.unignore_group(self._selected_group_id)
        else:
            self.resolver.ignore_group(self._selected_group_id)
        self._refresh_groups()
        self._update_stats()

    def _on_unignore_group(self, group_id: int) -> None:
        """Handle unignore group action."""
        self.resolver.unignore_group(group_id)
        self._refresh_groups()
        self._update_stats()

    def _on_unignore_selected(self) -> None:
        """Handle unignore action for selected groups."""
        if not self._selected_group_ids:
            if self.on_status_update:
                self.on_status_update("Select one or more ignored groups to unignore.")
            return

        unignored = 0
        skipped = 0
        for group_id in list(self._selected_group_ids):
            group = self.db.get_duplicate_group(group_id)
            if not group:
                continue
            if group.status != GroupStatus.IGNORED:
                skipped += 1
                continue
            self.resolver.unignore_group(group_id)
            unignored += 1

        if self.on_status_update:
            message = f"Unignored {unignored} group(s)."
            if skipped:
                message += f" Skipped {skipped} non-ignored group(s)."
            self.on_status_update(message)

        self._refresh_groups()
        self._update_stats()

    def _on_clear_selections(self) -> None:
        """Handle clear selections button."""
        count = self.resolver.clear_all_selections()
        logger.info(f"Cleared {count} selections")
        self._selected_group_ids.clear()
        self._refresh_groups()

    def _on_undo_last(self) -> None:
        """Undo the most recent reversible action."""
        if not self.action_engine:
            if self.on_status_update:
                self.on_status_update("Action engine not available.")
            return
        # Get most recent non-reversed entry
        entries = self.db.get_action_log(limit=1)
        if not entries:
            if self.on_status_update:
                self.on_status_update("No actions to undo.")
            return
        entry = entries[0]
        if not entry.reversible or entry.reversed:
            if self.on_status_update:
                self.on_status_update("Most recent action cannot be undone.")
            return
        result = self.action_engine.undo_action(entry.id)
        if result.success:
            if self.on_status_update:
                self.on_status_update(f"Undone: {entry.action_type.value} {entry.source_path}")
            self._refresh_groups()
            self._update_stats()
        else:
            if self.on_status_update:
                self.on_status_update(f"Undo failed: {result.error}", level="error")

    def _on_keep_best_quality(self, group_id: int) -> None:
        """Select the best quality file as keeper for a group."""
        group = self.db.get_duplicate_group(group_id, include_files=True)
        if not group:
            return
        file_ids = [m.file.id for m in group.members if m.file]
        if not file_ids:
            return

        # Check quality scores
        best_id = None
        best_score = -1.0
        for fid in file_ids:
            analysis = self.db.get_scene_analysis(fid)
            if analysis and analysis.quality_score is not None:
                if analysis.quality_score > best_score:
                    best_score = analysis.quality_score
                    best_id = fid
        if best_id is None:
            # No scores - fall back to largest file
            best_file = max(
                (m.file for m in group.members if m.file),
                key=lambda f: f.size,
            )
            best_id = best_file.id
            if self.on_status_update:
                self.on_status_update("No quality scores available, keeping largest file.")

        self.db.resolve_duplicate_group(group_id, best_id)
        logger.info(f"Set quality-based keeper for group {group_id}: file {best_id} (score: {best_score:.1f})")
        self._show_group_details(group_id)
        self._refresh_groups()

    def _on_keep_best_format(self, group_id: int) -> None:
        """Select the best format file as keeper for a group."""
        resolution = self.resolver.resolve_group(
            group_id, ResolutionStrategy.KEEP_BEST_FORMAT
        )
        if resolution:
            self.resolver.apply_resolution(resolution)
            if self.on_status_update:
                keeper = self.db.get_file(resolution.keeper_id)
                ext = (keeper.file_type or "").upper().lstrip('.') if keeper else "?"
                self.on_status_update(f"Keeping {ext} format file as keeper for group {group_id}")
            self._show_group_details(group_id)
            self._refresh_groups()
        else:
            if self.on_status_update:
                self.on_status_update("Could not determine best format for this group.")

    # ------------------------------------------------------------------
    # Context menus
    # ------------------------------------------------------------------

    def _create_context_menus(self) -> None:
        """Create right-click context menu windows."""
        # Group list context menu
        with dpg.window(
            tag=self.TAG_GROUP_CONTEXT_MENU,
            show=False,
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            no_scrollbar=True,
            autosize=True,
        ):
            dpg.add_selectable(label="Open Group Details", callback=self._ctx_open_group)
            dpg.add_selectable(label="Compare Side-by-Side", callback=self._ctx_compare_group)
            dpg.add_separator()
            dpg.add_selectable(label="Mark as Ignored", callback=self._ctx_ignore_group)
            dpg.add_separator()
            dpg.add_selectable(label="Quarantine Non-Keepers", callback=self._ctx_quarantine_group)
            dpg.add_selectable(label="Send to Trash", callback=self._ctx_trash_group)
            dpg.add_selectable(label="Delete Permanently", callback=self._ctx_delete_group)

        # File details context menu
        with dpg.window(
            tag=self.TAG_FILE_CONTEXT_MENU,
            show=False,
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            no_scrollbar=True,
            autosize=True,
        ):
            dpg.add_selectable(label="Open File", callback=self._ctx_open_file)
            dpg.add_selectable(label="Show in Explorer", callback=self._ctx_show_in_explorer)
            dpg.add_separator()
            dpg.add_selectable(label="Mark as Keeper", callback=self._ctx_mark_keeper)
            dpg.add_selectable(label="Copy Path", callback=self._ctx_copy_path)

        # Dismiss handler
        with dpg.handler_registry():
            dpg.add_mouse_click_handler(callback=self._on_dismiss_context_menu)

    def _show_group_context_menu(self, sender=None, app_data=None, user_data=None) -> None:
        """Show group context menu on right-click."""
        import time

        if user_data is not None:
            self._ctx_group_id = user_data
        mouse_pos = dpg.get_mouse_pos(local=False)
        dpg.configure_item(
            self.TAG_GROUP_CONTEXT_MENU,
            show=True,
            pos=[int(mouse_pos[0]), int(mouse_pos[1])],
        )
        dpg.configure_item(self.TAG_FILE_CONTEXT_MENU, show=False)
        self._context_menu_shown = True
        self._context_menu_open_time = time.time()

    def _show_file_context_menu(self, sender=None, app_data=None, user_data=None) -> None:
        """Show file context menu on right-click."""
        import time

        if user_data is not None:
            self._ctx_file_id, self._ctx_file_path = user_data
        mouse_pos = dpg.get_mouse_pos(local=False)
        dpg.configure_item(
            self.TAG_FILE_CONTEXT_MENU,
            show=True,
            pos=[int(mouse_pos[0]), int(mouse_pos[1])],
        )
        dpg.configure_item(self.TAG_GROUP_CONTEXT_MENU, show=False)
        self._context_menu_shown = True
        self._context_menu_open_time = time.time()

    def _on_dismiss_context_menu(self, sender=None, app_data=None) -> None:
        """Hide context menus on left-click outside."""
        import time

        if not self._context_menu_shown:
            return
        if time.time() - self._context_menu_open_time < 0.15:
            return
        try:
            if dpg.is_item_hovered(self.TAG_GROUP_CONTEXT_MENU):
                return
            if dpg.is_item_hovered(self.TAG_FILE_CONTEXT_MENU):
                return
        except (KeyError, SystemError):
            pass
        dpg.configure_item(self.TAG_GROUP_CONTEXT_MENU, show=False)
        dpg.configure_item(self.TAG_FILE_CONTEXT_MENU, show=False)
        self._context_menu_shown = False

    def _hide_context_menus(self) -> None:
        """Hide all context menus."""
        dpg.configure_item(self.TAG_GROUP_CONTEXT_MENU, show=False)
        dpg.configure_item(self.TAG_FILE_CONTEXT_MENU, show=False)
        self._context_menu_shown = False

    # Group context menu callbacks

    def _ctx_open_group(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_group_id is not None:
            self._on_group_selected(self._ctx_group_id)

    def _ctx_compare_group(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_group_id is not None:
            self._show_comparison_dialog(self._ctx_group_id)

    def _ctx_ignore_group(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_group_id is not None:
            self.resolver.ignore_group(self._ctx_group_id)
            self._refresh_groups()
            self._update_stats()

    def _ctx_quarantine_group(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_group_id is None:
            return
        # Temporarily set this as the only selected group
        saved = self._selected_group_ids.copy()
        self._selected_group_ids = {self._ctx_group_id}
        remove_ids, error = self._get_files_to_remove()
        self._selected_group_ids = saved
        if error:
            if self.on_status_update:
                self.on_status_update(error)
            return
        self._show_confirm_dialog("quarantine", remove_ids)

    def _ctx_trash_group(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_group_id is None:
            return
        saved = self._selected_group_ids.copy()
        self._selected_group_ids = {self._ctx_group_id}
        remove_ids, error = self._get_files_to_remove()
        self._selected_group_ids = saved
        if error:
            if self.on_status_update:
                self.on_status_update(error)
            return
        self._show_confirm_dialog("trash", remove_ids)

    def _ctx_delete_group(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_group_id is None:
            return
        saved = self._selected_group_ids.copy()
        self._selected_group_ids = {self._ctx_group_id}
        remove_ids, error = self._get_files_to_remove()
        self._selected_group_ids = saved
        if error:
            if self.on_status_update:
                self.on_status_update(error)
            return
        self._show_confirm_dialog("delete", remove_ids)

    # File context menu callbacks

    def _ctx_open_file(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_file_path:
            self._open_file(self._ctx_file_path)

    def _ctx_show_in_explorer(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_file_path:
            self._open_in_explorer(self._ctx_file_path)

    def _ctx_mark_keeper(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if self._ctx_file_id is not None and self._selected_group_id is not None:
            self._on_keeper_toggled(self._selected_group_id, self._ctx_file_id, True)

    def _ctx_copy_path(self, sender=None, app_data=None) -> None:
        self._hide_context_menus()
        if not self._ctx_file_path:
            return
        try:
            subprocess.run(["clip"], input=self._ctx_file_path.encode(), check=True)
            if self.on_status_update:
                self.on_status_update(f"Copied: {self._ctx_file_path}")
        except Exception as exc:
            logger.error(f"Failed to copy path: {exc}")

    def cleanup(self) -> None:
        """Clean up resources."""
        # Wait for running threads to finish
        if self._action_thread and self._action_thread.is_alive():
            self._action_thread.join(timeout=2.0)
            self._action_thread = None
        if self._detection_thread and self._detection_thread.is_alive():
            self._detection_thread.join(timeout=2.0)
            self._detection_thread = None

        self._operation_in_progress = False

        # Clean up handler registries
        for hr in self._group_row_handler_registries + self._file_detail_handler_registries:
            try:
                if dpg.does_item_exist(hr):
                    dpg.delete_item(hr)
            except Exception:
                pass
        self._group_row_handler_registries.clear()
        self._file_detail_handler_registries.clear()

        # Clean up textures
        for texture_tag in self._texture_cache.values():
            try:
                if dpg.does_item_exist(texture_tag):
                    dpg.delete_item(texture_tag)
            except Exception:
                pass
        self._texture_cache.clear()

        # Delete texture registry
        if dpg.does_item_exist("dup_texture_registry"):
            with contextlib.suppress(Exception):
                dpg.delete_item("dup_texture_registry")

    # --- Export ---

    def _create_export_dialog(self) -> None:
        """Create the export options dialog."""
        with dpg.window(
            tag=self.TAG_EXPORT_DIALOG,
            label="Export Duplicate Groups",
            modal=True,
            show=False,
            width=400,
            height=230,
            no_resize=True,
        ):
            dpg.add_text("Export Format:")
            dpg.add_radio_button(
                items=["CSV", "JSON", "HTML"],
                default_value="CSV",
                tag=self.TAG_EXPORT_FORMAT,
            )
            dpg.add_spacer(height=10)
            dpg.add_text("Scope:")
            dpg.add_radio_button(
                items=["Current filter", "All groups"],
                default_value="Current filter",
                tag=self.TAG_EXPORT_SCOPE,
            )
            dpg.add_spacer(height=15)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Export", callback=self._on_export_click, width=100)
                dpg.add_button(
                    label="Cancel", width=100,
                    callback=lambda: dpg.configure_item(self.TAG_EXPORT_DIALOG, show=False),
                )

    def _show_export_dialog(self) -> None:
        """Show the export dialog."""
        dpg.configure_item(self.TAG_EXPORT_DIALOG, show=True)
        self._center_dialog(self.TAG_EXPORT_DIALOG, 400, 230)

    def _on_export_click(self) -> None:
        """Handle export button click."""
        from duplicleaner.utils.export_manager import (
            export_csv,
            export_html,
            export_json,
            format_size,
            get_default_export_dir,
            get_timestamped_filename,
        )

        dpg.configure_item(self.TAG_EXPORT_DIALOG, show=False)

        fmt = dpg.get_value(self.TAG_EXPORT_FORMAT)
        scope = dpg.get_value(self.TAG_EXPORT_SCOPE)

        # Gather groups
        if scope == "Current filter":
            groups = self._current_groups
        else:
            groups = self.db.get_duplicate_groups(limit=100000)

        if not groups:
            if self.on_status_update:
                self.on_status_update("No duplicate groups to export.")
            return

        # Load members for each group
        full_groups = []
        for g in groups:
            full = self.db.get_duplicate_group(g.id, include_files=True)
            if full:
                full_groups.append(full)

        export_dir = get_default_export_dir()

        if fmt == "CSV":
            filepath = export_dir / get_timestamped_filename("duplicates", "csv")
            rows = []
            for g in full_groups:
                for m in g.members:
                    f = m.file
                    rows.append({
                        "group_id": g.id,
                        "match_type": g.match_type.value,
                        "similarity": f"{g.similarity:.2f}",
                        "status": g.status.value,
                        "file_id": m.file_id,
                        "filename": f.filename if f else "",
                        "path": f.path if f else "",
                        "size": f.size if f else 0,
                        "size_human": format_size(f.size) if f else "",
                        "modified": str(f.modified) if f and f.modified else "",
                        "content_hash": f.content_hash if f else "",
                        "is_keeper": m.is_keeper,
                    })
            count = export_csv(rows, filepath)
            msg = f"Exported {count} rows ({len(full_groups)} groups) to {filepath}"

        elif fmt == "JSON":
            filepath = export_dir / get_timestamped_filename("duplicates", "json")
            data = {
                "export_date": str(datetime.now()),
                "group_count": len(full_groups),
                "groups": [],
            }
            for g in full_groups:
                group_data = {
                    "id": g.id,
                    "match_type": g.match_type.value,
                    "similarity": g.similarity,
                    "file_count": g.file_count,
                    "total_size": g.total_size,
                    "wasted_size": g.wasted_size,
                    "status": g.status.value,
                    "files": [],
                }
                for m in g.members:
                    f = m.file
                    group_data["files"].append({
                        "file_id": m.file_id,
                        "filename": f.filename if f else "",
                        "path": f.path if f else "",
                        "size": f.size if f else 0,
                        "modified": str(f.modified) if f and f.modified else None,
                        "content_hash": f.content_hash if f else None,
                        "is_keeper": m.is_keeper,
                    })
                data["groups"].append(group_data)
            export_json(data, filepath)
            msg = f"Exported {len(full_groups)} groups to {filepath}"

        else:  # HTML
            filepath = export_dir / get_timestamped_filename("duplicates", "html")
            total_wasted = sum(g.wasted_size for g in full_groups)
            summary_stats = {
                "Groups": f"{len(full_groups):,}",
                "Total Files": f"{sum(g.file_count for g in full_groups):,}",
                "Wasted Space": format_size(total_wasted),
            }
            rows = []
            for g in full_groups:
                for m in g.members:
                    f = m.file
                    rows.append({
                        "Group": g.id,
                        "Type": g.match_type.value,
                        "Similarity": f"{g.similarity:.0%}",
                        "Status": g.status.value,
                        "Keeper": "Yes" if m.is_keeper else "",
                        "Filename": f.filename if f else "",
                        "Path": f.path if f else "",
                        "Size": format_size(f.size) if f else "",
                        "Modified": str(f.modified)[:19] if f and f.modified else "",
                    })
            columns = ["Group", "Type", "Similarity", "Status", "Keeper",
                       "Filename", "Path", "Size", "Modified"]
            export_html(
                "DupliCleaner - Duplicate Groups Report",
                [{"heading": "Duplicate Groups", "columns": columns, "rows": rows}],
                filepath,
                summary_stats=summary_stats,
            )
            msg = f"Exported {len(full_groups)} groups to {filepath}"

        logger.info(msg)
        if self.on_status_update:
            self.on_status_update(msg)
