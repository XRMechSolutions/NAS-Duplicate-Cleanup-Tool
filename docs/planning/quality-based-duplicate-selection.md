# Quality-Based Duplicate Selection

## Goal

Use the existing image quality scoring system to automatically recommend the best copy from each duplicate group, rather than relying solely on file age, path, or size. When you have 5 copies of the same photo, the system should pick the sharpest, best-exposed version.

## Current Capabilities (Already Implemented)

### Quality Scorer (ai/quality.py - 389 lines, fully working)

- **Blur scoring** - Laplacian variance algorithm (line 99)
- **Exposure scoring** - Histogram analysis for under/overexposure (line 124)
- **Contrast scoring** - Standard deviation of pixel values (line 166)
- **Noise scoring** - High-pass filter approach (line 186)
- **Combined analysis** - Overall score 0-100 (line 213)
- **Boolean flags** - is_blurry, is_underexposed, is_overexposed
- **Batch processing** - analyze_batch() with progress tracking (line 291)
- **Group comparison** - compare_quality() ranks files, get_best_from_group() selects winner (lines 339, 371)
- **Database storage** - quality_score, blur_score, exposure_score columns in scene_analysis table

### Resolver Integration (core/resolver.py - partial)

- **KEEP_BEST_QUALITY strategy** exists (line 204-207)
- **Quality factor** - 10% weight in ranking score (line 451-455)
- **Config** - quality_analysis_enabled setting (config.py:163)

## What's Missing

### 1. Quality Scores Not Surfaced in Duplicates UI

**Current state:** Quality scores are computed and stored but not displayed in the duplicates panel.

**Needed:**
- Show quality score badge on each duplicate in the group view
- Color coding: green (sharp), yellow (acceptable), red (blurry/overexposed)
- Star rating overlay on thumbnails (map 0-100 to 1-5 stars)
- "Recommended" label on the highest-quality copy
- Sort duplicates within group by quality (best first)

### 2. Auto-Selection Not Wired to UI

**Current state:** KEEP_BEST_QUALITY strategy exists in resolver but the duplicates UI doesn't offer it as a one-click option.

**Needed:**
- "Keep Best Quality" button per duplicate group
- "Keep Best Quality for ALL groups" batch action
- Preview before committing: show which files would be kept/deleted
- Override: user can disagree with quality recommendation

### 3. Quality Analysis Not Run Automatically

**Current state:** Quality analysis must be triggered manually or via CLI.

**Needed:**
- Option to auto-run quality analysis during duplicate detection
- Lazy scoring: only score files that are in duplicate groups (saves time)
- Progress indicator during quality analysis
- Cache scores: don't re-analyze files that haven't changed

### 4. Multi-Factor Quality Ranking

**Current state:** Quality is 10% of resolver ranking, dominated by other factors.

**Needed:**
- Configurable quality weight (default 40-50% for photo collections)
- Factor in resolution: higher resolution copy preferred (unless it's just upscaled)
- Factor in format: lossless (PNG/TIFF) preferred over lossy (JPEG) when content identical
- Factor in file size: larger JPEG at same resolution likely has less compression
- Factor in metadata completeness: copy with EXIF preferred over stripped copy

### 5. Quality Comparison View

**Current state:** No side-by-side quality comparison in the UI.

**Needed:**
- Side-by-side view of duplicate group members
- Zoom to same region on all copies simultaneously
- Quality metrics panel showing scores for each copy
- Highlight differences: blur regions, exposure differences
- "This copy is blurry" / "This copy is well-exposed" annotations

## Implementation Phases

### Phase 1: Surface Quality in Duplicates UI

- Run quality analysis on duplicate group members (lazy: only when group is viewed)
- Display quality scores and badges in duplicate group list
- Highlight recommended keeper
- Sort group members by quality descending

### Phase 2: One-Click Quality Selection

- Add "Keep Best Quality" action per group
- Add "Keep Best Quality for All" batch action
- Integrate with existing action engine (trash/delete/quarantine the rest)
- Dry-run preview showing what would happen
- Undo support via existing action log

### Phase 3: Auto-Quality During Scan

- Option in settings: "Auto-analyze quality for duplicates"
- Run quality scorer on duplicate group members as they're discovered
- Store scores in database for instant display later
- Skip re-analysis for previously scored files (unless file changed)

### Phase 4: Multi-Factor Ranking

- Configurable weight sliders in settings:
  - Sharpness weight (default 30%)
  - Exposure weight (default 20%)
  - Resolution weight (default 20%)
  - Format/compression weight (default 15%)
  - Metadata completeness weight (default 15%)
- Resolution comparison: prefer higher native resolution
- Format preference: PNG/TIFF > JPEG (when content matches)
- JPEG quality estimation: larger file at same resolution = less compression
- EXIF completeness: prefer copies that retained full metadata

### Phase 5: Comparison View

- Side-by-side viewer for 2-4 images
- Synchronized zoom and pan
- Quality metric overlay
- Pixel-level diff highlighting
- Full-screen comparison mode

## Technical Considerations

### Performance

- Quality analysis is CPU-bound (~50ms per image for blur+exposure+noise)
- Lazy scoring (only when needed) keeps scan fast
- Batch scoring can use thread pool for parallelism
- Scores cached in database, only re-compute if file hash changes

### Edge Cases

| Scenario | Handling |
|---|---|
| All copies equally sharp | Fall back to other factors (resolution, format, metadata) |
| Highest quality copy is on a drive marked for cleanup | Warn user, suggest copying to preferred drive first |
| Quality scores are very close (within 5 points) | Mark as "similar quality", let user decide |
| Upscaled copy has higher resolution but same quality | Detect upscaling (compare file size ratios), prefer original resolution |
| Screenshot duplicate vs photo duplicate | Different quality expectations; screenshots should prioritize resolution/clarity, not exposure |

### Integration with Other Features

- **Burst detection** - Quality scorer selects best from burst (already planned)
- **Metadata embedding** - Quality score can be written as XMP rating (1-5 stars)
- **AI summaries** - Include quality assessment in summary text
- **Cross-format dedup** - When same image exists as PNG and JPEG, factor quality into keeper selection
