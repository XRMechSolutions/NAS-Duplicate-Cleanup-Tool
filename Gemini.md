# Gemini.md

This file provides guidance to Gemini when working with code in this repository.

## Project Overview

**DupliCleaner** (package: `duplicleaner`)

Copyright 2026 XRMech Solutions LLC | Author: Clinton Campbell | License: BSL 1.1

A Python application for identifying and removing duplicate files from NAS storage. The tool scans directories, identifies exact and near-duplicates using multiple comparison methods (size, date, hash, content analysis), and provides intelligent deduplication options through a UI. Also includes image organization features for sorting phone dumps and unorganized photo collections.

## Critical Rules

1. **Documentation must match implementation** - When code changes deviate from the plan or documentation, update the relevant docs immediately. Never leave documentation out of sync with reality.

## Technology Stack

- **UI**: Dear PyGui (GPU-accelerated desktop application)
- **Database**: SQLite with full persistence
- **AI Acceleration**: NVIDIA CUDA
- **AI Models**: Downloaded on first use

## Architecture

### Core Components

- **Scanner**: Recursive file system walker that indexes files with metadata (size, dates, path)
- **Hasher**: Computes file hashes (xxHash for speed, SHA-256 for verification); chunked reading for large files
- **Comparator**: Handles near-duplicate detection for images/videos using perceptual hashing (pHash, dHash)
- **Database**: SQLite storage for scan results, duplicate groups, and processing state
- **Resolver**: Logic for selecting which duplicates to keep (newest, oldest, shortest path, user-defined rules)
- **Organizer**: Image/video organization using EXIF metadata and content analysis
- **AI Analyzer**: Face detection/recognition and scene classification using ML models
- **DriveManager**: Multi-drive coordination, redundancy checking, backup verification
- **ActionEngine**: Safe file operations with quarantine, trash, hard delete options + audit log
- **VersionTracker**: Git-based document version tracking with delta compression
- **UI**: Dear PyGui desktop interface for browsing duplicates and making decisions

### Image Organization Features

- **Date-based sorting**: Extract EXIF DateTimeOriginal to organize into YYYY/MM/DD or YYYY/MM folder structures
- **Location grouping**: Use GPS coordinates from EXIF to group photos by location (reverse geocoding to city/country)
- **Event clustering**: Group photos taken within configurable time windows (e.g., 2 hours apart = same event)
- **Smart renaming**: Rename files from IMG_XXXX.jpg to descriptive names like 2024-03-15_NYC_001.jpg
- **Screenshot detection**: Identify and separate screenshots based on dimensions and metadata
- **Burst detection**: Identify burst photos and suggest keeping only the best one
- **Video thumbnail matching**: Find videos that match photos (Live Photos, etc.)

### AI-Powered Analysis

- **Face detection**: Locate faces in images, store face embeddings in database
- **Face clustering**: Group unknown faces by similarity, allowing user to assign names
- **Face recognition**: Once faces are labeled, automatically tag new photos with recognized people
- **Pet detection and tracking**: Identify dogs, cats, and other pets; track them through time like people
- **Scene classification**: Categorize images (beach, mountain, city, indoor, food, pet, document, etc.)
- **Object detection**: Identify key objects in photos (car, dog, cake, Christmas tree, etc.)
- **Activity/event inference**: Combine scene + objects + date to suggest events (birthday, wedding, vacation)
- **Quality scoring**: Rate image quality (blur, exposure, composition) to help select best from duplicates
- **OCR for documents**: Extract text from document photos and screenshots for searchability
- **AI Summaries**: Rich natural language descriptions of photos ("Emma and Dad at beach with Max the dog")
- **Smart Tagging**: Auto-generated searchable tags from multiple sources (AI, EXIF, faces, pets)

### Age-Progression Face Recognition

Tracking children from baby to adult is challenging - faces change dramatically. Strategy:

- **Temporal bridging**: Link faces incrementally through time rather than matching baby→adult directly
  - Chain: Baby(0-1) → Toddler(2-4) → Child(5-9) → Preteen(10-12) → Teen(13-17) → Adult
  - Use photo dates to order faces chronologically within a person's cluster
- **Age-invariant models**: Use models with better cross-age performance
  - InsightFace/ArcFace (buffalo_l model) - trained on age-diverse datasets
  - AdaFace - handles quality/age variations well
- **Lower thresholds for temporal neighbors**: Accept lower similarity when photos are close in time
- **Multi-embedding storage**: Store multiple face embeddings per person at different ages
- **User-assisted linking**: Present uncertain cross-age matches for user confirmation
- **Age estimation**: Estimate apparent age to help group faces into life stages

### Pet Tracking Through Time

Similar challenges exist for pets - a puppy looks very different from an adult dog. Strategy:

