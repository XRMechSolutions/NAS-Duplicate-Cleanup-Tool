# Video Near-Duplicate Detection

## Goal

Extend DupliCleaner's duplicate detection pipeline to identify near-duplicate videos using perceptual hashing of extracted frames. Users with large video collections (phone recordings, screen captures, re-encoded copies) need to find videos that are visually similar even when file hashes differ due to re-encoding, trimming, or resolution changes.

## Current Capabilities

- **Video frame extraction** - OpenCV-based keyframe extraction at configurable intervals (content_summarizer.py)
- **Video summarization** - Frames sent to vision models for AI descriptions
- **Video file detection** - Recognizes 11 video formats (.mp4, .avi, .mov, .mkv, .webm, .flv, .wmv, .m4v, .mpeg, .mpg, .3gp)
- **Image near-duplicate detection** - Perceptual hashing (pHash, dHash) pipeline in comparator.py works for images
- **Config fields exist** - `process_videos: bool` and `video_frame_interval: int` defined but unused for duplicate detection
- **UI checkbox exists** - Labeled "Process videos for near-duplicates (not implemented yet)" in app.py

## What Needs to Be Built

### Phase 1: Basic Video Fingerprinting

- Extract N keyframes per video (reuse existing frame extraction logic)
- Compute perceptual hashes (pHash) for each extracted frame
- Store frame hashes in database linked to the source video
- Compare videos by matching their frame hash sets

### Phase 2: Similarity Scoring

- Define similarity metric: percentage of matching frame hashes between two videos
- Handle different lengths: a 30-second clip inside a 5-minute video should still match
- Configurable similarity threshold (default 70-80% frame match)
- Handle re-encoded copies: same content at different resolutions/bitrates

### Phase 3: Clustering and UI

- Group similar videos into duplicate clusters
- Display video duplicate groups in the Duplicates tab
- Show video thumbnails and metadata (duration, resolution, codec, bitrate) for comparison
- Allow users to preview and compare videos side-by-side

### Phase 4: Advanced Matching

- Temporal alignment: detect when videos share a common subsequence
- Audio fingerprinting (optional): use audio similarity as an additional signal
- Live Photo matching: correlate short videos with burst photos by timestamp proximity
- Handle trimmed/cropped versions of the same video

## Technical Approach

### Frame Hash Comparison

```
Video A: [hash1, hash2, hash3, hash4, hash5]
Video B: [hash1, hash2, hash3, hash6, hash7]

Match: 3/5 frames = 60% similarity
```

### Optimization

- Only compare videos of similar duration (within 2x ratio) to reduce comparisons
- Use file size as a pre-filter (similar to image dedup pipeline)
- Cache extracted frame hashes to avoid re-extraction
- Batch GPU processing for perceptual hash computation

### Database Schema

- `video_frames` table: video_file_id, frame_index, timestamp_sec, phash, dhash
- Extend `duplicate_groups` to support video group type

## Integration Points

- Wire up existing UI checkbox to trigger video comparison
- Reuse `comparator.py` pattern: size filter -> hash -> perceptual compare -> cluster
- Store results in same duplicate_groups table with a video type flag
- Frame extraction shared with content_summarizer's existing logic

## Dependencies

- OpenCV (already used)
- imagehash (already used for images)
- ffmpeg-python (already in requirements for video metadata)
