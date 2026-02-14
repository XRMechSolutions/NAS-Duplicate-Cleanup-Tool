# Screenshot and Burst Photo Detection

## Goal

Enhance the existing screenshot and burst photo detection with quality-based selection, Live Photo pairing, and tighter integration with the duplicate detection and organization workflows.

## Current Capabilities (Already Implemented)

### Screenshot Detection (organizer.py:540-548)

- **Filename pattern matching** - Detects "screenshot" in filename via regex
- **Screen dimension matching** - Checks against common screen resolutions (1920x1080, 2560x1600, etc.) defined at organizer.py:194
- **EXIF metadata analysis** - Checks for screenshot indicators in EXIF
- **Configurable handling** - ScreenshotHandling enum: SEPARATE (own folder), IGNORE (skip), SAME_FOLDER (treat like photos)
- **UI controls** - Dropdown in Organize panel (organize_panel.py:239-242)

### Burst Photo Detection (organizer.py:577-612)

- **Time-based grouping** - Photos taken within 2 seconds grouped as burst
- **Minimum burst size** - Requires 3+ photos to qualify as a burst
- **Configurable handling** - BurstHandling enum: KEEP_ALL, KEEP_BEST, SUBFOLDER
- **Burst group tracking** - `burst_group` field on file records (models.py:153)
- **Preview integration** - Shows burst count and group IDs in organize preview
- **UI controls** - Dropdown in Organize panel (organize_panel.py:248-251)

## What's Missing

### 1. Quality-Based Burst Selection

**Current state:** KEEP_BEST option exists in the enum but the selection logic doesn't use the quality scorer.

**Needed:**
- When KEEP_BEST is selected, run QualityScorer.get_best_from_group() on each burst
- Score all photos in burst by sharpness (blur_score), exposure, and noise
- Keep the sharpest, move others to a "burst extras" subfolder or mark for deletion
- Show quality scores in the burst preview UI so user can override

### 2. ML-Enhanced Screenshot Detection

**Current state:** Heuristic-only (dimensions + filename). Misses screenshots that have been cropped, resized, or renamed.

**Needed:**
- Detect screenshots by visual characteristics (UI elements, status bars, notification panels)
- CLIP-based classification: "screenshot of a phone app" vs "photograph"
- OCR integration: screenshots often contain dense text
- Detect screen recordings (video screenshots)

### 3. Live Photo Detection (Not Implemented)

**Current state:** No support for iOS Live Photo pairs (MOV + HEIC/JPG taken simultaneously).

**Needed:**
- Detect Live Photo pairs by matching timestamp + filename pattern
  - iOS naming: IMG_1234.HEIC + IMG_1234.MOV (same number, different extension)
  - Within 1-2 seconds of each other
- Group Live Photo pairs as a single logical item
- Organization options: keep both, keep photo only, keep video only
- Display paired video as a "live" indicator on the photo thumbnail

### 4. Screenshot Text Extraction Integration

**Current state:** OCR exists (easyocr/tesseract) but not specifically triggered for detected screenshots.

**Needed:**
- Auto-run OCR on detected screenshots
- Store extracted text for FTS5 search
- Use extracted text in AI summaries
- Group similar screenshots by content (e.g., all screenshots of the same app/website)

### 5. Burst Quality Preview in UI

**Current state:** Burst groups shown in organize preview but no quality comparison view.

**Needed:**
- Side-by-side thumbnail grid for each burst group
- Quality scores overlaid on thumbnails (blur, exposure)
- Green highlight on recommended "best" photo
- One-click "keep best, discard rest" action
- Manual override: click a different photo to keep instead

## Implementation Phases

### Phase 1: Wire Quality Scorer to Burst Selection

- In organizer.py burst handling, call QualityScorer when KEEP_BEST is selected
- Score each photo in burst group
- Select highest overall_score as keeper
- Log selection reasoning (blur_score, exposure_score for each)
- Existing code: quality.py:371 `get_best_from_group()` already does this

### Phase 2: Live Photo Pairing

- Add Live Photo detection in organizer.py
- Match by filename stem + timestamp proximity
- Add LivePhotoHandling enum: KEEP_BOTH, PHOTO_ONLY, VIDEO_ONLY
- UI dropdown alongside screenshot/burst handling
- Prevent Live Photo video from being flagged as a duplicate of the still

### Phase 3: Enhanced Screenshot Detection

- Add CLIP-based screenshot classification as secondary check
- Auto-trigger OCR on detected screenshots
- Store screenshot text in FTS5 for searching
- Configuration: screenshot detection sensitivity (strict/normal/aggressive)

### Phase 4: Burst Quality Preview UI

- Burst group viewer in organize preview
- Quality score overlay on thumbnails
- Recommended keeper highlighting
- Manual selection override
- Batch "keep best from all bursts" action

## Integration Points

- **Quality Scorer** (ai/quality.py) - Already implemented, needs to be called from burst selection
- **OCR** (ai/ocr.py) - Already implemented, needs screenshot-specific triggering
- **Organizer** (core/organizer.py) - Primary integration point for all detection
- **Comparator** (core/comparator.py) - Live Photos should not be flagged as cross-format duplicates
- **Metadata Embedding** - Screenshot/burst status could be written to IPTC keywords
