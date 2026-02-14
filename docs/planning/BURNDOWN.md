# DupliCleaner Feature Burndown

**Last updated:** 2026-02-14
**Total items:** 130 | **Completed:** 130 | **Deferred:** 0 | **Remaining:** 0

---

## How to Use This Document

- Work top to bottom. Each tier's items can be done in any internal order.
- Mark items: `[ ]` pending, `[~]` in progress, `[x]` complete, `[-]` cut/deferred
- When completing an item, add the date: `[x] ~~2026-02-15~~`
- Each item links to its detailed planning doc in `docs/planning/`

---

## Tier 0: UI Polish & Interaction (No Backend Dependencies)

Pure UI work that improves the experience across all panels. No backend changes needed, so this can be done first without affecting anything else. Context menus follow the existing pattern from `files_panel.py`.

### Phase 0A: Files Tab - Thumbnail Grid View
**Doc:** Right-Click Context Menus & Files Tab plan (Phase 1)
**Effort:** Medium | **Type:** UI feature

- [x] 0A.1 - Add view mode state, TAG constants, and thumbnail size config ~~2026-02-11~~
- [x] 0A.2 - Add view mode toolbar (List/Thumbnails toggle + size combo) ~~2026-02-11~~
- [x] 0A.3 - Add hidden thumbnail grid `child_window` container ~~2026-02-11~~
- [x] 0A.4 - Modify `_load_image_texture()` to accept optional size parameter ~~2026-02-11~~
- [x] 0A.5 - Branch `_load_folder_files()` by view mode (table vs grid) ~~2026-02-11~~
- [x] 0A.6 - Implement `_render_thumbnail_grid()` with row layout + right-click ~~2026-02-11~~
- [x] 0A.7 - Add view mode switch and size change callbacks ~~2026-02-11~~
- [x] 0A.8 - Test: toggle modes, change sizes, verify images load, right-click works ~~2026-02-14~~

### Phase 0B: Duplicates Panel - Context Menus
**Doc:** Right-Click Context Menus & Files Tab plan (Phase 2)
**Effort:** Medium | **Type:** UI interaction

- [x] 0B.1 - Add TAGs, state, handler registries for group + file context menus ~~2026-02-11~~
- [x] 0B.2 - Create group list context menu (Open, Compare, Ignore, Quarantine, Delete) ~~2026-02-11~~
- [x] 0B.3 - Create file details context menu (Open, Explorer, Mark Keeper, Copy Path) ~~2026-02-11~~
- [x] 0B.4 - Wire right-click handlers in `_refresh_groups()` and `_show_group_details()` ~~2026-02-11~~
- [x] 0B.5 - Add dismiss handler with debounce ~~2026-02-11~~
- [x] 0B.6 - Implement `_ctx_*` callback methods delegating to existing actions ~~2026-02-11~~

### Phase 0C: Search Panel - Context Menu
**Doc:** Right-Click Context Menus & Files Tab plan (Phase 3)
**Effort:** Small | **Type:** UI interaction

- [x] 0C.1 - Add TAG, state, handler registries ~~2026-02-11~~
- [x] 0C.2 - Create context menu (Preview, Open, Explorer, Copy Path) ~~2026-02-11~~
- [x] 0C.3 - Wire right-click on result card filename selectables ~~2026-02-11~~
- [x] 0C.4 - Add dismiss handler and `_ctx_*` callbacks ~~2026-02-11~~

### Phase 0D: Organize Panel - Context Menu
**Doc:** Right-Click Context Menus & Files Tab plan (Phase 4)
**Effort:** Small | **Type:** UI interaction

- [x] 0D.1 - Add TAG, state, handler registries ~~2026-02-11~~
- [x] 0D.2 - Create context menu (Open Source, Explorer, Copy Path) ~~2026-02-11~~
- [x] 0D.3 - Wire right-click on preview table source filename rows ~~2026-02-11~~
- [x] 0D.4 - Add dismiss handler and `_ctx_*` callbacks ~~2026-02-11~~

### Phase 0E: Faces Panel - Context Menus
**Doc:** Right-Click Context Menus & Files Tab plan (Phase 5)
**Effort:** Medium | **Type:** UI interaction

