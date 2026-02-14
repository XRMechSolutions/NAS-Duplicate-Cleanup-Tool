# AI Metadata Embedding

## Goal

Write AI-generated data (face names, object detections, scene classifications, summaries, tags, pet names) back into image file metadata so it is permanently embedded and portable. Photos should carry their AI analysis with them when copied, moved, or viewed in other applications (Windows Explorer, Adobe Lightroom, Google Photos, Apple Photos, digiKam, etc.).

## Current State

- **Reading**: Full EXIF read support via exifread + Pillow
- **Writing**: Only EXIF orientation tag is written (during manual rotation)
- **AI data storage**: All AI results (summaries, tags, faces, pets, scenes, objects, OCR) stored in SQLite only
- **No XMP, IPTC, or keyword writing** to files
- **No sidecar file support**

## Metadata Standards

Three main standards exist for photo metadata. For maximum compatibility, write to all three where possible.

### EXIF (Exchangeable Image File Format)

- Embedded in JPEG/TIFF files
- Limited tag set, primarily camera/capture data
- Relevant writable fields:
  - `ImageDescription` (0x010E) - Free-text description
  - `UserComment` (0x9286) - Extended comment field
  - `XPKeywords` (0x9C9E) - Windows keywords (semicolon-separated)
  - `XPSubject` (0x9C9F) - Windows subject
  - `XPComment` (0x9C9C) - Windows comment
- **Limitation**: No structured face regions, limited text length

### IPTC (International Press Telecommunications Council)

- Industry standard for photo asset management
- Relevant writable fields:
  - `Keywords` (2:25) - List of keywords/tags
  - `Caption/Abstract` (2:120) - Description text
  - `Headline` (2:105) - Short description
  - `Object Name` (2:05) - Title
  - `Supplemental Categories` (2:20) - Categories
- **Well supported** by Lightroom, Photoshop, digiKam, most DAM software

### XMP (Extensible Metadata Platform)

- Adobe-developed, most flexible and extensible
- Can be embedded in file or stored as sidecar (.xmp)
- Relevant namespaces and fields:
  - `dc:description` - Description/summary
  - `dc:subject` - Keywords/tags array
  - `dc:title` - Title
  - `xmp:Label` - Color label
  - `xmp:Rating` - Star rating (1-5)
  - `Iptc4xmpExt:PersonInImage` - People names (string array)
  - `mwg-rs:Regions` - **Face regions with names and bounding boxes** (MWG standard)
  - `lr:hierarchicalSubject` - Hierarchical tags (Lightroom compatible)
  - `digiKam:TagsList` - digiKam tag hierarchy

### MWG Face Regions (Most Important for Faces)

The Metadata Working Group (MWG) defines a standard for face regions in XMP that is recognized by Lightroom, Picasa, Windows Photo Gallery, digiKam, and others:

```xml
<mwg-rs:Regions>
  <mwg-rs:RegionList>
    <rdf:Bag>
      <rdf:li>
        <mwg-rs:Name>John Smith</mwg-rs:Name>
        <mwg-rs:Type>Face</mwg-rs:Type>
        <mwg-rs:Area
          stArea:x="0.45"   <!-- center x, normalized 0-1 -->
          stArea:y="0.32"   <!-- center y, normalized 0-1 -->
          stArea:w="0.15"   <!-- width, normalized 0-1 -->
          stArea:h="0.20"   <!-- height, normalized 0-1 -->
          stArea:unit="normalized"/>
      </rdf:li>
    </rdf:Bag>
  </mwg-rs:RegionList>
</mwg-rs:Regions>
```

This means other applications can display face boxes and names on photos that DupliCleaner has analyzed.

## What to Write

### Per Image

| AI Data | EXIF Field | IPTC Field | XMP Field |
|---------|-----------|------------|-----------|
| AI summary | ImageDescription, UserComment | Caption/Abstract | dc:description |
| Tags (scene, objects, etc.) | XPKeywords | Keywords | dc:subject |
| Face names | XPSubject | - | Iptc4xmpExt:PersonInImage |
| Face regions + names | - | - | mwg-rs:Regions (MWG standard) |
| Pet names | XPKeywords (as tag) | Keywords | dc:subject (as tag) |
| Quality score | - | - | xmp:Rating (mapped to 1-5 stars) |
| Scene category | XPKeywords (as tag) | Supplemental Categories | lr:hierarchicalSubject |
| OCR text | UserComment (if short) | - | dc:description (appended) |
| Detected objects | XPKeywords (as tags) | Keywords | dc:subject |

