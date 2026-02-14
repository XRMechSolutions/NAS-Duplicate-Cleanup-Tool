# Prioritized Implementation Order

This document defines the logical build order for all planned features. Items are grouped into tiers based on dependency chains - each tier can be worked in any internal order, but should be completed before moving to the next tier. This minimizes rework and ensures foundations are in place before dependent features.

---

## Tier 1: Core Wiring & Safety Net

These connect existing backend code to the UI and establish the safety foundation that all destructive operations depend on. Nothing here requires new AI models or major architecture changes.

### 1.1 - AI Analysis UI Controls
**Doc:** `ai-analysis-ui-controls.md`
**Why first:** Six stubbed callbacks need wiring. Almost every AI-dependent feature below assumes analysis has already run. This is the gateway to all AI features working from the UI.
**Touches:** Analysis section buttons, progress indicators, status panel

### 1.2 - Undo / Rollback System
**Doc:** `undo-rollback-system.md`
**Why early:** Every destructive action (delete, move, organize) needs undo support. Building this now means all subsequent features get undo for free instead of retrofitting later.
**Touches:** Action log panel, action engine, quarantine browser

### 1.3 - Quality-Based Duplicate Selection
**Doc:** `quality-based-duplicate-selection.md`
**Why early:** Quality scorer is fully implemented but not surfaced. This is pure UI wiring - add quality badges and "Keep Best Quality" to the duplicates panel. The resolver already has `KEEP_BEST_QUALITY` stubbed.
**Touches:** Duplicates panel (quality badges, batch actions)

### 1.4 - Side-by-Side Comparison Enhancements
**Doc:** `side-by-side-comparison-enhancements.md`
**Why here:** Basic comparison exists. Enhancements (sync zoom, quality overlay, EXIF table, diff view) make the duplicates panel much more useful before we add video/cross-format duplicates to it.
**Touches:** Duplicates panel comparison view

---

## Tier 2: Duplicate Detection Expansion

With quality scoring visible and comparison tools improved, expand what counts as a "duplicate."

### 2.1 - Video Near-Duplicate Detection
**Doc:** `video-near-duplicate-detection.md`
**Why now:** Frame extraction exists in content_summarizer. The UI checkbox for "Process Videos" exists but isn't wired. Extends the core value proposition to videos.
**Touches:** Duplicates panel, comparator, video thumbnail strips

### 2.2 - Cross-Format Deduplication
**Doc:** `cross-format-deduplication.md`
**Why now:** Same photo as JPG+PNG, same video as MP4+MOV. Image cross-format already works via perceptual hashing. Video and document cross-format depend on 2.1 and the existing OCR pipeline.
**Touches:** Duplicate groups, resolver (format preference), "Keep Best Format" action

---

## Tier 3: Organization & File Management

With duplicates fully handled, improve how files get organized and monitored.

### 3.1 - Screenshot & Burst Detection Enhancements
**Doc:** `screenshot-and-burst-detection.md`
**Why now:** Base features are implemented. Wire burst quality selection to the quality scorer (from 1.3). Add OCR for screenshot text content.
**Touches:** Organize panel, burst group viewer

### 3.2 - Live Photo / Video Matching Enhancements
**Doc:** `live-photo-video-matching-enhancements.md`
**Why now:** Base detection is complete. Enhancements (cross-directory matching, Apple ContentIdentifier, embedded Motion Photos) refine the organizer before auto-watching depends on it.
**Touches:** Organize panel, duplicate groups

### 3.3 - JPEG Corrupt File Recovery
**Doc:** `jpeg-corrupt-file-recovery.md`
**Why now:** Eight recovery modules already exist in utils/. This is UI integration work - add corruption detection to scan results and wire recovery buttons.
**Touches:** Scan results, recovery preview, progress indicators

### 3.4 - Folder Watching & Auto-Organization
**Doc:** `folder-watching-auto-organization.md`
**Why last in tier:** Depends on the organizer, scanner, and dedup pipeline all being solid. Automates what users currently trigger manually.
**Touches:** Drives/Settings panel, status notifications

---

## Tier 4: Face & Person Intelligence

Build on the existing face detection to create a full person-tracking system.

### 4.1 - Intelligent Face Assignment
**Doc:** `intelligent-face-assignment.md`
**Why first in tier:** Fixes false positives in auto-assignment (same person twice in one photo, impossible ages). Must be solid before age progression chains are built on top.
**Touches:** Faces panel assignment suggestions, conflict resolution

### 4.2 - Age-Progression Face Recognition
**Doc:** `age-progression-face-recognition.md`
**Why now:** Depends on solid face assignment (4.1). Temporal bridging chains link baby-to-adult through intermediate photos. Stores multi-embeddings per person at different ages.
**Touches:** Faces panel timeline view, person detail view

### 4.3 - Family Groups & Relationships
**Doc:** `family-groups-and-relationships.md`
**Why now:** Depends on persons existing in the DB with correct assignments. Adds parent/child/sibling/spouse relationships, co-occurrence analysis, family search.
**Touches:** Faces panel (family view), search panel (family filters)

