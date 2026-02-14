# AI File Summarization Guide

This guide explains how to use DupliCleaner's AI summarization feature to generate intelligent summaries of your files (images, documents, videos) using local or cloud LLMs.

## Features

The summarization system generates rich summaries that include:

1. **Overall contents and setting** - What the file contains
2. **Key points** - Important elements or main takeaways
3. **People mentions** - Any people visible (in images) or mentioned (in documents)

Summaries are stored in the database and are searchable via full-text search.

## Supported Providers

- **local** (Ollama) - Default, requires Ollama running locally
- **lmstudio** - LMStudio with vision models (NEW)
- **openai** - OpenAI GPT-4V (requires API key)
- **anthropic** - Claude 3 (requires API key)
- **google** - Gemini Pro Vision (requires API key)

## Setup Instructions

### Option 1: LMStudio (Recommended for Local Use)

1. **Download and install LMStudio**
   - Get it from: https://lmstudio.ai/
   - Install and launch the application

2. **Download a vision-capable model**
   - In LMStudio, go to the "Search" tab
   - Search for and download one of these models:
     - `llava-1.5-7b-q4` (smaller, faster, 4GB VRAM)
     - `llava-v1.6-vicuna-7b-q4` (improved quality)
     - `bakllava-1-7b-q4` (good balance)
     - `llava-1.5-13b-q4` (larger, better quality, 8GB VRAM)

3. **Load the model and start the server**
   - In LMStudio, go to "Local Server" tab
   - Select your downloaded vision model from the dropdown
   - Click "Start Server"
   - Server will start on `http://localhost:1234` by default

4. **Configure DupliCleaner**
   - Edit your config or set via UI settings:
     ```
     summary_provider: lmstudio
     summary_model_lmstudio: ""  (leave empty to use currently loaded model)
     lmstudio_base_url: http://localhost:1234/v1
     ```

### Option 2: Ollama (Alternative Local)

1. **Install Ollama**
   - Download from: https://ollama.ai/
   - Install and start the service

2. **Pull a vision model**
   ```bash
   ollama pull llava:13b
   ```

3. **Configure DupliCleaner**
   ```
   summary_provider: local
   summary_model_local: llava:13b
   ```

### Option 3: Cloud Providers (OpenAI/Anthropic/Google)

1. **Get API keys**
   - OpenAI: https://platform.openai.com/api-keys
   - Anthropic: https://console.anthropic.com/
   - Google: https://makersuite.google.com/app/apikey

2. **Store API keys securely**
   ```bash
   # Via Python
   from duplicleaner.utils.keystore import get_keystore, AIProvider
   keystore = get_keystore()
   keystore.store_key(AIProvider.OPENAI, "your-api-key-here")
   ```

3. **Configure provider**
   ```
   summary_provider: openai  # or anthropic, google
   ```

## Running Summarization

### Basic Usage

Generate summaries for all files in a directory:

```bash
python -m duplicleaner summarize --directory "C:\Users\clint\Photos\2024"
```

### Specify Provider

Use LMStudio (recommended):

```bash
python -m duplicleaner summarize --directory "C:\Users\clint\Photos\2024" --provider lmstudio
```

Use Ollama:

```bash
python -m duplicleaner summarize --directory "C:\Users\clint\Photos\2024" --provider local
```

Use OpenAI:

```bash
python -m duplicleaner summarize --directory "C:\Users\clint\Photos\2024" --provider openai
```

### Specify Model

Override the default model:

```bash
python -m duplicleaner summarize --directory "C:\Users\clint\Photos" --provider lmstudio --model "llava-v1.6-vicuna-7b"
```

### Filter by File Types

Only process specific file types:

```bash
# Only images
python -m duplicleaner summarize --directory "C:\Photos" --file-types ".jpg,.png,.heic"

# Only documents
python -m duplicleaner summarize --directory "C:\Documents" --file-types ".pdf,.docx,.txt"

# Mixed
python -m duplicleaner summarize --directory "C:\Files" --file-types ".jpg,.pdf,.mp4"
```

### Limit Batch Size

Process only a limited number of files:

```bash
python -m duplicleaner summarize --directory "C:\Photos" --limit 100
```

## Complete Examples

### Example 1: Summarize vacation photos with LMStudio