### Tag Hierarchy Example

Using Lightroom-compatible hierarchical subjects:

```
AI|Scene|Beach
AI|Scene|Sunset
AI|Objects|Dog
AI|Objects|Surfboard
AI|People|John Smith
AI|People|Jane Smith
AI|Pets|Max
AI|Quality|4 Stars
```

## Testing Safety Protocol

Metadata writing modifies original image files and is inherently risky. A bug in the writer could corrupt photos permanently. All development and testing MUST use copies, never originals.

### Test Directory Setup

- Create a dedicated test directory (e.g., `tests/fixtures/metadata_write_test/`)
- Copy a representative sample of real images into it before each test run:
  - JPEG with full EXIF (camera photo)
  - JPEG with minimal/no EXIF (screenshot, web download)
  - JPEG with existing IPTC/XMP keywords (previously tagged in Lightroom, etc.)
  - JPEG with MWG face regions (previously face-tagged in another app)
  - TIFF, PNG, HEIC if supported
  - Large file (>10MB) to test performance
  - Small file (<100KB) to test edge cases
- Automated test fixture: `conftest.py` copies test images to a temp directory, tests run against copies, temp directory is cleaned up after
- NEVER point tests or development at real photo directories

### Validation After Every Write

- Re-read the file after writing and verify:
  - File is still a valid image (can be opened by PIL/OpenCV)
  - File size is reasonable (not zero, not drastically changed)
  - Original EXIF data is preserved (camera make/model, dates, GPS)
  - New metadata was written correctly
  - Existing user keywords were not removed
- Compute hash before and after to detect unexpected changes to pixel data
- If any validation fails, restore from backup immediately

### Development Workflow

1. **Unit tests first**: Write against fixture copies in temp directories
2. **Manual testing**: Copy a handful of personal photos to a scratch folder, run writer, inspect in Windows Explorer / exiftool / Lightroom
3. **Batch testing**: Copy a larger set (~100 files), batch write, verify all pass validation
4. **Production safeguard**: First real use always defaults to dry-run mode, user must explicitly confirm

### Automated Test Cases

- Write keywords to clean JPEG -> verify keywords appear
- Write keywords to JPEG with existing keywords -> verify merge (no data loss)
- Write MWG face regions -> verify readable by exiftool and digiKam
- Write summary to ImageDescription -> verify readable in Windows Explorer
- Write to read-only file -> verify graceful error (no crash, no corruption)
- Write to corrupt/truncated JPEG -> verify graceful error
- Write very long summary (>10KB) -> verify field truncation or fallback
- Round-trip: write metadata, re-read, compare to expected values
- Pixel integrity: hash pixel data before and after write, confirm identical

## Implementation Phases

### Phase 1: Metadata Writer Module

- Create `src/duplicleaner/core/metadata_writer.py`
- Add dependency: `piexif` for EXIF writing, `python-xmp-toolkit` or `pyexiv2` for XMP/IPTC
- Alternative: use `exiftool` subprocess (most robust, handles all formats and standards)
- Implement write functions for each standard (EXIF, IPTC, XMP)
- Preserve all existing metadata when writing (read-modify-write pattern)
- Handle file format differences (JPEG, TIFF, PNG, HEIC)

### Phase 2: Data Mapping

- Map AI database fields to metadata fields:
  - `ai_summaries.summary` -> description fields
  - `file_tags` -> keyword fields
  - `faces` (with person names + bboxes) -> MWG face regions
  - `pet_detections` (with pet names) -> keyword tags
  - `scene_analysis` -> category tags
  - `ai_summaries.quality_score` -> star rating
  - `ocr_results` -> description or comment field
- Handle conflicts: what if the image already has keywords? Merge, not replace.
- Prefix AI-generated tags to distinguish from manual tags (configurable)

### Phase 3: Write Operations

- "Export Metadata" action: write AI data to selected files
- Batch export: write metadata for all analyzed files in a scan
- Dry-run mode: preview what would be written without modifying files
- Backup originals before writing (configurable)
- Progress reporting for batch operations
- Undo support: store original metadata for rollback

