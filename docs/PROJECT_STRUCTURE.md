# DupliCleaner Project Structure

Quick reference for navigating the codebase.

## Source Code: `src/duplicleaner/`

```
src/duplicleaner/
├── __init__.py                    - Package version and metadata
├── __main__.py                    - CLI entry point, argument parsing
├── app.py                         - Main application class, UI setup, event loop
│
├── ai/                            - AI/ML analysis modules
│   ├── __init__.py
│   ├── content_summarizer.py      - Batch file summarization (images, docs, video, audio)
│   ├── documents.py               - Document type classification
│   ├── faces.py                   - Face detection, clustering, recognition, age-progression
│   ├── model_manager.py           - ML model lifecycle (download, load, unload)
│   ├── objects.py                 - YOLO object detection
│   ├── ocr.py                     - Text extraction (EasyOCR, Tesseract)
│   ├── pets.py                    - Pet detection, color matching, clustering
│   ├── quality.py                 - Image quality scoring (blur, exposure, noise, contrast)
│   ├── scenes.py                  - CLIP scene classification
│   └── summaries.py               - LLM-based content summaries (LMStudio, Ollama, cloud)
│
├── core/                          - Core business logic
│   ├── __init__.py
│   ├── actions.py                 - File operations engine (delete, trash, quarantine, move)
│   ├── analysis_runner.py         - Orchestrates multi-step AI analysis
│   ├── comparator.py              - Near-duplicate detection (perceptual hashing)
│   ├── face_worker.py             - Background face processing thread
│   ├── hasher.py                  - File hashing (xxHash fast, SHA-256 verify)
│   ├── metadata_extractor.py      - EXIF/GPS extraction, reverse geocoding
│   ├── organizer.py               - Photo organization (date, location, events, bursts, screenshots)
│   ├── resolver.py                - Duplicate group resolution strategies
│   ├── scanner.py                 - Recursive file system walker
│   ├── versioning.py              - Git-based document version tracking
│   └── versioning_service.py      - Version tracking service layer
│
├── db/                            - Database layer
│   ├── __init__.py
│   ├── database.py                - SQLite interface (all queries, ~2000 lines)
│   ├── models.py                  - Dataclasses (FileRecord, Person, Face, Pet, etc.)
│   └── schema.sql                 - Table definitions, indexes, triggers
│
├── drives/                        - Multi-drive management
│   ├── __init__.py
│   ├── manager.py                 - Drive registration, file-to-drive mapping
│   └── redundancy.py              - Cross-drive backup verification
│
├── ui/                            - DearPyGUI interface
│   ├── __init__.py
│   ├── action_log_panel.py        - Audit log viewer
│   ├── documentation_panel.py     - In-app documentation viewer
│   ├── drives_panel.py            - Drive management UI
│   ├── duplicates_panel.py        - Duplicate groups browser and actions
│   ├── faces_panel.py             - Face clusters, person management, preview (~5000 lines)
│   ├── files_panel.py             - File browser with folder tree (not yet integrated)
│   ├── organize_panel.py          - Photo organization wizard
│   ├── search_panel.py            - Full-text and semantic search
│   ├── status_log_panel.py        - Real-time status and progress
│   ├── theme.py                   - Color scheme, fonts, spacing
│   └── tooltips.py                - UI help text and descriptions
│
└── utils/                         - Shared utilities
    ├── __init__.py
    ├── config.py                  - Settings management (all configurable values)
    ├── keystore.py                - Secure API key storage (Windows DPAPI)
    ├── lmstudio_manager.py        - LMStudio model detection and switching
    ├── logging.py                 - Log setup, rotation, formatting
    ├── profiling.py               - Performance profiling (opt-in)
    ├── jpeg_recovery.py           - Base JPEG recovery (PIL tolerant mode)
    ├── jpeg_binary_repair.py      - Binary marker reconstruction
    ├── jpeg_smart_recovery.py     - Multi-SOI stream extraction
    ├── jpeg_aggressive_recovery.py - Severe corruption recovery
    ├── jpeg_deep_recovery.py      - Error-tolerant decoding
    ├── jpeg_fragment_separator.py - Multi-photo extraction from corrupt files
    ├── jpeg_gap_filler.py         - Thumbnail upscale gap filling
    └── jpeg_hybrid_recovery.py    - Combined recovery strategies
```

## Tests: `tests/`

