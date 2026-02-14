# Advanced Content Summarization Guide

This guide explains DupliCleaner's advanced content summarization system that intelligently processes different file types using the optimal AI models.

## Overview

The new `ContentSummarizer` provides:

1. **Intelligent file type routing** - Automatically detects file types and routes to appropriate processing
2. **Batch processing by type** - Groups files and processes them together (all text, then all images, etc.)
3. **Efficient model management** - Minimizes model loading/unloading to save time
4. **Wide format support** - Text, images, PDFs, Office docs, videos, audio (with optional dependencies)

## Supported File Types

### Text Files (Fast Processing with Text Model)
- **Plain text**: `.txt`, `.md`, `.rst`, `.log`
- **Code**: `.py`, `.js`, `.java`, `.cpp`, `.c`, `.h`, `.cs`, `.go`, `.rs`, `.php`
- **Config**: `.json`, `.xml`, `.yaml`, `.yml`, `.toml`, `.ini`, `.conf`, `.cfg`
- **Web**: `.html`, `.css`, `.sql`
- **Scripts**: `.sh`, `.bat`, `.ps1`
- **Data**: `.csv`, `.tsv`
- **Email**: `.eml`, `.msg`

### Image Files (Vision Model)
- **Photos**: `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp`
- **Advanced**: `.tiff`, `.tif`, `.heic`, `.heif`
- **Graphics**: `.ico`, `.svg`

### Visual Documents (Text Extraction -> Text Model OR Render -> Vision Model)
- **PDF**: `.pdf` (tries text extraction first, falls back to image rendering if scanned)
- **Microsoft Office**: `.docx`, `.doc`, `.xlsx`, `.xls`, `.pptx`, `.ppt`
- **LibreOffice**: `.odt`, `.ods`, `.odp`

### Video Files (Keyframe Extraction -> Vision Model) *
- `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`, `.flv`, `.wmv`, `.m4v`
- `.mpeg`, `.mpg`, `.3gp`

*Requires optional video dependencies

### Audio Files (Whisper Transcription -> Text Model) *
- `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma`, `.opus`

*Requires optional audio dependencies

### Skipped File Types
These are intentionally skipped as they're not useful to summarize:
- Binaries: `.exe`, `.dll`, `.so`, `.dylib`
- Archives: `.zip`, `.rar`, `.7z`, `.tar`, `.gz`
- Databases: `.db`, `.sqlite`, `.mdb`
- Disk images: `.iso`, `.dmg`, `.img`
- Temp files: `.tmp`, `.cache`, `.lock`

## Setup Requirements

### Core Dependencies (Required)

Install the enhanced requirements:

```bash
pip install -r requirements.txt
```

This includes:
- `pymupdf` - Fast PDF text extraction
- `python-docx` - Word document reading
- `openpyxl` - Excel spreadsheet reading
- `python-pptx` - PowerPoint reading
- `python-magic` - File type detection

### Recommended LMStudio Models

You'll need TWO models for optimal performance:

#### 1. Text Model: Llama-3.2-3B-Instruct (Q4_K_M)
- **Download**: Search in LMStudio for `hugging-quants/Llama-3.2-3B-Instruct-Q4_K_M-GGUF`
- **Size**: ~2GB VRAM
- **Use**: Text files, extracted document text
- **Speed**: Very fast (~50-80 tokens/sec on RTX 3060)

#### 2. Vision Model: Qwen2.5-VL-7B (Q4_K_M)
- **Download**: Search in LMStudio for `Qwen2.5-VL-7B` (Q4_K_M quantization)
- **Size**: ~4.5GB VRAM
- **Use**: Images, scanned PDFs, visual documents
- **Speed**: Fast (~40-50 tokens/sec on RTX 3060)

**Total VRAM**: ~6.5GB (both models can fit in 12GB VRAM simultaneously if needed)

### Optional Dependencies

For video and audio processing (optional features):

```bash
# Video keyframe extraction (OpenCV is already in requirements.txt)
pip install opencv-python-headless

# Audio transcription (large install, includes PyTorch)
pip install faster-whisper
# Or use reference Whisper:
pip install openai-whisper torch
```

## How to Use

### Basic Usage

Process an entire directory with intelligent routing:

```bash
python -m duplicleaner summarize --directory "C:\NAS\Documents" --provider lmstudio
```

The system will:
1. Scan the directory and classify all files
2. Group files by type (text, images, PDFs, etc.)
3. Process each group in order, minimizing model switching

