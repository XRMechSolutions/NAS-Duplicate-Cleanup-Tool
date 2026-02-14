# Batch Summarization Examples

Quick reference for using the new `--batch` mode for intelligent content summarization.

## Basic Usage

### Standard Mode (One file at a time)
```bash
python -m duplicleaner summarize --directory "C:\Photos" --provider lmstudio
```

### Batch Mode (Groups by file type)
```bash
python -m duplicleaner summarize --directory "C:\Photos" --provider lmstudio --batch
```

## Why Use Batch Mode?

**Batch mode** groups files by type and processes them together, which:
- Minimizes model loading/unloading
- Provides better progress visibility
- Handles mixed content intelligently (text, images, PDFs, etc.)
- Automatically routes files to optimal processing method

## Example Scenarios

### 1. Photo Collection (Images Only)

```bash
# Single model (vision), no switching needed
python -m duplicleaner summarize \
  --directory "C:\Photos\2024Vacation" \
  --provider lmstudio \
  --batch \
  --file-types ".jpg,.png,.heic"
```

**Setup**: Load Qwen2.5-VL-7B in LMStudio, start processing

**Output**:
```
Starting intelligent batch summarization for: C:\Photos\2024Vacation
Provider: lmstudio
------------------------------------------------------------
File type breakdown: text=0, image=150, visual_doc=0, video=0, audio=0, skip=0

Processing 150 image files
Ensure vision model is loaded in LMStudio (e.g., Qwen2.5-VL-7B)
[1/150] C:\Photos\2024Vacation\IMG_001.jpg - Success
...

Batch Summarization Complete!
  Image files:     150
  Successful:      148
  Failed:          2
```

### 2. Mixed NAS Directory (Text + Images + PDFs)

```bash
# Multiple file types - requires model switching
python -m duplicleaner summarize \
  --directory "C:\NAS\ProjectAlpha" \
  --provider lmstudio \
  --batch \
  --limit 200
```

**Setup**:
1. Load Llama-3.2-3B-Instruct (text model)
2. Start processing
3. When "Processing image files" appears, switch to Qwen2.5-VL-7B (vision model)

**Output**:
```
File type breakdown: text=45, image=23, visual_doc=12, video=0, audio=0, skip=8

Processing 45 text files
Ensure text model is loaded in LMStudio (e.g., Llama-3.2-3B-Instruct)
[1/88] readme.md - Success
[2/88] notes.txt - Success
...

Processing 23 image files
Ensure vision model is loaded in LMStudio (e.g., Qwen2.5-VL-7B)
[46/88] screenshot.png - Success
...

Processing 12 visual_doc files
[69/88] report.pdf - Success (text extraction)
[70/88] invoice.pdf - Success (image rendering)
```

### 3. Document Archive (PDFs + Office Docs)

```bash
# Mostly text extraction, some scanned docs
python -m duplicleaner summarize \
  --directory "C:\Documents\Archive" \
  --provider lmstudio \
  --batch \
  --file-types ".pdf,.docx,.xlsx"
```

**Setup**: Load Llama-3.2-3B-Instruct (text model) for text-based PDFs, Qwen2.5-VL-7B for scanned PDFs

**Automatic behavior**:
- Text-based PDFs → extract text → text model
- Scanned PDFs → convert to images → vision model (requires manual switch)
- Office docs → extract text → text model

### 4. Code Repository (Text Only)

```bash
# Pure text, one model throughout
python -m duplicleaner summarize \
  --directory "C:\Projects\MyApp" \
  --provider lmstudio \
  --batch \
  --file-types ".py,.js,.md,.json,.yaml"
```

**Setup**: Load Llama-3.2-3B-Instruct, no switching needed

### 5. Testing on Small Subset

```bash
# Test with only 20 files first
python -m duplicleaner summarize \
  --directory "C:\NAS\Large" \
  --provider lmstudio \
  --batch \
  --limit 20
```

## Comparison: Standard vs Batch Mode

### Standard Mode
```bash
python -m duplicleaner summarize --directory "C:\Mixed" --provider lmstudio
```

**Behavior**:
- Processes files in directory order (IMG_001.jpg, notes.txt, report.pdf, IMG_002.jpg...)
- No grouping, no optimization
- User must manually ensure correct model is loaded for each file
- Slower overall due to context about file types

### Batch Mode
```bash
python -m duplicleaner summarize --directory "C:\Mixed" --provider lmstudio --batch
```

**Behavior**:
- Groups files by type first
- Processes all text files, then all images, then all PDFs
- Clear prompts when to switch models
- Faster overall, better progress tracking
- Automatic fallback strategies (e.g., PDF text extraction → image rendering)

## Model Recommendations

### For Text Files
**Model**: Llama-3.2-3B-Instruct (Q4_K_M)
- Size: ~2GB VRAM
- Speed: Very fast (~50-80 tokens/sec)
- Download: `hugging-quants/Llama-3.2-3B-Instruct-Q4_K_M-GGUF`

### For Images/Visual Content
**Model**: Qwen2.5-VL-7B (Q4_K_M)
- Size: ~4.5GB VRAM
- Speed: Fast (~40-50 tokens/sec)
- Download: Search "Qwen2.5-VL-7B" in LMStudio

## Tips

1. **Use batch mode for mixed directories** - It will group files intelligently
2. **Use standard mode for single-type directories** - Less overhead if all files are same type
3. **Filter by file type** with `--file-types` to narrow processing
4. **Test with `--limit 20`** before processing large directories
5. **Watch for model switch prompts** - Manual switching required until LMStudio supports API switching

## Expected Performance

**RTX 3060 12GB**:

| File Type | Model | Speed | Notes |
|-----------|-------|-------|-------|
| Text files | Llama 3.2 3B | 50-80 tokens/sec | Very fast |
| Images | Qwen2.5-VL 7B | 40-50 tokens/sec | Fast |
| Text PDFs | Llama 3.2 3B | 50-80 tokens/sec | After extraction |
| Scanned PDFs | Qwen2.5-VL 7B | 40-50 tokens/sec | Per page |
| Office docs | Llama 3.2 3B | 50-80 tokens/sec | After extraction |

**Time estimates**:
- 100 text files: ~2-3 minutes
- 100 images: ~3-5 minutes
- 100 mixed files: ~5-8 minutes (includes model switching)

## Troubleshooting

### "Ensure X model is loaded in LMStudio"

This is a reminder to manually switch models. Load the requested model in LMStudio and the processing will continue automatically.

### "PDF text extraction failed, converting to images"

Normal for scanned PDFs. Make sure vision model is loaded for these files.

### "Failed to process X files"

Check LMStudio logs for errors. Common causes:
- Wrong model type (text model for images, or vice versa)
- Out of VRAM (use lower quantization)
- Server not responding (restart LMStudio)

## Next Steps

1. Try batch mode on a small test directory
2. Compare speed vs standard mode
3. Process your full NAS directories
4. Search summaries with `python -m duplicleaner search "query"`
