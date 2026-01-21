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
from duplicleaner.utils.config import get_config
from duplicleaner.core.scanner import Scanner, ScanMode, ScanProgress, ScanState
from duplicleaner.core.hasher import Hasher, HashProgress, HashState
from duplicleaner.core.actions import ActionEngine, PendingAction, ActionType, OperationProgress
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
    TAG_REDUNDANCY_SUMMARY = "redundancy_summary_text"
    TAG_AT_RISK_TABLE = "at_risk_table"
    TAG_BACKUP_SOURCE = "backup_source_path"
    TAG_BACKUP_TARGETS_GROUP = "backup_targets_group"
    TAG_BACKUP_EXCLUDES = "backup_excludes"
    TAG_BACKUP_EXCLUDE_TABLE = "backup_exclude_table"
    TAG_BACKUP_PLAN_TABLE = "backup_plan_table"
    TAG_BACKUP_PROGRESS_GROUP = "backup_progress_group"
    TAG_BACKUP_PROGRESS_BAR = "backup_progress_bar"
    TAG_BACKUP_PROGRESS_TEXT = "backup_progress_text"
    TAG_BACKUP_PAUSE_BUTTON = "backup_pause_btn"
    TAG_BACKUP_CANCEL_BUTTON = "backup_cancel_btn"
    TAG_BACKUP_EXPORT_BUTTON = "backup_export_btn"
    TAG_BACKUP_OPEN_TARGET_BUTTON = "backup_open_target_btn"

    def __init__(
        self,
        parent: int | str,
        drive_manager: Optional[DriveManager] = None,
        on_scan_complete: Optional[Callable[[str], None]] = None,
        on_status_update: Optional[Callable[[str], None]] = None,
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
        self.redundancy_checker = RedundancyChecker(self.drive_manager.db, self.drive_manager)
        self.config = get_config()

        # Current scanner and hasher
        self._scanner: Optional[Scanner] = None
        self._hasher: Optional[Hasher] = None
        self._scan_thread: Optional[threading.Thread] = None
        self._current_scan_drive: Optional[str] = None
        self._resume_state: Optional[dict] = None

        # Selected drive
        self._selected_drive_id: Optional[str] = None
        self._redundancy_report: Optional[RedundancyReport] = None
        self._backup_plan: list[BackupPlanItem] = []
        self._drive_label_map: dict[str, str] = {}
        self._action_engine: Optional[ActionEngine] = None
        self._backup_thread: Optional[threading.Thread] = None

        # Build UI
        self._build_ui()
        self.drive_manager.start_monitoring()

    def _build_ui(self) -> None:
        """Build the panel UI."""
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            # Header
            dpg.add_text("Drives Management", color=(150, 200, 255))
            dpg.add_separator()
            dpg.add_spacer(height=10)

            # Action buttons
            with dpg.group(horizontal=True):
                dpg.add_button(label="Add Drive", callback=self._on_add_drive_click)
                dpg.add_button(label="Remove Selected", callback=self._on_remove_drive_click)
                dpg.add_spacer(width=20)
                dpg.add_button(label="Quick Scan", callback=lambda: self._on_scan_click(ScanMode.QUICK))
                dpg.add_button(label="Deep Scan", callback=lambda: self._on_scan_click(ScanMode.DEEP))
                dpg.add_button(label="Full Analysis", callback=lambda: self._on_scan_click(ScanMode.FULL))
                dpg.add_button(
                    label="Resume Scan",
                    tag=self.TAG_RESUME_SCAN_BUTTON,
                    callback=self._on_resume_scan_click,
                    enabled=False,
                )
                dpg.add_spacer(width=20)
                dpg.add_button(label="Refresh", callback=self._refresh_drive_list)

            dpg.add_spacer(height=10)

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
                dpg.add_table_column(label="", width_fixed=True, init_width_or_weight=30)  # Selection
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
                dpg.add_text("Scan Progress", color=(150, 200, 255))
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
            dpg.add_text("Drive Details", color=(150, 200, 255))
            dpg.add_spacer(height=5)

            with dpg.group(tag="drive_details"):
                dpg.add_text("Select a drive to view details.")

            dpg.add_spacer(height=10)
            dpg.add_separator()
            dpg.add_text("Redundancy & Backups", color=(150, 200, 255))
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_button(label="Generate Redundancy Report", callback=self._on_generate_redundancy)
                dpg.add_spacer(width=10)
                dpg.add_button(label="Build Backup Plan", callback=self._on_build_backup_plan)
                dpg.add_button(label="Execute Backup Plan", callback=self._on_execute_backup_plan)
                dpg.add_button(label="Export Plan", tag=self.TAG_BACKUP_EXPORT_BUTTON, callback=self._on_export_backup_plan)
                dpg.add_button(label="Open Targets", tag=self.TAG_BACKUP_OPEN_TARGET_BUTTON, callback=self._on_open_backup_target)

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_text("Backup source:")
                dpg.add_input_text(
                    tag=self.TAG_BACKUP_SOURCE,
                    width=360,
                    default_value=self.config.backup.source_path,
                    hint="Folder to back up..."
                )
                dpg.add_button(label="Browse...", callback=self._on_backup_source_browse)

            dpg.add_spacer(height=5)
            dpg.add_text("Backup targets:")
            with dpg.child_window(height=80, border=True):
                with dpg.group(tag=self.TAG_BACKUP_TARGETS_GROUP):
                    dpg.add_text("No drives registered.")

            dpg.add_spacer(height=5)
            dpg.add_text("Exclude patterns (one per line):")
            dpg.add_input_text(
                tag=self.TAG_BACKUP_EXCLUDES,
                multiline=True,
                width=-1,
                height=70,
                default_value="\n".join(self.config.backup.exclude_patterns),
            )
            dpg.add_button(label="Analyze Exclusions", callback=self._on_analyze_exclusions)

            dpg.add_spacer(height=5)
            dpg.add_text("No redundancy report yet.", tag=self.TAG_REDUNDANCY_SUMMARY)

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
                dpg.add_text("Backup Progress", color=(150, 200, 255))
                dpg.add_text("Status: Idle", tag=self.TAG_BACKUP_PROGRESS_TEXT)
                dpg.add_progress_bar(tag=self.TAG_BACKUP_PROGRESS_BAR, default_value=0.0, width=-1)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Pause", tag=self.TAG_BACKUP_PAUSE_BUTTON, callback=self._on_backup_pause)
                    dpg.add_button(label="Cancel", tag=self.TAG_BACKUP_CANCEL_BUTTON, callback=self._on_backup_cancel)

        # Create add drive dialog
        self._create_add_drive_dialog()
        self._create_backup_source_dialog()

        # Initial refresh
        self._refresh_drive_list()
        self._refresh_backup_targets()
        self._refresh_resume_button()
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

    def _refresh_drive_list(self) -> None:
        """Refresh the drive list table."""
        # Clear existing rows
        children = dpg.get_item_children(self.TAG_DRIVE_LIST, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        # Get all drives
        drives = self.drive_manager.get_all_drives()
        self._drive_label_map = {drive.label: drive.id for drive in drives}

        if not drives:
            with dpg.table_row(parent=self.TAG_DRIVE_LIST):
                dpg.add_text("")
                dpg.add_text("No drives registered.")
                dpg.add_text("Click 'Add Drive' to register a drive or network share.")
            self._refresh_resume_button()
            return

        # Add rows for each drive
        for drive in drives:
            status = self.drive_manager.get_drive_status(drive.id)
            space = self.drive_manager.get_space_info(drive.path) if status == DriveStatus.CONNECTED else None

            with dpg.table_row(parent=self.TAG_DRIVE_LIST):
                # Selection checkbox
                dpg.add_checkbox(
                    callback=lambda s, a, u: self._on_drive_selected(u),
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

    def _on_drive_selected(self, drive_id: str) -> None:
        """Handle drive selection."""
        self._selected_drive_id = drive_id
        self._update_drive_details(drive_id)
        self._refresh_resume_button()

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
            logger.warning("No path provided")
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
            # TODO: Show error dialog

    def _on_add_drive_cancel(self) -> None:
        """Handle add drive cancel."""
        dpg.hide_item(self.TAG_ADD_DIALOG)

    def _on_remove_drive_click(self) -> None:
        """Handle remove drive button click."""
        if not self._selected_drive_id:
            logger.warning("No drive selected")
            return

        # TODO: Add confirmation dialog
        self.drive_manager.remove_drive(self._selected_drive_id)
        self._selected_drive_id = None
        self._refresh_drive_list()

    def _on_scan_click(self, mode: ScanMode) -> None:
        """Handle scan button click."""
        if not self._selected_drive_id:
            logger.warning("No drive selected")
            return

        if self._scan_thread and self._scan_thread.is_alive():
            logger.warning("Scan already in progress")
            return

        drive = self.drive_manager.get_drive(self._selected_drive_id)
        if not drive:
            logger.warning("Drive not found")
            return

        self.drive_manager.db.clear_scan_state(drive.id)
        self._resume_state = None
        self._start_scan(drive, mode, resume_state=None)

    def _on_resume_scan_click(self) -> None:
        """Handle resume scan click."""
        if not self._selected_drive_id:
            logger.warning("No drive selected")
            return

        if self._scan_thread and self._scan_thread.is_alive():
            logger.warning("Scan already in progress")
            return

        drive = self.drive_manager.get_drive(self._selected_drive_id)
        if not drive:
            logger.warning("Drive not found")
            return

        resume_state = self.drive_manager.db.get_scan_state(drive.id)
        if not resume_state:
            logger.warning("No saved scan state")
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
        self._refresh_drive_list()

    def _run_scan(self, drive: Drive, mode: ScanMode, resume_state: Optional[dict]) -> None:
        """Run scan in background thread."""
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

        except Exception as e:
            logger.error(f"Scan error: {e}")
        finally:
            self._scanner = None
            self._current_scan_drive = None
            self._resume_state = None

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

    def _run_hash(self, drive_id: str) -> None:
        """Run hashing after scan completes."""
        try:
            self._hasher = Hasher(progress_callback=self._on_hash_progress)
            result = self._hasher.hash_files(drive_id)

            logger.info(f"Hashing complete: {result.files_hashed} files, "
                       f"{result.exact_duplicates} duplicates found")

        except Exception as e:
            logger.error(f"Hash error: {e}")
        finally:
            self._hasher = None
            if self.on_status_update:
                self.on_status_update("Hashing complete.")

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
        self._refresh_resume_button()

    def _refresh_resume_button(self) -> None:
        """Enable resume scan button if a persisted scan state exists."""
        enabled = False
        if self._selected_drive_id:
            state = self.drive_manager.db.get_scan_state(self._selected_drive_id)
            enabled = bool(state)
            self._resume_state = state
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
            logger.warning("No backup source selected")
            return

        targets = self._get_selected_targets()
        if not targets:
            logger.warning("No backup targets selected")
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
        except Exception as e:
            logger.error(f"Failed to export backup plan: {e}")

    def _on_open_backup_target(self) -> None:
        """Open selected backup target folders."""
        for drive_id in self._get_selected_targets():
            drive = self.drive_manager.get_drive(drive_id)
            if not drive:
                continue
            try:
                os.startfile(drive.path)
            except Exception:
                logger.warning("Failed to open backup target path")

    def _on_backup_source_browse(self) -> None:
        """Browse for backup source."""
        dpg.show_item("backup_source_dialog")

    def _on_backup_source_selected(self, sender, app_data) -> None:
        """Handle backup source selection."""
        path = app_data.get("file_path_name")
        if path:
            dpg.set_value(self.TAG_BACKUP_SOURCE, path)

    def _on_analyze_exclusions(self) -> None:
        """Analyze exclusion patterns and show impact."""
        source_path = dpg.get_value(self.TAG_BACKUP_SOURCE).strip().strip('"')
        if not source_path:
            logger.warning("No backup source selected")
            return

        exclude_text = dpg.get_value(self.TAG_BACKUP_EXCLUDES).strip()
        patterns = [line.strip() for line in exclude_text.splitlines() if line.strip()]
        candidates = self.redundancy_checker.get_exclusion_candidates(source_path, patterns)
        self._populate_exclusion_table(candidates)

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

    def cleanup(self) -> None:
        """Clean up resources."""
        if self._scanner:
            self._scanner.cancel()
        if self._hasher:
            self._hasher.cancel()
        if self._scan_thread:
            self._scan_thread.join(timeout=5)
        self.drive_manager.stop_monitoring()

    def _on_drive_status_change(self, drive_id: str, status: DriveStatus) -> None:
        """Handle drive status changes for auto-sync."""
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
