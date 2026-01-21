"""DupliCleaner main application.

Dear PyGui application with tabbed interface for managing duplicate files,
organizing photos, and AI-powered content analysis.
"""

from pathlib import Path
from typing import Callable, Optional

import os

import dearpygui.dearpygui as dpg

from duplicleaner.utils.logging import get_logger, setup_logging
from duplicleaner.utils.config import get_config, save_config
from duplicleaner.db.database import get_database
from duplicleaner.ui.search_panel import SearchPanel
from duplicleaner.ui.status_log_panel import StatusLogPanel
from duplicleaner.drives.manager import DriveManager, normalize_path
from duplicleaner.ai.model_manager import ModelManager
from duplicleaner.ui.drives_panel import DrivesPanel
from duplicleaner.ui.duplicates_panel import DuplicatesPanel
from duplicleaner.ui.organize_panel import OrganizePanel
from duplicleaner.ui.faces_panel import FacesPanel
from duplicleaner.core.versioning_service import VersioningService
from duplicleaner.core.versioning import VersionTracker, VersionEntry, ChangeEntry

logger = get_logger(__name__)


class DupliCleanerApp:
    """Main application class."""

    # Tag constants for UI elements
    TAG_MAIN_WINDOW = "main_window"
    TAG_TAB_BAR = "main_tab_bar"
    TAG_STATUS_BAR = "status_bar"
    TAG_STATUS_TEXT = "status_text"
    TAG_FILE_COUNT = "file_count"
    TAG_STORAGE_INFO = "storage_info"
    TAG_GPU_STATUS = "gpu_status"

    # Tab tags
    TAG_TAB_DRIVES = "tab_drives"
    TAG_TAB_DUPLICATES = "tab_duplicates"
    TAG_TAB_ORGANIZE = "tab_organize"
    TAG_TAB_FACES = "tab_faces"
    TAG_TAB_SEARCH = "tab_search"
    TAG_TAB_SETTINGS = "tab_settings"
    TAG_TAB_LOG = "tab_log"

    # Content area tags
    TAG_CONTENT_DRIVES = "content_drives"
    TAG_CONTENT_DUPLICATES = "content_duplicates"
    TAG_CONTENT_ORGANIZE = "content_organize"
    TAG_CONTENT_FACES = "content_faces"
    TAG_CONTENT_SEARCH = "content_search"
    TAG_CONTENT_SETTINGS = "content_settings"
    TAG_CONTENT_LOG = "content_log"

    # Versioning settings tags
    TAG_VERSION_FOLDER_INPUT = "version_folder_input"
    TAG_VERSION_FOLDER_LIST = "version_folder_list"
    TAG_VERSION_INCLUDE_SUBFOLDERS = "version_include_subfolders"
    TAG_VERSION_AUTO_MODE = "version_auto_mode"
    TAG_VERSION_MAX_SIZE = "version_max_size"
    TAG_VERSION_FILE_INPUT = "version_file_input"
    TAG_VERSION_HISTORY_DIALOG = "version_history_dialog"
    TAG_VERSION_HISTORY_TABLE = "version_history_table"
    TAG_VERSION_HISTORY_LABEL = "version_history_label"
    TAG_VERSION_RESTORE_BUTTON = "version_restore_button"
    TAG_VERSION_RECENT_TABLE = "version_recent_table"
    TAG_VERSION_FILE_DIALOG = "version_file_dialog"
    TAG_VERSION_OPEN_BUTTON = "version_open_button"
    TAG_VERSION_DIFF_TEXT = "version_diff_text"
    TAG_VERSION_DIFF_LABEL = "version_diff_label"
    TAG_MODEL_STATUS_FACES = "model_status_faces"
    TAG_MODEL_STATUS_CLIP = "model_status_clip"
    TAG_MODEL_STATUS_YOLO = "model_status_yolo"
    TAG_MODEL_STATUS_OCR = "model_status_ocr"

    def __init__(self) -> None:
        """Initialize the application."""
        self.config = get_config()
        self.db = get_database()
        self.search_panel: Optional[SearchPanel] = None
        self.status_log_panel: Optional[StatusLogPanel] = None
        self.drive_manager = DriveManager(self.db)
        self._wizard_step = 0
        self.versioning_service = VersioningService(self.config.versioning)
        self._version_history_entries: list[VersionEntry] = []
        self._version_history_file: Optional[Path] = None
        self._selected_history_commit: Optional[str] = None
        self.drives_panel: Optional[DrivesPanel] = None
        self.duplicates_panel: Optional[DuplicatesPanel] = None
        self.organize_panel: Optional[OrganizePanel] = None
        self.faces_panel: Optional[FacesPanel] = None
        self._model_download_state: dict[str, str] = {}

        # Callback registry
        self._callbacks: dict[str, list[Callable]] = {}

        logger.info("DupliCleaner application initialized")

    def setup(self) -> None:
        """Set up Dear PyGui context and create the UI."""
        dpg.create_context()

        # Configure viewport
        dpg.create_viewport(
            title="DupliCleaner",
            width=self.config.ui.window_width,
            height=self.config.ui.window_height,
            min_width=800,
            min_height=600,
        )

        # Set up theme
        self._setup_theme()

        # Create main window
        self._create_main_window()
        self._create_setup_wizard()

        # Set up Dear PyGui
        dpg.setup_dearpygui()
        dpg.show_viewport()

        # Set the main window as primary
        dpg.set_primary_window(self.TAG_MAIN_WINDOW, True)

        if self.config.first_run:
            dpg.show_item("setup_wizard")

        logger.info("UI setup complete")

    def _setup_theme(self) -> None:
        """Set up the application theme."""
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                # Colors for dark theme
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (30, 30, 30))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (40, 40, 40))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (60, 60, 60))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (50, 50, 50))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (70, 70, 70))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (80, 80, 80))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (40, 40, 40))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (50, 50, 50))
                dpg.add_theme_color(dpg.mvThemeCol_Tab, (50, 50, 50))
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (70, 100, 140))
                dpg.add_theme_color(dpg.mvThemeCol_TabActive, (60, 90, 130))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (60, 90, 130))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (70, 100, 140))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (80, 110, 150))
                dpg.add_theme_color(dpg.mvThemeCol_Header, (60, 90, 130))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (70, 100, 140))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (80, 110, 150))

                # Styling
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 4)

        dpg.bind_theme(global_theme)

    def _create_main_window(self) -> None:
        """Create the main application window."""
        with dpg.window(
            tag=self.TAG_MAIN_WINDOW,
            label="DupliCleaner",
            no_title_bar=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
            no_close=True,
        ):
            # Tab bar for main navigation
            with dpg.tab_bar(tag=self.TAG_TAB_BAR):
                # Drives tab
                with dpg.tab(label="Drives", tag=self.TAG_TAB_DRIVES):
                    self._create_drives_panel()

                # Duplicates tab
                with dpg.tab(label="Duplicates", tag=self.TAG_TAB_DUPLICATES):
                    self._create_duplicates_panel()

                # Organize tab
                with dpg.tab(label="Organize", tag=self.TAG_TAB_ORGANIZE):
                    self._create_organize_panel()

                # Faces tab
                with dpg.tab(label="Faces", tag=self.TAG_TAB_FACES):
                    self._create_faces_panel()

                # Search tab
                with dpg.tab(label="Search", tag=self.TAG_TAB_SEARCH):
                    self._create_search_panel()

                # Settings tab
                with dpg.tab(label="Settings", tag=self.TAG_TAB_SETTINGS):
                    self._create_settings_panel()

                # Status Log tab
                with dpg.tab(label="Log", tag=self.TAG_TAB_LOG):
                    self._create_log_panel()

            # Status bar at bottom
            dpg.add_spacer(height=10)
            self._create_status_bar(parent=self.TAG_MAIN_WINDOW)

    def _create_drives_panel(self) -> None:
        """Create the drives management panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_DRIVES, autosize_x=True, autosize_y=True):
            self.drives_panel = DrivesPanel(
                parent=self.TAG_CONTENT_DRIVES,
                on_status_update=self.update_status,
            )

    def _create_duplicates_panel(self) -> None:
        """Create the duplicates review panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_DUPLICATES, autosize_x=True, autosize_y=True):
            self.duplicates_panel = DuplicatesPanel(
                parent=self.TAG_CONTENT_DUPLICATES,
                on_status_update=self.update_status,
            )

    def _create_organize_panel(self) -> None:
        """Create the photo organization panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_ORGANIZE, autosize_x=True, autosize_y=True):
            self.organize_panel = OrganizePanel(
                parent=self.TAG_CONTENT_ORGANIZE,
                on_status_update=self.update_status,
            )

    def _create_faces_panel(self) -> None:
        """Create the face recognition panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_FACES, autosize_x=True, autosize_y=True):
            self.faces_panel = FacesPanel(
                parent=self.TAG_CONTENT_FACES,
                on_status_update=self.update_status,
            )

    def _create_search_panel(self) -> None:
        """Create the search panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_SEARCH, autosize_x=True, autosize_y=True):
            self.search_panel = SearchPanel(
                parent=self.TAG_CONTENT_SEARCH,
                on_status_update=self.update_status,
            )

    def _create_log_panel(self) -> None:
        """Create the status log panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_LOG, autosize_x=True, autosize_y=True):
            self.status_log_panel = StatusLogPanel(parent=self.TAG_CONTENT_LOG)

    def _create_setup_wizard(self) -> None:
        """Create the first-run setup wizard."""
        with dpg.window(
            tag="setup_wizard",
            label="DupliCleaner Setup",
            modal=True,
            show=False,
            width=600,
            height=420,
            no_resize=True,
            no_close=True,
        ):
            dpg.add_text("Welcome to DupliCleaner", color=(150, 200, 255))
            dpg.add_separator()

            # Step containers
            with dpg.group(tag="wizard_step_0"):
                dpg.add_text("This wizard will help you get started.")
                dpg.add_spacer(height=10)
                dpg.add_text("You'll choose drives to scan and set basic AI options.")

            with dpg.group(tag="wizard_step_1", show=False):
                dpg.add_text("Step 1: Add a drive or folder to scan")
                dpg.add_spacer(height=5)
                with dpg.group(horizontal=True):
                    dpg.add_input_text(tag="wizard_drive_path", width=360, hint="C:\\Photos or \\\\NAS\\share")
                    dpg.add_button(label="Add", callback=self._wizard_add_drive)
                    dpg.add_button(label="Browse...", callback=self._wizard_browse_drive)
                dpg.add_input_text(tag="wizard_drive_label", width=360, hint="Drive label (optional)")
                dpg.add_spacer(height=5)
                dpg.add_text("Registered Drives:")
                dpg.add_listbox(tag="wizard_drive_list", items=[], width=520, num_items=6)
                dpg.add_spacer(height=5)
                dpg.add_text("", tag="wizard_drive_status", color=(255, 180, 100))

            with dpg.group(tag="wizard_step_2", show=False):
                dpg.add_text("Step 2: AI Settings")
                dpg.add_checkbox(
                    label="Enable AI features",
                    tag="wizard_ai_enabled",
                    default_value=self.config.ai.enabled,
                )
                dpg.add_checkbox(
                    label="Use GPU acceleration (if available)",
                    tag="wizard_ai_gpu",
                    default_value=self.config.ai.use_gpu,
                )

            with dpg.group(tag="wizard_step_3", show=False):
                dpg.add_text("Step 3: Download AI Models (optional)")
                dpg.add_spacer(height=5)
                dpg.add_checkbox(label="Face recognition (InsightFace)", tag="wizard_model_faces", default_value=True)
                dpg.add_text("Status: Not downloaded", tag="wizard_status_faces", color=(180, 180, 180))
                dpg.add_checkbox(label="Scene search (CLIP)", tag="wizard_model_clip", default_value=True)
                dpg.add_text("Status: Not downloaded", tag="wizard_status_clip", color=(180, 180, 180))
                dpg.add_checkbox(label="Object detection (YOLO)", tag="wizard_model_yolo", default_value=True)
                dpg.add_text("Status: Not downloaded", tag="wizard_status_yolo", color=(180, 180, 180))
                dpg.add_checkbox(label="OCR (EasyOCR)", tag="wizard_model_ocr", default_value=True)
                dpg.add_text("Status: Not downloaded", tag="wizard_status_ocr", color=(180, 180, 180))
                dpg.add_spacer(height=5)
                dpg.add_text("Downloads happen on first use if skipped.")

            with dpg.group(tag="wizard_step_4", show=False):
                dpg.add_text("Setup Complete")
                dpg.add_spacer(height=10)
                dpg.add_text("You're ready to start scanning and deduping.")

            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Back", tag="wizard_back", callback=self._wizard_back, enabled=False)
                dpg.add_button(label="Next", tag="wizard_next", callback=self._wizard_next)

        with dpg.file_dialog(
            tag="wizard_drive_dialog",
            show=False,
            modal=True,
            width=700,
            height=400,
            directory_selector=True,
            callback=self._wizard_drive_selected,
        ):
            dpg.add_file_extension(".*", color=(255, 255, 255))

    def _wizard_add_drive(self) -> None:
        """Add a drive from wizard inputs."""
        path = dpg.get_value("wizard_drive_path").strip().strip('"')
        label = dpg.get_value("wizard_drive_label").strip()

        if not path:
            self._set_wizard_status("Enter a path to add a drive.", level="warning")
            return

        normalized = normalize_path(path)
        for drive in self.drive_manager.get_all_drives():
            if normalize_path(drive.path) == normalized:
                self._refresh_wizard_drive_list()
                self._set_wizard_status("Drive already registered.", level="warning")
                return

        if not label:
            label = Path(path).name or "Drive"

        try:
            self.drive_manager.add_drive(path, label)
            self._refresh_wizard_drive_list()
            dpg.set_value("wizard_drive_path", "")
            dpg.set_value("wizard_drive_label", "")
            self._set_wizard_status("Drive added.", level="info")
        except ValueError as exc:
            self._set_wizard_status(f"Failed to add drive: {exc}", level="error")

    def _show_setup_wizard(self) -> None:
        """Show the setup wizard from settings."""
        self._wizard_step = 0
        for step in range(5):
            dpg.configure_item(f"wizard_step_{step}", show=(step == 0))
        dpg.configure_item("wizard_back", enabled=False)
        dpg.configure_item("wizard_next", label="Next")
        self._refresh_wizard_drive_list()
        dpg.show_item("setup_wizard")

    def _refresh_wizard_drive_list(self) -> None:
        """Refresh wizard drive list from database."""
        drives = self.drive_manager.get_all_drives()
        items = [f"{d.label}  ({d.path})" for d in drives]
        dpg.configure_item("wizard_drive_list", items=items)

    def _wizard_browse_drive(self) -> None:
        """Show folder browser for wizard drive."""
        dpg.show_item("wizard_drive_dialog")

    def _wizard_drive_selected(self, sender, app_data) -> None:
        """Handle drive selection from dialog."""
        path = app_data.get("file_path_name")
        if path:
            dpg.set_value("wizard_drive_path", path)

    def _set_wizard_status(self, message: str, level: str = "info") -> None:
        """Update wizard-local status text."""
        color_map = {
            "info": (180, 180, 180),
            "warning": (255, 180, 100),
            "error": (255, 120, 120),
        }
        dpg.set_value("wizard_drive_status", message)
        dpg.configure_item("wizard_drive_status", color=color_map.get(level, (180, 180, 180)))
        self.update_status(message, level=level)

    def _wizard_next(self) -> None:
        """Advance wizard."""
        if self._wizard_step == 1:
            # Ensure at least one drive
            if not self.drive_manager.get_all_drives():
                self._set_wizard_status("Add at least one drive before continuing.", level="warning")
                return

        if self._wizard_step == 2:
            self.config.ai.enabled = dpg.get_value("wizard_ai_enabled")
            self.config.ai.use_gpu = dpg.get_value("wizard_ai_gpu")

        if self._wizard_step == 3:
            self._wizard_download_models()

        if self._wizard_step >= 4:
            self.config.first_run = False
            save_config()
            dpg.hide_item("setup_wizard")
            self.update_status("Setup complete. Ready.")
            return

        dpg.configure_item(f"wizard_step_{self._wizard_step}", show=False)
        self._wizard_step += 1
        dpg.configure_item(f"wizard_step_{self._wizard_step}", show=True)
        dpg.configure_item("wizard_back", enabled=self._wizard_step > 0)
        if self._wizard_step == 4:
            dpg.configure_item("wizard_next", label="Finish")

    def _wizard_back(self) -> None:
        """Go back in wizard."""
        if self._wizard_step == 0:
            return
        dpg.configure_item(f"wizard_step_{self._wizard_step}", show=False)
        self._wizard_step -= 1
        dpg.configure_item(f"wizard_step_{self._wizard_step}", show=True)
        dpg.configure_item("wizard_back", enabled=self._wizard_step > 0)
        dpg.configure_item("wizard_next", label="Next")

    def _wizard_download_models(self) -> None:
        """Placeholder for model download selection."""
        selections = []
        if dpg.get_value("wizard_model_faces"):
            selections.append("Faces")
        if dpg.get_value("wizard_model_clip"):
            selections.append("CLIP")
        if dpg.get_value("wizard_model_yolo"):
            selections.append("YOLO")
        if dpg.get_value("wizard_model_ocr"):
            selections.append("OCR")

        if not selections:
            self.update_status("No model downloads selected.")
            return

        self.update_status(f"Downloading models: {', '.join(selections)}")

        def run_downloads() -> None:
            manager = ModelManager(progress_callback=lambda msg: self.update_status(msg))
            mapping = [
                ("Faces", "faces", "wizard_status_faces", manager.download_faces),
                ("CLIP", "clip", "wizard_status_clip", manager.download_clip),
                ("YOLO", "yolo", "wizard_status_yolo", manager.download_yolo),
                ("OCR", "ocr", "wizard_status_ocr", manager.download_ocr),
            ]

            for label, key, tag, fn in mapping:
                if label not in selections:
                    continue
                self._set_wizard_model_status(tag, "Downloading...", (150, 200, 255))
                result = fn()
                if result.success:
                    self.config.ai.downloaded_models[key] = True
                    save_config()
                color = (120, 220, 140) if result.success else (255, 180, 100)
                self._set_wizard_model_status(tag, result.message, color)
                level = "info" if result.success else "warning"
                self.update_status(result.message, level=level)

        import threading
        thread = threading.Thread(target=run_downloads, daemon=True)
        thread.start()

    def _set_wizard_model_status(self, tag: str, text: str, color: tuple[int, int, int]) -> None:
        """Update wizard model status label safely."""
        try:
            dpg.split_frame()
            dpg.set_value(tag, text)
            dpg.configure_item(tag, color=color)
        except Exception:
            pass

    def _create_settings_panel(self) -> None:
        """Create the settings panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_SETTINGS, autosize_x=True, autosize_y=True):
            dpg.add_text("Settings", color=(150, 200, 255))
            dpg.add_separator()
            dpg.add_spacer(height=10)

            # General settings
            dpg.add_text("General", color=(200, 200, 200))
            dpg.add_checkbox(
                label="Confirm before destructive actions",
                tag="settings_confirm_destructive",
                default_value=self.config.actions.confirm_destructive
            )
            dpg.add_checkbox(
                label="Create audit log for all actions",
                tag="settings_create_audit_log",
                default_value=self.config.actions.create_audit_log
            )

            dpg.add_spacer(height=10)
            dpg.add_button(label="Run Setup Wizard", callback=self._show_setup_wizard)

            # Duplicate detection settings
            dpg.add_text("Duplicate Detection", color=(200, 200, 200))
            with dpg.group(horizontal=True):
                dpg.add_text("Near-duplicate threshold:")
                dpg.add_slider_float(
                    tag="settings_near_duplicate_threshold",
                    default_value=self.config.duplicates.near_duplicate_threshold,
                    min_value=0.5,
                    max_value=1.0,
                    width=200
                )
            dpg.add_checkbox(
                label="Match across formats (JPEG/PNG/HEIC)",
                tag="settings_match_formats",
                default_value=self.config.duplicates.match_across_formats
            )

            dpg.add_spacer(height=10)

            # Scan optimization
            dpg.add_text("Scan Optimization", color=(200, 200, 200))
            with dpg.group(horizontal=True):
                dpg.add_text("Min image size for near-duplicate checks:")
                dpg.add_input_int(
                    tag="settings_min_image_size",
                    default_value=self.config.duplicates.min_image_size,
                    min_value=0,
                    max_value=5000,
                    width=120,
                )
            with dpg.group(horizontal=True):
                dpg.add_text("Max file size (GB) to scan:")
                dpg.add_input_float(
                    tag="settings_max_file_size_gb",
                    default_value=self.config.scan.max_file_size_gb,
                    min_value=0.1,
                    max_value=500.0,
                    width=120,
                )
            dpg.add_checkbox(
                label="Process videos for near-duplicates (expensive)",
                tag="settings_process_videos",
                default_value=self.config.ai.process_videos,
            )

            dpg.add_spacer(height=10)

            # AI settings
            dpg.add_text("AI Features", color=(200, 200, 200))
            dpg.add_checkbox(
                label="Enable AI features",
                tag="settings_ai_enabled",
                default_value=self.config.ai.enabled
            )
            dpg.add_checkbox(
                label="Use GPU acceleration",
                tag="settings_ai_use_gpu",
                default_value=self.config.ai.use_gpu
            )

            dpg.add_spacer(height=10)

            # AI model management
            dpg.add_text("AI Models", color=(200, 200, 200))
            with dpg.table(
                header_row=True,
                borders_innerH=True,
                borders_outerH=True,
                borders_innerV=True,
                borders_outerV=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                row_background=True,
                height=160,
            ):
                dpg.add_table_column(label="Model", init_width_or_weight=170)
                dpg.add_table_column(label="Status", init_width_or_weight=200)
                dpg.add_table_column(label="Action", init_width_or_weight=120)

                self._add_model_row("Face recognition (InsightFace)", "faces", self.TAG_MODEL_STATUS_FACES)
                self._add_model_row("Scene search (CLIP)", "clip", self.TAG_MODEL_STATUS_CLIP)
                self._add_model_row("Object detection (YOLO)", "yolo", self.TAG_MODEL_STATUS_YOLO)
                self._add_model_row("OCR (EasyOCR)", "ocr", self.TAG_MODEL_STATUS_OCR)

            dpg.add_spacer(height=5)
            dpg.add_button(label="Refresh Model Status", callback=self._refresh_model_status)
            dpg.add_button(label="Verify Models", tag="verify_models_btn", callback=self._verify_models)
            dpg.add_text("Install AI deps: python -m pip install -r requirements-ai.txt", color=(150, 150, 150))

            dpg.add_spacer(height=20)

            # Version tracking settings
            dpg.add_text("Version Tracking", color=(200, 200, 200))
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    tag=self.TAG_VERSION_FOLDER_INPUT,
                    width=400,
                    hint="Folder to track..."
                )
                dpg.add_button(label="Add Folder", callback=self._on_add_tracked_folder)
                dpg.add_button(label="Remove Selected", callback=self._on_remove_tracked_folder)

            dpg.add_spacer(height=5)
            dpg.add_listbox(
                tag=self.TAG_VERSION_FOLDER_LIST,
                items=self.config.versioning.tracked_folders,
                width=600,
                num_items=4,
            )

            dpg.add_spacer(height=5)
            dpg.add_checkbox(
                label="Include subfolders",
                tag=self.TAG_VERSION_INCLUDE_SUBFOLDERS,
                default_value=self.config.versioning.include_subfolders,
                callback=self._on_versioning_settings_changed,
            )
            with dpg.group(horizontal=True):
                dpg.add_text("Auto-commit mode:")
                dpg.add_combo(
                    tag=self.TAG_VERSION_AUTO_MODE,
                    items=["on_save", "interval", "daily", "manual"],
                    default_value=self.config.versioning.auto_commit_mode,
                    width=120,
                    callback=self._on_versioning_settings_changed,
                )
                dpg.add_spacer(width=10)
                dpg.add_text("Max file size (MB):")
                dpg.add_input_float(
                    tag=self.TAG_VERSION_MAX_SIZE,
                    default_value=self.config.versioning.max_file_size_mb,
                    min_value=1.0,
                    max_value=500.0,
                    width=100,
                    callback=self._on_versioning_settings_changed,
                )

            dpg.add_spacer(height=20)

            # Version history tools
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    tag=self.TAG_VERSION_FILE_INPUT,
                    width=400,
                    hint="File path for history..."
                )
                dpg.add_button(label="Browse...", callback=self._show_version_file_dialog)
                dpg.add_button(label="View History", callback=self._on_view_history)
                dpg.add_button(label="Save Version", callback=self._on_save_version)

            dpg.add_spacer(height=10)
            dpg.add_text("Recent Changes", color=(200, 200, 200))
            with dpg.child_window(height=180, border=True):
                with dpg.table(
                    tag=self.TAG_VERSION_RECENT_TABLE,
                    header_row=True,
                    borders_innerH=True,
                    borders_outerH=True,
                    borders_innerV=True,
                    borders_outerV=True,
                    resizable=True,
                    policy=dpg.mvTable_SizingStretchProp,
                    row_background=True,
                    scrollY=True,
                    height=150,
                ):
                    dpg.add_table_column(label="File", init_width_or_weight=140)
                    dpg.add_table_column(label="Date", init_width_or_weight=120)
                    dpg.add_table_column(label="Message", init_width_or_weight=240)

            # Save button
            dpg.add_button(label="Save Settings", callback=self._on_save_settings)

            self._create_version_history_dialog()
            self._create_version_file_dialog()
            self._refresh_recent_changes()
            self._refresh_model_status()

    def _create_status_bar(self, parent: int | str) -> None:
        """Create the status bar at the bottom of the window."""
        with dpg.group(horizontal=True, tag=self.TAG_STATUS_BAR, parent=parent):
            dpg.add_text("Ready", tag=self.TAG_STATUS_TEXT)
            dpg.add_spacer(width=50)
            dpg.add_text("Files: 0", tag=self.TAG_FILE_COUNT)
            dpg.add_spacer(width=50)
            dpg.add_text("Storage: 0 GB", tag=self.TAG_STORAGE_INFO)
            dpg.add_spacer(width=50)
            dpg.add_text("GPU: Checking...", tag=self.TAG_GPU_STATUS)

    def update_status(self, message: str, level: str = "info") -> None:
        """Update the status bar message."""
        dpg.set_value(self.TAG_STATUS_TEXT, message)
        if self.status_log_panel:
            self.status_log_panel.add(message, level=level)

    def _add_model_row(self, label: str, key: str, status_tag: str) -> None:
        """Add a model status row in the settings table."""
        with dpg.table_row():
            dpg.add_text(label)
            dpg.add_text("", tag=status_tag)
            dpg.add_button(
                label="Download",
                tag=f"model_download_{key}",
                callback=lambda s, a, u: self._download_model(u),
                user_data=key,
            )

    def _refresh_model_status(self) -> None:
        """Refresh AI model status labels."""
        status_map = {
            "faces": self.TAG_MODEL_STATUS_FACES,
            "clip": self.TAG_MODEL_STATUS_CLIP,
            "yolo": self.TAG_MODEL_STATUS_YOLO,
            "ocr": self.TAG_MODEL_STATUS_OCR,
        }

        for key, tag in status_map.items():
            text, color = self._get_model_status(key)
            dpg.set_value(tag, text)
            dpg.configure_item(tag, color=color)
            dpg.configure_item(
                f"model_download_{key}",
                enabled=self._model_download_state.get(key) not in {"downloading", "verifying"},
            )

        any_active = any(
            state in {"downloading", "verifying"} for state in self._model_download_state.values()
        )
        dpg.configure_item("verify_models_btn", enabled=not any_active)

    def _get_model_status(self, key: str) -> tuple[str, tuple[int, int, int]]:
        """Get display status for a model."""
        if self._model_download_state.get(key) == "downloading":
            return ("Downloading...", (150, 200, 255))
        if self._model_download_state.get(key) == "verifying":
            return ("Verifying...", (150, 200, 255))

        if not self._model_dependency_ok(key):
            return ("Missing dependency", (255, 180, 100))

        if self.config.ai.downloaded_models.get(key):
            return ("Ready", (120, 220, 140))

        return ("Not downloaded", (180, 180, 180))

    def _model_dependency_ok(self, key: str) -> bool:
        """Check if a model dependency is installed."""
        try:
            if key == "faces":
                import insightface  # noqa: F401
            elif key == "clip":
                import open_clip  # noqa: F401
            elif key == "yolo":
                import ultralytics  # noqa: F401
            elif key == "ocr":
                import easyocr  # noqa: F401
        except Exception:
            return False
        return True

    def _download_model(self, key: str) -> None:
        """Download a specific AI model in the background."""
        if not self._model_dependency_ok(key):
            self.update_status(f"Missing dependency for {key}.", level="warning")
            self._refresh_model_status()
            return

        self._model_download_state[key] = "downloading"
        self._refresh_model_status()
        self.update_status(f"Downloading {key} model...")

        def run_download() -> None:
            manager = ModelManager(progress_callback=lambda msg: self.update_status(msg))
            if key == "faces":
                result = manager.download_faces()
            elif key == "clip":
                result = manager.download_clip()
            elif key == "yolo":
                result = manager.download_yolo()
            else:
                result = manager.download_ocr()

            if result.success:
                self.config.ai.downloaded_models[key] = True
                save_config()
            level = "info" if result.success else "warning"
            self.update_status(result.message, level=level)
            self._model_download_state.pop(key, None)
            dpg.split_frame()
            self._refresh_model_status()

        import threading
        thread = threading.Thread(target=run_download, daemon=True)
        thread.start()

    def _verify_models(self) -> None:
        """Verify model availability by attempting a lightweight load."""
        if any(state in {"downloading", "verifying"} for state in self._model_download_state.values()):
            self.update_status("Model download/verify already in progress.", level="warning")
            return

        keys = ["faces", "clip", "yolo", "ocr"]

        def run_verify() -> None:
            manager = ModelManager(progress_callback=lambda msg: self.update_status(msg))
            for key in keys:
                self._model_download_state[key] = "verifying"
                dpg.split_frame()
                self._refresh_model_status()
                if key == "faces":
                    result = manager.download_faces()
                elif key == "clip":
                    result = manager.download_clip()
                elif key == "yolo":
                    result = manager.download_yolo()
                else:
                    result = manager.download_ocr()

                if result.success:
                    self.config.ai.downloaded_models[key] = True
                    save_config()

                level = "info" if result.success else "warning"
                self.update_status(f"Verify {key}: {result.message}", level=level)
                self._model_download_state.pop(key, None)

            dpg.split_frame()
            self._refresh_model_status()

        import threading
        thread = threading.Thread(target=run_verify, daemon=True)
        thread.start()

    def update_file_count(self, count: int) -> None:
        """Update the file count display."""
        dpg.set_value(self.TAG_FILE_COUNT, f"Files: {count:,}")

    def update_storage_info(self, size_bytes: int) -> None:
        """Update the storage info display."""
        size_gb = size_bytes / (1024 ** 3)
        dpg.set_value(self.TAG_STORAGE_INFO, f"Storage: {size_gb:.1f} GB")

    def update_gpu_status(self, status: str) -> None:
        """Update the GPU status display."""
        dpg.set_value(self.TAG_GPU_STATUS, f"GPU: {status}")

    def _on_search(self) -> None:
        query = dpg.get_value("search_query")
        logger.info(f"Search clicked: {query}")
        self.update_status(f"Searching for '{query}'...")

    def _refresh_tracked_folders(self) -> None:
        """Refresh the tracked folders list in settings."""
        dpg.configure_item(
            self.TAG_VERSION_FOLDER_LIST,
            items=self.config.versioning.tracked_folders,
        )

    def _on_add_tracked_folder(self) -> None:
        """Add a folder to version tracking list."""
        folder = dpg.get_value(self.TAG_VERSION_FOLDER_INPUT).strip()
        if not folder:
            return

        path = Path(folder)
        if not path.exists() or not path.is_dir():
            self.update_status("Tracked folder not found.")
            return

        normalized = str(path)
        if normalized not in self.config.versioning.tracked_folders:
            self.config.versioning.tracked_folders.append(normalized)
            self._refresh_tracked_folders()
            dpg.set_value(self.TAG_VERSION_FOLDER_INPUT, "")
            self.update_status("Tracked folder added.")
        else:
            self.update_status("Folder already tracked.")

    def _on_remove_tracked_folder(self) -> None:
        """Remove selected folder from version tracking list."""
        selected = dpg.get_value(self.TAG_VERSION_FOLDER_LIST)
        if not selected:
            return

        if selected in self.config.versioning.tracked_folders:
            self.config.versioning.tracked_folders.remove(selected)
            self._refresh_tracked_folders()
            self.update_status("Tracked folder removed.")

    def _on_versioning_settings_changed(self) -> None:
        """Handle changes to version tracking settings."""
        self.config.versioning.include_subfolders = dpg.get_value(self.TAG_VERSION_INCLUDE_SUBFOLDERS)
        self.config.versioning.auto_commit_mode = dpg.get_value(self.TAG_VERSION_AUTO_MODE)
        self.config.versioning.max_file_size_mb = dpg.get_value(self.TAG_VERSION_MAX_SIZE)

    def _create_version_history_dialog(self) -> None:
        """Create version history modal dialog."""
        with dpg.window(
            tag=self.TAG_VERSION_HISTORY_DIALOG,
            label="Version History",
            modal=True,
            show=False,
            width=800,
            height=500,
            no_resize=True,
        ):
            dpg.add_text("", tag=self.TAG_VERSION_HISTORY_LABEL)
            dpg.add_separator()
            dpg.add_spacer(height=5)
            with dpg.child_window(height=260, border=True):
                with dpg.table(
                    tag=self.TAG_VERSION_HISTORY_TABLE,
                    header_row=True,
                    borders_innerH=True,
                    borders_outerH=True,
                    borders_innerV=True,
                    borders_outerV=True,
                    resizable=True,
                    policy=dpg.mvTable_SizingStretchProp,
                    row_background=True,
                    scrollY=True,
                    height=220,
                ):
                    dpg.add_table_column(label="Commit", init_width_or_weight=120)
                    dpg.add_table_column(label="Date", init_width_or_weight=140)
                    dpg.add_table_column(label="Message", init_width_or_weight=240)
                    dpg.add_table_column(label="Size", init_width_or_weight=80)
                    dpg.add_table_column(label="+/-", init_width_or_weight=80)

            dpg.add_spacer(height=5)
            dpg.add_text("Diff Preview", tag=self.TAG_VERSION_DIFF_LABEL, color=(200, 200, 200))
            with dpg.child_window(height=120, border=True):
                dpg.add_input_text(
                    tag=self.TAG_VERSION_DIFF_TEXT,
                    multiline=True,
                    readonly=True,
                    width=-1,
                    height=100,
                )

            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Restore Selected",
                    tag=self.TAG_VERSION_RESTORE_BUTTON,
                    callback=self._on_restore_selected,
                    enabled=False,
                )
                dpg.add_button(
                    label="Open File",
                    tag=self.TAG_VERSION_OPEN_BUTTON,
                    callback=self._on_open_current_file,
                    enabled=False,
                )
                dpg.add_button(
                    label="Close",
                    callback=lambda: dpg.configure_item(self.TAG_VERSION_HISTORY_DIALOG, show=False),
                )

    def _create_version_file_dialog(self) -> None:
        """Create file dialog for version history selection."""
        with dpg.file_dialog(
            tag=self.TAG_VERSION_FILE_DIALOG,
            show=False,
            modal=True,
            width=700,
            height=400,
            callback=self._on_version_file_selected,
        ):
            dpg.add_file_extension(".*", color=(255, 255, 255))

    def _show_version_file_dialog(self) -> None:
        """Show file dialog for selecting a file to view history."""
        dpg.show_item(self.TAG_VERSION_FILE_DIALOG)

    def _on_version_file_selected(self, sender, app_data) -> None:
        """Handle file selected from dialog."""
        file_path = app_data.get("file_path_name")
        if file_path:
            dpg.set_value(self.TAG_VERSION_FILE_INPUT, file_path)

    def _on_view_history(self) -> None:
        """Load and display version history for a file."""
        file_path = dpg.get_value(self.TAG_VERSION_FILE_INPUT).strip()
        if not file_path:
            self.update_status("Enter a file path to view history.")
            return

        target = Path(file_path)
        if not target.exists():
            self.update_status("File not found.")
            return

        tracker = self._get_tracker_for_file(target)
        if tracker is None:
            self.update_status("File is not under a tracked folder.")
            return

        history = tracker.get_file_history(target)
        self._version_history_entries = history
        self._version_history_file = target
        self._selected_history_commit = None

        dpg.set_value(self.TAG_VERSION_HISTORY_LABEL, f"History: {target.name}")
        self._populate_history_table(history)
        dpg.configure_item(self.TAG_VERSION_RESTORE_BUTTON, enabled=False)
        dpg.configure_item(self.TAG_VERSION_OPEN_BUTTON, enabled=True)
        dpg.set_value(self.TAG_VERSION_DIFF_TEXT, "")
        dpg.configure_item(self.TAG_VERSION_HISTORY_DIALOG, show=True)

    def _populate_history_table(self, history: list[VersionEntry]) -> None:
        """Populate history table with entries."""
        children = dpg.get_item_children(self.TAG_VERSION_HISTORY_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        if not history:
            with dpg.table_row(parent=self.TAG_VERSION_HISTORY_TABLE):
                dpg.add_text("No history found.")
                dpg.add_text("")
                dpg.add_text("")
                dpg.add_text("")
                dpg.add_text("")
            return

        for entry in history:
            short_hash = entry.commit_hash[:8]
            date_str = entry.committed_at.strftime("%Y-%m-%d %H:%M")
            size_str = f"{(entry.size_bytes or 0) / 1024:.1f} KB" if entry.size_bytes else "-"
            delta = ""
            if entry.insertions is not None or entry.deletions is not None:
                ins = entry.insertions or 0
                dels = entry.deletions or 0
                delta = f"+{ins}/-{dels}"

            with dpg.table_row(parent=self.TAG_VERSION_HISTORY_TABLE):
                dpg.add_selectable(
                    label=short_hash,
                    callback=self._on_history_selected,
                    user_data=entry.commit_hash,
                    span_columns=False,
                )
                dpg.add_text(date_str)
                dpg.add_text(entry.message)
                dpg.add_text(size_str)
                dpg.add_text(delta)

    def _on_history_selected(self, sender, app_data, user_data) -> None:
        """Handle selection of a history row."""
        self._selected_history_commit = user_data
        dpg.configure_item(self.TAG_VERSION_RESTORE_BUTTON, enabled=True)
        self._update_diff_preview()

    def _update_diff_preview(self) -> None:
        """Update diff preview for the selected commit."""
        if not self._version_history_file or not self._selected_history_commit:
            dpg.set_value(self.TAG_VERSION_DIFF_TEXT, "")
            return

        if not self._is_text_file(self._version_history_file):
            dpg.set_value(self.TAG_VERSION_DIFF_TEXT, "Diff preview not available for this file type.")
            return

        history = self._version_history_entries
        index = next((i for i, entry in enumerate(history) if entry.commit_hash == self._selected_history_commit), None)
        if index is None:
            dpg.set_value(self.TAG_VERSION_DIFF_TEXT, "")
            return

        if index + 1 >= len(history):
            dpg.set_value(self.TAG_VERSION_DIFF_TEXT, "No earlier version to diff against.")
            return

        tracker = self._get_tracker_for_file(self._version_history_file)
        if tracker is None:
            dpg.set_value(self.TAG_VERSION_DIFF_TEXT, "File is not under a tracked folder.")
            return

        newer_commit = history[index].commit_hash
        older_commit = history[index + 1].commit_hash
        diff_text = tracker.diff_versions(self._version_history_file, older_commit, newer_commit)
        if not diff_text:
            diff_text = "No diff available."
        dpg.set_value(self.TAG_VERSION_DIFF_TEXT, diff_text)

    def _on_restore_selected(self) -> None:
        """Restore file to selected version."""
        if not self._version_history_file or not self._selected_history_commit:
            return

        tracker = self._get_tracker_for_file(self._version_history_file)
        if tracker is None:
            self.update_status("File is not under a tracked folder.")
            return

        restored = tracker.restore_file(
            self._version_history_file,
            self._selected_history_commit,
        )

        if restored:
            self.update_status("File restored to selected version.")
            self._refresh_recent_changes()
        else:
            self.update_status("Restore failed.")

    def _on_open_current_file(self) -> None:
        """Open the current file in the default system app."""
        if not self._version_history_file:
            return

        try:
            os.startfile(self._version_history_file)
        except Exception:
            self.update_status("Failed to open file.")

    def _on_save_version(self) -> None:
        """Manually save a version for a file."""
        file_path = dpg.get_value(self.TAG_VERSION_FILE_INPUT).strip()
        if not file_path:
            self.update_status("Enter a file path to save a version.")
            return

        target = Path(file_path)
        if not target.exists():
            self.update_status("File not found.")
            return

        tracker = self._get_tracker_for_file(target)
        if tracker is None:
            self.update_status("File is not under a tracked folder.")
            return

        message = f"Manual save: {target.name}"
        committed = tracker.commit_files([target], message)
        if committed:
            self.update_status("Version saved.")
            self._refresh_recent_changes()
        else:
            self.update_status("No changes to save.")

    def _get_tracker_for_file(self, file_path: Path) -> Optional[VersionTracker]:
        """Resolve a file to its tracked repo."""
        root = self._find_tracked_root(file_path)
        if root is None:
            return None

        tracker = VersionTracker(
            root_path=str(root),
            include_patterns=self.config.versioning.include_patterns or None,
            exclude_patterns=self.config.versioning.exclude_patterns,
            include_subfolders=self.config.versioning.include_subfolders,
            max_file_size_mb=self.config.versioning.max_file_size_mb,
        )
        if tracker.init_repository():
            return tracker
        return None

    def _find_tracked_root(self, file_path: Path) -> Optional[Path]:
        """Find the tracked folder that contains the file."""
        target = file_path.resolve()
        best: Optional[Path] = None
        for folder in self.config.versioning.tracked_folders:
            root = Path(folder).resolve()
            try:
                target.relative_to(root)
                if best is None or len(str(root)) > len(str(best)):
                    best = root
            except ValueError:
                continue
        return best

    def _is_text_file(self, file_path: Path) -> bool:
        """Basic heuristic for text file types."""
        text_exts = {
            ".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".py", ".js",
            ".css", ".ini", ".yaml", ".yml", ".toml", ".conf", ".log", ".rtf",
        }
        return file_path.suffix.lower() in text_exts

    def _refresh_recent_changes(self) -> None:
        """Refresh recent changes table."""
        entries: list[ChangeEntry] = []

        for folder in self.config.versioning.tracked_folders:
            tracker = VersionTracker(
                root_path=folder,
                include_patterns=self.config.versioning.include_patterns or None,
                exclude_patterns=self.config.versioning.exclude_patterns,
                include_subfolders=self.config.versioning.include_subfolders,
                max_file_size_mb=self.config.versioning.max_file_size_mb,
            )
            if tracker.init_repository():
                entries.extend(tracker.get_recent_changes(limit=25))

        entries.sort(key=lambda e: e.committed_at, reverse=True)
        entries = entries[:50]

        children = dpg.get_item_children(self.TAG_VERSION_RECENT_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        if not entries:
            with dpg.table_row(parent=self.TAG_VERSION_RECENT_TABLE):
                dpg.add_text("No recent changes.")
                dpg.add_text("")
                dpg.add_text("")
            return

        for entry in entries:
            date_str = entry.committed_at.strftime("%Y-%m-%d %H:%M")
            name = Path(entry.file_path).name
            with dpg.table_row(parent=self.TAG_VERSION_RECENT_TABLE):
                dpg.add_text(name)
                dpg.add_text(date_str)
                dpg.add_text(entry.message)

    def _on_save_settings(self) -> None:
        logger.info("Save settings clicked")
        self.config.actions.confirm_destructive = dpg.get_value("settings_confirm_destructive")
        self.config.actions.create_audit_log = dpg.get_value("settings_create_audit_log")
        self.config.duplicates.near_duplicate_threshold = dpg.get_value("settings_near_duplicate_threshold")
        self.config.duplicates.match_across_formats = dpg.get_value("settings_match_formats")
        self.config.duplicates.min_image_size = dpg.get_value("settings_min_image_size")
        self.config.scan.max_file_size_gb = dpg.get_value("settings_max_file_size_gb")
        self.config.ai.process_videos = dpg.get_value("settings_process_videos")
        self.config.ai.enabled = dpg.get_value("settings_ai_enabled")
        self.config.ai.use_gpu = dpg.get_value("settings_ai_use_gpu")
        save_config()
        self.versioning_service.refresh_tracked_folders()
        self._refresh_recent_changes()
        self.update_status("Settings saved")

    def run(self) -> None:
        """Run the application main loop."""
        logger.info("Starting DupliCleaner")

        # Update initial status
        stats = self.db.get_statistics()
        self.update_file_count(stats["total_files"])
        self.update_storage_info(stats["total_size"])

        # Check GPU availability
        try:
            import torch
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                self.update_gpu_status(f"CUDA ({gpu_name})")
            else:
                self.update_gpu_status("CPU only")
        except ImportError:
            self.update_gpu_status("PyTorch not installed")

        # Start background version tracking
        self.versioning_service.start()

        # Main render loop
        while dpg.is_dearpygui_running():
            dpg.render_dearpygui_frame()

        self.cleanup()

    def cleanup(self) -> None:
        """Clean up resources before exit."""
        logger.info("Cleaning up...")
        self.versioning_service.stop()
        save_config()
        dpg.destroy_context()
        logger.info("DupliCleaner shutdown complete")


def run_app() -> None:
    """Entry point to run the application."""
    setup_logging()
    app = DupliCleanerApp()
    app.setup()
    app.run()