### Filter by File Type

Only process specific file types:

```bash
# Only images
python -m duplicleaner summarize --directory "C:\Photos" --file-types ".jpg,.png,.heic"

# Only documents
python -m duplicleaner summarize --directory "C:\Documents" --file-types ".pdf,.docx,.txt"

# Mixed content
python -m duplicleaner summarize --directory "C:\ProjectFiles" --file-types ".py,.md,.jpg,.pdf"
```

### Limit Processing

Process only first N files (useful for testing):

```bash
python -m duplicleaner summarize --directory "C:\NAS" --limit 100
```

## Processing Order

The system processes files in this optimal order to minimize model switching:

1. **Text files** (load text model once)
   - `.txt`, `.md`, `.py`, `.json`, etc.
   - Fast processing: ~50-100 files/minute

2. **Images** (load vision model once)
   - `.jpg`, `.png`, `.heic`, etc.
   - Medium speed: ~20-40 files/minute

3. **Visual documents** (use vision model already loaded)
   - Text-based PDFs -> extract text -> switch to text model
   - Scanned PDFs -> render to images -> use vision model
   - Office docs -> extract text -> text model

4. **Videos** (use vision model)
   - Extract keyframes -> vision model

5. **Audio** (switch to text model)
   - Transcribe -> text model

## Model Management

### Manual Model Switching in LMStudio

Since LMStudio doesn't support programmatic model switching yet, you'll need to:

**For mixed content directories:**
1. Load the **vision model** (Qwen2.5-VL-7B) first
2. Start the summarization
3. The system will process: text → images → docs → videos
4. When it reaches text files, manually switch to **text model** in LMStudio
5. The system will wait for you to switch and continue

**For single-type directories:**
- **Photos folder**: Just load vision model, no switching needed
- **Documents folder**: Load text model for PDFs/Office, vision model for scanned docs
- **Code repository**: Just load text model

### Future: Automatic Model Switching

A future update will add automatic model switching via LMStudio's API when they support it.

## Output Format

The system provides detailed progress tracking:

```
Starting batch summarization for directory: C:\Documents
File type breakdown: text=45, image=23, visual_doc=12, video=0, audio=0, skip=5

Processing 45 text files
Ensure text model is loaded in LMStudio (e.g., Llama-3.2-3B-Instruct)
[1/45] C:\Documents\notes.txt - Success
[2/45] C:\Documents\readme.md - Success
...

Processing 23 image files
Ensure vision model is loaded in LMStudio (e.g., Qwen2.5-VL-7B)
[46/80] C:\Documents\diagram.png - Success
[47/80] C:\Documents\photo.jpg - Success
...

Processing 12 visual_doc files
[69/80] C:\Documents\report.pdf - Success (text extraction)
[70/80] C:\Documents\scanned.pdf - Success (image rendering)
[71/80] C:\Documents\proposal.docx - Success
...

Summary generation complete!
  Successful: 78
  Failed: 2
  Skipped: 5
  Total: 85
```

## Examples

### Example 1: Mixed NAS Directory

```bash
# Process entire NAS folder with photos, docs, and code
python -m duplicleaner summarize \
  --directory "C:\NAS\ProjectAlpha" \
  --provider lmstudio
```

**Expected**: Text files (code, README) -> Images (screenshots) -> PDFs (documentation)

### Example 2: Photo Collection Only

```bash
# Only images, no model switching needed
python -m duplicleaner summarize \
  --directory "C:\Photos\2024Vacation" \
  --provider lmstudio \
  --file-types ".jpg,.png,.heic"
```

**Setup**: Load Qwen2.5-VL-7B, start processing, done!

### Example 3: Document Archive

```bash
# Mix of text PDFs, scanned PDFs, and Office docs
python -m duplicleaner summarize \
  --directory "C:\Documents\Archive" \
  --provider lmstudio \
  --file-types ".pdf,.docx,.xlsx"
```

**Expected**: System will try text extraction first, fall back to vision model for scanned docs

### Example 4: Code Repository

```bash
# Just code and markdown files
python -m duplicleaner summarize \
  --directory "C:\Projects\MyApp" \
  --provider lmstudio \
  --file-types ".py,.js,.md,.json"
```

**Setup**: Load Llama-3.2-3B-Instruct, process all files with text model

## Performance Tips

### 1. Group Similar Content

Process directories with similar file types together:
- Photos folder → vision model only
- Code repository → text model only
- Documents folder → mixed, requires switching

