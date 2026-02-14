# Using the Folder Summarization UI

## Overview

You can now generate AI summaries for specific folders directly from the **Drives tab** in the DupliCleaner UI!

## Location

**Drives Tab** → Expand "**Generate Summaries for Folder**" section

## Step-by-Step Instructions

### 1. Navigate to Drives Tab

Open DupliCleaner and click on the **Drives** tab.

### 2. Expand "Generate Summaries for Folder"

Scroll down and click on the **"Generate Summaries for Folder"** collapsing header to expand it.

### 3. Select Folder

**Option A: Type the path**
- In the "Folder Path" field, type or paste the path to the folder you want to summarize
- Examples:
  - `C:\Users\clint\Photos\2024`
  - `C:\NAS\Photos\Summer Vacation`
  - `\\NAS\share\Documents\Work`

**Option B: Browse for folder**
- Click the **"Browse..."** button
- Navigate to and select the folder
- Click "OK"

### 4. Configure Settings

**Provider (Required)**
- **lmstudio** - Local LMStudio (recommended, free, private)
- **local** - Local Ollama
- **openai** - OpenAI GPT-4V (requires API key)
- **anthropic** - Claude 3 (requires API key)
- **google** - Gemini Pro Vision (requires API key)

**Model (Optional)**
- Leave empty to use the default model for your provider
- Or specify a specific model:
  - LMStudio: Model name from your loaded models
  - Ollama: `llava:13b`, `llava:7b`, etc.
  - OpenAI: `gpt-4-vision-preview`, etc.

**File Types (Optional)**
- Leave empty to process all supported files (images, documents, videos)
- Or specify extensions: `.jpg,.png,.pdf`
- Comma-separated, with or without dots

**Limit (Default: 500)**
- Maximum number of files to process
- Use smaller number for testing: `10` or `50`
- Increase for production: `1000` or more

### 5. Click "Generate Summaries"

- Button starts the process
- Progress bar appears showing:
  - Number of files found
  - Current file being processed
  - Success/failure counts

### 6. Monitor Progress

The progress section shows:
- **"Querying files..."** - Searching database for files
- **"Found X files to summarize"** - Files identified
- **"Processing 5/50: IMG_1234.jpg"** - Current progress
- **"Complete: 48 generated, 2 failed"** - Final results

### 7. View Results

Once complete:
- Summaries are stored in the database
- Search for content via the **Search tab**
- Example: Search for "beach sunset" to find photos with those elements

## Examples

### Example 1: Summarize Vacation Photos (LMStudio)

1. Make sure LMStudio is running with a vision model loaded
2. Go to Drives tab → "Generate Summaries for Folder"
3. **Folder Path**: `C:\Users\clint\Photos\2024 Vacation`
4. **Provider**: `lmstudio`
5. **Model**: (leave empty)
6. **File Types**: `.jpg,.png,.heic`
7. **Limit**: `100`
8. Click **"Generate Summaries"**

### Example 2: Summarize Work Documents (Claude)

1. Ensure Claude API key is stored in settings
2. Go to Drives tab → "Generate Summaries for Folder"
3. **Folder Path**: `C:\Documents\Work\Projects\2024`
4. **Provider**: `anthropic`
5. **Model**: (leave empty)
6. **File Types**: `.pdf,.docx,.txt`
7. **Limit**: `50`
8. Click **"Generate Summaries"**

### Example 3: Test with Small Batch

1. Go to Drives tab → "Generate Summaries for Folder"
2. **Folder Path**: `C:\Photos\Test`
3. **Provider**: `lmstudio`
4. **Limit**: `5`
5. Click **"Generate Summaries"**

## Requirements

### For LMStudio (Recommended)
- LMStudio application installed and running
- Vision-capable model loaded (e.g., `llava-1.5-7b-q4`)
- Server started on default port (localhost:1234)

### For Ollama
- Ollama service installed and running
- Vision model pulled: `ollama pull llava:13b`

### For Cloud Providers
- API keys stored in Settings tab under "AI Settings"
- Active internet connection
- Sufficient API credits

## Folder Selection Tips

**Works with any folder:**
- Folders within scanned drives ✅
- Folders outside scanned drives ✅
- Network shares ✅
- USB drives ✅