```
tests/
├── conftest.py                    - Shared fixtures, temp DB setup
├── fixtures/
│   └── fs_builder.py              - File system builder for test scenarios
│
├── test_actions.py                - ActionEngine operations
├── test_ai_smoke.py               - AI module import and basic function tests
├── test_comparator.py             - Perceptual hash comparison
├── test_database_comprehensive.py - Full database CRUD coverage
├── test_db_datetime.py            - Date/time handling edge cases
├── test_db_integrity.py           - Foreign keys, constraints, migrations
├── test_db_schema.py              - Schema validation
├── test_docs_available.py         - Documentation file existence checks
├── test_drive_manager.py          - Drive registration and mapping
├── test_duplicates_actions.py     - Duplicate group actions
├── test_faces_functionality.py    - Face detection and clustering
├── test_hasher.py                 - Hash computation and verification
├── test_integration_actions.py    - End-to-end action workflows
├── test_integration_pipeline.py   - Full scan-to-resolution pipeline
├── test_organizer.py              - Organization logic
├── test_organizer_ai.py           - Organization with AI features
├── test_organizer_execute.py      - Organization file operations
├── test_performance_smoke.py      - Performance benchmarks
├── test_person_gallery.py         - Person/face gallery features
├── test_redundancy.py             - Cross-drive redundancy
├── test_resolver.py               - Duplicate resolution strategies
├── test_resolver_comprehensive.py - Resolver edge cases
├── test_scanner.py                - File system scanning
├── test_search_panel.py           - Search functionality
├── test_snapshots.py              - Snapshot/state tests
├── test_ui_smoke.py               - UI initialization
├── test_versioning.py             - Version tracking
└── test_versioning_service.py     - Version service operations
```

## Documentation: `docs/`

```
docs/
├── 01-scanner.md                  - File scanning architecture
├── 02-hasher.md                   - Hashing strategy and algorithms
├── 03-duplicate-detection.md      - Exact and near-duplicate detection
├── 04-drive-manager.md            - Multi-drive coordination
├── 05-photo-organization.md       - Photo organization features
├── 06-face-recognition.md         - Face detection and recognition
├── 07-ai-content-analysis.md      - AI analysis pipeline
├── 08-duplicate-resolution.md     - Resolution strategies and rules
├── 09-file-operations.md          - Safe file operations and audit
├── 10-database.md                 - Database schema and queries
├── 11-user-interface.md           - DearPyGUI interface design
├── 12-document-versioning.md      - Git-based version tracking
├── USER_GUIDE.md                  - End-user documentation
├── PROJECT_STRUCTURE.md           - This file
│
└── planning/                      - Future feature specifications
    ├── age-progression-face-recognition.md
    ├── ai-analysis-ui-controls.md
    ├── ai-metadata-embedding.md
    ├── audio-transcription-integration.md
    ├── celebrity-face-identification.md
    ├── cross-format-deduplication.md
    ├── document-corpus-analysis.md
    ├── export-and-reporting.md
    ├── family-groups-and-relationships.md
    ├── folder-watching-auto-organization.md
    ├── intelligent-face-assignment.md
    ├── jpeg-corrupt-file-recovery.md
    ├── live-photo-video-matching-enhancements.md
    ├── pet-detection-and-tracking.md
    ├── quality-based-duplicate-selection.md
    ├── screenshot-and-burst-detection.md
    ├── side-by-side-comparison-enhancements.md
    ├── storage-analytics.md
    ├── undo-rollback-system.md
    └── video-near-duplicate-detection.md
```

## Root Configuration

```
CLAUDE.md                          - Claude Code project instructions
pyproject.toml                     - Package metadata, build config
requirements.txt                   - Core dependencies
requirements-ai.txt                - AI/ML optional dependencies
requirements-dev.txt               - Development/testing dependencies
start-duplicleaner.bat             - Windows launcher
.github/workflows/tests.yml       - CI/CD pipeline
```

## Key File Size Reference

| File | Lines | Role |
|---|---|---|
| `ui/faces_panel.py` | ~5000 | Largest UI panel (face management, preview, assignment) |
| `db/database.py` | ~2000 | All database queries and operations |
| `ai/faces.py` | ~1500 | Face detection, clustering, age-progression, matching |
| `app.py` | ~1400 | Main application setup, settings, tab creation |
| `ui/files_panel.py` | ~1900 | File browser (not yet integrated into main app) |
| `ai/content_summarizer.py` | ~930 | Batch summarization across all file types |
| `core/organizer.py` | ~1000 | Photo organization with screenshots, bursts, events |
| `ai/pets.py` | ~900 | Pet detection, color matching, clustering |
| `ui/duplicates_panel.py` | ~800 | Duplicate group browser and actions |
| `ui/organize_panel.py` | ~800 | Organization wizard UI |
