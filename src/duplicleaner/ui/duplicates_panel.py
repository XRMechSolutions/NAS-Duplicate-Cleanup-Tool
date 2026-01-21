"""Duplicates Panel for DupliCleaner.

Dear PyGui UI component for reviewing and resolving duplicate files.
"""

import threading
from typing import Callable, Optional

import dearpygui.dearpygui as dpg

from duplicleaner.db.database import get_database
from duplicleaner.db.models import DuplicateGroup, MatchType, GroupStatus
from duplicleaner.core.comparator import Comparator
from duplicleaner.core.resolver import Resolver, ResolutionStrategy, get_strategy_description
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
    TAG_PREVIEW_DIALOG = "dup_preview_dialog"

    def __init__(
        self,
        parent: int | str,
        on_action_requested: Optional[Callable[[list[int]], None]] = None,
        on_status_update: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the duplicates panel.

        Args:
            parent: Parent window/container tag
            on_action_requested: Callback when user wants to act on files (list of file IDs)
        """
        self.parent = parent
        self.on_action_requested = on_action_requested
        self.on_status_update = on_status_update

        self.db = get_database()
        self.resolver = Resolver()
        self.comparator = Comparator()

        # Current state
        self._current_groups: list[DuplicateGroup] = []
        self._selected_group_id: Optional[int] = None
        self._filter_type: Optional[MatchType] = None
        self._filter_drive: Optional[str] = None
        self._filter_scope: str = "all"

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the panel UI."""
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            # Header with stats
            dpg.add_text("Duplicate Files", color=(150, 200, 255))
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Statistics bar
            with dpg.group(horizontal=True, tag=self.TAG_STATS):
                dpg.add_text("Loading statistics...", tag="dup_stats_text")

            dpg.add_spacer(height=10)

            # Filter and action bar
            with dpg.group(horizontal=True):
                dpg.add_text("Filter:")
                dpg.add_combo(
                    items=["All", "Exact Matches", "Near Duplicates"],
                    default_value="All",
                    width=150,
                    callback=self._on_filter_type_change,
                    tag="filter_type_combo"
                )

                dpg.add_spacer(width=20)
                dpg.add_text("Scope:")
                dpg.add_combo(
                    items=["All Groups", "Cross-Drive Only", "Single-Drive Only"],
                    default_value="All Groups",
                    width=160,
                    callback=self._on_filter_scope_change,
                    tag="filter_scope_combo"
                )

                dpg.add_spacer(width=20)
                dpg.add_text("Drive:")
                dpg.add_combo(
                    items=["All Drives"],
                    default_value="All Drives",
                    width=150,
                    callback=self._on_filter_drive_change,
                    tag="filter_drive_combo"
                )

                dpg.add_spacer(width=20)
                dpg.add_button(label="Refresh", callback=self._refresh_groups)
                dpg.add_button(label="Find Duplicates", callback=self._on_find_duplicates)

            dpg.add_spacer(height=10)

            # Main content area - split into list and details
            with dpg.group(horizontal=True):
                # Left side - group list
                with dpg.child_window(width=600, height=400, border=True):
                    dpg.add_text("Duplicate Groups", color=(200, 200, 200))
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
            dpg.add_text("Resolution", color=(150, 200, 255))
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_text("Strategy:")
                dpg.add_combo(
                    items=[
                        "Keep Newest",
                        "Keep Oldest",
                        "Keep Largest",
                        "Keep Shortest Path",
                        "Keep on Drive...",
                        "Manual",
                    ],
                    default_value="Keep Largest",
                    width=200,
                    tag=self.TAG_STRATEGY_COMBO
                )

                dpg.add_spacer(width=20)
                dpg.add_button(label="Preview", callback=self._on_preview_resolution)
                dpg.add_button(label="Apply to Selected", callback=self._on_apply_to_selected)
                dpg.add_button(label="Apply to All", callback=self._on_apply_to_all)

            dpg.add_spacer(height=10)

            # Action buttons for selected files
            with dpg.group(horizontal=True):
                dpg.add_button(label="Delete Selected", callback=self._on_delete_selected)
                dpg.add_button(label="Move to Quarantine", callback=self._on_quarantine_selected)
                dpg.add_button(label="Ignore Group", callback=self._on_ignore_group)
                dpg.add_spacer(width=20)
                dpg.add_button(label="Clear Selections", callback=self._on_clear_selections)

        # Create preview dialog
        self._create_preview_dialog()

        # Initial refresh
        self._refresh_groups()
        self._update_stats()
        self._populate_drive_filter()

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
        ):
            dpg.add_text("Resolution Preview", color=(150, 200, 255))
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

    def _update_stats(self) -> None:
        """Update the statistics display."""
        stats = self.db.get_statistics()

        pending_groups = stats.get("pending_duplicate_groups", 0)
        wasted_space = stats.get("wasted_space", 0)
        wasted_gb = wasted_space / (1024 ** 3)

        text = f"Duplicate Groups: {pending_groups:,} | "
        text += f"Potential Space Savings: {wasted_gb:.1f} GB"

        dpg.set_value("dup_stats_text", text)

    def _populate_drive_filter(self) -> None:
        """Populate the drive filter combo box."""
        drives = self.db.get_all_drives()
        items = ["All Drives"] + [d.label for d in drives]
        dpg.configure_item("filter_drive_combo", items=items)

    def _refresh_groups(self) -> None:
        """Refresh the duplicate groups list."""
        # Clear existing rows
        children = dpg.get_item_children(self.TAG_GROUP_LIST, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        # Get groups with filters
        match_type = self._filter_type

        groups = self.db.get_duplicate_groups(
            status=GroupStatus.PENDING,
            match_type=match_type,
            limit=500
        )

        if self._filter_scope != "all" or self._filter_drive:
            groups = self._apply_scope_filter(groups)

        self._current_groups = groups

        if not groups:
            with dpg.table_row(parent=self.TAG_GROUP_LIST):
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
                # Make row clickable
                dpg.add_selectable(
                    label=type_str,
                    callback=lambda s, a, u: self._on_group_selected(u),
                    user_data=group.id,
                    span_columns=True
                )

            # Add actual data in separate row (workaround for selectable spanning)
            with dpg.table_row(parent=self.TAG_GROUP_LIST):
                dpg.add_text(type_str)
                dpg.add_text(str(group.file_count))
                dpg.add_text(sample_name[:30] + "..." if len(sample_name) > 30 else sample_name)
                dpg.add_text(wasted_str)
                dpg.add_text(status_str)

        self._update_stats()

    def _on_group_selected(self, group_id: int) -> None:
        """Handle group selection."""
        self._selected_group_id = group_id
        self._show_group_details(group_id)

    def _show_group_details(self, group_id: int) -> None:
        """Show details for a selected group."""
        # Clear existing details
        children = dpg.get_item_children(self.TAG_DETAILS_PANEL, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        group = self.db.get_duplicate_group(group_id, include_files=True)
        if not group:
            dpg.add_text("Group not found", parent=self.TAG_DETAILS_PANEL)
            return

        # Header
        match_type = "Exact Match" if group.match_type == MatchType.EXACT else f"Near Match ({group.similarity:.0%})"
        dpg.add_text(f"Group #{group.id} - {match_type}", parent=self.TAG_DETAILS_PANEL, color=(150, 200, 255))
        dpg.add_separator(parent=self.TAG_DETAILS_PANEL)
        dpg.add_spacer(height=5, parent=self.TAG_DETAILS_PANEL)

        # AI Recommendation
        recommendation = self.resolver.get_recommendation(group_id)
        if recommendation:
            keeper, reasons = recommendation
            dpg.add_text("Recommended: Keep", parent=self.TAG_DETAILS_PANEL, color=(100, 200, 100))
            dpg.add_text(f"  {keeper.filename}", parent=self.TAG_DETAILS_PANEL)
            for reason in reasons[:3]:
                dpg.add_text(f"    - {reason}", parent=self.TAG_DETAILS_PANEL, color=(150, 150, 150))
            dpg.add_spacer(height=5, parent=self.TAG_DETAILS_PANEL)

        # File list
        dpg.add_text(f"Files ({group.file_count}):", parent=self.TAG_DETAILS_PANEL)

        for member in group.members:
            if not member.file:
                continue

            file = member.file
            is_keeper = member.is_keeper

            # File info
            with dpg.group(horizontal=True, parent=self.TAG_DETAILS_PANEL):
                # Checkbox for keeper selection
                dpg.add_checkbox(
                    default_value=is_keeper,
                    callback=lambda s, a, u: self._on_keeper_toggled(u[0], u[1], a),
                    user_data=(group_id, file.id)
                )

                # Keeper indicator
                if is_keeper:
                    dpg.add_text("[KEEP]", color=(100, 200, 100))
                else:
                    dpg.add_text("[    ]", color=(100, 100, 100))

            # File details
            size_kb = file.size / 1024
            if size_kb >= 1024:
                size_str = f"{size_kb / 1024:.1f} MB"
            else:
                size_str = f"{size_kb:.0f} KB"

            dpg.add_text(f"  {file.filename} ({size_str})", parent=self.TAG_DETAILS_PANEL)
            dpg.add_text(f"    {file.path}", parent=self.TAG_DETAILS_PANEL, color=(150, 150, 150))

            if file.modified:
                dpg.add_text(f"    Modified: {file.modified.strftime('%Y-%m-%d %H:%M')}",
                           parent=self.TAG_DETAILS_PANEL, color=(150, 150, 150))

    def _on_keeper_toggled(self, group_id: int, file_id: int, is_keeper: bool) -> None:
        """Handle keeper checkbox toggle."""
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

    def _on_filter_drive_change(self, sender, app_data, user_data) -> None:
        """Handle drive filter change."""
        drive_label = dpg.get_value("filter_drive_combo")
        if drive_label == "All Drives":
            self._filter_drive = None
        else:
            drives = self.db.get_all_drives()
            drive = next((d for d in drives if d.label == drive_label), None)
            self._filter_drive = drive.id if drive else None
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

    def _on_find_duplicates(self) -> None:
        """Handle find duplicates button click."""
        logger.info("Starting duplicate detection")
        if self.on_status_update:
            self.on_status_update("Finding duplicates...")

        # Run in background thread
        def run_detection():
            try:
                result = self.comparator.find_all_duplicates()
                logger.info(f"Found {result.exact_groups} exact and {result.near_groups} near-duplicate groups")

                # Refresh UI
                self._refresh_groups()
                self._update_stats()

            except Exception as e:
                logger.error(f"Error finding duplicates: {e}")
            finally:
                if self.on_status_update:
                    self.on_status_update("Duplicate scan complete.")

        thread = threading.Thread(target=run_detection, daemon=True)
        thread.start()

    def _get_selected_strategy(self) -> ResolutionStrategy:
        """Get the currently selected resolution strategy."""
        strategy_map = {
            "Keep Newest": ResolutionStrategy.KEEP_NEWEST,
            "Keep Oldest": ResolutionStrategy.KEEP_OLDEST,
            "Keep Largest": ResolutionStrategy.KEEP_LARGEST,
            "Keep Shortest Path": ResolutionStrategy.KEEP_SHORTEST_PATH,
            "Keep on Drive...": ResolutionStrategy.KEEP_ON_DRIVE,
            "Manual": ResolutionStrategy.MANUAL,
        }

        selected = dpg.get_value(self.TAG_STRATEGY_COMBO)
        return strategy_map.get(selected, ResolutionStrategy.KEEP_LARGEST)

    def _on_preview_resolution(self) -> None:
        """Handle preview button click."""
        strategy = self._get_selected_strategy()

        if strategy == ResolutionStrategy.MANUAL:
            return

        preview = self.resolver.preview_resolution(strategy)

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
        if not self._selected_group_id:
            return

        strategy = self._get_selected_strategy()
        resolution = self.resolver.resolve_group(self._selected_group_id, strategy)

        if resolution:
            self.resolver.apply_resolution(resolution)
            self._refresh_groups()
            self._show_group_details(self._selected_group_id)

    def _on_apply_to_all(self) -> None:
        """Apply strategy to all pending groups."""
        self._on_preview_resolution()

    def _on_delete_selected(self) -> None:
        """Handle delete selected button."""
        if not self._selected_group_id:
            return

        group = self.db.get_duplicate_group(self._selected_group_id, include_files=True)
        if not group:
            return

        # Get non-keeper files
        remove_ids = [m.file_id for m in group.members if not m.is_keeper]

        if remove_ids and self.on_action_requested:
            self.on_action_requested(remove_ids)

    def _on_quarantine_selected(self) -> None:
        """Handle quarantine selected button."""
        # Similar to delete but with different action type
        self._on_delete_selected()

    def _on_ignore_group(self) -> None:
        """Handle ignore group button."""
        if not self._selected_group_id:
            return

        self.resolver.ignore_group(self._selected_group_id)
        self._refresh_groups()
        self._update_stats()

    def _on_clear_selections(self) -> None:
        """Handle clear selections button."""
        count = self.resolver.clear_all_selections()
        logger.info(f"Cleared {count} selections")
        self._refresh_groups()

    def cleanup(self) -> None:
        """Clean up resources."""
        pass
