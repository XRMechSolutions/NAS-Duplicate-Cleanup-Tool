"""DupliCleaner main application.

Dear PyGui application with tabbed interface for managing duplicate files,
organizing photos, and AI-powered content analysis.
"""

from pathlib import Path
from typing import Callable, Optional

import os
import re
import subprocess
import sys
import tempfile
import threading

import dearpygui.dearpygui as dpg

from duplicleaner.utils.logging import get_logger, setup_logging
from duplicleaner.utils.profiling import profile_block
from duplicleaner.utils.config import get_config, save_config
from duplicleaner.utils.keystore import AIProvider, get_keystore, mask_api_key
from duplicleaner.db.database import get_database
from duplicleaner.ui.search_panel import SearchPanel
from duplicleaner.ui.documentation_panel import DocumentationPanel
from duplicleaner.ui.status_log_panel import StatusLogPanel
from duplicleaner.drives.manager import DriveManager, normalize_path
from duplicleaner.ai.model_manager import ModelManager
from duplicleaner.ui.drives_panel import DrivesPanel
from duplicleaner.ui.duplicates_panel import DuplicatesPanel
from duplicleaner.ui.organize_panel import OrganizePanel
from duplicleaner.ui.faces_panel import FacesPanel
from duplicleaner.ui.tooltips import add_tooltip, SETTINGS_TOOLTIPS
from duplicleaner.core.analysis_runner import AnalysisRunner, AnalysisOptions
from duplicleaner.core.versioning_service import VersioningService
from duplicleaner.core.versioning import VersionTracker, VersionEntry, ChangeEntry
from duplicleaner.core.actions import ActionEngine
from duplicleaner.ui.theme import apply_theme, get_theme_manager, get_status_color, get_accent_color, get_text_color

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
    TAG_TAB_DOCS = "tab_docs"

    # Content area tags
    TAG_CONTENT_DRIVES = "content_drives"
    TAG_CONTENT_DUPLICATES = "content_duplicates"
    TAG_CONTENT_ORGANIZE = "content_organize"
    TAG_CONTENT_FACES = "content_faces"
    TAG_CONTENT_SEARCH = "content_search"
    TAG_CONTENT_SETTINGS = "content_settings"
    TAG_CONTENT_LOG = "content_log"
    TAG_CONTENT_DOCS = "content_docs"

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
    TAG_INSTALL_AI_DEPS_BUTTON = "install_ai_deps_btn"
    TAG_INSTALL_AI_DEPS_STATUS = "install_ai_deps_status"
    TAG_INSTALL_AI_DEPS_VARIANT = "install_ai_deps_variant"
    TAG_INSTALL_AI_DEPS_SCOPE = "install_ai_deps_scope"
    TAG_OPENAI_KEY_INPUT = "settings_openai_key_input"
    TAG_OPENAI_KEY_STATUS = "settings_openai_key_status"
    TAG_ANTHROPIC_KEY_INPUT = "settings_anthropic_key_input"
    TAG_ANTHROPIC_KEY_STATUS = "settings_anthropic_key_status"
    TAG_KEY_STORAGE_STATUS = "settings_key_storage_status"
    TAG_SUMMARY_PROVIDER = "settings_summary_provider"
    TAG_SUMMARY_MODEL_LOCAL = "settings_summary_model_local"
    TAG_SUMMARY_MODEL_OPENAI = "settings_summary_model_openai"
    TAG_SUMMARY_MODEL_ANTHROPIC = "settings_summary_model_anthropic"
    TAG_SUMMARY_MODEL_GOOGLE = "settings_summary_model_google"
    TAG_SUMMARY_MAX_TOKENS = "settings_summary_max_tokens"
    TAG_SUMMARY_TEMPERATURE = "settings_summary_temperature"
    TAG_METADATA_LOCATION_LOOKUP = "settings_metadata_location_lookup"
    TAG_METADATA_LOCATION_LEVEL = "settings_metadata_location_level"
    TAG_ANALYSIS_STATUS = "analysis_status_text"
    TAG_ANALYSIS_RUN = "analysis_run_btn"
    TAG_ANALYSIS_CANCEL = "analysis_cancel_btn"
    TAG_ANALYSIS_INCLUDE_IMAGES = "analysis_include_images"
    TAG_ANALYSIS_INCLUDE_DOCS = "analysis_include_docs"
    TAG_ANALYSIS_INCLUDE_DATA = "analysis_include_data"
    TAG_ANALYSIS_DOC_EXTENSIONS = "analysis_doc_extensions"
    TAG_ANALYSIS_DATA_EXTENSIONS = "analysis_data_extensions"
    TAG_ANALYSIS_SCAN_BEFORE_FULL = "analysis_scan_before_full"
    TAG_ANALYSIS_REANALYZE = "analysis_reanalyze_existing"
    TAG_GPU_STATUS_HINT = "gpu_status_hint"
    TAG_GPU_HELP_GROUP = "gpu_help_group"
    TAG_GPU_HELP_TEXT = "gpu_help_text"
    TAG_THEME_SELECTOR = "settings_theme_selector"

    def __init__(self) -> None:
        """Initialize the application."""
        with profile_block("startup.config"):
            self.config = get_config()
        with profile_block("startup.database"):
            self.db = get_database()
        with profile_block("startup.keystore"):
            self.keystore = get_keystore()
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
        self.documentation_panel: Optional[DocumentationPanel] = None
        self.action_engine = ActionEngine(self.db)
        self._model_download_state: dict[str, str] = {}
        self._doc_fonts: dict[str, str] = {}
        self._model_download_queue: list[str] = []
        self._ai_deps_installing = False
        self._face_worker_active = False
        self._analysis_thread: Optional[threading.Thread] = None
        self._analysis_cancel_event = threading.Event()
        self._analysis_running = False

        # Callback registry
        self._callbacks: dict[str, list[Callable]] = {}

        # Detect CUDA availability once at startup
        with profile_block("startup.gpu_detect"):
            self._cuda_available = self._detect_cuda_available()
            self._apply_gpu_defaults()

        logger.info("DupliCleaner application initialized")

    def setup(self) -> None:
        """Set up Dear PyGui context and create the UI."""
        with profile_block("startup.dpg.create_context"):
            dpg.create_context()

        # Configure viewport
        with profile_block("startup.dpg.create_viewport"):
            dpg.create_viewport(
                title="DupliCleaner",
                width=self.config.ui.window_width,
                height=self.config.ui.window_height,
                min_width=800,
                min_height=600,
            )

        # Set up theme
        with profile_block("startup.theme"):
            self._setup_theme()

        # Create main window
        with profile_block("startup.main_window"):
            self._create_main_window()
        with profile_block("startup.setup_wizard"):
            self._create_setup_wizard()

        # Set up Dear PyGui
        with profile_block("startup.dpg.setup"):
            dpg.setup_dearpygui()
        with profile_block("startup.dpg.show_viewport"):
            dpg.show_viewport()

        # Set the main window as primary
        dpg.set_primary_window(self.TAG_MAIN_WINDOW, True)

        if self.config.first_run:
            dpg.show_item("setup_wizard")

        logger.info("UI setup complete")

        # Sync GPU status after UI is ready
        with profile_block("startup.refresh_gpu"):
            self._refresh_gpu_ui_state()
        with profile_block("startup.recent_changes"):
            self._refresh_recent_changes()

    def _setup_theme(self) -> None:
        """Set up the application theme."""
        # Apply theme from config using the theme manager
        apply_theme(self.config.ui.theme)

        # Load custom fonts for documentation (if available)
        try:
            fonts_dir = Path(__file__).resolve().parents[2] / "resources" / "fonts"
            body_font = fonts_dir / "lexendregular.ttf"
            heading_font = fonts_dir / "playfairdisplayvariablefontwght.ttf"
            if body_font.exists() and heading_font.exists():
                with dpg.font_registry():
                    doc_body = dpg.add_font(str(body_font), 16, tag="doc_body_font")
                    doc_h1 = dpg.add_font(str(heading_font), 22, tag="doc_h1_font")
                    doc_h2 = dpg.add_font(str(heading_font), 19, tag="doc_h2_font")
                    doc_h3 = dpg.add_font(str(heading_font), 17, tag="doc_h3_font")
                self._doc_fonts = {
                    "body": "doc_body_font",
                    "h1": "doc_h1_font",
                    "h2": "doc_h2_font",
                    "h3": "doc_h3_font",
                }
                self._doc_fonts_loaded = True
            else:
                self._doc_fonts_loaded = False
        except Exception as exc:
            logger.warning("Failed to load documentation fonts: %s", exc)
            self._doc_fonts_loaded = False

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

                # Photo Organizer tab
                with dpg.tab(label="Photos", tag=self.TAG_TAB_ORGANIZE):
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

                # Documentation tab
                with dpg.tab(label="Documentation", tag=self.TAG_TAB_DOCS):
                    self._create_documentation_panel()

                # Status Log tab
                with dpg.tab(label="Log", tag=self.TAG_TAB_LOG):
                    self._create_log_panel()

            # Status bar at bottom
            dpg.add_spacer(height=10)
            self._create_status_bar(parent=self.TAG_MAIN_WINDOW)

    def _create_status_bar(self, parent: int | str) -> None:
        """Create the status bar."""
        with dpg.group(parent=parent, horizontal=True, tag=self.TAG_STATUS_BAR):
            dpg.add_text("", tag=self.TAG_STATUS_TEXT, color=get_status_color("info"))
            dpg.add_spacer(width=20)
            dpg.add_text("Files: 0", tag=self.TAG_FILE_COUNT, color=get_text_color("secondary"))
            dpg.add_spacer(width=20)
            dpg.add_text("Storage: 0 B", tag=self.TAG_STORAGE_INFO, color=get_text_color("secondary"))
            dpg.add_spacer(width=20)
            dpg.add_text("GPU: Unknown", tag=self.TAG_GPU_STATUS, color=get_text_color("secondary"))

    def _format_bytes(self, size: int) -> str:
        """Format bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def update_status(self, message: str, level: str = "info") -> None:
        """Update the status bar and log."""
        if dpg.does_item_exist(self.TAG_STATUS_TEXT):
            dpg.set_value(self.TAG_STATUS_TEXT, message)
            dpg.configure_item(self.TAG_STATUS_TEXT, color=get_status_color(level))
        if self.status_log_panel:
            self.status_log_panel.add(message, level=level)

    def update_file_count(self, count: int) -> None:
        """Update file count label."""
        if dpg.does_item_exist(self.TAG_FILE_COUNT):
            dpg.set_value(self.TAG_FILE_COUNT, f"Files: {count:,}")

    def update_storage_info(self, total_size: int) -> None:
        """Update storage size label."""
        if dpg.does_item_exist(self.TAG_STORAGE_INFO):
            dpg.set_value(self.TAG_STORAGE_INFO, f"Storage: {self._format_bytes(total_size)}")

    def update_gpu_status(self, message: str) -> None:
        """Update GPU status label."""
        if dpg.does_item_exist(self.TAG_GPU_STATUS):
            dpg.set_value(self.TAG_GPU_STATUS, f"GPU: {message}")

    def _create_drives_panel(self) -> None:
        """Create the drives management panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_DRIVES, autosize_x=True, autosize_y=True):
            self.drives_panel = DrivesPanel(
                parent=self.TAG_CONTENT_DRIVES,
                on_status_update=self.update_status,
                on_face_worker_state_change=self._on_face_worker_state_change,
            )

    def _create_duplicates_panel(self) -> None:
        """Create the duplicates review panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_DUPLICATES, autosize_x=True, autosize_y=True):
            self.duplicates_panel = DuplicatesPanel(
                parent=self.TAG_CONTENT_DUPLICATES,
                action_engine=self.action_engine,
                on_status_update=self.update_status,
            )

    def _create_organize_panel(self) -> None:
        """Create the photo organizer panel."""
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
            self.faces_panel.set_background_face_analysis_active(self._face_worker_active)

    def _on_face_worker_state_change(self, active: bool) -> None:
        """Sync face analysis state with Faces panel."""
        self._face_worker_active = active
        if self.faces_panel:
            self.faces_panel.set_background_face_analysis_active(active)

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

    def _create_documentation_panel(self) -> None:
        """Create the documentation panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_DOCS, autosize_x=True, autosize_y=True):
            self.documentation_panel = DocumentationPanel(
                parent=self.TAG_CONTENT_DOCS,
                fonts=self._doc_fonts if self._doc_fonts_loaded else None,
            )
            self.documentation_panel.build()

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
            dpg.add_text("Welcome to DupliCleaner", color=get_accent_color())
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
                dpg.add_text("", tag="wizard_drive_status", color=get_status_color("warning"))

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
                dpg.add_text("Status: Not downloaded", tag="wizard_status_faces", color=get_text_color("secondary"))
                dpg.add_checkbox(label="Scene search (CLIP)", tag="wizard_model_clip", default_value=True)
                dpg.add_text("Status: Not downloaded", tag="wizard_status_clip", color=get_text_color("secondary"))
                dpg.add_checkbox(label="Object detection (YOLO)", tag="wizard_model_yolo", default_value=True)
                dpg.add_text("Status: Not downloaded", tag="wizard_status_yolo", color=get_text_color("secondary"))
                dpg.add_checkbox(label="OCR (EasyOCR)", tag="wizard_model_ocr", default_value=True)
                dpg.add_text("Status: Not downloaded", tag="wizard_status_ocr", color=get_text_color("secondary"))
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
        dpg.set_value("wizard_drive_status", message)
        dpg.configure_item("wizard_drive_status", color=get_status_color(level))
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
                self._set_wizard_model_status(tag, "Downloading...", get_status_color("info"))
                result = fn()
                if result.success:
                    self.config.ai.downloaded_models[key] = True
                    save_config()
                color = get_status_color("success") if result.success else get_status_color("warning")
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

    def _add_model_row(self, model_name: str, model_key: str, status_tag: str) -> None:
        """Add a row to the AI Models table."""
        with dpg.table_row():
            dpg.add_text(model_name)
            dpg.add_text("Not checked", tag=status_tag, color=get_text_color("secondary"))
            dpg.add_button(
                label="Download",
                callback=self._on_model_download_clicked,
                user_data={"key": model_key, "tag": status_tag},
            )

    def _on_model_download_clicked(self, sender, app_data, user_data) -> None:
        """Handle model download button click."""
        model_key = user_data["key"]
        status_tag = user_data["tag"]
        dpg.set_value(status_tag, "Queued for download...")
        dpg.configure_item(status_tag, color=get_status_color("info"))
        # Run download in a separate thread to avoid blocking UI
        thread = threading.Thread(target=self._download_model, args=(model_key, status_tag), daemon=True)
        thread.start()

    def _download_model(self, model_key: str, status_tag: str) -> None:
        """Download a model and update the UI."""
        manager = ModelManager(progress_callback=self.update_status)
        download_methods = {
            "faces": manager.download_faces,
            "clip": manager.download_clip,
            "yolo": manager.download_yolo,
            "ocr": manager.download_ocr,
        }

        if model_key in download_methods:
            dpg.set_value(status_tag, "Downloading...")
            result = download_methods[model_key]()
            if result.success:
                self.config.ai.downloaded_models[model_key] = True
                save_config()
            color = get_status_color("success") if result.success else get_status_color("error")
            dpg.set_value(status_tag, result.message)
            dpg.configure_item(status_tag, color=color)
            self.update_status(result.message, level="info" if result.success else "error")

    def _refresh_model_status(self) -> None:
        """Refresh the status of all models."""
        # This method needs to be implemented.
        self.update_status("Model status refresh not yet implemented.", level="warning")

    def _verify_models(self) -> None:
        """Verify the integrity of all models."""
        # This method needs to be implemented.
        self.update_status("Model verification not yet implemented.", level="warning")

    def _install_ai_dependencies(self) -> None:
        """Install AI dependencies."""
        # This method needs to be implemented.
        self.update_status("AI dependency installation not yet implemented.", level="warning")

    def _on_ai_deps_variant_changed(self, sender, app_data, user_data) -> None:
        """Handle AI dependency variant change."""
        # This method needs to be implemented.
        self.update_status("AI dependency variant change not yet implemented.", level="warning")

    def _format_extension_list(self, extensions: list[str]) -> str:
        """Format a list of extensions into a comma-separated string."""
        return ", ".join(extensions)

    def _on_run_analysis(self, sender, app_data, user_data) -> None:
        """Handle run analysis button click."""
        # This method needs to be implemented.
        self.update_status("Run analysis not yet implemented.", level="warning")

    def _on_cancel_analysis(self, sender, app_data, user_data) -> None:
        """Handle cancel analysis button click."""
        # This method needs to be implemented.
        self.update_status("Cancel analysis not yet implemented.", level="warning")

    def _create_settings_panel(self) -> None:
        """Create the settings panel."""
        with dpg.child_window(tag=self.TAG_CONTENT_SETTINGS, autosize_x=True, autosize_y=True):
            dpg.add_text("Settings", color=(150, 200, 255))
            dpg.add_separator()
            dpg.add_spacer(height=10)

            # General settings
            with dpg.collapsing_header(label="General", default_open=True):
                confirm_cb = dpg.add_checkbox(
                    label="Confirm before destructive actions",
                    tag="settings_confirm_destructive",
                    default_value=self.config.actions.confirm_destructive,
                )
                add_tooltip(confirm_cb, SETTINGS_TOOLTIPS["confirm_destructive"])
                audit_cb = dpg.add_checkbox(
                    label="Create audit log for all actions",
                    tag="settings_create_audit_log",
                    default_value=self.config.actions.create_audit_log,
                )
                add_tooltip(audit_cb, SETTINGS_TOOLTIPS["audit_log"])

                dpg.add_spacer(height=6)
                wizard_btn = dpg.add_button(label="Run Setup Wizard", callback=self._show_setup_wizard)
                add_tooltip(wizard_btn, SETTINGS_TOOLTIPS["run_wizard"])

            # Duplicate detection settings
            with dpg.collapsing_header(label="Duplicate Detection", default_open=False):
                with dpg.group(horizontal=True):
                    dpg.add_text("Near-duplicate threshold:")
                    threshold_slider = dpg.add_slider_float(
                        tag="settings_near_duplicate_threshold",
                        default_value=self.config.duplicates.near_duplicate_threshold,
                        min_value=0.5,
                        max_value=1.0,
                        width=200,
                        callback=lambda: dpg.set_value(
                            "settings_near_duplicate_threshold_value",
                            f"{dpg.get_value('settings_near_duplicate_threshold'):.2f}",
                        ),
                    )
                    add_tooltip(threshold_slider, SETTINGS_TOOLTIPS["near_duplicate_threshold"])
                    dpg.add_text(
                        f"{self.config.duplicates.near_duplicate_threshold:.2f}",
                        tag="settings_near_duplicate_threshold_value",
                        color=(150, 150, 150),
                    )
                match_cb = dpg.add_checkbox(
                    label="Match across formats (JPEG/PNG/HEIC)",
                    tag="settings_match_formats",
                    default_value=self.config.duplicates.match_across_formats,
                )
                add_tooltip(match_cb, SETTINGS_TOOLTIPS["match_formats"])

            # Scan optimization
            with dpg.collapsing_header(label="Scan Optimization", default_open=False):
                with dpg.group(horizontal=True):
                    dpg.add_text("Min image size for near-duplicate checks:")
                    min_img = dpg.add_input_int(
                        tag="settings_min_image_size",
                        default_value=self.config.duplicates.min_image_size,
                        min_value=0,
                        max_value=5000,
                        width=120,
                    )
                    add_tooltip(min_img, SETTINGS_TOOLTIPS["min_image_size"])
                with dpg.group(horizontal=True):
                    dpg.add_text("Max file size (GB) to scan:")
                    max_size = dpg.add_input_float(
                        tag="settings_max_file_size_gb",
                        default_value=self.config.scan.max_file_size_gb,
                        min_value=0.1,
                        max_value=500.0,
                        width=120,
                    )
                    add_tooltip(max_size, SETTINGS_TOOLTIPS["max_file_size"])
                process_videos_cb = dpg.add_checkbox(
                    label="Process videos for near-duplicates (not implemented yet)",
                    tag="settings_process_videos",
                    default_value=self.config.ai.process_videos,
                    enabled=False,
                )
                add_tooltip(process_videos_cb, SETTINGS_TOOLTIPS["process_videos"])

            # AI settings
            with dpg.collapsing_header(label="AI Features", default_open=False):
                ai_cb = dpg.add_checkbox(
                    label="Enable AI features",
                    tag="settings_ai_enabled",
                    default_value=self.config.ai.enabled,
                )
                add_tooltip(ai_cb, SETTINGS_TOOLTIPS["ai_enabled"])
                gpu_cb = dpg.add_checkbox(
                    label="Use GPU acceleration",
                    tag="settings_ai_use_gpu",
                    default_value=self.config.ai.use_gpu,
                    callback=self._on_ai_use_gpu_changed,
                )
                add_tooltip(gpu_cb, SETTINGS_TOOLTIPS["ai_gpu"])
                dpg.add_text("", tag=self.TAG_GPU_STATUS_HINT, color=(255, 180, 100))
                with dpg.child_window(
                    tag=self.TAG_GPU_HELP_GROUP,
                    height=140,
                    border=True,
                    show=not self._cuda_available,
                ):
                    dpg.add_text("GPU Setup Help", color=(200, 200, 200))
                    dpg.add_input_text(
                        tag=self.TAG_GPU_HELP_TEXT,
                        multiline=True,
                        readonly=True,
                        width=-1,
                        height=110,
                    )

            # Cloud AI providers
            with dpg.collapsing_header(label="Cloud AI Providers", default_open=False):
                storage_text = "Secure key storage available" if self.keystore.is_secure_storage_available() else "Using fallback key storage"
                storage_label = dpg.add_text(storage_text, tag=self.TAG_KEY_STORAGE_STATUS, color=(150, 150, 150))
                add_tooltip(storage_label, SETTINGS_TOOLTIPS["key_storage"])
                dpg.add_text("Keys are saved immediately.", color=(120, 120, 120))
                with dpg.group(horizontal=True):
                    dpg.add_text("OpenAI API key:")
                    openai_key = dpg.add_input_text(
                        tag=self.TAG_OPENAI_KEY_INPUT,
                        password=True,
                        width=260,
                        hint="sk-...",
                    )
                    add_tooltip(openai_key, SETTINGS_TOOLTIPS["openai_key"])
                    dpg.add_button(
                        label="Save",
                        callback=lambda s, a, u: self._on_store_api_key(u),
                        user_data=AIProvider.OPENAI,
                    )
                    dpg.add_button(
                        label="Clear",
                        callback=lambda s, a, u: self._on_clear_api_key(u),
                        user_data=AIProvider.OPENAI,
                    )
                dpg.add_text("", tag=self.TAG_OPENAI_KEY_STATUS, color=(150, 150, 150))
                with dpg.group(horizontal=True):
                    dpg.add_text("Anthropic API key:")
                    anthropic_key = dpg.add_input_text(
                        tag=self.TAG_ANTHROPIC_KEY_INPUT,
                        password=True,
                        width=260,
                        hint="sk-ant-...",
                    )
                    add_tooltip(anthropic_key, SETTINGS_TOOLTIPS["anthropic_key"])
                    dpg.add_button(
                        label="Save",
                        callback=lambda s, a, u: self._on_store_api_key(u),
                        user_data=AIProvider.ANTHROPIC,
                    )
                    dpg.add_button(
                        label="Clear",
                        callback=lambda s, a, u: self._on_clear_api_key(u),
                        user_data=AIProvider.ANTHROPIC,
                    )
                dpg.add_text("", tag=self.TAG_ANTHROPIC_KEY_STATUS, color=(150, 150, 150))

            # Summary settings
            with dpg.collapsing_header(label="AI Summaries", default_open=False):
                provider_combo = dpg.add_combo(
                    label="Summary provider",
                    tag=self.TAG_SUMMARY_PROVIDER,
                    items=["local", "openai", "anthropic", "google"],
                    default_value=self.config.ai.summary_provider,
                    width=160,
                )
                add_tooltip(provider_combo, SETTINGS_TOOLTIPS["summary_provider"])
                with dpg.group(horizontal=True):
                    dpg.add_text("Local model:")
                    local_model = dpg.add_input_text(
                        tag=self.TAG_SUMMARY_MODEL_LOCAL,
                        default_value=self.config.ai.summary_model_local,
                        width=200,
                    )
                    add_tooltip(local_model, SETTINGS_TOOLTIPS["summary_model_local"])
                with dpg.group(horizontal=True):
                    dpg.add_text("OpenAI model:")
                    openai_model = dpg.add_input_text(
                        tag=self.TAG_SUMMARY_MODEL_OPENAI,
                        default_value=self.config.ai.summary_model_openai,
                        width=200,
                    )
                    add_tooltip(openai_model, SETTINGS_TOOLTIPS["summary_model_openai"])
                with dpg.group(horizontal=True):
                    dpg.add_text("Anthropic model:")
                    anthropic_model = dpg.add_input_text(
                        tag=self.TAG_SUMMARY_MODEL_ANTHROPIC,
                        default_value=self.config.ai.summary_model_anthropic,
                        width=200,
                    )
                    add_tooltip(anthropic_model, SETTINGS_TOOLTIPS["summary_model_anthropic"])
                with dpg.group(horizontal=True):
                    dpg.add_text("Google model:")
                    google_model = dpg.add_input_text(
                        tag=self.TAG_SUMMARY_MODEL_GOOGLE,
                        default_value=self.config.ai.summary_model_google,
                        width=200,
                    )
                    add_tooltip(google_model, SETTINGS_TOOLTIPS["summary_model_google"])
                with dpg.group(horizontal=True):
                    dpg.add_text("Max tokens:")
                    max_tokens = dpg.add_input_int(
                        tag=self.TAG_SUMMARY_MAX_TOKENS,
                        default_value=self.config.ai.summary_max_tokens,
                        min_value=256,
                        max_value=8192,
                        width=120,
                    )
                    add_tooltip(max_tokens, SETTINGS_TOOLTIPS["summary_max_tokens"])
                with dpg.group(horizontal=True):
                    dpg.add_text("Temperature:")
                    temp_slider = dpg.add_slider_float(
                        tag=self.TAG_SUMMARY_TEMPERATURE,
                        default_value=self.config.ai.summary_temperature,
                        min_value=0.0,
                        max_value=1.0,
                        width=200,
                    )
                    add_tooltip(temp_slider, SETTINGS_TOOLTIPS["summary_temperature"])

            # AI model management
            with dpg.collapsing_header(label="AI Models", default_open=False):
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
                refresh_btn = dpg.add_button(label="Refresh Model Status", callback=self._refresh_model_status)
                add_tooltip(refresh_btn, SETTINGS_TOOLTIPS["model_refresh"])
                verify_btn = dpg.add_button(label="Verify Models", tag="verify_models_btn", callback=self._verify_models)
                add_tooltip(verify_btn, SETTINGS_TOOLTIPS["model_verify"])
                with dpg.group(horizontal=True):
                    variant_label = "GPU (CUDA)" if self.config.ai.dependency_variant != "cpu" else "CPU only"
                    variant_combo = dpg.add_combo(
                        label="Install",
                        tag=self.TAG_INSTALL_AI_DEPS_VARIANT,
                        items=["GPU (CUDA)", "CPU only"],
                        default_value=variant_label,
                        width=140,
                        callback=self._on_ai_deps_variant_changed,
                    )
                    add_tooltip(variant_combo, SETTINGS_TOOLTIPS["deps_variant"])
                    scope_combo = dpg.add_combo(
                        label="Scope",
                        tag=self.TAG_INSTALL_AI_DEPS_SCOPE,
                        items=["User (recommended)", "System"],
                        default_value="User (recommended)",
                        width=170,
                    )
                    add_tooltip(scope_combo, SETTINGS_TOOLTIPS["deps_scope"])
                    install_btn = dpg.add_button(
                        label="Install AI Dependencies",
                        tag=self.TAG_INSTALL_AI_DEPS_BUTTON,
                        callback=self._install_ai_dependencies,
                    )
                    add_tooltip(install_btn, SETTINGS_TOOLTIPS["deps_install"])
                    dpg.add_text("", tag=self.TAG_INSTALL_AI_DEPS_STATUS, color=(150, 150, 150))

            # Metadata & analysis tools
            with dpg.collapsing_header(label="Metadata & AI Analysis", default_open=False):
                dpg.add_text("Applies to the next analysis run.", color=(120, 120, 120))
                lookup_cb = dpg.add_checkbox(
                    label="Lookup GPS location names (requires internet)",
                    tag=self.TAG_METADATA_LOCATION_LOOKUP,
                    default_value=self.config.ai.metadata_location_lookup,
                )
                add_tooltip(lookup_cb, SETTINGS_TOOLTIPS["metadata_location_lookup"])
                location_combo = dpg.add_combo(
                    label="Location detail level",
                    tag=self.TAG_METADATA_LOCATION_LEVEL,
                    items=["city", "city_country", "full"],
                    default_value=self.config.ai.metadata_location_level,
                    width=160,
                )
                add_tooltip(location_combo, SETTINGS_TOOLTIPS["metadata_location_level"])
                meta_cb = dpg.add_checkbox(
                    label="Extract file metadata (EXIF, size)",
                    tag="analysis_include_metadata",
                    default_value=self.config.ai.analysis_include_metadata,
                )
                add_tooltip(meta_cb, SETTINGS_TOOLTIPS["analysis_include_metadata"])
                scenes_cb = dpg.add_checkbox(
                    label="Scene classification (CLIP)",
                    tag="analysis_include_scenes",
                    default_value=self.config.ai.analysis_include_scenes,
                )
                add_tooltip(scenes_cb, SETTINGS_TOOLTIPS["analysis_include_scenes"])
                objects_cb = dpg.add_checkbox(
                    label="Object detection (YOLO)",
                    tag="analysis_include_objects",
                    default_value=self.config.ai.analysis_include_objects,
                )
                add_tooltip(objects_cb, SETTINGS_TOOLTIPS["analysis_include_objects"])
                ocr_cb = dpg.add_checkbox(
                    label="OCR text (EasyOCR)",
                    tag="analysis_include_ocr",
                    default_value=self.config.ai.analysis_include_ocr,
                )
                add_tooltip(ocr_cb, SETTINGS_TOOLTIPS["analysis_include_ocr"])
                summaries_cb = dpg.add_checkbox(
                    label="AI summaries (uses provider above)",
                    tag="analysis_include_summaries",
                    default_value=self.config.ai.analysis_include_summaries,
                )
                add_tooltip(summaries_cb, SETTINGS_TOOLTIPS["analysis_include_summaries"])
                dpg.add_spacer(height=5)
                images_cb = dpg.add_checkbox(
                    label="Analyze images",
                    tag=self.TAG_ANALYSIS_INCLUDE_IMAGES,
                    default_value=self.config.ai.analysis_include_images,
                )
                add_tooltip(images_cb, SETTINGS_TOOLTIPS["analysis_include_images"])
                docs_cb = dpg.add_checkbox(
                    label="Analyze documents/text files",
                    tag=self.TAG_ANALYSIS_INCLUDE_DOCS,
                    default_value=self.config.ai.analysis_include_documents,
                )
                add_tooltip(docs_cb, SETTINGS_TOOLTIPS["analysis_include_docs"])
                data_cb = dpg.add_checkbox(
                    label="Analyze data files (csv/json/xml/yaml)",
                    tag=self.TAG_ANALYSIS_INCLUDE_DATA,
                    default_value=self.config.ai.analysis_include_data_files,
                )
                add_tooltip(data_cb, SETTINGS_TOOLTIPS["analysis_include_data"])
                doc_ext = dpg.add_input_text(
                    tag=self.TAG_ANALYSIS_DOC_EXTENSIONS,
                    default_value=self._format_extension_list(self.config.ai.analysis_doc_extensions),
                    width=520,
                    hint="Doc extensions (comma-separated)",
                )
                add_tooltip(doc_ext, SETTINGS_TOOLTIPS["analysis_doc_extensions"])
                data_ext = dpg.add_input_text(
                    tag=self.TAG_ANALYSIS_DATA_EXTENSIONS,
                    default_value=self._format_extension_list(self.config.ai.analysis_data_extensions),
                    width=520,
                    hint="Data extensions (comma-separated)",
                )
                add_tooltip(data_ext, SETTINGS_TOOLTIPS["analysis_data_extensions"])
                scan_cb = dpg.add_checkbox(
                    label="Full Analysis: scan before analysis",
                    tag=self.TAG_ANALYSIS_SCAN_BEFORE_FULL,
                    default_value=self.config.ai.analysis_scan_before_full,
                )
                add_tooltip(scan_cb, SETTINGS_TOOLTIPS["analysis_scan_before_full"])
                reanalyze_cb = dpg.add_checkbox(
                    label="Re-analyze existing results (overwrite)",
                    tag=self.TAG_ANALYSIS_REANALYZE,
                    default_value=self.config.ai.analysis_reanalyze_existing,
                )
                add_tooltip(reanalyze_cb, SETTINGS_TOOLTIPS["analysis_reanalyze_existing"])
                with dpg.group(horizontal=True):
                    run_btn = dpg.add_button(label="Run Analysis", tag=self.TAG_ANALYSIS_RUN, callback=self._on_run_analysis)
                    add_tooltip(run_btn, SETTINGS_TOOLTIPS["analysis_run"])
                    cancel_btn = dpg.add_button(
                        label="Cancel",
                        tag=self.TAG_ANALYSIS_CANCEL,
                        callback=self._on_cancel_analysis,
                        enabled=False,
                    )
                    add_tooltip(cancel_btn, SETTINGS_TOOLTIPS["analysis_cancel"])
                dpg.add_text("", tag=self.TAG_ANALYSIS_STATUS, color=(150, 150, 150))

            # Version tracking settings
            with dpg.collapsing_header(label="Version Tracking", default_open=False):
                dpg.add_text("Changes are saved immediately.", color=(120, 120, 120))
                with dpg.group(horizontal=True):
                    dpg.add_input_text(
                        tag=self.TAG_VERSION_FOLDER_INPUT,
                        width=400,
                        hint="Folder to track...",
                    )
                    add_folder_btn = dpg.add_button(label="Add Folder", callback=self._on_add_tracked_folder)
                    add_tooltip(add_folder_btn, SETTINGS_TOOLTIPS["version_add_folder"])
                    remove_folder_btn = dpg.add_button(label="Remove Selected", callback=self._on_remove_tracked_folder)
                    add_tooltip(remove_folder_btn, SETTINGS_TOOLTIPS["version_remove_folder"])

                dpg.add_spacer(height=5)
                dpg.add_listbox(
                    tag=self.TAG_VERSION_FOLDER_LIST,
                    items=self.config.versioning.tracked_folders,
                    width=600,
                    num_items=4,
                )

                dpg.add_spacer(height=5)
                include_sub = dpg.add_checkbox(
                    label="Include subfolders",
                    tag=self.TAG_VERSION_INCLUDE_SUBFOLDERS,
                    default_value=self.config.versioning.include_subfolders,
                    callback=self._on_versioning_settings_changed,
                )
                add_tooltip(include_sub, SETTINGS_TOOLTIPS["version_include_subfolders"])
                with dpg.group(horizontal=True):
                    dpg.add_text("Auto-commit mode:")
                    auto_combo = dpg.add_combo(
                        tag=self.TAG_VERSION_AUTO_MODE,
                        items=["on_save", "interval", "daily", "manual"],
                        default_value=self.config.versioning.auto_commit_mode,
                        width=120,
                        callback=self._on_versioning_settings_changed,
                    )
                    add_tooltip(auto_combo, SETTINGS_TOOLTIPS["version_auto_mode"])
                    dpg.add_spacer(width=10)
                    dpg.add_text("Max file size (MB):")
                    max_mb = dpg.add_input_float(
                        tag=self.TAG_VERSION_MAX_SIZE,
                        default_value=self.config.versioning.max_file_size_mb,
                        min_value=1.0,
                        max_value=500.0,
                        width=100,
                        callback=self._on_versioning_settings_changed,
                    )
                    add_tooltip(max_mb, SETTINGS_TOOLTIPS["version_max_size"])

            # Version history tools
            with dpg.collapsing_header(label="Version History", default_open=False):
                with dpg.group(horizontal=True):
                    dpg.add_input_text(
                        tag=self.TAG_VERSION_FILE_INPUT,
                        width=400,
                        hint="File path for history...",
                    )
                    browse_btn = dpg.add_button(label="Browse...", callback=self._show_version_file_dialog)
                    add_tooltip(browse_btn, SETTINGS_TOOLTIPS["version_browse"])
                    view_btn = dpg.add_button(label="View History", callback=self._on_view_history)
                    add_tooltip(view_btn, SETTINGS_TOOLTIPS["version_view_history"])
                    save_btn = dpg.add_button(label="Save Version", callback=self._on_save_version)
                    add_tooltip(save_btn, SETTINGS_TOOLTIPS["version_save"])

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
            dpg.add_spacer(height=10)
            dpg.add_button(label="Save Preferences", callback=self._on_save_settings)

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
        self.config.ai.summary_provider = dpg.get_value(self.TAG_SUMMARY_PROVIDER)
        self.config.ai.summary_model_local = dpg.get_value(self.TAG_SUMMARY_MODEL_LOCAL)
        self.config.ai.summary_model_openai = dpg.get_value(self.TAG_SUMMARY_MODEL_OPENAI)
        self.config.ai.summary_model_anthropic = dpg.get_value(self.TAG_SUMMARY_MODEL_ANTHROPIC)
        self.config.ai.summary_model_google = dpg.get_value(self.TAG_SUMMARY_MODEL_GOOGLE)
        self.config.ai.summary_max_tokens = dpg.get_value(self.TAG_SUMMARY_MAX_TOKENS)
        self.config.ai.summary_temperature = dpg.get_value(self.TAG_SUMMARY_TEMPERATURE)
        self.config.ai.metadata_location_lookup = dpg.get_value(self.TAG_METADATA_LOCATION_LOOKUP)
        self.config.ai.metadata_location_level = dpg.get_value(self.TAG_METADATA_LOCATION_LEVEL)
        save_config()
        self.versioning_service.refresh_tracked_folders()
        self._refresh_recent_changes()
        self.update_status("Preferences saved (general, duplicates, scan, AI, summaries, metadata)")

    def _on_add_tracked_folder(self) -> None:
        """Add a folder to version tracking."""
        raw_path = dpg.get_value(self.TAG_VERSION_FOLDER_INPUT).strip().strip('"')
        if not raw_path:
            self.update_status("Enter a folder path to track.", level="warning")
            return

        normalized = normalize_path(raw_path)
        if not os.path.exists(normalized):
            self.update_status(f"Folder does not exist: {normalized}", level="error")
            return
        if not os.path.isdir(normalized):
            self.update_status(f"Path is not a folder: {normalized}", level="error")
            return

        existing = {normalize_path(p).lower() for p in self.config.versioning.tracked_folders}
        if normalized.lower() in existing:
            self.update_status("Folder is already tracked.", level="warning")
            dpg.configure_item(self.TAG_VERSION_FOLDER_LIST, items=self.config.versioning.tracked_folders)
            return

        self.config.versioning.tracked_folders.append(normalized)
        save_config()
        dpg.set_value(self.TAG_VERSION_FOLDER_INPUT, "")
        dpg.configure_item(self.TAG_VERSION_FOLDER_LIST, items=self.config.versioning.tracked_folders)
        self.versioning_service.refresh_tracked_folders()
        self._refresh_recent_changes()
        self.update_status("Added folder to version tracking.", level="info")

    def _on_remove_tracked_folder(self) -> None:
        """Remove the selected tracked folder."""
        selected = dpg.get_value(self.TAG_VERSION_FOLDER_LIST)
        if not selected:
            self.update_status("Select a folder to remove.", level="warning")
            return

        normalized = normalize_path(selected)
        self.config.versioning.tracked_folders = [
            path for path in self.config.versioning.tracked_folders
            if normalize_path(path).lower() != normalized.lower()
        ]
        save_config()
        dpg.configure_item(self.TAG_VERSION_FOLDER_LIST, items=self.config.versioning.tracked_folders)
        self.versioning_service.refresh_tracked_folders()
        self._refresh_recent_changes()
        self.update_status("Removed tracked folder.", level="info")

    def _on_versioning_settings_changed(self, sender, app_data, user_data) -> None:
        """Persist versioning settings as they change."""
        self.config.versioning.include_subfolders = bool(dpg.get_value(self.TAG_VERSION_INCLUDE_SUBFOLDERS))
        self.config.versioning.auto_commit_mode = dpg.get_value(self.TAG_VERSION_AUTO_MODE)
        max_size = dpg.get_value(self.TAG_VERSION_MAX_SIZE)
        try:
            self.config.versioning.max_file_size_mb = max(1.0, float(max_size))
        except (TypeError, ValueError):
            self.config.versioning.max_file_size_mb = 50.0
            dpg.set_value(self.TAG_VERSION_MAX_SIZE, 50.0)

        save_config()
        self.versioning_service.refresh_tracked_folders()
        self.update_status("Version tracking settings updated.", level="info")

    def _show_version_file_dialog(self) -> None:
        """Show file dialog for version history."""
        if not dpg.does_item_exist(self.TAG_VERSION_FILE_DIALOG):
            with dpg.file_dialog(
                tag=self.TAG_VERSION_FILE_DIALOG,
                show=False,
                modal=True,
                width=700,
                height=400,
                callback=self._on_version_file_selected,
            ):
                dpg.add_file_extension(".*", color=(255, 255, 255))

        dpg.show_item(self.TAG_VERSION_FILE_DIALOG)

    def _on_version_file_selected(self, sender, app_data) -> None:
        """Handle file selection for version history."""
        path = app_data.get("file_path_name")
        if path:
            dpg.set_value(self.TAG_VERSION_FILE_INPUT, path)

    def _on_view_history(self) -> None:
        """Open version history dialog for the selected file."""
        raw_path = dpg.get_value(self.TAG_VERSION_FILE_INPUT).strip().strip('"')
        if not raw_path:
            self.update_status("Choose a file to view history.", level="warning")
            return

        file_path = Path(raw_path)
        if not file_path.exists():
            self.update_status(f"File not found: {file_path}", level="error")
            return

        tracker = self._get_tracker_for_path(file_path)
        if tracker is None:
            self.update_status("File is not inside a tracked folder.", level="warning")
            return
        if not tracker.is_available():
            self.update_status("Version tracking unavailable (GitPython missing).", level="warning")
            return
        if not tracker.init_repository():
            self.update_status("Failed to initialize version tracking repository.", level="error")
            return

        history = tracker.get_file_history(file_path)
        if not history:
            self.update_status("No history found for this file.", level="warning")
            return

        self._version_history_file = file_path
        self._version_history_entries = history
        self._selected_history_commit = None
        self._ensure_version_history_dialog()
        dpg.set_value(self.TAG_VERSION_HISTORY_LABEL, f"History for: {file_path}")
        self._populate_version_history_table(history)
        dpg.set_value(self.TAG_VERSION_DIFF_TEXT, "")
        dpg.set_value(self.TAG_VERSION_DIFF_LABEL, "Diff (select a commit)")
        dpg.configure_item(self.TAG_VERSION_RESTORE_BUTTON, enabled=False)
        dpg.configure_item(self.TAG_VERSION_OPEN_BUTTON, enabled=file_path.exists())
        dpg.show_item(self.TAG_VERSION_HISTORY_DIALOG)

    def _on_save_version(self) -> None:
        """Manually save a version for the selected file."""
        raw_path = dpg.get_value(self.TAG_VERSION_FILE_INPUT).strip().strip('"')
        if not raw_path:
            self.update_status("Choose a file to save a version.", level="warning")
            return

        file_path = Path(raw_path)
        if not file_path.exists():
            self.update_status(f"File not found: {file_path}", level="error")
            return

        tracker = self._get_tracker_for_path(file_path)
        if tracker is None:
            self.update_status("File is not inside a tracked folder.", level="warning")
            return
        if not tracker.is_available():
            self.update_status("Version tracking unavailable (GitPython missing).", level="warning")
            return
        if not tracker.init_repository():
            self.update_status("Failed to initialize version tracking repository.", level="error")
            return

        committed = tracker.commit_files([file_path], f"Manual save: {file_path.name}")
        if committed:
            self.update_status("Version saved.", level="info")
            self._refresh_recent_changes()
        else:
            self.update_status("No changes to save.", level="warning")

    def _refresh_recent_changes(self) -> None:
        """Refresh the recent changes table."""
        if not dpg.does_item_exist(self.TAG_VERSION_RECENT_TABLE):
            return

        children = dpg.get_item_children(self.TAG_VERSION_RECENT_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        tracked = self.config.versioning.tracked_folders
        if not tracked:
            return

        changes: list[ChangeEntry] = []
        for folder in tracked:
            tracker = self._build_tracker(folder)
            if tracker is None or not tracker.is_available():
                continue
            if not tracker.init_repository():
                continue
            changes.extend(tracker.get_recent_changes(limit=50))

        changes.sort(key=lambda item: item.committed_at, reverse=True)
        for change in changes[:50]:
            with dpg.table_row(parent=self.TAG_VERSION_RECENT_TABLE):
                dpg.add_text(change.file_path)
                dpg.add_text(change.committed_at.strftime("%Y-%m-%d %H:%M"))
                dpg.add_text(change.message)

    def _ensure_version_history_dialog(self) -> None:
        """Create the version history dialog if missing."""
        if dpg.does_item_exist(self.TAG_VERSION_HISTORY_DIALOG):
            return

        with dpg.window(
            tag=self.TAG_VERSION_HISTORY_DIALOG,
            label="Version History",
            modal=True,
            show=False,
            width=900,
            height=520,
            no_resize=True,
        ):
            dpg.add_text("", tag=self.TAG_VERSION_HISTORY_LABEL, color=get_text_color("secondary"))
            dpg.add_spacer(height=5)
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
                dpg.add_table_column(label="Date", init_width_or_weight=140)
                dpg.add_table_column(label="Author", init_width_or_weight=160)
                dpg.add_table_column(label="Message", init_width_or_weight=240)
                dpg.add_table_column(label="Size", init_width_or_weight=80)
                dpg.add_table_column(label="Changes", init_width_or_weight=100)

            dpg.add_spacer(height=6)
            dpg.add_text("Diff", tag=self.TAG_VERSION_DIFF_LABEL, color=get_text_color("secondary"))
            dpg.add_input_text(
                tag=self.TAG_VERSION_DIFF_TEXT,
                multiline=True,
                readonly=True,
                width=-1,
                height=140,
            )
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Restore Selected",
                    tag=self.TAG_VERSION_RESTORE_BUTTON,
                    callback=self._on_restore_version,
                    enabled=False,
                )
                dpg.add_button(
                    label="Open File",
                    tag=self.TAG_VERSION_OPEN_BUTTON,
                    callback=self._on_open_history_file,
                    enabled=False,
                )
                dpg.add_spacer(width=10)
                dpg.add_button(label="Close", callback=lambda: dpg.hide_item(self.TAG_VERSION_HISTORY_DIALOG))

    def _populate_version_history_table(self, history: list[VersionEntry]) -> None:
        """Render history table rows."""
        children = dpg.get_item_children(self.TAG_VERSION_HISTORY_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        for entry in history:
            with dpg.table_row(parent=self.TAG_VERSION_HISTORY_TABLE):
                label = entry.committed_at.strftime("%Y-%m-%d %H:%M")
                dpg.add_selectable(
                    label=label,
                    callback=self._on_history_selected,
                    user_data=entry.commit_hash,
                    span_columns=False,
                )
                dpg.add_text(entry.author)
                dpg.add_text(entry.message)
                dpg.add_text(self._format_bytes(entry.size_bytes or 0))
                if entry.insertions is not None and entry.deletions is not None:
                    dpg.add_text(f"+{entry.insertions} / -{entry.deletions}")
                else:
                    dpg.add_text("-")

    def _on_history_selected(self, sender, app_data, user_data) -> None:
        """Handle version history row selection."""
        commit_hash = str(user_data)
        self._selected_history_commit = commit_hash
        dpg.configure_item(self.TAG_VERSION_RESTORE_BUTTON, enabled=True)

        if not self._version_history_file or not self._version_history_entries:
            return

        tracker = self._get_tracker_for_path(self._version_history_file)
        if tracker is None:
            return

        diff_text = ""
        label = "Diff"
        for idx, entry in enumerate(self._version_history_entries):
            if entry.commit_hash == commit_hash:
                parent_hash = None
                if idx + 1 < len(self._version_history_entries):
                    parent_hash = self._version_history_entries[idx + 1].commit_hash
                if parent_hash:
                    diff_text = tracker.diff_versions(self._version_history_file, parent_hash, commit_hash)
                    label = f"Diff {parent_hash[:8]} -> {commit_hash[:8]}"
                else:
                    label = f"Diff (initial commit {commit_hash[:8]})"
                break

        dpg.set_value(self.TAG_VERSION_DIFF_TEXT, diff_text)
        dpg.set_value(self.TAG_VERSION_DIFF_LABEL, label)

    def _on_restore_version(self) -> None:
        """Restore the selected version of the file."""
        if not self._version_history_file or not self._selected_history_commit:
            self.update_status("Select a version to restore.", level="warning")
            return

        tracker = self._get_tracker_for_path(self._version_history_file)
        if tracker is None:
            self.update_status("Tracked repository not found.", level="warning")
            return

        restored = tracker.restore_file(self._version_history_file, self._selected_history_commit)
        if restored:
            self.update_status("Version restored.", level="info")
            self._on_view_history()
            self._refresh_recent_changes()
        else:
            self.update_status("Failed to restore version.", level="error")

    def _on_open_history_file(self) -> None:
        """Open the history file in the default application."""
        if not self._version_history_file:
            return
        try:
            os.startfile(str(self._version_history_file))
        except Exception as exc:
            logger.error("Failed to open file: %s", exc)
            self.update_status("Failed to open file.", level="error")

    def _get_tracker_for_path(self, file_path: Path) -> Optional[VersionTracker]:
        """Return a VersionTracker for a file if it is in a tracked folder."""
        resolved = file_path.resolve()
        for folder in self.config.versioning.tracked_folders:
            root = Path(folder).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            return self._build_tracker(root)
        return None

    def _build_tracker(self, root_path: str | Path) -> Optional[VersionTracker]:
        """Build a VersionTracker for the given root path."""
        root = Path(root_path)
        if not root.exists():
            return None
        return VersionTracker(
            root_path=str(root),
            include_patterns=self.config.versioning.include_patterns or None,
            exclude_patterns=self.config.versioning.exclude_patterns,
            include_subfolders=self.config.versioning.include_subfolders,
            max_file_size_mb=self.config.versioning.max_file_size_mb,
        )

    def run(self) -> None:
        """Run the application main loop."""
        logger.info("Starting DupliCleaner")

        # Update initial status
        with profile_block("startup.db_statistics"):
            stats = self.db.get_statistics()
            self.update_file_count(stats["total_files"])
            self.update_storage_info(stats["total_size"])

        # Check GPU availability
        with profile_block("startup.gpu_ui"):
            self._refresh_gpu_ui_state()

        # Start background version tracking
        with profile_block("startup.versioning_service.start"):
            self.versioning_service.start()

        # Main render loop
        while dpg.is_dearpygui_running():
            if self.faces_panel:
                self.faces_panel.on_frame()
            dpg.render_dearpygui_frame()

        self.cleanup()

    def cleanup(self) -> None:
        """Clean up resources before exit."""
        logger.info("Cleaning up...")

        # Clean up UI panels
        if self.drives_panel:
            self.drives_panel.cleanup()
        if self.duplicates_panel:
            self.duplicates_panel.cleanup()
        if self.faces_panel:
            self.faces_panel.cleanup()
        if self.organize_panel:
            self.organize_panel.destroy()
        if self.search_panel:
            self.search_panel.cleanup()
        if self.status_log_panel:
            self.status_log_panel.cleanup()

        self.versioning_service.stop()
        save_config()
        dpg.destroy_context()
        logger.info("DupliCleaner shutdown complete")

    def _detect_cuda_available(self) -> bool:
        """Return True if CUDA is usable for AI workloads."""
        try:
            import torch
            if not torch.cuda.is_available():
                logger.info("GPU check: torch.cuda.is_available() is False")
                return False
        except ImportError:
            logger.info("GPU check: torch not installed")
            return False

        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if "CUDAExecutionProvider" not in providers:
                logger.info("GPU check: onnxruntime missing CUDAExecutionProvider")
                return False
            if os.name == "nt":
                import ctypes
                capi_dir = Path(ort.__file__).resolve().parent / "capi"
                provider_dll = capi_dir / "onnxruntime_providers_cuda.dll"
                if provider_dll.exists():
                    try:
                        ctypes.WinDLL(str(provider_dll))
                    except OSError:
                        logger.info("GPU check: failed to load onnxruntime_providers_cuda.dll")
                        return False
        except ImportError:
            # Allow GPU for torch-only features if onnxruntime isn't installed yet.
            logger.info("GPU check: onnxruntime not installed (allowing torch-only GPU features)")
            return True

        return True

    def _get_gpu_block_reason(self) -> str:
        """Return a human-readable reason for GPU being unavailable."""
        if self.config.ai.dependency_variant == "cpu":
            return "GPU disabled (dependency variant set to CPU-only)."
        try:
            import torch
            if not torch.cuda.is_available():
                return "CUDA not available (torch.cuda.is_available() is False)."
        except ImportError:
            return "PyTorch not installed."

        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if "CUDAExecutionProvider" not in providers:
                return "ONNX Runtime CUDA provider not available."
        except ImportError:
            return "ONNX Runtime not installed (GPU limited to torch-only features)."

        return "GPU unavailable (unknown reason)."

    def _get_cuda_info(self) -> tuple[str, str]:
        """Return (driver_version, cuda_version) from nvidia-smi if available."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version,cuda_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return ("unknown", "unknown")
            line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                return (parts[0], parts[1])
        except Exception:
            pass
        return ("unknown", "unknown")

    def _get_gpu_help_text(self) -> str:
        """Build guidance text for GPU setup."""
        reason = self._get_gpu_block_reason()
        driver_version, cuda_version = self._get_cuda_info()
        cuda_hint = "cu121"
        if cuda_version.startswith("11."):
            cuda_hint = "cu118"
        elif cuda_version.startswith("12."):
            cuda_hint = "cu121"

        lines = [
            f"Status: {reason}",
            f"NVIDIA driver: {driver_version}",
            f"CUDA version: {cuda_version}",
            "",
            "Install CUDA-enabled PyTorch (example):",
            f"pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/{cuda_hint}",
            "",
            "Install ONNX Runtime GPU (for InsightFace GPU):",
            "pip install onnxruntime-gpu",
            "",
            "Verify:",
            "python - <<'PY'\nimport torch\nprint(torch.cuda.is_available())\nprint(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')\nPY",
        ]
        return "\n".join(lines)

    def _apply_gpu_defaults(self) -> None:
        """Set GPU defaults based on availability and user preference."""
        if self.config.first_run and self._cuda_available:
            self.config.ai.dependency_variant = "gpu"

        if self.config.ai.dependency_variant == "cpu":
            self.config.ai.use_gpu = False
        elif not self._cuda_available:
            self.config.ai.use_gpu = False

    def _refresh_gpu_ui_state(self) -> None:
        """Update GPU status text and settings state."""
        if self._cuda_available:
            try:
                import torch
                gpu_name = torch.cuda.get_device_name(0)
                self.update_gpu_status(f"CUDA ({gpu_name})")
            except Exception:
                self.update_gpu_status("CUDA available")
        else:
            self.update_gpu_status("CPU only")

        if dpg.does_item_exist("settings_ai_use_gpu"):
            dpg.set_value("settings_ai_use_gpu", self.config.ai.use_gpu)
            dpg.configure_item("settings_ai_use_gpu", enabled=self.config.ai.dependency_variant != "cpu")
        if dpg.does_item_exist(self.TAG_GPU_STATUS_HINT):
            hint = "" if self._cuda_available else self._get_gpu_block_reason()
            dpg.set_value(self.TAG_GPU_STATUS_HINT, hint)
        if dpg.does_item_exist(self.TAG_GPU_HELP_GROUP):
            dpg.configure_item(self.TAG_GPU_HELP_GROUP, show=not self._cuda_available)
        if dpg.does_item_exist(self.TAG_GPU_HELP_TEXT):
            dpg.set_value(self.TAG_GPU_HELP_TEXT, self._get_gpu_help_text() if not self._cuda_available else "")

    def _on_ai_use_gpu_changed(self, sender, app_data, user_data) -> None:
        """Persist GPU toggle immediately."""
        want_gpu = bool(dpg.get_value("settings_ai_use_gpu"))
        if want_gpu and not self._cuda_available:
            self.config.ai.use_gpu = False
            dpg.set_value("settings_ai_use_gpu", False)
            reason = self._get_gpu_block_reason()
            self.update_status(f"GPU disabled: {reason}", level="warning")
            if dpg.does_item_exist(self.TAG_GPU_STATUS_HINT):
                dpg.set_value(self.TAG_GPU_STATUS_HINT, reason)
        else:
            self.config.ai.use_gpu = want_gpu
        save_config()

    def _on_theme_changed(self, sender, app_data, user_data) -> None:
        """Handle theme selection change."""
        theme_name = app_data.lower()
        self.config.ui.theme = theme_name
        apply_theme(theme_name)
        save_config()
        self.update_status(f"Theme changed to {app_data}", level="info")


def run_app() -> None:
    """Entry point to run the application."""
    setup_logging()
    app = DupliCleanerApp()
    app.setup()
    app.run()