- [x] 0E.1 - Add TAGs and state for 3 context menus (cluster, people, gallery) ~~2026-02-12~~
- [x] 0E.2 - Create cluster context menu (View All, Name, Split, Ignore) ~~2026-02-12~~
- [x] 0E.3 - Create people table context menu (Gallery, Timeline, Edit, Find More, Delete) ~~2026-02-12~~
- [x] 0E.4 - Create gallery photo context menu (View, Open, Explorer, Remove, Copy Path) ~~2026-02-12~~
- [x] 0E.5 - Wire right-click handlers in cluster cards, people rows, gallery photos ~~2026-02-12~~
- [x] 0E.6 - Add dismiss handler and `_ctx_*` callbacks ~~2026-02-12~~

---

## Tier 1: Core Wiring & Safety Net

Connect existing backend code to the UI. Establish undo/rollback so all future destructive features get safety for free.

### 1.1 - AI Analysis UI Controls
**Doc:** [`ai-analysis-ui-controls.md`](ai-analysis-ui-controls.md)
**Effort:** Small | **Type:** UI wiring

- [x] 1.1.1 - Wire "Refresh Models" button to ModelManager ~~2026-02-12~~
- [x] 1.1.2 - Wire "Verify Models" button ~~2026-02-12~~
- [x] 1.1.3 - Wire "Install AI Deps" button ~~2026-02-12~~
- [x] 1.1.4 - Wire "Run Analysis" to AnalysisRunner with progress callback ~~2026-02-12~~
- [x] 1.1.5 - Wire "Cancel Analysis" to AnalysisRunner.cancel() ~~2026-02-12~~
- [x] 1.1.6 - Connect progress indicators and status panel updates ~~2026-02-12~~

### 1.2 - Undo / Rollback System
**Doc:** [`undo-rollback-system.md`](undo-rollback-system.md)
**Effort:** Medium | **Type:** New system

- [x] 1.2.1 - Design transaction grouping for action engine ~~2026-02-12~~ (undo_batch already exists)
- [x] 1.2.2 - Implement undo logic (reverse delete/move/link operations) ~~2026-02-12~~ (already in ActionEngine)
- [x] 1.2.3 - Build quarantine browser UI ~~2026-02-12~~ (already in ActionLogPanel)
- [x] 1.2.4 - Add undo buttons to action history panel ~~2026-02-12~~ (already in ActionLogPanel)
- [x] 1.2.5 - Add "Undo Last" quick action to duplicates toolbar ~~2026-02-12~~
- [x] 1.2.6 - Test: undo delete, undo move, undo quarantine, multi-step undo ~~2026-02-14~~

### 1.3 - Quality-Based Duplicate Selection
**Doc:** [`quality-based-duplicate-selection.md`](quality-based-duplicate-selection.md)
**Effort:** Small | **Type:** UI wiring

- [x] 1.3.1 - Add quality score badges to duplicate group file entries ~~2026-02-12~~
- [x] 1.3.2 - Wire "Keep Best Quality" button per group ~~2026-02-12~~
- [x] 1.3.3 - Wire "Keep Best Quality for All" batch action ~~2026-02-12~~
- [x] 1.3.4 - Add quality overlay to side-by-side comparison view ~~2026-02-12~~

### 1.4 - Side-by-Side Comparison Enhancements
**Doc:** [`side-by-side-comparison-enhancements.md`](side-by-side-comparison-enhancements.md)
**Effort:** Medium | **Type:** UI work

- [x] 1.4.1 - Implement synchronized zoom/pan between compared images ~~2026-02-14~~
- [x] 1.4.2 - Add EXIF comparison table below images ~~2026-02-12~~
- [x] 1.4.3 - Add pixel difference / highlight overlay view ~~2026-02-14~~
- [x] 1.4.4 - Support multi-file grid comparison (3+ files) ~~2026-02-12~~

---

## Tier 2: Duplicate Detection Expansion

Quality scoring visible and comparison tools improved. Now expand what counts as a "duplicate."

### 2.1 - Video Near-Duplicate Detection
**Doc:** [`video-near-duplicate-detection.md`](video-near-duplicate-detection.md)
**Effort:** Medium | **Type:** Backend + UI

- [x] 2.1.1 - Extract keyframes from video files for perceptual hashing ~~2026-02-12~~
- [x] 2.1.2 - Extend comparator to handle video-to-video similarity ~~2026-02-12~~
- [x] 2.1.3 - Wire "Process Videos" UI checkbox to comparator pipeline ~~2026-02-12~~
- [x] 2.1.4 - Add video thumbnail strips to duplicate group view ~~2026-02-12~~
- [x] 2.1.5 - Test with MP4/MOV/AVI duplicate sets ~~2026-02-14~~

