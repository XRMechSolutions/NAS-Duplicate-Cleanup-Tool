"""Photo Organizer Panel for DupliCleaner.

Dear PyGui UI component for organizing photos into date/location-based folder structures.
"""

import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

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
    LivePhotoHandling,
    ConflictResolution,
    UndatedHandling,
)
from duplicleaner.utils.logging import get_logger
from duplicleaner.ui.tooltips import add_tooltip, ORGANIZE_TOOLTIPS
from duplicleaner.ui.theme import get_status_color, get_accent_color, get_text_color

logger = get_logger(__name__)


def format_size(size_bytes: int) -> str:
    """Format byte size to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


class OrganizePanel:
    """UI panel for organizing photos into structured folder hierarchies."""

    # Tag constants
    TAG_PANEL = "organize_panel"
    TAG_SOURCE_INPUT = "org_source_input"
    TAG_DEST_INPUT = "org_dest_input"
    TAG_PREVIEW_TABLE = "org_preview_table"
    TAG_PREVIEW_GALLERY = "org_preview_gallery"
    TAG_PROGRESS_GROUP = "org_progress_group"
    TAG_PROGRESS_BAR = "org_progress_bar"
    TAG_PROGRESS_TEXT = "org_progress_text"
    TAG_CURRENT_FILE = "org_current_file"
    TAG_STATS_GROUP = "org_stats_group"
    TAG_SETTINGS_GROUP = "org_settings_group"
    TAG_FOLDER_TREE = "org_folder_tree"
    TAG_SOURCE_DIALOG = "org_source_dialog"
    TAG_DEST_DIALOG = "org_dest_dialog"
    TAG_EXPORT_DIALOG = "org_export_dialog"
    TAG_PREVIEW_BTN = "org_preview_btn"
    TAG_TEXTURE_REGISTRY = "org_texture_registry"

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
        self._preview_thread: Optional[threading.Thread] = None
        self._current_preview: Optional[OrganizePreview] = None
        self._operation_in_progress = False

        # Settings
        self._settings = OrganizeSettings()

        # UI State
        self._texture_registry: dict[str, int | str] = {}
        self._thumbnail_registry: dict[str, Any] = {}

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the panel UI."""
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            # Header
            dpg.add_text("Photo Organizer", color=get_accent_color())
            dpg.add_separator()
            dpg.add_spacer(height=10)

            # Source and destination
            with dpg.group():
                with dpg.group(horizontal=True):
                    dpg.add_text("Source Folder:", indent=0)
                    inp = dpg.add_input_text(
                        tag=self.TAG_SOURCE_INPUT,
                        width=400,
                        hint="Select folder with unorganized photos..."
                    )
                    add_tooltip(inp, ORGANIZE_TOOLTIPS["source_folder"])
                    dpg.add_button(label="Browse...", callback=self._on_browse_source)

                dpg.add_spacer(height=5)

                with dpg.group(horizontal=True):
                    dpg.add_text("Destination: ", indent=0)
                    inp = dpg.add_input_text(
                        tag=self.TAG_DEST_INPUT,
                        width=400,
                        hint="Select destination for organized photos..."
                    )
                    add_tooltip(inp, ORGANIZE_TOOLTIPS["dest_folder"])
                    dpg.add_button(label="Browse...", callback=self._on_browse_dest)

            dpg.add_spacer(height=10)

            # Statistics (updated after preview)
            with dpg.group(tag=self.TAG_STATS_GROUP):
                dpg.add_text("Run Preview to see organization statistics.", color=get_text_color("disabled"))

            dpg.add_spacer(height=10)

            # Settings collapsible section
            with dpg.collapsing_header(label="Organization Settings", default_open=True):
                with dpg.group(horizontal=True):
                    # Left column - Folder structure
                    with dpg.child_window(width=350, height=320, border=False):
                        dpg.add_text("Folder Structure", color=get_accent_color())
                        dpg.add_separator()

                        ctrl = dpg.add_combo(
                            label="Date Format",
                            items=["YYYY/MM", "YYYY/MM-Month", "YYYY/MM/DD", "YYYY/YYYY-MM-DD"],
                            default_value="YYYY/MM-Month",
                            callback=self._on_date_format_change,
                            tag="org_date_format"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["date_format"])

                        ctrl = dpg.add_checkbox(
                            label="Include Location in Folders",
                            default_value=False,
                            callback=self._on_location_toggle,
                            tag="org_include_location"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["include_location"])

                        ctrl = dpg.add_combo(
                            label="Location Detail",
                            items=["City Only", "City + Country", "City + State + Country"],
                            default_value="City Only",
                            callback=self._on_location_level_change,
                            tag="org_location_level"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["location_level"])

                        ctrl = dpg.add_checkbox(
                            label="Event Clustering",
                            default_value=False,
                            callback=self._on_event_toggle,
                            tag="org_event_clustering"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["event_clustering"])

                        with dpg.group(horizontal=True):
                            dpg.add_text("Event Gap (hours):")
                            ctrl = dpg.add_input_int(
                                default_value=4,
                                min_value=1,
                                max_value=48,
                                width=100,
                                callback=self._on_event_gap_change,
                                tag="org_event_gap"
                            )
                            add_tooltip(ctrl, ORGANIZE_TOOLTIPS["event_gap"])

                    # Middle column - File naming
                    with dpg.child_window(width=350, height=320, border=False):
                        dpg.add_text("File Naming", color=get_accent_color())
                        dpg.add_separator()

                        ctrl = dpg.add_checkbox(
                            label="Rename Files",
                            default_value=True,
                            callback=self._on_rename_toggle,
                            tag="org_rename_files"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["rename_files"])

                        ctrl = dpg.add_combo(
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
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["rename_pattern"])

                        ctrl = dpg.add_combo(
                            label="Conflict Resolution",
                            items=["Add Sequence Number", "Add Timestamp", "Skip", "Overwrite if Identical"],
                            default_value="Add Sequence Number",
                            callback=self._on_conflict_change,
                            tag="org_conflict"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["conflict_resolution"])

                    # Right column - Special handling
                    with dpg.child_window(width=350, height=320, border=False):
                        dpg.add_text("Special Handling", color=get_accent_color())
                        dpg.add_separator()

                        ctrl = dpg.add_combo(
                            label="Screenshots",
                            items=["Mix with Photos", "Separate Folder"],
                            default_value="Separate Folder",
                            callback=self._on_screenshot_change,
                            tag="org_screenshots"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["screenshots"])

                        ctrl = dpg.add_combo(
                            label="Burst Photos",
                            items=["Keep All", "Subfolder", "Flag for Review"],
                            default_value="Keep All",
                            callback=self._on_burst_change,
                            tag="org_bursts"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["bursts"])

                        ctrl = dpg.add_combo(
                            label="Live Photos",
                            items=["Keep Together", "Video Subfolder"],
                            default_value="Keep Together",
                            callback=self._on_livephoto_change,
                            tag="org_livephotos"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["live_photos"])

                        ctrl = dpg.add_combo(
                            label="Undated Photos",
                            items=["Undated Folder", "Use File Date", "Skip"],
                            default_value="Undated Folder",
                            callback=self._on_undated_change,
                            tag="org_undated"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["undated"])

                        dpg.add_spacer(height=10)

                        ctrl = dpg.add_checkbox(
                            label="Move Files (uncheck to copy)",
                            default_value=True,
                            callback=self._on_move_toggle,
                            tag="org_move_files"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["move_files"])

                        ctrl = dpg.add_checkbox(
                            label="Dry Run (preview only)",
                            default_value=False,
                            callback=self._on_dryrun_toggle,
                            tag="org_dry_run"
                        )
                        add_tooltip(ctrl, ORGANIZE_TOOLTIPS["dry_run"])

                    # AI column - New
                    with dpg.child_window(width=350, height=320, border=False):
                        dpg.add_text("AI Analysis", color=get_accent_color())
                        dpg.add_separator()
                        ctrl = dpg.add_checkbox(
                            label="Run Object Detection",
                            default_value=False,
                            callback=self._on_ai_settings_change,
                            tag="org_run_object_detection"
                        )
                        add_tooltip(ctrl, "Analyzes image content to generate searchable tags (e.g., 'dog', 'car'). Can be slow.")
                        ctrl = dpg.add_checkbox(
                            label="Run Document Classification",
                            default_value=False,
                            callback=self._on_ai_settings_change,
                            tag="org_run_doc_classification"
                        )
                        add_tooltip(ctrl, "Uses OCR to determine if an image is a document or a photo. Can be slow.")

            dpg.add_spacer(height=10)

            # Action buttons
            with dpg.group(horizontal=True):
                btn = dpg.add_button(
                    label="Preview Organization",
                    callback=self._on_preview_click,
                    width=150,
                    tag=self.TAG_PREVIEW_BTN
                )
                add_tooltip(btn, ORGANIZE_TOOLTIPS["preview"])
                btn = dpg.add_button(
                    label="Organize Now",
                    callback=self._on_organize_click,
                    width=150,
                    tag="org_organize_btn"
                )
                add_tooltip(btn, ORGANIZE_TOOLTIPS["organize"])
                dpg.add_spacer(width=20)
                btn = dpg.add_button(label="Cancel", callback=self._on_cancel_click, tag="org_cancel_btn", enabled=False)
                add_tooltip(btn, ORGANIZE_TOOLTIPS["cancel"])
                dpg.add_spacer(width=20)
                btn = dpg.add_button(label="Export Preview as CSV", callback=self._on_export_click, tag="org_export_btn", enabled=False)
                add_tooltip(btn, ORGANIZE_TOOLTIPS["export_csv"])

            dpg.add_spacer(height=10)

            # Progress section (initially hidden)
            with dpg.group(tag=self.TAG_PROGRESS_GROUP, show=False):
                dpg.add_separator()
                dpg.add_text("Organization Progress", color=get_accent_color())
                dpg.add_spacer(height=5)

                dpg.add_text("Status: Idle", tag=self.TAG_PROGRESS_TEXT)
                dpg.add_progress_bar(tag=self.TAG_PROGRESS_BAR, default_value=0.0, width=-1)
                dpg.add_text("Current: ", tag=self.TAG_CURRENT_FILE)

            dpg.add_spacer(height=10)

            # Preview section
            dpg.add_separator()
            dpg.add_text("Preview", color=get_accent_color())
            dpg.add_spacer(height=5)

            with dpg.tab_bar(tag="org_preview_tab_bar"):
                with dpg.tab(label="File List"):
                    # Two-column layout: folder tree and file list
                    with dpg.group(horizontal=True):
                        # Folder tree
                        with dpg.child_window(width=300, height=400, border=True):
                            dpg.add_text("Folders to Create", color=get_accent_color())
                            dpg.add_separator()
                            with dpg.tree_node(label="Organized Photos", tag=self.TAG_FOLDER_TREE, default_open=True):
                                dpg.add_text("Run preview to see folder structure", color=get_text_color("disabled"))

                        # File list table
                        with dpg.child_window(width=-1, height=400, border=True):
                            dpg.add_text("Files to Organize", color=get_accent_color())
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
                                dpg.add_table_column(label="Source", init_width_or_weight=200)
                                dpg.add_table_column(label="Destination", init_width_or_weight=300)
                                dpg.add_table_column(label="Date", init_width_or_weight=50)
                                dpg.add_table_column(label="Location", init_width_or_weight=80)
                                dpg.add_table_column(label="Burst", init_width_or_weight=50)
                                dpg.add_table_column(label="Live", init_width_or_weight=40)
                
                with dpg.tab(label="Image Gallery"):
                    with dpg.child_window(tag=self.TAG_PREVIEW_GALLERY, width=-1, height=400):
                        dpg.add_text("Run preview with AI analysis to see image gallery.", color=get_text_color("disabled"))


        # File dialogs
        self._create_file_dialogs()

        # Texture registry for thumbnails
        with dpg.texture_registry(tag=self.TAG_TEXTURE_REGISTRY):
            pass


    def _create_file_dialogs(self) -> None:
        """Create file/folder dialogs."""
        # Source folder dialog
        with dpg.file_dialog(
            directory_selector=True,
            show=False,
            callback=self._on_source_selected,
            cancel_callback=lambda: None,
            tag=self.TAG_SOURCE_DIALOG,
            width=700,
            height=400,
        ):
            pass

        # Destination folder dialog
        with dpg.file_dialog(
            directory_selector=True,
            show=False,
            callback=self._on_dest_selected,
            cancel_callback=lambda: None,
            tag=self.TAG_DEST_DIALOG,
            width=700,
            height=400,
        ):
            pass

        # Export file dialog
        with dpg.file_dialog(
            directory_selector=False,
            show=False,
            callback=self._on_export_path_selected,
            cancel_callback=lambda: None,
            tag=self.TAG_EXPORT_DIALOG,
            width=700,
            height=400,
            default_filename="organize_preview.csv",
        ):
            dpg.add_file_extension(".csv", color=(0, 255, 0, 255))

    def _on_browse_source(self) -> None:
        """Handle source browse button click."""
        dpg.show_item(self.TAG_SOURCE_DIALOG)

    def _on_browse_dest(self) -> None:
        """Handle destination browse button click."""
        dpg.show_item(self.TAG_DEST_DIALOG)

    def _on_source_selected(self, sender, app_data) -> None:
        """Handle source folder selection from dialog."""
        if not app_data or "file_path_name" not in app_data:
            return

        path = app_data["file_path_name"]
        if not Path(path).exists():
            self._show_error(f"Source folder does not exist: {path}")
            return
        if not Path(path).is_dir():
            self._show_error(f"Source path is not a directory: {path}")
            return

        dpg.set_value(self.TAG_SOURCE_INPUT, path)

    def _on_dest_selected(self, sender, app_data) -> None:
        """Handle destination folder selection from dialog."""
        if not app_data or "file_path_name" not in app_data:
            return

        path = app_data["file_path_name"]
        # Destination doesn't need to exist, but parent should
        parent = Path(path).parent
        if not parent.exists():
            self._show_error(f"Parent directory does not exist: {parent}")
            return

        dpg.set_value(self.TAG_DEST_INPUT, path)

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

        # Location level
        location_level_map = {
            "City Only": "city",
            "City + Country": "city_country",
            "City + State + Country": "full",
        }
        self._settings.location_level = location_level_map.get(
            dpg.get_value("org_location_level"), "city"
        )

        # Pattern
        self._settings.rename_pattern = dpg.get_value("org_rename_pattern")

        # Screenshots
        screenshot_map = {
            "Mix with Photos": ScreenshotHandling.MIX,
            "Separate Folder": ScreenshotHandling.SEPARATE,
        }
        self._settings.screenshot_handling = screenshot_map.get(
            dpg.get_value("org_screenshots"), ScreenshotHandling.SEPARATE
        )

        # Burst handling
        burst_map = {
            "Keep All": BurstHandling.KEEP_ALL,
            "Subfolder": BurstHandling.SUBFOLDER,
            "Flag for Review": BurstHandling.FLAG,
        }
        self._settings.burst_handling = burst_map.get(
            dpg.get_value("org_bursts"), BurstHandling.KEEP_ALL
        )

        # Live Photo handling
        livephoto_map = {
            "Keep Together": LivePhotoHandling.KEEP_TOGETHER,
            "Video Subfolder": LivePhotoHandling.VIDEO_SUBFOLDER,
        }
        self._settings.live_photo_handling = livephoto_map.get(
            dpg.get_value("org_livephotos"), LivePhotoHandling.KEEP_TOGETHER
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

        # AI Settings
        self._settings.run_object_detection = dpg.get_value("org_run_object_detection")
        self._settings.run_document_classification = dpg.get_value("org_run_doc_classification")

    def _on_date_format_change(self, sender, app_data) -> None:
        """Handle date format change."""
        self._update_settings_from_ui()

    def _on_location_toggle(self, sender, app_data) -> None:
        """Handle location toggle."""
        self._update_settings_from_ui()

    def _on_location_level_change(self, sender, app_data) -> None:
        """Handle location level change."""
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

    def _on_burst_change(self, sender, app_data) -> None:
        """Handle burst photo handling change."""
        self._update_settings_from_ui()

    def _on_livephoto_change(self, sender, app_data) -> None:
        """Handle live photo handling change."""
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

    def _on_ai_settings_change(self, sender, app_data) -> None:
        """Handle AI settings change."""
        self._update_settings_from_ui()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable action buttons during operations."""
        dpg.configure_item(self.TAG_PREVIEW_BTN, enabled=enabled)
        dpg.configure_item("org_organize_btn", enabled=enabled)
        # Export button depends on having a preview
        if enabled and self._current_preview:
            dpg.configure_item("org_export_btn", enabled=True)
        elif not enabled:
            dpg.configure_item("org_export_btn", enabled=False)

    def _on_preview_click(self) -> None:
        """Handle preview button click."""
        if self._operation_in_progress:
            self._show_error("An operation is already in progress.")
            return

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
        self._set_buttons_enabled(False)
        self._operation_in_progress = True

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
            finally:
                dpg.split_frame()
                self._operation_in_progress = False
                self._set_buttons_enabled(True)

        self._preview_thread = threading.Thread(target=preview_thread)
        self._preview_thread.start()

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
        # Second row for burst and live photo stats
        with dpg.group(parent=self.TAG_STATS_GROUP, horizontal=True):
            if preview.bursts_detected > 0:
                dpg.add_text(f"Burst Groups: {preview.bursts_detected}", color=get_status_color("warning"))
                dpg.add_spacer(width=20)
            if preview.live_photos_detected > 0:
                dpg.add_text(f"Live Photos: {preview.live_photos_detected}", color=get_status_color("info"))
                dpg.add_spacer(width=20)

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
                # Burst group column
                if change.burst_group is not None:
                    dpg.add_text(f"#{change.burst_group}", color=get_status_color("warning"))
                else:
                    dpg.add_text("")
                # Live photo column
                if change.is_live_photo:
                    dpg.add_text("Yes", color=get_status_color("info"))
                else:
                    dpg.add_text("")

        if len(preview.changes) > 500:
            with dpg.table_row(parent=self.TAG_PREVIEW_TABLE):
                dpg.add_text(f"... and {len(preview.changes) - 500} more files")
                dpg.add_text("")
                dpg.add_text("")
                dpg.add_text("")
                dpg.add_text("")
                dpg.add_text("")

        # Update image gallery
        self._update_gallery_view(preview)

        # Enable export and organize buttons
        dpg.configure_item("org_export_btn", enabled=True)

    def _update_gallery_view(self, preview: OrganizePreview) -> None:
        """Update the image gallery view with thumbnails and AI data."""
        # Clear existing gallery content
        dpg.delete_item(self.TAG_PREVIEW_GALLERY, children_only=True)

        # Unload previous textures
        for path, texture_id in self._texture_registry.items():
            if dpg.does_item_exist(texture_id):
                dpg.delete_item(texture_id)
        self._texture_registry.clear()

        # Filter for changes with thumbnails and add them to the gallery
        image_changes = [c for c in preview.changes if c.thumbnail_path]
        if not image_changes:
            dpg.add_text(
                "No images to display. Run preview on a folder with images.",
                parent=self.TAG_PREVIEW_GALLERY,
                color=get_text_color("disabled")
            )
            return

        for change in image_changes:
            if not change.thumbnail_path or not Path(change.thumbnail_path).exists():
                continue

            try:
                width, height, channels, data = dpg.load_image(change.thumbnail_path)
                texture_id = dpg.add_static_texture(width, height, data, parent=self.TAG_TEXTURE_REGISTRY)
                self._texture_registry[change.source_path] = texture_id

                with dpg.group(parent=self.TAG_PREVIEW_GALLERY, horizontal=True):
                    dpg.add_image(texture_id, width=128, height=128)
                    with dpg.group():
                        dpg.add_text(Path(change.source_path).name, wrap=400)
                        if change.is_document:
                            dpg.add_text("Type: Document", color=get_status_color("info"))
                        if change.ai_tags:
                            dpg.add_text(f"Tags: {', '.join(change.ai_tags)}", wrap=400)
                        dpg.add_text(f"-> {change.dest_path}", wrap=400, color=get_text_color("disabled"))
                dpg.add_separator(parent=self.TAG_PREVIEW_GALLERY)

            except Exception as e:
                logger.warning(f"Failed to load thumbnail for {change.source_path}: {e}")
                continue

    def _on_organize_click(self) -> None:
        """Handle organize button click."""
        if self._operation_in_progress:
            self._show_error("An operation is already in progress.")
            return

        if self._current_preview is None:
            self._show_error("Please run Preview first.")
            return

        source = dpg.get_value(self.TAG_SOURCE_INPUT).strip()
        dest = dpg.get_value(self.TAG_DEST_INPUT).strip()

        if not source or not dest:
            self._show_error("Source and destination are required.")
            return

        # Re-validate source still exists before organizing
        if not Path(source).exists():
            self._show_error(f"Source folder no longer exists: {source}")
            return

        # Show progress
        dpg.configure_item(self.TAG_PROGRESS_GROUP, show=True)
        dpg.configure_item("org_cancel_btn", enabled=True)
        self._set_buttons_enabled(False)
        self._operation_in_progress = True

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
                self._set_buttons_enabled(True)
                dpg.configure_item("org_cancel_btn", enabled=False)
                dpg.configure_item(self.TAG_PROGRESS_GROUP, show=False)
                if self.on_status_update:
                    self.on_status_update("Organization failed.")
            finally:
                dpg.split_frame()
                self._operation_in_progress = False

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
        dpg.configure_item("org_cancel_btn", enabled=False)

        # Clear preview and re-enable buttons
        self._current_preview = None
        self._set_buttons_enabled(True)
        # Export disabled since preview is cleared
        dpg.configure_item("org_export_btn", enabled=False)

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
        # Show file save dialog
        dpg.show_item(self.TAG_EXPORT_DIALOG)

    def _on_export_path_selected(self, sender, app_data) -> None:
        """Handle export path selection from dialog."""
        if not app_data or "file_path_name" not in app_data:
            return

        export_path = Path(app_data["file_path_name"])

        # Ensure .csv extension
        if export_path.suffix.lower() != ".csv":
            export_path = export_path.with_suffix(".csv")

        try:
            with open(export_path, "w", encoding="utf-8") as f:
                f.write("Source,Destination,Date Source,Location,Event,Burst Group,Live Photo\n")
                for change in self._current_preview.changes:
                    burst_str = str(change.burst_group) if change.burst_group is not None else ""
                    live_str = "Yes" if change.is_live_photo else ""
                    f.write(
                        f'"{change.source_path}","{change.dest_path}",'
                        f'"{change.date_source or ""}","{change.location or ""}",'
                        f'"{change.event_name or ""}","{burst_str}","{live_str}"\n'
                    )

            logger.info(f"Preview exported to {export_path}")
            self._show_message("Export Successful", f"Preview exported to:\n{export_path}")

        except PermissionError:
            logger.error(f"Permission denied exporting preview to {export_path}")
            self._show_error("Permission denied. Close the file if it's open in another program.")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            self._show_error(f"Export failed: {e}")

    def _show_message(self, title: str, message: str) -> None:
        """Show an informational message.

        Args:
            title: Dialog title
            message: Message to display
        """
        popup_tag = f"org_msg_popup_{uuid.uuid4().hex[:8]}"
        with dpg.window(
            label=title,
            modal=True,
            width=450,
            height=150,
            pos=[400, 300],
            no_resize=True,
            tag=popup_tag
        ):
            dpg.add_text(message, wrap=430)
            dpg.add_spacer(height=20)
            dpg.add_button(
                label="OK",
                callback=lambda: dpg.delete_item(popup_tag),
                width=100
            )

    def _show_error(self, message: str) -> None:
        """Show an error message.

        Args:
            message: Error message
        """
        popup_tag = f"org_error_popup_{uuid.uuid4().hex[:8]}"
        with dpg.window(
            label="Error",
            modal=True,
            width=400,
            height=150,
            pos=[400, 300],
            no_resize=True,
            tag=popup_tag
        ):
            dpg.add_text(message, wrap=380)
            dpg.add_spacer(height=20)
            dpg.add_button(
                label="OK",
                callback=lambda: dpg.delete_item(popup_tag),
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
        # Cancel any running organizer
        if self._organizer:
            self._organizer.cancel()

        # Wait for preview thread
        if self._preview_thread and self._preview_thread.is_alive():
            self._preview_thread.join(timeout=2.0)
            self._preview_thread = None

        # Wait for organize thread
        if self._organize_thread and self._organize_thread.is_alive():
            self._organize_thread.join(timeout=2.0)
            self._organize_thread = None

        # Clear state
        self._current_preview = None
        self._organizer = None
        self._operation_in_progress = False
