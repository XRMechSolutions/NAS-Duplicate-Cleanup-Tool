"""Organize Panel for DupliCleaner.

Dear PyGui UI component for photo organization features.
"""

import threading
from pathlib import Path
from typing import Callable, Optional

import dearpygui.dearpygui as dpg

from duplicleaner.core.organizer import (
    Organizer,
    OrganizeSettings,
    OrganizePreview,
    OrganizeProgress,
    OrganizeResult,
    DateFormat,
    ScreenshotHandling,
    BurstHandling,
    ConflictResolution,
    UndatedHandling,
)
from duplicleaner.utils.logging import get_logger
from duplicleaner.utils.config import get_config

logger = get_logger(__name__)


def format_size(size_bytes: int) -> str:
    """Format byte size to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


class OrganizePanel:
    """UI panel for photo organization."""

    # Tag constants
    TAG_PANEL = "organize_panel"
    TAG_SOURCE_INPUT = "org_source_input"
    TAG_DEST_INPUT = "org_dest_input"
    TAG_PREVIEW_TABLE = "org_preview_table"
    TAG_PROGRESS_GROUP = "org_progress_group"
    TAG_PROGRESS_BAR = "org_progress_bar"
    TAG_PROGRESS_TEXT = "org_progress_text"
    TAG_CURRENT_FILE = "org_current_file"
    TAG_STATS_GROUP = "org_stats_group"
    TAG_SETTINGS_GROUP = "org_settings_group"
    TAG_FOLDER_TREE = "org_folder_tree"

    def __init__(
        self,
        parent: int | str,
        on_organize_complete: Optional[Callable[[list[OrganizeResult]], None]] = None,
        on_status_update: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the organize panel.

        Args:
            parent: Parent window/container tag
            on_organize_complete: Callback when organization completes
        """
        self.parent = parent
        self.on_organize_complete = on_organize_complete
        self.on_status_update = on_status_update

        # Organizer instance
        self._organizer: Optional[Organizer] = None
        self._organize_thread: Optional[threading.Thread] = None
        self._current_preview: Optional[OrganizePreview] = None

        # Settings
        self._settings = OrganizeSettings()

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the panel UI."""
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            # Header
            dpg.add_text("Photo Organization", color=(150, 200, 255))
            dpg.add_separator()
            dpg.add_spacer(height=10)

            # Source and destination
            with dpg.group():
                with dpg.group(horizontal=True):
                    dpg.add_text("Source Folder:", indent=0)
                    dpg.add_input_text(
                        tag=self.TAG_SOURCE_INPUT,
                        width=400,
                        hint="Select folder with unorganized photos..."
                    )
                    dpg.add_button(label="Browse...", callback=self._on_browse_source)

                dpg.add_spacer(height=5)

                with dpg.group(horizontal=True):
                    dpg.add_text("Destination: ", indent=0)
                    dpg.add_input_text(
                        tag=self.TAG_DEST_INPUT,
                        width=400,
                        hint="Select destination for organized photos..."
                    )
                    dpg.add_button(label="Browse...", callback=self._on_browse_dest)

            dpg.add_spacer(height=10)

            # Statistics (updated after preview)
            with dpg.group(tag=self.TAG_STATS_GROUP):
                dpg.add_text("Run Preview to see organization statistics.", color=(150, 150, 150))

            dpg.add_spacer(height=10)

            # Settings collapsible section
            with dpg.collapsing_header(label="Organization Settings", default_open=True):
                with dpg.group(horizontal=True):
                    # Left column - Folder structure
                    with dpg.child_window(width=350, height=250, border=False):
                        dpg.add_text("Folder Structure", color=(150, 200, 255))
                        dpg.add_separator()

                        dpg.add_combo(
                            label="Date Format",
                            items=["YYYY/MM", "YYYY/MM-Month", "YYYY/MM/DD", "YYYY/YYYY-MM-DD"],
                            default_value="YYYY/MM-Month",
                            callback=self._on_date_format_change,
                            tag="org_date_format"
                        )

                        dpg.add_checkbox(
                            label="Include Location in Folders",
                            default_value=False,
                            callback=self._on_location_toggle,
                            tag="org_include_location"
                        )

                        dpg.add_checkbox(
                            label="Event Clustering",
                            default_value=False,
                            callback=self._on_event_toggle,
                            tag="org_event_clustering"
                        )

                        with dpg.group(horizontal=True):
                            dpg.add_text("Event Gap (hours):")
                            dpg.add_input_int(
                                default_value=4,
                                min_value=1,
                                max_value=48,
                                width=100,
                                callback=self._on_event_gap_change,
                                tag="org_event_gap"
                            )

                    # Middle column - File naming
                    with dpg.child_window(width=350, height=250, border=False):
                        dpg.add_text("File Naming", color=(150, 200, 255))
                        dpg.add_separator()

                        dpg.add_checkbox(
                            label="Rename Files",
                            default_value=True,
                            callback=self._on_rename_toggle,
                            tag="org_rename_files"
                        )

                        dpg.add_combo(
                            label="Rename Pattern",
                            items=[
                                "{date}_{seq}",
                                "{date}_{location}_{seq}",
                                "{date}_{time}_{seq}",
                                "{original}"
                            ],
                            default_value="{date}_{seq}",
                            callback=self._on_pattern_change,
                            tag="org_rename_pattern"
                        )

                        dpg.add_combo(
                            label="Conflict Resolution",
                            items=["Add Sequence Number", "Add Timestamp", "Skip", "Overwrite if Identical"],
                            default_value="Add Sequence Number",
                            callback=self._on_conflict_change,
                            tag="org_conflict"
                        )

                    # Right column - Special handling
                    with dpg.child_window(width=350, height=250, border=False):
                        dpg.add_text("Special Handling", color=(150, 200, 255))
                        dpg.add_separator()

                        dpg.add_combo(
                            label="Screenshots",
                            items=["Mix with Photos", "Separate Folder", "Separate by App"],
                            default_value="Separate Folder",
                            callback=self._on_screenshot_change,
                            tag="org_screenshots"
                        )

                        dpg.add_combo(
                            label="Undated Photos",
                            items=["Undated Folder", "Use File Date", "Skip"],
                            default_value="Undated Folder",
                            callback=self._on_undated_change,
                            tag="org_undated"
                        )

                        dpg.add_spacer(height=10)

                        dpg.add_checkbox(
                            label="Move Files (uncheck to copy)",
                            default_value=True,
                            callback=self._on_move_toggle,
                            tag="org_move_files"
                        )

                        dpg.add_checkbox(
                            label="Dry Run (preview only)",
                            default_value=False,
                            callback=self._on_dryrun_toggle,
                            tag="org_dry_run"
                        )

            dpg.add_spacer(height=10)

            # Action buttons
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Preview Organization",
                    callback=self._on_preview_click,
                    width=150
                )
                dpg.add_button(
                    label="Organize Now",
                    callback=self._on_organize_click,
                    width=150,
                    tag="org_organize_btn"
                )
                dpg.add_spacer(width=20)
                dpg.add_button(label="Cancel", callback=self._on_cancel_click, tag="org_cancel_btn", enabled=False)
                dpg.add_spacer(width=20)
                dpg.add_button(label="Export Preview as CSV", callback=self._on_export_click, tag="org_export_btn", enabled=False)

            dpg.add_spacer(height=10)

            # Progress section (initially hidden)
            with dpg.group(tag=self.TAG_PROGRESS_GROUP, show=False):
                dpg.add_separator()
                dpg.add_text("Organization Progress", color=(150, 200, 255))
                dpg.add_spacer(height=5)

                dpg.add_text("Status: Idle", tag=self.TAG_PROGRESS_TEXT)
                dpg.add_progress_bar(tag=self.TAG_PROGRESS_BAR, default_value=0.0, width=-1)
                dpg.add_text("Current: ", tag=self.TAG_CURRENT_FILE)

            dpg.add_spacer(height=10)

            # Preview section
            dpg.add_separator()
            dpg.add_text("Preview", color=(150, 200, 255))
            dpg.add_spacer(height=5)

            # Two-column layout: folder tree and file list
            with dpg.group(horizontal=True):
                # Folder tree
                with dpg.child_window(width=300, height=400, border=True):
                    dpg.add_text("Folders to Create", color=(150, 200, 255))
                    dpg.add_separator()
                    with dpg.tree_node(label="Organized Photos", tag=self.TAG_FOLDER_TREE, default_open=True):
                        dpg.add_text("Run preview to see folder structure", color=(150, 150, 150))

                # File list table
                with dpg.child_window(width=-1, height=400, border=True):
                    dpg.add_text("Files to Organize", color=(150, 200, 255))
                    dpg.add_separator()
                    with dpg.table(
                        tag=self.TAG_PREVIEW_TABLE,
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
                        dpg.add_table_column(label="Source", init_width_or_weight=250)
                        dpg.add_table_column(label="Destination", init_width_or_weight=350)
                        dpg.add_table_column(label="Date Source", init_width_or_weight=80)
                        dpg.add_table_column(label="Location", init_width_or_weight=100)

        # File dialogs
        self._create_file_dialogs()

    def _create_file_dialogs(self) -> None:
        """Create file/folder dialogs."""
        # We'll use a simple input for now since file dialogs need more setup
        # In production, use dpg.add_file_dialog
        pass

    def _on_browse_source(self) -> None:
        """Handle source browse button click."""
        # For now, prompt user to enter path manually
        # Full implementation would use dpg.add_file_dialog
        logger.info("Browse source clicked - enter path manually")

    def _on_browse_dest(self) -> None:
        """Handle destination browse button click."""
        logger.info("Browse destination clicked - enter path manually")

    def _update_settings_from_ui(self) -> None:
        """Update settings object from UI controls."""
        # Date format
        date_fmt = dpg.get_value("org_date_format")
        format_map = {
            "YYYY/MM": DateFormat.YYYY_MM,
            "YYYY/MM-Month": DateFormat.YYYY_MM_MONTH,
            "YYYY/MM/DD": DateFormat.YYYY_MM_DD,
            "YYYY/YYYY-MM-DD": DateFormat.YYYY_FULL_DATE,
        }
        self._settings.date_format = format_map.get(date_fmt, DateFormat.YYYY_MM_MONTH)

        # Toggles
        self._settings.include_location = dpg.get_value("org_include_location")
        self._settings.event_clustering = dpg.get_value("org_event_clustering")
        self._settings.event_gap_hours = dpg.get_value("org_event_gap")
        self._settings.rename_files = dpg.get_value("org_rename_files")
        self._settings.move_files = dpg.get_value("org_move_files")
        self._settings.dry_run = dpg.get_value("org_dry_run")

        # Pattern
        self._settings.rename_pattern = dpg.get_value("org_rename_pattern")

        # Screenshots
        screenshot_map = {
            "Mix with Photos": ScreenshotHandling.MIX,
            "Separate Folder": ScreenshotHandling.SEPARATE,
            "Separate by App": ScreenshotHandling.SEPARATE_BY_APP,
        }
        self._settings.screenshot_handling = screenshot_map.get(
            dpg.get_value("org_screenshots"), ScreenshotHandling.SEPARATE
        )

        # Undated
        undated_map = {
            "Undated Folder": UndatedHandling.UNDATED_FOLDER,
            "Use File Date": UndatedHandling.USE_FILE_DATE,
            "Skip": UndatedHandling.SKIP,
        }
        self._settings.undated_handling = undated_map.get(
            dpg.get_value("org_undated"), UndatedHandling.UNDATED_FOLDER
        )

        # Conflict
        conflict_map = {
            "Add Sequence Number": ConflictResolution.ADD_SEQUENCE,
            "Add Timestamp": ConflictResolution.ADD_TIMESTAMP,
            "Skip": ConflictResolution.SKIP,
            "Overwrite if Identical": ConflictResolution.OVERWRITE_IF_IDENTICAL,
        }
        self._settings.conflict_resolution = conflict_map.get(
            dpg.get_value("org_conflict"), ConflictResolution.ADD_SEQUENCE
        )

    def _on_date_format_change(self, sender, app_data) -> None:
        """Handle date format change."""
        self._update_settings_from_ui()

    def _on_location_toggle(self, sender, app_data) -> None:
        """Handle location toggle."""
        self._update_settings_from_ui()

    def _on_event_toggle(self, sender, app_data) -> None:
        """Handle event clustering toggle."""
        self._update_settings_from_ui()

    def _on_event_gap_change(self, sender, app_data) -> None:
        """Handle event gap change."""
        self._update_settings_from_ui()

    def _on_rename_toggle(self, sender, app_data) -> None:
        """Handle rename toggle."""
        self._update_settings_from_ui()

    def _on_pattern_change(self, sender, app_data) -> None:
        """Handle pattern change."""
        self._update_settings_from_ui()

    def _on_screenshot_change(self, sender, app_data) -> None:
        """Handle screenshot handling change."""
        self._update_settings_from_ui()

    def _on_undated_change(self, sender, app_data) -> None:
        """Handle undated handling change."""
        self._update_settings_from_ui()

    def _on_conflict_change(self, sender, app_data) -> None:
        """Handle conflict resolution change."""
        self._update_settings_from_ui()

    def _on_move_toggle(self, sender, app_data) -> None:
        """Handle move/copy toggle."""
        self._update_settings_from_ui()

    def _on_dryrun_toggle(self, sender, app_data) -> None:
        """Handle dry run toggle."""
        self._update_settings_from_ui()

    def _on_preview_click(self) -> None:
        """Handle preview button click."""
        source = dpg.get_value(self.TAG_SOURCE_INPUT).strip()
        dest = dpg.get_value(self.TAG_DEST_INPUT).strip()

        if not source:
            self._show_error("Please enter a source folder.")
            return

        if not dest:
            self._show_error("Please enter a destination folder.")
            return

        if not Path(source).exists():
            self._show_error(f"Source folder does not exist: {source}")
            return

        self._update_settings_from_ui()

        # Run preview in thread
        def preview_thread():
            try:
                if self.on_status_update:
                    self.on_status_update("Generating organization preview...")
                self._organizer = Organizer(settings=self._settings)
                preview = self._organizer.preview(source, dest)
                self._current_preview = preview

                # Update UI in main thread
                dpg.split_frame()
                self._update_preview_ui(preview)
                if self.on_status_update:
                    self.on_status_update("Preview complete.")

            except Exception as e:
                logger.error(f"Preview failed: {e}")
                dpg.split_frame()
                self._show_error(f"Preview failed: {e}")
                if self.on_status_update:
                    self.on_status_update("Preview failed.")

        thread = threading.Thread(target=preview_thread)
        thread.start()

    def _update_preview_ui(self, preview: OrganizePreview) -> None:
        """Update UI with preview results.

        Args:
            preview: Preview results
        """
        # Update statistics
        dpg.delete_item(self.TAG_STATS_GROUP, children_only=True)
        with dpg.group(parent=self.TAG_STATS_GROUP, horizontal=True):
            dpg.add_text(f"Total Files: {preview.total_files}")
            dpg.add_spacer(width=20)
            dpg.add_text(f"To Move: {preview.files_to_move}")
            dpg.add_spacer(width=20)
            dpg.add_text(f"To Rename: {preview.files_to_rename}")
            dpg.add_spacer(width=20)
            dpg.add_text(f"Skip: {preview.files_to_skip}")
            dpg.add_spacer(width=20)
            dpg.add_text(f"Folders: {preview.folders_to_create}")

        # Update folder tree
        dpg.delete_item(self.TAG_FOLDER_TREE, children_only=True)

        # Build tree structure
        folder_tree: dict = {}
        for folder, count in sorted(preview.folders.items()):
            parts = folder.split('/')
            current = folder_tree
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current['__count__'] = count

        def add_tree_nodes(parent, tree, path=""):
            for key, value in sorted(tree.items()):
                if key == '__count__':
                    continue
                full_path = f"{path}/{key}" if path else key
                count = value.get('__count__', 0)
                label = f"{key} ({count} files)" if count else key

                if any(k != '__count__' for k in value.keys()):
                    with dpg.tree_node(label=label, parent=parent, default_open=False):
                        add_tree_nodes(dpg.last_item(), value, full_path)
                else:
                    dpg.add_text(f"  {label}", parent=parent)

        add_tree_nodes(self.TAG_FOLDER_TREE, folder_tree)

        # Update file list table
        dpg.delete_item(self.TAG_PREVIEW_TABLE, children_only=True, slot=1)

        # Re-add columns
        with dpg.table_row(parent=self.TAG_PREVIEW_TABLE):
            pass  # Header row handled by table

        # Add first 500 files to table
        for change in preview.changes[:500]:
            with dpg.table_row(parent=self.TAG_PREVIEW_TABLE):
                dpg.add_text(Path(change.source_path).name)
                dpg.add_text(change.dest_path)
                dpg.add_text(change.date_source or "")
                dpg.add_text(change.location or "")

        if len(preview.changes) > 500:
            with dpg.table_row(parent=self.TAG_PREVIEW_TABLE):
                dpg.add_text(f"... and {len(preview.changes) - 500} more files")

        # Enable export and organize buttons
        dpg.configure_item("org_export_btn", enabled=True)

    def _on_organize_click(self) -> None:
        """Handle organize button click."""
        if self._current_preview is None:
            self._show_error("Please run Preview first.")
            return

        source = dpg.get_value(self.TAG_SOURCE_INPUT).strip()
        dest = dpg.get_value(self.TAG_DEST_INPUT).strip()

        if not source or not dest:
            self._show_error("Source and destination are required.")
            return

        # Show progress
        dpg.configure_item(self.TAG_PROGRESS_GROUP, show=True)
        dpg.configure_item("org_cancel_btn", enabled=True)
        dpg.configure_item("org_organize_btn", enabled=False)

        self._update_settings_from_ui()

        def organize_thread():
            try:
                if self.on_status_update:
                    self.on_status_update("Organizing files...")
                self._organizer = Organizer(settings=self._settings)
                self._organizer.set_progress_callback(self._on_progress_update)

                results = self._organizer.execute(
                    source, dest,
                    preview=self._current_preview
                )

                dpg.split_frame()
                self._on_organize_complete_internal(results)
                if self.on_status_update:
                    self.on_status_update("Organization complete.")

            except Exception as e:
                logger.error(f"Organization failed: {e}")
                dpg.split_frame()
                self._show_error(f"Organization failed: {e}")
                dpg.configure_item("org_organize_btn", enabled=True)
                dpg.configure_item("org_cancel_btn", enabled=False)
                if self.on_status_update:
                    self.on_status_update("Organization failed.")

        self._organize_thread = threading.Thread(target=organize_thread)
        self._organize_thread.start()

    def _on_progress_update(self, progress: OrganizeProgress) -> None:
        """Handle progress updates from organizer.

        Args:
            progress: Current progress
        """
        # Update UI (called from worker thread, use split_frame)
        dpg.split_frame()

        pct = progress.processed_files / max(progress.total_files, 1)
        dpg.set_value(self.TAG_PROGRESS_BAR, pct)
        dpg.set_value(
            self.TAG_PROGRESS_TEXT,
            f"Status: {progress.state.title()} - "
            f"{progress.processed_files}/{progress.total_files} files "
            f"({progress.successful} OK, {progress.failed} failed)"
        )
        dpg.set_value(
            self.TAG_CURRENT_FILE,
            f"Current: {Path(progress.current_file).name}" if progress.current_file else ""
        )

    def _on_organize_complete_internal(self, results: list[OrganizeResult]) -> None:
        """Handle organization completion.

        Args:
            results: List of results
        """
        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success and r.action == "error")
        skipped = sum(1 for r in results if r.action == "skip")

        dpg.set_value(
            self.TAG_PROGRESS_TEXT,
            f"Complete! {successful} organized, {failed} failed, {skipped} skipped"
        )
        dpg.set_value(self.TAG_PROGRESS_BAR, 1.0)
        dpg.configure_item("org_organize_btn", enabled=True)
        dpg.configure_item("org_cancel_btn", enabled=False)

        # Clear preview
        self._current_preview = None

        if self.on_organize_complete:
            self.on_organize_complete(results)

    def _on_cancel_click(self) -> None:
        """Handle cancel button click."""
        if self._organizer:
            self._organizer.cancel()
            logger.info("Organization cancelled by user")

    def _on_export_click(self) -> None:
        """Handle export preview button click."""
        if self._current_preview is None:
            return

        # Export to CSV
        try:
            export_path = Path.home() / "Desktop" / "organize_preview.csv"

            with open(export_path, "w", encoding="utf-8") as f:
                f.write("Source,Destination,Date Source,Location,Event\n")
                for change in self._current_preview.changes:
                    f.write(
                        f'"{change.source_path}","{change.dest_path}",'
                        f'"{change.date_source or ""}","{change.location or ""}",'
                        f'"{change.event_name or ""}"\n'
                    )

            logger.info(f"Preview exported to {export_path}")
            # Could show success message in UI

        except Exception as e:
            logger.error(f"Export failed: {e}")
            self._show_error(f"Export failed: {e}")

    def _show_error(self, message: str) -> None:
        """Show an error message.

        Args:
            message: Error message
        """
        # Simple popup for now
        with dpg.window(
            label="Error",
            modal=True,
            width=400,
            height=150,
            pos=[400, 300],
            no_resize=True,
            tag="org_error_popup"
        ):
            dpg.add_text(message, wrap=380)
            dpg.add_spacer(height=20)
            dpg.add_button(
                label="OK",
                callback=lambda: dpg.delete_item("org_error_popup"),
                width=100
            )

    def refresh(self) -> None:
        """Refresh the panel."""
        # Reset state
        self._current_preview = None
        dpg.configure_item(self.TAG_PROGRESS_GROUP, show=False)
        dpg.configure_item("org_export_btn", enabled=False)

    def destroy(self) -> None:
        """Clean up resources."""
        if self._organizer:
            self._organizer.cancel()
        if self._organize_thread and self._organize_thread.is_alive():
            self._organize_thread.join(timeout=2.0)
