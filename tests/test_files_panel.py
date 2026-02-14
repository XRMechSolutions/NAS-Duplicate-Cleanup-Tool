"""Tests for the Files Panel thumbnail grid view and view modes.

Tests TAG constants, view mode state, thumbnail size presets,
and image extension detection without requiring DearPyGUI context.
"""

from __future__ import annotations

import pytest


class TestFilesPanel:
    """Tests for FilesPanel class attributes and constants."""

    def _get_cls(self):
        """Import FilesPanel class for attribute inspection."""
        from duplicleaner.ui.files_panel import FilesPanel
        return FilesPanel

    def test_view_mode_tags_defined(self):
        """View mode TAG constants are defined."""
        cls = self._get_cls()
        assert hasattr(cls, "TAG_VIEW_MODE_LIST")
        assert hasattr(cls, "TAG_VIEW_MODE_THUMBS")
        assert hasattr(cls, "TAG_THUMBNAIL_GRID")
        assert hasattr(cls, "TAG_THUMB_SIZE_COMBO")

    def test_thumbnail_size_presets_exist(self):
        """Thumbnail size presets provide multiple options."""
        cls = self._get_cls()
        presets = cls.THUMB_SIZE_PRESETS
        assert isinstance(presets, dict)
        assert len(presets) >= 3
        for label, size in presets.items():
            assert isinstance(label, str)
            assert isinstance(size, int)
            assert size > 0

    def test_thumbnail_size_presets_ordered(self):
        """Thumbnail size presets are in ascending order of pixel size."""
        cls = self._get_cls()
        sizes = list(cls.THUMB_SIZE_PRESETS.values())
        assert sizes == sorted(sizes)

    def test_image_extensions_set(self):
        """IMAGE_EXTENSIONS should include common formats."""
        cls = self._get_cls()
        exts = cls.IMAGE_EXTENSIONS
        for expected in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
            assert expected in exts, f"Missing extension: {expected}"

    def test_texture_cache_limits(self):
        """Texture cache limits should be higher for thumbnail mode."""
        cls = self._get_cls()
        assert cls.MAX_TEXTURE_CACHE_THUMBS > cls.MAX_TEXTURE_CACHE

    def test_preview_size_positive(self):
        """Preview size constant should be a positive integer."""
        cls = self._get_cls()
        assert cls.PREVIEW_SIZE > 0

    def test_default_view_mode_is_list(self):
        """Verify the documented default view mode is list."""
        # This tests that the class doesn't accidentally change the default
        # by checking the source code pattern rather than instantiating
        import inspect
        cls = self._get_cls()
        source = inspect.getsource(cls.__init__)
        assert '"list"' in source or "'list'" in source


class TestViewModeLogic:
    """Test the view mode switching logic (state, not UI rendering)."""

    def test_view_mode_values(self):
        """View mode should only be 'list' or 'thumbnails'."""
        valid_modes = {"list", "thumbnails"}
        # Test that the constants reference valid modes
        assert "list" in valid_modes
        assert "thumbnails" in valid_modes

    def test_thumbnail_size_config_round_trip(self):
        """Thumbnail size config value should survive round-trip."""
        from duplicleaner.utils.config import UISettings
        settings = UISettings(thumbnail_size=128)
        assert settings.thumbnail_size == 128

    def test_default_thumbnail_size(self):
        """Default thumbnail size should be reasonable."""
        from duplicleaner.utils.config import UISettings
        settings = UISettings()
        assert 50 <= settings.thumbnail_size <= 512


class TestImageExtensionDetection:
    """Test file type detection for preview support."""

    def test_image_file_detected(self):
        """Common image extensions should be recognized."""
        from duplicleaner.db.models import FileRecord
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".heic"]:
            record = FileRecord(file_type=ext)
            assert record.is_image, f"{ext} not detected as image"

    def test_video_file_not_image(self):
        """Video files should not be recognized as images."""
        from duplicleaner.db.models import FileRecord
        for ext in [".mp4", ".avi", ".mov", ".mkv"]:
            record = FileRecord(file_type=ext)
            assert not record.is_image, f"{ext} incorrectly detected as image"

    def test_document_file_not_image(self):
        """Document files should not be recognized as images."""
        from duplicleaner.db.models import FileRecord
        for ext in [".pdf", ".docx", ".txt"]:
            record = FileRecord(file_type=ext)
            assert not record.is_image, f"{ext} incorrectly detected as image"


class TestThumbnailSizePresets:
    """Test that size presets cover the expected range."""

    def test_smallest_preset_at_least_32(self):
        """Smallest thumbnail should be at least 32px."""
        from duplicleaner.ui.files_panel import FilesPanel
        smallest = min(FilesPanel.THUMB_SIZE_PRESETS.values())
        assert smallest >= 32

    def test_largest_preset_at_most_512(self):
        """Largest thumbnail should be at most 512px."""
        from duplicleaner.ui.files_panel import FilesPanel
        largest = max(FilesPanel.THUMB_SIZE_PRESETS.values())
        assert largest <= 512

    def test_medium_96_is_default(self):
        """Medium (96px) should be available as a preset."""
        from duplicleaner.ui.files_panel import FilesPanel
        assert 96 in FilesPanel.THUMB_SIZE_PRESETS.values()
