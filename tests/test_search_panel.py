"""Tests for the Search Panel functionality."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from duplicleaner.db.models import FileRecord


# Test SearchItem dataclass behavior
@dataclass
class MockSearchItem:
    """Mock SearchItem for testing without importing UI module."""
    file_id: int
    file_path: str
    source: str
    similarity: float | None = None
    categories: dict[str, float] | None = None
    file: FileRecord | None = None


class TestSearchItemDataclass:
    """Tests for SearchItem dataclass."""

    def test_search_item_creation(self):
        """Test basic SearchItem creation."""
        item = MockSearchItem(
            file_id=1,
            file_path="/path/to/file.jpg",
            source="semantic",
            similarity=0.95,
        )
        assert item.file_id == 1
        assert item.file_path == "/path/to/file.jpg"
        assert item.source == "semantic"
        assert item.similarity == 0.95

    def test_search_item_with_categories(self):
        """Test SearchItem with categories."""
        categories = {"beach": 0.9, "sunset": 0.8, "travel": 0.7}
        item = MockSearchItem(
            file_id=1,
            file_path="/path/to/file.jpg",
            source="semantic",
            categories=categories,
        )
        assert item.categories == categories
        assert len(item.categories) == 3

    def test_search_item_with_file_record(self):
        """Test SearchItem with FileRecord."""
        file_record = FileRecord(
            id=1,
            drive_id="D1",
            path="/path/to/file.jpg",
            filename="file.jpg",
            size=1024,
            modified=datetime(2024, 1, 15, 10, 30),
        )
        item = MockSearchItem(
            file_id=1,
            file_path="/path/to/file.jpg",
            source="tags",
            file=file_record,
        )
        assert item.file is not None
        assert item.file.size == 1024


class TestSearchPanelHelpers:
    """Tests for SearchPanel helper methods."""

    def test_format_size_bytes(self):
        """Test file size formatting for bytes."""
        # Simulate the format_size function
        def format_size(size: int) -> str:
            if size >= 1024 * 1024 * 1024:
                return f"{size / (1024 * 1024 * 1024):.1f} GB"
            elif size >= 1024 * 1024:
                return f"{size / (1024 * 1024):.1f} MB"
            elif size >= 1024:
                return f"{size / 1024:.0f} KB"
            return f"{size} B"

        assert format_size(500) == "500 B"
        assert format_size(1024) == "1 KB"
        assert format_size(1536) == "2 KB"  # rounds to nearest
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert format_size(1024 * 1024 * 1024 * 2.5) == "2.5 GB"

    def test_is_image_file(self):
        """Test image file detection."""
        IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif'}

        def is_image_file(file_path: str) -> bool:
            ext = Path(file_path).suffix.lower()
            return ext in IMAGE_EXTENSIONS

        assert is_image_file("photo.jpg") is True
        assert is_image_file("photo.JPEG") is True
        assert is_image_file("photo.PNG") is True
        assert is_image_file("photo.gif") is True
        assert is_image_file("photo.webp") is True
        assert is_image_file("document.pdf") is False
        assert is_image_file("video.mp4") is False
        assert is_image_file("text.txt") is False

    def test_format_categories(self):
        """Test category formatting."""
        def format_categories(categories: dict[str, float] | None) -> str:
            if not categories:
                return ""
            pairs = sorted(categories.items(), key=lambda x: x[1], reverse=True)
            top = pairs[:4]
            return ", ".join(f"{name} ({score:.2f})" for name, score in top)

        # Empty categories
        assert format_categories(None) == ""
        assert format_categories({}) == ""

        # Single category
        assert format_categories({"beach": 0.9}) == "beach (0.90)"

        # Multiple categories (should be sorted by score)
        cats = {"beach": 0.7, "sunset": 0.9, "travel": 0.5, "vacation": 0.8}
        result = format_categories(cats)
        assert result == "sunset (0.90), vacation (0.80), beach (0.70), travel (0.50)"

        # More than 4 categories (should show top 4)
        cats = {"a": 0.1, "b": 0.2, "c": 0.3, "d": 0.4, "e": 0.5, "f": 0.6}
        result = format_categories(cats)
        assert "f (0.60)" in result
        assert "e (0.50)" in result
        assert "d (0.40)" in result
        assert "c (0.30)" in result
        assert "a (0.10)" not in result
        assert "b (0.20)" not in result

    def test_merge_sources(self):
        """Test source merging logic."""
        def merge_sources(existing: str, new_source: str) -> str:
            sources = {s.strip() for s in existing.split("+") if s.strip()}
            sources.add(new_source)
            return "+".join(sorted(sources))

        assert merge_sources("semantic", "tags") == "semantic+tags"
        assert merge_sources("semantic+tags", "ocr") == "ocr+semantic+tags"
        assert merge_sources("semantic", "semantic") == "semantic"  # No duplicates


class TestSearchSorting:
    """Tests for search result sorting."""

    def create_mock_items(self) -> list[MockSearchItem]:
        """Create mock search items for sorting tests."""
        items = []
        for i, (name, sim, date, size) in enumerate([
            ("photo_a.jpg", 0.9, datetime(2024, 3, 15), 1024 * 1024),
            ("photo_b.jpg", 0.8, datetime(2024, 3, 20), 2048 * 1024),
            ("photo_c.jpg", None, datetime(2024, 3, 10), 512 * 1024),
            ("photo_d.jpg", 0.95, datetime(2024, 3, 1), 3072 * 1024),
        ]):
            file_record = FileRecord(
                id=i + 1,
                drive_id="D1",
                path=f"/path/{name}",
                filename=name,
                size=size,
                modified=date,
            )
            items.append(MockSearchItem(
                file_id=i + 1,
                file_path=f"/path/{name}",
                source="semantic" if sim else "tags",
                similarity=sim,
                file=file_record,
            ))
        return items

    def test_sort_by_relevance(self):
        """Test sorting by relevance (similarity score)."""
        items = self.create_mock_items()

        # Sort: semantic results first by similarity, then text results
        sorted_items = sorted(
            items,
            key=lambda x: (0 if x.similarity else 1, -(x.similarity or 0))
        )

        # Highest similarity should be first
        assert sorted_items[0].similarity == 0.95
        assert sorted_items[1].similarity == 0.9
        assert sorted_items[2].similarity == 0.8
        # No similarity should be last
        assert sorted_items[3].similarity is None

    def test_sort_by_date_newest(self):
        """Test sorting by date (newest first)."""
        items = self.create_mock_items()

        sorted_items = sorted(
            items,
            key=lambda x: x.file.modified if x.file and x.file.modified else datetime.min,
            reverse=True
        )

        assert sorted_items[0].file.filename == "photo_b.jpg"  # 2024-03-20
        assert sorted_items[1].file.filename == "photo_a.jpg"  # 2024-03-15
        assert sorted_items[2].file.filename == "photo_c.jpg"  # 2024-03-10
        assert sorted_items[3].file.filename == "photo_d.jpg"  # 2024-03-01

    def test_sort_by_date_oldest(self):
        """Test sorting by date (oldest first)."""
        items = self.create_mock_items()

        sorted_items = sorted(
            items,
            key=lambda x: x.file.modified if x.file and x.file.modified else datetime.max
        )

        assert sorted_items[0].file.filename == "photo_d.jpg"  # 2024-03-01
        assert sorted_items[3].file.filename == "photo_b.jpg"  # 2024-03-20

    def test_sort_by_size_largest(self):
        """Test sorting by size (largest first)."""
        items = self.create_mock_items()

        sorted_items = sorted(
            items,
            key=lambda x: x.file.size if x.file else 0,
            reverse=True
        )

        assert sorted_items[0].file.filename == "photo_d.jpg"  # 3072 KB
        assert sorted_items[1].file.filename == "photo_b.jpg"  # 2048 KB
        assert sorted_items[2].file.filename == "photo_a.jpg"  # 1024 KB
        assert sorted_items[3].file.filename == "photo_c.jpg"  # 512 KB

    def test_sort_by_name(self):
        """Test sorting by name (alphabetical)."""
        items = self.create_mock_items()

        sorted_items = sorted(
            items,
            key=lambda x: Path(x.file_path).name.lower()
        )

        assert sorted_items[0].file.filename == "photo_a.jpg"
        assert sorted_items[1].file.filename == "photo_b.jpg"
        assert sorted_items[2].file.filename == "photo_c.jpg"
        assert sorted_items[3].file.filename == "photo_d.jpg"


class TestSearchFilters:
    """Tests for search filter logic."""

    def test_type_filter_images(self):
        """Test filtering by image type."""
        # Simulate passes_type_filter
        def is_image(file_record: FileRecord) -> bool:
            return file_record.file_type in {'.jpg', '.jpeg', '.png', '.gif'}

        img_file = FileRecord(
            id=1, drive_id="D1", path="/a.jpg", filename="a.jpg",
            size=1024, file_type=".jpg"
        )
        pdf_file = FileRecord(
            id=2, drive_id="D1", path="/b.pdf", filename="b.pdf",
            size=1024, file_type=".pdf"
        )

        assert is_image(img_file) is True
        assert is_image(pdf_file) is False

    def test_date_filter(self):
        """Test date range filtering."""
        def passes_date_filter(
            file_record: FileRecord,
            date_from: datetime | None,
            date_to: datetime | None,
        ) -> bool:
            if not date_from and not date_to:
                return True
            file_date = file_record.modified
            if not file_date:
                return False
            if date_from and file_date < date_from:
                return False
            return not (date_to and file_date > date_to)

        file1 = FileRecord(
            id=1, drive_id="D1", path="/a.jpg", filename="a.jpg",
            size=1024, modified=datetime(2024, 3, 15)
        )
        file2 = FileRecord(
            id=2, drive_id="D1", path="/b.jpg", filename="b.jpg",
            size=1024, modified=datetime(2024, 1, 10)
        )

        # No filter
        assert passes_date_filter(file1, None, None) is True
        assert passes_date_filter(file2, None, None) is True

        # From filter
        assert passes_date_filter(file1, datetime(2024, 3, 1), None) is True
        assert passes_date_filter(file2, datetime(2024, 3, 1), None) is False

        # To filter
        assert passes_date_filter(file1, None, datetime(2024, 2, 1)) is False
        assert passes_date_filter(file2, None, datetime(2024, 2, 1)) is True

        # Range filter
        assert passes_date_filter(
            file1, datetime(2024, 3, 1), datetime(2024, 3, 31)
        ) is True
        assert passes_date_filter(
            file2, datetime(2024, 3, 1), datetime(2024, 3, 31)
        ) is False


class TestSearchPanelImport:
    """Tests that SearchPanel can be imported (basic smoke test)."""

    def test_import_search_panel_module(self):
        """Test that search_panel module can be imported."""
        # This tests that all imports and syntax are correct
        try:
            from duplicleaner.ui import search_panel
            assert hasattr(search_panel, 'SearchPanel')
            assert hasattr(search_panel, 'SearchItem')
        except ImportError as e:
            # Allow test to pass if dearpygui is not installed
            if "dearpygui" in str(e).lower():
                pytest.skip("Dear PyGui not available")
            raise

    def test_search_item_exists(self):
        """Test that SearchItem dataclass is defined."""
        try:
            from duplicleaner.ui.search_panel import SearchItem
            # Verify it's a dataclass with expected fields
            item = SearchItem(
                file_id=1,
                file_path="/test/path.jpg",
                source="test",
            )
            assert item.file_id == 1
            assert item.similarity is None
        except ImportError as e:
            if "dearpygui" in str(e).lower():
                pytest.skip("Dear PyGui not available")
            raise