### Phase 4: XMP Sidecar Support

- Option to write XMP sidecar files instead of modifying originals
- Sidecar naming: `photo.jpg` -> `photo.xmp`
- Non-destructive: original file never modified
- Useful for RAW files that shouldn't be modified
- Configurable per file type: embed for JPEG, sidecar for RAW

### Phase 5: UI Integration

- "Write Metadata" button in Files tab and Faces tab
- Settings: which standards to write (EXIF/IPTC/XMP/sidecar)
- Settings: which data to include (faces, tags, summary, rating)
- Settings: tag prefix (e.g., "AI|" or "DupliCleaner|" or none)
- Settings: backup originals before writing
- Preview panel: show what metadata will be written before confirming
- Per-file and batch operations
- Status column showing which files have had metadata written

### Phase 6: Round-Trip Sync

- On re-scan, read metadata from files and compare to database
- Detect external changes (user edited tags in Lightroom)
- Merge strategy: database wins, file wins, or manual resolve
- Sync indicator: show if file metadata matches database

## Library Options

### Option A: exiftool (subprocess)

- **Pros**: Most robust, handles every format and standard, battle-tested
- **Cons**: External dependency (Perl), subprocess overhead
- **Best for**: Maximum compatibility, handles edge cases
- Usage: `exiftool -PersonInImage="John Smith" -Keywords+="Beach" photo.jpg`

### Option B: piexif + python-xmp-toolkit

- **Pros**: Pure Python (piexif), no external deps for EXIF
- **Cons**: piexif is EXIF-only, python-xmp-toolkit needs Exempi C library
- **Best for**: Simple EXIF writes, may struggle with XMP face regions

### Option C: pyexiv2

- **Pros**: Handles EXIF + IPTC + XMP in one library
- **Cons**: Requires libexiv2 C library, Windows builds can be tricky
- **Best for**: Full metadata support if the C library dependency is acceptable

### Recommended: exiftool with piexif fallback

- Use exiftool for full XMP/IPTC/MWG writes (most reliable)
- Fallback to piexif for basic EXIF writes if exiftool not installed
- Bundle exiftool with the application or prompt user to install

## Technical Considerations

### File Safety

- ALWAYS read-modify-write to preserve existing metadata
- NEVER overwrite user-added keywords or descriptions
- NEVER operate on original files during development or testing (see Testing Safety Protocol above)
- Create backup before first write (configurable, default ON)
- Validate file integrity after write (re-read and verify)
- Verify pixel data hash is unchanged after metadata write
- Handle read-only files and permission errors gracefully
- Default to dry-run mode on first use, require explicit user confirmation to write
- Log every file modification to the audit log with before/after metadata hashes

### Performance

- Metadata writing is I/O bound, not CPU bound
- Batch writes can process ~100 files/second
- exiftool supports batch mode (-stay_open) for much faster batch processing
- Queue writes and process in background thread

### Format Support

| Format | EXIF | IPTC | XMP Embed | XMP Sidecar | Face Regions |
|--------|------|------|-----------|-------------|--------------|
| JPEG | Yes | Yes | Yes | Yes | Yes |
| TIFF | Yes | Yes | Yes | Yes | Yes |
| PNG | Limited | No | Yes | Yes | Yes |
| HEIC | Yes | No | Yes | Yes | Yes |
| RAW (CR2, NEF, ARW) | Read only | No | Sidecar only | Yes | Yes |
| WebP | Limited | No | Yes | Yes | Varies |

### Face Region Coordinate Conversion

DupliCleaner stores face bboxes as pixel coordinates (x1, y1, x2, y2). MWG regions use normalized center+size format:

```python
# Convert DupliCleaner bbox to MWG region
mwg_x = (x1 + x2) / 2 / image_width    # center x, normalized
mwg_y = (y1 + y2) / 2 / image_height   # center y, normalized
mwg_w = (x2 - x1) / image_width         # width, normalized
mwg_h = (y2 - y1) / image_height        # height, normalized
```

Face bboxes are in ORIENTED (displayed) coordinates, which is correct for MWG regions since they reference the displayed image.

## Database Schema Extensions

- `metadata_writes` table: file_id, write_date, standards_written, fields_written, backup_path
- Track which files have had metadata exported vs pending
- Store original metadata hash for change detection
