"""Search Panel for DupliCleaner.

Dear PyGui UI component for semantic and text-based search.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import dearpygui.dearpygui as dpg

from duplicleaner.ai.scenes import SceneClassifier, SearchResult
from duplicleaner.db.database import get_database
from duplicleaner.db.models import FileRecord
from duplicleaner.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchItem:
    """Unified search result item."""
    file_id: int
    file_path: str
    source: str
    similarity: Optional[float] = None
    categories: Optional[dict[str, float]] = None
    file: Optional[FileRecord] = None


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
    TAG_ENABLE_SEMANTIC = "search_enable_semantic"
    TAG_ENABLE_TEXT = "search_enable_text"
    TAG_LIMIT = "search_limit"

    def __init__(self, parent: int | str, on_status_update: Optional[Callable[[str], None]] = None):
        """Initialize search panel."""
        self.parent = parent
        self.db = get_database()
        self.on_status_update = on_status_update

        self._scene_classifier: Optional[SceneClassifier] = None
        self._search_thread: Optional[threading.Thread] = None

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
            dpg.add_text("Semantic Search", color=(150, 200, 255))
            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Search input
            with dpg.group(horizontal=True):
                dpg.add_input_text(
                    tag=self.TAG_QUERY,
                    width=520,
                    hint="Search photos, scenes, or text...",
                )
                dpg.add_button(label="Search", callback=self._on_search)
                dpg.add_button(label="Clear", callback=self._on_clear)

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

            dpg.add_spacer(height=10)

            dpg.add_text("Enter a query to search your library.", tag=self.TAG_STATUS_TEXT, color=(150, 150, 150))
            dpg.add_spacer(height=5)

            # Results table
            with dpg.child_window(height=420, border=True):
                with dpg.table(
                    tag=self.TAG_RESULTS_TABLE,
                    header_row=True,
                    borders_innerH=True,
                    borders_outerH=True,
                    borders_innerV=True,
                    borders_outerV=True,
                    resizable=True,
                    policy=dpg.mvTable_SizingStretchProp,
                    row_background=True,
                    scrollY=True,
                    height=390,
                ):
                    dpg.add_table_column(label="File", init_width_or_weight=150)
                    dpg.add_table_column(label="Path", init_width_or_weight=340)
                    dpg.add_table_column(label="Source", init_width_or_weight=90)
                    dpg.add_table_column(label="Score", init_width_or_weight=70)
                    dpg.add_table_column(label="Categories", init_width_or_weight=220)

    def _set_status(self, message: str, color: Optional[tuple[int, int, int]] = None) -> None:
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
        self._clear_results()
        self._set_status("Search cleared.", color=(150, 150, 150))

    def _clear_results(self) -> None:
        """Clear results table rows."""
        children = dpg.get_item_children(self.TAG_RESULTS_TABLE, slot=1)
        if children:
            for child in children:
                dpg.delete_item(child)

    def _on_search(self) -> None:
        """Handle search button click."""
        if self._search_thread and self._search_thread.is_alive():
            logger.info("Search already in progress")
            return

        query = dpg.get_value(self.TAG_QUERY).strip()
        if not query:
            self._set_status("Please enter a search query.", color=(255, 150, 150))
            self._notify_status("Search query is empty.", level="warning")
            return

        self._set_status("Searching...", color=(150, 200, 255))
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
                    self._set_status("Semantic search unavailable (missing CLIP dependencies).", color=(255, 200, 120))

            if enable_text:
                text_results = self.db.search_files(query, limit=limit)
                self._merge_text_results(items, text_results)

            results = list(items.values())
            results = self._apply_filters(results)
            results.sort(key=self._sort_key)

            self._render_results(results)
            self._notify_status(f"Search complete: {len(results)} result(s).")

        except Exception as e:
            logger.error(f"Search failed: {e}")
            self._set_status(f"Search failed: {e}", color=(255, 150, 150))
            self._notify_status("Search failed.", level="error")

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
        """Apply type, date, and person filters."""
        filter_type = dpg.get_value(self.TAG_FILTER_TYPE)
        date_from = self._parse_date(dpg.get_value(self.TAG_FILTER_DATE_FROM))
        date_to = self._parse_date(dpg.get_value(self.TAG_FILTER_DATE_TO))
        person_query = dpg.get_value(self.TAG_FILTER_PERSON).strip().lower()

        person_file_ids: Optional[set[int]] = None
        if person_query:
            person_file_ids = self._get_files_for_person_query(person_query)

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
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> bool:
        if not date_from and not date_to:
            return True

        file_date = file_record.modified or file_record.created
        if not file_date:
            return False

        if date_from and file_date < date_from:
            return False
        if date_to and file_date > date_to:
            return False

        return True

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

    def _sort_key(self, item: SearchItem) -> tuple[int, float]:
        """Sort semantic results first by similarity, then source."""
        if item.similarity is not None:
            return (0, -item.similarity)
        return (1, 0.0)

    def _render_results(self, results: list[SearchItem]) -> None:
        dpg.split_frame()
        self._clear_results()

        if not results:
            with dpg.table_row(parent=self.TAG_RESULTS_TABLE):
                dpg.add_text("No matches found.")
                dpg.add_text("")
                dpg.add_text("")
                dpg.add_text("")
                dpg.add_text("")
            self._set_status("No matches found.", color=(150, 150, 150))
            return

        for item in results:
            name = Path(item.file_path).name
            score = f"{item.similarity:.3f}" if item.similarity is not None else ""
            categories = self._format_categories(item.categories)

            with dpg.table_row(parent=self.TAG_RESULTS_TABLE):
                dpg.add_text(name)
                dpg.add_text(item.file_path)
                dpg.add_text(item.source)
                dpg.add_text(score)
                dpg.add_text(categories)

        self._set_status(f"Found {len(results)} result(s).", color=(150, 200, 255))

    def _format_categories(self, categories: Optional[dict[str, float]]) -> str:
        if not categories:
            return ""

        pairs = sorted(categories.items(), key=lambda x: x[1], reverse=True)
        top = pairs[:4]
        return ", ".join(f"{name} ({score:.2f})" for name, score in top)

    def _parse_date(self, value: str) -> Optional[datetime]:
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
        self._clear_results()
        self._set_status("Ready to search.", color=(150, 150, 150))