### 4.4 - Celebrity Face Identification
**Doc:** `celebrity-face-identification.md`
**Why last in tier:** Nice-to-have extension. Uses cloud APIs (Rekognition) or local embeddings. Benefits from the face assignment improvements in 4.1.
**Touches:** Faces panel, settings (API config)

---

## Tier 5: Pet & Audio Intelligence

Parallel to faces but independent - can be done alongside Tier 4 if desired.

### 5.1 - Pet Detection & Tracking
**Doc:** `pet-detection-and-tracking.md`
**Why here:** YOLO detection works. This adds visual embeddings, breed classification, and temporal tracking. Similar architecture to face tracking (Tier 4) so patterns can be reused.
**Touches:** Faces/Pets panel, search, AI summaries

### 5.2 - Audio Transcription Integration
**Doc:** `audio-transcription-integration.md`
**Why here:** Whisper backend exists. Wire into UI workflow, add audio settings, display transcriptions in file details. Independent of image features.
**Touches:** Settings panel, analysis runner, file details

---

## Tier 6: Data Portability & Reporting

Once all analysis features generate data, make that data portable and reportable.

### 6.1 - Export & Reporting
**Doc:** `export-and-reporting.md`
**Why now:** All panels now produce rich data. Add export to duplicates, faces, search results. Unified PDF/CSV reports.
**Touches:** All panels (Export buttons), report generator

### 6.2 - AI Metadata Embedding
**Doc:** `ai-metadata-embedding.md`
**Why now:** Write face names, tags, summaries, quality scores into EXIF/IPTC/XMP. Depends on all AI analysis being complete and correct before writing to files.
**Touches:** Files panel, faces panel, settings (write preferences)

---

## Tier 7: Advanced Analytics & Corpus

Power-user features that require all foundational data to exist.

### 7.1 - Storage Analytics
**Doc:** `storage-analytics.md`
**Why here:** Visualize storage usage, duplicate waste, redundancy. Benefits from having complete scan + duplicate + drive data.
**Touches:** New Storage Analytics panel/dashboard

### 7.2 - Document Corpus Analysis
**Doc:** `document-corpus-analysis.md`
**Why last:** Most specialized feature. Requires OCR, FTS5, NER, graph analysis. Serves document-heavy use cases.
**Touches:** New Corpus Analysis panel, visualization components

---

## Quick Reference: Dependency Graph

```
Tier 1 (foundations)
  1.1 AI UI Controls ──────────────────────────────┐
  1.2 Undo/Rollback                                 |
  1.3 Quality Scoring UI ──┐                        |
  1.4 Comparison Enhancements                       |
                           |                        |
Tier 2 (expanded dedup)   |                        |
  2.1 Video Dedup ─────────┤                        |
  2.2 Cross-Format Dedup ──┘                        |
                                                    |
Tier 3 (organization)                              |
  3.1 Screenshot/Burst Enhancements                 |
  3.2 Live Photo Enhancements                       |
  3.3 JPEG Recovery UI                              |
  3.4 Folder Watching                               |
                                                    |
Tier 4 (people) ───────────────────────────────────┘
  4.1 Intelligent Assignment
  4.2 Age Progression ──── depends on 4.1
  4.3 Family Groups ────── depends on 4.1, 4.2
  4.4 Celebrity ID

Tier 5 (parallel to T4)
  5.1 Pet Tracking
  5.2 Audio Transcription

Tier 6 (portability) ──── depends on T1-T5 data
  6.1 Export & Reports
  6.2 Metadata Embedding

Tier 7 (analytics) ────── depends on T1-T6 data
  7.1 Storage Analytics
  7.2 Corpus Analysis
```

## Estimated Effort per Item

| Item | Effort | Type |
|------|--------|------|
| 1.1 AI UI Controls | Small | UI wiring |
| 1.2 Undo/Rollback | Medium | New system |
| 1.3 Quality Scoring UI | Small | UI wiring |
| 1.4 Comparison Enhancements | Medium | UI work |
| 2.1 Video Dedup | Medium | Backend + UI |
| 2.2 Cross-Format Dedup | Medium | Backend + UI |
| 3.1 Screenshot/Burst Enhancements | Small | Wiring |
| 3.2 Live Photo Enhancements | Small | Refinement |
| 3.3 JPEG Recovery UI | Small | UI wiring |
| 3.4 Folder Watching | Medium | New system |
| 4.1 Intelligent Assignment | Medium | Backend logic |
| 4.2 Age Progression | Large | ML + Backend |
| 4.3 Family Groups | Medium | Backend + UI |
| 4.4 Celebrity ID | Medium | API integration |
| 5.1 Pet Tracking | Large | ML + Backend |
| 5.2 Audio Transcription | Small | UI wiring |
| 6.1 Export & Reports | Medium | UI + generation |
| 6.2 Metadata Embedding | Medium | File writing |
| 7.1 Storage Analytics | Medium | New panel |
| 7.2 Corpus Analysis | Large | NLP + UI |
