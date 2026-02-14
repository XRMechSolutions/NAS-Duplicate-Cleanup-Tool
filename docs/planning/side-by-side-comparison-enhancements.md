# Side-by-Side Comparison UI Enhancements

## Current State: Fully Implemented

The basic side-by-side comparison feature is fully implemented in the duplicates panel:

### Comparison View (ui/duplicates_panel.py:633-725)

- Two-panel comparison layout showing duplicate pair side by side
- Displays file thumbnails at reasonable preview size
- Shows metadata below each image: path, size, date, dimensions
- Navigation: previous/next pair within a duplicate group
- "Keep Left" / "Keep Right" action buttons
- Works for image files with thumbnail generation

### What Works Well

- Clear visual comparison of two duplicate candidates
- Metadata displayed for informed decision-making
- Action buttons for quick resolution
- Integration with duplicate group navigation

## Enhancement Opportunities

### 1. Synchronized Zoom and Pan

**Current limitation:** Images displayed at fixed preview size. No way to zoom in and compare fine detail (compression artifacts, sharpness, noise).

**Enhancement:**
- Mouse wheel zoom on either panel
- Synchronized zoom: zooming one panel zooms the other to the same region
- Click-and-drag pan with synchronized scrolling
- "Fit to window" / "1:1 pixel" / "Zoom to face" presets
- Zoom indicator showing current magnification level

### 2. Quality Overlay

**Current limitation:** Quality scores exist (ai/quality.py) but are not shown in comparison view.

**Enhancement:**
- Overlay quality metrics on each image:
  - Blur score (sharpness)
  - Exposure score
  - Noise level
  - Contrast score
  - Overall quality rating
- Color-coded indicators: green (good), yellow (fair), red (poor)
- Highlight the better image with a subtle border or badge
- "Quality Winner" label on the recommended keeper

### 3. Pixel Difference View

**Enhancement:** Show exactly where two images differ at the pixel level.

**Modes:**
- **Side-by-side** (current): two images next to each other
- **Overlay blend**: crossfade slider between the two images (0% = left, 100% = right)
- **Difference map**: show pixel differences as a heatmap (identical regions = black, different = bright)
- **Flicker**: rapidly alternate between the two images to spot differences
- **Swipe**: vertical or horizontal divider line that user drags to reveal one image vs the other

### 4. EXIF/Metadata Comparison Table

**Current limitation:** Basic metadata shown (path, size, date).

**Enhancement:** Detailed side-by-side metadata table:
- Camera make/model
- Lens info
- ISO, shutter speed, aperture
- GPS coordinates and location name
- EXIF DateTimeOriginal vs file system date
- Color space, bit depth
- Compression quality (JPEG quality level if detectable)
- AI-generated tags and summary (if available)
- Differences highlighted in color

### 5. Multi-File Comparison

**Current limitation:** Only two files compared at once.

**Enhancement:** When a duplicate group has 3+ members:
- Grid view: show all group members in a grid (2x2, 3x2, etc.)
- Carousel: swipe through all members with the selected keeper highlighted
- Ranking view: files ordered by quality score, best at top
- Bulk selection: check/uncheck files to keep or delete
- "Keep Best, Delete Rest" one-click action

### 6. Audio/Video Comparison

**Enhancement:** Extend comparison beyond images:
- Video: show keyframe thumbnails, duration, resolution, codec, bitrate
- Audio: show waveform visualization, duration, format, bitrate, sample rate
- Documents: show side-by-side text content (diff view)
- Play buttons for audio/video preview

## Implementation Phases

### Phase 1: Quality Overlay

- Fetch quality scores from database for both files
- Display quality metrics as overlay or sidebar panel
- Highlight the recommended keeper based on quality
- Add "Keep Best Quality" button that auto-selects the higher-quality file
- Fall back gracefully when quality scores haven't been computed

### Phase 2: EXIF Comparison Table

- Extract full EXIF data for both files
- Display in a two-column comparison table below the images
- Highlight differences between the two files
- Collapsible sections: Camera, Exposure, Location, AI Analysis, File Info

### Phase 3: Pixel Difference Modes

- Implement overlay blend with slider control
- Implement difference heatmap (compute per-pixel absolute difference)
- Implement swipe divider (draw both images, clip to divider position)
- Mode selector: Side-by-Side | Blend | Difference | Swipe
- DearPyGUI implementation using draw layers and texture manipulation

### Phase 4: Synchronized Zoom

- Add mouse wheel zoom handler to both image panels
- Track zoom level and pan offset per panel
- Synchronize: when one panel zooms/pans, apply same transform to the other
- Render zoomed region from full-resolution image (not just scaling the thumbnail)
- Requires loading full-resolution images on demand (memory management)

### Phase 5: Multi-File Grid

- When group has 3+ files, show grid view option
- Flexible grid layout (auto-columns based on file count)
- Selection checkboxes on each grid cell
- Quality ranking mode: sort grid by quality score
- "Keep Selected, Remove Rest" batch action

## Technical Considerations

### DearPyGUI Rendering

- **Overlay blend**: Create two textures, blend in shader or pre-compute blended image
- **Difference map**: Compute with NumPy/PIL, render as texture
- **Swipe divider**: Use drawlist with clipping regions or render two textures with viewport cropping
- **Zoom**: Use `dpg.set_value()` on plot axes or custom draw commands with transform
- **Performance**: Full-resolution images can be large; load on demand, cache current pair only

### Memory Management

- Two full-resolution images in memory for comparison (could be 20-50 MB each for RAW)
- Preload next pair while current is displayed
- Unload previous pair when advancing
- For grid view with 5+ images, use thumbnails with zoom-to-full on click

### Pixel Difference Computation

```python
# Difference map using PIL
from PIL import ImageChops
diff = ImageChops.difference(img1.resize(common_size), img2.resize(common_size))
# Amplify for visibility
diff = diff.point(lambda x: min(255, x * 3))
```

### Quality Score Display

```python
# Quality metrics from ai/quality.py
scores = {
    "blur": quality_scorer.score_blur(image),      # 0-100
    "exposure": quality_scorer.score_exposure(image),  # 0-100
    "noise": quality_scorer.score_noise(image),     # 0-100
    "contrast": quality_scorer.score_contrast(image),  # 0-100
    "overall": quality_scorer.score_overall(image),    # 0-100
}
```

## Edge Cases

| Scenario | Handling |
|---|---|
| Images of very different resolutions | Resize to common dimensions for difference map; show original dimensions in metadata |
| One file is corrupt/unreadable | Show error placeholder, skip comparison features that need both images |
| RAW vs JPEG comparison | Convert RAW to viewable format for display; note format difference prominently |
| Video files in comparison | Show keyframe thumbnails instead of full video; show codec/duration metadata |
| Very large images (>50 MP) | Downsample for display; load full resolution only for zoomed region |
| Identical images (difference map is all black) | Show "Images are pixel-identical" message |

## Integration Points

- **Quality Scorer** (ai/quality.py) - Provide quality metrics for overlay display
- **Metadata Extractor** - Full EXIF data for comparison table
- **Resolver** - Quality-based keeper selection integrates with comparison actions
- **Duplicate Detection** - Similarity score displayed in comparison header
- **Cross-Format Dedup** - Format differences highlighted in comparison metadata
