# JPEG and Corrupt File Recovery

## Goal

Integrate DupliCleaner's existing suite of JPEG recovery utilities into the main application workflow. Users with NAS storage frequently encounter corrupted photos from disk failures, incomplete transfers, or file system errors. The recovery tools should be accessible through the UI and integrated into the scan/analysis pipeline.

## Current Capabilities (Fully Implemented, Not Integrated)

Eight recovery modules exist in `src/duplicleaner/utils/` with increasing levels of aggressiveness:

| Module | Strategy | Use Case |
|--------|----------|----------|
| `jpeg_recovery.py` | PIL tolerant mode re-encoding with EXIF preservation | Minor corruption, truncated files |
| `jpeg_binary_repair.py` | Binary-level JPEG marker reconstruction, strip junk bytes | Header damage, embedded garbage data |
| `jpeg_smart_recovery.py` | Multi-SOI marker extraction, test each embedded JPEG stream | Multiple images concatenated in one file |
| `jpeg_aggressive_recovery.py` | Extract EXIF dimensions, find full-size image offsets | Severely damaged headers |
| `jpeg_deep_recovery.py` | Error-tolerant decoding with EOI padding at various positions | Truncated/partial files |
| `jpeg_fragment_separator.py` | Extract distinct photos from mixed corrupt files, deduplicate fragments | Multiple photos merged into one file |
| `jpeg_gap_filler.py` | Find valid thumbnails, upscale to fill gray/missing pixel areas | Partial data loss with intact thumbnail |
| `jpeg_hybrid_recovery.py` | Combine actual data recovery with thumbnail-based gap filling | Best-effort recovery combining multiple strategies |

## What Needs to Be Built

### Phase 1: Corruption Detection During Scan

- During file scanning, detect potentially corrupt images:
  - Files that fail to open with PIL/OpenCV
  - Files with truncated data (file size much smaller than expected for resolution)
  - Files with invalid JPEG markers
  - Files that open but produce partial/gray images
- Flag corrupt files in database with corruption type and severity
- Display corruption count in scan results summary

### Phase 2: Recovery Pipeline

- Create a `RecoveryManager` class that orchestrates the recovery modules
- Apply recovery strategies in order from least to most aggressive:
  1. PIL tolerant mode (fastest, least risk)
  2. Binary marker repair
  3. Smart multi-SOI extraction
  4. Aggressive offset scanning
  5. Deep error-tolerant decoding
  6. Hybrid recovery with gap filling
- Stop at first successful recovery
- Store recovered files alongside originals (never overwrite)
- Log recovery results: which strategy succeeded, pixel recovery percentage

### Phase 3: UI Integration

- "Corrupt Files" section in the scan results or a dedicated panel
- List corrupt files with thumbnails (if partially recoverable)
- "Attempt Recovery" button per file or batch recovery for all
- Recovery preview: show before/after comparison
- Recovery options: save recovered copy, replace original, skip
- Progress indicator for batch recovery operations

### Phase 4: Advanced Recovery

- Extend beyond JPEG to other formats:
  - PNG recovery (chunk-based repair)
  - HEIC/HEIF recovery
  - Video file repair (MP4 atom reconstruction)
  - RAW format recovery (CR2, NEF, ARW)
- Cross-file recovery: if the same photo exists on multiple drives with different corruption patterns, combine good sections from each copy
- Integration with drive redundancy checking: prioritize recovery for files that exist on only one drive

## Integration Points

### Scanner Integration

- Add corruption check during hash phase (files are already being read)
- Store corruption flag and details in FileRecord
- Minimal overhead: PIL open attempt is fast, only detailed analysis on failures

### Duplicate Detection Integration

- A corrupt file and its recovered version are the same photo, not duplicates
- Link recovered files back to their corrupt originals
- When a duplicate exists on another drive in good condition, flag for user (recovery may be unnecessary)

### Drive Manager Integration

- Cross-reference corrupt files with backup copies on other drives
- Alert: "File X is corrupt on Drive A but healthy on Drive B"
- Suggest copying healthy version rather than attempting recovery

### Action Engine Integration

- "Recover" as a new action type alongside delete/trash/move
- Audit log entries for recovery operations
- Undo support: delete recovered copy to revert

## Technical Considerations

### Recovery Quality Metrics

- Pixel recovery percentage: how much of the image was recovered vs gray/missing
- EXIF preservation: was metadata recovered alongside pixel data
- Visual quality score: run quality analyzer on recovered image
- Hash comparison: if a good copy exists elsewhere, compare hashes to verify recovery accuracy

### Storage

- Recovered files stored in a configurable recovery output directory
- Naming convention: `original_name_recovered.jpg`
- Preserve original corrupt file (never modify in place)
- Track recovery history in database

### Performance

- Recovery is CPU-intensive but not time-critical (user-initiated, not during scan)
- Batch recovery should use thread pool for parallelism
- Progress reporting per file and overall batch

## Database Schema Extensions

- `corrupt_files` table: file_id, corruption_type, severity, detected_date
- `recovery_attempts` table: file_id, strategy_used, success, pixel_recovery_pct, recovered_path, attempt_date
