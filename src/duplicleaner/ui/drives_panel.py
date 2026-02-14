"""Drives Panel for DupliCleaner.

Dear PyGui UI component for managing drives and initiating scans.
"""

import contextlib
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

import dearpygui.dearpygui as dpg

from duplicleaner.core.actions import ActionEngine, ActionType, OperationProgress, PendingAction
from duplicleaner.core.analysis_runner import AnalysisOptions, AnalysisRunner
from duplicleaner.core.face_worker import FaceAnalysisWorker
from duplicleaner.core.hasher import Hasher, HashProgress, HashState
from duplicleaner.core.folder_watcher import FolderWatcher
from duplicleaner.core.scanner import RecoveryManager, ScanMode, Scanner, ScanProgress, ScanState
from duplicleaner.db.models import Drive
from duplicleaner.drives.manager import DriveInfo, DriveManager, DriveStatus
from duplicleaner.drives.redundancy import (
    BackupPlanItem,
    ExclusionCandidate,
    RedundancyChecker,
    RedundancyReport,
)
from duplicleaner.ui.theme import get_accent_color
from duplicleaner.ui.tooltips import DRIVE_TOOLTIPS, add_tooltip
from duplicleaner.utils.config import get_config, save_config
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


class DrivesPanel:
    """UI panel for drive management and scanning."""

    # Tag constants
    TAG_PANEL = "drives_panel"
    TAG_DRIVE_LIST = "drive_list_table"
    TAG_ADD_DIALOG = "add_drive_dialog"
    TAG_SCAN_PROGRESS = "scan_progress_group"
    TAG_PROGRESS_BAR = "scan_progress_bar"
    TAG_PROGRESS_TEXT = "scan_progress_text"
    TAG_CURRENT_FILE = "scan_current_file"
    TAG_RESUME_SCAN_BUTTON = "scan_resume_btn"
    TAG_HASH_FORCE = "hash_force_rehash"
    TAG_REDUNDANCY_SUMMARY = "redundancy_summary_text"
    TAG_AT_RISK_TABLE = "at_risk_table"
    TAG_BACKUP_SOURCE = "backup_source_path"
    TAG_BACKUP_TARGETS_GROUP = "backup_targets_group"
    TAG_BACKUP_EXCLUDES = "backup_excludes"
    TAG_BACKUP_EXCLUDE_TABLE = "backup_exclude_table"
    TAG_PROJECT_DETECTIONS = "backup_project_detections"
    TAG_PROJECT_SUGGESTIONS = "backup_project_suggestions"
    TAG_BACKUP_PLAN_TABLE = "backup_plan_table"
    TAG_BACKUP_PROGRESS_GROUP = "backup_progress_group"
    TAG_BACKUP_PROGRESS_BAR = "backup_progress_bar"
    TAG_BACKUP_PROGRESS_TEXT = "backup_progress_text"
    TAG_BACKUP_PAUSE_BUTTON = "backup_pause_btn"
    TAG_BACKUP_CANCEL_BUTTON = "backup_cancel_btn"
    TAG_BACKUP_EXPORT_BUTTON = "backup_export_btn"
    TAG_BACKUP_OPEN_TARGET_BUTTON = "backup_open_target_btn"
    TAG_FULL_SCAN_FIRST = "full_analysis_scan_first"
    TAG_FULL_REANALYZE = "full_analysis_reanalyze"
    TAG_FULL_METADATA = "full_analysis_include_metadata"
    TAG_FULL_SCENES = "full_analysis_include_scenes"
    TAG_FULL_OBJECTS = "full_analysis_include_objects"
    TAG_FULL_OCR = "full_analysis_include_ocr"
    TAG_FULL_SUMMARIES = "full_analysis_include_summaries"
    TAG_FULL_IMAGES = "full_analysis_include_images"
    TAG_FULL_DOCS = "full_analysis_include_docs"
    TAG_FULL_DATA = "full_analysis_include_data"
    TAG_FULL_DOC_EXTENSIONS = "full_analysis_doc_extensions"
    TAG_FULL_DATA_EXTENSIONS = "full_analysis_data_extensions"
    TAG_BG_ANALYSIS = "full_analysis_background"
    TAG_BG_HASH = "full_hash_background"
    TAG_SCAN_ALL_DIALOG = "scan_all_dialog"
    TAG_SCAN_ALL_MODE = "scan_all_mode"
    TAG_BG_STATUS = "background_status_text"
    TAG_GETTING_STARTED = "drives_getting_started"
    TAG_SELECTED_SUMMARY = "drives_selected_summary"
    TAG_SCAN_HELP = "drives_scan_help"
    TAG_ANALYSIS_HEADER = "drives_analysis_header"
    TAG_ADVANCED_HEADER = "drives_advanced_header"
    TAG_BACKUP_HEADER = "drives_backup_header"
    TAG_BTN_REMOVE = "drives_btn_remove"
    TAG_BTN_QUICK = "drives_btn_quick"
    TAG_BTN_DEEP = "drives_btn_deep"
    TAG_BTN_FULL = "drives_btn_full"
    TAG_BTN_SCAN_ALL = "drives_btn_scan_all"
    TAG_BTN_HASH = "drives_btn_hash"
    TAG_BTN_RESET = "drives_btn_reset"
    TAG_BTN_REFRESH = "drives_btn_refresh"
    TAG_BTN_REDUNDANCY = "drives_btn_redundancy"
    TAG_BTN_BACKUP_BUILD = "drives_btn_backup_build"
    TAG_BTN_BACKUP_EXECUTE = "drives_btn_backup_execute"
    TAG_BTN_BACKUP_ANALYZE = "drives_btn_backup_analyze"

    # Remap dialog tags
    TAG_REMAP_DIALOG = "remap_drive_dialog"
    TAG_REMAP_PATH = "remap_drive_path"

    # Corrupt files tags
    TAG_CORRUPT_HEADER = "drives_corrupt_header"
    TAG_CORRUPT_TABLE = "corrupt_files_table"
    TAG_CORRUPT_COUNT = "corrupt_files_count_text"
    TAG_CORRUPT_PROGRESS = "corrupt_scan_progress_group"
    TAG_CORRUPT_PROGRESS_BAR = "corrupt_scan_progress_bar"
    TAG_CORRUPT_PROGRESS_TEXT = "corrupt_scan_progress_text"
    TAG_BTN_CHECK_CORRUPT = "drives_btn_check_corrupt"
    TAG_BTN_RECOVER_ALL = "drives_btn_recover_all"
    TAG_RECOVERY_PROGRESS = "recovery_progress_group"
    TAG_RECOVERY_PROGRESS_BAR = "recovery_progress_bar"
    TAG_RECOVERY_PROGRESS_TEXT = "recovery_progress_text"

    # Watch folders tags
    TAG_WATCH_HEADER = "drives_watch_header"
    TAG_WATCH_ENABLED = "watch_global_enabled"
    TAG_WATCH_TABLE = "watch_folders_table"
    TAG_WATCH_PATH_INPUT = "watch_folder_path_input"
    TAG_WATCH_ADD_DIALOG = "watch_add_folder_dialog"
    TAG_WATCH_POLL_INTERVAL = "watch_poll_interval"
    TAG_WATCH_DEBOUNCE = "watch_debounce"
    TAG_WATCH_AUTO_SCAN = "watch_auto_scan"
    TAG_WATCH_AUTO_ORGANIZE = "watch_auto_organize"
    TAG_WATCH_AUTO_AI = "watch_auto_ai"
    TAG_WATCH_ORG_FORMAT = "watch_organize_format"
    TAG_WATCH_STATUS = "watch_status_text"
    TAG_BTN_WATCH_ADD = "drives_btn_watch_add"
    TAG_BTN_WATCH_START = "drives_btn_watch_start"
    TAG_WATCH_FOLDER_DIALOG = "watch_folder_browse_dialog"

    # Folder summarization tags
    TAG_SUMMARIZE_HEADER = "drives_summarize_header"
    TAG_SUMMARIZE_FOLDER = "summarize_folder_input"
    TAG_SUMMARIZE_PROVIDER = "summarize_provider_combo"
    TAG_SUMMARIZE_MODEL = "summarize_model_input"
    TAG_SUMMARIZE_FILE_TYPES = "summarize_file_types_input"
    TAG_SUMMARIZE_LIMIT = "summarize_limit_input"
    TAG_SUMMARIZE_BATCH_MODE = "summarize_batch_mode_checkbox"
    TAG_SUMMARIZE_MODEL_STATUS = "summarize_model_status_text"
    TAG_BTN_SUMMARIZE = "drives_btn_summarize"
    TAG_BTN_SUMMARIZE_BROWSE = "drives_btn_summarize_browse"
    TAG_SUMMARIZE_PROGRESS = "summarize_progress_group"
    TAG_SUMMARIZE_PROGRESS_BAR = "summarize_progress_bar"
    TAG_SUMMARIZE_PROGRESS_TEXT = "summarize_progress_text"
    TAG_SUMMARIZE_DIALOG = "summarize_folder_dialog"

    def __init__(
        self,
        parent: int | str,
        drive_manager: DriveManager | None = None,
        on_scan_complete: Callable[[str], None] | None = None,
        on_status_update: Callable[[str], None] | None = None,
        on_face_worker_state_change: Callable[[bool], None] | None = None,
        folder_watcher: FolderWatcher | None = None,
    ):
        """Initialize the drives panel.

        Args:
            parent: Parent window/container tag
            drive_manager: DriveManager instance (creates one if not provided)
            on_scan_complete: Callback when scan completes (drive_id)
            folder_watcher: FolderWatcher instance for watch folder management
        """
        self.parent = parent
        self.drive_manager = drive_manager or DriveManager(status_callback=self._on_drive_status_change)
        self.on_scan_complete = on_scan_complete
        self.on_status_update = on_status_update
        self.on_face_worker_state_change = on_face_worker_state_change
        self._folder_watcher = folder_watcher
        self.redundancy_checker = RedundancyChecker(self.drive_manager.db, self.drive_manager)
        self.config = get_config()

        # Current scanner and hasher
        self._scanner: Scanner | None = None
        self._hasher: Hasher | None = None
        self._scan_thread: threading.Thread | None = None
        self._current_scan_drive: str | None = None
        self._resume_state: dict | None = None
        self._face_worker: FaceAnalysisWorker | None = None
        self._face_worker_drive_id: str | None = None

        # Selected drive
        self._selected_drive_id: str | None = None
        self._redundancy_report: RedundancyReport | None = None
        self._analytics_report = None  # StorageReport
        self._backup_plan: list[BackupPlanItem] = []
        self._drive_label_map: dict[str, str] = {}
        self._action_engine: ActionEngine | None = None
        self._backup_thread: threading.Thread | None = None
        self._analysis_thread: threading.Thread | None = None
        self._analysis_worker_thread: threading.Thread | None = None
        self._analysis_worker_stop = threading.Event()
        self._hash_worker_thread: threading.Thread | None = None
        self._hash_worker_stop = threading.Event()
        self._hash_lock = threading.Lock()
        self._queue_lock = threading.Lock()
        self._selection_tags: dict[str, str] = {}
        self._suppress_selection_events = False
        self._scan_all_queue: list[str] = []
        self._scan_all_mode: ScanMode | None = None
        self._scan_all_active = False
        self._corrupt_scan_thread: threading.Thread | None = None
        self._recovery_thread: threading.Thread | None = None
        self._recovery_manager: RecoveryManager | None = None
        self._corrupt_files_cache: list[dict] = []
        self._pending_full_refresh = True
        self._full_refresh_after = time.time() + 0.5
        self._pending_monitor_start = True
        self._monitor_start_after = time.time() + 0.5

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the panel UI."""
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            # Header
            dpg.add_text("Drives Management", color=get_accent_color())
            dpg.add_separator()
            dpg.add_spacer(height=10)

            with dpg.group(tag=self.TAG_GETTING_STARTED, show=False):
                dpg.add_text("Getting Started", color=get_accent_color())
                dpg.add_text("1) Add a drive or network share to scan.")
                dpg.add_text("2) Select a drive from the list.")
                dpg.add_text("3) Run a Quick Scan to begin.")
                dpg.add_spacer(height=8)

            # Action buttons
            with dpg.group(horizontal=True):
                btn = dpg.add_button(label="Add Drive", callback=self._on_add_drive_click)
                add_tooltip(btn, DRIVE_TOOLTIPS["add_drive"])
                btn = dpg.add_button(label="Remove Drive", tag=self.TAG_BTN_REMOVE, callback=self._on_remove_drive_click)
                add_tooltip(btn, DRIVE_TOOLTIPS["remove_selected"])
                dpg.add_spacer(width=20)
                btn = dpg.add_button(
                    label="Quick Scan",
                    tag=self.TAG_BTN_QUICK,
                    callback=lambda: self._on_scan_click(ScanMode.QUICK),
                )
                add_tooltip(btn, DRIVE_TOOLTIPS["quick_scan"])
                btn = dpg.add_button(
                    label="Deep Scan",
                    tag=self.TAG_BTN_DEEP,
                    callback=lambda: self._on_scan_click(ScanMode.DEEP),
                )
                add_tooltip(btn, DRIVE_TOOLTIPS["deep_scan"])
                btn = dpg.add_button(
                    label="Full Analysis",
                    tag=self.TAG_BTN_FULL,
                    callback=lambda: self._on_scan_click(ScanMode.FULL),
                )
                add_tooltip(btn, DRIVE_TOOLTIPS["full_analysis"])
                btn = dpg.add_button(label="Scan All...", tag=self.TAG_BTN_SCAN_ALL, callback=self._on_scan_all_click)
                add_tooltip(btn, DRIVE_TOOLTIPS["scan_all"])
                btn = dpg.add_button(label="Generate Hashes", tag=self.TAG_BTN_HASH, callback=self._on_hash_click)
                add_tooltip(btn, DRIVE_TOOLTIPS["hash_now"])
                btn = dpg.add_button(
                    label="Resume Scan",
                    tag=self.TAG_RESUME_SCAN_BUTTON,
                    callback=self._on_resume_scan_click,
                    enabled=False,
                )
                add_tooltip(btn, DRIVE_TOOLTIPS["resume_scan"])
            dpg.add_text("Selected drive: None", tag=self.TAG_SELECTED_SUMMARY)
            dpg.add_text(
                "Quick: fastest | Deep: more thorough | Full Analysis: AI content analysis (slowest)",
                tag=self.TAG_SCAN_HELP,
            )

            with dpg.collapsing_header(
                label="Analysis Options",
                default_open=False,
                tag=self.TAG_ANALYSIS_HEADER,
            ):
                with dpg.group(horizontal=True):
                    cb = dpg.add_checkbox(
                        label="Scan before Full Analysis",
                        tag=self.TAG_FULL_SCAN_FIRST,
                        default_value=self.config.ai.analysis_scan_before_full,
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["scan_before_full"])
                    cb = dpg.add_checkbox(
                        label="Re-analyze existing",
                        tag=self.TAG_FULL_REANALYZE,
                        default_value=self.config.ai.analysis_reanalyze_existing,
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["reanalyze_existing"])
                    cb = dpg.add_checkbox(
                        label="Background analysis during scan",
                        tag=self.TAG_BG_ANALYSIS,
                        default_value=self.config.ai.analysis_background_during_scan,
                        callback=lambda *_: self._update_background_status(),
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["bg_analysis"])
                    cb = dpg.add_checkbox(
                        label="Background hashing during scan",
                        tag=self.TAG_BG_HASH,
                        default_value=self.config.ai.hash_background_during_scan,
                        callback=lambda *_: self._update_background_status(),
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["bg_hash"])
                with dpg.group(horizontal=True):
                    cb = dpg.add_checkbox(
                        label="Metadata",
                        tag=self.TAG_FULL_METADATA,
                        default_value=self.config.ai.analysis_include_metadata,
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["analysis_metadata"])
                    cb = dpg.add_checkbox(
                        label="Scenes",
                        tag=self.TAG_FULL_SCENES,
                        default_value=self.config.ai.analysis_include_scenes,
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["analysis_scenes"])
                    cb = dpg.add_checkbox(
                        label="Objects",
                        tag=self.TAG_FULL_OBJECTS,
                        default_value=self.config.ai.analysis_include_objects,
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["analysis_objects"])
                    cb = dpg.add_checkbox(
                        label="OCR/Text",
                        tag=self.TAG_FULL_OCR,
                        default_value=self.config.ai.analysis_include_ocr,
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["analysis_ocr"])
                    cb = dpg.add_checkbox(
                        label="Summaries",
                        tag=self.TAG_FULL_SUMMARIES,
                        default_value=self.config.ai.analysis_include_summaries,
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["analysis_summaries"])
                with dpg.group(horizontal=True):
                    cb = dpg.add_checkbox(
                        label="Images",
                        tag=self.TAG_FULL_IMAGES,
                        default_value=self.config.ai.analysis_include_images,
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["analysis_images"])
                    cb = dpg.add_checkbox(
                        label="Docs",
                        tag=self.TAG_FULL_DOCS,
                        default_value=self.config.ai.analysis_include_documents,
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["analysis_docs"])
                    cb = dpg.add_checkbox(
                        label="Data",
                        tag=self.TAG_FULL_DATA,
                        default_value=self.config.ai.analysis_include_data_files,
                    )
                    add_tooltip(cb, DRIVE_TOOLTIPS["analysis_data"])
                with dpg.group(horizontal=True):
                    inp = dpg.add_input_text(
                        tag=self.TAG_FULL_DOC_EXTENSIONS,
                        default_value=", ".join(self.config.ai.analysis_doc_extensions),
                        width=360,
                        hint="Doc extensions",
                    )
                    add_tooltip(inp, DRIVE_TOOLTIPS["doc_extensions"])
                    inp = dpg.add_input_text(
                        tag=self.TAG_FULL_DATA_EXTENSIONS,
                        default_value=", ".join(self.config.ai.analysis_data_extensions),
                        width=260,
                        hint="Data extensions",
                    )
                    add_tooltip(inp, DRIVE_TOOLTIPS["data_extensions"])
                dpg.add_text("", tag=self.TAG_BG_STATUS)

            with dpg.collapsing_header(
                label="Generate Summaries for Folder",
                default_open=False,
                tag=self.TAG_SUMMARIZE_HEADER,
            ):
                dpg.add_text(
                    "Generate AI summaries for files. Uses selected drive below OR enter a folder path.",
                    wrap=600
                )
                dpg.add_text(
                    "If path not scanned, will auto-scan first (registers new drives automatically).",
                    wrap=600,
                    color=(180, 180, 180)
                )
                dpg.add_spacer(height=5)

                dpg.add_text("Folder Path (optional - uses selected drive if empty):")
                with dpg.group(horizontal=True):
                    dpg.add_input_text(
                        tag=self.TAG_SUMMARIZE_FOLDER,
                        width=450,
                        hint="Leave empty to use selected drive, or enter specific path"
                    )
                    btn = dpg.add_button(
                        label="Browse...",
                        tag=self.TAG_BTN_SUMMARIZE_BROWSE,
                        callback=self._on_summarize_browse_click
                    )
                    add_tooltip(
                        btn,
                        "Browse for folder to summarize\n"
                        "If not scanned, will auto-scan before summarization"
                    )

                dpg.add_spacer(height=5)

                with dpg.group(horizontal=True):
                    dpg.add_text("Provider:")
                    dpg.add_combo(
                        tag=self.TAG_SUMMARIZE_PROVIDER,
                        items=["lmstudio", "local", "openai", "anthropic", "google"],
                        default_value="lmstudio",
                        width=150
                    )
                    add_tooltip(dpg.last_item(), "LLM provider (LMStudio=local, local=Ollama, others=cloud)")

                    dpg.add_text("  Model (optional):")
                    dpg.add_input_text(
                        tag=self.TAG_SUMMARIZE_MODEL,
                        width=200,
                        hint="Leave empty for default"
                    )

                dpg.add_spacer(height=5)

                with dpg.group(horizontal=True):
                    dpg.add_text("File Types:")
                    dpg.add_input_text(
                        tag=self.TAG_SUMMARIZE_FILE_TYPES,
                        width=200,
                        hint=".jpg,.png,.pdf (or leave empty for all)"
                    )
                    add_tooltip(dpg.last_item(), "Comma-separated file extensions to process")

                    dpg.add_text("  Limit:")
                    dpg.add_input_text(
                        tag=self.TAG_SUMMARIZE_LIMIT,
                        width=80,
                        default_value="500"
                    )
                    add_tooltip(dpg.last_item(), "Maximum number of files to process")

                dpg.add_spacer(height=5)

                # Batch mode checkbox
                cb = dpg.add_checkbox(
                    label="Enable intelligent batch processing (groups by file type, detects model)",
                    tag=self.TAG_SUMMARIZE_BATCH_MODE,
                    default_value=True
                )
                add_tooltip(
                    cb,
                    "When enabled, groups files by type and processes them in batches.\n"
                    "Requires LMStudioMonitorService for automatic model detection.\n"
                    "If disabled, processes files one-by-one in directory order."
                )

                dpg.add_spacer(height=5)

                # Model status text (shows current loaded model if LMStudio)
                dpg.add_text("", tag=self.TAG_SUMMARIZE_MODEL_STATUS, color=(180, 180, 180))

                dpg.add_spacer(height=10)

                btn = dpg.add_button(
                    label="Generate Summaries",
                    tag=self.TAG_BTN_SUMMARIZE,
                    callback=self._on_summarize_click
                )
                add_tooltip(btn, "Start generating AI summaries for files in the folder")

                dpg.add_spacer(height=10)

                # Progress section (initially hidden)
                with dpg.group(tag=self.TAG_SUMMARIZE_PROGRESS, show=False):
                    dpg.add_text("Summarization Progress:", color=get_accent_color())
                    dpg.add_spacer(height=5)
                    dpg.add_text("", tag=self.TAG_SUMMARIZE_PROGRESS_TEXT)
                    dpg.add_progress_bar(tag=self.TAG_SUMMARIZE_PROGRESS_BAR, default_value=0.0, width=-1)

            with dpg.collapsing_header(
                label="Watch Folders",
                default_open=False,
                tag=self.TAG_WATCH_HEADER,
            ):
                dpg.add_text(
                    "Monitor folders for new files. When detected, auto-scan, hash, and optionally organize.",
                    wrap=600,
                )
                dpg.add_spacer(height=5)

                with dpg.group(horizontal=True):
                    cb = dpg.add_checkbox(
                        label="Enable folder watching",
                        tag=self.TAG_WATCH_ENABLED,
                        default_value=self.config.watch.global_enabled,
                        callback=self._on_watch_enabled_toggle,
                    )
                    add_tooltip(cb, "Master toggle for all watch folders")
                    dpg.add_spacer(width=15)
                    btn = dpg.add_button(
                        label="Add Watch Folder",
                        tag=self.TAG_BTN_WATCH_ADD,
                        callback=self._on_watch_add_click,
                    )
                    add_tooltip(btn, "Add a new folder to monitor for incoming files")
                    btn = dpg.add_button(
                        label="Start Watcher",
                        tag=self.TAG_BTN_WATCH_START,
                        callback=self._on_watch_start_stop_click,
                    )
                    add_tooltip(btn, "Start or stop the folder watcher")

                dpg.add_spacer(height=5)
                dpg.add_text("Not running", tag=self.TAG_WATCH_STATUS, color=(180, 180, 180))

                dpg.add_spacer(height=5)
                with dpg.child_window(height=160, border=True):
                    with dpg.table(
                        tag=self.TAG_WATCH_TABLE,
                        header_row=True,
                        borders_innerH=True,
                        borders_outerH=True,
                        borders_innerV=True,
                        borders_outerV=True,
                        resizable=True,
                        policy=dpg.mvTable_SizingStretchProp,
                        row_background=True,
                        scrollY=True,
                        height=130,
                    ):
                        dpg.add_table_column(label="Path", init_width_or_weight=250)
                        dpg.add_table_column(label="Poll (s)", init_width_or_weight=60)
                        dpg.add_table_column(label="Auto-Scan", init_width_or_weight=60)
                        dpg.add_table_column(label="Auto-Org", init_width_or_weight=60)
                        dpg.add_table_column(label="Enabled", init_width_or_weight=50)
                        dpg.add_table_column(label="Action", width_fixed=True, init_width_or_weight=70)

                self._refresh_watch_table()

            with dpg.collapsing_header(
                label="Advanced / Maintenance",
                default_open=False,
                tag=self.TAG_ADVANCED_HEADER,
            ):
                cb = dpg.add_checkbox(
                    label="Force rehash",
                    tag=self.TAG_HASH_FORCE,
                    default_value=False,
                )
                add_tooltip(cb, DRIVE_TOOLTIPS["force_rehash"])
                btn = dpg.add_button(
                    label="Reset Deleted Flags",
                    tag=self.TAG_BTN_RESET,
                    callback=self._on_reset_deleted_click,
                )
                add_tooltip(btn, DRIVE_TOOLTIPS["reset_deleted"])

            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_text("Registered Drives", color=get_accent_color())
                btn = dpg.add_button(label="Refresh", tag=self.TAG_BTN_REFRESH, callback=self._refresh_drive_list)
                add_tooltip(btn, DRIVE_TOOLTIPS["refresh"])
                dpg.add_text("Select one drive for actions.")

            # Drive list table
            with dpg.table(
                tag=self.TAG_DRIVE_LIST,
                header_row=True,
                borders_innerH=True,
                borders_outerH=True,
                borders_innerV=True,
                borders_outerV=True,
                resizable=True,
                policy=dpg.mvTable_SizingStretchProp,
                row_background=True,
                scrollY=True,
                height=300,
            ):
                dpg.add_table_column(label="Select", width_fixed=True, init_width_or_weight=40)
                dpg.add_table_column(label="Name", init_width_or_weight=150)
                dpg.add_table_column(label="Path", init_width_or_weight=250)
                dpg.add_table_column(label="Status", init_width_or_weight=100)
                dpg.add_table_column(label="Files", init_width_or_weight=80)
                dpg.add_table_column(label="Used Space", init_width_or_weight=100)
                dpg.add_table_column(label="Free Space", init_width_or_weight=100)
                dpg.add_table_column(label="Last Scan", init_width_or_weight=120)

            dpg.add_spacer(height=10)

            # Scan progress section (initially hidden)
            with dpg.group(tag=self.TAG_SCAN_PROGRESS, show=False):
                dpg.add_separator()
                dpg.add_text("Scan Progress", color=get_accent_color())
                dpg.add_spacer(height=5)

                with dpg.group(horizontal=True):
                    dpg.add_text("Status:", tag=self.TAG_PROGRESS_TEXT)

                dpg.add_progress_bar(tag=self.TAG_PROGRESS_BAR, default_value=0.0, width=-1)

                dpg.add_text("Current: ", tag=self.TAG_CURRENT_FILE)

                dpg.add_spacer(height=5)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Pause", callback=self._on_pause_click, tag="scan_pause_btn")
                    dpg.add_button(label="Cancel", callback=self._on_cancel_click, tag="scan_cancel_btn")

            dpg.add_spacer(height=10)

            # Drive details section
            dpg.add_separator()
            dpg.add_text("Drive Details", color=get_accent_color())
            dpg.add_spacer(height=5)

            with dpg.group(tag="drive_details"):
                dpg.add_text("Select a drive to view details.")

            dpg.add_spacer(height=10)

            with dpg.collapsing_header(
                label="Corrupt Files & Recovery",
                default_open=False,
                tag=self.TAG_CORRUPT_HEADER,
            ):
                dpg.add_text(
                    "Scan for corrupt images and attempt automated recovery using progressive strategies.",
                    wrap=600,
                )
                dpg.add_spacer(height=5)

                with dpg.group(horizontal=True):
                    btn = dpg.add_button(
                        label="Check for Corrupt Files",
                        tag=self.TAG_BTN_CHECK_CORRUPT,
                        callback=self._on_check_corruption_click,
                    )
                    add_tooltip(
                        btn,
                        "Scan image files on the selected drive for corruption.\n"
                        "Checks JPEG markers, truncation, and image integrity.",
                    )
                    btn = dpg.add_button(
                        label="Recover All",
                        tag=self.TAG_BTN_RECOVER_ALL,
                        callback=self._on_recover_all_click,
                        enabled=False,
                    )
                    add_tooltip(
                        btn,
                        "Attempt automated recovery on all corrupt files.\n"
                        "Uses 6 progressive strategies from least to most aggressive.",
                    )

                dpg.add_spacer(height=5)
                dpg.add_text("No corruption scan results yet.", tag=self.TAG_CORRUPT_COUNT)

                # Corruption scan progress (hidden)
                with dpg.group(tag=self.TAG_CORRUPT_PROGRESS, show=False):
                    dpg.add_text("", tag=self.TAG_CORRUPT_PROGRESS_TEXT)
                    dpg.add_progress_bar(tag=self.TAG_CORRUPT_PROGRESS_BAR, default_value=0.0, width=-1)

                # Recovery progress (hidden)
                with dpg.group(tag=self.TAG_RECOVERY_PROGRESS, show=False):
                    dpg.add_text("", tag=self.TAG_RECOVERY_PROGRESS_TEXT)
                    dpg.add_progress_bar(tag=self.TAG_RECOVERY_PROGRESS_BAR, default_value=0.0, width=-1)

                dpg.add_spacer(height=5)

                # Corrupt files table
                with dpg.child_window(height=220, border=True):
                    with dpg.table(
                        tag=self.TAG_CORRUPT_TABLE,
                        header_row=True,
                        borders_innerH=True,
                        borders_outerH=True,
                        borders_innerV=True,
                        borders_outerV=True,
                        resizable=True,
                        policy=dpg.mvTable_SizingStretchProp,
                        row_background=True,
                        scrollY=True,
                        height=190,
                    ):
                        dpg.add_table_column(label="Filename", init_width_or_weight=180)
                        dpg.add_table_column(label="Type", init_width_or_weight=100)
                        dpg.add_table_column(label="Severity", init_width_or_weight=70)
                        dpg.add_table_column(label="Size", init_width_or_weight=70)
                        dpg.add_table_column(label="Action", width_fixed=True, init_width_or_weight=160)

            with dpg.collapsing_header(
                label="Redundancy & Backups",
                default_open=False,
                tag=self.TAG_BACKUP_HEADER,
            ):
                with dpg.group(horizontal=True):
                    btn = dpg.add_button(
                        label="Generate Redundancy Report",
                        tag=self.TAG_BTN_REDUNDANCY,
                        callback=self._on_generate_redundancy,
                    )
                    add_tooltip(btn, DRIVE_TOOLTIPS["generate_redundancy"])
                    dpg.add_spacer(width=10)
                    btn = dpg.add_button(
                        label="Build Backup Plan",
                        tag=self.TAG_BTN_BACKUP_BUILD,
                        callback=self._on_build_backup_plan,
                    )
                    add_tooltip(btn, DRIVE_TOOLTIPS["build_backup_plan"])
                    btn = dpg.add_button(
                        label="Execute Backup Plan",
                        tag=self.TAG_BTN_BACKUP_EXECUTE,
                        callback=self._on_execute_backup_plan,
                    )
                    add_tooltip(btn, DRIVE_TOOLTIPS["execute_backup_plan"])
                    btn = dpg.add_button(
                        label="Export Plan",
                        tag=self.TAG_BACKUP_EXPORT_BUTTON,
                        callback=self._on_export_backup_plan,
                    )
                    add_tooltip(btn, DRIVE_TOOLTIPS["export_plan"])
                    btn = dpg.add_button(
                        label="Open Targets",
                        tag=self.TAG_BACKUP_OPEN_TARGET_BUTTON,
                        callback=self._on_open_backup_target,
                    )
                    add_tooltip(btn, DRIVE_TOOLTIPS["open_targets"])
                    dpg.add_spacer(width=20)
                    dpg.add_button(
                        label="Export Redundancy Report",
                        callback=self._on_export_redundancy,
                    )

                dpg.add_spacer(height=5)
                with dpg.group(horizontal=True):
                    dpg.add_text("Backup source:")
                    inp = dpg.add_input_text(
                        tag=self.TAG_BACKUP_SOURCE,
                        width=360,
                        default_value=self.config.backup.source_path,
                        hint="Folder to back up..."
                    )
                    add_tooltip(inp, DRIVE_TOOLTIPS["backup_source"])
                    dpg.add_button(label="Browse...", callback=self._on_backup_source_browse)

                dpg.add_spacer(height=5)
                lbl = dpg.add_text("Backup targets:")
                add_tooltip(lbl, DRIVE_TOOLTIPS["backup_targets"])
                with (
                    dpg.child_window(height=80, border=True),
                    dpg.group(tag=self.TAG_BACKUP_TARGETS_GROUP),
                ):
                    dpg.add_text("No drives registered.")

                dpg.add_spacer(height=5)
                dpg.add_text("Exclude patterns (one per line):")
                inp = dpg.add_input_text(
                    tag=self.TAG_BACKUP_EXCLUDES,
                    multiline=True,
                    width=-1,
                    height=70,
                    default_value="\n".join(self.config.backup.exclude_patterns),
                )
                add_tooltip(inp, DRIVE_TOOLTIPS["exclude_patterns"])
                btn = dpg.add_button(
                    label="Analyze Exclusions",
                    tag=self.TAG_BTN_BACKUP_ANALYZE,
                    callback=self._on_analyze_exclusions,
                )
                add_tooltip(btn, DRIVE_TOOLTIPS["analyze_exclusions"])
                dpg.add_spacer(height=5)
                dpg.add_text("Detected project types:")
                dpg.add_input_text(
                    tag=self.TAG_PROJECT_DETECTIONS,
                    multiline=True,
                    width=-1,
                    height=50,
                    readonly=True,
                    default_value="",
                )
                dpg.add_text("Suggested excludes (not auto-applied):")
                dpg.add_input_text(
                    tag=self.TAG_PROJECT_SUGGESTIONS,
                    multiline=True,
                    width=-1,
                    height=60,
                    readonly=True,
                    default_value="",
                )

                dpg.add_spacer(height=5)
                lbl = dpg.add_text("No redundancy report yet.", tag=self.TAG_REDUNDANCY_SUMMARY)
                add_tooltip(lbl, DRIVE_TOOLTIPS["at_risk_table"])

                with dpg.child_window(height=180, border=True), dpg.table(
                    tag=self.TAG_AT_RISK_TABLE,
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
                    dpg.add_table_column(label="File", init_width_or_weight=160)
                    dpg.add_table_column(label="Drive", init_width_or_weight=120)
                    dpg.add_table_column(label="Size", init_width_or_weight=80)
                    dpg.add_table_column(label="Path", init_width_or_weight=260)

                dpg.add_spacer(height=5)
                with dpg.child_window(height=140, border=True), dpg.table(
                    tag=self.TAG_BACKUP_EXCLUDE_TABLE,
                    header_row=True,
                    borders_innerH=True,
                    borders_outerH=True,
                    borders_innerV=True,
                    borders_outerV=True,
                    resizable=True,
                    policy=dpg.mvTable_SizingStretchProp,
                    row_background=True,
                    scrollY=True,
                    height=110,
                ):
                    dpg.add_table_column(label="Pattern", init_width_or_weight=240)
                    dpg.add_table_column(label="Files", init_width_or_weight=80)
                    dpg.add_table_column(label="Size", init_width_or_weight=100)

                dpg.add_spacer(height=5)
                with dpg.child_window(height=160, border=True), dpg.table(
                    tag=self.TAG_BACKUP_PLAN_TABLE,
                    header_row=True,
                    borders_innerH=True,
                    borders_outerH=True,
                    borders_innerV=True,
                    borders_outerV=True,
                    resizable=True,
                    policy=dpg.mvTable_SizingStretchProp,
                    row_background=True,
                    scrollY=True,
                    height=130,
                ):
                    dpg.add_table_column(label="Source", init_width_or_weight=160)
                    dpg.add_table_column(label="Target", init_width_or_weight=260)
                    dpg.add_table_column(label="Size", init_width_or_weight=80)

                dpg.add_spacer(height=5)
                with dpg.group(tag=self.TAG_BACKUP_PROGRESS_GROUP, show=False):
                    dpg.add_text("Backup Progress", color=get_accent_color())
                    dpg.add_text("Status: Idle", tag=self.TAG_BACKUP_PROGRESS_TEXT)
                    dpg.add_progress_bar(tag=self.TAG_BACKUP_PROGRESS_BAR, default_value=0.0, width=-1)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Pause", tag=self.TAG_BACKUP_PAUSE_BUTTON, callback=self._on_backup_pause)
                        dpg.add_button(label="Cancel", tag=self.TAG_BACKUP_CANCEL_BUTTON, callback=self._on_backup_cancel)

            with dpg.collapsing_header(
                label="Storage Analytics",
                default_open=False,
                tag="analytics_header",
            ):
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Compute Analytics",
                        tag="analytics_compute_btn",
                        callback=self._on_compute_analytics,
                    )
                    dpg.add_button(
                        label="Export Analytics",
                        tag="analytics_export_btn",
                        callback=self._on_export_analytics,
                    )

                dpg.add_spacer(height=5)

                # Summary cards
                with dpg.group(horizontal=True, tag="analytics_summary"):
                    with dpg.child_window(width=200, height=60, border=True, tag="analytics_card_files"):
                        dpg.add_text("Total Files", color=get_accent_color())
                        dpg.add_text("--", tag="analytics_total_files")
                    with dpg.child_window(width=200, height=60, border=True, tag="analytics_card_size"):
                        dpg.add_text("Total Size", color=get_accent_color())
                        dpg.add_text("--", tag="analytics_total_size")
                    with dpg.child_window(width=200, height=60, border=True, tag="analytics_card_waste"):
                        dpg.add_text("Duplicate Waste", color=get_accent_color())
                        dpg.add_text("--", tag="analytics_dup_waste")
                    with dpg.child_window(width=200, height=60, border=True, tag="analytics_card_risk"):
                        dpg.add_text("At-Risk Data", color=get_accent_color())
                        dpg.add_text("--", tag="analytics_at_risk")

                dpg.add_spacer(height=10)

                # File type breakdown chart
                with dpg.plot(
                    label="Storage by File Type",
                    height=200,
                    width=-1,
                    tag="analytics_type_plot",
                    no_mouse_pos=True,
                ):
                    dpg.add_plot_legend()
                    dpg.add_plot_axis(dpg.mvXAxis, label="", tag="analytics_type_x",
                                     no_tick_labels=True)
                    dpg.add_plot_axis(dpg.mvYAxis, label="Size (GB)", tag="analytics_type_y")

                dpg.add_spacer(height=10)

                # Year breakdown chart
                with dpg.plot(
                    label="Storage by Year",
                    height=200,
                    width=-1,
                    tag="analytics_year_plot",
                    no_mouse_pos=True,
                ):
                    dpg.add_plot_legend()
                    dpg.add_plot_axis(dpg.mvXAxis, label="Year", tag="analytics_year_x")
                    dpg.add_plot_axis(dpg.mvYAxis, label="Size (GB)", tag="analytics_year_y")

                dpg.add_spacer(height=10)

                # Quick wins table
                dpg.add_text("Quick Wins - Recoverable Space", color=get_accent_color())
                with dpg.child_window(height=120, border=True):
                    with dpg.table(
                        tag="analytics_quickwins_table",
                        header_row=True,
                        borders_innerH=True,
                        borders_outerH=True,
                        borders_innerV=True,
                        borders_outerV=True,
                        resizable=True,
                        policy=dpg.mvTable_SizingStretchProp,
                        row_background=True,
                    ):
                        dpg.add_table_column(label="Category", init_width_or_weight=150)
                        dpg.add_table_column(label="Description", init_width_or_weight=300)
                        dpg.add_table_column(label="Files", init_width_or_weight=80)
                        dpg.add_table_column(label="Recoverable", init_width_or_weight=100)

        # Create add drive dialog
        self._create_add_drive_dialog()
        self._create_backup_source_dialog()
        self._create_scan_all_dialog()
        self._create_summarize_folder_dialog()
        self._create_watch_add_dialog()
        self._create_watch_folder_browse_dialog()
        self._update_background_status()

        # Initial refresh (fast, no probing)
        self._refresh_drive_list(probe=False)
        self._refresh_backup_targets()
        self._refresh_resume_button()

    def _create_add_drive_dialog(self) -> None:
        """Create the add drive dialog."""
        with dpg.window(
            tag=self.TAG_ADD_DIALOG,
            label="Add Drive",
            modal=True,
            show=False,
            width=500,
            height=200,
            no_resize=True,
            pos=[100, 100],
        ):
            dpg.add_text("Add a new drive or network share")
            dpg.add_spacer(height=10)

            with dpg.group(horizontal=True):
                dpg.add_text("Path:")
                dpg.add_input_text(tag="add_drive_path", width=350, hint="C:\\Photos or \\\\NAS\\share")

            with dpg.group(horizontal=True):
                dpg.add_text("Name:")
                dpg.add_input_text(tag="add_drive_label", width=350, hint="My Photos Drive")

            dpg.add_spacer(height=20)

            with dpg.group(horizontal=True):
                dpg.add_button(label="Add", callback=self._on_add_drive_confirm, width=100)
                dpg.add_button(label="Cancel", callback=self._on_add_drive_cancel, width=100)

    def _create_backup_source_dialog(self) -> None:
        """Create folder dialog for backup source selection."""
        with dpg.file_dialog(
            tag="backup_source_dialog",
            show=False,
            modal=True,
            width=700,
            height=400,
            directory_selector=True,
            callback=self._on_backup_source_selected,
        ):
            dpg.add_file_extension(".*", color=(255, 255, 255))

    def _create_scan_all_dialog(self) -> None:
        """Create scan-all dialog."""
        with dpg.window(
            tag=self.TAG_SCAN_ALL_DIALOG,
            label="Scan All Drives",
            modal=True,
            show=False,
            width=420,
            height=200,
            no_resize=True,
            pos=[140, 140],
        ):
            dpg.add_text("Choose scan mode for all registered drives:")
            dpg.add_spacer(height=10)
            dpg.add_combo(
                tag=self.TAG_SCAN_ALL_MODE,
                items=["Quick", "Deep", "Full Analysis"],
                default_value="Quick",
                width=200,
            )
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Start", callback=self._on_scan_all_confirm, width=100)
                dpg.add_button(label="Cancel", callback=lambda: dpg.hide_item(self.TAG_SCAN_ALL_DIALOG), width=100)

    def _create_summarize_folder_dialog(self) -> None:
        """Create the summarize folder browser dialog."""
        with dpg.file_dialog(
            tag=self.TAG_SUMMARIZE_DIALOG,
            directory_selector=True,
            show=False,
            callback=self._on_summarize_folder_selected,
            width=700,
            height=400,
        ):
            dpg.add_file_extension(".*", color=(255, 255, 255, 255))

    def _set_section_visibility(self, has_drives: bool) -> None:
        """Toggle visibility for empty state and advanced sections."""
        if dpg.does_item_exist(self.TAG_GETTING_STARTED):
            dpg.configure_item(self.TAG_GETTING_STARTED, show=not has_drives)
        for tag in (self.TAG_ANALYSIS_HEADER, self.TAG_SUMMARIZE_HEADER, self.TAG_WATCH_HEADER, self.TAG_ADVANCED_HEADER, self.TAG_CORRUPT_HEADER, self.TAG_BACKUP_HEADER):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, show=has_drives)

    def _update_selected_summary(self) -> None:
        """Update selected drive summary text."""
        if not dpg.does_item_exist(self.TAG_SELECTED_SUMMARY):
            return
        if self._selected_drive_id:
            drive = self.drive_manager.get_drive(self._selected_drive_id)
            label = drive.label if drive else "Unknown drive"
            dpg.set_value(self.TAG_SELECTED_SUMMARY, f"Selected drive: {label}")
        else:
            dpg.set_value(self.TAG_SELECTED_SUMMARY, "Selected drive: None")

    def _refresh_action_states(self, has_drives: bool | None = None) -> None:
        """Enable/disable action buttons based on current state."""
        if has_drives is None:
            has_drives = bool(self.drive_manager.get_all_drives())
        scan_active = bool(self._scan_thread and self._scan_thread.is_alive())
        has_selection = bool(self._selected_drive_id)
        enable_selected_actions = has_drives and has_selection and not scan_active
        enable_scan_all = has_drives and not scan_active

        action_states = {
            self.TAG_BTN_REMOVE: enable_selected_actions,
            self.TAG_BTN_QUICK: enable_selected_actions,
            self.TAG_BTN_DEEP: enable_selected_actions,
            self.TAG_BTN_FULL: enable_selected_actions,
            self.TAG_BTN_HASH: enable_selected_actions,
            self.TAG_BTN_SCAN_ALL: enable_scan_all,
            self.TAG_BTN_RESET: enable_selected_actions,
            self.TAG_BTN_REDUNDANCY: has_drives,
            self.TAG_BTN_BACKUP_BUILD: has_drives,
            self.TAG_BTN_BACKUP_EXECUTE: has_drives,
            self.TAG_BTN_BACKUP_ANALYZE: has_drives,
        }
        for tag, enabled in action_states.items():
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=enabled)

    def _refresh_drive_list(self, probe: bool = True) -> None:
        """Refresh the drive list table."""
        # Clear existing rows
        children = dpg.get_item_children(self.TAG_DRIVE_LIST, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)
        self._selection_tags = {}

        # Get all drives
        drives = self.drive_manager.get_all_drives()
        self._drive_label_map = {drive.label: drive.id for drive in drives}

        if not drives:
            self._selected_drive_id = None
            with dpg.table_row(parent=self.TAG_DRIVE_LIST):
                dpg.add_text("")
                dpg.add_text("No drives registered.")
                dpg.add_text("Click 'Add Drive' to register a drive or network share.")
            self._clear_drive_details()
            self._refresh_resume_button()
            self._set_section_visibility(False)
            self._update_selected_summary()
            self._refresh_action_states(False)
            return

        # Add rows for each drive
        for drive in drives:
            status = None
            status_label = "Checking"
            status_color = (160, 160, 160)
            if probe:
                status = self.drive_manager.get_drive_status(drive.id)
            else:
                status = self.drive_manager._status_cache.get(drive.id)
            if status is not None:
                status_label = status.value.title()
                status_colors = {
                    DriveStatus.CONNECTED: (100, 200, 100),
                    DriveStatus.DISCONNECTED: (200, 100, 100),
                    DriveStatus.SCANNING: (100, 150, 255),
                    DriveStatus.ERROR: (255, 100, 100),
                    DriveStatus.NEEDS_SCAN: (200, 200, 100),
                }
                status_color = status_colors.get(status, (200, 200, 200))

            space = None
            if probe and status == DriveStatus.CONNECTED:
                space = self.drive_manager.get_space_info(drive.path)
            elif not probe and drive.total_space and drive.free_space:
                used_bytes = max(drive.total_space - drive.free_space, 0)
                space = DriveInfo(
                    drive=drive,
                    status=status or DriveStatus.NEEDS_SCAN,
                    is_network=drive.is_network,
                )
                # Attach lightweight fields for display
                space.total_bytes = drive.total_space
                space.free_bytes = drive.free_space
                space.used_bytes = used_bytes

            with dpg.table_row(parent=self.TAG_DRIVE_LIST):
                # Selection checkbox
                select_tag = f"drive_select_{drive.id}"
                self._selection_tags[drive.id] = select_tag
                dpg.add_checkbox(
                    tag=select_tag,
                    callback=self._on_drive_selection_changed,
                    user_data=drive.id,
                    default_value=(drive.id == self._selected_drive_id)
                )

                # Name
                dpg.add_text(drive.label)

                # Path
                dpg.add_text(drive.path)

                # Status with color
                dpg.add_text(status_label, color=status_color)

                # Files
                dpg.add_text(f"{drive.file_count:,}" if drive.file_count else "-")

                # Used space
                if space:
                    used_gb = space.used_bytes / (1024 ** 3)
                    dpg.add_text(f"{used_gb:.1f} GB")
                else:
                    dpg.add_text("-")

                # Free space
                if space:
                    free_gb = space.free_bytes / (1024 ** 3)
                    dpg.add_text(f"{free_gb:.1f} GB")
                else:
                    dpg.add_text("-")

                # Last scan
                if drive.last_scan:
                    dpg.add_text(drive.last_scan.strftime("%Y-%m-%d %H:%M"))
                else:
                    dpg.add_text("Never")

        self._refresh_backup_targets()
        self._set_section_visibility(True)
        self._update_selected_summary()
        self._refresh_action_states(True)

    def on_frame(self) -> None:
        """Run deferred startup actions on the main thread."""
        now = time.time()
        if self._pending_full_refresh and now >= self._full_refresh_after:
            self._pending_full_refresh = False
            self._refresh_drive_list(probe=True)
        if self._pending_monitor_start and now >= self._monitor_start_after:
            self._pending_monitor_start = False
            self.drive_manager.start_monitoring()

    def _on_drive_selection_changed(self, sender, app_data, user_data) -> None:
        """Handle single-drive selection changes."""
        if self._suppress_selection_events:
            return

        drive_id = str(user_data)
        is_checked = bool(app_data)

        if not is_checked:
            if drive_id == self._selected_drive_id:
                self._selected_drive_id = None
                self._clear_drive_details()
                self._refresh_resume_button()
                self._update_selected_summary()
                self._refresh_action_states()
            return

        self._selected_drive_id = drive_id
        self._update_drive_details(drive_id)
        self._refresh_resume_button()
        self._update_selected_summary()
        self._refresh_action_states()
        self._refresh_corrupt_table(drive_id)

        # Ensure only one checkbox is active
        self._suppress_selection_events = True
        try:
            for other_id, tag in self._selection_tags.items():
                if other_id != drive_id and dpg.does_item_exist(tag):
                    dpg.set_value(tag, False)
        finally:
            self._suppress_selection_events = False

    def _clear_drive_details(self) -> None:
        """Clear the drive details section."""
        children = dpg.get_item_children("drive_details", slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)
        dpg.add_text("Select a drive to view details.", parent="drive_details")

    def _update_drive_details(self, drive_id: str) -> None:
        """Update the drive details section."""
        # Clear existing details
        children = dpg.get_item_children("drive_details", slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        drive_info = self.drive_manager.get_drive_info(drive_id)
        if not drive_info:
            dpg.add_text("Drive not found.", parent="drive_details")
            return

        drive = drive_info.drive

        dpg.add_text(f"Name: {drive.label}", parent="drive_details")
        dpg.add_text(f"Path: {drive.path}", parent="drive_details")
        dpg.add_text(f"Status: {drive_info.status.value.title()}", parent="drive_details")

        if drive_info.status == DriveStatus.DISCONNECTED:
            btn = dpg.add_button(
                label="Remap Path...",
                callback=lambda: self._on_remap_drive_click(),
                parent="drive_details",
            )
            add_tooltip(btn, DRIVE_TOOLTIPS["remap_drive"])

        if drive_info.is_network:
            dpg.add_text("Type: Network Share", parent="drive_details")
            if drive_info.server:
                dpg.add_text(f"Server: {drive_info.server}", parent="drive_details")
        else:
            dpg.add_text("Type: Local Drive", parent="drive_details")
            if drive_info.volume_label:
                dpg.add_text(f"Volume: {drive_info.volume_label}", parent="drive_details")
            if drive_info.filesystem:
                dpg.add_text(f"Filesystem: {drive_info.filesystem}", parent="drive_details")

        dpg.add_text(f"Files: {drive.file_count:,}", parent="drive_details")

        if drive.last_scan:
            dpg.add_text(f"Last Scan: {drive.last_scan.strftime('%Y-%m-%d %H:%M:%S')}", parent="drive_details")

        # Show corrupt file count if any
        corrupt_files = self.drive_manager.db.get_corrupt_files(drive_id=drive_id)
        if corrupt_files:
            dpg.add_text(
                f"Corrupt Files: {len(corrupt_files)}",
                parent="drive_details",
                color=(255, 180, 60),
            )

    def _on_add_drive_click(self) -> None:
        """Handle add drive button click."""
        dpg.set_value("add_drive_path", "")
        dpg.set_value("add_drive_label", "")
        dpg.show_item(self.TAG_ADD_DIALOG)

    def _on_add_drive_confirm(self) -> None:
        """Handle add drive confirmation."""
        path = dpg.get_value("add_drive_path")
        label = dpg.get_value("add_drive_label")

        if not path:
            self._show_error_dialog("Add Drive", "No path provided.")
            return

        if not label:
            # Generate label from path
            label = path.split('\\')[-1] or path.split('/')[-1] or "Drive"

        try:
            drive = self.drive_manager.add_drive(path, label)
            logger.info(f"Added drive: {drive.label}")
            dpg.hide_item(self.TAG_ADD_DIALOG)
            self._refresh_drive_list()
        except ValueError as e:
            logger.error(f"Failed to add drive: {e}")
            self._show_error_dialog("Add Drive", str(e))

    def _on_add_drive_cancel(self) -> None:
        """Handle add drive cancel."""
        dpg.hide_item(self.TAG_ADD_DIALOG)

    def _on_remove_drive_click(self) -> None:
        """Handle remove drive button click."""
        if not self._selected_drive_id:
            self._show_error_dialog("Remove Drive", "Select a drive to remove.")
            return

        drive = self.drive_manager.get_drive(self._selected_drive_id)
        if not drive:
            self._show_error_dialog("Remove Drive", "Drive not found.")
            return
        self._confirm_remove_drive(drive.label)

    def _on_reset_deleted_click(self) -> None:
        """Reset deleted flags for selected drive."""
        if not self._selected_drive_id:
            self._show_error_dialog("Reset Deleted Flags", "Select a drive first.")
            return
        drive = self.drive_manager.get_drive(self._selected_drive_id)
        if not drive:
            self._show_error_dialog("Reset Deleted Flags", "Drive not found.")
            return
        def do_reset():
            updated = self.drive_manager.db.reset_deleted_flags(drive.id, touch_scan_date=True)
            if self.on_status_update:
                self.on_status_update(f"Reset deleted flags for {drive.label}: {updated} files.")
            self._refresh_drive_list()

        self._confirm_reset_deleted_flags(drive.label, do_reset)

    def _confirm_reset_deleted_flags(self, drive_label: str, on_confirm) -> None:
        """Show confirmation dialog for resetting deleted flags."""
        tag = "confirm_reset_deleted_flags"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        def confirm(_sender=None, _app_data=None, _user_data=None):
            dpg.configure_item(tag, show=False)
            if callable(on_confirm):
                on_confirm()

        def cancel(_sender=None, _app_data=None, _user_data=None):
            dpg.configure_item(tag, show=False)

        with dpg.window(
            label="Confirm Reset",
            tag=tag,
            modal=True,
            show=True,
            width=420,
            height=170,
            no_resize=True,
            pos=[300, 200],
        ):
            dpg.add_text(f"Reset deleted flags for '{drive_label}'?")
            dpg.add_text("This will mark all files on this drive as not deleted.")
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Reset", callback=confirm)
                dpg.add_button(label="Cancel", callback=cancel)

    def _on_scan_click(self, mode: ScanMode) -> None:
        """Handle scan button click."""
        if not self._selected_drive_id:
            self._show_error_dialog("Scan", "Select a drive first.")
            return

        if self._scan_thread and self._scan_thread.is_alive():
            self._show_error_dialog("Scan", "A scan is already in progress.")
            return

        drive = self.drive_manager.get_drive(self._selected_drive_id)
        if not drive:
            self._show_error_dialog("Scan", "Drive not found.")
            return

        self._sync_analysis_settings_from_ui()

        if mode == ScanMode.FULL and not self.config.ai.analysis_scan_before_full:
            self._start_analysis_only(drive.id)
            return

        self.drive_manager.db.clear_scan_state(drive.id)
        self._resume_state = None
        self._start_scan(drive, mode, resume_state=None)

    def _on_scan_all_click(self) -> None:
        """Show scan-all dialog."""
        if self._scan_thread and self._scan_thread.is_alive():
            self._show_error_dialog("Scan All", "A scan is already in progress.")
            return
        dpg.show_item(self.TAG_SCAN_ALL_DIALOG)

    def _on_scan_all_confirm(self) -> None:
        """Start scan-all with selected mode."""
        mode_value = dpg.get_value(self.TAG_SCAN_ALL_MODE)
        mode = ScanMode.QUICK
        if mode_value == "Deep":
            mode = ScanMode.DEEP
        elif mode_value == "Full Analysis":
            mode = ScanMode.FULL
        dpg.hide_item(self.TAG_SCAN_ALL_DIALOG)
        self._start_scan_all(mode)

    def _start_scan_all(self, mode: ScanMode) -> None:
        """Queue scans for all drives."""
        drives = self.drive_manager.get_all_drives()
        if not drives:
            self._show_error_dialog("Scan All", "No drives registered.")
            return
        if self._scan_thread and self._scan_thread.is_alive():
            self._show_error_dialog("Scan All", "A scan is already in progress.")
            return

        with self._queue_lock:
            self._scan_all_queue = [drive.id for drive in drives]
            self._scan_all_mode = mode
            self._scan_all_active = True
        self._scan_next_in_queue()

    def _scan_next_in_queue(self) -> None:
        """Start the next queued scan if any."""
        with self._queue_lock:
            if not self._scan_all_active:
                return
            if self._scan_thread and self._scan_thread.is_alive():
                return
            if not self._scan_all_queue:
                self._scan_all_active = False
                if self.on_status_update:
                    self.on_status_update("Scan all complete.")
                return

            drive_id = self._scan_all_queue.pop(0)
            current_mode = self._scan_all_mode

        drive = self.drive_manager.get_drive(drive_id)
        if not drive:
            self._scan_next_in_queue()
            return

        self._set_selected_drive(drive_id)
        self._sync_analysis_settings_from_ui()

        if current_mode == ScanMode.FULL and not self.config.ai.analysis_scan_before_full:
            self._start_analysis_only_for_queue(drive_id)
            return

        self.drive_manager.db.clear_scan_state(drive.id)
        self._resume_state = None
        self._start_scan(drive, current_mode or ScanMode.QUICK, resume_state=None)

    def _start_analysis_only_for_queue(self, drive_id: str) -> None:
        """Run analysis-only in queue sequence."""
        if self._analysis_thread and self._analysis_thread.is_alive():
            return

        def run_and_continue():
            try:
                self._run_analysis(drive_id)
            finally:
                self._scan_next_in_queue()

        self._analysis_thread = threading.Thread(target=run_and_continue, daemon=True)
        self._analysis_thread.start()

    def _on_hash_click(self) -> None:
        """Run hashing for selected drive."""
        if not self._selected_drive_id:
            self._show_error_dialog("Generate Hashes", "Select a drive first.")
            return
        if self._scan_thread and self._scan_thread.is_alive():
            self._show_error_dialog("Generate Hashes", "A scan is already in progress.")
            return

        drive = self.drive_manager.get_drive(self._selected_drive_id)
        if not drive:
            self._show_error_dialog("Generate Hashes", "Drive not found.")
            return

        force = dpg.get_value(self.TAG_HASH_FORCE)
        threading.Thread(
            target=self._run_hash,
            args=(drive.id, force),
            daemon=True,
        ).start()
        dpg.show_item(self.TAG_SCAN_PROGRESS)
        dpg.set_value(self.TAG_PROGRESS_TEXT, "Status: Hashing...")
        dpg.set_value(self.TAG_PROGRESS_BAR, 0.0)
        if self.on_status_update:
            self.on_status_update("Hashing started...")

    def _on_resume_scan_click(self) -> None:
        """Handle resume scan click."""
        if not self._selected_drive_id:
            self._show_error_dialog("Resume Scan", "Select a drive first.")
            return

        if self._scan_thread and self._scan_thread.is_alive():
            self._show_error_dialog("Resume Scan", "A scan is already in progress.")
            return

        drive = self.drive_manager.get_drive(self._selected_drive_id)
        if not drive:
            self._show_error_dialog("Resume Scan", "Drive not found.")
            return

        resume_state = self.drive_manager.db.get_scan_state(drive.id)
        if not resume_state:
            self._show_error_dialog("Resume Scan", "No saved scan state for this drive.")
            self._refresh_resume_button()
            return

        self._resume_state = resume_state
        try:
            mode_value = resume_state.get("mode")
            mode = ScanMode(mode_value) if mode_value else ScanMode.QUICK
        except ValueError:
            mode = ScanMode.QUICK

        self._start_scan(drive, mode, resume_state=resume_state)

    def _start_scan(self, drive: Drive, mode: ScanMode, resume_state: dict | None) -> None:
        """Start a scan (new or resume) in background thread."""
        self._current_scan_drive = drive.id
        self._scan_thread = threading.Thread(
            target=self._run_scan,
            args=(drive, mode, resume_state),
            daemon=True
        )
        self._scan_thread.start()

        dpg.show_item(self.TAG_SCAN_PROGRESS)
        dpg.configure_item("scan_pause_btn", label="Pause")
        self.drive_manager.set_drive_status(drive.id, DriveStatus.SCANNING)
        if self.on_status_update:
            prefix = "Resuming" if resume_state else "Scanning"
            self.on_status_update(f"{prefix} {drive.label} ({mode.value})...")
        self._start_face_worker(drive.id)
        self._start_background_pipeline(drive.id)
        self._refresh_drive_list()

    def _start_analysis_only(self, drive_id: str) -> None:
        """Run analysis without a preceding scan."""
        if self._analysis_thread and self._analysis_thread.is_alive():
            logger.warning("Analysis already running")
            return
        self._analysis_thread = threading.Thread(
            target=self._run_analysis,
            args=(drive_id,),
            daemon=True,
        )
        self._analysis_thread.start()
        if self.on_status_update:
            self.on_status_update("Running analysis...")

    def _parse_extension_list(self, text: str) -> list[str]:
        parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
        normalized = []
        for part in parts:
            ext = part.lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            normalized.append(ext)
        return sorted(set(normalized))

    def _sync_analysis_settings_from_ui(self) -> None:
        """Persist analysis UI settings to config."""
        self.config.ai.analysis_scan_before_full = dpg.get_value(self.TAG_FULL_SCAN_FIRST)
        self.config.ai.analysis_reanalyze_existing = dpg.get_value(self.TAG_FULL_REANALYZE)
        self.config.ai.analysis_include_metadata = dpg.get_value(self.TAG_FULL_METADATA)
        self.config.ai.analysis_include_scenes = dpg.get_value(self.TAG_FULL_SCENES)
        self.config.ai.analysis_include_objects = dpg.get_value(self.TAG_FULL_OBJECTS)
        self.config.ai.analysis_include_ocr = dpg.get_value(self.TAG_FULL_OCR)
        self.config.ai.analysis_include_summaries = dpg.get_value(self.TAG_FULL_SUMMARIES)
        self.config.ai.analysis_include_images = dpg.get_value(self.TAG_FULL_IMAGES)
        self.config.ai.analysis_include_documents = dpg.get_value(self.TAG_FULL_DOCS)
        self.config.ai.analysis_include_data_files = dpg.get_value(self.TAG_FULL_DATA)
        self.config.ai.analysis_doc_extensions = self._parse_extension_list(
            dpg.get_value(self.TAG_FULL_DOC_EXTENSIONS)
        )
        self.config.ai.analysis_data_extensions = self._parse_extension_list(
            dpg.get_value(self.TAG_FULL_DATA_EXTENSIONS)
        )
        self.config.ai.analysis_background_during_scan = dpg.get_value(self.TAG_BG_ANALYSIS)
        self.config.ai.hash_background_during_scan = dpg.get_value(self.TAG_BG_HASH)
        save_config()
    def _build_analysis_options(self, drive_id: str) -> AnalysisOptions:
        return AnalysisOptions(
            include_metadata=dpg.get_value(self.TAG_FULL_METADATA),
            include_scenes=dpg.get_value(self.TAG_FULL_SCENES),
            include_objects=dpg.get_value(self.TAG_FULL_OBJECTS),
            include_ocr=dpg.get_value(self.TAG_FULL_OCR),
            include_summaries=dpg.get_value(self.TAG_FULL_SUMMARIES),
            include_images=dpg.get_value(self.TAG_FULL_IMAGES),
            include_documents=dpg.get_value(self.TAG_FULL_DOCS),
            include_data_files=dpg.get_value(self.TAG_FULL_DATA),
            document_extensions=self._parse_extension_list(dpg.get_value(self.TAG_FULL_DOC_EXTENSIONS)),
            data_extensions=self._parse_extension_list(dpg.get_value(self.TAG_FULL_DATA_EXTENSIONS)),
            reanalyze_existing=dpg.get_value(self.TAG_FULL_REANALYZE),
            drive_id=drive_id,
            batch_limit=self.config.ai.analysis_batch_limit,
        )

    def _run_analysis(self, drive_id: str) -> None:
        """Run metadata and AI analysis for a drive."""
        try:
            runner = AnalysisRunner(
                self.drive_manager.db,
                status_callback=self.on_status_update,
            )
            options = self._build_analysis_options(drive_id)
            stats = runner.run(options)
            if self.on_status_update:
                self.on_status_update(
                    f"Analysis complete: metadata {stats.metadata}, scenes {stats.scenes}, "
                    f"objects {stats.objects}, OCR {stats.ocr}, summaries {stats.summaries}"
                )
        except Exception as exc:
            logger.error(f"Analysis error: {exc}")
            if self.on_status_update:
                self.on_status_update(f"Analysis failed: {exc}")

    def _run_scan(self, drive: Drive, mode: ScanMode, resume_state: dict | None) -> None:
        """Run scan in background thread."""
        scan_state = None
        try:
            # Create scanner with progress callback
            self._scanner = Scanner(progress_callback=self._on_scan_progress)

            # Run scan
            result = self._scanner.scan(drive, mode, resume_state=resume_state)

            if self._scanner.state == ScanState.CANCELLED:
                logger.info("Scan cancelled")
            else:
                logger.info(f"Scan complete: {result.total_files} files, "
                           f"{result.new_files} new, {result.errors} errors")

                # If scan completed, run hashing
                if self._scanner.state == ScanState.COMPLETED:
                    self._run_hash(drive.id)
                    if mode == ScanMode.FULL:
                        self._run_analysis(drive.id)
            scan_state = self._scanner.state

        except Exception as e:
            logger.error(f"Scan error: {e}")
        finally:
            self._scan_thread = None
            self._scanner = None
            self._current_scan_drive = None
            self._resume_state = None
            self._stop_background_pipeline()
            if scan_state == ScanState.COMPLETED:
                self._stop_face_worker(drain=True)
            else:
                self._stop_face_worker(drain=False)

            # Update UI on main thread
            dpg.configure_item(self.TAG_SCAN_PROGRESS, show=False)
            self.drive_manager.set_drive_status(drive.id, DriveStatus.CONNECTED)

            # Refresh on main thread
            self._refresh_drive_list()

            if self.on_scan_complete:
                self.on_scan_complete(drive.id)
            if self.on_status_update:
                self.on_status_update(f"Scan finished for {drive.label}.")
            self._refresh_resume_button()
            if scan_state == ScanState.COMPLETED:
                self._scan_next_in_queue()
            else:
                with self._queue_lock:
                    self._scan_all_queue = []
                    self._scan_all_active = False

    def _start_background_pipeline(self, drive_id: str) -> None:
        """Start background analysis/hash workers during scan."""
        if dpg.get_value(self.TAG_BG_ANALYSIS):
            self._analysis_worker_stop.clear()
            self._analysis_worker_thread = threading.Thread(
                target=self._analysis_worker_loop,
                args=(drive_id,),
                daemon=True,
            )
            self._analysis_worker_thread.start()

        if dpg.get_value(self.TAG_BG_HASH):
            self._hash_worker_stop.clear()
            self._hash_worker_thread = threading.Thread(
                target=self._hash_worker_loop,
                args=(drive_id,),
                daemon=True,
            )
            self._hash_worker_thread.start()
        self._update_background_status()

    def _stop_background_pipeline(self) -> None:
        """Stop background analysis/hash workers."""
        self._analysis_worker_stop.set()
        self._hash_worker_stop.set()
        self._update_background_status()

    def _analysis_worker_loop(self, drive_id: str) -> None:
        """Continuously fill missing analysis while scan runs."""
        while not self._analysis_worker_stop.is_set():
            try:
                options = self._build_analysis_options(drive_id)
                options.reanalyze_existing = False
                runner = AnalysisRunner(
                    self.drive_manager.db,
                    status_callback=self.on_status_update,
                )
                runner.run(options)
            except Exception as exc:
                logger.warning("Background analysis error: %s", exc)
            if self._analysis_worker_stop.wait(timeout=15.0):
                break

    def _hash_worker_loop(self, drive_id: str) -> None:
        """Continuously hash files while scan runs."""
        while not self._hash_worker_stop.is_set():
            if self._hash_worker_stop.wait(timeout=5.0):
                break
            if not self._hash_lock.acquire(blocking=False):
                continue
            try:
                hasher = Hasher(self.drive_manager.db)
                hasher.hash_files(drive_id=drive_id, force_rehash=False)
            except Exception as exc:
                logger.warning("Background hash error: %s", exc)
            finally:
                self._hash_lock.release()
    def _start_face_worker(self, drive_id: str) -> None:
        """Start face analysis worker during scans."""
        if not self.config.ai.process_images:
            return
        if self._face_worker and self._face_worker.is_running():
            if self._face_worker_drive_id == drive_id:
                return
            self._face_worker.stop(wait=False)
        self._face_worker = FaceAnalysisWorker(
            self.drive_manager.db,
            drive_id=drive_id,
            status_callback=self.on_status_update,
        )
        self._face_worker_drive_id = drive_id
        self._face_worker.start()
        if self.on_face_worker_state_change:
            self.on_face_worker_state_change(True)

    def _stop_face_worker(self, drain: bool) -> None:
        """Stop or drain the face analysis worker."""
        if not self._face_worker:
            return
        if drain:
            self._face_worker.request_drain()
        else:
            self._face_worker.stop(wait=False)
        if self.on_face_worker_state_change:
            self.on_face_worker_state_change(False)

    def _run_hash(self, drive_id: str, force_rehash: bool = False) -> None:
        """Run hashing after scan completes."""
        try:
            if not self._hash_lock.acquire(blocking=False):
                logger.warning("Hash already running")
                return
            self._hasher = Hasher(progress_callback=self._on_hash_progress)
            result = self._hasher.hash_files(drive_id, force_rehash=force_rehash)

            logger.info(f"Hashing complete: {result.files_hashed} files, "
                       f"{result.exact_duplicates} duplicates found")

        except Exception as e:
            logger.error(f"Hash error: {e}")
        finally:
            self._hasher = None
            if self._hash_lock.locked():
                self._hash_lock.release()
            if self.on_status_update:
                self.on_status_update("Hashing complete.")
            dpg.configure_item(self.TAG_SCAN_PROGRESS, show=False)

    def _on_scan_progress(self, progress: ScanProgress) -> None:
        """Handle scan progress update."""
        # Update UI (must be called from main thread in real app)
        try:
            if progress.files_found > 0:
                # Estimate progress (rough, since we don't know total)
                # For now just show activity
                dpg.set_value(self.TAG_PROGRESS_BAR, 0.5)  # Indeterminate

            status_text = f"Files: {progress.files_found:,} | "
            status_text += f"Folders: {progress.folders_processed:,} | "
            status_text += f"Speed: {progress.files_per_second:.0f} files/sec | "
            status_text += f"Errors: {progress.errors}"

            dpg.set_value(self.TAG_PROGRESS_TEXT, f"Status: {status_text}")

            # Truncate current path for display
            current = progress.current_path
            if len(current) > 80:
                current = "..." + current[-77:]
            dpg.set_value(self.TAG_CURRENT_FILE, f"Current: {current}")

        except Exception:
            pass  # UI may not be ready

    def _on_hash_progress(self, progress: HashProgress) -> None:
        """Handle hash progress update."""
        try:
            if progress.files_to_hash > 0:
                pct = progress.files_completed / progress.files_to_hash
                dpg.set_value(self.TAG_PROGRESS_BAR, pct)

            status_text = f"Hashing: {progress.files_completed:,}/{progress.files_to_hash:,} | "
            status_text += f"Speed: {progress.bytes_per_second / (1024*1024):.1f} MB/s"

            dpg.set_value(self.TAG_PROGRESS_TEXT, f"Status: {status_text}")

            current = progress.current_file
            if len(current) > 80:
                current = "..." + current[-77:]
            dpg.set_value(self.TAG_CURRENT_FILE, f"Current: {current}")

        except Exception:
            pass

    def _on_pause_click(self) -> None:
        """Handle pause/resume button click."""
        if self._scanner:
            if self._scanner.state == ScanState.SCANNING:
                self._scanner.pause()
                dpg.configure_item("scan_pause_btn", label="Resume")
            elif self._scanner.state == ScanState.PAUSED:
                self._scanner.resume()
                dpg.configure_item("scan_pause_btn", label="Pause")

        if self._hasher:
            if self._hasher.state == HashState.HASHING:
                self._hasher.pause()
                dpg.configure_item("scan_pause_btn", label="Resume")
            elif self._hasher.state == HashState.PAUSED:
                self._hasher.resume()
                dpg.configure_item("scan_pause_btn", label="Pause")

    def _on_cancel_click(self) -> None:
        """Handle cancel button click."""
        if self._scanner:
            self._scanner.cancel()
        if self._hasher:
            self._hasher.cancel()
        with self._queue_lock:
            self._scan_all_queue = []
            self._scan_all_active = False
        self._refresh_resume_button()

    def _refresh_resume_button(self) -> None:
        """Enable resume scan button if a persisted scan state exists.

        Note: This only updates the button state. The actual resume state
        is fetched fresh when the resume button is clicked.
        """
        enabled = False
        if self._selected_drive_id:
            state = self.drive_manager.db.get_scan_state(self._selected_drive_id)
            enabled = bool(state)
        dpg.configure_item(self.TAG_RESUME_SCAN_BUTTON, enabled=enabled)

    def _refresh_backup_targets(self) -> None:
        """Refresh backup target list based on drives."""
        drives = self.drive_manager.get_all_drives()
        children = dpg.get_item_children(self.TAG_BACKUP_TARGETS_GROUP, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        if not drives:
            dpg.add_text("No drives registered.", parent=self.TAG_BACKUP_TARGETS_GROUP)
            return

        for drive in drives:
            checked = drive.id in self.config.backup.target_drive_ids
            dpg.add_checkbox(
                label=f"{drive.label} ({drive.path})",
                tag=f"backup_target_{drive.id}",
                default_value=checked,
                parent=self.TAG_BACKUP_TARGETS_GROUP,
            )

    def _get_selected_targets(self) -> list[str]:
        """Get selected backup target drive IDs."""
        drives = self.drive_manager.get_all_drives()
        selected: list[str] = []
        for drive in drives:
            tag = f"backup_target_{drive.id}"
            try:
                if dpg.get_value(tag):
                    selected.append(drive.id)
            except Exception:
                continue
        return selected

    def _on_generate_redundancy(self) -> None:
        """Generate redundancy report and update UI."""
        if self.on_status_update:
            self.on_status_update("Building redundancy report...")
        report = self.redundancy_checker.build_report(limit=1000)
        self._redundancy_report = report

        if report.total_groups == 0 or report.total_hashed_files == 0:
            summary = "No hashed files found. Use Generate Hashes to build redundancy data."
        else:
            summary = (
                f"Hashed files: {report.total_hashed_files:,} | "
                f"Groups: {report.total_groups:,} | "
                f"At-risk files: {report.at_risk_files:,} | "
                f"At-risk size: {self._format_bytes(report.at_risk_size_bytes)}"
            )
        dpg.set_value(self.TAG_REDUNDANCY_SUMMARY, summary)
        self._populate_at_risk_table(report)
        if self.on_status_update:
            self.on_status_update("Redundancy report ready.")

    def _populate_at_risk_table(self, report: RedundancyReport) -> None:
        """Populate at-risk files table."""
        children = dpg.get_item_children(self.TAG_AT_RISK_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        if report.total_groups == 0 or report.total_hashed_files == 0:
            with dpg.table_row(parent=self.TAG_AT_RISK_TABLE):
                dpg.add_text("No hashed files found. Use Generate Hashes to build a report.")
                dpg.add_text("")
                dpg.add_text("")
                dpg.add_text("")
            return

        if not report.at_risk_groups:
            with dpg.table_row(parent=self.TAG_AT_RISK_TABLE):
                dpg.add_text("No at-risk files found.")
                dpg.add_text("")
                dpg.add_text("")
                dpg.add_text("")
            return

        for group in report.at_risk_groups[:200]:
            for file in group.files[:5]:
                drive = self.drive_manager.get_drive(file.drive_id)
                drive_name = drive.label if drive else file.drive_id
                with dpg.table_row(parent=self.TAG_AT_RISK_TABLE):
                    dpg.add_text(file.filename)
                    dpg.add_text(drive_name)
                    dpg.add_text(self._format_bytes(file.size))
                    dpg.add_text(file.path)

    def _on_build_backup_plan(self) -> None:
        """Build backup plan for at-risk files."""
        source_path = dpg.get_value(self.TAG_BACKUP_SOURCE).strip().strip('"')
        if not source_path:
            self._show_error_dialog("Build Backup Plan", "Choose a backup source folder first.")
            return

        targets = self._get_selected_targets()
        if not targets:
            self._show_error_dialog("Build Backup Plan", "Select at least one backup target.")
            return

        exclude_text = dpg.get_value(self.TAG_BACKUP_EXCLUDES).strip()
        exclude_patterns = [line.strip() for line in exclude_text.splitlines() if line.strip()]

        self.config.backup.source_path = source_path
        self.config.backup.target_drive_ids = targets
        self.config.backup.exclude_patterns = exclude_patterns
        from duplicleaner.utils.config import save_config
        save_config()

        self._backup_plan = self.redundancy_checker.build_backup_plan_for_source(
            source_path=source_path,
            target_drive_ids=targets,
            exclude_patterns=exclude_patterns,
        )
        self._populate_backup_plan_table(self._backup_plan)
        self._update_project_detections(source_path)

    def _on_execute_backup_plan(self) -> None:
        """Execute backup plan using ActionEngine."""
        if not self._backup_plan:
            self._on_build_backup_plan()
            if not self._backup_plan:
                logger.warning("No backup plan to execute")
                return

        if self._backup_thread and self._backup_thread.is_alive():
            logger.warning("Backup already in progress")
            return

        if self._action_engine is None:
            self._action_engine = ActionEngine(self.drive_manager.db, verify_copies=True)
            self._action_engine.set_progress_callback(self._on_backup_progress)

        actions: list[PendingAction] = []
        for item in self._backup_plan:
            actions.append(
                PendingAction(
                    action_type=ActionType.COPY,
                    source_path=item.source_path,
                    dest_path=item.target_path,
                    file_size=item.size,
                    file_hash=item.content_hash,
                )
            )

        self._action_engine.clear_pending()
        self._action_engine.add_pending_batch(actions)

        dpg.configure_item(self.TAG_BACKUP_PROGRESS_GROUP, show=True)
        dpg.set_value(self.TAG_BACKUP_PROGRESS_TEXT, "Status: Preparing...")
        dpg.set_value(self.TAG_BACKUP_PROGRESS_BAR, 0.0)
        dpg.configure_item(self.TAG_BACKUP_PAUSE_BUTTON, enabled=True, label="Pause")
        dpg.configure_item(self.TAG_BACKUP_CANCEL_BUTTON, enabled=True)
        if self.on_status_update:
            self.on_status_update("Executing backup plan...")

        def run_backup():
            try:
                self._action_engine.execute_pending(confirm_delete=False)
            except Exception as e:
                logger.error(f"Backup plan execution failed: {e}")

        self._backup_thread = threading.Thread(target=run_backup, daemon=True)
        self._backup_thread.start()

    def _on_backup_progress(self, progress: OperationProgress) -> None:
        """Update backup progress UI."""
        try:
            pct = progress.completed_files / max(progress.total_files, 1)
            dpg.set_value(self.TAG_BACKUP_PROGRESS_BAR, pct)
            status = (
                f"Status: {progress.phase} | "
                f"{progress.completed_files}/{progress.total_files} files | "
                f"{progress.successful} OK, {progress.failed} failed"
            )
            dpg.set_value(self.TAG_BACKUP_PROGRESS_TEXT, status)

            if progress.phase == "complete":
                summary = (
                    f"Complete: {progress.successful} OK, {progress.failed} failed, "
                    f"{progress.skipped} skipped"
                )
                dpg.set_value(self.TAG_BACKUP_PROGRESS_TEXT, summary)
                dpg.configure_item(self.TAG_BACKUP_PAUSE_BUTTON, enabled=False)
                dpg.configure_item(self.TAG_BACKUP_CANCEL_BUTTON, enabled=False)
                if self.on_status_update:
                    self.on_status_update("Backup plan complete.")
        except Exception:
            pass

    def _on_backup_pause(self) -> None:
        """Pause/resume backup execution."""
        if not self._action_engine:
            return

        if self._action_engine.progress.is_paused:
            self._action_engine.resume()
            dpg.configure_item(self.TAG_BACKUP_PAUSE_BUTTON, label="Pause")
        else:
            self._action_engine.pause()
            dpg.configure_item(self.TAG_BACKUP_PAUSE_BUTTON, label="Resume")

    def _on_backup_cancel(self) -> None:
        """Cancel backup execution."""
        if self._action_engine:
            self._action_engine.cancel()

    def _on_export_backup_plan(self) -> None:
        """Export backup plan to CSV on Desktop."""
        if not self._backup_plan:
            self._show_error_dialog("Export Plan", "No backup plan to export. Build a plan first.")
            return

        try:
            export_path = Path.home() / "Desktop" / "backup_plan.csv"
            with open(export_path, "w", encoding="utf-8") as handle:
                handle.write("source_path,target_path,size_bytes,content_hash,target_drive_id\n")
                for item in self._backup_plan:
                    handle.write(
                        f"\"{item.source_path}\",\"{item.target_path}\","
                        f"{item.size},{item.content_hash},{item.target_drive_id}\n"
                    )
            logger.info(f"Backup plan exported to {export_path}")
            if self.on_status_update:
                self.on_status_update(f"Backup plan exported to {export_path}")
        except PermissionError:
            logger.error("Permission denied exporting backup plan")
            self._show_error_dialog("Export Plan", "Permission denied. Close the file if it's open in another program.")
        except Exception as e:
            logger.error(f"Failed to export backup plan: {e}")
            self._show_error_dialog("Export Plan", f"Failed to export: {e}")

    def _on_open_backup_target(self) -> None:
        """Open selected backup target folders."""
        targets = self._get_selected_targets()
        if not targets:
            self._show_error_dialog("Open Targets", "No backup targets selected.")
            return

        failed_paths: list[str] = []
        for drive_id in targets:
            drive = self.drive_manager.get_drive(drive_id)
            if not drive:
                continue
            try:
                os.startfile(drive.path)
            except Exception as e:
                logger.warning(f"Failed to open backup target path {drive.path}: {e}")
                failed_paths.append(drive.label)

        if failed_paths:
            self._show_error_dialog(
                "Open Targets",
                f"Failed to open: {', '.join(failed_paths)}"
            )

    def _on_backup_source_browse(self) -> None:
        """Browse for backup source."""
        dpg.show_item("backup_source_dialog")

    def _on_backup_source_selected(self, sender, app_data) -> None:
        """Handle backup source selection."""
        path = app_data.get("file_path_name")
        if not path:
            return

        # Validate the selected path
        if not os.path.exists(path):
            self._show_error_dialog("Backup Source", f"Path does not exist: {path}")
            return

        if not os.path.isdir(path):
            self._show_error_dialog("Backup Source", f"Path is not a directory: {path}")
            return

        dpg.set_value(self.TAG_BACKUP_SOURCE, path)

    def _on_analyze_exclusions(self) -> None:
        """Analyze exclusion patterns and show impact."""
        source_path = dpg.get_value(self.TAG_BACKUP_SOURCE).strip().strip('"')
        if not source_path:
            self._show_error_dialog("Analyze Exclusions", "Choose a backup source folder first.")
            return

        exclude_text = dpg.get_value(self.TAG_BACKUP_EXCLUDES).strip()
        patterns = [line.strip() for line in exclude_text.splitlines() if line.strip()]
        candidates = self.redundancy_checker.get_exclusion_candidates(source_path, patterns)
        self._populate_exclusion_table(candidates)
        self._update_project_detections(source_path)

    def _update_project_detections(self, source_path: str) -> None:
        """Update project detection UI."""
        detections = self.redundancy_checker.detect_project_types(source_path)
        if not detections:
            dpg.set_value(self.TAG_PROJECT_DETECTIONS, "None detected")
            dpg.set_value(self.TAG_PROJECT_SUGGESTIONS, "")
            return

        lines = []
        suggestions: list[str] = []
        for detection in detections:
            lines.append(f"- {detection.name}")
            for pattern in detection.suggested_excludes:
                if pattern not in suggestions:
                    suggestions.append(pattern)

        dpg.set_value(self.TAG_PROJECT_DETECTIONS, "\n".join(lines))
        dpg.set_value(self.TAG_PROJECT_SUGGESTIONS, "\n".join(suggestions))

    def _populate_exclusion_table(self, candidates: list[ExclusionCandidate]) -> None:
        """Populate exclusion analysis table."""
        children = dpg.get_item_children(self.TAG_BACKUP_EXCLUDE_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        if not candidates:
            with dpg.table_row(parent=self.TAG_BACKUP_EXCLUDE_TABLE):
                dpg.add_text("No matches.")
                dpg.add_text("")
                dpg.add_text("")
            return

        for item in candidates[:200]:
            with dpg.table_row(parent=self.TAG_BACKUP_EXCLUDE_TABLE):
                dpg.add_text(item.pattern)
                dpg.add_text(str(item.file_count))
                dpg.add_text(self._format_bytes(item.total_size))

    def _populate_backup_plan_table(self, plan: list[BackupPlanItem]) -> None:
        """Populate backup plan table."""
        children = dpg.get_item_children(self.TAG_BACKUP_PLAN_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        if not plan:
            with dpg.table_row(parent=self.TAG_BACKUP_PLAN_TABLE):
                dpg.add_text("No backup plan.")
                dpg.add_text("")
                dpg.add_text("")
            dpg.configure_item(self.TAG_BACKUP_EXPORT_BUTTON, enabled=False)
            dpg.configure_item(self.TAG_BACKUP_OPEN_TARGET_BUTTON, enabled=False)
            return

        for item in plan[:200]:
            with dpg.table_row(parent=self.TAG_BACKUP_PLAN_TABLE):
                dpg.add_text(Path(item.source_path).name)
                dpg.add_text(item.target_path)
                dpg.add_text(self._format_bytes(item.size))

        dpg.configure_item(self.TAG_BACKUP_EXPORT_BUTTON, enabled=True)
        dpg.configure_item(self.TAG_BACKUP_OPEN_TARGET_BUTTON, enabled=True)

    def _format_bytes(self, size: int) -> str:
        """Format bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def _set_selected_drive(self, drive_id: str) -> None:
        """Select a drive programmatically."""
        self._selected_drive_id = drive_id
        self._update_drive_details(drive_id)
        self._refresh_resume_button()
        self._update_selected_summary()
        self._refresh_action_states()
        self._suppress_selection_events = True
        try:
            for other_id, tag in self._selection_tags.items():
                if dpg.does_item_exist(tag):
                    dpg.set_value(tag, other_id == drive_id)
        finally:
            self._suppress_selection_events = False

    def _show_error_dialog(self, title: str, message: str) -> None:
        """Show a simple modal error dialog."""
        tag = "drives_error_dialog"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
        with dpg.window(
            label=title,
            tag=tag,
            modal=True,
            show=True,
            width=420,
            height=170,
            no_resize=True,
            pos=[300, 200],
        ):
            dpg.add_text(message)
            dpg.add_spacer(height=10)
            dpg.add_button(label="OK", callback=lambda: dpg.configure_item(tag, show=False))

    def _on_remap_drive_click(self) -> None:
        """Handle remap drive button click."""
        if not self._selected_drive_id:
            self._show_error_dialog("Remap Path", "Select a drive first.")
            return

        drive = self.drive_manager.get_drive(self._selected_drive_id)
        if not drive:
            self._show_error_dialog("Remap Path", "Drive not found.")
            return

        self._show_remap_dialog(drive)

    def _show_remap_dialog(self, drive: Drive) -> None:
        """Show dialog to remap a drive's root path."""
        tag = self.TAG_REMAP_DIALOG
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        def confirm():
            new_path = dpg.get_value(self.TAG_REMAP_PATH).strip()
            if not new_path:
                self._show_error_dialog("Remap Path", "No path provided.")
                return
            try:
                count = self.drive_manager.remap_drive_path(drive.id, new_path)
                dpg.configure_item(tag, show=False)
                if self.on_status_update:
                    self.on_status_update(
                        f"Remapped '{drive.label}' to {new_path} ({count} files updated)"
                    )
                self._refresh_drive_list()
            except ValueError as e:
                self._show_error_dialog("Remap Path", str(e))

        def cancel():
            dpg.configure_item(tag, show=False)

        with dpg.window(
            label="Remap Drive Path",
            tag=tag,
            modal=True,
            show=True,
            width=520,
            height=250,
            no_resize=True,
            pos=[250, 180],
        ):
            dpg.add_text(f"Drive: {drive.label}")
            dpg.add_text(f"Current path: {drive.path}")
            dpg.add_spacer(height=5)
            dpg.add_text(
                "All scan data, faces, metadata, and AI results will be preserved.\n"
                "Only the file paths in the database will be updated."
            )
            dpg.add_spacer(height=5)
            dpg.add_text("New path:")
            dpg.add_input_text(tag=self.TAG_REMAP_PATH, width=-1)
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Remap", callback=confirm)
                dpg.add_button(label="Cancel", callback=cancel)

    def _confirm_remove_drive(self, drive_label: str) -> None:
        """Show confirmation dialog for removing a drive."""
        tag = "confirm_remove_drive"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        def confirm():
            dpg.configure_item(tag, show=False)
            if not self._selected_drive_id:
                return
            self.drive_manager.remove_drive(self._selected_drive_id)
            self._selected_drive_id = None
            self._refresh_drive_list()

        def cancel():
            dpg.configure_item(tag, show=False)

        with dpg.window(
            label="Remove Drive",
            tag=tag,
            modal=True,
            show=True,
            width=420,
            height=190,
            no_resize=True,
            pos=[300, 200],
        ):
            dpg.add_text(f"Remove '{drive_label}' from the list?")
            dpg.add_text("This removes scan data but does not delete files.")
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Remove", callback=confirm)
                dpg.add_button(label="Cancel", callback=cancel)

    def _update_background_status(self) -> None:
        """Update background pipeline status text."""
        analysis_on = bool(dpg.get_value(self.TAG_BG_ANALYSIS)) if dpg.does_item_exist(self.TAG_BG_ANALYSIS) else False
        hash_on = bool(dpg.get_value(self.TAG_BG_HASH)) if dpg.does_item_exist(self.TAG_BG_HASH) else False
        status = f"Background: analysis {'ON' if analysis_on else 'OFF'}, hash {'ON' if hash_on else 'OFF'}"
        if dpg.does_item_exist(self.TAG_BG_STATUS):
            dpg.set_value(self.TAG_BG_STATUS, status)

    def cleanup(self) -> None:
        """Clean up resources."""
        # Stop scan operations
        if self._scanner:
            self._scanner.cancel()
        if self._hasher:
            self._hasher.cancel()
        if self._scan_thread:
            self._scan_thread.join(timeout=5)

        # Stop background pipeline workers
        self._analysis_worker_stop.set()
        self._hash_worker_stop.set()
        if self._analysis_worker_thread:
            self._analysis_worker_thread.join(timeout=5)
            self._analysis_worker_thread = None
        if self._hash_worker_thread:
            self._hash_worker_thread.join(timeout=5)
            self._hash_worker_thread = None

        # Stop analysis thread
        if self._analysis_thread:
            self._analysis_thread.join(timeout=5)
            self._analysis_thread = None

        # Stop face worker
        if self._face_worker:
            self._face_worker.stop(wait=False)
            self._face_worker = None
            self._face_worker_drive_id = None

        # Stop backup thread
        if self._action_engine:
            self._action_engine.cancel()
        if self._backup_thread:
            self._backup_thread.join(timeout=5)
            self._backup_thread = None

        # Clear scan-all queue
        self._scan_all_queue = []
        self._scan_all_active = False

        self.drive_manager.stop_monitoring()

    def _on_drive_status_change(self, drive_id: str, status: DriveStatus) -> None:
        """Handle drive status changes for auto-sync."""
        with contextlib.suppress(Exception):
            self._refresh_drive_list()
        if status != DriveStatus.CONNECTED:
            return
        if drive_id not in self.config.backup.target_drive_ids:
            return
        if not self.config.backup.source_path:
            return
        if self._backup_thread and self._backup_thread.is_alive():
            return
        self._sync_backup_to_drive(drive_id)

    def _sync_backup_to_drive(self, drive_id: str) -> None:
        """Sync backup plan to a specific drive."""
        source_path = self.config.backup.source_path
        exclude_patterns = self.config.backup.exclude_patterns
        plan = self.redundancy_checker.build_backup_plan_for_source(
            source_path=source_path,
            target_drive_ids=[drive_id],
            exclude_patterns=exclude_patterns,
        )
        if not plan:
            return
        self._backup_plan = plan
        self._populate_backup_plan_table(plan)
        self._on_execute_backup_plan()

    def _on_summarize_browse_click(self) -> None:
        """Show folder browser for summarization."""
        dpg.show_item(self.TAG_SUMMARIZE_DIALOG)

    def _on_summarize_folder_selected(self, sender, app_data) -> None:
        """Handle folder selection from browser."""
        selections = app_data.get("selections", {})
        if selections:
            folder_path = list(selections.values())[0]
            dpg.set_value(self.TAG_SUMMARIZE_FOLDER, folder_path)

    def _on_summarize_click(self) -> None:
        """Start summarization for the selected folder or drive."""
        # Get folder path from input OR use selected drive
        folder_path = dpg.get_value(self.TAG_SUMMARIZE_FOLDER).strip().strip('"')

        # Get selected drive if no folder path provided
        selected_drive = None
        if not folder_path and self._selected_drive_id:
            selected_drive = self.drive_manager.get_drive(self._selected_drive_id)

        # Determine target path: folder input takes precedence, then selected drive
        target_path = None
        if folder_path:
            target_path = folder_path
        elif selected_drive:
            target_path = selected_drive.path
        else:
            if self.on_status_update:
                self.on_status_update(
                    "Select a drive or enter a folder path to summarize",
                    level="warning"
                )
            return

        if not os.path.exists(target_path):
            if self.on_status_update:
                self.on_status_update(f"Path not found: {target_path}", level="error")
            return

        provider = dpg.get_value(self.TAG_SUMMARIZE_PROVIDER)
        model = dpg.get_value(self.TAG_SUMMARIZE_MODEL).strip()
        file_types_str = dpg.get_value(self.TAG_SUMMARIZE_FILE_TYPES).strip()
        limit_str = dpg.get_value(self.TAG_SUMMARIZE_LIMIT).strip()
        batch_mode = dpg.get_value(self.TAG_SUMMARIZE_BATCH_MODE)

        try:
            limit = int(limit_str) if limit_str else 500
        except ValueError:
            if self.on_status_update:
                self.on_status_update("Limit must be a number", level="error")
            return

        file_types = None
        if file_types_str:
            file_types = [
                ext.strip() if ext.startswith(".") else f".{ext.strip()}"
                for ext in file_types_str.split(",")
            ]

        # Check LMStudio model status if using LMStudio provider
        if provider == "lmstudio":
            self._update_lmstudio_model_status()

        if self.on_status_update:
            mode_str = "batch mode" if batch_mode else "sequential mode"
            source_str = "selected drive" if (not folder_path and selected_drive) else "folder"
            self.on_status_update(
                f"Starting summarization ({mode_str}) for {source_str}: {target_path}..."
            )

        dpg.configure_item(self.TAG_BTN_SUMMARIZE, enabled=False)
        dpg.configure_item(self.TAG_SUMMARIZE_PROGRESS, show=True)
        dpg.set_value(self.TAG_SUMMARIZE_PROGRESS_TEXT, "Checking if path is scanned...")
        dpg.set_value(self.TAG_SUMMARIZE_PROGRESS_BAR, 0.0)

        thread = threading.Thread(
            target=self._run_summarization_with_auto_scan,
            args=(target_path, provider, model, file_types, limit, batch_mode),
            daemon=True
        )
        thread.start()

    def _run_summarization_with_auto_scan(
        self,
        target_path: str,
        provider: str,
        model: str,
        file_types: list[str] | None,
        limit: int,
        batch_mode: bool
    ) -> None:
        """Run summarization with automatic scanning if path not in database."""
        try:
            # Check if path is within any scanned drive
            drives = self.drive_manager.get_all_drives()
            matching_drive = None

            for drive in drives:
                if target_path == drive.path or target_path.startswith(drive.path + os.sep):
                    matching_drive = drive
                    break

            # Check if we have files in database for this path
            files_in_db = self.drive_manager.db.get_files_needing_summary_in_directory(
                target_path,
                limit=1,  # Just check if any exist
                file_types=file_types
            )

            # If no files in database, we need to scan
            if not files_in_db:
                if matching_drive:
                    # Path is within a registered drive but not scanned yet
                    dpg.configure_item(
                        self.TAG_SUMMARIZE_PROGRESS_TEXT,
                        default_value="Path in registered drive but not scanned. Scanning now..."
                    )
                    if self.on_status_update:
                        self.on_status_update(f"Scanning {target_path} before summarization...")

                    # Run scan on the drive
                    self._scan_drive_for_summarization(matching_drive.id, target_path)

                else:
                    # Path is not in any registered drive - register and scan it
                    dpg.configure_item(
                        self.TAG_SUMMARIZE_PROGRESS_TEXT,
                        default_value="Path not registered. Adding as drive and scanning..."
                    )
                    if self.on_status_update:
                        self.on_status_update(f"Registering and scanning {target_path}...")

                    # Add as new drive
                    import uuid
                    drive_id = str(uuid.uuid4())
                    drive_label = os.path.basename(target_path) or target_path

                    # Use DriveManager to add the drive properly
                    success = self.drive_manager.add_drive(
                        drive_id=drive_id,
                        label=drive_label,
                        path=target_path
                    )

                    if success:
                        # Scan the newly added drive
                        self._scan_drive_for_summarization(drive_id, target_path)
                        # Refresh drive list in UI
                        self._populate_drive_list()
                    else:
                        dpg.configure_item(
                            self.TAG_SUMMARIZE_PROGRESS_TEXT,
                            default_value="Failed to register drive"
                        )
                        dpg.configure_item(self.TAG_BTN_SUMMARIZE, enabled=True)
                        return

            # Now run summarization (path is guaranteed to be scanned)
            dpg.configure_item(
                self.TAG_SUMMARIZE_PROGRESS_TEXT,
                default_value="Starting summarization..."
            )
            self._run_summarization(target_path, provider, model, file_types, limit, batch_mode)

        except Exception as exc:
            logger.error(f"Auto-scan summarization failed: {exc}")
            dpg.configure_item(
                self.TAG_SUMMARIZE_PROGRESS_TEXT,
                default_value=f"Error: {exc}"
            )
            dpg.configure_item(self.TAG_BTN_SUMMARIZE, enabled=True)
            if self.on_status_update:
                self.on_status_update(f"Summarization failed: {exc}", level="error")

    def _scan_drive_for_summarization(self, drive_id: int, path: str) -> None:
        """Run a quick scan on a drive/folder before summarization."""
        from duplicleaner.core.scanner import ScanMode, Scanner

        dpg.configure_item(
            self.TAG_SUMMARIZE_PROGRESS_TEXT,
            default_value=f"Scanning {path}..."
        )

        drive = self.drive_manager.get_drive(drive_id)
        if not drive:
            raise Exception("Drive not found for summarization scan")

        def on_progress(progress: ScanProgress) -> None:
            dpg.set_value(self.TAG_SUMMARIZE_PROGRESS_BAR, 0.0)
            dpg.configure_item(
                self.TAG_SUMMARIZE_PROGRESS_TEXT,
                default_value=f"Scanning: {progress.files_found} files found..."
            )

        scanner = Scanner(self.drive_manager.db, progress_callback=on_progress)
        result = scanner.scan(drive, mode=ScanMode.QUICK, resume_state=None)

        if scanner.state == ScanState.COMPLETED:
            dpg.configure_item(
                self.TAG_SUMMARIZE_PROGRESS_TEXT,
                default_value=f"Scan complete: {result.total_files} files indexed"
            )
            if self.on_status_update:
                self.on_status_update(f"Scan complete: {result.total_files} files found")
        elif scanner.state == ScanState.CANCELLED:
            raise Exception("Scan cancelled")
        else:
            raise Exception(f"Scan failed: {scanner.state.value}")

    def _update_lmstudio_model_status(self) -> None:
        """Update the model status text with current LMStudio model."""
        try:
            from duplicleaner.utils.lmstudio_manager import LMStudioManager

            manager = LMStudioManager()
            if manager.is_available():
                current_model = manager.get_current_model()
                if current_model:
                    status_text = f"Current model: {current_model.name} ({current_model.type.value})"
                    dpg.set_value(self.TAG_SUMMARIZE_MODEL_STATUS, status_text)
                else:
                    dpg.set_value(self.TAG_SUMMARIZE_MODEL_STATUS, "No model loaded in LMStudio")
            else:
                dpg.set_value(self.TAG_SUMMARIZE_MODEL_STATUS, "LMStudioMonitorService not available")
        except Exception as exc:
            logger.debug(f"Could not check LMStudio status: {exc}")
            dpg.set_value(self.TAG_SUMMARIZE_MODEL_STATUS, "")

    def _run_summarization(
        self,
        folder_path: str,
        provider: str,
        model: str,
        file_types: list[str] | None,
        limit: int,
        batch_mode: bool = True
    ) -> None:
        """Run summarization in background thread with optional intelligent batch processing."""
        try:
            original_provider = self.config.ai.summary_provider
            try:
                self.config.ai.summary_provider = provider
                if model:
                    if provider == "lmstudio":
                        self.config.ai.summary_model_lmstudio = model
                    elif provider == "openai":
                        self.config.ai.summary_model_openai = model
                    elif provider == "anthropic":
                        self.config.ai.summary_model_anthropic = model
                    elif provider == "local":
                        self.config.ai.summary_model_local = model

                if batch_mode:
                    self._run_batch_summarization(folder_path, provider, file_types, limit)
                else:
                    self._run_sequential_summarization(folder_path, file_types, limit)


            finally:
                self.config.ai.summary_provider = original_provider
                dpg.configure_item(self.TAG_BTN_SUMMARIZE, enabled=True)

        except Exception as exc:
            logger.error(f"Summarization failed: {exc}")
            dpg.configure_item(
                self.TAG_SUMMARIZE_PROGRESS_TEXT,
                default_value=f"Error: {exc}"
            )
            dpg.configure_item(self.TAG_BTN_SUMMARIZE, enabled=True)
            if self.on_status_update:
                self.on_status_update(f"Summarization failed: {exc}", level="error")

    def _run_batch_summarization(
        self,
        folder_path: str,
        provider: str,
        file_types: list[str] | None,
        limit: int
    ) -> None:
        """Run intelligent batch summarization with model detection."""
        from duplicleaner.ai.content_summarizer import ContentSummarizer

        summarizer = ContentSummarizer(self.drive_manager.db)

        # Check if LMStudio Monitor Service is available
        if provider == "lmstudio" and summarizer.lmstudio_manager:
            dpg.configure_item(
                self.TAG_SUMMARIZE_PROGRESS_TEXT,
                default_value="LMStudio Monitor detected - automatic model management enabled"
            )
            time.sleep(1)

        # Convert file_types list to set for ContentSummarizer
        file_types_set = set(file_types) if file_types else None

        dpg.configure_item(
            self.TAG_SUMMARIZE_PROGRESS_TEXT,
            default_value="Analyzing files and grouping by type..."
        )

        # Run batch summarization
        progress = summarizer.summarize_directory_batch(
            directory=folder_path,
            file_types=file_types_set,
            limit=limit,
        )

        # Update UI with file type breakdown
        breakdown_text = (
            f"File breakdown: "
            f"text={progress.text_files}, "
            f"images={progress.image_files}, "
            f"docs={progress.visual_doc_files}, "
            f"skipped={progress.skipped_files}"
        )
        dpg.configure_item(
            self.TAG_SUMMARIZE_PROGRESS_TEXT,
            default_value=breakdown_text
        )
        time.sleep(2)

        # Monitor progress
        last_processed = 0
        while progress.current_phase != "complete":
            current_processed = progress.processed_files
            if current_processed != last_processed:
                pct = progress.percent_complete
                dpg.set_value(self.TAG_SUMMARIZE_PROGRESS_BAR, pct / 100.0)

                phase_name = progress.current_phase.replace("_", " ").title()
                dpg.configure_item(
                    self.TAG_SUMMARIZE_PROGRESS_TEXT,
                    default_value=f"{phase_name}: {current_processed}/{progress.total_files} - {os.path.basename(progress.current_file)}"
                )
                last_processed = current_processed

            time.sleep(0.5)

        # Final results
        dpg.set_value(self.TAG_SUMMARIZE_PROGRESS_BAR, 1.0)
        dpg.configure_item(
            self.TAG_SUMMARIZE_PROGRESS_TEXT,
            default_value=f"Complete: {progress.successful} successful, {progress.failed} failed, {progress.skipped_files} skipped"
        )

        if self.on_status_update:
            self.on_status_update(
                f"Summarization complete: {progress.successful} generated, {progress.failed} failed"
            )

    def _run_sequential_summarization(
        self,
        folder_path: str,
        file_types: list[str] | None,
        limit: int
    ) -> None:
        """Run sequential file-by-file summarization (original behavior)."""
        from duplicleaner.ai.summaries import SummaryEngine

        files = self.drive_manager.db.get_files_needing_summary_in_directory(
            folder_path,
            limit=limit,
            file_types=file_types
        )

        if not files:
            dpg.configure_item(self.TAG_SUMMARIZE_PROGRESS_TEXT, default_value="No files found that need summaries")
            if self.on_status_update:
                self.on_status_update("No files found that need summaries", level="warning")
            return

        dpg.configure_item(
            self.TAG_SUMMARIZE_PROGRESS_TEXT,
            default_value=f"Found {len(files)} files to summarize"
        )

        engine = SummaryEngine(self.drive_manager.db)
        if not engine.is_available():
            dpg.configure_item(
                self.TAG_SUMMARIZE_PROGRESS_TEXT,
                default_value="Provider not available"
            )
            if self.on_status_update:
                self.on_status_update(
                    "Provider not available. Check LMStudio/Ollama is running or API keys are set.",
                    level="error"
                )
            return

        generated = 0
        failed = 0
        for i, file_record in enumerate(files, 1):
            progress = i / len(files)
            dpg.set_value(self.TAG_SUMMARIZE_PROGRESS_BAR, progress)
            dpg.configure_item(
                self.TAG_SUMMARIZE_PROGRESS_TEXT,
                default_value=f"Processing {i}/{len(files)}: {os.path.basename(file_record.path)}"
            )

            try:
                summary = engine.analyze_file(file_record)
                if summary:
                    generated += 1
                else:
                    failed += 1
            except Exception as exc:
                logger.warning(f"Failed to summarize {file_record.path}: {exc}")
                failed += 1

        dpg.configure_item(
            self.TAG_SUMMARIZE_PROGRESS_TEXT,
            default_value=f"Complete: {generated} generated, {failed} failed"
        )
        if self.on_status_update:
            self.on_status_update(
                f"Summarization complete: {generated} generated, {failed} failed"
            )

    # ─── Corrupt Files & Recovery ─────────────────────────────────────

    def _on_check_corruption_click(self) -> None:
        """Start a corruption scan on the selected drive."""
        if self._corrupt_scan_thread and self._corrupt_scan_thread.is_alive():
            self._show_error_dialog("Corruption Scan", "A corruption scan is already running.")
            return

        drive_id = self._selected_drive_id
        if not drive_id:
            self._show_error_dialog("Corruption Scan", "Select a drive first.")
            return

        dpg.configure_item(self.TAG_BTN_CHECK_CORRUPT, enabled=False)
        dpg.configure_item(self.TAG_CORRUPT_PROGRESS, show=True)
        dpg.set_value(self.TAG_CORRUPT_PROGRESS_TEXT, "Starting corruption scan...")
        dpg.set_value(self.TAG_CORRUPT_PROGRESS_BAR, 0.0)
        dpg.set_value(self.TAG_CORRUPT_COUNT, "Scanning...")

        self._corrupt_scan_thread = threading.Thread(
            target=self._run_corruption_scan,
            args=(drive_id,),
            daemon=True,
        )
        self._corrupt_scan_thread.start()

    def _run_corruption_scan(self, drive_id: str) -> None:
        """Run corruption scan in background thread."""
        try:
            scanner = Scanner()

            def progress(processed: int, total: int, path: str) -> None:
                if total > 0:
                    pct = processed / total
                    dpg.set_value(self.TAG_CORRUPT_PROGRESS_BAR, pct)
                filename = os.path.basename(path)
                dpg.set_value(
                    self.TAG_CORRUPT_PROGRESS_TEXT,
                    f"Checking {processed:,}/{total:,}: {filename}",
                )

            corrupt_count = scanner.detect_corrupt_images(
                drive_id=drive_id,
                progress_callback=progress,
            )

            dpg.set_value(self.TAG_CORRUPT_PROGRESS_TEXT, f"Done: {corrupt_count} corrupt files found")
            dpg.set_value(self.TAG_CORRUPT_PROGRESS_BAR, 1.0)

            self._refresh_corrupt_table(drive_id)

            if self.on_status_update:
                self.on_status_update(f"Corruption scan complete: {corrupt_count} corrupt files found")

        except Exception as e:
            logger.error(f"Corruption scan error: {e}")
            dpg.set_value(self.TAG_CORRUPT_PROGRESS_TEXT, f"Error: {e}")
        finally:
            dpg.configure_item(self.TAG_BTN_CHECK_CORRUPT, enabled=True)
            self._corrupt_scan_thread = None

    def _refresh_corrupt_table(self, drive_id: str | None = None) -> None:
        """Refresh the corrupt files table from the database."""
        db = self.drive_manager.db
        corrupt_files = db.get_corrupt_files(drive_id=drive_id)
        self._corrupt_files_cache = corrupt_files

        count = len(corrupt_files)
        if count == 0:
            dpg.set_value(self.TAG_CORRUPT_COUNT, "No corrupt files found.")
            dpg.configure_item(self.TAG_BTN_RECOVER_ALL, enabled=False)
        else:
            total_size = sum(cf.get("size", 0) for cf in corrupt_files)
            dpg.set_value(
                self.TAG_CORRUPT_COUNT,
                f"{count} corrupt file{'s' if count != 1 else ''} ({self._fmt_size(total_size)})",
            )
            dpg.configure_item(self.TAG_BTN_RECOVER_ALL, enabled=True)

        # Clear table
        children = dpg.get_item_children(self.TAG_CORRUPT_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        severity_colors = {
            "high": (255, 80, 80),
            "medium": (255, 180, 60),
            "low": (180, 220, 100),
        }

        for cf in corrupt_files:
            with dpg.table_row(parent=self.TAG_CORRUPT_TABLE):
                # Filename
                filename = cf.get("filename", os.path.basename(cf.get("path", "")))
                dpg.add_text(filename)
                add_tooltip(dpg.last_item(), cf.get("path", ""))

                # Corruption type
                ctype = cf.get("corruption_type", "unknown")
                dpg.add_text(ctype.replace("_", " ").title())

                # Severity
                sev = cf.get("severity", "medium")
                dpg.add_text(sev.upper(), color=severity_colors.get(sev, (200, 200, 200)))

                # Size
                dpg.add_text(self._fmt_size(cf.get("size", 0)))

                # Action buttons
                file_id = cf["file_id"]
                path = cf["path"]
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Recover",
                        callback=lambda s, a, u: self._on_recover_file_click(u[0], u[1]),
                        user_data=(file_id, path),
                    )
                    dpg.add_button(
                        label="Preview",
                        callback=lambda s, a, u: self._on_preview_corrupt_click(u[0], u[1]),
                        user_data=(file_id, path),
                    )

    @staticmethod
    def _fmt_size(size_bytes: int) -> str:
        """Format bytes as human readable size."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def _on_recover_file_click(self, file_id: int, file_path: str) -> None:
        """Attempt recovery on a single corrupt file."""
        if self._recovery_thread and self._recovery_thread.is_alive():
            self._show_error_dialog("Recovery", "A recovery operation is already running.")
            return

        self._recovery_thread = threading.Thread(
            target=self._run_single_recovery,
            args=(file_id, file_path),
            daemon=True,
        )
        self._recovery_thread.start()

    def _run_single_recovery(self, file_id: int, file_path: str) -> None:
        """Run single file recovery in background."""
        try:
            dpg.configure_item(self.TAG_RECOVERY_PROGRESS, show=True)
            dpg.set_value(
                self.TAG_RECOVERY_PROGRESS_TEXT,
                f"Recovering: {os.path.basename(file_path)}...",
            )
            dpg.set_value(self.TAG_RECOVERY_PROGRESS_BAR, 0.5)

            if not self._recovery_manager:
                self._recovery_manager = RecoveryManager(db=self.drive_manager.db)

            result = self._recovery_manager.recover_file(file_id, file_path)

            if result.success:
                msg = f"Recovered using {result.strategy_used}: {os.path.basename(result.recovered_path or '')}"
                dpg.set_value(self.TAG_RECOVERY_PROGRESS_TEXT, msg)
                if self.on_status_update:
                    self.on_status_update(msg)
                # Show before/after preview
                self._show_recovery_preview(file_path, result.recovered_path)
            else:
                msg = f"Recovery failed: {result.error or 'All strategies exhausted'}"
                dpg.set_value(self.TAG_RECOVERY_PROGRESS_TEXT, msg)
                if self.on_status_update:
                    self.on_status_update(msg)

            dpg.set_value(self.TAG_RECOVERY_PROGRESS_BAR, 1.0)

            # Refresh table
            self._refresh_corrupt_table(self._selected_drive_id)

        except Exception as e:
            logger.error(f"Recovery error: {e}")
            dpg.set_value(self.TAG_RECOVERY_PROGRESS_TEXT, f"Error: {e}")
        finally:
            self._recovery_thread = None

    def _on_recover_all_click(self) -> None:
        """Start batch recovery on all corrupt files."""
        if self._recovery_thread and self._recovery_thread.is_alive():
            self._show_error_dialog("Recovery", "A recovery operation is already running.")
            return

        if not self._corrupt_files_cache:
            self._show_error_dialog("Recovery", "No corrupt files to recover.")
            return

        dpg.configure_item(self.TAG_BTN_RECOVER_ALL, enabled=False)
        dpg.configure_item(self.TAG_RECOVERY_PROGRESS, show=True)
        dpg.set_value(self.TAG_RECOVERY_PROGRESS_TEXT, "Starting batch recovery...")
        dpg.set_value(self.TAG_RECOVERY_PROGRESS_BAR, 0.0)

        self._recovery_thread = threading.Thread(
            target=self._run_batch_recovery,
            daemon=True,
        )
        self._recovery_thread.start()

    def _run_batch_recovery(self) -> None:
        """Run batch recovery in background thread."""
        try:
            if not self._recovery_manager:
                self._recovery_manager = RecoveryManager(db=self.drive_manager.db)

            corrupt_files = list(self._corrupt_files_cache)

            def progress(processed: int, total: int, filename: str, success: bool) -> None:
                pct = processed / total if total > 0 else 0
                dpg.set_value(self.TAG_RECOVERY_PROGRESS_BAR, pct)
                status = "OK" if success else "FAILED"
                dpg.set_value(
                    self.TAG_RECOVERY_PROGRESS_TEXT,
                    f"[{processed}/{total}] {filename}: {status}",
                )

            success_count, fail_count = self._recovery_manager.recover_batch(
                corrupt_files, progress_callback=progress,
            )

            dpg.set_value(
                self.TAG_RECOVERY_PROGRESS_TEXT,
                f"Batch complete: {success_count} recovered, {fail_count} failed",
            )
            dpg.set_value(self.TAG_RECOVERY_PROGRESS_BAR, 1.0)

            if self.on_status_update:
                self.on_status_update(
                    f"Batch recovery: {success_count} recovered, {fail_count} failed"
                )

            # Refresh table
            self._refresh_corrupt_table(self._selected_drive_id)

        except Exception as e:
            logger.error(f"Batch recovery error: {e}")
            dpg.set_value(self.TAG_RECOVERY_PROGRESS_TEXT, f"Error: {e}")
        finally:
            dpg.configure_item(self.TAG_BTN_RECOVER_ALL, enabled=True)
            self._recovery_thread = None

    def _on_preview_corrupt_click(self, file_id: int, file_path: str) -> None:
        """Show a preview of the corrupt file."""
        if not os.path.exists(file_path):
            self._show_error_dialog("Preview", f"File not found:\n{file_path}")
            return

        # Check if there's already a successful recovery
        attempts = self.drive_manager.db.get_recovery_attempts(file_id)
        recovered_path = None
        for attempt in attempts:
            if attempt.get("success") and attempt.get("recovered_path"):
                rp = attempt["recovered_path"]
                if os.path.exists(rp):
                    recovered_path = rp
                    break

        if recovered_path:
            self._show_recovery_preview(file_path, recovered_path)
        else:
            self._show_corrupt_preview(file_path)

    def _show_corrupt_preview(self, file_path: str) -> None:
        """Show a preview dialog for a corrupt file."""
        tag = "corrupt_preview_dialog"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        # Try to load image (even partially)
        texture_tag = "corrupt_preview_tex"
        tex_loaded = False
        try:
            from PIL import Image, ImageOps
            import numpy as np

            with Image.open(file_path) as img:
                img.load()
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGBA")
                # Scale to fit preview
                max_dim = 400
                w, h = img.size
                if w > max_dim or h > max_dim:
                    ratio = min(max_dim / w, max_dim / h)
                    img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
                w, h = img.size
                data = np.array(img).flatten().astype(np.float32) / 255.0

                if dpg.does_item_exist(texture_tag):
                    dpg.delete_item(texture_tag)
                with dpg.texture_registry():
                    dpg.add_static_texture(w, h, data.tolist(), tag=texture_tag)
                tex_loaded = True
        except Exception:
            tex_loaded = False

        with dpg.window(
            label="Corrupt File Preview",
            tag=tag,
            modal=True,
            show=True,
            width=480,
            height=550 if tex_loaded else 180,
            no_resize=True,
            pos=[200, 100],
        ):
            dpg.add_text(f"File: {os.path.basename(file_path)}")
            dpg.add_text(f"Path: {file_path}", wrap=450, color=(180, 180, 180))
            dpg.add_spacer(height=5)

            if tex_loaded:
                dpg.add_text("Preview (may show partial/corrupted image):")
                dpg.add_image(texture_tag)
            else:
                dpg.add_text("Cannot load preview - file is too corrupted.", color=(255, 80, 80))

            dpg.add_spacer(height=10)
            dpg.add_button(label="Close", callback=lambda: dpg.configure_item(tag, show=False))

    def _show_recovery_preview(self, original_path: str, recovered_path: str | None) -> None:
        """Show before/after recovery preview dialog."""
        if not recovered_path or not os.path.exists(recovered_path):
            return

        tag = "recovery_preview_dialog"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        orig_tex_tag = "recovery_orig_tex"
        recv_tex_tag = "recovery_recv_tex"
        orig_loaded = False
        recv_loaded = False

        # Helper to load image texture
        def load_tex(path: str, tex_tag: str) -> bool:
            try:
                from PIL import Image, ImageOps
                import numpy as np

                with Image.open(path) as img:
                    img.load()
                    img = ImageOps.exif_transpose(img)
                    img = img.convert("RGBA")
                    max_dim = 350
                    w, h = img.size
                    if w > max_dim or h > max_dim:
                        ratio = min(max_dim / w, max_dim / h)
                        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
                    w, h = img.size
                    data = np.array(img).flatten().astype(np.float32) / 255.0

                    if dpg.does_item_exist(tex_tag):
                        dpg.delete_item(tex_tag)
                    with dpg.texture_registry():
                        dpg.add_static_texture(w, h, data.tolist(), tag=tex_tag)
                    return True
            except Exception:
                return False

        orig_loaded = load_tex(original_path, orig_tex_tag)
        recv_loaded = load_tex(recovered_path, recv_tex_tag)

        dialog_width = 760 if (orig_loaded and recv_loaded) else 440
        dialog_height = 520

        with dpg.window(
            label="Recovery Preview - Before / After",
            tag=tag,
            modal=True,
            show=True,
            width=dialog_width,
            height=dialog_height,
            no_resize=True,
            pos=[120, 80],
        ):
            dpg.add_text(f"Original: {os.path.basename(original_path)}")
            dpg.add_text(f"Recovered: {os.path.basename(recovered_path)}", color=(100, 255, 100))
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                # Original
                with dpg.child_window(width=360, height=400, border=True):
                    dpg.add_text("ORIGINAL (corrupt)", color=(255, 120, 80))
                    if orig_loaded:
                        dpg.add_image(orig_tex_tag)
                    else:
                        dpg.add_text("Cannot load", color=(255, 80, 80))

                dpg.add_spacer(width=10)

                # Recovered
                with dpg.child_window(width=360, height=400, border=True):
                    dpg.add_text("RECOVERED", color=(100, 255, 100))
                    if recv_loaded:
                        dpg.add_image(recv_tex_tag)
                    else:
                        dpg.add_text("Cannot load", color=(255, 80, 80))

            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Close", callback=lambda: dpg.configure_item(tag, show=False))
                if os.path.exists(recovered_path):
                    dpg.add_button(
                        label="Open Recovered File",
                        callback=lambda: os.startfile(recovered_path),
                    )

    # --- Watch Folders ---------------------------------------------------

    def _create_watch_add_dialog(self) -> None:
        """Create the add watch folder dialog."""
        tag = self.TAG_WATCH_ADD_DIALOG
        with dpg.window(
            tag=tag,
            label="Add Watch Folder",
            modal=True,
            show=False,
            width=520,
            height=320,
            no_resize=True,
            pos=[140, 120],
        ):
            dpg.add_text("Configure a folder to monitor for new files.")
            dpg.add_spacer(height=10)

            with dpg.group(horizontal=True):
                dpg.add_text("Path:")
                dpg.add_input_text(
                    tag=self.TAG_WATCH_PATH_INPUT,
                    width=350,
                    hint="C:\\Photos\\Inbox or \\\\NAS\\incoming",
                )
                dpg.add_button(
                    label="Browse...",
                    callback=lambda: dpg.show_item(self.TAG_WATCH_FOLDER_DIALOG),
                )

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Poll interval (seconds):")
                dpg.add_input_int(
                    tag=self.TAG_WATCH_POLL_INTERVAL,
                    default_value=self.config.watch.default_poll_interval,
                    min_value=5,
                    max_value=3600,
                    width=100,
                )
                dpg.add_text("  Debounce (seconds):")
                dpg.add_input_int(
                    tag=self.TAG_WATCH_DEBOUNCE,
                    default_value=self.config.watch.default_debounce,
                    min_value=5,
                    max_value=600,
                    width=100,
                )

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_checkbox(
                    label="Auto-scan new files",
                    tag=self.TAG_WATCH_AUTO_SCAN,
                    default_value=True,
                )
                dpg.add_checkbox(
                    label="Auto-organize",
                    tag=self.TAG_WATCH_AUTO_ORGANIZE,
                    default_value=False,
                )
                dpg.add_checkbox(
                    label="Auto-AI analysis",
                    tag=self.TAG_WATCH_AUTO_AI,
                    default_value=False,
                )

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Organize format:")
                dpg.add_combo(
                    tag=self.TAG_WATCH_ORG_FORMAT,
                    items=["YYYY/MM", "YYYY/MM/DD", "YYYY-MM", "YYYY"],
                    default_value="YYYY/MM",
                    width=150,
                )

            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Add", callback=self._on_watch_add_confirm, width=100)
                dpg.add_button(
                    label="Cancel",
                    callback=lambda: dpg.configure_item(tag, show=False),
                    width=100,
                )

    def _create_watch_folder_browse_dialog(self) -> None:
        """Create the folder browse dialog for watch folder path."""
        with dpg.file_dialog(
            tag=self.TAG_WATCH_FOLDER_DIALOG,
            directory_selector=True,
            show=False,
            callback=self._on_watch_folder_selected,
            width=700,
            height=400,
        ):
            dpg.add_file_extension(".*", color=(255, 255, 255, 255))

    def _on_watch_folder_selected(self, sender, app_data) -> None:
        """Handle folder selection from browse dialog."""
        selections = app_data.get("selections", {})
        if selections:
            path = list(selections.values())[0]
        else:
            path = app_data.get("file_path_name", "")
        if path:
            dpg.set_value(self.TAG_WATCH_PATH_INPUT, path)

    def _on_watch_add_click(self) -> None:
        """Show the add watch folder dialog."""
        dpg.set_value(self.TAG_WATCH_PATH_INPUT, "")
        dpg.set_value(self.TAG_WATCH_POLL_INTERVAL, self.config.watch.default_poll_interval)
        dpg.set_value(self.TAG_WATCH_DEBOUNCE, self.config.watch.default_debounce)
        dpg.set_value(self.TAG_WATCH_AUTO_SCAN, True)
        dpg.set_value(self.TAG_WATCH_AUTO_ORGANIZE, False)
        dpg.set_value(self.TAG_WATCH_AUTO_AI, False)
        dpg.set_value(self.TAG_WATCH_ORG_FORMAT, "YYYY/MM")
        dpg.show_item(self.TAG_WATCH_ADD_DIALOG)

    def _on_watch_add_confirm(self) -> None:
        """Add a new watch folder from dialog values."""
        from duplicleaner.utils.config import WatchFolderEntry, save_config

        path = dpg.get_value(self.TAG_WATCH_PATH_INPUT).strip()
        if not path:
            self._show_error_dialog("Add Watch Folder", "No path provided.")
            return

        if not os.path.isdir(path):
            self._show_error_dialog("Add Watch Folder", f"Path not found:\n{path}")
            return

        entry = WatchFolderEntry(
            path=path,
            enabled=True,
            poll_interval_seconds=dpg.get_value(self.TAG_WATCH_POLL_INTERVAL),
            debounce_seconds=dpg.get_value(self.TAG_WATCH_DEBOUNCE),
            auto_scan=dpg.get_value(self.TAG_WATCH_AUTO_SCAN),
            auto_organize=dpg.get_value(self.TAG_WATCH_AUTO_ORGANIZE),
            auto_ai_analysis=dpg.get_value(self.TAG_WATCH_AUTO_AI),
            organize_format=dpg.get_value(self.TAG_WATCH_ORG_FORMAT),
        )

        try:
            if self._folder_watcher:
                self._folder_watcher.add_watch_folder(entry)
            else:
                # No watcher instance, just save to config
                self.config.watch.watch_folders.append(entry)
                save_config()
            dpg.configure_item(self.TAG_WATCH_ADD_DIALOG, show=False)
            self._refresh_watch_table()
            if self.on_status_update:
                self.on_status_update(f"Added watch folder: {path}")
        except ValueError as e:
            self._show_error_dialog("Add Watch Folder", str(e))

    def _on_watch_enabled_toggle(self, sender, app_data) -> None:
        """Toggle global watch folder enabled state."""
        from duplicleaner.utils.config import save_config

        self.config.watch.global_enabled = bool(app_data)
        save_config()
        self._update_watch_status()

    def _on_watch_start_stop_click(self) -> None:
        """Start or stop the folder watcher."""
        if not self._folder_watcher:
            self._show_error_dialog("Watch Folders", "No folder watcher available.")
            return

        if self._folder_watcher.is_running:
            self._folder_watcher.stop()
            dpg.configure_item(self.TAG_BTN_WATCH_START, label="Start Watcher")
        else:
            if not self.config.watch.global_enabled:
                self.config.watch.global_enabled = True
                dpg.set_value(self.TAG_WATCH_ENABLED, True)
                from duplicleaner.utils.config import save_config
                save_config()
            self._folder_watcher.start()
            dpg.configure_item(self.TAG_BTN_WATCH_START, label="Stop Watcher")

        self._update_watch_status()

    def _on_watch_remove_click(self, path: str) -> None:
        """Remove a watch folder."""
        if self._folder_watcher:
            self._folder_watcher.remove_watch_folder(path)
        else:
            from duplicleaner.utils.config import save_config
            normalized = os.path.normpath(path)
            self.config.watch.watch_folders = [
                wf for wf in self.config.watch.watch_folders
                if os.path.normpath(wf.path) != normalized
            ]
            save_config()
        self._refresh_watch_table()

    def _on_watch_toggle_click(self, path: str, enabled: bool) -> None:
        """Toggle a watch folder enabled/disabled."""
        if self._folder_watcher:
            self._folder_watcher.toggle_folder(path, enabled)
        else:
            from duplicleaner.utils.config import save_config
            normalized = os.path.normpath(path)
            for wf in self.config.watch.watch_folders:
                if os.path.normpath(wf.path) == normalized:
                    wf.enabled = enabled
                    break
            save_config()
        self._refresh_watch_table()

    def _refresh_watch_table(self) -> None:
        """Refresh the watch folders table."""
        if not dpg.does_item_exist(self.TAG_WATCH_TABLE):
            return

        # Clear table rows
        children = dpg.get_item_children(self.TAG_WATCH_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        folders = self.config.watch.watch_folders
        for wf in folders:
            with dpg.table_row(parent=self.TAG_WATCH_TABLE):
                # Path
                display_path = wf.path
                if len(display_path) > 40:
                    display_path = "..." + display_path[-37:]
                dpg.add_text(display_path)
                add_tooltip(dpg.last_item(), wf.path)

                # Poll interval
                dpg.add_text(str(wf.poll_interval_seconds))

                # Auto-scan
                dpg.add_text("Yes" if wf.auto_scan else "No")

                # Auto-organize
                dpg.add_text("Yes" if wf.auto_organize else "No")

                # Enabled
                enabled_color = (100, 255, 100) if wf.enabled else (180, 180, 180)
                dpg.add_text("ON" if wf.enabled else "OFF", color=enabled_color)

                # Actions
                path = wf.path
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="X",
                        callback=lambda s, a, u: self._on_watch_remove_click(u),
                        user_data=path,
                        width=25,
                    )
                    is_on = wf.enabled
                    dpg.add_button(
                        label="Off" if is_on else "On",
                        callback=lambda s, a, u: self._on_watch_toggle_click(u[0], u[1]),
                        user_data=(path, not is_on),
                        width=35,
                    )

        self._update_watch_status()

    def _update_watch_status(self) -> None:
        """Update watch status text."""
        if not dpg.does_item_exist(self.TAG_WATCH_STATUS):
            return

        if self._folder_watcher and self._folder_watcher.is_running:
            count = self._folder_watcher.get_watched_folder_count()
            dpg.set_value(
                self.TAG_WATCH_STATUS,
                f"Running: monitoring {count} folder{'s' if count != 1 else ''}",
            )
            dpg.configure_item(self.TAG_WATCH_STATUS, color=(100, 255, 100))
            dpg.configure_item(self.TAG_BTN_WATCH_START, label="Stop Watcher")
        else:
            enabled_count = sum(1 for wf in self.config.watch.watch_folders if wf.enabled)
            if enabled_count > 0 and self.config.watch.global_enabled:
                dpg.set_value(
                    self.TAG_WATCH_STATUS,
                    f"Stopped ({enabled_count} folder{'s' if enabled_count != 1 else ''} configured)",
                )
                dpg.configure_item(self.TAG_WATCH_STATUS, color=(255, 180, 60))
            else:
                dpg.set_value(self.TAG_WATCH_STATUS, "Not running")
                dpg.configure_item(self.TAG_WATCH_STATUS, color=(180, 180, 180))
            dpg.configure_item(self.TAG_BTN_WATCH_START, label="Start Watcher")

    # --- Export ---

    def _on_export_redundancy(self) -> None:
        """Export redundancy report to CSV."""
        from duplicleaner.utils.export_manager import (
            export_csv,
            format_size,
            get_default_export_dir,
            get_timestamped_filename,
        )

        if not self._redundancy_report:
            if self.on_status_update:
                self.on_status_update("No redundancy report to export. Generate one first.")
            return

        report = self._redundancy_report
        export_dir = get_default_export_dir()
        filepath = export_dir / get_timestamped_filename("redundancy_report", "csv")

        rows = []
        for group in report.at_risk_groups:
            for file in group.files:
                drive = self.drive_manager.get_drive(file.drive_id)
                rows.append({
                    "status": "AT_RISK",
                    "content_hash": group.content_hash,
                    "drive_id": file.drive_id,
                    "drive_label": drive.label if drive else file.drive_id,
                    "filename": file.filename,
                    "path": file.path,
                    "size": file.size,
                    "size_human": format_size(file.size),
                })

        for group in report.redundant_groups:
            rows.append({
                "status": "REDUNDANT",
                "content_hash": group.content_hash,
                "drive_id": "",
                "drive_label": f"{group.drive_count} drives",
                "filename": f"{group.file_count} copies",
                "path": "",
                "size": group.size,
                "size_human": format_size(group.size),
            })

        count = export_csv(rows, filepath)
        msg = (
            f"Exported redundancy report ({report.at_risk_files} at-risk files, "
            f"{len(report.redundant_groups)} redundant groups) to {filepath}"
        )
        logger.info(msg)
        if self.on_status_update:
            self.on_status_update(msg)

    # --- Storage Analytics ---

    def _on_compute_analytics(self) -> None:
        """Compute and display storage analytics."""
        from duplicleaner.core.storage_analytics import compute_storage_report
        from duplicleaner.utils.export_manager import format_size

        if self.on_status_update:
            self.on_status_update("Computing storage analytics...")

        try:
            report = compute_storage_report(self.db)
            self._analytics_report = report

            # Update summary cards
            dpg.set_value("analytics_total_files", f"{report.total_files:,}")
            dpg.set_value("analytics_total_size", format_size(report.total_size))
            dpg.set_value("analytics_dup_waste", format_size(report.duplicate_waste))
            dpg.set_value("analytics_at_risk", format_size(report.at_risk_size))

            # Update type breakdown chart
            if report.type_breakdown:
                # Clear existing series
                for child in dpg.get_item_children("analytics_type_y", slot=1) or []:
                    dpg.delete_item(child)

                top_types = report.type_breakdown[:15]
                labels = [t.extension for t in top_types]
                sizes_gb = [t.total_size / (1024**3) for t in top_types]
                x_vals = list(range(len(labels)))

                dpg.add_bar_series(
                    x_vals, sizes_gb,
                    parent="analytics_type_y",
                    label="Size (GB)",
                )
                dpg.set_axis_limits("analytics_type_x", -0.5, len(labels) - 0.5)
                dpg.set_axis_ticks("analytics_type_x", tuple(zip(labels, x_vals)))

            # Update year breakdown chart
            if report.year_breakdown:
                for child in dpg.get_item_children("analytics_year_y", slot=1) or []:
                    dpg.delete_item(child)

                # Sort by year ascending for chart
                years_sorted = sorted(report.year_breakdown, key=lambda y: y.year)
                years = [float(y.year) for y in years_sorted]
                sizes_gb = [y.total_size / (1024**3) for y in years_sorted]

                dpg.add_bar_series(
                    years, sizes_gb,
                    parent="analytics_year_y",
                    label="Size (GB)",
                )
                if years:
                    dpg.set_axis_limits("analytics_year_x", min(years) - 0.5, max(years) + 0.5)

            # Update quick wins table
            children = dpg.get_item_children("analytics_quickwins_table", slot=1)
            if children:
                for child in children:
                    dpg.delete_item(child)

            if report.quick_wins:
                for qw in report.quick_wins:
                    with dpg.table_row(parent="analytics_quickwins_table"):
                        dpg.add_text(qw.category)
                        dpg.add_text(qw.description)
                        dpg.add_text(f"{qw.file_count:,}")
                        dpg.add_text(format_size(qw.recoverable_bytes))
            else:
                with dpg.table_row(parent="analytics_quickwins_table"):
                    dpg.add_text("No quick wins identified.")
                    dpg.add_text("")
                    dpg.add_text("")
                    dpg.add_text("")

            if self.on_status_update:
                self.on_status_update(
                    f"Analytics computed: {report.total_files:,} files, "
                    f"{format_size(report.total_size)}"
                )

        except Exception as exc:
            logger.error("Failed to compute analytics: %s", exc)
            if self.on_status_update:
                self.on_status_update(f"Analytics failed: {exc}")

    def _on_export_analytics(self) -> None:
        """Export analytics report to HTML."""
        from duplicleaner.utils.export_manager import (
            export_html,
            format_size,
            get_default_export_dir,
            get_timestamped_filename,
        )

        report = getattr(self, "_analytics_report", None)
        if not report:
            if self.on_status_update:
                self.on_status_update("No analytics to export. Compute analytics first.")
            return

        export_dir = get_default_export_dir()
        filepath = export_dir / get_timestamped_filename("analytics", "html")

        summary_stats = {
            "Total Files": f"{report.total_files:,}",
            "Total Size": format_size(report.total_size),
            "Duplicate Waste": format_size(report.duplicate_waste),
            "At-Risk Data": format_size(report.at_risk_size),
        }

        sections = []

        # Type breakdown
        if report.type_breakdown:
            type_rows = [{
                "Extension": t.extension,
                "Count": f"{t.count:,}",
                "Size": format_size(t.total_size),
                "Percentage": f"{t.percentage:.1f}%",
            } for t in report.type_breakdown[:30]]
            sections.append({
                "heading": "Storage by File Type",
                "columns": ["Extension", "Count", "Size", "Percentage"],
                "rows": type_rows,
            })

        # Year breakdown
        if report.year_breakdown:
            year_rows = [{
                "Year": y.year,
                "Files": f"{y.count:,}",
                "Size": format_size(y.total_size),
            } for y in sorted(report.year_breakdown, key=lambda x: x.year, reverse=True)]
            sections.append({
                "heading": "Storage by Year",
                "columns": ["Year", "Files", "Size"],
                "rows": year_rows,
            })

        # Quick wins
        if report.quick_wins:
            qw_rows = [{
                "Category": qw.category,
                "Description": qw.description,
                "Files": f"{qw.file_count:,}",
                "Recoverable": format_size(qw.recoverable_bytes),
            } for qw in report.quick_wins]
            sections.append({
                "heading": "Quick Wins",
                "columns": ["Category", "Description", "Files", "Recoverable"],
                "rows": qw_rows,
            })

        export_html(
            "DupliCleaner - Storage Analytics Report",
            sections,
            filepath,
            summary_stats=summary_stats,
        )

        msg = f"Analytics exported to {filepath}"
        logger.info(msg)
        if self.on_status_update:
            self.on_status_update(msg)