### 2.2 - Cross-Format Deduplication
**Doc:** [`cross-format-deduplication.md`](cross-format-deduplication.md)
**Effort:** Medium | **Type:** Backend + UI

- [x] 2.2.1 - Add format preference hierarchy to resolver (e.g., RAW > TIFF > PNG > JPG) ~~2026-02-12~~
- [x] 2.2.2 - Implement video cross-format matching (MP4 vs MOV vs AVI) ~~2026-02-12~~
- [x] 2.2.3 - Implement document cross-format matching (DOCX vs PDF via text) ~~2026-02-12~~
- [x] 2.2.4 - Add "Keep Best Format" action button to duplicate groups ~~2026-02-12~~
- [x] 2.2.5 - Show format info badges in duplicate group entries ~~2026-02-12~~

---

## Tier 3: Organization & File Management

Duplicates fully handled. Improve file organization and monitoring.

### 3.1 - Screenshot & Burst Detection Enhancements
**Doc:** [`screenshot-and-burst-detection.md`](screenshot-and-burst-detection.md)
**Effort:** Small | **Type:** Wiring

- [x] 3.1.1 - Wire burst quality selection to quality scorer (from 1.3) ~~2026-02-12~~
- [x] 3.1.2 - Add quality-ranked burst group viewer ~~2026-02-12~~
- [x] 3.1.3 - Add OCR for screenshot text extraction and search ~~2026-02-12~~
- [x] 3.1.4 - ML-enhanced screenshot detection (beyond dimension heuristics) ~~2026-02-12~~

### 3.2 - Live Photo / Video Matching Enhancements
**Doc:** [`live-photo-video-matching-enhancements.md`](live-photo-video-matching-enhancements.md)
**Effort:** Small | **Type:** Refinement

- [x] 3.2.1 - Add cross-directory Live Photo matching ~~2026-02-12~~
- [x] 3.2.2 - Parse Apple ContentIdentifier metadata ~~2026-02-12~~
- [x] 3.2.3 - Support embedded Motion Photo extraction (Samsung/Google) ~~2026-02-12~~
- [x] 3.2.4 - Integrate Live Photo context into duplicate group display ~~2026-02-12~~

### 3.3 - JPEG Corrupt File Recovery
**Doc:** [`jpeg-corrupt-file-recovery.md`](jpeg-corrupt-file-recovery.md)
**Effort:** Small | **Type:** UI wiring

- [x] 3.3.1 - Add corruption detection to scan phase (2026-02-12)
- [x] 3.3.2 - Display "Corrupt Files" section in scan results (2026-02-12)
- [x] 3.3.3 - Wire recovery buttons to existing 8 recovery modules (2026-02-12)
- [x] 3.3.4 - Add before/after recovery preview (2026-02-12)
- [x] 3.3.5 - Batch recovery progress indicator (2026-02-12)

### 3.4 - Folder Watching & Auto-Organization
**Doc:** [`folder-watching-auto-organization.md`](folder-watching-auto-organization.md)
**Effort:** Medium | **Type:** New system

- [x] 3.4.1 - Implement file system watcher (watchdog or polling) (2026-02-12)
- [x] 3.4.2 - Add "Watch Folders" configuration UI in Drives panel (2026-02-12)
- [x] 3.4.3 - Wire new file events to incremental scan pipeline (2026-02-12)
- [x] 3.4.4 - Wire new file events to auto-organization rules (2026-02-12)
- [x] 3.4.5 - Add status notifications for auto-processed files (2026-02-12)

---

## Tier 4: Face & Person Intelligence

Build on existing face detection for a full person-tracking system. Depends on 1.1 (AI UI Controls) for analysis to run from UI.

### 4.1 - Intelligent Face Assignment
**Doc:** [`intelligent-face-assignment.md`](intelligent-face-assignment.md)
**Effort:** Medium | **Type:** Backend logic

- [x] 4.1.1 - Add per-photo conflict detection (same person assigned twice) ~~2026-02-12~~
- [x] 4.1.2 - Add age plausibility checks (birth_year vs photo date) ~~2026-02-12~~
- [x] 4.1.3 - Add pre-birth impossibility guard ~~2026-02-12~~
- [x] 4.1.4 - Build assignment suggestions UI with reasoning text ~~2026-02-12~~
- [x] 4.1.5 - Add sibling detection based on co-occurrence patterns ~~2026-02-12~~

### 4.2 - Age-Progression Face Recognition
**Doc:** [`age-progression-face-recognition.md`](age-progression-face-recognition.md)
**Effort:** Large | **Type:** ML + Backend