### 2. Use File Type Filters

Narrow down processing to specific types:

```bash
# Process only the files you need
--file-types ".jpg,.png"   # Images only
--file-types ".txt,.md"    # Text only
--file-types ".pdf"        # PDFs only
```

### 3. Test Small Batches First

Use `--limit` to test on a small subset:

```bash
python -m duplicleaner summarize --directory "C:\NAS" --limit 20
```

### 4. Monitor VRAM Usage

- Text model: ~2GB VRAM
- Vision model: ~4.5GB VRAM
- Both can fit in 12GB VRAM if needed

### 5. Adjust Context Length

For very long documents, the text model may need more context:
- Default: 512 tokens output
- Increase in LMStudio settings if summaries are truncated

## Searching Summaries

Once generated, search across all summaries:

```bash
# Search by content
python -m duplicleaner search "budget proposal"
python -m duplicleaner search "family vacation photos"
python -m duplicleaner search "API documentation"

# Search specific file types
python -m duplicleaner search "meeting notes" --type document
python -m duplicleaner search "sunset beach" --type image
```

## Troubleshooting

### "No files found that need summaries"

**Cause**: All files already have summaries, or no files match filter

**Solution**:
- Check files exist in database (run scan first)
- Remove `--file-types` filter to process all files
- Delete existing summaries if you want to regenerate

### "LMStudio summary failed"

**Cause**: Model not loaded, wrong model type, or server not running

**Solution**:
1. Check LMStudio server is running (green indicator)
2. Verify correct model is loaded:
   - Text files need text model (Llama 3.2 3B)
   - Images need vision model (Qwen2.5-VL)
3. Check server URL in config: `http://localhost:1234/v1`

### "PDF text extraction failed, converting to images"

**Cause**: PDF is scanned/image-based, not text-based

**Solution**: This is normal! System automatically falls back to vision model. Make sure vision model is loaded in LMStudio.

### "python-docx not installed"

**Cause**: Missing optional dependencies

**Solution**:
```bash
pip install python-docx openpyxl python-pptx pymupdf
```

### Slow performance

**Cause**: Large files, wrong model, or hitting VRAM limits

**Solutions**:
- Use Q4 quantization (not Q8 or FP16)
- Reduce batch size with `--limit`
- For text files, use 3B model (not 7B+)
- For images, resize large images before processing

## Future Enhancements

The following features are planned:

### Video Summarization Improvements
- More adaptive keyframe sampling
- Scene boundary detection for better summaries

### Audio Transcription Improvements
- Store transcript snippets alongside summary

### Automatic Model Switching
- Detect which model is currently loaded
- Send model switch commands to LMStudio
- Eliminate manual switching between batches

### Parallel Processing
- Process multiple files simultaneously
- Utilize full GPU capacity
- Batch inference for higher throughput

## Integration with Existing Features

Summaries integrate with other DupliCleaner features:

### Face Detection
```bash
# Find photos with summaries mentioning specific people
python -m duplicleaner search "Emma and Dad" --type image
```

### Duplicate Detection
- Summaries help identify content duplicates (same content, different filenames)
- Semantic search finds similar images even without exact matches

### Organization
- Use summaries to intelligently sort files
- Group by content theme (work, personal, vacation)
- Auto-tag based on summary content

## Privacy and Security

- **Local models (LMStudio)**: All processing happens on your machine, no data sent externally
- **Cloud models**: Files are sent to external APIs if using OpenAI/Anthropic/Google
- **Summaries**: Stored locally in SQLite database
- **API keys**: Stored securely using Windows Credential Manager

## Configuration

Edit `C:\Users\clint\.duplicleaner\config.toml`:

```toml
[ai]
summary_enabled = true
summary_provider = "lmstudio"
lmstudio_base_url = "http://localhost:1234/v1"
summary_model_lmstudio = ""  # Empty = use currently loaded model
summary_max_tokens = 500
summary_temperature = 0.7

# File type filters
analysis_doc_extensions = [".pdf", ".docx", ".doc", ".xlsx", ".pptx"]
analysis_data_extensions = [".csv", ".json", ".xml"]
```

## Next Steps

1. Install dependencies: `pip install -r requirements.txt`
2. Download both models in LMStudio (text + vision)
3. Start with a small test directory: `--limit 20`
4. Scale up to full NAS directories
5. Search and explore your summarized content

For questions or issues, see the main README or open a GitHub issue.
