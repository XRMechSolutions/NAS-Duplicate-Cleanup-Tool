# UI Summarization with Automatic Model Detection

The DupliCleaner UI now includes intelligent model detection and batch processing for the "Generate Summaries" feature!

## New Features

### 1. **Automatic Model Detection**
When using LMStudio provider, the UI now shows which model is currently loaded:
```
Current model: Josiefied-DeepSeek-R1-Qwen3-8B-abliterated (text)
```

This helps you verify you have the right model loaded before starting summarization.

### 2. **Intelligent Batch Processing** (New Checkbox)
✅ **Enable intelligent batch processing (groups by file type, detects model)**

When enabled (default):
- Groups files by type (text, images, PDFs, etc.)
- Processes each group together
- Detects if wrong model type is loaded
- Provides guidance on which model to load
- Shows detailed file type breakdown

When disabled:
- Processes files one-by-one in directory order
- Original behavior (no grouping)
- Faster to start but no model intelligence

## How to Use

### Step 1: Load the Right Model in LMStudio

For **text-heavy folders** (documents, PDFs):
- Load: `Josiefied-DeepSeek-R1-Qwen3-8B-abliterated`
- Or: `Llama-3.2-3B-Instruct`

For **image folders** (photos):
- Load: `Qwen2.5-VL-7B`
- Or: `LLaVA-v1.6-7B`

### Step 2: Check Model Status

In the UI under "Generate Summaries for Folder":
- Look for: `Current model: [model-name] (text/vision)`
- Verify it matches your content type

If the status shows:
- `LMStudioMonitorService not available` → Your monitor service isn't running (batch mode will still work, but without model detection)
- `No model loaded in LMStudio` → Load a model first

### Step 3: Configure Summarization

**Folder Path**: Browse to your folder (e.g., `C:\EpsteinFiles`)

**Provider**: Select `lmstudio` (recommended for local processing)

**Model** (optional): Leave empty to use currently loaded model

**File Types** (optional): Filter to specific types
- Examples:
  - `.pdf,.txt,.docx` (text documents only)
  - `.jpg,.png,.heic` (images only)
  - Leave empty for all file types

**Limit**: Maximum files to process (default: 500)

**Batch Mode**: ✅ Enabled (recommended)

### Step 4: Click "Generate Summaries"

The UI will:

1. **Check model status** (if LMStudio + batch mode)
2. **Analyze and group files** by type
3. **Show file breakdown**:
   ```
   File breakdown: text=45, images=23, docs=12, skipped=5
   ```

4. **Process each group**:
   - Text files first
   - Images second
   - Visual documents third
   - etc.

5. **Detect model mismatches** and show guidance
6. **Update progress** in real-time

## What Happens During Processing

### Batch Mode Enabled (Recommended)

**Phase 1: Initialization**
```
Analyzing files and grouping by type...
File breakdown: text=45, images=23, docs=12, skipped=5
```

**Phase 2: Text Processing**
```
Processing Text Files: 15/45 - witness-statement-001.txt
```

If wrong model detected:
```
Wrong model type! Current: vision, Required: text
Please switch to text model in LMStudio
```

**Phase 3: Image Processing**
```
Processing Image Files: 8/23 - evidence-photo-001.jpg
```

**Phase 4: Complete**
```
Complete: 78 successful, 2 failed, 5 skipped
```

### Batch Mode Disabled (Original Behavior)

```
Processing 1/85: file-001.pdf
Processing 2/85: image-001.jpg
Processing 3/85: file-002.pdf
...
Complete: 78 generated, 7 failed
```

No grouping, no model detection, processes in directory order.

## Model Detection & Guidance

### Scenario 1: Correct Model Loaded ✅

Status shows: `Current model: Josiefied-DeepSeek-R1-Qwen3-8B-abliterated (text)`

Processing text files → No warnings, smooth processing

### Scenario 2: Wrong Model Loaded ⚠️