- [x] 4.2.1 - Implement temporal bridging chain logic
- [x] 4.2.2 - Store multi-embeddings per person at different life stages
- [x] 4.2.3 - Add age estimation model integration
- [x] 4.2.4 - Lower similarity thresholds for temporally adjacent photos
- [x] 4.2.5 - Build face timeline view in faces panel
- [x] 4.2.6 - Add user-assisted cross-age linking UI

### 4.3 - Family Groups & Relationships
**Doc:** [`family-groups-and-relationships.md`](family-groups-and-relationships.md)
**Effort:** Medium | **Type:** Backend + UI

- [x] 4.3.1 - Add relationship model to database (parent/child/sibling/spouse) ~~2026-02-13~~
- [x] 4.3.2 - Build relationship management UI in person detail panel ~~2026-02-13~~
- [x] 4.3.3 - Implement co-occurrence analysis for relationship suggestions ~~2026-02-13~~
- [x] 4.3.4 - Add family group view in faces panel ~~2026-02-13~~
- [x] 4.3.5 - Add family filters to search panel ~~2026-02-13~~

### 4.4 - Celebrity Face Identification
**Doc:** [`celebrity-face-identification.md`](celebrity-face-identification.md)
**Effort:** Medium | **Type:** API integration

- [x] 4.4.1 - Integrate cloud API (Amazon Rekognition) for celebrity detection ~~2026-02-13~~
- [x] 4.4.2 - Alternative: local celebrity embedding database ~~2026-02-13~~
- [x] 4.4.3 - Add "Identify Unknown Faces" button to faces panel ~~2026-02-13~~
- [x] 4.4.4 - Add confidence threshold settings and review queue ~~2026-02-13~~

---

## Tier 5: Pet & Audio Intelligence

Independent of Tier 4. Can be worked in parallel.

### 5.1 - Pet Detection & Tracking
**Doc:** [`pet-detection-and-tracking.md`](pet-detection-and-tracking.md)
**Effort:** Large | **Type:** ML + Backend

- [x] 5.1.1 - Add visual embedding extraction for detected pets ~~2026-02-13~~
- [x] 5.1.2 - Implement breed classification model ~~2026-02-13~~
- [x] 5.1.3 - Build pet tracking with temporal bridging (puppy to adult) ~~2026-02-13~~
- [x] 5.1.4 - Add color/marking analysis for pet distinction ~~2026-02-13~~
- [x] 5.1.5 - Build pet management UI (name, timeline, gallery) ~~2026-02-13~~
- [x] 5.1.6 - Integrate pet names into AI summaries and search ~~2026-02-13~~

### 5.2 - Audio Transcription Integration
**Doc:** [`audio-transcription-integration.md`](audio-transcription-integration.md)
**Effort:** Small | **Type:** UI wiring

- [x] 5.2.1 - Add audio settings controls (Whisper model, device, compute type) ~~2026-02-13~~
- [x] 5.2.2 - Wire transcription into analysis run callback ~~2026-02-13~~
- [x] 5.2.3 - Display transcriptions in file details panel ~~2026-02-13~~
- [x] 5.2.4 - Index transcription text in FTS5 for search ~~2026-02-13~~

---

## Tier 6: Data Portability & Reporting

All analysis features generate data. Make it portable and reportable.

### 6.1 - Export & Reporting
**Doc:** [`export-and-reporting.md`](export-and-reporting.md)
**Effort:** Medium | **Type:** UI + generation

- [x] 6.1.1 - Add export button to duplicates panel (CSV/JSON) ~~2026-02-14~~
- [x] 6.1.2 - Add export button to faces panel (person roster) ~~2026-02-14~~
- [x] 6.1.3 - Add export button to search panel (results) ~~2026-02-14~~
- [x] 6.1.4 - Add export button to drives panel (redundancy report) ~~2026-02-14~~
- [x] 6.1.5 - Build unified PDF/HTML report generator ~~2026-02-14~~
- [x] 6.1.6 - Add report configuration dialog (select sections, date range) ~~2026-02-14~~

### 6.2 - AI Metadata Embedding
**Doc:** [`ai-metadata-embedding.md`](ai-metadata-embedding.md)
**Effort:** Medium | **Type:** File writing

