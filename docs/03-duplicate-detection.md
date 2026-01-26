# Duplicate Detection

## What It Does

The Duplicate Detection system finds files that are identical or nearly identical to each other. It groups these duplicates together so you can decide which copies to keep and which to remove.

The app detects two types of duplicates:

1. **Exact Duplicates** - Files with identical content (same bytes)
2. **Near Duplicates** - Files that are visually similar but not byte-for-byte identical (resized, recompressed, format-converted images)

## Exact Duplicates

### How They're Found

Two files are exact duplicates when they have the same SHA-256 hash. This means every single byte is identical - the files are perfect copies of each other.

Common causes of exact duplicates:
- Copying files to multiple locations for backup
- Downloading the same file multiple times
- Syncing the same folder to multiple drives
- Importing photos from the same camera card twice

### What You'll See

Go to the **Duplicates** tab to see your duplicate groups:

```
Exact Duplicates Found: 2,341 groups (7,892 files)
Potential space savings: 45.2 GB

[Group 1] vacation_photo.jpg - 4.2 MB (3 copies)
  [x] \\NAS\Photos\2023\Summer\vacation_photo.jpg
  [ ] C:\Users\clint\Pictures\Backup\vacation_photo.jpg
  [ ] \\NAS\Backup\Old Photos\vacation_photo.jpg

[Group 2] birthday_video.mp4 - 1.2 GB (2 copies)
  [x] \\NAS\Videos\Family\birthday_video.mp4
  [ ] D:\Temp Downloads\birthday_video.mp4
```

Each group shows:
- Representative filename and size
- Number of copies found
- Full paths to each copy
- Checkbox to select which to keep (checked) vs remove (unchecked)

### Filtering Exact Duplicates

Use the filter bar to narrow down results:

- **By drive** - Show only duplicates on a specific drive
- **By file type** - Images only, videos only, documents, etc.
- **By size** - Large files first (biggest space savings)
- **By date** - Newest or oldest duplicates
- **Cross-drive only** - Duplicates spanning multiple drives (for consolidation)

## Near Duplicates (Images)

### How They're Found

Near-duplicate detection uses **perceptual hashing** - a technique that creates a fingerprint based on what an image looks like, not its exact bytes.

The app uses multiple perceptual hash algorithms:
- **pHash (Perceptual Hash)** - Analyzes frequency patterns in the image
- **dHash (Difference Hash)** - Analyzes gradients between adjacent pixels
- **aHash (Average Hash)** - Compares brightness to the image average

By combining these, the app can detect images that are:
- **Resized** - Same image at different resolutions
- **Recompressed** - Same image saved with different JPEG quality
- **Format converted** - Same image as JPEG, PNG, HEIC, WebP, etc.
- **Slightly cropped** - Minor cropping around edges
- **Color adjusted** - Minor brightness/contrast tweaks

### Cross-Format Matching

The app matches duplicates across different image formats. If you have:
- `photo.jpg` (from camera)
- `photo.png` (exported from editor)
- `photo.HEIC` (from iPhone)

And they're visually the same image, they'll be grouped together as near-duplicates, even though they're different file formats with different byte contents.

### Similarity Threshold

The similarity threshold controls how similar images must be to count as duplicates. Adjust this in **Settings > Duplicate Detection > Similarity Threshold**.

| Threshold | Behavior |
|-----------|----------|
| **95-100%** | Very strict. Only catches obvious duplicates: exact resizes, recompression. Almost no false positives. |
| **90-95%** | Balanced. Catches most real duplicates including moderate edits. Recommended starting point. |
| **85-90%** | Permissive. Catches more duplicates but may group similar-but-different images. |
| **80-85%** | Aggressive. Will catch heavily edited versions but expect more false positives to review. |
| **Below 80%** | Not recommended. Too many unrelated images will be grouped together. |

**Tip:** Start at 90% and adjust based on results. If you're missing obvious duplicates, lower it. If you're seeing unrelated images grouped together, raise it.

### What Near-Duplicate Groups Look Like

```
Near Duplicates Found: 847 groups

[Group 1] IMG_4521.jpg - 92% similar (3 images)
  [x] \\NAS\Photos\2023\IMG_4521.jpg (4032x3024, 4.2 MB, JPEG)
  [ ] C:\Backup\IMG_4521.png (4032x3024, 12.1 MB, PNG)
  [ ] \\NAS\Archive\IMG_4521_small.jpg (1920x1440, 890 KB, JPEG)

  [Preview: side-by-side comparison of all 3 images]
  Suggested: Keep highest resolution (first one)
```

Each near-duplicate group shows:
- Similarity percentage
- Image dimensions, size, and format for each
- Side-by-side preview to verify they're really the same
- Suggestion for which to keep (highest resolution, best quality)

### What Near-Duplicates Won't Catch

Perceptual hashing has limits. It won't reliably detect:
- **Heavily cropped images** - Removing large portions changes the image too much
- **Images with text overlays** - Memes, watermarks, captions
- **Color-inverted or heavily filtered** - Major color changes
- **Rotated images** - 90/180/270 degree rotations (future enhancement)
- **Mirrored images** - Horizontally flipped (future enhancement)

These may need manual review or the AI-powered similarity features.

## Near Duplicates (Videos)

Video near-duplicate detection is not currently implemented. The UI includes a
setting for processing videos, but duplicate detection today focuses on
content hashes (exact matches) and perceptual hashing for images.

## The Duplicates Tab

### Main View

The Duplicates tab shows groups on the left and details on the right:

- **Filters:** Type, Status (Pending/Resolved/Ignored), Scope, and Drive
- **Select All / Select None:** Bulk-select visible groups
- **Group list:** One row per group with a selection checkbox

### Deciding Keepers

Use the **Strategy** section to mark keepers without deleting files:

- **Keep Newest**
- **Keep Oldest**
- **Keep Largest**
- **Keep Shortest Path**
- **Keep on Drive...** (requires a preferred drive selection)
- **Manual** (choose a keeper per group)

Use:
- **Preview** to estimate impact for the selected groups (or current view)
- **Set Keepers (Selected)** to apply the strategy to checked groups
- **Set Keepers (All Pending)** to apply to all pending groups in the current view

### Processing Files

Once keepers are selected, use the action buttons:

- **Quarantine** (recommended, recoverable)
- **Send to Trash**
- **Delete Permanently**

These actions remove non-keeper files from the selected groups.

## Libraries Used

### imagehash (Python)

The primary library for perceptual hashing:
- Implements pHash, dHash, aHash, and more
- Fast and well-tested
- Used by many duplicate detection tools

### Pillow (PIL)

Image loading and preprocessing:
- Opens images in all common formats
- Converts to standard format for hashing
- Handles EXIF orientation

### ffmpeg-python

Video frame extraction:
- Extracts frames at specified intervals
- Handles all common video formats
- Hardware acceleration when available

## Technical Details

### Perceptual Hash Storage

Perceptual hashes are stored as 64-bit integers, allowing fast comparison using Hamming distance (count of differing bits).

### Similarity Calculation

Similarity = 1 - (hamming_distance / hash_length)

For a 64-bit hash with 5 bits different:
Similarity = 1 - (5/64) = 92.2%

### Hash Comparison Performance

Comparing perceptual hashes is extremely fast (bitwise operations). The app can compare millions of image pairs per second.

The bottleneck is computing hashes initially, not comparing them.

### Group Formation

Duplicates are grouped using transitive clustering:
- If A matches B, and B matches C, then A, B, C are in the same group
- Even if A doesn't directly match C's threshold

This catches chains of similar images that have drifted over many edits.
