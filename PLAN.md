# DupliCleaner - Project Plan

**Application Name:** DupliCleaner
**Package Name:** duplicleaner
**Copyright:** 2026 XRMech Solutions LLC
**Author:** Clinton Campbell
**License:** Business Source License 1.1 (BSL 1.1) - Converts to MIT on 2030-01-01

## Decisions Summary

| Decision | Choice |
|----------|--------|
| UI Framework | Dear PyGui (GPU-accelerated desktop app) |
| Scale | Multi-drive, unknown size, must handle large collections |
| GPU | NVIDIA GPU with CUDA support |
| Delete Modes | All options (quarantine, trash, hard delete + audit log) |
| Drive Strategy | Consolidate duplicates + verify backup redundancy |
| Current State | Partially organized drives |
| File Types | All files (special handling for media) |
| MVP Scope | Full feature set |
| AI Models | Download on first use, stored in per-user AppData |
| Persistence | Full SQLite database |
| Network Paths | UNC paths (\\\\server\\share format) |
| Scan Strategy | Quick scan (mtime check) + deep scan option |
| Python Version | 3.11+ |
| Windows Version | Windows 10+ only |
| Distribution | Windows installer (.msi) with auto-update |
| Settings Storage | In SQLite database |
| Concurrency | Full multitasking (background operations) |
| License | BSL 1.1 (source-available, converts to MIT 2030) |
| First Run | Setup wizard for initial configuration |
| Thumbnails | Stored in SQLite as BLOBs |
| Logging | Verbose with configurable levels |
| Testing | Unit tests + integration tests |
| Near-dupe Threshold | User-configurable in settings |
| Cross-format Matching | Yes (JPEG, PNG, HEIC matched as duplicates) |
| Document Versioning | Git-based (GitPython), user-selected folders |

---

## Architecture Overview

```
+------------------------------------------------------------------+
|                        Dear PyGui UI                              |
|  +------------+  +------------+  +------------+  +------------+   |
|  |   Drives   |  |   Scan     |  | Duplicates |  |   Photos   |   |
|  |   Panel    |  |   Progress |  |   Review   |  |  Organizer |   |
|  +------------+  +------------+  +------------+  +------------+   |
|  +------------+  +------------+  +------------+  +------------+   |
|  |   Faces    |  |   Search   |  |  Settings  |  |   Actions  |   |
|  |   Gallery  |  |   Results  |  |   Panel    |  |    Log     |   |
|  +------------+  +------------+  +------------+  +------------+   |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                      Core Engine Layer                            |
|  +-------------+  +-------------+  +-------------+                |
|  |   Scanner   |  |   Hasher    |  |  Comparator |                |
|  +-------------+  +-------------+  +-------------+                |
|  +-------------+  +-------------+  +-------------+                |
|  |  Organizer  |  | AIAnalyzer  |  |  Resolver   |                |
|  +-------------+  +-------------+  +-------------+                |
|  +-------------+  +-------------+                                 |
|  | DriveManager|  |ActionEngine |                                 |
|  +-------------+  +-------------+                                 |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                       Data Layer                                  |
|  +---------------------------+  +---------------------------+     |
|  |    SQLite Database        |  |    File System Access     |     |
|  |  - files, hashes, faces   |  |  - multi-drive support    |     |
|  |  - duplicates, clusters   |  |  - network paths          |     |
|  |  - embeddings, metadata   |  |  - permission handling    |     |
|  +---------------------------+  +---------------------------+     |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
|                    AI/ML Layer (Optional)                         |
|  +-------------+  +-------------+  +-------------+                |
|  | InsightFace |  |    CLIP     |  |   YOLOv8    |                |
|  | (faces)     |  | (semantic)  |  | (objects)   |                |
|  +-------------+  +-------------+  +-------------+                |
|  +-------------+  +-------------+                                 |
|  |  EasyOCR    |  | ImageQuality|                                 |
|  | (text)      |  | (scoring)   |                                 |
|  +-------------+  +-------------+                                 |
+------------------------------------------------------------------+
```

---

## Module Specifications

### 1. Scanner Module
**Purpose**: Recursively walk directories, collect file metadata

**Responsibilities**:
- Enumerate files across multiple drives/mount points
- Collect: path, size, created/modified dates, file type
- Handle permission errors gracefully
- Support pause/resume scanning
- Track scan progress for UI updates
- Detect drive disconnection during scan