- [x] 6.2.1 - Implement EXIF/IPTC/XMP writer (exiftool or piexif) ~~2026-02-14~~
- [x] 6.2.2 - Write face regions using MWG standard ~~2026-02-14~~
- [x] 6.2.3 - Write AI tags, summaries, and quality scores ~~2026-02-14~~
- [x] 6.2.4 - Add "Write Metadata" button to files panel ~~2026-02-14~~
- [x] 6.2.5 - Add preview panel showing what will be written ~~2026-02-14~~
- [x] 6.2.6 - Add metadata write preferences in settings ~~2026-02-14~~

---

## Tier 7: Advanced Analytics & Corpus

Power-user features requiring all foundational data.

### 7.1 - Storage Analytics
**Doc:** [`storage-analytics.md`](storage-analytics.md)
**Effort:** Medium | **Type:** New panel

- [x] 7.1.1 - Build storage analytics panel/dashboard ~~2026-02-14~~
- [x] 7.1.2 - Add storage breakdown by file type visualization ~~2026-02-14~~
- [x] 7.1.3 - Add duplicate waste calculation and display ~~2026-02-14~~
- [x] 7.1.4 - Add redundancy analysis across drives ~~2026-02-14~~
- [x] 7.1.5 - Add "Quick Wins" section (largest duplicates to clean) ~~2026-02-14~~
- [x] 7.1.6 - Add file age distribution chart ~~2026-02-14~~

### 7.2 - Document Corpus Analysis
**Doc:** [`document-corpus-analysis.md`](document-corpus-analysis.md)
**Effort:** Large | **Type:** NLP + UI

- [x] 7.2.1 - Implement term frequency / keyword extraction ~~2026-02-14~~
- [x] 7.2.2 - Add named entity recognition (spaCy) ~~2026-02-14~~
- [x] 7.2.3 - Build communication network mapping (NetworkX) ~~2026-02-14~~
- [x] 7.2.4 - Add pattern detection across document collections ~~2026-02-14~~
- [x] 7.2.5 - Build corpus analysis panel with visualizations ~~2026-02-14~~
- [x] 7.2.6 - Add export for corpus reports ~~2026-02-14~~

---

## Progress Summary

| Tier | Description | Items | Done | Deferred | % |
|------|-------------|-------|------|----------|---|
| 0 | UI Polish & Interaction | 28 | 28 | 0 | 100% |
| 1 | Core Wiring & Safety Net | 20 | 20 | 0 | 100% |
| 2 | Duplicate Detection Expansion | 10 | 10 | 0 | 100% |
| 3 | Organization & File Management | 18 | 18 | 0 | 100% |
| 4 | Face & Person Intelligence | 20 | 20 | 0 | 100% |
| 5 | Pet & Audio Intelligence | 10 | 10 | 0 | 100% |
| 6 | Data Portability & Reporting | 12 | 12 | 0 | 100% |
| 7 | Advanced Analytics & Corpus | 12 | 12 | 0 | 100% |
| **Total** | | **130** | **130** | **0** | **100%** |

---

## Dependency Map

```
Tier 0 (UI polish) ---- no dependencies, do first ----
  0A Files Thumbnail Grid
  0B Duplicates Context Menus
  0C Search Context Menu
  0D Organize Context Menu
  0E Faces Context Menus
      |
Tier 1 (foundations)
  1.1 AI UI Controls ─────────────────────────────────┐
  1.2 Undo/Rollback (safety for all future actions)   |
  1.3 Quality Scoring UI ────┐                        |
  1.4 Comparison Enhancements|                        |
                             |                        |
Tier 2 (expanded dedup)     |                        |
  2.1 Video Dedup ───────────┤                        |
  2.2 Cross-Format Dedup ────┘                        |
                                                      |
Tier 3 (organization)                                |
  3.1 Screenshot/Burst (+quality from 1.3)            |
  3.2 Live Photo Enhancements                         |
  3.3 JPEG Recovery UI                                |
  3.4 Folder Watching (needs solid scanner+organizer) |
                                                      |
Tier 4 (people) ──────────────────────────────────────┘
  4.1 Intelligent Assignment
  4.2 Age Progression ────── depends on 4.1
  4.3 Family Groups ──────── depends on 4.1, 4.2
  4.4 Celebrity ID

Tier 5 (parallel to T4)
  5.1 Pet Tracking
  5.2 Audio Transcription

Tier 6 (portability) ────── depends on T1-T5 generating data
  6.1 Export & Reports
  6.2 Metadata Embedding

Tier 7 (analytics) ──────── depends on T1-T6 data existing
  7.1 Storage Analytics
  7.2 Corpus Analysis
```