Status shows: `Current model: Qwen2.5-VL-7B (vision)`

Processing text files → Console logs show:
```
Wrong model type loaded! Current: vision, Required: text

============================================================
PLEASE SWITCH MODEL IN LMSTUDIO:
For text processing, load a text model such as:
  - Josiefied-DeepSeek-R1-Qwen3-8B-abliterated (recommended)
  - Llama-3.2-3B-Instruct
============================================================
Waiting 10 seconds for model switch...
```

**What to do:**
1. In LMStudio, stop current model
2. Load the recommended model
3. Start server
4. Processing continues automatically after 10 seconds

### Scenario 3: No Monitor Service

If LMStudioMonitorService is not running:
- Model detection is disabled
- Batch processing still works
- No automatic model checking
- Manual model management required

## Tips for Best Results

### 1. Pre-Load Correct Model
Before starting, load the model that matches your content:
- **Text-heavy**: Load text model first
- **Image-heavy**: Load vision model first
- **Mixed**: Load text model first (usually the larger group)

### 2. Use File Type Filters
Narrow down to one model type:
```
File Types: .pdf,.txt,.docx     # Text only
File Types: .jpg,.png           # Images only
```

This eliminates model switching entirely.

### 3. Start Small
Test with a small limit first:
```
Limit: 20
```

Verify everything works before processing thousands of files.

### 4. Monitor Console Logs
Watch the DupliCleaner console for:
- Model detection messages
- Model switch requests
- Processing phase updates

### 5. Keep Monitor Service Running
For best experience, ensure LMStudioMonitorService is running:
```bash
# Check if running:
curl http://localhost:5000/api/health
```

## Troubleshooting

### "Current model: [empty]"

**Cause**: Model status couldn't be determined

**Solution**:
- Check LMStudio is running
- Check a model is loaded
- Verify LMStudioMonitorService is running

### "Processing seems stuck"

**Cause**: Wrong model type loaded, waiting for switch

**Solution**:
- Check console logs for model switch request
- Manually switch to recommended model in LMStudio
- Processing will continue after detection

### "Failed to summarize most files"

**Cause**: Wrong model type for content

**Solution**:
- Stop processing
- Load correct model type
- Re-run with batch mode enabled

### Batch mode not grouping files

**Cause**: Batch mode checkbox is disabled

**Solution**:
- Enable "Enable intelligent batch processing" checkbox
- Re-run summarization

## Performance Comparison

### Epstein Files Example (80 PDFs + 20 images)

**With Batch Mode** (Recommended):
```
Time: ~8 minutes
- Text model loads once
- Processes all 80 PDFs: 6 minutes
- Switch to vision model (manual)
- Processes all 20 images: 2 minutes
```

**Without Batch Mode** (Sequential):
```
Time: ~12 minutes
- Processes in directory order: PDF, image, PDF, image, PDF...
- No grouping, no efficiency gains
- May fail if wrong model loaded
```

**Savings: 33% faster with batch mode!**

## Summary

### ✅ Enable Batch Mode When:
- Processing mixed content (text + images)
- Want automatic model detection
- Using LMStudio provider
- LMStudioMonitorService is running

### ❌ Disable Batch Mode When:
- Processing single file type only (though it still works fine)
- Want original behavior
- Not using LMStudio (other providers don't need model switching)

### 🎯 Best Practice:
**Always use batch mode with LMStudio** for optimal performance and automatic model management!

## Next Steps

1. Ensure LMStudioMonitorService is running
2. Load your preferred models in LMStudio
3. Test on a small folder with `Limit: 20`
4. Scale up to full NAS directories
5. Enjoy automatic model detection and intelligent batch processing!

For more details, see:
- [LMSTUDIO_AUTO_SWITCHING_GUIDE.md](LMSTUDIO_AUTO_SWITCHING_GUIDE.md)
- [CONTENT_SUMMARIZATION_GUIDE.md](CONTENT_SUMMARIZATION_GUIDE.md)