**Key Classes**:
```python
class DriveSource:
    path: Path
    label: str  # User-friendly name
    drive_id: str  # Unique identifier
    is_connected: bool

class FileRecord:
    id: int
    path: str
    drive_id: str
    size: int
    created: datetime
    modified: datetime
    file_type: str  # extension or MIME
    content_hash: Optional[str]
    perceptual_hash: Optional[str]
    scan_date: datetime
```

### 2. Hasher Module
**Purpose**: Compute file hashes for duplicate detection

**Responsibilities**:
- Compute xxHash (fast) for initial comparison
- Compute SHA-256 for verification
- Chunked reading for large files (stream, don't load into memory)
- Skip hashing if size is unique (optimization)
- Cache hashes in database

**Strategy**:
1. Group files by size
2. For size groups > 1 file, compute quick hash (first 64KB + last 64KB)
3. For quick hash matches, compute full hash
4. Store results in database

### 3. Comparator Module
**Purpose**: Find exact and near-duplicates

**Responsibilities**:
- Exact duplicates: match on full content hash
- Near-duplicate images: perceptual hash (pHash, dHash)
- Near-duplicate videos: frame sampling + perceptual hash
- Configurable similarity threshold
- Group duplicates into clusters

**Key Classes**:
```python
class DuplicateGroup:
    id: int
    match_type: Literal["exact", "near"]
    similarity: float  # 1.0 for exact
    files: List[FileRecord]
    recommended_keep: Optional[FileRecord]
    recommendation_reason: str

class ComparisonResult:
    groups: List[DuplicateGroup]
    total_wasted_space: int
    files_analyzed: int
```

### 4. DriveManager Module
**Purpose**: Multi-drive coordination and redundancy checking

**Responsibilities**:
- Track which drives are registered and connected
- Map files to drives
- Identify "at-risk" files (exist on only one drive)
- Suggest backup operations
- Handle drive mount/unmount events

**Key Classes**:
```python
class DriveStatus:
    drive: DriveSource
    total_space: int
    free_space: int
    file_count: int
    last_scan: datetime
    health: Literal["connected", "disconnected", "error"]

class RedundancyReport:
    files_single_copy: List[FileRecord]  # At risk
    files_multi_copy: List[FileRecord]   # Safe
    suggested_backups: List[Tuple[FileRecord, DriveSource]]  # What to copy where
```

### 5. Organizer Module
**Purpose**: Photo/video organization using metadata

**Responsibilities**:
- Extract EXIF metadata (date, GPS, camera)
- Parse various date formats
- Build folder structure (YYYY/MM or YYYY/MM/DD)
- Reverse geocode GPS to location names
- Rename files intelligently
- Detect screenshots, bursts, Live Photos

**Organization Modes**:
```python
class OrganizationConfig:
    date_format: str  # "YYYY/MM", "YYYY/MM/DD", "YYYY/YYYY-MM-DD"
    include_location: bool
    group_by_event: bool  # Cluster by time proximity
    separate_screenshots: bool
    separate_videos: bool
    rename_pattern: Optional[str]  # e.g., "{date}_{location}_{seq}"
```

### 6. AI Analyzer Module
**Purpose**: Face recognition, scene classification, content analysis

**Sub-modules**:

#### 6a. Face Analyzer
- Detect faces using InsightFace
- Extract face embeddings (512-dim vectors)
- Cluster unknown faces
- Match faces to known identities
- Handle age progression (temporal bridging)
- Age/gender estimation

```python
class FaceRecord:
    id: int
    file_id: int
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    embedding: bytes  # 512 floats serialized
    person_id: Optional[int]
    confidence: float
    estimated_age: Optional[int]

class Person:
    id: int
    name: str
    reference_faces: List[int]  # Multiple embeddings at different ages
    photo_count: int
```

#### 6b. Scene Classifier
- Use CLIP for zero-shot classification
- Predefined categories + custom labels
- Confidence scores per category

```python
SCENE_CATEGORIES = [
    "beach", "mountain", "forest", "city", "indoor",
    "restaurant", "party", "wedding", "birthday",
    "sports", "travel", "nature", "portrait", "group photo",
    "document", "screenshot", "meme", "artwork"
]

class SceneAnalysis:
    file_id: int
    categories: Dict[str, float]  # category -> confidence
    objects: List[str]  # Detected objects
    description: Optional[str]  # CLIP-generated caption
```

#### 6c. Quality Scorer
- Blur detection (Laplacian variance)
- Exposure analysis (histogram)
- Composition scoring
- Resolution consideration

```python
class QualityScore:
    file_id: int
    blur_score: float  # 0-1, higher = sharper
    exposure_score: float  # 0-1, 0.5 = ideal
    overall_score: float
```

### 7. Resolver Module
**Purpose**: Decide which duplicates to keep/remove

**Strategies**:
```python
class ResolutionStrategy(Enum):
    KEEP_NEWEST = "keep_newest"
    KEEP_OLDEST = "keep_oldest"
    KEEP_LARGEST = "keep_largest"  # Higher resolution
    KEEP_BEST_QUALITY = "keep_best_quality"  # AI quality score
    KEEP_SHORTEST_PATH = "keep_shortest_path"
    KEEP_ON_DRIVE = "keep_on_drive"  # Prefer specific drive
    MANUAL = "manual"  # User decides each

class Resolution:
    group: DuplicateGroup
    keep: FileRecord
    remove: List[FileRecord]
    strategy_used: ResolutionStrategy
    user_confirmed: bool
```

### 8. Action Engine Module
**Purpose**: Execute file operations safely

**Responsibilities**:
- Move to quarantine folder
- Move to system trash
- Hard delete with audit log
- Create hard links (dedupe without deleting)
- Create symbolic links
- Copy files for backup redundancy
- Undo capability (from audit log)

```python
class ActionLog:
    id: int
    timestamp: datetime
    action_type: Literal["delete", "quarantine", "trash", "link", "copy", "move"]
    source_path: str
    destination_path: Optional[str]
    file_hash: str
    file_size: int
    reversible: bool
    reversed: bool
```

---

## Database Schema

```sql
-- Drives/sources
CREATE TABLE drives (
    id TEXT PRIMARY KEY,
    label TEXT,
    path TEXT,
    last_scan TIMESTAMP,
    total_space INTEGER,
    free_space INTEGER
);

-- All scanned files
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    drive_id TEXT REFERENCES drives(id),
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    created TIMESTAMP,
    modified TIMESTAMP,
    file_type TEXT,
    mime_type TEXT,
    content_hash TEXT,
    quick_hash TEXT,
    perceptual_hash TEXT,
    scan_date TIMESTAMP,
    UNIQUE(drive_id, path)
);

-- EXIF and metadata
CREATE TABLE file_metadata (
    file_id INTEGER PRIMARY KEY REFERENCES files(id),
    exif_date TIMESTAMP,
    gps_lat REAL,
    gps_lon REAL,
    location_name TEXT,
    camera_make TEXT,
    camera_model TEXT,
    width INTEGER,
    height INTEGER,
    duration_seconds REAL,  -- For videos
    raw_exif JSON
);

-- Duplicate groups
CREATE TABLE duplicate_groups (
    id INTEGER PRIMARY KEY,
    match_type TEXT,  -- 'exact' or 'near'
    similarity REAL,
    file_count INTEGER,
    total_size INTEGER,
    wasted_size INTEGER,
    status TEXT  -- 'pending', 'resolved', 'ignored'
);

CREATE TABLE duplicate_members (
    group_id INTEGER REFERENCES duplicate_groups(id),
    file_id INTEGER REFERENCES files(id),
    is_keeper BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (group_id, file_id)
);

-- Face recognition
CREATE TABLE faces (
    id INTEGER PRIMARY KEY,
    file_id INTEGER REFERENCES files(id),
    person_id INTEGER REFERENCES persons(id),
    bbox_x INTEGER,
    bbox_y INTEGER,
    bbox_w INTEGER,
    bbox_h INTEGER,
    embedding BLOB,  -- 512 floats
    confidence REAL,
    estimated_age INTEGER,
    estimated_gender TEXT
);

CREATE TABLE persons (
    id INTEGER PRIMARY KEY,
    name TEXT,
    created TIMESTAMP,
    photo_count INTEGER DEFAULT 0
);

-- Scene/content analysis
CREATE TABLE scene_analysis (
    file_id INTEGER PRIMARY KEY REFERENCES files(id),
    categories JSON,  -- {"beach": 0.9, "outdoor": 0.8}
    objects JSON,     -- ["dog", "ball", "grass"]
    quality_score REAL,
    blur_score REAL,
    analyzed_date TIMESTAMP
);

-- OCR results
CREATE TABLE ocr_results (
    file_id INTEGER PRIMARY KEY REFERENCES files(id),
    extracted_text TEXT,
    confidence REAL
);

-- Action audit log
CREATE TABLE action_log (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP,
    action_type TEXT,
    source_path TEXT,
    dest_path TEXT,
    file_hash TEXT,
    file_size INTEGER,
    reversible BOOLEAN,
    reversed BOOLEAN DEFAULT FALSE,
    metadata JSON
);

-- Indexes
CREATE INDEX idx_files_hash ON files(content_hash);
CREATE INDEX idx_files_size ON files(size);
CREATE INDEX idx_files_drive ON files(drive_id);
CREATE INDEX idx_faces_person ON faces(person_id);
CREATE INDEX idx_metadata_date ON file_metadata(exif_date);
```

---

## UI Screens & Flow

### Main Window Layout
```
+------------------------------------------------------------------+
|  [Drives] [Scan] [Duplicates] [Photos] [Faces] [Search]          |
+------------------------------------------------------------------+
|                                                                   |
|  +------------------+  +--------------------------------------+   |
|  |                  |  |                                      |   |
|  |   Left Panel     |  |         Main Content Area            |   |
|  |   - Drive tree   |  |         (changes based on tab)       |   |
|  |   - Filters      |  |                                      |   |
|  |   - Quick stats  |  |                                      |   |
|  |                  |  |                                      |   |
|  +------------------+  +--------------------------------------+   |
|                                                                   |
+------------------------------------------------------------------+
|  Status Bar: [Progress] [Files: X] [Space: Y GB] [GPU: Active]   |
+------------------------------------------------------------------+
```

### Screen Descriptions

#### 1. Drives Panel
- List registered drives with status indicators
- Add/remove drives
- Show space usage per drive
- "At risk" file count (single-copy files)
- Scan buttons per drive or all

#### 2. Scan Progress
- Real-time progress bars
- Files scanned / total estimated
- Current file being processed
- Pause/Resume/Cancel buttons
- Phase indicator (scanning → hashing → analyzing)

#### 3. Duplicates Review
- Grid/list of duplicate groups
- Thumbnail preview for images
- File details (path, size, date, drive)
- "Keep" checkbox for each file
- Bulk actions: keep newest, keep on drive X, etc.
- Filter: exact only, images only, videos only, by drive

#### 4. Photo Organizer Panel (Photos tab)
- Preview of proposed organization
- Source folder selection (unorganized photos)
- Destination folder selection (organized output)
- Organization options (date format, location, event clustering)
- Before/after folder tree view
- Execute button with dry-run option
- Handles screenshots, bursts, and Live Photos

#### 5. Faces Gallery
- Grid of detected faces
- Cluster view: grouped unknown faces
- Person view: all photos of a person
- Name assignment interface
- "Same person?" confirmation dialogs for uncertain matches
- Age timeline view for a person

#### 6. Search Panel
- Text search box (uses CLIP semantic search)
- Filters: date range, drive, file type, person
- Results grid with thumbnails
- "Find similar" button on any image

#### 7. Settings Panel
- AI model management (download, update, remove)
- Similarity thresholds
- Default resolution strategies
- Quarantine folder location
- Theme (light/dark)

#### 8. Action Log Panel
- History of all operations
- Filter by action type
- Undo button for reversible actions
- Export log as CSV

---

## Feature List by Priority

### Phase 1: Core Foundation
- [ ] Project structure and build system
- [ ] Dear PyGui application skeleton
- [ ] SQLite database setup with migrations
- [ ] Drive registration and monitoring
- [ ] File scanner with progress reporting
- [ ] Basic file listing UI

### Phase 2: Duplicate Detection
- [ ] Size-based grouping
- [ ] Quick hash computation
- [ ] Full hash verification
- [ ] Exact duplicate grouping
- [ ] Duplicates review UI
- [ ] Basic resolution (keep newest/oldest)
- [ ] Quarantine/delete actions
- [ ] Action audit log

### Phase 3: Image-Specific Features
- [ ] EXIF metadata extraction
- [ ] Perceptual hashing (pHash)
- [ ] Near-duplicate detection for images
- [ ] Thumbnail generation and caching
- [ ] Image preview in UI

### Phase 4: Organization Features
- [ ] Date-based folder organization
- [ ] Smart file renaming
- [ ] Screenshot detection
- [ ] Organization preview UI
- [ ] Dry-run mode
- [ ] Execute with undo support

### Phase 5: AI Features - Faces
- [ ] InsightFace model download/setup
- [ ] Face detection
- [ ] Face embedding extraction
- [ ] Face clustering (unknown faces)
- [ ] Person naming UI
- [ ] Face recognition (match to known)
- [ ] Age-based temporal bridging
- [ ] Faces gallery UI

### Phase 6: AI Features - Content
- [ ] CLIP model setup
- [ ] Scene classification
- [ ] Semantic search ("beach sunset")
- [ ] Object detection (YOLOv8)
- [ ] Quality scoring
- [ ] Search UI

### Phase 7: Advanced Features
- [ ] OCR for documents/screenshots
- [ ] Video frame extraction
- [ ] Video duplicate detection
- [ ] GPS reverse geocoding
- [ ] Location-based organization
- [ ] Event clustering

### Phase 8: Multi-Drive Features
- [x] Cross-drive duplicate analysis (hash groups across drives)
- [x] Redundancy report (at-risk files, basic UI)
- [x] Backup suggestions (plan preview only)
- [x] Sync/copy operations (backup plan execution)
- [x] Drive health monitoring (status/space/last scan)

### Phase 9: Polish
- [ ] Performance optimization
- [ ] Memory usage optimization for large collections
- [ ] Background processing
- [ ] Notifications
- [ ] Export/import scan data
- [ ] Help documentation
- [ ] Plan binary text diff support: Office (DOCX/DOC, XLSX/XLS, PPTX/PPT), docs (PDF/RTF/ODT/EPUB), email (EML/MSG), web (HTML/HTM), structured text (CSV/JSON/XML); optional OCR for images/scans

---

## Directory Structure

```
nas_dedup/
├── src/
│   ├── nas_dedup/
│   │   ├── __init__.py
│   │   ├── __main__.py          # Entry point
│   │   ├── app.py               # Dear PyGui app setup
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── scanner.py       # File system scanning
│   │   │   ├── hasher.py        # Hash computation
│   │   │   ├── comparator.py    # Duplicate detection
│   │   │   ├── resolver.py      # Keep/remove decisions
│   │   │   ├── organizer.py     # Photo organization
│   │   │   └── actions.py       # File operations
│   │   │
│   │   ├── drives/
│   │   │   ├── __init__.py
│   │   │   ├── manager.py       # Multi-drive coordination
│   │   │   └── redundancy.py    # Backup verification
│   │   │
│   │   ├── ai/
│   │   │   ├── __init__.py
│   │   │   ├── model_manager.py # Download/load models
│   │   │   ├── faces.py         # Face detection/recognition
│   │   │   ├── scenes.py        # CLIP scene classification
│   │   │   ├── objects.py       # YOLO object detection
│   │   │   ├── quality.py       # Image quality scoring
│   │   │   └── ocr.py           # Text extraction
│   │   │
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── database.py      # SQLite connection/setup
│   │   │   ├── models.py        # Data classes
│   │   │   └── migrations/      # Schema migrations
│   │   │
│   │   ├── ui/
│   │   │   ├── __init__.py
│   │   │   ├── main_window.py   # Main application window
│   │   │   ├── drives_panel.py
│   │   │   ├── scan_panel.py
│   │   │   ├── duplicates_panel.py
│   │   │   ├── organize_panel.py # Photo Organizer (Photos tab)
│   │   │   ├── faces_panel.py
│   │   │   ├── search_panel.py
│   │   │   ├── settings_panel.py
│   │   │   ├── action_log_panel.py
│   │   │   └── components/      # Reusable UI components
│   │   │       ├── image_grid.py
│   │   │       ├── file_tree.py
│   │   │       └── progress_bar.py
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── exif.py          # EXIF extraction
│   │       ├── thumbnails.py    # Thumbnail generation
│   │       ├── geocoding.py     # GPS to location
│   │       └── config.py        # App configuration
│   │
├── tests/
│   ├── __init__.py
│   ├── test_scanner.py
│   ├── test_hasher.py
│   ├── test_comparator.py
│   └── ...
│
├── resources/
│   └── icons/                   # UI icons
│
├── pyproject.toml
├── requirements.txt
├── requirements-ai.txt          # Optional AI dependencies
├── CLAUDE.md
├── PLAN.md
└── README.md
```

---

## Technical Considerations

### Performance
- Use thread pool for file I/O operations
- GPU batching for AI inference (32-64 images per batch)
- Lazy thumbnail loading in UI
- Pagination for large result sets
- Index database properly for common queries

### Memory Management
- Stream large files during hashing (never load full file)
- Clear AI model from GPU when not in use
- Limit thumbnail cache size
- Use generators for file enumeration

### Error Handling
- Graceful handling of permission denied
- Network drive disconnection during scan
- Corrupted images (can't extract EXIF/hash)
- AI model inference failures
- Database corruption recovery

---

## Implementation Gaps (Current vs Plan)

The following items are planned in this document but are not fully implemented yet
or are partially wired in the UI:

### UI Wired But Missing Backend
- **Full Analysis button** in Drives panel runs scan + hash only; does not trigger AI analysis pipeline.
- **Google AI summaries** listed as provider in config/UI but no key UI or backend implementation.

### Planned Features Not Implemented
- **CLI commands** for `organize`, `analyze`, `search`, and `faces train` are stubs.
- **Quality scoring pipeline** exists but is not executed; “keep best quality” falls back to file size.
- **Thumbnail generation/caching** schema exists but no generator or UI integration.
- **Auto-tagging** tables exist but no tagging pipeline populates `tags` / `file_tags`.
- **Video analysis/dedup** (frame extraction + similarity) not implemented.
- **Settings storage** planned for SQLite; current implementation persists config to JSON.
- **Drive manager filter/sorting UI** and **notifications** are not implemented.
- **Action log cleanup UI** and **quarantine browser** are placeholders.

### Security
- No execution of files
- Sanitize paths to prevent directory traversal
- Audit log is append-only
- Optional confirmation for destructive actions

---

## Resolved Questions

1. **Network drives**: UNC paths (\\\\server\\share) - handle SMB network paths natively on Windows

2. **Incremental scanning**: Quick scan uses mtime check; deep scan re-hashes everything

3. **Concurrent access**: Single-user mode; simple SQLite locking sufficient

## Future Considerations

1. **Cloud backup integration**: Verify cloud backups match local files?

2. **Mobile companion**: App to review duplicates on phone?

3. **Commercialization**: Keep code clean, consider licensing structure for potential future sale

---

## Network Path Handling

Since the NAS uses UNC paths like `\\LS210D11E\share\BasementPC\Documents`:

```python
from pathlib import PureWindowsPath, Path
import os

class NetworkPath:
    """Handle UNC paths for Buffalo LinkStation and similar NAS devices."""

    @staticmethod
    def is_unc(path: str) -> bool:
        return path.startswith('\\\\') or path.startswith('//')

    @staticmethod
    def normalize(path: str) -> str:
        """Convert to consistent UNC format."""
        return path.replace('/', '\\')

    @staticmethod
    def get_server_share(path: str) -> tuple[str, str]:
        """Extract server and share from UNC path."""
        # \\server\share\path -> (server, share)
        parts = path.lstrip('\\').split('\\')
        return parts[0], parts[1] if len(parts) > 1 else ''

    @staticmethod
    def is_accessible(path: str) -> bool:
        """Check if network path is reachable."""
        try:
            return os.path.exists(path)
        except (OSError, PermissionError):
            return False
```

### Considerations for Network Drives
- Handle network timeouts gracefully
- Retry logic for intermittent connectivity
- Cache file listings to reduce network chatter
- Show clear status when NAS is unreachable
- Support reconnection without losing scan progress

---

## Scan Strategies

```python
class ScanMode(Enum):
    QUICK = "quick"      # Check mtime only, skip unchanged files
    DEEP = "deep"        # Re-hash all files regardless of mtime
    FULL = "full"        # Full rescan + AI analysis

class ScanStrategy:
    """Determine which files need processing."""

    def __init__(self, mode: ScanMode, db: Database):
        self.mode = mode
        self.db = db

    def needs_hash(self, file_path: str, mtime: float, size: int) -> bool:
        if self.mode == ScanMode.DEEP:
            return True

        # Quick mode: check if file changed since last scan
        existing = self.db.get_file(file_path)
        if not existing:
            return True  # New file

        if existing.modified != mtime or existing.size != size:
            return True  # File changed

        return False  # Use cached hash
```

### Scan UI Options
- **Quick Scan**: Fast, uses cached hashes for unchanged files (default after first scan)
- **Deep Scan**: Re-hash everything, useful if files might have changed without mtime update
- **Full Analysis**: Deep scan + run AI analysis on all images
