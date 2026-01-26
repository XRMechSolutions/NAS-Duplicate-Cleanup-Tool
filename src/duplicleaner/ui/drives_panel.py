"""Drives Panel for DupliCleaner.

Dear PyGui UI component for managing drives and initiating scans.
"""

import os
import threading
from pathlib import Path
from typing import Callable, Optional

import dearpygui.dearpygui as dpg

from duplicleaner.db.models import Drive
from duplicleaner.drives.manager import DriveManager, DriveStatus, DriveInfo
from duplicleaner.drives.redundancy import RedundancyChecker, RedundancyReport, BackupPlanItem, ExclusionCandidate
from duplicleaner.utils.config import get_config, save_config
from duplicleaner.core.scanner import Scanner, ScanMode, ScanProgress, ScanState
from duplicleaner.core.hasher import Hasher, HashProgress, HashState
from duplicleaner.core.actions import ActionEngine, PendingAction, ActionType, OperationProgress
from duplicleaner.core.face_worker import FaceAnalysisWorker
from duplicleaner.core.analysis_runner import AnalysisRunner, AnalysisOptions
from duplicleaner.utils.logging import get_logger
from duplicleaner.ui.tooltips import add_tooltip, DRIVE_TOOLTIPS
from duplicleaner.ui.theme import get_status_color, get_accent_color, get_text_color

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

    def __init__(
        self,
        parent: int | str,
        drive_manager: Optional[DriveManager] = None,
        on_scan_complete: Optional[Callable[[str], None]] = None,
        on_status_update: Optional[Callable[[str], None]] = None,
        on_face_worker_state_change: Optional[Callable[[bool], None]] = None,
    ):
        """Initialize the drives panel.

        Args:
            parent: Parent window/container tag
            drive_manager: DriveManager instance (creates one if not provided)
            on_scan_complete: Callback when scan completes (drive_id)
        """
        self.parent = parent
        self.drive_manager = drive_manager or DriveManager(status_callback=self._on_drive_status_change)
        self.on_scan_complete = on_scan_complete
        self.on_status_update = on_status_update
        self.on_face_worker_state_change = on_face_worker_state_change
        self.redundancy_checker = RedundancyChecker(self.drive_manager.db, self.drive_manager)
        self.config = get_config()

        # Current scanner and hasher
        self._scanner: Optional[Scanner] = None
        self._hasher: Optional[Hasher] = None
        self._scan_thread: Optional[threading.Thread] = None
        self._current_scan_drive: Optional[str] = None
        self._resume_state: Optional[dict] = None
        self._face_worker: Optional[FaceAnalysisWorker] = None
        self._face_worker_drive_id: Optional[str] = None

        # Selected drive
        self._selected_drive_id: Optional[str] = None
        self._redundancy_report: Optional[RedundancyReport] = None
        self._backup_plan: list[BackupPlanItem] = []
        self._drive_label_map: dict[str, str] = {}
        self._action_engine: Optional[ActionEngine] = None
        self._backup_thread: Optional[threading.Thread] = None
        self._analysis_thread: Optional[threading.Thread] = None
        self._analysis_worker_thread: Optional[threading.Thread] = None
        self._analysis_worker_stop = threading.Event()
        self._hash_worker_thread: Optional[threading.Thread] = None
        self._hash_worker_stop = threading.Event()
        self._hash_lock = threading.Lock()
        self._queue_lock = threading.Lock()
        self._selection_tags: dict[str, str] = {}
        self._suppress_selection_events = False
        self._scan_all_queue: list[str] = []
        self._scan_all_mode: Optional[ScanMode] = None
        self._scan_all_active = False

        # Build UI
        self._build_ui()
        self.drive_manager.start_monitoring()

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
                with dpg.child_window(height=80, border=True):
                    with dpg.group(tag=self.TAG_BACKUP_TARGETS_GROUP):
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

                with dpg.child_window(height=180, border=True):
                    with dpg.table(
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
                with dpg.child_window(height=140, border=True):
                    with dpg.table(
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
                with dpg.child_window(height=160, border=True):
                    with dpg.table(
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

        # Create add drive dialog
        self._create_add_drive_dialog()
        self._create_backup_source_dialog()
        self._create_scan_all_dialog()
        self._update_background_status()

        # Initial refresh
        self._refresh_drive_list()
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

    def _set_section_visibility(self, has_drives: bool) -> None:
        """Toggle visibility for empty state and advanced sections."""
        if dpg.does_item_exist(self.TAG_GETTING_STARTED):
            dpg.configure_item(self.TAG_GETTING_STARTED, show=not has_drives)
        for tag in (self.TAG_ANALYSIS_HEADER, self.TAG_ADVANCED_HEADER, self.TAG_BACKUP_HEADER):
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

    def _refresh_action_states(self, has_drives: Optional[bool] = None) -> None:
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

    def _refresh_drive_list(self) -> None:
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
            status = self.drive_manager.get_drive_status(drive.id)
            space = self.drive_manager.get_space_info(drive.path) if status == DriveStatus.CONNECTED else None

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
                status_colors = {
                    DriveStatus.CONNECTED: (100, 200, 100),
                    DriveStatus.DISCONNECTED: (200, 100, 100),
                    DriveStatus.SCANNING: (100, 150, 255),
                    DriveStatus.ERROR: (255, 100, 100),
                    DriveStatus.NEEDS_SCAN: (200, 200, 100),
                }
                dpg.add_text(status.value.title(), color=status_colors.get(status, (200, 200, 200)))

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

        if drive_info.is_network:
            dpg.add_text(f"Type: Network Share", parent="drive_details")
            if drive_info.server:
                dpg.add_text(f"Server: {drive_info.server}", parent="drive_details")
        else:
            dpg.add_text(f"Type: Local Drive", parent="drive_details")
            if drive_info.volume_label:
                dpg.add_text(f"Volume: {drive_info.volume_label}", parent="drive_details")
            if drive_info.filesystem:
                dpg.add_text(f"Filesystem: {drive_info.filesystem}", parent="drive_details")

        dpg.add_text(f"Files: {drive.file_count:,}", parent="drive_details")

        if drive.last_scan:
            dpg.add_text(f"Last Scan: {drive.last_scan.strftime('%Y-%m-%d %H:%M:%S')}", parent="drive_details")

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

        def confirm(sender=None, app_data=None, user_data=None):
            dpg.configure_item(tag, show=False)
            if callable(on_confirm):
                on_confirm()

        def cancel(sender=None, app_data=None, user_data=None):
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

    def _start_scan(self, drive: Drive, mode: ScanMode, resume_state: Optional[dict]) -> None:
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

    def _run_scan(self, drive: Drive, mode: ScanMode, resume_state: Optional[dict]) -> None:
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
            logger.error(f"Permission denied exporting backup plan")
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
        try:
            self._refresh_drive_list()
        except Exception:
            pass
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
