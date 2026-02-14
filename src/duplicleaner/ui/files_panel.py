"""Files Panel for DupliCleaner.

Dear PyGui UI component for browsing files and folders in scanned drives.
"""

import hashlib
import os
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

import dearpygui.dearpygui as dpg

try:
    import numpy as np
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from duplicleaner.db.database import get_database
from duplicleaner.db.models import Face, FileRecord, Person
from duplicleaner.drives.manager import DriveManager
from duplicleaner.ui.theme import get_accent_color, get_status_color, get_text_color
from duplicleaner.ui.tooltips import add_tooltip
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


def _render_pdf_page(pdf_path: str, page_num: int = 0, zoom: float = 2.0) -> "Image.Image | None":
    """Render a single PDF page to a PIL Image. Returns None if PyMuPDF unavailable."""
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(pdf_path)
        if page_num >= len(doc):
            doc.close()
            return None
        page = doc[page_num]
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        mode = "L" if pix.n == 1 else "RGB"
        img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        doc.close()
        return img
    except Exception:
        return None


def _get_pdf_page_count(pdf_path: str) -> int:
    """Get the number of pages in a PDF. Returns 0 if unavailable."""
    try:
        import fitz
        doc = fitz.open(pdf_path)
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 0


class FilesPanel:
    """UI panel for browsing scanned files and folders."""

    # Tag constants
    TAG_PANEL = "files_panel"
    TAG_TREE = "files_tree"
    TAG_FILE_TABLE = "files_file_table"
    TAG_DETAILS_GROUP = "files_details_group"
    TAG_DETAILS_PATH = "files_details_path"
    TAG_DETAILS_SIZE = "files_details_size"
    TAG_DETAILS_DATE = "files_details_date"
    TAG_DETAILS_TYPE = "files_details_type"
    TAG_DETAILS_PREVIEW = "files_details_preview"
    TAG_DETAILS_PEOPLE = "files_details_people"
    TAG_DETAILS_SUMMARY = "files_details_summary"
    TAG_DETAILS_SUMMARY_MODEL = "files_details_summary_model"
    TAG_TEXTURE_REGISTRY = "files_texture_registry"
    TAG_BTN_OPEN = "files_btn_open"
    TAG_BTN_SUMMARIZE = "files_btn_summarize"
    TAG_BTN_DETECT_FACES = "files_btn_detect_faces"
    TAG_BTN_EXTRACT_PAGES = "files_btn_extract_pages"
    TAG_BTN_REFRESH = "files_btn_refresh"
    TAG_BTN_FOLDER_DETECT_FACES = "files_btn_folder_detect_faces"
    TAG_BTN_FOLDER_SUMMARIZE = "files_btn_folder_summarize"
    TAG_BTN_FOLDER_UNREDACT = "files_btn_folder_unredact"
    TAG_FOLDER_PROGRESS = "files_folder_progress"
    TAG_CURRENT_PATH = "files_current_path"
    TAG_FILE_COUNT = "files_file_count"
    TAG_PEOPLE_CONTAINER = "files_people_container"
    TAG_ASSIGN_DIALOG = "files_assign_dialog"
    TAG_ASSIGN_LIST = "files_assign_list"
    TAG_ASSIGN_NAME_INPUT = "files_assign_name_input"
    TAG_ASSIGN_BIRTH_YEAR = "files_assign_birth_year"
    TAG_ASSIGN_AGE_CHECK = "files_assign_age_check"
    TAG_ASSIGN_FACE_PREVIEW = "files_assign_face_preview"
    TAG_KEY_HANDLER = "files_key_handler"
    TAG_CONTEXT_MENU = "files_context_menu"
    TAG_VIEW_MODE_LIST = "files_view_mode_list"
    TAG_VIEW_MODE_THUMBS = "files_view_mode_thumbs"
    TAG_THUMB_SIZE_COMBO = "files_thumb_size_combo"
    TAG_THUMBNAIL_GRID = "files_thumbnail_grid"
    TAG_BTN_WRITE_META = "files_btn_write_meta"
    TAG_BTN_PREVIEW_META = "files_btn_preview_meta"
    TAG_META_PREVIEW_DIALOG = "files_meta_preview_dialog"
    TAG_META_PREVIEW_CONTENT = "files_meta_preview_content"

    # Image file extensions for preview
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic', '.heif'}

    # Texture/preview settings
    PREVIEW_SIZE = 200
    MAX_TEXTURE_CACHE = 30
    MAX_TEXTURE_CACHE_THUMBS = 120

    # Thumbnail size presets: label -> pixel size
    THUMB_SIZE_PRESETS = {
        "Small (48)": 48,
        "Medium (96)": 96,
        "Large (128)": 128,
        "Extra Large (256)": 256,
    }

    def __init__(
        self,
        parent: int | str,
        drive_manager: DriveManager | None = None,
        on_status_update: Callable[[str], None] | None = None,
    ):
        """Initialize the files panel.

        Args:
            parent: Parent window/container tag
            drive_manager: DriveManager instance
            on_status_update: Callback for status messages
        """
        self.parent = parent
        self.db = get_database()
        self.drive_manager = drive_manager or DriveManager()
        self.on_status_update = on_status_update

        # Current state
        self._current_folder_path: str | None = None
        self._selected_file_id: int | None = None
        self._selected_row_index: int = -1
        self._folder_files: list[FileRecord] = []

        # Tree node tracking for lazy loading
        self._populated_nodes: set[str] = set()
        self._node_paths: dict[str, str] = {}

        # Texture cache for image previews
        self._texture_cache: dict[str, str] = {}
        self._texture_lru: list[str] = []
        self._texture_counter = 0

        # Face thumbnail state
        self._face_textures_cache: dict[str, str] = {}
        self._current_faces: list[Face] = []
        self._assign_face_id: int | None = None
        self._assign_person_map: dict[str, int] = {}  # listbox label -> person_id

        # Folder-level operation state
        self._folder_operation_thread: threading.Thread | None = None
        self._folder_cancel_event = threading.Event()

        # PDF preview state
        self._pdf_current_page: int = 0
        self._pdf_page_count: int = 0
        self._pdf_current_path: str = ""
        self._pdf_extracted_pages: list[tuple[int, int]] = []  # (page_number, extracted_file_id)

        # Right-click context menu state
        self._row_handler_registries: list[int | str] = []
        self._context_menu_shown = False
        self._context_menu_open_time = 0.0

        # Thumbnail grid view state
        self._view_mode: str = "list"  # "list" or "thumbnails"
        self._thumbnail_size: int = 96
        self._thumb_grid_handler_registries: list[int | str] = []

        self._create_ui()
        self._create_assign_dialog()
        self._create_meta_preview_dialog()
        self._refresh_tree()

    def _create_ui(self) -> None:
        """Create the UI layout."""
        # Texture registry for image previews
        with dpg.texture_registry(tag=self.TAG_TEXTURE_REGISTRY):
            pass

        with dpg.group(tag=self.TAG_PANEL, parent=self.parent):
            # Current path display and header combined
            with dpg.group(horizontal=True):
                dpg.add_text("Files Browser", color=get_accent_color())
                dpg.add_spacer(width=20)
                dpg.add_text("Current folder:")
                dpg.add_text("(select a folder)", tag=self.TAG_CURRENT_PATH, color=get_text_color("secondary"))
                dpg.add_spacer(width=20)
                dpg.add_button(
                    label="Refresh",
                    tag=self.TAG_BTN_REFRESH,
                    callback=self._on_refresh_click,
                    small=True
                )

            dpg.add_spacer(height=3)

            # Main layout: Tree on left, file list on right
            with dpg.group(horizontal=True):
                # Left panel: Folder tree
                with dpg.child_window(width=250, height=200, border=True):
                    with dpg.child_window(tag=self.TAG_TREE, border=False, height=-1):
                        dpg.add_text("Loading...", color=get_text_color("disabled"))

                dpg.add_spacer(width=5)

                # Right panel: File list
                with dpg.child_window(width=-1, height=200, border=False):
                    # File list header
                    with dpg.group(horizontal=True):
                        dpg.add_text("Files", color=get_accent_color())
                        dpg.add_spacer(width=10)
                        dpg.add_text("0 files", tag=self.TAG_FILE_COUNT, color=get_text_color("disabled"))
                        dpg.add_spacer(width=20)
                        dpg.add_button(
                            label="Detect Faces (Folder)",
                            tag=self.TAG_BTN_FOLDER_DETECT_FACES,
                            callback=self._on_folder_detect_faces_click,
                            enabled=False,
                            small=True,
                        )
                        dpg.add_button(
                            label="Summarize (Folder)",
                            tag=self.TAG_BTN_FOLDER_SUMMARIZE,
                            callback=self._on_folder_summarize_click,
                            enabled=False,
                            small=True,
                        )
                        btn = dpg.add_button(
                            label="Unredact PDFs (Folder)",
                            tag=self.TAG_BTN_FOLDER_UNREDACT,
                            callback=self._on_folder_unredact_click,
                            enabled=False,
                            small=True,
                        )
                        add_tooltip(
                            btn,
                            "Use external unredact.py to recover weak redactions in PDFs.\n"
                            "Writes new files with -unredact before the extension.",
                        )
                        dpg.add_text("", tag=self.TAG_FOLDER_PROGRESS, color=get_text_color("secondary"))

                    # View mode toolbar
                    with dpg.group(horizontal=True):
                        dpg.add_text("View:", color=get_text_color("secondary"))
                        dpg.add_button(
                            label="List",
                            tag=self.TAG_VIEW_MODE_LIST,
                            callback=self._on_view_mode_list,
                            small=True,
                        )
                        dpg.add_button(
                            label="Thumbnails",
                            tag=self.TAG_VIEW_MODE_THUMBS,
                            callback=self._on_view_mode_thumbs,
                            small=True,
                        )
                        dpg.add_spacer(width=10)
                        dpg.add_text("Size:", color=get_text_color("secondary"))
                        dpg.add_combo(
                            items=list(self.THUMB_SIZE_PRESETS.keys()),
                            tag=self.TAG_THUMB_SIZE_COMBO,
                            default_value="Medium (96)",
                            callback=self._on_thumb_size_change,
                            width=140,
                            enabled=False,
                        )

                    dpg.add_spacer(height=3)

                    # File table
                    with dpg.table(
                        tag=self.TAG_FILE_TABLE,
                        header_row=True,
                        borders_innerH=True,
                        borders_outerH=True,
                        borders_innerV=True,
                        borders_outerV=True,
                        resizable=True,
                        policy=dpg.mvTable_SizingStretchProp,
                        row_background=True,
                        scrollY=True,
                        height=-1,
                        callback=self._on_file_table_click,
                    ):
                        dpg.add_table_column(label="Name", init_width_or_weight=200)
                        dpg.add_table_column(label="Size", init_width_or_weight=80)
                        dpg.add_table_column(label="Modified", init_width_or_weight=120)
                        dpg.add_table_column(label="Type", init_width_or_weight=60)
                        dpg.add_table_column(label="Summary", init_width_or_weight=60)

                    # Thumbnail grid (hidden by default, shown when view mode = thumbnails)
                    with dpg.child_window(
                        tag=self.TAG_THUMBNAIL_GRID,
                        show=False,
                        border=False,
                        height=-1,
                        horizontal_scrollbar=True,
                    ):
                        pass

            dpg.add_spacer(height=3)

            # File details section
            with dpg.group(tag=self.TAG_DETAILS_GROUP):
                dpg.add_separator()

                with dpg.group(horizontal=True):
                    dpg.add_text("Path:")
                    dpg.add_text("(select a file)", tag=self.TAG_DETAILS_PATH, color=get_text_color("secondary"))

                with dpg.group(horizontal=True):
                    dpg.add_text("Size:")
                    dpg.add_text("", tag=self.TAG_DETAILS_SIZE, color=get_text_color("secondary"))
                    dpg.add_spacer(width=20)
                    dpg.add_text("Modified:")
                    dpg.add_text("", tag=self.TAG_DETAILS_DATE, color=get_text_color("secondary"))
                    dpg.add_spacer(width=20)
                    dpg.add_text("Type:")
                    dpg.add_text("", tag=self.TAG_DETAILS_TYPE, color=get_text_color("secondary"))
                    dpg.add_spacer(width=30)
                    dpg.add_button(
                        label="Open File",
                        tag=self.TAG_BTN_OPEN,
                        callback=self._on_open_click,
                        enabled=False,
                        small=True,
                    )
                    dpg.add_button(
                        label="Generate Summary",
                        tag=self.TAG_BTN_SUMMARIZE,
                        callback=self._on_summarize_click,
                        enabled=False,
                        small=True,
                    )
                    dpg.add_button(
                        label="Detect Faces",
                        tag=self.TAG_BTN_DETECT_FACES,
                        callback=self._on_detect_faces_click,
                        enabled=False,
                        small=True,
                    )
                    dpg.add_button(
                        label="Extract Pages",
                        tag=self.TAG_BTN_EXTRACT_PAGES,
                        callback=self._on_extract_pages_click,
                        enabled=False,
                        show=False,
                        small=True,
                    )
                    dpg.add_button(
                        label="Write Metadata",
                        tag=self.TAG_BTN_WRITE_META,
                        callback=self._on_write_metadata_click,
                        enabled=False,
                        small=True,
                    )
                    dpg.add_button(
                        label="Preview Metadata",
                        tag=self.TAG_BTN_PREVIEW_META,
                        callback=self._on_preview_metadata_click,
                        enabled=False,
                        small=True,
                    )

                dpg.add_spacer(height=5)

                # Image preview, people, and summary side by side
                with dpg.group(horizontal=True):
                    # Image preview container
                    with dpg.child_window(
                        tag=self.TAG_DETAILS_PREVIEW,
                        width=210,
                        height=210,
                        border=True,
                        no_scrollbar=True,
                    ):
                        dpg.add_text("No preview", color=get_text_color("disabled"))

                    dpg.add_spacer(width=5)

                    # People list with face thumbnails
                    with dpg.group():
                        dpg.add_text("People:", color=get_accent_color())
                        with dpg.child_window(
                            tag=self.TAG_PEOPLE_CONTAINER,
                            width=-1,
                            height=120,
                            border=False,
                            horizontal_scrollbar=True,
                        ):
                            dpg.add_text(
                                "No faces detected",
                                tag=self.TAG_DETAILS_PEOPLE,
                                color=get_text_color("disabled"),
                            )

                        dpg.add_spacer(height=3)
                        dpg.add_text("AI Summary:", color=get_accent_color())
                        dpg.add_input_text(
                            tag=self.TAG_DETAILS_SUMMARY,
                            multiline=True,
                            readonly=True,
                            height=50,
                            width=-1,
                            default_value="No summary available"
                        )
                        dpg.add_text("", tag=self.TAG_DETAILS_SUMMARY_MODEL, color=get_text_color("disabled"))

        # Key/scroll handler for file list navigation
        with dpg.handler_registry(tag=self.TAG_KEY_HANDLER):
            dpg.add_key_press_handler(key=dpg.mvKey_Up, callback=self._on_key_up)
            dpg.add_key_press_handler(key=dpg.mvKey_Down, callback=self._on_key_down)
            dpg.add_mouse_wheel_handler(callback=self._on_mouse_wheel)
            dpg.add_mouse_click_handler(callback=self._on_dismiss_context_menu)

        # Right-click context menu for file list
        with dpg.window(
            tag=self.TAG_CONTEXT_MENU,
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
            dpg.add_selectable(label="Generate Summary", callback=self._ctx_summarize)
            dpg.add_selectable(label="Detect Faces", callback=self._ctx_detect_faces)
            dpg.add_separator()
            dpg.add_selectable(label="Copy Path", callback=self._ctx_copy_path)

    def _on_key_up(self, sender, app_data) -> None:
        """Navigate to previous file in the list."""
        if not dpg.is_item_visible(self.TAG_FILE_TABLE):
            return
        self._navigate_file(-1)

    def _on_key_down(self, sender, app_data) -> None:
        """Navigate to next file in the list."""
        if not dpg.is_item_visible(self.TAG_FILE_TABLE):
            return
        self._navigate_file(1)

    def _on_mouse_wheel(self, sender, app_data) -> None:
        """Navigate files on scroll wheel when hovering the file table."""
        try:
            if not dpg.is_item_hovered(self.TAG_FILE_TABLE):
                return
        except (KeyError, SystemError):
            return
        # app_data is scroll delta: positive = up, negative = down
        if app_data > 0:
            self._navigate_file(-1)
        elif app_data < 0:
            self._navigate_file(1)

    def _navigate_file(self, direction: int) -> None:
        """Navigate to a file by offset from current selection.

        Args:
            direction: -1 for previous, +1 for next
        """
        if not self._folder_files:
            return

        new_index = self._selected_row_index + direction
        if new_index < 0 or new_index >= len(self._folder_files):
            return

        self._selected_row_index = new_index
        file_record = self._folder_files[new_index]
        if file_record.id:
            self._display_file_details(file_record.id)

            # Update selectable highlight in the table
            children = dpg.get_item_children(self.TAG_FILE_TABLE, slot=1)
            if children:
                for i, row_tag in enumerate(children):
                    row_children = dpg.get_item_children(row_tag, slot=1)
                    if row_children:
                        dpg.set_value(row_children[0], i == new_index)

    def _refresh_tree(self) -> None:
        """Refresh the folder tree with scanned drives."""
        # Reset lazy-loading state
        self._populated_nodes.clear()
        self._node_paths.clear()

        # Clear existing tree
        children = dpg.get_item_children(self.TAG_TREE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        # Get all drives
        drives = self.drive_manager.get_all_drives()
        if not drives:
            dpg.add_text(
                "No drives scanned yet.\nGo to Drives tab to scan folders.",
                parent=self.TAG_TREE,
                color=get_text_color("disabled")
            )
            return

        # Build tree for each drive
        for drive in drives:
            self._add_drive_node(drive.path, drive.label)

    def _add_drive_node(self, drive_path: str, drive_label: str) -> None:
        """Add a drive node to the tree."""
        # Sanitize path for tag (remove invalid characters)
        path_hash = hashlib.md5(drive_path.encode()).hexdigest()[:8]
        node_tag = f"files_tree_drive_{path_hash}"

        # Don't recreate if already exists
        if dpg.does_item_exist(node_tag):
            return

        # Track path for this node
        self._node_paths[node_tag] = drive_path

        with dpg.tree_node(
            label=f"  {drive_label}",
            parent=self.TAG_TREE,
            tag=node_tag,
            selectable=True,
            default_open=False,
        ):
            # Add subdirectories (first level)
            self._add_subdirectories(drive_path, node_tag)

        # Mark as populated since we loaded first-level children
        self._populated_nodes.add(node_tag)

        # Set up click and expand callbacks
        def make_click_handler(path):
            return lambda: self._on_tree_node_click(path)

        def make_expand_handler(tag):
            return lambda s, a: self._on_tree_node_expand(tag)

        with dpg.item_handler_registry() as handler:
            dpg.add_item_clicked_handler(callback=make_click_handler(drive_path))
            dpg.add_item_toggled_open_handler(callback=make_expand_handler(node_tag))
        dpg.bind_item_handler_registry(node_tag, handler)

    def _add_subdirectories(self, parent_path: str, parent_node_tag: str) -> None:
        """Add subdirectories under a parent node."""
        try:
            subdirs = self._get_subdirectories(parent_path)

            if not subdirs:
                dpg.add_text("(no subfolders)", parent=parent_node_tag, color=get_text_color("disabled"))
                return

            for subdir in subdirs[:50]:  # Max 50 subdirs per level
                subdir_name = os.path.basename(subdir)
                path_hash = hashlib.md5(subdir.encode()).hexdigest()[:8]
                subnode_tag = f"files_tree_subdir_{path_hash}"

                if dpg.does_item_exist(subnode_tag):
                    continue

                # Track path for lazy loading
                self._node_paths[subnode_tag] = subdir

                with dpg.tree_node(
                    label=f"  {subdir_name}",
                    parent=parent_node_tag,
                    tag=subnode_tag,
                    selectable=True,
                    default_open=False,
                ):
                    # Placeholder - replaced on expand
                    dpg.add_text("...", color=get_text_color("disabled"))

                # Click loads files, expand loads children
                def make_click_handler(path):
                    return lambda: self._on_tree_node_click(path)

                def make_expand_handler(tag):
                    return lambda s, a: self._on_tree_node_expand(tag)

                with dpg.item_handler_registry() as handler:
                    dpg.add_item_clicked_handler(callback=make_click_handler(subdir))
                    dpg.add_item_toggled_open_handler(callback=make_expand_handler(subnode_tag))
                dpg.bind_item_handler_registry(subnode_tag, handler)

        except Exception as exc:
            logger.error(f"Failed to add subdirectories for {parent_path}: {exc}")

    def _get_subdirectories(self, parent_path: str) -> list[str]:
        """Get list of subdirectories from database."""
        normalized_parent = os.path.normpath(parent_path).replace("\\", "/")

        query = """
            SELECT DISTINCT SUBSTR(
                REPLACE(path, '\\', '/'),
                1,
                INSTR(SUBSTR(REPLACE(path, '\\', '/'), LENGTH(?) + 2), '/') + LENGTH(?) + 1
            ) as subdir
            FROM files
            WHERE REPLACE(path, '\\', '/') LIKE ?
              AND LENGTH(REPLACE(path, '\\', '/')) > LENGTH(?)
            ORDER BY subdir
        """

        params = [
            normalized_parent,
            normalized_parent,
            f"{normalized_parent}/%",
            normalized_parent
        ]

        with self.db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            subdirs = [row[0].rstrip('/') for row in rows if row[0]]
            # Filter out duplicates and the parent itself
            unique_subdirs = []
            seen = set()
            for subdir in subdirs:
                if subdir and subdir != normalized_parent and subdir not in seen:
                    unique_subdirs.append(subdir.replace("/", "\\"))
                    seen.add(subdir)
            return unique_subdirs

    def _on_tree_node_expand(self, node_tag: str) -> None:
        """Handle tree node expand - lazy load children."""
        if node_tag in self._populated_nodes:
            return

        folder_path = self._node_paths.get(node_tag)
        if not folder_path:
            return

        self._populated_nodes.add(node_tag)

        # Remove placeholder children ("..." text)
        children = dpg.get_item_children(node_tag, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        # Load real subdirectories
        self._add_subdirectories(folder_path, node_tag)

    def _on_tree_node_click(self, folder_path: str) -> None:
        """Handle tree node click - load files in folder."""
        self._current_folder_path = folder_path
        dpg.set_value(self.TAG_CURRENT_PATH, folder_path)
        dpg.configure_item(self.TAG_BTN_FOLDER_UNREDACT, enabled=False)
        self._load_folder_files(folder_path)
        # Enable folder-level action buttons
        dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=True)
        dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=True)
        dpg.set_value(self.TAG_FOLDER_PROGRESS, "")

    def _load_folder_files(self, folder_path: str) -> None:
        """Load and display files in the selected folder."""
        # Clean up old row handler registries
        for hr in self._row_handler_registries:
            try:
                if dpg.does_item_exist(hr):
                    dpg.delete_item(hr)
            except Exception:
                pass
        self._row_handler_registries.clear()

        # Clean up old thumbnail grid handler registries
        for hr in self._thumb_grid_handler_registries:
            try:
                if dpg.does_item_exist(hr):
                    dpg.delete_item(hr)
            except Exception:
                pass
        self._thumb_grid_handler_registries.clear()

        # Clear existing table rows
        children = dpg.get_item_children(self.TAG_FILE_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        # Clear existing thumbnail grid children
        grid_children = dpg.get_item_children(self.TAG_THUMBNAIL_GRID, slot=1)
        if grid_children:
            for child in grid_children:
                dpg.delete_item(child)

        # Validate folder_path
        if not folder_path or not isinstance(folder_path, str):
            logger.error(f"Invalid folder_path: {folder_path} (type: {type(folder_path)})")
            return

        # Query files in this folder (not subdirectories)
        # Normalize path and ensure it ends with separator for matching
        normalized_path = os.path.normpath(folder_path).replace("\\", "/")
        if not normalized_path.endswith("/"):
            normalized_path += "/"

        # Get all files that start with this path, but don't have additional subdirectories
        # This finds files directly in folder_path, not in subdirectories
        query = """
            SELECT f.*,
                   CASE WHEN s.file_id IS NOT NULL THEN 1 ELSE 0 END as has_summary
            FROM files f
            LEFT JOIN ai_summaries s ON s.file_id = f.id
            WHERE f.is_deleted = FALSE
              AND REPLACE(f.path, '\\', '/') LIKE ? || '%'
              AND REPLACE(f.path, '\\', '/') NOT LIKE ? || '%/%'
            ORDER BY f.filename
        """

        with self.db.connection() as conn:
            rows = conn.execute(query, [normalized_path, normalized_path]).fetchall()

            # Extract FileRecord fields (exclude has_summary which is not part of the model)
            self._folder_files = []
            for row in rows:
                row_dict = dict(row)
                # Remove the calculated field before creating FileRecord
                row_dict.pop('has_summary', None)
                self._folder_files.append(FileRecord(**row_dict))

        # Update file count
        dpg.set_value(self.TAG_FILE_COUNT, f"{len(self._folder_files)} files")

        # Log for debugging
        if self.on_status_update:
            self.on_status_update(f"Loaded {len(self._folder_files)} files from {folder_path}")

        # Branch by view mode
        if self._view_mode == "thumbnails":
            dpg.configure_item(self.TAG_FILE_TABLE, show=False)
            dpg.configure_item(self.TAG_THUMBNAIL_GRID, show=True)
            self._render_thumbnail_grid()
        else:
            dpg.configure_item(self.TAG_FILE_TABLE, show=True)
            dpg.configure_item(self.TAG_THUMBNAIL_GRID, show=False)
            self._render_file_table(rows)

        if not self._folder_files and self.on_status_update:
            self.on_status_update(f"Folder is empty: {folder_path}")

        self._update_folder_action_buttons()

    def _update_folder_action_buttons(self) -> None:
        """Enable/disable folder action buttons based on availability."""
        has_pdf_targets = any(
            self._is_pdf_unredact_target(fr.path) for fr in self._folder_files
        )
        unredact_ready = self._is_unredact_available() and has_pdf_targets
        dpg.configure_item(self.TAG_BTN_FOLDER_UNREDACT, enabled=unredact_ready)

    @staticmethod
    def _is_pdf_unredact_target(file_path: str) -> bool:
        """Return True if the file is a PDF eligible for unredact."""
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            return False
        return not path.stem.lower().endswith("-unredact")

    @staticmethod
    def _get_unredact_script_path() -> Path | None:
        """Resolve the unredact.py script location."""
        override = os.environ.get("DUPLICLEANER_UNREDACT_PATH", "").strip()
        if override:
            candidate = Path(override)
        else:
            candidate = Path.home() / "unredactFiles" / "src" / "unredact.py"
        return candidate if candidate.exists() else None

    def _is_unredact_available(self) -> bool:
        """Check if unredact tool is available on disk."""
        return self._get_unredact_script_path() is not None

    def _build_unredact_output_path(self, source_path: str) -> Path:
        """Build output path with -unredact suffix before extension."""
        src = Path(source_path)
        return src.with_name(f"{src.stem}-unredact{src.suffix}")

    @staticmethod
    def _span_is_red(span: dict) -> bool:
        """Return True if the span color is close to red."""
        color_val = span.get("color")
        if color_val is None:
            return False
        r = (color_val >> 16) & 0xFF
        g = (color_val >> 8) & 0xFF
        b = color_val & 0xFF
        return r >= 200 and g <= 60 and b <= 60

    def _add_unredact_boxes(self, pdf_path: Path) -> bool:
        """Add thin red boxes around red text spans in a PDF."""
        try:
            import fitz
        except ImportError:
            return False

        try:
            doc = fitz.open(pdf_path)
            changed = False
            for page in doc:
                text_dict = page.get_text("dict")
                shape = page.new_shape()
                page_changed = False
                for block in text_dict.get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            if not span.get("text", "").strip():
                                continue
                            if not self._span_is_red(span):
                                continue
                            bbox = span.get("bbox")
                            if not bbox:
                                continue
                            rect = fitz.Rect(bbox)
                            shape.draw_rect(rect)
                            page_changed = True
                if page_changed:
                    shape.finish(color=(1, 0, 0), width=0.6)
                    shape.commit()
                    changed = True

            if not changed:
                doc.close()
                return False

            fd, tmp_path = tempfile.mkstemp(
                prefix=f"{pdf_path.stem}_boxed_",
                suffix=pdf_path.suffix,
                dir=str(pdf_path.parent),
            )
            os.close(fd)
            doc.save(tmp_path, garbage=3, deflate=False)
            doc.close()
            os.replace(tmp_path, pdf_path)
            return True
        except Exception as exc:
            logger.error("Failed to add redaction boxes to %s: %s", pdf_path, exc)
            return False

    def _run_unredact_tool(self, source_path: str, output_path: Path) -> tuple[bool, str]:
        """Run external unredact tool on a single PDF."""
        script_path = self._get_unredact_script_path()
        if script_path is None:
            return False, "unredact tool not found"
        cmd = [
            sys.executable,
            str(script_path),
            "-i",
            source_path,
            "-o",
            str(output_path.parent),
            "-n",
            output_path.name,
            "--highlight",
            "1",
            "-b",
            "1",
            "--skip-existing",
            "--json",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            json_payload = None
            for line in reversed(result.stdout.splitlines()):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        import json
                        json_payload = json.loads(line)
                        break
                    except Exception:
                        continue

            if json_payload and json_payload.get("results"):
                entry = json_payload["results"][0]
                status = entry.get("status")
                if status == "ok":
                    if output_path.exists():
                        self._add_unredact_boxes(output_path)
                        return True, ""
                    return False, "output not created"
                if status == "skipped_exists":
                    return False, "output exists"
                err = entry.get("error") or "unredact tool failed"
                return False, err

            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip()
                return False, err or "unredact tool failed"
            if not output_path.exists():
                return False, "output not created"
            self._add_unredact_boxes(output_path)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def _render_file_table(self, rows: list) -> None:
        """Populate the file table from query rows."""
        for idx, row_data in enumerate(rows):
            row_dict = dict(row_data)
            has_summary = row_dict.get("has_summary", 0)
            # Remove calculated field
            row_dict.pop('has_summary', None)
            file_record = FileRecord(**row_dict)

            with dpg.table_row(parent=self.TAG_FILE_TABLE):
                # Name - clickable with right-click context menu
                sel_tag = f"files_sel_{file_record.id}"
                dpg.add_selectable(
                    label=file_record.filename,
                    tag=sel_tag,
                    callback=lambda s, a, u: self._on_file_selectable_click(u[0], u[1]),
                    user_data=(file_record.id, idx),
                    span_columns=False,
                )
                with dpg.item_handler_registry() as hr:
                    dpg.add_item_clicked_handler(
                        button=dpg.mvMouseButton_Right,
                        callback=self._on_file_right_click,
                        user_data=(file_record.id, idx),
                    )
                dpg.bind_item_handler_registry(sel_tag, hr)
                self._row_handler_registries.append(hr)

                # Size
                dpg.add_text(self._format_size(file_record.size))

                # Modified date
                date_str = file_record.modified.strftime('%Y-%m-%d %H:%M') if file_record.modified else ""
                dpg.add_text(date_str)

                # Type
                dpg.add_text((file_record.file_type or "").upper())

                # Summary status (has_summary is 1 or 0 from SQL)
                has_summary_bool = bool(has_summary) if has_summary is not None else False
                summary_text = "Y" if has_summary_bool else "N"
                summary_color = get_status_color("success") if has_summary_bool else get_text_color("disabled")
                dpg.add_text(summary_text, color=summary_color)

    def _render_thumbnail_grid(self) -> None:
        """Render files as a thumbnail grid in the grid container."""
        if not self._folder_files:
            dpg.add_text(
                "No files in folder",
                parent=self.TAG_THUMBNAIL_GRID,
                color=get_text_color("disabled"),
            )
            return

        thumb_sz = self._thumbnail_size
        # Cell width: thumbnail + padding + text margin
        cell_width = thumb_sz + 16
        # Estimate available width from the grid container
        try:
            avail_width = dpg.get_item_width(self.TAG_THUMBNAIL_GRID)
            if avail_width and avail_width > 0:
                items_per_row = max(1, avail_width // cell_width)
            else:
                items_per_row = max(1, 600 // cell_width)
        except Exception:
            items_per_row = max(1, 600 // cell_width)

        current_row_group = None
        for idx, file_record in enumerate(self._folder_files):
            # Start a new row group when needed
            if idx % items_per_row == 0:
                current_row_group = dpg.add_group(
                    horizontal=True,
                    parent=self.TAG_THUMBNAIL_GRID,
                )

            # Each thumbnail cell: image + filename
            with dpg.group(parent=current_row_group):
                is_image = self._is_image_file(file_record.path)

                if is_image:
                    texture_tag = self._load_image_texture(file_record.path, size=thumb_sz)
                    if texture_tag:
                        btn_tag = dpg.add_image_button(
                            texture_tag,
                            width=thumb_sz,
                            height=thumb_sz,
                            callback=lambda s, a, u: self._on_file_selectable_click(u[0], u[1]),
                            user_data=(file_record.id, idx),
                        )
                        # Right-click handler
                        with dpg.item_handler_registry() as hr:
                            dpg.add_item_clicked_handler(
                                button=dpg.mvMouseButton_Right,
                                callback=self._on_file_right_click,
                                user_data=(file_record.id, idx),
                            )
                        dpg.bind_item_handler_registry(btn_tag, hr)
                        self._thumb_grid_handler_registries.append(hr)
                    else:
                        self._render_thumb_placeholder(file_record, idx, thumb_sz)
                else:
                    self._render_thumb_placeholder(file_record, idx, thumb_sz)

                # Truncated filename below thumbnail
                max_chars = max(6, thumb_sz // 7)
                name = file_record.filename
                display_name = (name[:max_chars - 2] + "..") if len(name) > max_chars else name
                dpg.add_text(display_name, color=get_text_color("secondary"))
                dpg.add_spacer(width=4)

    def _render_thumb_placeholder(self, file_record: FileRecord, idx: int, thumb_sz: int) -> None:
        """Render a non-image placeholder button for the thumbnail grid."""
        ext = Path(file_record.path).suffix.upper() or "FILE"
        btn_tag = dpg.add_button(
            label=ext,
            width=thumb_sz,
            height=thumb_sz,
            callback=lambda s, a, u: self._on_file_selectable_click(u[0], u[1]),
            user_data=(file_record.id, idx),
        )
        with dpg.item_handler_registry() as hr:
            dpg.add_item_clicked_handler(
                button=dpg.mvMouseButton_Right,
                callback=self._on_file_right_click,
                user_data=(file_record.id, idx),
            )
        dpg.bind_item_handler_registry(btn_tag, hr)
        self._thumb_grid_handler_registries.append(hr)

    def _on_file_selectable_click(self, file_id: int, row_index: int) -> None:
        """Handle click on a file name selectable."""
        self._selected_row_index = row_index
        self._selected_file_id = file_id
        self._display_file_details(file_id)

    def _on_file_table_click(self, sender, app_data) -> None:
        """Handle file table row click."""
        # Get clicked row
        row = app_data
        if row < 0:
            return

        # Get file_id from row user_data
        children = dpg.get_item_children(self.TAG_FILE_TABLE, slot=1)
        if not children or row >= len(children):
            return

        row_tag = children[row]
        file_id = dpg.get_item_user_data(row_tag)

        if file_id:
            self._selected_row_index = row
            self._selected_file_id = file_id
            self._display_file_details(file_id)

    def _is_image_file(self, file_path: str) -> bool:
        """Check if a file is an image based on extension."""
        ext = Path(file_path).suffix.lower()
        return ext in self.IMAGE_EXTENSIONS

    def _load_image_texture(self, file_path: str, size: int | None = None) -> str | None:
        """Load an image file as a Dear PyGui texture.

        Args:
            file_path: Path to image file.
            size: Thumbnail size in pixels. Defaults to PREVIEW_SIZE.

        Returns:
            Texture tag or None if failed.
        """
        if not HAS_PIL or not os.path.exists(file_path):
            return None

        thumb_size = size or self.PREVIEW_SIZE
        cache_key = f"{file_path}_{thumb_size}"
        if cache_key in self._texture_cache:
            if cache_key in self._texture_lru:
                self._texture_lru.remove(cache_key)
            self._texture_lru.append(cache_key)
            return self._texture_cache[cache_key]

        try:
            img = Image.open(file_path)
            img = ImageOps.exif_transpose(img)
            img.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)

            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            width, height = img.size
            data = np.array(img).astype(np.float32) / 255.0
            data = data.flatten().tolist()

            self._texture_counter += 1
            texture_tag = f"files_texture_{self._texture_counter}"

            dpg.add_static_texture(
                width=width,
                height=height,
                default_value=data,
                tag=texture_tag,
                parent=self.TAG_TEXTURE_REGISTRY,
            )

            # Evict oldest if cache is full
            max_cache = self.MAX_TEXTURE_CACHE_THUMBS if self._view_mode == "thumbnails" else self.MAX_TEXTURE_CACHE
            while len(self._texture_cache) >= max_cache and self._texture_lru:
                oldest_key = self._texture_lru.pop(0)
                if oldest_key in self._texture_cache:
                    old_tag = self._texture_cache.pop(oldest_key)
                    try:
                        if dpg.does_item_exist(old_tag):
                            dpg.delete_item(old_tag)
                    except Exception:
                        pass

            self._texture_cache[cache_key] = texture_tag
            self._texture_lru.append(cache_key)
            return texture_tag

        except Exception as e:
            logger.debug(f"Failed to load image texture for {file_path}: {e}")
            return None

    def _update_preview(self, file_path: str) -> None:
        """Update the image preview container for the given file."""
        # Clear existing preview content
        children = dpg.get_item_children(self.TAG_DETAILS_PREVIEW, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        if self._is_image_file(file_path):
            texture_tag = self._load_image_texture(file_path)
            if texture_tag:
                dpg.add_image(texture_tag, parent=self.TAG_DETAILS_PREVIEW)
            else:
                dpg.add_text(
                    "Failed to load preview",
                    parent=self.TAG_DETAILS_PREVIEW,
                    color=get_text_color("disabled"),
                )
        elif file_path.lower().endswith('.pdf'):
            self._show_pdf_preview(file_path)
        else:
            dpg.add_text(
                "No preview available",
                parent=self.TAG_DETAILS_PREVIEW,
                color=get_text_color("disabled"),
            )

    def _show_pdf_preview(self, file_path: str) -> None:
        """Show PDF page preview with navigation controls.

        Prefers pre-extracted JPEG pages when available (fast path).
        Falls back to on-the-fly rendering via PyMuPDF.
        """
        if file_path != self._pdf_current_path:
            self._pdf_current_page = 0
            self._pdf_current_path = file_path
            self._pdf_page_count = _get_pdf_page_count(file_path)
            # Check for pre-extracted pages
            self._pdf_extracted_pages = []
            if self._selected_file_id:
                try:
                    self._pdf_extracted_pages = self.db.get_pdf_extractions(
                        self._selected_file_id
                    )
                except Exception:
                    pass
                if self._pdf_extracted_pages:
                    self._pdf_page_count = len(self._pdf_extracted_pages)

        if self._pdf_page_count == 0:
            dpg.add_text(
                "PDF preview not available (install PyMuPDF)",
                parent=self.TAG_DETAILS_PREVIEW,
                color=get_text_color("disabled"),
            )
            return

        # Try to load from extracted JPEG first
        loaded = False
        if self._pdf_extracted_pages and self._pdf_current_page < len(self._pdf_extracted_pages):
            _page_num, extracted_file_id = self._pdf_extracted_pages[self._pdf_current_page]
            extracted_record = self.db.get_file(extracted_file_id)
            if extracted_record and os.path.exists(extracted_record.path):
                texture_tag = self._load_image_texture(extracted_record.path)
                if texture_tag:
                    dpg.add_image(texture_tag, parent=self.TAG_DETAILS_PREVIEW)
                    loaded = True

        # Fall back to on-the-fly rendering
        if not loaded:
            img = _render_pdf_page(file_path, self._pdf_current_page)
            if img:
                texture_tag = self._create_texture_from_pil(img)
                if texture_tag:
                    dpg.add_image(texture_tag, parent=self.TAG_DETAILS_PREVIEW)
                    loaded = True

        if not loaded:
            dpg.add_text(
                "Failed to render page",
                parent=self.TAG_DETAILS_PREVIEW,
                color=get_text_color("disabled"),
            )

        # Navigation controls
        with dpg.group(horizontal=True, parent=self.TAG_DETAILS_PREVIEW):
            dpg.add_button(
                label="< Prev",
                callback=self._on_pdf_prev_page,
                enabled=self._pdf_current_page > 0,
                small=True,
            )
            dpg.add_text(
                f"Page {self._pdf_current_page + 1} / {self._pdf_page_count}"
            )
            dpg.add_button(
                label="Next >",
                callback=self._on_pdf_next_page,
                enabled=self._pdf_current_page < self._pdf_page_count - 1,
                small=True,
            )

    def _create_texture_from_pil(self, img: "Image.Image") -> str | None:
        """Create a DPG texture from a PIL Image, thumbnailed to PREVIEW_SIZE."""
        if not HAS_PIL:
            return None
        try:
            img.thumbnail(
                (self.PREVIEW_SIZE, self.PREVIEW_SIZE), Image.Resampling.LANCZOS
            )
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            width, height = img.size
            data = np.array(img).astype(np.float32) / 255.0
            data = data.flatten().tolist()

            self._texture_counter += 1
            texture_tag = f"files_texture_{self._texture_counter}"
            dpg.add_static_texture(
                width=width,
                height=height,
                default_value=data,
                tag=texture_tag,
                parent=self.TAG_TEXTURE_REGISTRY,
            )

            # Evict oldest if cache is full
            while len(self._texture_cache) >= self.MAX_TEXTURE_CACHE and self._texture_lru:
                oldest_key = self._texture_lru.pop(0)
                if oldest_key in self._texture_cache:
                    old_tag = self._texture_cache.pop(oldest_key)
                    try:
                        if dpg.does_item_exist(old_tag):
                            dpg.delete_item(old_tag)
                    except Exception:
                        pass

            cache_key = f"pdf_{self._pdf_current_path}_p{self._pdf_current_page}"
            self._texture_cache[cache_key] = texture_tag
            self._texture_lru.append(cache_key)
            return texture_tag
        except Exception as e:
            logger.debug(f"Failed to create texture from PIL image: {e}")
            return None

    def _on_pdf_prev_page(self) -> None:
        """Navigate to previous PDF page."""
        if self._pdf_current_page > 0:
            self._pdf_current_page -= 1
            self._update_preview(self._pdf_current_path)

    def _on_pdf_next_page(self) -> None:
        """Navigate to next PDF page."""
        if self._pdf_current_page < self._pdf_page_count - 1:
            self._pdf_current_page += 1
            self._update_preview(self._pdf_current_path)

    def _on_extract_pages_click(self) -> None:
        """Manually extract PDF pages to persistent JPEGs."""
        if not self._selected_file_id:
            return
        file_record = self.db.get_file(self._selected_file_id)
        if not file_record or not file_record.path.lower().endswith('.pdf'):
            return

        dpg.configure_item(self.TAG_BTN_EXTRACT_PAGES, enabled=False)

        def run_extraction() -> None:
            try:
                from duplicleaner.ai.faces import FaceAnalyzer

                analyzer = FaceAnalyzer(self.db)
                extracted = analyzer._ensure_pdf_extracted(file_record)
                if extracted:
                    if self.on_status_update:
                        self.on_status_update(
                            f"Extracted {len(extracted)} pages from {file_record.filename}"
                        )
                    # Reset preview state so it picks up extracted pages
                    self._pdf_current_path = ""
                    self._update_preview(file_record.path)
                else:
                    if self.on_status_update:
                        self.on_status_update(
                            f"Failed to extract pages from {file_record.filename}",
                            level="error",
                        )
            except Exception as exc:
                logger.error(f"PDF extraction failed: {exc}")
                if self.on_status_update:
                    self.on_status_update(
                        f"PDF extraction failed: {exc}", level="error"
                    )
            finally:
                dpg.configure_item(self.TAG_BTN_EXTRACT_PAGES, enabled=True)

        threading.Thread(target=run_extraction, daemon=True).start()

    def _update_people(self, file_id: int) -> None:
        """Update the people section with face thumbnail cards."""
        # Clear existing children in the container
        children = dpg.get_item_children(self.TAG_PEOPLE_CONTAINER, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        try:
            faces = self.db.get_faces_for_file(file_id)
        except Exception as e:
            logger.debug(f"Failed to get faces for file {file_id}: {e}")
            faces = []

        self._current_faces = faces

        if not faces:
            dpg.add_text(
                "No faces detected",
                parent=self.TAG_PEOPLE_CONTAINER,
                color=get_text_color("disabled"),
            )
            return

        # Get file path for cropping
        file_record = self.db.get_file(file_id)
        if not file_record:
            return

        # Horizontal row of face cards
        with dpg.group(horizontal=True, parent=self.TAG_PEOPLE_CONTAINER):
            for face in faces:
                with dpg.group():
                    # Crop and display face thumbnail
                    tex_tag = self._crop_face_texture(face, file_record.path)
                    if tex_tag:
                        dpg.add_image(tex_tag, width=64, height=64)
                    else:
                        # Fallback placeholder
                        with dpg.drawlist(width=64, height=64):
                            dpg.draw_rectangle(
                                (0, 0), (64, 64),
                                color=(100, 100, 100),
                                fill=(60, 60, 60),
                            )
                            dpg.draw_text(
                                (16, 22), "?",
                                color=(180, 180, 180),
                                size=24,
                            )

                    # Name label
                    if face.person_id:
                        person = self.db.get_person(face.person_id)
                        if person and person.is_hidden:
                            # Skip faces assigned to hidden/ignored persons
                            continue
                        name = (person.name if person and person.name else "Unknown")
                    else:
                        name = "Unknown"

                    dpg.add_text(name, color=get_text_color("secondary"))

                    if name == "Unknown":
                        # Assign and Ignore buttons for unknown faces
                        with dpg.group(horizontal=True):
                            dpg.add_button(
                                label="Assign",
                                callback=self._on_assign_click,
                                user_data=face.id,
                                small=True,
                            )
                            dpg.add_button(
                                label="Ignore",
                                callback=self._on_ignore_click,
                                user_data=face.id,
                                small=True,
                            )
                    else:
                        # Reassign / Wrong buttons for named faces
                        with dpg.group(horizontal=True):
                            dpg.add_button(
                                label="Wrong",
                                callback=self._on_wrong_click,
                                user_data=face.id,
                                small=True,
                            )

                    dpg.add_spacer(width=8)

    def _display_file_details(self, file_id: int) -> None:
        """Display details for selected file."""
        self._selected_file_id = file_id

        file_record = self.db.get_file(file_id)
        if not file_record:
            return

        # Update details fields
        dpg.set_value(self.TAG_DETAILS_PATH, file_record.path)
        dpg.set_value(self.TAG_DETAILS_SIZE, self._format_size(file_record.size))

        date_str = file_record.modified.strftime('%Y-%m-%d %H:%M:%S') if file_record.modified else "Unknown"
        dpg.set_value(self.TAG_DETAILS_DATE, date_str)

        dpg.set_value(self.TAG_DETAILS_TYPE, file_record.file_type or "Unknown")

        # Update image preview
        self._update_preview(file_record.path)

        # Update people list
        self._update_people(file_id)

        # Get and display summary (or transcription for audio files)
        summary = self.db.get_ai_summary(file_id)
        if summary:
            if summary.document_type == "audio":
                # Show transcription for audio files
                summary_text = summary.summary or summary.document_summary or "No transcription text"
                label_prefix = "[Transcription] "
            else:
                summary_text = summary.summary or summary.document_summary or "No summary text"
                label_prefix = ""

            # Include pet names if present
            pets = summary.get_pets_list()
            pet_info = f"\nPets: {', '.join(pets)}" if pets else ""

            dpg.set_value(self.TAG_DETAILS_SUMMARY, label_prefix + summary_text + pet_info)

            model_info = f"Generated by {summary.summary_model}" if summary.summary_model else ""
            if summary.generated_at:
                model_info += f" on {summary.generated_at.strftime('%Y-%m-%d %H:%M')}"
            dpg.set_value(self.TAG_DETAILS_SUMMARY_MODEL, model_info)
        else:
            dpg.set_value(self.TAG_DETAILS_SUMMARY, "No summary available for this file.")
            dpg.set_value(self.TAG_DETAILS_SUMMARY_MODEL, "")

        # Enable action buttons
        dpg.configure_item(self.TAG_BTN_OPEN, enabled=True)
        dpg.configure_item(
            self.TAG_BTN_SUMMARIZE,
            enabled=True,
            label="Regenerate Summary" if summary else "Generate Summary",
        )
        # Enable Detect Faces for image files and PDFs
        is_img = file_record.is_image if hasattr(file_record, "is_image") else self._is_image_file(file_record.path)
        is_pdf = file_record.path.lower().endswith('.pdf')
        dpg.configure_item(self.TAG_BTN_DETECT_FACES, enabled=(is_img or is_pdf))
        # Show Extract Pages button only for PDFs
        dpg.configure_item(self.TAG_BTN_EXTRACT_PAGES, show=is_pdf, enabled=is_pdf)
        # Enable Write Metadata for image files
        dpg.configure_item(self.TAG_BTN_WRITE_META, enabled=is_img)
        dpg.configure_item(self.TAG_BTN_PREVIEW_META, enabled=is_img)

    def _on_open_click(self) -> None:
        """Open selected file in system default application."""
        if not self._selected_file_id:
            return

        file_record = self.db.get_file(self._selected_file_id)
        if not file_record:
            return

        try:
            if os.path.exists(file_record.path):
                os.startfile(file_record.path)
                if self.on_status_update:
                    self.on_status_update(f"Opened: {file_record.filename}")
            else:
                if self.on_status_update:
                    self.on_status_update(f"File not found: {file_record.path}", level="error")
        except Exception as exc:
            logger.error(f"Failed to open file: {exc}")
            if self.on_status_update:
                self.on_status_update(f"Failed to open file: {exc}", level="error")

    def _on_summarize_click(self) -> None:
        """Generate summary for selected file."""
        if not self._selected_file_id:
            return
        file_record = self.db.get_file(self._selected_file_id)
        if not file_record:
            return

        def run_summary() -> None:
            try:
                from duplicleaner.ai.summaries import SummaryEngine

                engine = SummaryEngine(self.db)
                if not engine.is_available():
                    if self.on_status_update:
                        self.on_status_update("Summary provider not available.", level="error")
                    dpg.set_value(self.TAG_DETAILS_SUMMARY, "Summary provider not available.")
                    dpg.set_value(self.TAG_DETAILS_SUMMARY_MODEL, "")
                    dpg.configure_item(self.TAG_BTN_SUMMARIZE, enabled=True)
                    return

                if self.on_status_update:
                    self.on_status_update(f"Generating summary for: {file_record.filename}")

                summary = engine.analyze_file(file_record)
                if summary:
                    if self.on_status_update:
                        self.on_status_update("Summary generated.")
                    self._display_file_details(file_record.id)
                    if self._current_folder_path:
                        self._load_folder_files(self._current_folder_path)
                else:
                    if self.on_status_update:
                        self.on_status_update("Summary generation failed.", level="warning")
                    dpg.set_value(self.TAG_DETAILS_SUMMARY, "Summary generation failed.")
                    dpg.set_value(self.TAG_DETAILS_SUMMARY_MODEL, "")
                    dpg.configure_item(self.TAG_BTN_SUMMARIZE, enabled=True)

            except Exception as exc:
                logger.error(f"Summary generation failed: {exc}")
                if self.on_status_update:
                    self.on_status_update(f"Summary generation failed: {exc}", level="error")
                dpg.set_value(self.TAG_DETAILS_SUMMARY, "Summary generation failed.")
                dpg.set_value(self.TAG_DETAILS_SUMMARY_MODEL, "")
                dpg.configure_item(self.TAG_BTN_SUMMARIZE, enabled=True)

        dpg.set_value(self.TAG_DETAILS_SUMMARY, "Generating summary...")
        dpg.set_value(self.TAG_DETAILS_SUMMARY_MODEL, "")
        dpg.configure_item(self.TAG_BTN_SUMMARIZE, enabled=False)
        threading.Thread(target=run_summary, daemon=True).start()

    def _on_detect_faces_click(self) -> None:
        """Run face detection on the selected file."""
        if not self._selected_file_id:
            return
        file_record = self.db.get_file(self._selected_file_id)
        if not file_record:
            return

        def run_detection() -> None:
            try:
                from duplicleaner.ai.faces import FaceAnalyzer

                analyzer = FaceAnalyzer(self.db)
                if not analyzer.is_available():
                    if self.on_status_update:
                        self.on_status_update("Face detection model not available.", level="error")
                    dpg.configure_item(self.TAG_BTN_DETECT_FACES, enabled=True)
                    return

                if self.on_status_update:
                    self.on_status_update(f"Detecting faces in: {file_record.filename}")

                # Clear previous results so re-detection works
                self.db.delete_faces_for_file(file_record.id)

                faces = analyzer.analyze_file(file_record)
                if faces:
                    # Try to auto-match detected faces to known persons
                    matched, assigned = analyzer.match_and_assign_faces(
                        faces=faces, auto_assign=True,
                    )
                    if assigned:
                        if self.on_status_update:
                            self.on_status_update(
                                f"Found {len(faces)} face(s), recognized {assigned} in {file_record.filename}"
                            )
                    else:
                        if self.on_status_update:
                            self.on_status_update(
                                f"Found {len(faces)} face(s) in {file_record.filename}"
                            )
                else:
                    if self.on_status_update:
                        self.on_status_update(f"No faces found in {file_record.filename}")

                # Refresh the people list (re-read from DB to pick up assignments)
                self._update_people(file_record.id)
                dpg.configure_item(self.TAG_BTN_DETECT_FACES, enabled=True)

            except Exception as exc:
                logger.error(f"Face detection failed: {exc}")
                if self.on_status_update:
                    self.on_status_update(f"Face detection failed: {exc}", level="error")
                dpg.configure_item(self.TAG_BTN_DETECT_FACES, enabled=True)

        dpg.configure_item(self.TAG_BTN_DETECT_FACES, enabled=False)
        # Show detecting message in people container
        children = dpg.get_item_children(self.TAG_PEOPLE_CONTAINER, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)
        dpg.add_text(
            "Detecting faces...",
            parent=self.TAG_PEOPLE_CONTAINER,
            color=get_text_color("secondary"),
        )
        threading.Thread(target=run_detection, daemon=True).start()

    def _on_folder_detect_faces_click(self) -> None:
        """Run face detection on all images in the current folder (recursively)."""
        folder_path = self._current_folder_path
        if not folder_path:
            return

        def run_folder_faces() -> None:
            try:
                from duplicleaner.ai.faces import FaceAnalyzer

                analyzer = FaceAnalyzer(self.db)
                if not analyzer.is_available():
                    if self.on_status_update:
                        self.on_status_update("Face detection model not available.", level="error")
                    dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=True)
                    dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=True)
                    dpg.set_value(self.TAG_FOLDER_PROGRESS, "")
                    return

                logger.info("Folder face detection starting for: %s", folder_path)
                files = self.db.get_image_files_missing_face_analysis_in_directory(folder_path)
                if not files:
                    # All files analyzed -- reset ones with 0 faces so they get rescanned
                    cleared = self.db.clear_face_analysis_no_faces_in_directory(folder_path)
                    if cleared:
                        logger.info(
                            "Cleared face analysis for %d files with 0 faces in %s for rescan",
                            cleared, folder_path,
                        )
                        files = self.db.get_image_files_missing_face_analysis_in_directory(folder_path)
                    if not files:
                        # No new files to scan, but try re-matching unknown faces
                        logger.info("No new files to scan, checking for unassigned faces to re-match")
                        dpg.set_value(self.TAG_FOLDER_PROGRESS, "Re-matching unknown faces...")
                        unassigned = self.db.get_unassigned_faces_in_directory(folder_path)
                        logger.info("Found %d unassigned faces in folder", len(unassigned))
                        if unassigned:
                            if self.on_status_update:
                                self.on_status_update(
                                    f"Re-matching {len(unassigned)} unknown faces against known people..."
                                )
                            _, rematch_assigned = analyzer.match_and_assign_faces(
                                faces=unassigned, auto_assign=True,
                            )
                            if rematch_assigned:
                                logger.info("Re-matched %d previously unknown faces", rematch_assigned)
                                if self.on_status_update:
                                    self.on_status_update(
                                        f"Auto-assigned {rematch_assigned} previously unknown faces"
                                    )
                                dpg.set_value(
                                    self.TAG_FOLDER_PROGRESS,
                                    f"Done: {rematch_assigned} faces matched",
                                )
                                dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=True)
                                dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=True)
                                return
                        msg = (
                            f"All files in this folder already have face analysis. "
                            f"No new files to scan in {folder_path}"
                        )
                        logger.info(msg)
                        if self.on_status_update:
                            self.on_status_update(msg)
                        dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=True)
                        dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=True)
                        dpg.set_value(self.TAG_FOLDER_PROGRESS, "All files already analyzed")
                        return
                    if self.on_status_update:
                        self.on_status_update(
                            f"Rescanning {len(files)} images that previously had no faces detected..."
                        )

                logger.info("Found %d images needing face analysis in %s", len(files), folder_path)
                if self.on_status_update:
                    self.on_status_update(f"Detecting faces in {len(files)} images under {folder_path}...")

                total_faces = 0
                total_assigned = 0
                self._folder_cancel_event.clear()
                for i, file_record in enumerate(files):
                    if self._folder_cancel_event.is_set():
                        logger.info("Folder face detection cancelled at %d/%d", i, len(files))
                        break
                    dpg.set_value(
                        self.TAG_FOLDER_PROGRESS,
                        f"Faces: {i + 1}/{len(files)} - {total_faces} found, {total_assigned} matched",
                    )
                    faces = analyzer.analyze_file(file_record)
                    total_faces += len(faces)
                    if faces:
                        matched, assigned = analyzer.match_and_assign_faces(faces=faces, auto_assign=True)
                        total_assigned += assigned
                        logger.info(
                            "  [%d/%d] %s: %d face(s), %d matched",
                            i + 1, len(files), file_record.filename,
                            len(faces), assigned,
                        )
                    # Periodic status bar update every 10 files
                    if (i + 1) % 10 == 0 and self.on_status_update:
                        self.on_status_update(
                            f"Face detection: {i + 1}/{len(files)} files, "
                            f"{total_faces} faces, {total_assigned} matched..."
                        )

                # Re-match existing unassigned faces in this folder
                dpg.set_value(self.TAG_FOLDER_PROGRESS, "Re-matching unknown faces...")
                logger.info("Looking for unassigned faces in: %s", folder_path)
                unassigned = self.db.get_unassigned_faces_in_directory(folder_path)
                logger.info("Found %d unassigned faces in folder", len(unassigned))
                rematch_assigned = 0
                if unassigned:
                    logger.info(
                        "Re-matching %d unassigned faces in %s against known people",
                        len(unassigned), folder_path,
                    )
                    if self.on_status_update:
                        self.on_status_update(
                            f"Re-matching {len(unassigned)} unknown faces against known people..."
                        )
                    _, rematch_assigned = analyzer.match_and_assign_faces(
                        faces=unassigned, auto_assign=True,
                    )
                    if rematch_assigned:
                        logger.info("Re-matched %d previously unknown faces", rematch_assigned)

                total_assigned += rematch_assigned
                result_msg = (
                    f"Face detection complete: {total_faces} new faces in "
                    f"{len(files)} images, {total_assigned} total matched"
                )
                if rematch_assigned:
                    result_msg += f" ({rematch_assigned} previously unknown)"
                logger.info(result_msg)
                if self.on_status_update:
                    self.on_status_update(result_msg)
                dpg.set_value(
                    self.TAG_FOLDER_PROGRESS,
                    f"Done: {total_faces} faces, {total_assigned} matched",
                )

            except Exception as exc:
                logger.error(f"Folder face detection failed: {exc}", exc_info=True)
                if self.on_status_update:
                    self.on_status_update(f"Folder face detection failed: {exc}", level="error")
                dpg.set_value(self.TAG_FOLDER_PROGRESS, "Error - check log")
            finally:
                dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=True)
                dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=True)
                self._folder_operation_thread = None

        dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=False)
        dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=False)
        dpg.set_value(self.TAG_FOLDER_PROGRESS, "Starting face detection...")
        self._folder_operation_thread = threading.Thread(target=run_folder_faces, daemon=True)
        self._folder_operation_thread.start()

    def _on_folder_summarize_click(self) -> None:
        """Generate summaries for all files in the current folder (recursively)."""
        folder_path = self._current_folder_path
        if not folder_path:
            return

        def run_folder_summaries() -> None:
            try:
                from duplicleaner.ai.summaries import SummaryEngine

                engine = SummaryEngine(self.db)
                if not engine.is_available():
                    if self.on_status_update:
                        self.on_status_update("Summary provider not available.", level="error")
                    dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=True)
                    dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=True)
                    dpg.set_value(self.TAG_FOLDER_PROGRESS, "")
                    return

                files = self.db.get_files_needing_summary_in_directory(folder_path)
                if not files:
                    if self.on_status_update:
                        self.on_status_update(f"No files need summaries in {folder_path}")
                    dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=True)
                    dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=True)
                    dpg.set_value(self.TAG_FOLDER_PROGRESS, "")
                    return

                if self.on_status_update:
                    self.on_status_update(f"Generating summaries for {len(files)} files under {folder_path}...")

                generated = 0
                self._folder_cancel_event.clear()
                for i, file_record in enumerate(files):
                    if self._folder_cancel_event.is_set():
                        break
                    dpg.set_value(
                        self.TAG_FOLDER_PROGRESS,
                        f"Summaries: {i + 1}/{len(files)} ({generated} done)",
                    )
                    if engine.analyze_file(file_record):
                        generated += 1

                if self.on_status_update:
                    self.on_status_update(
                        f"Summary generation complete: {generated}/{len(files)} files"
                    )
                dpg.set_value(self.TAG_FOLDER_PROGRESS, f"Done: {generated} summaries")
                # Refresh file list to show updated summary status
                if self._current_folder_path:
                    self._load_folder_files(self._current_folder_path)

            except Exception as exc:
                logger.error(f"Folder summary generation failed: {exc}")
                if self.on_status_update:
                    self.on_status_update(f"Folder summary failed: {exc}", level="error")
                dpg.set_value(self.TAG_FOLDER_PROGRESS, "")
            finally:
                dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=True)
                dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=True)
                self._folder_operation_thread = None

        dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=False)
        dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=False)
        dpg.set_value(self.TAG_FOLDER_PROGRESS, "Starting summary generation...")
        self._folder_operation_thread = threading.Thread(target=run_folder_summaries, daemon=True)
        self._folder_operation_thread.start()

    def _on_folder_unredact_click(self) -> None:
        """Run the external unredact tool on all PDFs in the current folder."""
        folder_path = self._current_folder_path
        if not folder_path:
            return

        if self._folder_operation_thread and self._folder_operation_thread.is_alive():
            if self.on_status_update:
                self.on_status_update("Another folder operation is already running.", level="warning")
            return

        script_path = self._get_unredact_script_path()
        if script_path is None:
            if self.on_status_update:
                self.on_status_update("Unredact tool not found. Set DUPLICLEANER_UNREDACT_PATH.", level="error")
            dpg.configure_item(self.TAG_BTN_FOLDER_UNREDACT, enabled=False)
            return

        pdf_files = [
            fr for fr in self._folder_files
            if self._is_pdf_unredact_target(fr.path) and os.path.exists(fr.path)
        ]
        if not pdf_files:
            if self.on_status_update:
                self.on_status_update(f"No PDF files to unredact in {folder_path}")
            dpg.set_value(self.TAG_FOLDER_PROGRESS, "")
            dpg.configure_item(self.TAG_BTN_FOLDER_UNREDACT, enabled=False)
            return

        def run_folder_unredact() -> None:
            processed = 0
            skipped = 0
            failed = 0
            try:
                if self.on_status_update:
                    self.on_status_update(f"Unredacting {len(pdf_files)} PDFs in {folder_path}...")
                self._folder_cancel_event.clear()
                for idx, file_record in enumerate(pdf_files):
                    if self._folder_cancel_event.is_set():
                        break
                    source_path = file_record.path
                    output_path = self._build_unredact_output_path(source_path)
                    if output_path.exists():
                        skipped += 1
                    else:
                        ok, err = self._run_unredact_tool(source_path, output_path)
                        if ok:
                            processed += 1
                        else:
                            failed += 1
                            logger.error("Unredact failed for %s: %s", source_path, err)
                    dpg.set_value(
                        self.TAG_FOLDER_PROGRESS,
                        (
                            f"Unredact: {idx + 1}/{len(pdf_files)} "
                            f"(ok: {processed}, skipped: {skipped}, failed: {failed})"
                        ),
                    )

                if self.on_status_update:
                    self.on_status_update(
                        f"Unredact complete: {processed} created, {skipped} skipped, {failed} failed"
                    )
                dpg.set_value(
                    self.TAG_FOLDER_PROGRESS,
                    f"Done: {processed} created, {skipped} skipped, {failed} failed",
                )
                if self._current_folder_path:
                    self._load_folder_files(self._current_folder_path)
            except Exception as exc:
                logger.error("Folder unredact failed: %s", exc)
                if self.on_status_update:
                    self.on_status_update(f"Folder unredact failed: {exc}", level="error")
                dpg.set_value(self.TAG_FOLDER_PROGRESS, "")
            finally:
                dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=True)
                dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=True)
                self._update_folder_action_buttons()
                self._folder_operation_thread = None

        dpg.configure_item(self.TAG_BTN_FOLDER_DETECT_FACES, enabled=False)
        dpg.configure_item(self.TAG_BTN_FOLDER_SUMMARIZE, enabled=False)
        dpg.configure_item(self.TAG_BTN_FOLDER_UNREDACT, enabled=False)
        dpg.set_value(self.TAG_FOLDER_PROGRESS, "Starting unredact...")
        self._folder_operation_thread = threading.Thread(target=run_folder_unredact, daemon=True)
        self._folder_operation_thread.start()

    def _on_refresh_click(self) -> None:
        """Refresh the tree and current folder."""
        self._refresh_tree()
        if self._current_folder_path:
            self._load_folder_files(self._current_folder_path)
        if self.on_status_update:
            self.on_status_update("File browser refreshed")

    # ------------------------------------------------------------------
    # Face thumbnail helpers (adapted from faces_panel)
    # ------------------------------------------------------------------

    @staticmethod
    def _transform_point(
        pt: tuple[float, float],
        orientation: int,
        width: int,
        height: int,
    ) -> tuple[float, float]:
        """Map a point from raw image coords to EXIF-oriented coords."""
        x, y = pt
        if orientation == 1:
            return (x, y)
        if orientation == 2:
            return (width - x, y)
        if orientation == 3:
            return (width - x, height - y)
        if orientation == 4:
            return (x, height - y)
        if orientation == 5:
            return (y, x)
        if orientation == 6:
            return (height - y, x)
        if orientation == 7:
            return (height - y, width - x)
        if orientation == 8:
            return (y, width - x)
        return (x, y)

    @staticmethod
    def _apply_orientation_to_bbox(
        bbox: tuple[int, int, int, int],
        orientation: int,
        width: int,
        height: int,
    ) -> tuple[float, float, float, float] | None:
        """Map a raw bbox into EXIF-oriented image coordinates."""
        x, y, bw, bh = bbox
        corners = [
            (x, y),
            (x + bw, y),
            (x, y + bh),
            (x + bw, y + bh),
        ]
        mapped = [FilesPanel._transform_point(pt, orientation, width, height) for pt in corners]
        xs = [p[0] for p in mapped]
        ys = [p[1] for p in mapped]
        if not xs or not ys:
            return None
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return (min_x, min_y, max_x - min_x, max_y - min_y)

    @staticmethod
    def _square_crop_bounds(
        x: float,
        y: float,
        bw: float,
        bh: float,
        width: int,
        height: int,
        pad: float = 0.35,
    ) -> tuple[int, int, int, int]:
        """Return a square crop (left, top, right, bottom) centered on bbox with padding."""
        cx = x + (bw / 2.0)
        cy = y + (bh / 2.0)
        size = max(bw, bh) * (1.0 + 2.0 * pad)
        size = max(1.0, size)
        half = size / 2.0
        left = cx - half
        top = cy - half
        right = cx + half
        bottom = cy + half

        if left < 0:
            right -= left
            left = 0
        if top < 0:
            bottom -= top
            top = 0
        if right > width:
            left -= (right - width)
            right = width
        if bottom > height:
            top -= (bottom - height)
            bottom = height

        left = max(0, min(left, width))
        top = max(0, min(top, height))
        right = max(left + 1, min(right, width))
        bottom = max(top + 1, min(bottom, height))

        return int(left), int(top), int(right), int(bottom)

    def _crop_face_texture(self, face: Face, image_path: str) -> str | None:
        """Crop a face from an image and create a 64x64 DPG texture.

        Returns texture tag or None on failure.
        """
        if not HAS_PIL or not os.path.exists(image_path):
            return None

        cache_key = f"face_{face.id}"
        if cache_key in self._face_textures_cache:
            tag = self._face_textures_cache[cache_key]
            if dpg.does_item_exist(tag):
                return tag
            # Stale entry
            del self._face_textures_cache[cache_key]

        try:
            if image_path.lower().endswith('.pdf'):
                page_num = face.page_number or 0
                image = _render_pdf_page(image_path, page_num=page_num)
                if image is None:
                    return None
                image = image.convert("RGB")
            else:
                raw_image = Image.open(image_path)
                image = ImageOps.exif_transpose(raw_image).convert("RGB")
            img_w, img_h = image.size

            # OpenCV auto-rotates JPEGs so bboxes are already in oriented coords
            x, y, bw, bh = face.bbox_x, face.bbox_y, face.bbox_w, face.bbox_h
            left, top, right, bottom = self._square_crop_bounds(
                x, y, bw, bh, img_w, img_h,
            )
            if right <= left or bottom <= top:
                return None

            cropped = image.crop((left, top, right, bottom)).resize(
                (64, 64), Image.BILINEAR,
            )
            rgba = cropped.convert("RGBA")
            data = np.asarray(rgba).astype(np.float32) / 255.0

            self._texture_counter += 1
            tex_tag = f"files_face_tex_{self._texture_counter}"
            dpg.add_static_texture(
                64,
                64,
                data.flatten().tolist(),
                tag=tex_tag,
                parent=self.TAG_TEXTURE_REGISTRY,
            )
            self._face_textures_cache[cache_key] = tex_tag
            return tex_tag
        except Exception as exc:
            logger.debug(f"Failed to create face texture for face {face.id}: {exc}")
            return None

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format byte size to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if abs(size_bytes) < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

    # ------------------------------------------------------------------
    # Assign dialog
    # ------------------------------------------------------------------

    def _create_assign_dialog(self) -> None:
        """Create the modal dialog for assigning unknown faces to persons."""
        with dpg.window(
            label="Assign Face",
            tag=self.TAG_ASSIGN_DIALOG,
            modal=True,
            show=False,
            width=800,
            height=380,
            no_resize=True,
            pos=[120, 100],
        ):
            with dpg.group(horizontal=True):
                # Face thumbnail preview
                with dpg.group():
                    dpg.add_text("Face:", color=get_accent_color())
                    with dpg.child_window(
                        tag=self.TAG_ASSIGN_FACE_PREVIEW,
                        width=100,
                        height=100,
                        border=True,
                        no_scrollbar=True,
                    ):
                        pass
                    dpg.add_spacer(height=10)
                    dpg.add_button(
                        label="Cancel",
                        callback=self._on_cancel_assign,
                        width=100,
                    )

                dpg.add_spacer(width=10)

                # Create New Person
                with dpg.child_window(width=300, height=300, border=True):
                    dpg.add_text("Create New Person", color=get_accent_color())
                    dpg.add_spacer(height=6)
                    dpg.add_text("Name:")
                    dpg.add_input_text(tag=self.TAG_ASSIGN_NAME_INPUT, width=260)
                    dpg.add_spacer(height=6)
                    dpg.add_checkbox(
                        label="Enable age tracking",
                        tag=self.TAG_ASSIGN_AGE_CHECK,
                    )
                    dpg.add_text("Birth year (approximate):")
                    dpg.add_input_int(
                        tag=self.TAG_ASSIGN_BIRTH_YEAR,
                        default_value=2000,
                        width=100,
                    )
                    dpg.add_spacer(height=8)
                    dpg.add_button(
                        label="Create & Assign",
                        callback=self._on_create_and_assign,
                        width=140,
                    )

                dpg.add_spacer(width=10)

                # Assign to Existing (sorted by similarity)
                with dpg.child_window(width=320, height=300, border=True):
                    dpg.add_text("Assign to Existing", color=get_accent_color())
                    dpg.add_spacer(height=6)
                    dpg.add_listbox(
                        tag=self.TAG_ASSIGN_LIST,
                        items=[],
                        num_items=10,
                        width=290,
                    )
                    dpg.add_spacer(height=8)
                    dpg.add_button(
                        label="Assign Selected",
                        callback=self._on_assign_existing,
                        width=140,
                    )

    def _on_assign_click(self, sender, app_data, user_data) -> None:
        """Handle Assign button click -- open the assign dialog sorted by similarity."""
        self._assign_face_id = user_data
        self._assign_person_map.clear()

        # Get the face embedding for similarity scoring
        face_embedding = None
        face = next((f for f in self._current_faces if f.id == user_data), None)
        if face and face.embedding and HAS_PIL:
            try:
                face_embedding = np.frombuffer(face.embedding, dtype=np.float32)
            except Exception:
                pass

        # Build person list sorted by similarity
        persons = self.db.get_all_persons(named_only=True)
        scored: list[tuple[float | None, str, int]] = []

        if face_embedding is not None and np.linalg.norm(face_embedding) > 0:
            try:
                from duplicleaner.ai.faces import FaceAnalyzer
                analyzer = FaceAnalyzer(self.db)
                analyzer.load_person_embeddings()

                for person in persons:
                    if person.id is None or not person.name:
                        continue
                    embeddings = analyzer._person_embeddings.get(person.id, [])
                    if embeddings:
                        best_sim = max(
                            analyzer.compute_similarity(face_embedding, emb)
                            for _stage, emb in embeddings
                        )
                    else:
                        best_sim = None
                    scored.append((best_sim, person.name, person.id))
            except Exception:
                # Fall back to unsorted
                for person in persons:
                    if person.id is not None and person.name:
                        scored.append((None, person.name, person.id))
        else:
            for person in persons:
                if person.id is not None and person.name:
                    scored.append((None, person.name, person.id))

        # Sort: highest similarity first, then alphabetical
        scored.sort(key=lambda item: (-(item[0] or -1.0), item[1].lower()))

        labels = []
        for sim, name, pid in scored:
            label = f"{name} ({sim:.0%})" if sim is not None else name
            labels.append(label)
            self._assign_person_map[label] = pid

        dpg.configure_item(self.TAG_ASSIGN_LIST, items=labels)

        # Populate face thumbnail preview in dialog
        children = dpg.get_item_children(self.TAG_ASSIGN_FACE_PREVIEW, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)
        if face and self._selected_file_id is not None:
            file_record = self.db.get_file(self._selected_file_id)
            if file_record:
                tex_tag = self._crop_face_texture(face, file_record.path)
                if tex_tag:
                    dpg.add_image(tex_tag, width=90, height=90, parent=self.TAG_ASSIGN_FACE_PREVIEW)

        # Reset inputs
        dpg.set_value(self.TAG_ASSIGN_NAME_INPUT, "")
        dpg.set_value(self.TAG_ASSIGN_BIRTH_YEAR, 2000)
        dpg.set_value(self.TAG_ASSIGN_AGE_CHECK, False)

        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=True)

    def _on_create_and_assign(self) -> None:
        """Create a new person and assign the face to them."""
        name = dpg.get_value(self.TAG_ASSIGN_NAME_INPUT).strip()
        if not name:
            if self.on_status_update:
                self.on_status_update("Please enter a name.", level="warning")
            return

        birth_year = None
        if dpg.get_value(self.TAG_ASSIGN_AGE_CHECK):
            birth_year = dpg.get_value(self.TAG_ASSIGN_BIRTH_YEAR)

        person = Person(name=name, birth_year=birth_year)
        person_id = self.db.add_person(person)

        if self._assign_face_id is not None:
            self.db.assign_face_to_person(self._assign_face_id, person_id)

        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=False)

        if self.on_status_update:
            self.on_status_update(f"Created person '{name}' and assigned face.")

        # Refresh the people section
        if self._selected_file_id is not None:
            self._update_people(self._selected_file_id)

    def _on_assign_existing(self) -> None:
        """Assign the face to the selected existing person."""
        selected_label = dpg.get_value(self.TAG_ASSIGN_LIST)
        if not selected_label:
            if self.on_status_update:
                self.on_status_update("Please select a person.", level="warning")
            return

        # Look up person_id from the label map
        person_id = self._assign_person_map.get(selected_label)
        if person_id is None:
            if self.on_status_update:
                self.on_status_update("Person not found.", level="error")
            return

        person = self.db.get_person(person_id)

        if self._assign_face_id is not None:
            self.db.assign_face_to_person(self._assign_face_id, person_id)

        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=False)

        person_name = person.name if person else "Unknown"
        if self.on_status_update:
            self.on_status_update(f"Assigned face to '{person_name}'.")

        # Refresh the people section
        if self._selected_file_id is not None:
            self._update_people(self._selected_file_id)

    def _on_ignore_click(self, sender, app_data, user_data) -> None:
        """Ignore a face -- create a hidden person and assign it."""
        face_id = user_data
        if face_id is None:
            return

        # Use the DB helper to create a hidden person for this single face
        self.db.create_hidden_person_from_cluster([face_id])

        if self.on_status_update:
            self.on_status_update("Face ignored.")

        # Refresh people section to remove the ignored face
        if self._selected_file_id is not None:
            self._update_people(self._selected_file_id)

    def _on_wrong_click(self, sender, app_data, user_data) -> None:
        """Handle Wrong button -- unassign the face and open assign dialog."""
        face_id = user_data
        if face_id is None:
            return

        self.db.unassign_face_from_person(face_id)

        # Refresh so the face now shows as Unknown with Assign/Ignore
        if self._selected_file_id is not None:
            self._update_people(self._selected_file_id)

        # Open the assign dialog for this face
        self._on_assign_click(sender, app_data, face_id)

    def _on_cancel_assign(self) -> None:
        """Close the assign dialog without changes."""
        self._assign_face_id = None
        dpg.configure_item(self.TAG_ASSIGN_DIALOG, show=False)

    # ------------------------------------------------------------------
    # View mode callbacks
    # ------------------------------------------------------------------

    def _on_view_mode_list(self, sender=None, app_data=None) -> None:
        """Switch to list/table view mode."""
        self._view_mode = "list"
        dpg.configure_item(self.TAG_THUMB_SIZE_COMBO, enabled=False)
        if self._current_folder_path:
            self._load_folder_files(self._current_folder_path)

    def _on_view_mode_thumbs(self, sender=None, app_data=None) -> None:
        """Switch to thumbnail grid view mode."""
        self._view_mode = "thumbnails"
        dpg.configure_item(self.TAG_THUMB_SIZE_COMBO, enabled=True)
        if self._current_folder_path:
            self._load_folder_files(self._current_folder_path)

    def _on_thumb_size_change(self, sender=None, app_data=None) -> None:
        """Handle thumbnail size combo change."""
        selected = dpg.get_value(self.TAG_THUMB_SIZE_COMBO)
        new_size = self.THUMB_SIZE_PRESETS.get(selected, 96)
        if new_size != self._thumbnail_size:
            self._thumbnail_size = new_size
            if self._view_mode == "thumbnails" and self._current_folder_path:
                self._load_folder_files(self._current_folder_path)

    # ------------------------------------------------------------------
    # Context menu callbacks
    # ------------------------------------------------------------------

    def _on_file_right_click(self, sender=None, app_data=None, user_data=None) -> None:
        """Show context menu on right-click of a file row."""
        import time

        if user_data:
            file_id, row_idx = user_data
            self._on_file_selectable_click(file_id, row_idx)

        mouse_pos = dpg.get_mouse_pos(local=False)
        dpg.configure_item(
            self.TAG_CONTEXT_MENU,
            show=True,
            pos=[int(mouse_pos[0]), int(mouse_pos[1])],
        )
        self._context_menu_shown = True
        self._context_menu_open_time = time.time()

    def _on_dismiss_context_menu(self, sender=None, app_data=None) -> None:
        """Hide context menu on left-click outside it."""
        import time

        if not self._context_menu_shown:
            return
        # Ignore clicks within a short window after opening (avoids immediate dismiss)
        if time.time() - self._context_menu_open_time < 0.15:
            return
        try:
            if dpg.is_item_hovered(self.TAG_CONTEXT_MENU):
                return
        except (KeyError, SystemError):
            pass
        dpg.configure_item(self.TAG_CONTEXT_MENU, show=False)
        self._context_menu_shown = False

    def _ctx_open_file(self, sender=None, app_data=None) -> None:
        """Context menu: open selected file."""
        dpg.configure_item(self.TAG_CONTEXT_MENU, show=False)
        self._context_menu_shown = False
        self._on_open_click()

    def _ctx_show_in_explorer(self, sender=None, app_data=None) -> None:
        """Context menu: show file in Windows Explorer."""
        dpg.configure_item(self.TAG_CONTEXT_MENU, show=False)
        self._context_menu_shown = False
        if not self._selected_file_id:
            return
        file_record = self.db.get_file(self._selected_file_id)
        if not file_record:
            return
        try:
            if os.path.exists(file_record.path):
                subprocess.Popen(["explorer", "/select,", file_record.path])
            else:
                if self.on_status_update:
                    self.on_status_update(f"File not found: {file_record.path}", level="error")
        except Exception as exc:
            logger.error(f"Failed to open explorer: {exc}")

    def _ctx_summarize(self, sender=None, app_data=None) -> None:
        """Context menu: generate AI summary for selected file."""
        dpg.configure_item(self.TAG_CONTEXT_MENU, show=False)
        self._context_menu_shown = False
        self._on_summarize_click()

    def _ctx_detect_faces(self, sender=None, app_data=None) -> None:
        """Context menu: detect faces in selected file."""
        dpg.configure_item(self.TAG_CONTEXT_MENU, show=False)
        self._context_menu_shown = False
        self._on_detect_faces_click()

    def _ctx_copy_path(self, sender=None, app_data=None) -> None:
        """Context menu: copy file path to clipboard."""
        dpg.configure_item(self.TAG_CONTEXT_MENU, show=False)
        self._context_menu_shown = False
        if not self._selected_file_id:
            return
        file_record = self.db.get_file(self._selected_file_id)
        if not file_record:
            return
        try:
            subprocess.run(["clip"], input=file_record.path.encode(), check=True)
            if self.on_status_update:
                self.on_status_update(f"Copied: {file_record.path}")
        except Exception as exc:
            logger.error(f"Failed to copy path: {exc}")

    # --- Metadata Write ---

    def _create_meta_preview_dialog(self) -> None:
        """Create the metadata preview dialog."""
        with dpg.window(
            tag=self.TAG_META_PREVIEW_DIALOG,
            label="Metadata Preview",
            modal=True,
            show=False,
            width=600,
            height=400,
            no_resize=False,
        ):
            dpg.add_text("Metadata that will be written to this file:",
                         color=get_accent_color())
            dpg.add_separator()
            dpg.add_spacer(height=5)
            with dpg.child_window(height=280, border=True, tag=self.TAG_META_PREVIEW_CONTENT):
                dpg.add_text("Loading preview...")
            dpg.add_spacer(height=10)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Write Now", callback=self._on_write_metadata_click, width=120)
                dpg.add_button(
                    label="Close", width=120,
                    callback=lambda: dpg.configure_item(self.TAG_META_PREVIEW_DIALOG, show=False),
                )

    def _on_preview_metadata_click(self) -> None:
        """Show preview of metadata that would be written to the selected file."""
        if not self._selected_file_id:
            return

        from duplicleaner.core.metadata_writer import preview_metadata_for_file

        preview = preview_metadata_for_file(self.db, self._selected_file_id)

        # Clear and populate preview content
        children = dpg.get_item_children(self.TAG_META_PREVIEW_CONTENT, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        if not preview:
            dpg.add_text("No AI data available for this file.", parent=self.TAG_META_PREVIEW_CONTENT,
                         color=get_text_color("disabled"))
        else:
            for field_name, value in preview.items():
                with dpg.group(horizontal=True, parent=self.TAG_META_PREVIEW_CONTENT):
                    dpg.add_text(f"{field_name}:", color=get_accent_color())
                text_val = str(value)
                dpg.add_text(text_val, wrap=560, parent=self.TAG_META_PREVIEW_CONTENT)
                dpg.add_spacer(height=5, parent=self.TAG_META_PREVIEW_CONTENT)

        dpg.configure_item(self.TAG_META_PREVIEW_DIALOG, show=True)

    def _on_write_metadata_click(self) -> None:
        """Write AI metadata to the selected image file."""
        if not self._selected_file_id:
            return

        dpg.configure_item(self.TAG_META_PREVIEW_DIALOG, show=False)

        file_record = self.db.get_file(self._selected_file_id)
        if not file_record:
            return

        from duplicleaner.core.metadata_writer import build_payload_for_file, write_metadata
        from duplicleaner.utils.config import get_config

        config = get_config()
        tag_prefix = getattr(config.ai, "metadata_tag_prefix", "AI")
        inc_summary = getattr(config.ai, "metadata_include_summary", True)
        inc_tags = getattr(config.ai, "metadata_include_tags", True)
        inc_faces = getattr(config.ai, "metadata_include_faces", True)
        inc_quality = getattr(config.ai, "metadata_include_quality", True)

        payload = build_payload_for_file(
            self.db, self._selected_file_id,
            tag_prefix=tag_prefix,
            include_summary=inc_summary,
            include_tags=inc_tags,
            include_faces=inc_faces,
            include_quality=inc_quality,
        )

        if not payload.summary and not payload.keywords and not payload.face_regions:
            if self.on_status_update:
                self.on_status_update("No AI data available to write for this file.")
            return

        backup = getattr(config.ai, "metadata_backup", True)

        result = write_metadata(
            file_record.path,
            payload,
            backup=backup,
        )

        if result.success:
            msg = f"Metadata written to {file_record.filename} via {result.method}: {', '.join(result.fields_written)}"
            logger.info(msg)
            if self.on_status_update:
                self.on_status_update(msg)
        else:
            msg = f"Failed to write metadata to {file_record.filename}: {result.error}"
            logger.error(msg)
            if self.on_status_update:
                self.on_status_update(msg)