**BUT** - Files must be in the database:
- If the folder hasn't been scanned yet, run a scan first
- The feature only processes files that exist in the DupliCleaner database
- Unscanend files will be ignored

**Best practice:**
1. Scan the parent drive/folder first (Drives tab → Quick/Deep scan)
2. Then use "Generate Summaries" on specific subfolders

## Performance Tips

### Start Small
- Test with 5-10 files first (`Limit: 10`)
- Verify it works before processing hundreds

### Choose Right Provider
- **LMStudio**: Best for large batches, free, private
- **Cloud APIs**: Faster but costs money per image

### Filter File Types
- Only process what you need
- Images take longer than documents
- Videos require frame extraction (slowest)

### Batch Size
- Default 500 is good for overnight runs
- Use 50-100 for active monitoring
- Use 5-10 for testing

## Troubleshooting

### "No files found that need summaries"

**Cause**: No files in that folder, or all already have summaries

**Solutions**:
- Verify folder path is correct
- Check if folder has been scanned (Drives tab)
- Check if summaries already exist (Search tab)

### "Provider 'lmstudio' not available"

**Cause**: LMStudio not running or server not started

**Solutions**:
- Open LMStudio application
- Load a vision model
- Start the server (Local Server tab)
- Verify it's on localhost:1234

### "Provider 'openai' not available"

**Cause**: API key not configured

**Solutions**:
- Go to Settings tab
- Find "AI Settings" section
- Enter your OpenAI API key
- Click "Save Settings"

### Progress Stuck

**Cause**: Model processing large file or crashed

**Solutions**:
- Wait 2-3 minutes per file (normal for images)
- Check LMStudio console for errors
- Restart LMStudio if frozen
- Try smaller batch size
- Try different model

### Some Files Fail

**Normal**: 5-10% failure rate is acceptable
- Corrupted files
- Unsupported formats
- Very large files
- Model errors

**Not Normal**: >20% failure rate
- Check model compatibility
- Check file types match provider capabilities
- Check provider logs for errors

## What Gets Summarized

### Images
- Overall contents and setting
- Key points and notable elements
- People visible (characteristics, not names)

### Documents
- Overall contents and purpose
- Key points and main takeaways
- People or entities mentioned

### Videos
- Frame extraction and analysis
- Scene and content description
- Notable elements

## Where Summaries Are Stored

- **Database**: SQLite database in `~/.duplicleaner/`
- **Table**: `ai_summaries`
- **Searchable**: Via Search tab full-text search

## Next Steps After Summarization

1. **Search Your Content**
   - Go to Search tab
   - Try queries like "beach", "meeting notes", "family gathering"

2. **Filter and Organize**
   - Summaries help identify content types
   - Use search results to organize files

3. **Find Duplicates**
   - Similar summaries can indicate duplicate or near-duplicate content

4. **Review AI Accuracy**
   - Check a few summaries to verify quality
   - Adjust provider/model if needed

## Comparison: UI vs CLI

### Use UI When:
✅ You want visual feedback and progress
✅ You need to browse for folders
✅ You prefer point-and-click interface
✅ You're processing moderate amounts (<500 files)

### Use CLI When:
✅ You want to script/automate summarization
✅ You're processing large batches (>1000 files)
✅ You need to run headless/remote
✅ You're integrating with other tools

Both methods produce identical results!

## Tips for Best Results

### Model Selection
- **llava-1.5-7b**: Fast, good for general photos
- **llava-v1.6-vicuna-7b**: Better quality, slightly slower
- **llava-1.5-13b**: Best quality, requires more GPU memory

### Provider Selection
- **LMStudio**: Best for photos, free, unlimited
- **Claude**: Best for documents with text
- **GPT-4V**: Best for complex scenes and detailed descriptions

### File Type Selection
- Process similar file types together
- Images and documents have different requirements
- Mixed batches work but may be less efficient

## Feedback and Issues

If you encounter problems:
1. Check this guide's troubleshooting section
2. Check TESTING_PLAN.md for detailed test procedures
3. Check LMStudio/Ollama logs for error messages
4. Check DupliCleaner log files in status panel

Happy summarizing! 🚀
