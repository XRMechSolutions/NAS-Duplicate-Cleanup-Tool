# Live Photo / Video-Photo Matching Enhancements

## Current State: Fully Implemented

Live Photo matching is already fully implemented in the codebase:

### Detection (core/organizer.py:660-706)

- `detect_live_photos()` pairs .jpg/.jpeg photos with .mov/.mp4 videos
- Matching criteria: same stem name, within 3 seconds of each other, same directory
- Returns `LivePhotoPair` dataclass with photo path, video path, and time difference
- Handles case-insensitive extension matching

### Organization Support (core/organizer.py)

- Live Photo pairs are kept together during organization
- When a photo moves, its paired video moves to the same destination
- Live Photo column shown in organize preview export

### UI Display (ui/organize_panel.py)

- Live Photo pairs displayed in organization preview
- "Live Photo" column in organize table

## Enhancement Opportunities

While the core feature works, several improvements would make it more useful.

### 1. Cross-Directory Live Photo Matching

**Current limitation:** Only matches photos and videos in the same directory.

**Enhancement:** After phone sync or manual copying, the photo and video components of a Live Photo may end up in different directories (e.g., photos sorted into date folders but videos left in a flat dump folder).

- Allow cross-directory matching when filenames match and timestamps are close
- Configurable: same-directory-only (default, fast) or cross-directory (slower, catches separated pairs)
- Show separated pairs as actionable items: "Reunite 12 separated Live Photo pairs"

### 2. Live Photo Duplicate Handling

**Current limitation:** Duplicate detection treats photos and videos independently.

**Enhancement:** When a photo is identified as a duplicate, check if it has a Live Photo video component:
- If keeping the photo, keep its video too
- If deleting the photo, offer to delete the video component
- Show Live Photo context in duplicate group view: "This photo has a Live Photo video (2.3 MB)"
- Prevent orphaned videos (video without its photo)

### 3. Apple Live Photo Metadata Detection

**Current limitation:** Matching relies on filename stems and timestamps.

**Enhancement:** Apple Live Photos contain specific metadata:
- EXIF `MakerNote` contains `ContentIdentifier` (UUID shared between photo and video)
- QuickTime metadata in .mov contains matching `ContentIdentifier`
- Using ContentIdentifier is more reliable than filename matching (handles renamed files)
- Fall back to filename/timestamp matching when metadata is absent

### 4. Samsung Motion Photo / Google Motion Photo Support

**Current limitation:** Only handles separate file pairs.

**Enhancement:** Samsung and Google embed the video directly inside the JPEG:
- Samsung Motion Photos: video appended after JPEG EOI marker
- Google Motion Photos: video embedded with XMP metadata pointing to offset
- Detect embedded videos using file analysis
- Option to extract embedded video as separate file
- Show Motion Photo indicator in file browser

### 5. Live Photo Browser

**Enhancement:** Dedicated view for browsing all detected Live Photo pairs:
- Grid showing Live Photo thumbnails with play icon overlay
- Click to preview: show photo with option to play the video clip
- Filter: paired, orphaned (photo without video), orphaned (video without photo)
- Batch actions: extract all video components, reunite separated pairs, delete all video components

## Implementation Phases

### Phase 1: Cross-Directory Matching

- Add optional cross-directory mode to `detect_live_photos()`
- Index all photos and videos by stem name, then match across directories
- Timestamp proximity check (within 5 seconds for cross-directory)
- UI toggle in organize panel: "Match Live Photos across directories"

### Phase 2: Duplicate Integration

- When building duplicate groups, annotate files that are Live Photo components
- In duplicate resolution UI, show Live Photo pairing info
- "Keep with Live Photo" option in resolver
- Warn before deleting a photo that has a Live Photo video (or vice versa)

### Phase 3: Apple ContentIdentifier Matching

- Extract ContentIdentifier from EXIF MakerNote (photo) and QuickTime metadata (video)
- Primary matching: ContentIdentifier UUID
- Fallback: filename + timestamp (current approach)
- More reliable for renamed or moved files

### Phase 4: Embedded Motion Photo Detection

- Detect Samsung/Google Motion Photos by scanning for video data after JPEG EOI
- Read XMP metadata for Google Motion Photo offset
- Option to extract embedded video to separate file
- Show "Motion Photo" indicator in file listings

## Technical Considerations

### ContentIdentifier Extraction

```python
# Photo (JPEG): Read from EXIF MakerNote or XMP
# Requires: exifread or piexif for MakerNote parsing
# XMP tag: apple-fi:ContentIdentifier

# Video (MOV): Read from QuickTime metadata
# Requires: ffprobe or pymediainfo
# Atom: com.apple.quicktime.content.identifier
```

### Samsung Motion Photo Detection

```python
# Samsung embeds video after JPEG EOI marker (0xFFD9)
# Search backwards from end of file for secondary JPEG SOI or video header
# MotionPhoto_Data XMP tag indicates presence
# Samsung-specific: look for 'MotionPhoto_Data' in XMP
```

### Performance

- ContentIdentifier extraction adds per-file overhead (read EXIF/QuickTime metadata)
- Cross-directory matching is O(n*m) without indexing; use hash map on stem names
- Embedded video detection requires reading file tail (fast seek, no full read)

## Edge Cases

| Scenario | Handling |
|---|---|
| Renamed Live Photo (photo renamed, video still original name) | ContentIdentifier matching catches this; filename matching misses it |
| Live Photo from WhatsApp (different naming convention) | Timestamp matching with relaxed filename requirement |
| Multiple videos matching one photo timestamp | Prefer same-directory, then closest timestamp |
| Very long Live Photo video (edited to extend) | Still matches by identifier; timestamp window may need widening |
| HEIC + MOV Live Photo (iPhone default) | Already handled by extension list in current implementation |
| Converted Live Photo (HEIC->JPG but video still MOV) | Filename stem matching still works |

## Integration Points

- **Organizer** - Already integrated for keeping pairs together during organization
- **Duplicate Detection** - Flag Live Photo components to prevent orphaning
- **Storage Analytics** - Report space used by Live Photo video components
- **File Browser** - Show Live Photo indicator icon
- **Metadata Embedding** - Preserve ContentIdentifier when writing metadata
