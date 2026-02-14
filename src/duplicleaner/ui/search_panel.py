"""Search Panel for DupliCleaner.

Dear PyGui UI component for semantic and text-based search.
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
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

from duplicleaner.ai.scenes import SceneClassifier, SearchResult
from duplicleaner.db.database import get_database
from duplicleaner.db.models import FileRecord
from duplicleaner.ui.theme import get_accent_color, get_status_color, get_text_color
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchItem:
    """Unified search result item."""
    file_id: int
    file_path: str
    source: str
    similarity: float | None = None
    categories: dict[str, float] | None = None
    file: FileRecord | None = None


class SearchPanel:
    """UI panel for semantic and text search."""

    TAG_PANEL = "search_panel"
    TAG_QUERY = "search_query"
    TAG_RESULTS_TABLE = "search_results_table"
    TAG_STATUS_TEXT = "search_status_text"
    TAG_FILTER_TYPE = "search_filter_type"
    TAG_FILTER_DATE_FROM = "search_filter_date_from"
    TAG_FILTER_DATE_TO = "search_filter_date_to"
    TAG_FILTER_PERSON = "search_filter_person"
    TAG_FILTER_FAMILY = "search_filter_family"
    TAG_ENABLE_SEMANTIC = "search_enable_semantic"
    TAG_ENABLE_TEXT = "search_enable_text"
    TAG_LIMIT = "search_limit"
    TAG_SORT_BY = "search_sort_by"
    TAG_CORPUS_DIALOG = "corpus_analysis_dialog"
    TAG_CORPUS_FOLDER = "corpus_folder_input"
    TAG_CORPUS_RESULTS = "corpus_results_container"
    TAG_CORPUS_STATUS = "corpus_status_text"
    TAG_RESULTS_CONTAINER = "search_results_container"
    TAG_PREVIEW_DIALOG = "search_preview_dialog"
    TAG_PREVIEW_IMAGE = "search_preview_image"
    TAG_PREVIEW_INFO = "search_preview_info"
    TAG_TEXTURE_REGISTRY = "search_texture_registry"
    TAG_CONTEXT_MENU = "search_context_menu"

    # Image file extensions for preview
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic', '.heif'}

    # Thumbnail size for results list
    THUMBNAIL_SIZE = 60

    # Preview dialog image size
    PREVIEW_SIZE = 500

    # Maximum texture cache size (LRU eviction when exceeded)
    MAX_TEXTURE_CACHE = 100

    # Tags for buttons that need state management
    TAG_SEARCH_BUTTON = "search_search_button"
    TAG_CLEAR_BUTTON = "search_clear_button"

    def __init__(self, parent: int | str, on_status_update: Callable[[str], None] | None = None):
        """Initialize search panel."""
        self.parent = parent
        self.db = get_database()
        self.on_status_update = on_status_update

        self._scene_classifier: SceneClassifier | None = None
        self._search_thread: threading.Thread | None = None

        # Current results and state
        self._current_results: list[SearchItem] = []
        self._selected_result_ids: set[int] = set()
        self._result_checkbox_tags: dict[int, str] = {}

        # Texture cache for image previews (with LRU tracking)
        self._texture_cache: dict[str, str] = {}
        self._texture_lru: list[str] = []  # Track access order for LRU eviction
        self._texture_counter = 0
        self._preview_texture_tag: str | None = None
        self._preview_file_path: str | None = None

        # Operation state
        self._search_in_progress = False

        # Context menu state
        self._context_menu_shown = False
        self._context_menu_open_time = 0.0
        self._ctx_file_id: int | None = None
        self._ctx_file_path: str | None = None
        self._result_handler_registries: list[int | str] = []

        self._build_ui()

    @property
    def scene_classifier(self) -> SceneClassifier:
        """Get or create scene classifier."""
        if self._scene_classifier is None:
            self._scene_classifier = SceneClassifier(self.db)
        return self._scene_classifier

    def _build_ui(self) -> None:
        """Build the search panel UI."""
        with dpg.child_window(parent=self.parent, tag=self.TAG_PANEL, autosize_x=True, autosize_y=True):
            dpg.add_text("Semantic Search", color=get_accent_color())
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Search input
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    tag=self.TAG_QUERY,
                    width=520,
                    hint="Search photos, scenes, or text...",
                    on_enter=True,
                    callback=self._on_search,
                )
                dpg.add_button(label="Search", tag=self.TAG_SEARCH_BUTTON, callback=self._on_search)
                dpg.add_button(label="Clear", tag=self.TAG_CLEAR_BUTTON, callback=self._on_clear)

            dpg.add_spacer(height=5)

            # Search options
            with dpg.group(horizontal=True):
                dpg.add_checkbox(
                    label="Semantic (CLIP)",
                    default_value=True,
                    tag=self.TAG_ENABLE_SEMANTIC,
                )
                dpg.add_checkbox(
                    label="Text (summaries/OCR/tags)",
                    default_value=True,
                    tag=self.TAG_ENABLE_TEXT,
                )
                dpg.add_spacer(width=20)
                dpg.add_text("Limit:")
                dpg.add_input_int(tag=self.TAG_LIMIT, default_value=200, min_value=10, max_value=5000, width=80)
                dpg.add_spacer(width=20)
                dpg.add_text("Sort:")
                dpg.add_combo(
                    tag=self.TAG_SORT_BY,
                    items=["Relevance", "Date (Newest)", "Date (Oldest)", "Size (Largest)", "Size (Smallest)", "Name"],
                    default_value="Relevance",
                    width=130,
                    callback=self._on_sort_change,
                )

            dpg.add_spacer(height=10)

            # Filters
            with dpg.group(horizontal=True):
                dpg.add_text("Type:")
                dpg.add_combo(
                    tag=self.TAG_FILTER_TYPE,
                    items=["All", "Images", "Videos", "Documents", "Other"],
                    default_value="All",
                    width=120,
                )
                dpg.add_spacer(width=10)
                dpg.add_text("Date:")
                dpg.add_input_text(tag=self.TAG_FILTER_DATE_FROM, hint="From (YYYY-MM-DD)", width=120)
                dpg.add_input_text(tag=self.TAG_FILTER_DATE_TO, hint="To (YYYY-MM-DD)", width=120)
                dpg.add_spacer(width=10)
                dpg.add_text("Person:")
                dpg.add_input_text(tag=self.TAG_FILTER_PERSON, hint="Name contains...", width=160)
                dpg.add_spacer(width=10)
                dpg.add_text("Family:")
                dpg.add_combo(tag=self.TAG_FILTER_FAMILY, items=["(any)"], default_value="(any)", width=140, callback=self._on_family_filter_change)

            dpg.add_spacer(height=10)

            # Status and selection controls
            with dpg.group(horizontal=True):
                dpg.add_text("Enter a query to search your library.", tag=self.TAG_STATUS_TEXT, color=get_text_color("disabled"))
                dpg.add_spacer(width=20)
                dpg.add_button(label="Select All", callback=self._select_all_results, small=True)
                dpg.add_button(label="Select None", callback=self._deselect_all_results, small=True)
                dpg.add_spacer(width=10)
                dpg.add_button(label="Export Results", callback=self._on_export_results, small=True)
                dpg.add_spacer(width=10)
                dpg.add_button(label="Corpus Analysis", callback=self._on_open_corpus_analysis, small=True)

            dpg.add_spacer(height=5)

            # Results container - scrollable list of result cards
            with dpg.child_window(height=-1, border=True, tag=self.TAG_RESULTS_CONTAINER):
                dpg.add_text("Results will appear here...", tag="search_results_placeholder", color=get_text_color("disabled"))

        # Create texture registry
        with dpg.texture_registry(tag=self.TAG_TEXTURE_REGISTRY):
            pass

        # Create preview dialog
        self._create_preview_dialog()
        self._create_corpus_dialog()

        # Context menu
        with dpg.window(
            tag=self.TAG_CONTEXT_MENU,
            show=False,
            no_title_bar=True,
            no_resize=True,
            no_move=True,
            no_scrollbar=True,
            autosize=True,
        ):
            dpg.add_selectable(label="Preview", callback=self._ctx_preview)
            dpg.add_selectable(label="Open File", callback=self._ctx_open_file)
            dpg.add_selectable(label="Show in Explorer", callback=self._ctx_show_in_explorer)
            dpg.add_separator()
            dpg.add_selectable(label="Copy Path", callback=self._ctx_copy_path)

        # Dismiss handler
        with dpg.handler_registry():
            dpg.add_mouse_click_handler(callback=self._on_dismiss_context_menu)

    def _set_status(self, message: str, color: tuple[int, int, int] | None = None) -> None:
        """Update status text."""
        dpg.split_frame()
        if color:
            dpg.configure_item(self.TAG_STATUS_TEXT, color=color)
        dpg.set_value(self.TAG_STATUS_TEXT, message)

    def _on_clear(self) -> None:
        """Clear the search input and results."""
        dpg.set_value(self.TAG_QUERY, "")
        dpg.set_value(self.TAG_FILTER_PERSON, "")
        dpg.set_value(self.TAG_FILTER_DATE_FROM, "")
        dpg.set_value(self.TAG_FILTER_DATE_TO, "")
        dpg.set_value(self.TAG_FILTER_FAMILY, "(any)")
        self._current_results = []
        self._selected_result_ids.clear()
        self._result_checkbox_tags.clear()
        self._clear_results()
        self._set_status("Search cleared.", color=get_text_color("disabled"))

    def _clear_results(self) -> None:
        """Clear results container."""
        # Clean up handler registries
        for hr in self._result_handler_registries:
            try:
                if dpg.does_item_exist(hr):
                    dpg.delete_item(hr)
            except Exception:
                pass
        self._result_handler_registries.clear()

        children = dpg.get_item_children(self.TAG_RESULTS_CONTAINER, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable search buttons during operations."""
        for tag in [self.TAG_SEARCH_BUTTON, self.TAG_CLEAR_BUTTON]:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=enabled)

    def _on_search(self) -> None:
        """Handle search button click."""
        if self._search_in_progress:
            logger.info("Search already in progress")
            return

        query = dpg.get_value(self.TAG_QUERY).strip()
        if not query:
            self._set_status("Please enter a search query.", color=get_status_color("error"))
            self._notify_status("Search query is empty.", level="warning")
            return

        self._search_in_progress = True
        self._set_buttons_enabled(False)
        self._set_status("Searching...", color=get_status_color("info"))
        self._notify_status(f"Searching for '{query}'...")
        self._clear_results()

        self._search_thread = threading.Thread(target=self._run_search, args=(query,), daemon=True)
        self._search_thread.start()

    def _run_search(self, query: str) -> None:
        """Run search in background thread."""
        try:
            enable_semantic = dpg.get_value(self.TAG_ENABLE_SEMANTIC)
            enable_text = dpg.get_value(self.TAG_ENABLE_TEXT)
            limit = max(10, int(dpg.get_value(self.TAG_LIMIT) or 200))

            items: dict[int, SearchItem] = {}

            if enable_semantic:
                if self.scene_classifier.is_available():
                    semantic_results = self.scene_classifier.search(query, limit=limit)
                    self._merge_semantic_results(items, semantic_results)
                else:
                    self._set_status("Semantic search unavailable (missing CLIP dependencies).", color=get_status_color("warning"))

            if enable_text:
                text_results = self.db.search_files(query, limit=limit)
                self._merge_text_results(items, text_results)

            results = list(items.values())
            results = self._apply_filters(results)
            results = self._apply_sort(results)

            # Store results for later use
            self._current_results = results
            self._selected_result_ids.clear()
            self._result_checkbox_tags.clear()

            self._render_results(results)
            self._notify_status(f"Search complete: {len(results)} result(s).")

        except Exception as e:
            logger.error(f"Search failed: {e}")
            self._set_status(f"Search failed: {e}", color=get_status_color("error"))
            self._notify_status("Search failed.", level="error")
        finally:
            self._search_in_progress = False
            self._set_buttons_enabled(True)

    def _notify_status(self, message: str, level: str = "info") -> None:
        """Send status update if callback provided."""
        if not self.on_status_update:
            return
        try:
            self.on_status_update(message, level=level)
        except TypeError:
            self.on_status_update(message)

    def _merge_semantic_results(
        self,
        items: dict[int, SearchItem],
        results: list[SearchResult],
    ) -> None:
        for result in results:
            file_record = self.db.get_file(result.file_id)
            if not file_record:
                continue

            item = items.get(result.file_id)
            if item is None:
                items[result.file_id] = SearchItem(
                    file_id=result.file_id,
                    file_path=result.file_path,
                    source="semantic",
                    similarity=result.similarity,
                    categories=result.preview_categories,
                    file=file_record,
                )
            else:
                item.source = self._merge_sources(item.source, "semantic")
                item.similarity = max(item.similarity or 0.0, result.similarity)
                if result.preview_categories:
                    item.categories = result.preview_categories

    def _merge_text_results(
        self,
        items: dict[int, SearchItem],
        results: list[tuple[FileRecord, str]],
    ) -> None:
        for file_record, source in results:
            if file_record.id is None:
                continue

            item = items.get(file_record.id)
            if item is None:
                items[file_record.id] = SearchItem(
                    file_id=file_record.id,
                    file_path=file_record.path,
                    source=source,
                    file=file_record,
                )
            else:
                item.source = self._merge_sources(item.source, source)

    def _merge_sources(self, existing: str, new_source: str) -> str:
        sources = {s.strip() for s in existing.split("+") if s.strip()}
        sources.add(new_source)
        return "+".join(sorted(sources))

    def _apply_filters(self, results: list[SearchItem]) -> list[SearchItem]:
        """Apply type, date, person, and family group filters."""
        filter_type = dpg.get_value(self.TAG_FILTER_TYPE)
        date_from = self._parse_date(dpg.get_value(self.TAG_FILTER_DATE_FROM))
        date_to = self._parse_date(dpg.get_value(self.TAG_FILTER_DATE_TO))
        person_query = dpg.get_value(self.TAG_FILTER_PERSON).strip().lower()
        family_filter = dpg.get_value(self.TAG_FILTER_FAMILY)

        person_file_ids: set[int] | None = None
        if person_query:
            person_file_ids = self._get_files_for_person_query(person_query)

        # Family group filter
        family_file_ids: set[int] | None = None
        if family_filter and family_filter != "(any)":
            family_file_ids = self._get_files_for_family_group(family_filter)

        filtered = []
        for item in results:
            file_record = item.file
            if not file_record:
                continue

            if not self._passes_type_filter(file_record, filter_type):
                continue

            if not self._passes_date_filter(file_record, date_from, date_to):
                continue

            if person_file_ids is not None and file_record.id not in person_file_ids:
                continue

            if family_file_ids is not None and file_record.id not in family_file_ids:
                continue

            filtered.append(item)

        return filtered

    def _passes_type_filter(self, file_record: FileRecord, filter_type: str) -> bool:
        if filter_type == "All":
            return True
        if filter_type == "Images":
            return file_record.is_image
        if filter_type == "Videos":
            return file_record.is_video
        if filter_type == "Documents":
            return file_record.is_document
        if filter_type == "Other":
            return not (file_record.is_image or file_record.is_video or file_record.is_document)
        return True

    def _passes_date_filter(
        self,
        file_record: FileRecord,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> bool:
        if not date_from and not date_to:
            return True

        file_date = file_record.modified or file_record.created
        if not file_date:
            return False

        if date_from and file_date < date_from:
            return False
        return not (date_to and file_date > date_to)

    def _get_files_for_person_query(self, query: str) -> set[int]:
        matches = [p for p in self.db.get_all_persons(named_only=True) if p.name and query in p.name.lower()]
        if not matches:
            return set()

        file_ids: set[int] = set()
        for person in matches:
            faces = self.db.get_faces_for_person(person.id)
            for face in faces:
                file_ids.add(face.file_id)

        return file_ids

    def _get_files_for_family_group(self, group_name: str) -> set[int]:
        """Get all file IDs containing faces of any member of the named family group."""
        groups = self.db.get_all_family_groups()
        group = next((g for g in groups if g.name == group_name), None)
        if not group or group.id is None:
            return set()
        return set(self.db.get_family_group_file_ids(group.id))

    def _on_family_filter_change(self, sender=None, app_data=None) -> None:
        """Re-run search when family filter changes."""
        if self._current_results:
            self._on_search()

    def refresh_family_groups(self) -> None:
        """Refresh the family group combo items from the database."""
        groups = self.db.get_all_family_groups()
        names = ["(any)"] + [g.name for g in groups]
        if dpg.does_item_exist(self.TAG_FILTER_FAMILY):
            dpg.configure_item(self.TAG_FILTER_FAMILY, items=names)

    def _apply_sort(self, results: list[SearchItem]) -> list[SearchItem]:
        """Apply sorting based on user selection."""
        sort_by = dpg.get_value(self.TAG_SORT_BY)

        if sort_by == "Relevance":
            # Semantic results first by similarity, then text results
            return sorted(results, key=lambda x: (0 if x.similarity else 1, -(x.similarity or 0)))
        elif sort_by == "Date (Newest)":
            return sorted(results, key=lambda x: x.file.modified if x.file and x.file.modified else datetime.min, reverse=True)
        elif sort_by == "Date (Oldest)":
            return sorted(results, key=lambda x: x.file.modified if x.file and x.file.modified else datetime.max)
        elif sort_by == "Size (Largest)":
            return sorted(results, key=lambda x: x.file.size if x.file else 0, reverse=True)
        elif sort_by == "Size (Smallest)":
            return sorted(results, key=lambda x: x.file.size if x.file else float('inf'))
        elif sort_by == "Name":
            return sorted(results, key=lambda x: Path(x.file_path).name.lower())
        return results

    def _on_sort_change(self, sender, app_data, user_data) -> None:
        """Handle sort dropdown change - re-sort and re-render current results."""
        if self._current_results:
            self._current_results = self._apply_sort(self._current_results)
            self._render_results(self._current_results)

    def _render_results(self, results: list[SearchItem]) -> None:
        """Render search results as cards with thumbnails and actions."""
        dpg.split_frame()
        self._clear_results()

        if not results:
            dpg.add_text(
                "No matches found.",
                parent=self.TAG_RESULTS_CONTAINER,
                color=get_text_color("disabled")
            )
            self._set_status("No matches found.", color=get_text_color("disabled"))
            return

        for item in results:
            self._render_result_card(item)

        self._set_status(f"Found {len(results)} result(s).", color=get_status_color("info"))

    def _render_result_card(self, item: SearchItem) -> None:
        """Render a single result as a card with preview, info, and actions."""
        file = item.file
        if not file:
            return

        # Card container with border
        with (
            dpg.child_window(
                parent=self.TAG_RESULTS_CONTAINER,
                height=90,
                border=True,
                no_scrollbar=True,
            ),
            dpg.group(horizontal=True),
        ):
            # Checkbox for selection
            checkbox_tag = f"search_result_checkbox_{item.file_id}"
            self._result_checkbox_tags[item.file_id] = checkbox_tag
            dpg.add_checkbox(
                tag=checkbox_tag,
                default_value=item.file_id in self._selected_result_ids,
                callback=self._on_result_checkbox_toggled,
                user_data=item.file_id,
            )

            # Thumbnail preview (for images)
            if self._is_image_file(item.file_path):
                texture_tag = self._load_image_texture(item.file_path, size=self.THUMBNAIL_SIZE)
                if texture_tag:
                    dpg.add_image(
                        texture_tag,
                        width=self.THUMBNAIL_SIZE,
                        height=self.THUMBNAIL_SIZE,
                    )
                else:
                    # Placeholder for failed load
                    with dpg.group():
                        dpg.add_text("[Image]", color=get_text_color("disabled"))
                        dpg.add_spacer(width=self.THUMBNAIL_SIZE - 40)
            else:
                # Non-image placeholder
                with dpg.group():
                    ext = Path(item.file_path).suffix.upper()
                    dpg.add_text(ext if ext else "[File]", color=get_text_color("disabled"))
                    dpg.add_spacer(width=self.THUMBNAIL_SIZE - 40)

            dpg.add_spacer(width=10)

            # File info column
            with dpg.group():
                # Filename (clickable for preview, right-click for context menu)
                name = Path(item.file_path).name
                display_name = name[:45] + "..." if len(name) > 45 else name
                fname_sel = dpg.add_selectable(
                    label=display_name,
                    callback=lambda s, a, u: self._show_preview(u),
                    user_data=item.file_id,
                    span_columns=False,
                )
                with dpg.item_handler_registry() as hr:
                    dpg.add_item_clicked_handler(
                        button=dpg.mvMouseButton_Right,
                        callback=self._on_result_right_click,
                        user_data=(item.file_id, item.file_path),
                    )
                dpg.bind_item_handler_registry(fname_sel, hr)
                self._result_handler_registries.append(hr)

                # Size and date
                size_str = self._format_size(file.size)
                date_str = file.modified.strftime('%Y-%m-%d %H:%M') if file.modified else "Unknown date"
                dpg.add_text(f"{size_str}  |  {date_str}", color=get_text_color("disabled"))

                # Source and score
                score_str = f"  |  Score: {item.similarity:.3f}" if item.similarity is not None else ""
                dpg.add_text(f"Source: {item.source}{score_str}", color=get_text_color("secondary"))

                # Categories if available
                if item.categories:
                    cats = self._format_categories(item.categories)
                    if cats:
                        dpg.add_text(
                            cats[:60] + "..." if len(cats) > 60 else cats,
                            color=get_text_color("secondary"),
                            wrap=250,
                        )

            dpg.add_spacer(width=20)

            # Action buttons column
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Preview",
                    callback=lambda s, a, u: self._show_preview(u),
                    user_data=item.file_id,
                    width=65,
                    small=True,
                )
                dpg.add_button(
                    label="Open",
                    callback=lambda s, a, u: self._open_file(u),
                    user_data=item.file_path,
                    width=50,
                    small=True,
                )
                dpg.add_button(
                    label="Explorer",
                    callback=lambda s, a, u: self._open_in_explorer(u),
                    user_data=item.file_path,
                    width=65,
                    small=True,
                )



    def _format_categories(self, categories: dict[str, float] | None) -> str:
        if not categories:
            return ""

        pairs = sorted(categories.items(), key=lambda x: x[1], reverse=True)
        top = pairs[:4]
        return ", ".join(f"{name} ({score:.2f})" for name, score in top)

    def _format_size(self, size: int) -> str:
        """Format file size in human-readable form."""
        if size >= 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
        elif size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            return f"{size / 1024:.0f} KB"
        return f"{size} B"

    def _is_image_file(self, file_path: str) -> bool:
        """Check if a file is an image based on extension."""
        ext = Path(file_path).suffix.lower()
        return ext in self.IMAGE_EXTENSIONS

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

        size = size or self.THUMBNAIL_SIZE

        # Check cache
        cache_key = f"{file_path}_{size}"
        if cache_key in self._texture_cache:
            # Update LRU order
            if cache_key in self._texture_lru:
                self._texture_lru.remove(cache_key)
            self._texture_lru.append(cache_key)
            return self._texture_cache[cache_key]

        try:
            # Load and resize image
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
            texture_tag = f"search_texture_{self._texture_counter}"

            # Add static texture
            dpg.add_static_texture(
                width=width,
                height=height,
                default_value=data,
                tag=texture_tag,
                parent=self.TAG_TEXTURE_REGISTRY
            )

            # Evict oldest entries if cache is full
            while len(self._texture_cache) >= self.MAX_TEXTURE_CACHE and self._texture_lru:
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

    def _open_file(self, file_path: str) -> None:
        """Open a file with its default application."""
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            self._notify_status(f"File not found: {Path(file_path).name}", level="warning")
            return

        try:
            os.startfile(file_path)
        except Exception as e:
            logger.error(f"Failed to open file: {e}")
            self._notify_status(f"Failed to open file: {e}", level="error")

    def _open_in_explorer(self, file_path: str) -> None:
        """Open Windows Explorer with the file selected."""
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            self._notify_status(f"File not found: {Path(file_path).name}", level="warning")
            return

        try:
            # Use explorer /select to highlight the file
            subprocess.run(['explorer', '/select,', file_path], check=False)
        except Exception as e:
            logger.error(f"Failed to open Explorer: {e}")
            self._notify_status(f"Failed to open Explorer: {e}", level="error")

    def _on_result_checkbox_toggled(self, sender, app_data, user_data) -> None:
        """Handle selection checkbox toggle for a result."""
        file_id = user_data
        if app_data:
            self._selected_result_ids.add(file_id)
        else:
            self._selected_result_ids.discard(file_id)

    def _select_all_results(self) -> None:
        """Select all visible results."""
        self._selected_result_ids = {item.file_id for item in self._current_results}
        for file_id, tag in self._result_checkbox_tags.items():
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, file_id in self._selected_result_ids)

    def _deselect_all_results(self) -> None:
        """Clear selection for all results."""
        self._selected_result_ids.clear()
        for tag in self._result_checkbox_tags.values():
            if dpg.does_item_exist(tag):
                dpg.set_value(tag, False)

    def _center_dialog(self, dialog_tag: str, width: int, height: int) -> None:
        """Center a dialog on the viewport."""
        try:
            vp_width = dpg.get_viewport_width()
            vp_height = dpg.get_viewport_height()
            x = max(0, (vp_width - width) // 2)
            y = max(0, (vp_height - height) // 2)
            dpg.set_item_pos(dialog_tag, [x, y])
        except Exception:
            pass

    def _create_preview_dialog(self) -> None:
        """Create the file preview dialog."""
        with dpg.window(
            tag=self.TAG_PREVIEW_DIALOG,
            label="File Preview",
            modal=True,
            show=False,
            width=650,
            height=600,
            no_resize=False,
        ):
            dpg.add_text("File Preview", color=get_accent_color())
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # File info section
            with dpg.group(tag=self.TAG_PREVIEW_INFO):
                dpg.add_text("Loading...", tag="search_preview_filename")
                dpg.add_text("", tag="search_preview_details", color=get_text_color("disabled"))
                dpg.add_text("", tag="search_preview_path", color=get_text_color("disabled"), wrap=600)

            dpg.add_spacer(height=10)

            # Image preview area
            with dpg.child_window(height=420, border=True, tag="search_preview_image_container"):
                dpg.add_text("Preview will appear here...", tag="search_preview_placeholder", color=get_text_color("disabled"))

            dpg.add_spacer(height=10)

            # Action buttons
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Open File",
                    callback=self._preview_open_file,
                    width=100,
                )
                dpg.add_button(
                    label="Show in Explorer",
                    callback=self._preview_show_in_explorer,
                    width=130,
                )
                dpg.add_spacer(width=200)
                dpg.add_button(
                    label="Close",
                    callback=lambda: dpg.hide_item(self.TAG_PREVIEW_DIALOG),
                    width=80,
                )

    def _show_preview(self, file_id: int) -> None:
        """Show preview dialog for a file."""
        # Find the item
        item = next((i for i in self._current_results if i.file_id == file_id), None)
        if not item or not item.file:
            return

        file = item.file
        self._preview_file_path = item.file_path

        # Update file info
        dpg.set_value("search_preview_filename", file.filename)

        size_str = self._format_size(file.size)
        date_str = file.modified.strftime('%Y-%m-%d %H:%M') if file.modified else "Unknown date"
        details = f"Size: {size_str}  |  Modified: {date_str}"
        if item.similarity is not None:
            details += f"  |  Score: {item.similarity:.3f}"
        dpg.set_value("search_preview_details", details)

        dpg.set_value("search_preview_path", f"Path: {item.file_path}")

        # Clear previous preview
        children = dpg.get_item_children("search_preview_image_container", slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

        # Clean up previous preview texture
        if self._preview_texture_tag and dpg.does_item_exist(self._preview_texture_tag):
            with contextlib.suppress(Exception):
                dpg.delete_item(self._preview_texture_tag)
            self._preview_texture_tag = None

        # Load preview image
        if self._is_image_file(item.file_path):
            texture_tag = self._load_preview_image(item.file_path)
            if texture_tag:
                self._preview_texture_tag = texture_tag
                dpg.add_image(
                    texture_tag,
                    parent="search_preview_image_container",
                )
            else:
                dpg.add_text(
                    "Failed to load image preview.",
                    parent="search_preview_image_container",
                    color=get_status_color("error")
                )
        else:
            # Non-image file
            ext = Path(item.file_path).suffix.upper()
            dpg.add_text(
                f"No preview available for {ext} files.",
                parent="search_preview_image_container",
                color=get_text_color("disabled")
            )
            dpg.add_spacer(height=20, parent="search_preview_image_container")
            dpg.add_text(
                "Click 'Open File' to view with the default application.",
                parent="search_preview_image_container",
                color=get_text_color("disabled")
            )

        self._center_dialog(self.TAG_PREVIEW_DIALOG, 650, 600)
        dpg.show_item(self.TAG_PREVIEW_DIALOG)

    def _load_preview_image(self, file_path: str) -> str | None:
        """Load a larger preview image for the dialog."""
        if not HAS_PIL or not os.path.exists(file_path):
            return None

        try:
            img = Image.open(file_path)
            img = ImageOps.exif_transpose(img)
            img.thumbnail((self.PREVIEW_SIZE, self.PREVIEW_SIZE), Image.Resampling.LANCZOS)

            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            width, height = img.size
            data = np.array(img).astype(np.float32) / 255.0
            data = data.flatten().tolist()

            self._texture_counter += 1
            texture_tag = f"search_preview_{self._texture_counter}"

            dpg.add_static_texture(
                width=width,
                height=height,
                default_value=data,
                tag=texture_tag,
                parent=self.TAG_TEXTURE_REGISTRY
            )

            return texture_tag

        except Exception as e:
            logger.debug(f"Failed to load preview image: {e}")
            return None

    def _preview_open_file(self) -> None:
        """Open file from preview dialog."""
        if self._preview_file_path:
            self._open_file(self._preview_file_path)

    def _preview_show_in_explorer(self) -> None:
        """Show file in explorer from preview dialog."""
        if self._preview_file_path:
            self._open_in_explorer(self._preview_file_path)

    def _parse_date(self, value: str) -> datetime | None:
        text = (value or "").strip()
        if not text:
            return None

        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass

        try:
            from dateutil import parser
        except Exception:
            return None

        try:
            return parser.parse(text)
        except Exception:
            return None

    def refresh(self) -> None:
        """Refresh the panel."""
        self._current_results = []
        self._selected_result_ids.clear()
        self._result_checkbox_tags.clear()
        self._clear_results()
        self._set_status("Ready to search.", color=get_text_color("disabled"))

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _on_result_right_click(self, sender=None, app_data=None, user_data=None) -> None:
        """Show context menu on right-click of a result."""
        import time

        if user_data:
            self._ctx_file_id, self._ctx_file_path = user_data
        mouse_pos = dpg.get_mouse_pos(local=False)
        dpg.configure_item(
            self.TAG_CONTEXT_MENU,
            show=True,
            pos=[int(mouse_pos[0]), int(mouse_pos[1])],
        )
        self._context_menu_shown = True
        self._context_menu_open_time = time.time()

    def _on_dismiss_context_menu(self, sender=None, app_data=None) -> None:
        """Hide context menu on left-click outside."""
        import time

        if not self._context_menu_shown:
            return
        if time.time() - self._context_menu_open_time < 0.15:
            return
        try:
            if dpg.is_item_hovered(self.TAG_CONTEXT_MENU):
                return
        except (KeyError, SystemError):
            pass
        dpg.configure_item(self.TAG_CONTEXT_MENU, show=False)
        self._context_menu_shown = False

    def _hide_context_menu(self) -> None:
        dpg.configure_item(self.TAG_CONTEXT_MENU, show=False)
        self._context_menu_shown = False

    def _ctx_preview(self, sender=None, app_data=None) -> None:
        self._hide_context_menu()
        if self._ctx_file_id is not None:
            self._show_preview(self._ctx_file_id)

    def _ctx_open_file(self, sender=None, app_data=None) -> None:
        self._hide_context_menu()
        if self._ctx_file_path:
            self._open_file(self._ctx_file_path)

    def _ctx_show_in_explorer(self, sender=None, app_data=None) -> None:
        self._hide_context_menu()
        if self._ctx_file_path:
            self._open_in_explorer(self._ctx_file_path)

    def _ctx_copy_path(self, sender=None, app_data=None) -> None:
        self._hide_context_menu()
        if not self._ctx_file_path:
            return
        try:
            subprocess.run(["clip"], input=self._ctx_file_path.encode(), check=True)
            self._notify_status(f"Copied: {self._ctx_file_path}")
        except Exception as exc:
            logger.error(f"Failed to copy path: {exc}")

    def cleanup(self) -> None:
        """Clean up resources (textures, threads, etc.)."""
        # Wait for search thread to finish (with timeout)
        if self._search_thread and self._search_thread.is_alive():
            logger.debug("Waiting for search thread to finish...")
            self._search_thread.join(timeout=2.0)
            if self._search_thread.is_alive():
                logger.warning("Search thread did not finish in time")
        self._search_thread = None
        self._search_in_progress = False

        # Clean up cached textures
        for texture_tag in self._texture_cache.values():
            try:
                if dpg.does_item_exist(texture_tag):
                    dpg.delete_item(texture_tag)
            except Exception:
                pass
        self._texture_cache.clear()
        self._texture_lru.clear()

        # Clean up preview texture
        if self._preview_texture_tag and dpg.does_item_exist(self._preview_texture_tag):
            with contextlib.suppress(Exception):
                dpg.delete_item(self._preview_texture_tag)
            self._preview_texture_tag = None

        # Delete texture registry
        if dpg.does_item_exist(self.TAG_TEXTURE_REGISTRY):
            with contextlib.suppress(Exception):
                dpg.delete_item(self.TAG_TEXTURE_REGISTRY)

    # --- Export ---

    def _on_export_results(self) -> None:
        """Export current search results to CSV."""
        from duplicleaner.utils.export_manager import (
            export_csv,
            format_size,
            get_default_export_dir,
            get_timestamped_filename,
        )

        if not self._current_results:
            if self.on_status_update:
                self.on_status_update("No search results to export.")
            return

        query = dpg.get_value(self.TAG_QUERY) if dpg.does_item_exist(self.TAG_QUERY) else ""
        export_dir = get_default_export_dir()
        filepath = export_dir / get_timestamped_filename("search_results", "csv")

        rows = []
        for item in self._current_results:
            f = item.file
            rows.append({
                "file_id": item.file_id,
                "file_path": item.file_path,
                "source": item.source,
                "similarity": f"{item.similarity:.3f}" if item.similarity is not None else "",
                "filename": f.filename if f else "",
                "size": f.size if f else 0,
                "size_human": format_size(f.size) if f else "",
                "file_type": f.file_type if f else "",
                "modified": str(f.modified) if f and f.modified else "",
            })

        count = export_csv(rows, filepath)
        msg = f"Exported {count} search results (query: '{query}') to {filepath}"
        logger.info(msg)
        if self.on_status_update:
            self.on_status_update(msg)

    # --- Corpus Analysis ---

    def _create_corpus_dialog(self) -> None:
        """Create the corpus analysis dialog."""
        with dpg.window(
            tag=self.TAG_CORPUS_DIALOG,
            label="Document Corpus Analysis",
            modal=False,
            show=False,
            width=800,
            height=600,
            no_resize=False,
        ):
            dpg.add_text("Corpus Analysis", color=get_accent_color())
            dpg.add_text(
                "Analyze term frequency, entities, and patterns across your document collection.",
                color=get_text_color("secondary"), wrap=760,
            )
            dpg.add_separator()
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                dpg.add_text("Folder filter (optional):")
                dpg.add_input_text(
                    tag=self.TAG_CORPUS_FOLDER,
                    hint="Leave empty for all documents",
                    width=400,
                )

            dpg.add_spacer(height=5)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Run Analysis", callback=self._on_run_corpus_analysis)
                dpg.add_button(label="Export Report", callback=self._on_export_corpus)
                dpg.add_text("", tag=self.TAG_CORPUS_STATUS, color=get_text_color("disabled"))

            dpg.add_spacer(height=10)

            # Results area with tabs
            with dpg.tab_bar(tag="corpus_tab_bar"):
                with dpg.tab(label="Top Terms (TF-IDF)"):
                    with dpg.child_window(height=380, border=True, tag="corpus_terms_container"):
                        dpg.add_text("Run analysis to see results.", color=get_text_color("disabled"))

                with dpg.tab(label="Phrases"):
                    with dpg.child_window(height=380, border=True, tag="corpus_phrases_container"):
                        dpg.add_text("Run analysis to see results.", color=get_text_color("disabled"))

                with dpg.tab(label="Entities"):
                    with dpg.child_window(height=380, border=True, tag="corpus_entities_container"):
                        dpg.add_text("Run analysis to see results.", color=get_text_color("disabled"))

                with dpg.tab(label="Co-Occurrences"):
                    with dpg.child_window(height=380, border=True, tag="corpus_cooc_container"):
                        dpg.add_text("Run analysis to see results.", color=get_text_color("disabled"))

    def _on_open_corpus_analysis(self) -> None:
        """Open the corpus analysis dialog."""
        dpg.configure_item(self.TAG_CORPUS_DIALOG, show=True)

    def _on_run_corpus_analysis(self) -> None:
        """Run corpus analysis on documents in the database."""
        from duplicleaner.ai.corpus_analyzer import CorpusAnalyzer, gather_corpus_documents

        folder = dpg.get_value(self.TAG_CORPUS_FOLDER).strip() or None
        dpg.set_value(self.TAG_CORPUS_STATUS, "Gathering documents...")

        documents = gather_corpus_documents(self.db, folder_path=folder)
        if not documents:
            dpg.set_value(self.TAG_CORPUS_STATUS, "No documents with text found.")
            return

        dpg.set_value(self.TAG_CORPUS_STATUS, f"Analyzing {len(documents)} documents...")

        analyzer = CorpusAnalyzer()
        self._corpus_report = analyzer.analyze_corpus(documents, include_entities=True)

        # Also try communication network
        self._corpus_report.communication_edges = analyzer.build_communication_network(documents)

        dpg.set_value(
            self.TAG_CORPUS_STATUS,
            f"Done: {self._corpus_report.total_documents} docs, "
            f"{self._corpus_report.total_words:,} words, "
            f"{len(self._corpus_report.entities)} entities",
        )

        self._populate_corpus_results()

    def _populate_corpus_results(self) -> None:
        """Populate the corpus analysis results tabs."""
        report = self._corpus_report

        # Terms tab
        self._clear_container("corpus_terms_container")
        if report.top_terms:
            with dpg.table(
                parent="corpus_terms_container",
                header_row=True,
                borders_innerH=True, borders_outerH=True,
                borders_innerV=True, borders_outerV=True,
                resizable=True, policy=dpg.mvTable_SizingStretchProp,
                row_background=True, scrollY=True, height=350,
            ):
                dpg.add_table_column(label="Term", init_width_or_weight=150)
                dpg.add_table_column(label="Count", init_width_or_weight=80)
                dpg.add_table_column(label="Documents", init_width_or_weight=80)
                dpg.add_table_column(label="TF-IDF", init_width_or_weight=100)

                for t in report.top_terms[:100]:
                    with dpg.table_row():
                        dpg.add_text(t.term)
                        dpg.add_text(f"{t.count:,}")
                        dpg.add_text(f"{t.doc_count:,}")
                        dpg.add_text(f"{t.tf_idf:.6f}")

        # Phrases tab
        self._clear_container("corpus_phrases_container")
        all_phrases = report.top_bigrams + report.top_trigrams
        all_phrases.sort(key=lambda x: x.count, reverse=True)
        if all_phrases:
            with dpg.table(
                parent="corpus_phrases_container",
                header_row=True,
                borders_innerH=True, borders_outerH=True,
                borders_innerV=True, borders_outerV=True,
                resizable=True, policy=dpg.mvTable_SizingStretchProp,
                row_background=True, scrollY=True, height=350,
            ):
                dpg.add_table_column(label="Phrase", init_width_or_weight=250)
                dpg.add_table_column(label="Count", init_width_or_weight=80)
                dpg.add_table_column(label="Documents", init_width_or_weight=80)

                for p in all_phrases[:100]:
                    with dpg.table_row():
                        dpg.add_text(p.phrase)
                        dpg.add_text(f"{p.count:,}")
                        dpg.add_text(f"{p.doc_count:,}")

        # Entities tab
        self._clear_container("corpus_entities_container")
        if report.entities:
            with dpg.table(
                parent="corpus_entities_container",
                header_row=True,
                borders_innerH=True, borders_outerH=True,
                borders_innerV=True, borders_outerV=True,
                resizable=True, policy=dpg.mvTable_SizingStretchProp,
                row_background=True, scrollY=True, height=350,
            ):
                dpg.add_table_column(label="Entity", init_width_or_weight=200)
                dpg.add_table_column(label="Type", init_width_or_weight=100)
                dpg.add_table_column(label="Count", init_width_or_weight=80)
                dpg.add_table_column(label="Documents", init_width_or_weight=80)

                for e in report.entities[:100]:
                    with dpg.table_row():
                        dpg.add_text(e.text)
                        dpg.add_text(e.entity_type)
                        dpg.add_text(f"{e.count:,}")
                        dpg.add_text(f"{len(e.source_file_ids):,}")
        else:
            dpg.add_text("No entities found. Install spaCy for NER: pip install spacy && python -m spacy download en_core_web_sm",
                         parent="corpus_entities_container", wrap=700, color=get_text_color("disabled"))

        # Co-occurrences tab
        self._clear_container("corpus_cooc_container")
        if report.co_occurrences:
            with dpg.table(
                parent="corpus_cooc_container",
                header_row=True,
                borders_innerH=True, borders_outerH=True,
                borders_innerV=True, borders_outerV=True,
                resizable=True, policy=dpg.mvTable_SizingStretchProp,
                row_background=True, scrollY=True, height=350,
            ):
                dpg.add_table_column(label="Entity A", init_width_or_weight=200)
                dpg.add_table_column(label="Entity B", init_width_or_weight=200)
                dpg.add_table_column(label="Co-occurrences", init_width_or_weight=100)

                for c in report.co_occurrences[:100]:
                    with dpg.table_row():
                        dpg.add_text(c.entity_a)
                        dpg.add_text(c.entity_b)
                        dpg.add_text(f"{c.count:,}")

    def _clear_container(self, tag: str) -> None:
        """Clear all children from a container."""
        children = dpg.get_item_children(tag, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

    def _on_export_corpus(self) -> None:
        """Export corpus analysis report."""
        from duplicleaner.utils.export_manager import (
            export_csv,
            get_default_export_dir,
            get_timestamped_filename,
        )

        report = getattr(self, "_corpus_report", None)
        if not report:
            if self.on_status_update:
                self.on_status_update("No corpus analysis to export. Run analysis first.")
            return

        export_dir = get_default_export_dir()

        # Export terms
        if report.top_terms:
            filepath = export_dir / get_timestamped_filename("corpus_terms", "csv")
            rows = [{
                "term": t.term,
                "count": t.count,
                "doc_count": t.doc_count,
                "tf_idf": f"{t.tf_idf:.6f}",
            } for t in report.top_terms]
            export_csv(rows, filepath)

        # Export entities
        if report.entities:
            filepath = export_dir / get_timestamped_filename("corpus_entities", "csv")
            rows = [{
                "entity": e.text,
                "type": e.entity_type,
                "count": e.count,
                "doc_count": len(e.source_file_ids),
            } for e in report.entities]
            export_csv(rows, filepath)

        # Export phrases
        all_phrases = report.top_bigrams + report.top_trigrams
        if all_phrases:
            filepath = export_dir / get_timestamped_filename("corpus_phrases", "csv")
            rows = [{
                "phrase": p.phrase,
                "count": p.count,
                "doc_count": p.doc_count,
            } for p in sorted(all_phrases, key=lambda x: x.count, reverse=True)]
            export_csv(rows, filepath)

        msg = f"Corpus analysis exported to {export_dir}"
        logger.info(msg)
        if self.on_status_update:
            self.on_status_update(msg)