- **Pet detection**: Use YOLO to detect dogs, cats, birds, and other animals
- **Species/breed classification**: Identify breed to narrow down matches
- **Visual embeddings**: Store visual features for each detected pet
- **Color analysis**: Coat color and markings help distinguish similar pets
- **Life stage tracking**: Puppy/Kitten → Young → Adult → Senior
- **Temporal bridging**: Same approach as humans - link through incremental time steps
- **Multi-signal matching**: Combine embeddings, color, breed, and temporal proximity

### AI Summaries and Search

Rich natural language descriptions enable powerful search:

- **Local models**: LLaVA runs on your GPU for free, private summaries
- **Cloud APIs**: Optional GPT-4V, Claude, or Gemini with your own API keys
- **Secure key storage**: API keys encrypted with Windows DPAPI/keyring, never transmitted
- **Full-text search**: FTS5 indexes for instant searching across summaries and OCR text
- **Smart tagging**: Auto-tags from scene detection, objects, faces, pets, and AI summaries

### Data Flow

1. Scan phase: Walk directories, collect file metadata, store in SQLite
2. Hash phase: Compute hashes for files of matching sizes (optimization: only hash potential duplicates)
3. Group phase: Cluster exact duplicates by hash, near-duplicates by perceptual similarity
4. Review phase: Present groups in UI with recommendations
5. Action phase: Delete, move to trash, or create hard/symbolic links

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python -m nas_dedup

# Run with specific scan path
python -m nas_dedup --scan "/path/to/nas"

# Organize photos by date
python -m nas_dedup organize --by-date --format "YYYY/MM"

# Organize with full features (date + location + events)
python -m nas_dedup organize --by-date --by-location --detect-events

# Run AI analysis on images
python -m nas_dedup analyze --faces --scenes

# Train face recognition on labeled photos
python -m nas_dedup faces train --input labeled_faces/

# Search photos by content
python -m nas_dedup search "beach sunset"

# Run tests
pytest tests/

# Run single test file
pytest tests/test_hasher.py -v

# Type checking
mypy src/

# Linting
ruff check src/
```

## Key Libraries

### Core
- **dearpygui**: GPU-accelerated desktop UI framework
- **imagehash**: Perceptual hashing for image near-duplicates
- **pillow**: Image processing and EXIF extraction
- **exifread**: Robust EXIF metadata parsing (fallback for Pillow edge cases)
- **ffmpeg-python**: Video frame extraction for video comparison
- **sqlite3**: Built-in database for scan results
- **xxhash**: Fast hashing for large files
-- **geopy**: Reverse geocoding for GPS coordinates to location names
- **python-dateutil**: Flexible date parsing for various EXIF date formats
- **gitpython**: Git integration for document version tracking with delta compression
- **keyring**: Secure API key storage using Windows DPAPI/system keychain

### AI/ML (optional, for advanced features)
- **insightface**: Primary face recognition (ArcFace/buffalo_l model, best cross-age performance)
- **adaface-pytorch**: Alternative model with strong age/quality robustness
- **face_recognition**: Simpler face detection and recognition (wraps dlib)
- **deepface**: Multi-backend face analysis, includes age/gender estimation
- **transformers**: Hugging Face models for CLIP, scene classification
- **torch**: PyTorch backend for running ML models
- **onnxruntime**: Efficient model inference (InsightFace uses ONNX)
- **open-clip-torch**: OpenAI CLIP for semantic image search and classification
- **ultralytics**: YOLOv8 for fast object detection
- **easyocr** or **pytesseract**: OCR for document/screenshot text extraction
- **scikit-learn**: Face embedding clustering, quality scoring models

## Design Decisions

### Multi-Drive Strategy
- Consolidate duplicates across drives while verifying backup redundancy
- Track which files exist on which drives
- Flag "at-risk" files that exist on only one drive
- Support all delete modes: quarantine folder, system trash, hard delete with audit log

### Performance & Safety
- Use content hashing only after size-matching to minimize I/O
- Store scan state in SQLite to allow resumable scans
- Near-duplicate threshold configurable (default 90% similarity)
- Never auto-delete; always require user confirmation
- Support dry-run mode for all destructive operations
- Log all deletions/moves to a separate undo/audit log
- Prefer EXIF DateTimeOriginal over file system dates (more reliable for photos)
- Fall back to file modified date when EXIF unavailable
- Cache reverse geocoding results to avoid API rate limits
- Organization operations copy by default; move only with explicit flag
- Preserve original files in "unsorted" folder when metadata is missing
- AI features are optional; core dedup works without ML dependencies
- Face embeddings stored locally in SQLite (no cloud API required)
- CLIP model runs locally for privacy; no images sent to external services
- GPU acceleration used when available, graceful fallback to CPU
- AI analysis results cached to avoid reprocessing unchanged images
- Face clusters require user confirmation before assigning names
- Batch processing for AI to maximize GPU utilization
