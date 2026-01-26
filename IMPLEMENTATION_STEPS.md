# DupliCleaner - Implementation Steps

Quick reference for implementing the project. Full details in `PLAN.md` and `docs/`.

## Project Info
- **Name:** DupliCleaner (package: `duplicleaner`)
- **Author:** Clinton Campbell, XRMech Solutions LLC
- **License:** BSL 1.1
- **Stack:** Python 3.11+, Dear PyGui, SQLite, NVIDIA CUDA

---

## Phase 1: Project Foundation

### 1.1 Project Structure
```
duplicleaner/
├── src/duplicleaner/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py
│   ├── core/
│   ├── ai/
│   ├── db/
│   ├── ui/
│   └── utils/
├── tests/
├── resources/
├── pyproject.toml
└── requirements.txt
```

### 1.2 Setup Files
- [x] Create `pyproject.toml` (build config, dependencies, metadata)
- [x] Create `requirements.txt` (core deps)
- [x] Create `requirements-ai.txt` (optional AI deps)
- [x] Create `requirements-dev.txt` (pytest, mypy, ruff, black)
- [x] Setup logging infrastructure (`utils/logging.py`)
- [x] Setup config management (`utils/config.py`)

### 1.3 Database Setup
- [x] Create SQLite schema (`db/schema.sql`) - see PLAN.md for full schema
- [x] Create database manager (`db/database.py`)
- [x] Create data models (`db/models.py`) using dataclasses
- [x] Tables: drives, files, file_metadata, duplicate_groups, faces, persons, scene_analysis, action_log
- [x] Tables: ai_summaries, tags, file_tags (for AI content analysis)
- [x] Full-text search: ai_summaries_fts, ocr_fts with triggers

### 1.4 Basic UI Shell
- [x] Dear PyGui app initialization (`app.py`)
- [x] Main window with tab bar: Drives, Duplicates, Photos, Faces, Search, Settings
- [x] Status bar (file count, storage, GPU status)
- [x] Left panel placeholder
- [x] Main content area placeholder

---

## Phase 2: Core Scanning & Hashing

### 2.1 Scanner Module (`core/scanner.py`)
- [x] Recursive directory walker using `os.scandir()`
- [x] UNC path support (`\\server\share`)
- [x] Collect metadata: path, size, created, modified, type
- [x] Ignore patterns (configurable, smart defaults)
- [x] Progress callbacks for UI
- [x] Pause/resume/cancel support
- [x] Error handling (permissions, disconnections)

### 2.2 Hasher Module (`core/hasher.py`)
- [x] xxHash for quick hash (first+last 64KB)
- [x] SHA-256 for full verification
- [x] Chunked reading (1MB chunks)
- [x] Size-based grouping optimization
- [x] Hash caching in database

### 2.3 Drive Manager (`drives/manager.py`)
- [x] Drive registration and tracking
- [x] Connection status monitoring
- [x] Space usage reporting
- [x] UNC path normalization

### 2.4 Drives UI (`ui/drives_panel.py`)
- [x] Drive list view
- [x] Add/remove drives
- [x] Scan buttons (Quick/Deep/Full)
- [x] Progress display

---

## Phase 3: Duplicate Detection

### 3.1 Comparator Module (`core/comparator.py`)
- [x] Exact duplicate grouping (by SHA-256)
- [x] Perceptual hashing for images (imagehash library)
- [x] pHash, dHash, aHash computation
- [x] Similarity threshold (configurable)
- [x] Cross-format matching (JPEG/PNG/HEIC)
- [x] Duplicate group formation

### 3.2 Resolver Module (`core/resolver.py`)
- [x] Keep strategies: newest, oldest, largest, best quality, specific drive, shortest path
- [x] Auto-select logic
- [x] Manual override support

### 3.3 Duplicates UI (`ui/duplicates_panel.py`)
- [x] Duplicate groups list/grid
- [x] Thumbnail previews
- [x] Side-by-side comparison
- [x] Selection checkboxes
- [x] Bulk action buttons
- [x] Filters (type, drive, size)

---

## Phase 4: Photo Organization

### 4.1 Organizer Module (`core/organizer.py`)
- [x] EXIF extraction (Pillow + exifread)
- [x] Date parsing (python-dateutil)
- [x] Folder structure generation (YYYY/MM, YYYY/MM-Month, etc.)
- [x] GPS reverse geocoding (geopy with caching)
- [x] Event clustering by time gaps
- [x] Smart file renaming with patterns
- [x] Screenshot detection (dimensions, patterns, EXIF)
- [x] Burst photo detection
- [x] Dry-run mode
- [x] Progress tracking with cancel support
- [x] Conflict resolution options

