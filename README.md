# DupliCleaner

**Intelligent duplicate detection, photo organization, and AI-powered media management for NAS and local storage.**

[![License: BSL 1.1](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://www.python.org/downloads/)
[![Windows 10+](https://img.shields.io/badge/Windows-10+-0078D6.svg)](https://www.microsoft.com/windows)
[![Build Status](https://img.shields.io/badge/Build-Passing-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/Coverage-0%25-red.svg)]()

---

<p align="center">
  <strong>Developed by <a href="https://xrmech.com">XRMech Solutions LLC</a></strong><br>
  Clinton Campbell | 2026
</p>

---

## Overview

DupliCleaner is a powerful desktop application that helps you reclaim storage space and organize your digital life. Whether you have years of photos dumped from phones, multiple backup drives with overlapping content, or a NAS filled with duplicates, DupliCleaner provides the tools to clean up intelligently.

### Key Features

- **Smart Duplicate Detection** - Find exact duplicates via content hashing, plus near-duplicates using perceptual image hashing
- **AI-Powered Face Recognition** - Identify people across your photo collection, even tracking children as they grow up
- **Intelligent Photo Organization** - Automatically sort photos by date, location, and events using EXIF metadata
- **Multi-Drive Management** - Scan across NAS, external drives, and local storage with redundancy verification
- **Semantic Search** - Find photos by describing them: "sunset at the beach" or "birthday party with cake"
- **Document Version Tracking** - Git-based versioning eliminates the need for file_v1, file_v2, file_final copies
- **Safe Operations** - Quarantine mode, undo support, and detailed audit logs protect your data

## Screenshots

<!-- TODO: Add screenshots after UI is built -->

| Duplicates View | Face Recognition | Photo Organization |
|-----------------|------------------|-------------------|
| ![Duplicates](docs/screenshots/duplicates.png) | ![Faces](docs/screenshots/faces.png) | ![Organize](docs/screenshots/organize.png) |

| Semantic Search | Drive Management | Settings |
|-----------------|------------------|----------|
| ![Search](docs/screenshots/search.png) | ![Drives](docs/screenshots/drives.png) | ![Settings](docs/screenshots/settings.png) |

## Features in Detail

### Duplicate Detection

| Type | Method | Accuracy |
|------|--------|----------|
| Exact Duplicates | SHA-256 content hashing | 100% |
| Similar Images | Perceptual hashing (pHash, dHash) | Configurable threshold |
| Cross-Format | JPEG/PNG/HEIC matched as same image | Automatic |
| Videos | Frame sampling + perceptual hashing | High accuracy |

### AI Capabilities

- **Face Detection & Recognition** using InsightFace (ArcFace model)
- **Age Progression Tracking** - Follow people from baby photos to adulthood
- **Scene Classification** using CLIP - Beach, mountain, party, wedding, etc.
- **Object Detection** using YOLOv8 - Find photos containing specific objects
- **Quality Scoring** - Automatically identify the sharpest, best-exposed photos
- **OCR** - Extract text from screenshots and document photos

### Photo Organization

- Sort by **date** (YYYY/MM or YYYY/MM/DD folder structures)
- Sort by **location** using GPS metadata with reverse geocoding
- Cluster by **events** (photos taken within time windows)
- **Smart renaming** from IMG_0001.jpg to 2024-03-15_NYC_001.jpg
- Automatic **screenshot detection** and separation
- **Burst photo** and **Live Photo** handling

### Safety First

- **Never auto-deletes** - All removals require confirmation
- **Quarantine mode** - Move files to review folder instead of deleting
- **Complete audit log** - Every action is recorded and reversible
- **Dry run mode** - Preview all changes before executing

## Installation

### Requirements

- Windows 10 or later
- Python 3.11+ (if installing from source)
- NVIDIA GPU recommended for AI features (CPU fallback available)

### Download Installer

Download the latest installer from the [Releases](https://github.com/xrmech/duplicleaner/releases) page.

### Install from Source

```bash
# Clone the repository
git clone https://github.com/xrmech/duplicleaner.git
cd duplicleaner

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install AI dependencies (optional, for face/scene recognition)
pip install -r requirements-ai.txt

# GPU setup (optional)
# 1) Check CUDA version
nvidia-smi
# 2) Install CUDA-enabled PyTorch (example for CUDA 12.1)
pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu121
# 3) Install ONNX Runtime GPU (for InsightFace GPU)
pip install onnxruntime-gpu

# Run the application
python -m duplicleaner
```

## Quick Start

1. **Launch DupliCleaner** - The setup wizard guides you through initial configuration
2. **Add your storage locations** - Local drives, external drives, or network shares (UNC paths)
3. **Run a scan** - The app indexes your files and computes hashes
4. **Review duplicates** - See grouped duplicates with smart recommendations
5. **Take action** - Keep the best copies, quarantine or delete the rest

## Architecture

DupliCleaner is built with a modular architecture for maintainability and extensibility:

```
+------------------------------------------------------------------+
|                     Dear PyGui UI (GPU-accelerated)               |
+------------------------------------------------------------------+
|  Drives | Duplicates | Organize | Faces | Search | Settings      |
+------------------------------------------------------------------+
                              |
+------------------------------------------------------------------+
|                        Core Engine                                |
|  Scanner | Hasher | Comparator | Resolver | Organizer | Actions  |
+------------------------------------------------------------------+
                              |
+------------------------------------------------------------------+
|                     AI/ML Layer (Optional)                        |
|  InsightFace | CLIP | YOLOv8 | EasyOCR | Quality Scoring         |
+------------------------------------------------------------------+
                              |
+------------------------------------------------------------------+
|                      Data Layer                                   |
|  SQLite Database | File System | Git (Version Tracking)          |
+------------------------------------------------------------------+
```

### Technology Stack

| Component | Technology |
|-----------|------------|
| UI Framework | Dear PyGui (GPU-accelerated) |
| Database | SQLite |
| Face Recognition | InsightFace (ArcFace) |
| Scene/Search | OpenAI CLIP |
| Object Detection | YOLOv8 (Ultralytics) |
| OCR | EasyOCR |
| Version Tracking | Git (via GitPython) |
| Installer | Windows MSI with auto-update |

## Documentation

Comprehensive documentation is available in the [docs/](docs/) folder:

- [File Scanner](docs/01-scanner.md) - Scanning, network paths, ignore patterns
- [File Hashing](docs/02-hasher.md) - Hash algorithms, performance, caching
- [Duplicate Detection](docs/03-duplicate-detection.md) - Exact and near-duplicate finding
- [Drive Management](docs/04-drive-manager.md) - Multi-drive support, redundancy
- [Photo Organization](docs/05-photo-organization.md) - Date/location sorting, renaming
- [Face Recognition](docs/06-face-recognition.md) - Detection, clustering, age tracking
- [AI Content Analysis](docs/07-ai-content-analysis.md) - Scenes, objects, quality, OCR
- [Duplicate Resolution](docs/08-duplicate-resolution.md) - Keep strategies, auto-select
- [File Operations](docs/09-file-operations.md) - Delete, quarantine, undo
- [Database](docs/10-database.md) - Storage, backup, export
- [User Interface](docs/11-user-interface.md) - UI guide, shortcuts
- [Document Versioning](docs/12-document-versioning.md) - Git-based version tracking

## Development

### Project Structure

```
duplicleaner/
├── src/
│   └── duplicleaner/
│       ├── core/          # Scanner, hasher, comparator, etc.
│       ├── ai/            # Face recognition, CLIP, YOLO
│       ├── db/            # Database models and migrations
│       ├── ui/            # Dear PyGui interface
│       └── utils/         # Helpers, config, logging
├── tests/                 # Unit and integration tests
├── docs/                  # Documentation
└── resources/             # Icons, assets
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=duplicleaner --cov-report=html

# Run specific test file
pytest tests/test_hasher.py -v
```

### Code Quality

```bash
# Type checking
mypy src/

# Linting
ruff check src/

# Format code
black src/
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Ways to Contribute

- Report bugs and request features via [Issues](https://github.com/xrmech/duplicleaner/issues)
- Submit pull requests for bug fixes or new features
- Improve documentation
- Share feedback and suggestions

## Roadmap

### v1.0 (Current Development)
- [x] Project architecture and documentation
- [ ] Core scanning and hashing
- [ ] Duplicate detection (exact + near)
- [ ] Basic UI with Dear PyGui
- [ ] Photo organization
- [ ] Face recognition
- [ ] AI content analysis
- [ ] Document versioning

### Future Plans
- [ ] Cloud backup verification (Google Drive, OneDrive, etc.)
- [ ] Mobile companion app for reviewing duplicates
- [ ] Plugin system for custom analyzers
- [ ] Linux and macOS support

## License

This project is licensed under the **Business Source License 1.1** (BSL 1.1).

- **Free for non-production use**: Development, testing, personal use, and evaluation
- **Commercial use requires a license**: Contact [XRMech Solutions LLC](https://xrmech.com) for commercial licensing
- **Converts to MIT on January 1, 2030**: After this date, the code becomes fully open source

See the [LICENSE](LICENSE) file for full details.

## About XRMech Solutions

**[XRMech Solutions LLC](https://xrmech.com)** provides software development and consulting services specializing in:

- Custom desktop and web applications
- AI/ML integration and computer vision
- Data management and automation solutions
- Technical consulting and architecture design

**Contact:** Visit [xrmech.com](https://xrmech.com) for inquiries.

---

<p align="center">
  Made with care by <a href="https://xrmech.com">XRMech Solutions LLC</a>
</p>
