# Cross-Format Deduplication

## Goal

Detect when the same content exists in different file formats (same photo as .jpg and .png, same video as .mp4 and .mov, same document as .docx and .pdf) and present them as duplicate groups so users can keep the preferred format and remove the rest.

## Current Capabilities (Partially Working)

### Image Cross-Format Detection (comparator.py - working)

- **Perceptual hashing** works across image formats (line 295-323)
- `Image.open()` handles format conversion automatically (line 308)
- Auto-converts to RGB for comparison (line 310-311)
- Supported formats: .jpg, .jpeg, .png, .gif, .bmp, .tiff, .tif, .webp, .heic, .heif (line 439-440)
- Perceptual hash stored in database is format-independent

**This means:** A photo saved as both .jpg and .png WILL be detected as near-duplicates by the existing pipeline, as long as both files are in the scan. No additional work needed for basic image cross-format detection.

### What's NOT Handled

- Video cross-format detection (same video as .mp4 and .mov)
- Document cross-format detection (same document as .docx and .pdf)
- Audio cross-format detection (same song as .mp3 and .flac)
- Quality-aware format preference (keep PNG over JPEG when identical content)
- Resolution-aware comparison (same photo at different resolutions)

## What Needs to Be Built

### 1. Format-Aware Keeper Selection

**Current state:** When a .jpg and .png of the same photo are detected as duplicates, the resolver uses generic rules (newest, oldest, shortest path). It doesn't know that PNG is lossless and JPEG is lossy.

**Needed:**
- Format preference hierarchy for images: RAW > TIFF > PNG > HEIC > JPEG > WebP > GIF > BMP
- Lossless preferred over lossy when content is identical
- Higher resolution preferred (unless upscaled)
- Larger file at same resolution = less compression = better quality
- User-configurable format preferences

### 2. Resolution-Aware Comparison

**Current state:** Perceptual hash comparison finds visually similar images regardless of resolution, but doesn't track which copy is higher resolution.

**Needed:**
- When two images match perceptually, compare their resolutions
- Flag when a lower-resolution copy exists alongside the original
- Detect upscaled copies (compare file size ratios to resolution ratios)
- Prefer native resolution over upscaled
- Show resolution in duplicate group view: "4032x3024 vs 1920x1080"

### 3. Video Cross-Format Detection

**Current state:** Not implemented. Same video as .mp4 and .mov are treated as completely separate files.

**Needed:**
- Extract keyframes from both videos
- Compare keyframe perceptual hashes
- Match videos by: duration similarity + keyframe similarity + audio similarity
- Format preference: original format > re-encoded (check codec metadata)
- Resolution/bitrate preference: higher quality copy preferred
- Ties into video near-duplicate detection planning doc

### 4. Document Cross-Format Detection

**Current state:** Not implemented. Same document as .docx and .pdf are unrelated.

**Needed:**
- Extract text from both documents
- Compare text content (exact match or high similarity)
- Consider: a .pdf exported from .docx is usually the same content
- Format preference depends on use case:
  - For editing: keep .docx
  - For archival: keep .pdf
  - User-configurable preference

### 5. Audio Cross-Format Detection

**Current state:** Not implemented.

**Needed:**
- Audio fingerprinting (e.g., Chromaprint/AcoustID)
- Match same song in different formats (.mp3 vs .flac vs .wav)
- Format preference: lossless (FLAC/WAV) > high bitrate lossy (320kbps MP3) > low bitrate lossy
- Handle metadata differences (different tags on same audio content)

## Implementation Phases

### Phase 1: Format-Aware Image Keeper Selection

- Add format preference to resolver scoring
- When duplicate group contains mixed formats:
  - Rank by format preference hierarchy
  - Factor in resolution (higher = better)
  - Factor in file size relative to resolution (better compression indicator)
- Display format info in duplicate group UI
- "Keep Best Format" action alongside existing keep strategies

### Phase 2: Resolution Comparison

- Store image dimensions in file_records (already available via metadata_extractor)
- When displaying duplicate groups, show resolution for each copy
- Highlight resolution differences
- Detect obvious upscales: if file A is 4032x3024 (3.5MB) and file B is 4032x3024 (12MB), B might be an upscale from a smaller original
- Factor resolution into quality ranking

### Phase 3: Video Cross-Format (Depends on video-near-duplicate-detection.md)

- Extend video fingerprinting to detect same video in different containers/codecs
- Match by: duration (within 1 second) + keyframe hashes + resolution
- Format preference: higher bitrate/resolution > lower
- Original codec > re-encoded (detect re-encoding artifacts)

### Phase 4: Document Cross-Format

- Use existing OCR/text extraction to compare document content
- Text similarity threshold: 95%+ = likely same document in different format
- Present as cross-format duplicates
- Let user choose which format to keep

### Phase 5: Audio Cross-Format

- Add Chromaprint audio fingerprinting
- Match audio files by acoustic fingerprint
- Format/quality preference ranking
- Integrate with existing audio pipeline

## Technical Considerations

### Perceptual Hash Limitations

- Perceptual hashing handles format differences well for images
- Very different resolutions may produce different hashes (resize before hashing helps)
- Heavily compressed JPEG may hash differently from lossless PNG of same image
- Configurable similarity threshold helps (default 90%, lower for cross-format)

### Format Detection

- Don't trust file extension alone (a .jpg could actually be a PNG with wrong extension)
- Verify actual format using PIL/magic bytes
- Handle format conversion artifacts (JPEG artifacts visible in re-saved PNG)

### Performance

- Cross-format comparison is already handled by existing perceptual hash pipeline
- No additional per-file cost for images (hashes are already computed)
- Video/audio fingerprinting adds processing time (addressed in separate planning docs)
- Document text comparison is fast (already extracted for OCR/search)

### Edge Cases

| Scenario | Handling |
|---|---|
| Same image, one cropped | Perceptual hash may not match if crop is significant; lower threshold helps |
| Screenshot saved as PNG and JPEG | Detected as near-duplicate by existing pipeline |
| Photo edited in one format (brightness adjusted) | May or may not match depending on edit severity |
| RAW + JPEG from same camera shot | Often identical content; RAW preferred for quality |
| HEIC from iPhone + JPEG export | Common scenario; HEIC preferred (better compression, same quality) |
| Video recorded as MOV, converted to MP4 for sharing | Should match; prefer original MOV |
| PDF generated from DOCX vs scanned PDF of printed DOCX | Text extraction may match, but scanned version has OCR quality issues |

## Integration Points

- **Quality Scorer** - Factor quality into format preference when visual quality differs
- **Metadata Embedding** - Preferred format could be tagged before writing metadata
- **Storage Analytics** - Show space wasted by format redundancy ("12GB of JPEGs that also exist as PNGs")
- **Resolver** - New KEEP_BEST_FORMAT strategy option
- **Organizer** - During organization, detect and flag cross-format copies in source