### 4.2 Photo Organizer UI (`ui/organize_panel.py` - Photos tab)
- [x] Source/destination folder selection
- [x] Organization settings (date format, location, events)
- [x] File naming settings (patterns, conflicts)
- [x] Special handling (screenshots, undated files)
- [x] Preview with folder tree and file list
- [x] Progress display
- [x] Export preview as CSV

---

## Phase 5: File Operations

### 5.1 Action Engine (`core/actions.py`)
- [x] Quarantine (move to folder with date-based organization)
- [x] Move to trash (send2trash)
- [x] Permanent delete
- [x] Copy/move files with verification
- [x] Hard link creation
- [x] Symbolic link creation
- [x] Audit logging (every action)
- [x] Undo support (single and batch)
- [x] Progress tracking with pause/resume/cancel
- [x] Dry-run mode
- [x] Protected system folder checks

### 5.2 Action Log UI (`ui/action_log_panel.py`)
- [x] Action history list with table view
- [x] Filters (action type, date range, status)
- [x] Pagination support
- [x] Undo button (single and batch)
- [x] Export log (CSV, JSON, HTML)
- [x] Quarantine management (browse, restore, empty)

---

## Phase 5.5: AI Infrastructure

### 5.5.1 Secure Key Storage (`utils/keystore.py`)
- [x] KeyStore class with Windows DPAPI/keyring integration
- [x] AIProvider enum (OpenAI, Anthropic, Google, Ollama)
- [x] Secure storage/retrieval/deletion of API keys
- [x] Key format validation
- [x] Fallback file storage with obfuscation

### 5.5.2 AI Configuration (`utils/config.py`)
- [x] Detailed AISettings with model configuration
- [x] Local model settings (InsightFace, CLIP, YOLO, EasyOCR)
- [x] Cloud API model settings (OpenAI, Anthropic, Google)
- [x] Summary generation settings
- [x] Auto-tagging settings
- [x] Processing preferences (images, documents, videos)

### 5.5.3 AI Database Models
- [x] AISummary dataclass with rich fields
- [x] Tag and FileTag dataclasses
- [x] TagCategory and TagSource enums
- [x] Enhanced Person dataclass (birth_year, notes, favorites)

### 5.5.4 AI Database Operations
- [x] CRUD for ai_summaries table
- [x] CRUD for tags table
- [x] CRUD for file_tags table
- [x] Full-text search via FTS5
- [x] Combined search across summaries, OCR, and tags
- [x] Popular tags query
- [x] Files needing summary query

---

## Phase 6: AI - Face & Pet Recognition

---

## Test Plan Updates

- [x] DriveManager: distinct folder IDs on same volume
- [ ] Drives UI: single-selection behavior (manual)
- [ ] Drives UI: hash-only shows progress (manual)
- [ ] Drives UI: status auto-refresh on connect/disconnect (manual)
- [ ] Drives UI: scan all runs sequentially and completes (manual)
- [ ] Drives UI: remove confirmation dialog (manual)

### 6.1 Face Analyzer (`ai/faces.py`)
- [x] InsightFace model download/loading (buffalo_l)
- [x] Face detection with RetinaFace
- [x] Embedding extraction (512-dim ArcFace)
- [x] Face clustering (scikit-learn DBSCAN)
- [x] Person matching with similarity scores
- [x] Age estimation from InsightFace
- [x] Temporal bridging for age progression
- [x] Multi-embedding storage per person
- [x] Similar face search

### 6.2 Pet Analyzer (`ai/pets.py`)
- [x] Pet detection via YOLOv8 (COCO animal classes)
- [x] Species classification (dog, cat, bird, etc.)
- [x] Color histogram extraction for matching
- [x] Age stage estimation (baby, young, adult, senior)
- [x] Pet clustering by species and color
- [x] Pet matching and assignment
- [x] Timeline view support

### 6.3 Faces/Pets UI (`ui/faces_panel.py`)
- [x] Cluster view (unknown faces/pets)
- [x] People view (named individuals)
- [x] Pets view (named pets)
- [x] Name assignment dialog (person and pet)
- [x] Age timeline view (people and pets)
- [x] Find more photos button
- [x] Pet species/breed editing
- [x] Analysis progress tracking with cancel

