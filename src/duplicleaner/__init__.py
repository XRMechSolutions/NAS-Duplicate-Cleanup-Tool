"""DupliCleaner - NAS duplicate file cleanup and photo organization tool.

Copyright 2026 XRMech Solutions LLC
Author: Clinton Campbell
License: BSL 1.1

A Python application for identifying and removing duplicate files from NAS storage.
Features include exact and near-duplicate detection, photo organization by date/location,
AI-powered face recognition and scene classification, and semantic search.
"""

__version__ = "0.1.0"
__author__ = "Clinton Campbell"
__email__ = "clinton@xrmech.com"
__license__ = "BSL-1.1"

# Enable HEIC/HEIF support for PIL globally (Apple iPhone photos)
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass  # Optional dependency - gracefully degrade if not installed

try:
    from duplicleaner.app import DupliCleanerApp, run_app
except Exception:
    DupliCleanerApp = None
    run_app = None

__all__ = ["DupliCleanerApp", "run_app", "__version__"]