```bash
# 1. Start LMStudio with llava model loaded
# 2. Run summarization
python -m duplicleaner summarize \
  --directory "C:\Users\clint\Photos\2024 Vacation" \
  --provider lmstudio \
  --limit 500
```

### Example 2: Summarize scanned documents with Claude

```bash
python -m duplicleaner summarize \
  --directory "C:\Users\clint\Documents\Scanned" \
  --provider anthropic \
  --file-types ".pdf,.jpg" \
  --limit 200
```

### Example 3: Summarize a subfolder within a scanned directory

```bash
# First scan the parent directory
python -m duplicleaner --scan "C:\NAS\Photos"

# Then summarize a specific subfolder
python -m duplicleaner summarize \
  --directory "C:\NAS\Photos\Family\2024" \
  --provider lmstudio
```

## Output Format

The command will show progress and results:

```
Found 150 files to summarize using lmstudio provider
Using model: llava-1.5-7b-q4
[1/150] Processing: IMG_1234.jpg - Success
[2/150] Processing: IMG_1235.jpg - Success
[3/150] Processing: vacation.pdf - Success
...
[150/150] Processing: notes.txt - Success

Summary generation complete!
  Generated: 148
  Failed: 2
  Total: 150
```

## Searching Summaries

Once summaries are generated, you can search them:

```bash
# Search for specific content
python -m duplicleaner search "beach sunset"
python -m duplicleaner search "meeting notes John"
python -m duplicleaner search "family gathering"
```

## Summary Database Schema

Summaries are stored in the `ai_summaries` table with these fields:

- `summary` - Main natural language description
- `summary_model` - Model used (e.g., "llava:13b", "gpt-4-vision-preview")
- `people_mentioned` - JSON array of people names
- `activities` - JSON array of detected activities
- `mood_atmosphere` - Emotional tone
- `time_of_day` - Temporal context
- `season_weather` - Environmental context
- `document_type` - For documents
- `document_summary` - For documents
- `key_entities` - JSON object with extracted entities
- `generated_at` - Timestamp
- `user_edited` - Boolean flag for manual edits

## Performance Tips

1. **Use LMStudio for best performance**
   - No API costs
   - Privacy (runs locally)
   - Good quality with llava models

2. **Adjust batch size**
   - Use `--limit` to process in smaller batches
   - Monitor GPU/CPU usage

3. **Filter by file type**
   - Only process files you need summarized
   - Images require vision models, documents can use text-only models

4. **Model selection**
   - Smaller models (7B) are faster but less detailed
   - Larger models (13B+) are slower but more accurate

## Troubleshooting

### "Summary provider not available"

- **LMStudio**: Ensure server is started and model is loaded
- **Ollama**: Ensure ollama service is running (`ollama serve`)
- **Cloud providers**: Check API keys are stored correctly

### "LMStudio summary failed"

- Verify server is running on the correct port
- Check that a vision-capable model is loaded
- Try a different model

### "No files found that need summaries"

- Files may already have summaries
- Check that files exist in the specified directory
- Verify file types match supported extensions

### Slow performance

- Use a smaller model (7B instead of 13B)
- Reduce batch size with `--limit`
- For images, ensure they're not too large (they're automatically resized to 2048px)

## Integration with Full Analysis

Summaries can also be generated as part of full AI analysis:

```bash
python -m duplicleaner analyze --summaries --all
```

This will:
1. Extract metadata (EXIF)
2. Detect scenes
3. Detect objects
4. Run OCR
5. Generate summaries

## Privacy and Security

- **Local providers (LMStudio/Ollama)**: Files never leave your machine
- **Cloud providers**: Files are sent to external APIs
- **API keys**: Stored securely using Windows Credential Manager
- **Summaries**: Stored locally in SQLite database

## Configuration File

Edit `C:\Users\clint\.duplicleaner\config.toml` to set defaults:

```toml
[ai]
summary_enabled = true
summary_provider = "lmstudio"
summary_model_lmstudio = ""
lmstudio_base_url = "http://localhost:1234/v1"
summary_model_local = "llava:13b"
summary_max_tokens = 500
summary_temperature = 0.7
```

## Next Steps

1. Set up your preferred LLM provider (LMStudio recommended)
2. Scan your directories with DupliCleaner
3. Run summarization on specific folders
4. Search and explore your summaries via the UI or CLI

For questions or issues, refer to the main README or open an issue on GitHub.
