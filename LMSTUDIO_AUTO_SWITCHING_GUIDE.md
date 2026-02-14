# LMStudio Automatic Model Detection & Switching Guide

DupliCleaner now integrates with your **LMStudioMonitorService** for intelligent model management!

## Overview

Your existing **LMStudioMonitorService** (running on `http://localhost:5000`) enables DupliCleaner to:
1. **Detect** which model is currently loaded in LMStudio
2. **Verify** the correct model type is loaded (text vs vision)
3. **Guide you** when the wrong model is loaded
4. **Optionally switch** models automatically (future feature)

## Requirements

### 1. LMStudioMonitorService Must Be Running

Check if it's running:
```bash
# Test the health endpoint
curl http://localhost:5000/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "lmStudioRunning": true,
  "modelName": "Josiefied-DeepSeek-R1-Qwen3-8B-abliterated",
  "timestamp": "2026-02-09T12:34:56Z"
}
```

If not running:
- Start the LMStudioMonitorService (Windows Service or manual exe)
- Located at: `C:\Users\clint\GeneralizedServiceChatbot\LMStudioMonitorService`

### 2. LMStudio Running with Model Loaded

Ensure:
- LMStudio is open
- A model is loaded and server is started
- Server running on `http://localhost:1234` (default)

## How It Works

### Automatic Model Detection

When you run batch summarization with `--batch` flag:

1. **DupliCleaner connects** to LMStudioMonitorService
2. **Queries current model** via `/api/health` endpoint
3. **Detects model type** (text or vision) based on model name
4. **Compares** with required model type for current processing phase

### Intelligent Guidance

When processing different file types:

#### Scenario 1: Correct Model Already Loaded ✅
```
Current model in LMStudio: Josiefied-DeepSeek-R1-Qwen3-8B-abliterated (text)
Processing 45 text files
Correct model type already loaded
[Processing continues...]
```

#### Scenario 2: Wrong Model Loaded ⚠️
```
Current model in LMStudio: Qwen2.5-VL-7B (vision)
Processing 45 text files
Wrong model type loaded! Current: vision, Required: text

============================================================
PLEASE SWITCH MODEL IN LMSTUDIO:
For text processing, load a text model such as:
  - Josiefied-DeepSeek-R1-Qwen3-8B-abliterated (recommended)
  - Llama-3.2-3B-Instruct
  - Qwen2.5-3B-Instruct
============================================================
Waiting 10 seconds for model switch...

Model switched successfully: Josiefied-DeepSeek-R1-Qwen3-8B-abliterated
[Processing continues...]
```

#### Scenario 3: No Model Loaded ❌
```
No model loaded in LMStudio!
For text processing, load a text model such as:
  - Josiefied-DeepSeek-R1-Qwen3-8B-abliterated (recommended)
  - Llama-3.2-3B-Instruct
  - Qwen2.5-3B-Instruct
```

## Usage Examples

### Example 1: Epstein Files (Text Only)

**Recommended Model**: Josiefied-DeepSeek-R1-Qwen3-8B-abliterated

```bash
# 1. Load text model in LMStudio
# 2. Start server
# 3. Run batch summarization
python -m duplicleaner summarize \
  --directory "C:\EpsteinFiles" \
  --provider lmstudio \
  --batch \
  --file-types ".pdf,.txt,.doc,.docx"
```

**What happens:**
- DupliCleaner detects your text model is loaded ✅
- Processes all documents without interruption
- No model switching needed

### Example 2: Mixed Content (Photos + Documents)

**Required Models**:
- Text: Josiefied-DeepSeek-R1-Qwen3-8B-abliterated
- Vision: Qwen2.5-VL-7B

```bash
# Load TEXT model first in LMStudio
python -m duplicleaner summarize \
  --directory "C:\NAS\ProjectFolder" \
  --provider lmstudio \
  --batch
```

**What happens:**

**Phase 1: Text Files**
```
Current model: Josiefied-DeepSeek-R1-Qwen3-8B-abliterated (text) ✅
Processing 45 text files
[Processing automatically...]
```

**Phase 2: Image Files**
```
Wrong model type loaded! Current: text, Required: vision ⚠️

============================================================
PLEASE SWITCH MODEL IN LMSTUDIO:
For image processing, load a vision model such as:
  - Qwen2.5-VL-7B (recommended)
  - LLaVA-v1.6-7B
============================================================
Waiting 10 seconds for model switch...
```

**You manually switch to Qwen2.5-VL-7B in LMStudio**

```
Model switched successfully: Qwen2.5-VL-7B ✅
Processing 23 image files
[Processing automatically...]
```

### Example 3: Photos Only (No Switching)

**Recommended Model**: Qwen2.5-VL-7B

```bash
# Load vision model in LMStudio
python -m duplicleaner summarize \
  --directory "C:\Photos\2024Vacation" \
  --provider lmstudio \
  --batch \
  --file-types ".jpg,.png,.heic"
```

**What happens:**
- DupliCleaner detects vision model is loaded ✅
- Processes all images
- No switching needed

## Model Detection Rules

DupliCleaner automatically detects model types by name:

### Vision Models (Keywords)
- `vl`, `vision`, `llava`, `qwen2.5-vl`, `qwen-vl`
- **Examples**:
  - `Qwen2.5-VL-7B` → Vision ✅
  - `LLaVA-v1.6-7B` → Vision ✅

### Text Models (Keywords)
- `instruct`, `chat`, `text`, `llama`, `qwen`, `mistral`, `dolphin`
- **Examples**:
  - `Josiefied-DeepSeek-R1-Qwen3-8B-abliterated` → Text ✅
  - `Llama-3.2-3B-Instruct` → Text ✅
  - `Dolphin-Mistral-7B` → Text ✅

### Unknown Models
If a model name doesn't match any keywords, you'll see:
```
Could not determine model type for: custom-model-v1
```

In this case, manually verify it's the correct type for your task.

## Manual Model Switching

When prompted to switch models:

1. **In LMStudio**:
   - Stop the current model (if running)
   - Click "Load Model"
   - Select the recommended model
   - Click "Start Server"

2. **Wait for model to load** (~10-30 seconds)

3. **DupliCleaner will automatically detect** the new model and continue

## API Endpoints Reference

Your LMStudioMonitorService provides these endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Health check + current model info |
| `/LMStudioApi/model` | GET | Get detailed model info |
| `/LMStudioApi/model` | POST | Load a different model |
| `/LMStudioApi/restart` | POST | Restart LMStudio |
| `/LMStudioApi/models` | GET | List available models |

## Future: Fully Automatic Switching

**Coming soon**: DupliCleaner will automatically switch models without manual intervention.

The infrastructure is ready - the `LMStudioManager` class can:
- Call `/LMStudioApi/model` with model path
- Wait for model to load
- Verify model is ready
- Resume processing

This requires:
1. Model path configuration (mapping model names to file paths)
2. User approval for automatic switching (security consideration)
3. Handling model loading timeouts gracefully

## Troubleshooting

### "LMStudioMonitorService not available - model detection disabled"

**Cause**: Monitor service is not running or not accessible

**Solution**:
1. Start LMStudioMonitorService:
   ```bash
   cd C:\Users\clint\GeneralizedServiceChatbot\LMStudioMonitorService
   # Run as Windows Service or directly
   ```
2. Verify it's running:
   ```bash
   curl http://localhost:5000/api/health
   ```

### "Could not determine model type"

**Cause**: Model name doesn't match known patterns

**Solution**:
- If it's a text model, ensure name contains: `instruct`, `chat`, `llama`, etc.
- If it's a vision model, ensure name contains: `vl`, `vision`, `llava`, etc.
- Manually verify you've loaded the correct model type for your task

### "Wrong model type loaded! ... Waiting 10 seconds for model switch..."

**Cause**: Wrong model type is loaded for the current processing phase

**Solution**:
1. **Manually switch** to the recommended model in LMStudio within 10 seconds
2. If you miss the window, the system will still attempt to process (may fail)
3. Stop and restart with correct model loaded

### Model switching takes too long

**Cause**: Large models (13B+) take 30-60 seconds to load

**Solution**:
- Use smaller models (7B or 8B) for faster switching
- Pre-plan your workflow to minimize switches
- Process files in separate runs (text-only, then images-only)

## Best Practices

### 1. Pre-Load the Right Model

Before running batch summarization:
- **Text-heavy directories**: Load text model first
- **Image directories**: Load vision model first
- **Mixed content**: Load text model first (it's usually the larger group)

### 2. Use File Type Filters

Narrow down to one model type at a time:
```bash
# Text only (no switching needed)
--file-types ".pdf,.txt,.docx"

# Images only (no switching needed)
--file-types ".jpg,.png,.heic"
```

### 3. Monitor Service Health

Before starting large jobs:
```bash
curl http://localhost:5000/api/health
```

Verify:
- Service is running
- LMStudio is running
- Model is loaded

### 4. Process in Batches

For very large directories (3M+ files):
```bash
--limit 1000  # Process 1000 at a time
```

This allows you to:
- Monitor progress
- Adjust models between batches
- Stop/resume without losing work

## Configuration

Add to your `~/.duplicleaner/config.toml`:

```toml
[ai]
summary_provider = "lmstudio"
lmstudio_base_url = "http://localhost:1234/v1"
lmstudio_monitor_url = "http://localhost:5000"  # New setting

# Optional: Disable model detection if Monitor Service unavailable
lmstudio_auto_detect = true  # Default: true
```

## Summary

With LMStudioMonitorService integration:

✅ **Automatic model detection** - knows what's loaded
✅ **Intelligent guidance** - tells you when to switch
✅ **10-second grace period** - time to switch models
✅ **Clear recommendations** - suggests specific models
✅ **Seamless processing** - continues automatically after switch

**No more guessing** which model is loaded or manually tracking which phase needs which model!

## Next Steps

1. Verify LMStudioMonitorService is running
2. Try a small mixed-content directory with `--batch --limit 20`
3. Watch the automatic detection in action
4. Scale up to your full NAS directories

For automatic model switching (coming soon), see the `LMStudioManager` class in `src/duplicleaner/utils/lmstudio_manager.py`.