---

## Phase 7: AI - Content Analysis

### 7.1 Scene Classifier (`ai/scenes.py`)
- [x] CLIP model loading (open-clip-torch)
- [x] Scene category classification
- [x] Custom category support
- [x] Semantic search encoding

### 7.2 Object Detector (`ai/objects.py`)
- [x] YOLOv8 loading (ultralytics)
- [x] Object detection and tagging

### 7.3 Quality Scorer (`ai/quality.py`)
- [x] Blur detection (Laplacian)
- [x] Exposure analysis
- [x] Overall quality score

### 7.4 OCR (`ai/ocr.py`)
- [x] EasyOCR integration
- [x] Text extraction from images
- [x] Text indexing for search

### 7.5 Search UI (`ui/search_panel.py`)
- [x] Semantic search box
- [x] Results grid
- [x] Filters (date, person, type)

---

## Phase 8: Document Versioning

### 8.1 Version Tracker (`core/versioning.py`)
- [x] GitPython integration
- [x] Folder tracking setup
- [x] Automatic commits on file save
- [x] Version history retrieval
- [x] Restore previous versions
- [x] Diff generation

### 8.2 Versioning UI
- [x] Settings panel for tracked folders
- [x] Version history viewer
- [x] Restore dialog

### 8.5 Multi-Drive Features (implemented early from PLAN.md)
- [x] Cross-drive duplicate analysis (hash groups across drives)
- [x] Redundancy report (at-risk files, basic UI)
- [x] Backup suggestions (plan preview + execute)
- [x] Sync/copy operations
- [x] Drive health monitoring (status/space/last scan)

### 8.3 Future Enhancement (plan before implementing)
- [ ] Binary text diffs via extraction + diff: Office (DOCX/DOC, XLSX/XLS, PPTX/PPT), docs (PDF/RTF/ODT/EPUB), email (EML/MSG), web (HTML/HTM), structured text (CSV/JSON/XML); optional OCR for images/scans

---

## Phase 9: Polish & Distribution

### 9.1 First-Run Experience
- [x] Setup wizard
- [x] Initial drive selection
- [x] AI model download prompt
- [x] Settings configuration

### 9.2 Settings UI (`ui/settings_panel.py`)
- [ ] All configurable options
- [x] AI model management
- [ ] Database management
- [ ] Logging level

### 9.3 Installer
- [ ] PyInstaller executable
- [ ] Windows MSI installer
- [ ] Auto-update mechanism

### 9.4 Testing
- [ ] Unit tests for all core modules
- [ ] Integration tests for workflows
- [ ] CI/CD with GitHub Actions

---

## Key Libraries

| Purpose | Library |
|---------|---------|
| UI | dearpygui |
| Image hashing | imagehash |
| Image processing | pillow, exifread |
| Fast hashing | xxhash |
| Database | sqlite3 (built-in) |
| Face recognition | insightface, onnxruntime |
| Scene/search | open-clip-torch |
| Object detection | ultralytics |
| OCR | easyocr |
| Geocoding | geopy |
| Version tracking | gitpython |
| Video frames | ffmpeg-python |

---

## Key Decisions Reference

- **UI:** Dear PyGui (GPU-accelerated desktop)
- **Database:** SQLite (settings + thumbnails + all data)
- **AI Models:** Per-user AppData, download on first use
- **Concurrency:** Full multitasking (background operations)
- **Delete modes:** Quarantine, trash, hard delete (all available)
- **Near-dupe threshold:** User-configurable
- **Cross-format:** JPEG/PNG/HEIC matched as duplicates
- **Windows:** 10+ only
- **Logging:** Verbose, configurable levels

---

## Documentation Reference

All detailed specs in `docs/`:
1. `01-scanner.md` - File scanning
2. `02-hasher.md` - Hash computation
3. `03-duplicate-detection.md` - Duplicate finding
4. `04-drive-manager.md` - Multi-drive support
5. `05-photo-organization.md` - Photo sorting
6. `06-face-recognition.md` - Face AI
7. `07-ai-content-analysis.md` - Scene/object AI
8. `08-duplicate-resolution.md` - Keep strategies
9. `09-file-operations.md` - Delete/quarantine
10. `10-database.md` - Data storage
11. `11-user-interface.md` - UI guide
12. `12-document-versioning.md` - Git versioning
