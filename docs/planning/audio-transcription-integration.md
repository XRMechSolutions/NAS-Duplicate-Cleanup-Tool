# Audio Transcription Integration

## Goal

Fully integrate the existing audio transcription backend into the DupliCleaner UI and workflow. The transcription engine (Whisper/faster-whisper) is implemented and functional in the batch processing pipeline, but UI controls need to be connected and the feature needs to be surfaced as a first-class capability alongside image and document analysis.

## Current Capabilities (Fully Implemented in Backend)

- **Dual-backend transcription** - faster-whisper (preferred) with openai-whisper fallback
- **Audio file detection** - Recognizes 8 formats: .mp3, .wav, .m4a, .flac, .ogg, .aac, .wma, .opus
- **Configurable Whisper settings** - Model size (tiny/base/small/medium/large), device (cpu/cuda), compute type (int8/float16/float32)
- **Transcription-to-summary pipeline** - Audio transcribed to text, then summarized by LLM
- **Model caching** - Whisper model loaded once and reused across files
- **Batch processing** - Audio files processed alongside text files in content summarizer
- **Database storage** - Transcriptions stored as AISummary with document_type="audio"
- **CLI access** - Works via `python -m duplicleaner summarize` command

## Reference Implementation: Habla

The **Habla** project (`C:\Users\clint\HablaTranslate\habla`) is a sibling project that implements real-time bidirectional Spanish-English speech translation. Its audio pipeline is more advanced and serves as a reference for improving DupliCleaner's transcription:

### Habla's Audio Pipeline

```
Audio Input → ffmpeg decoder → Silero VAD (speech segmentation)
  → WhisperX ASR (word-level timestamps)
  → Pyannote diarization (speaker identification)
  → LLM post-processing (error correction using conversational context)
```

### Key Patterns to Adopt

| Habla Feature | What It Does | DupliCleaner Benefit |
|---|---|---|
| **WhisperX** (not just faster-whisper) | Word-level timestamp alignment | Click-to-seek in transcripts, subtitle export |
| **Silero VAD** | Detects speech vs silence, segments audio | Skip silence in long recordings, faster processing |
| **Pyannote 3.1 diarization** | Labels speakers (A, B, C...) on CPU | Multi-speaker meeting/interview transcription |
| **LLM post-processing** | Fixes ASR errors using context | Better accuracy via existing LLM integration |
| **ffmpeg subprocess decoding** | Handles any audio format reliably | Broad format support without library issues |
| **Two-tier transcription** | Partial (streaming) + final (polished) | Show rough progress during long files |

### Habla Architecture Notes

- **Silero VAD** runs on CPU (~2MB model), parameters: 0.35 speech threshold, 600ms silence duration, 400ms min speech, 30s max segment
- **WhisperX** wraps faster-whisper but adds alignment for word-level timestamps
- **Pyannote** runs on CPU (zero GPU impact), requires HuggingFace token for model access
- **LLM correction** uses conversation context (last 10 exchanges + topic summary) to fix ASR errors
- **VRAM budget**: Habla runs WhisperX small + Ollama qwen3:4b in ~5GB on RTX 3060 12GB

### Habla Source File Reference

Reference these files when implementing. They contain proven, working patterns for each pipeline stage.

| Component | File | Key Classes/Functions |
|---|---|---|
| **VAD + Audio Decoder** | `C:\Users\clint\HablaTranslate\habla\server\pipeline\vad_buffer.py` (~306 lines) | `StreamingVADBuffer` (feed_pcm, flush, reset), `AudioDecoder` (ffmpeg subprocess, decode_chunk, decode_blob), `VADConfig` (all tuning parameters) |
| **Pipeline Orchestrator** | `C:\Users\clint\HablaTranslate\habla\server\pipeline\orchestrator.py` (~720 lines) | `PipelineOrchestrator` (startup, process_audio, process_text), `_run_quick_asr()` (fast partial), `_run_asr_and_diarize()` (WhisperX + Pyannote full pipeline) |
| **LLM Translation/Correction** | `C:\Users\clint\HablaTranslate\habla\server\pipeline\translator.py` (~544 lines) | `Translator` (translate, switch_provider), `_call_ollama()`, `_call_lmstudio()`, `_call_openai()` with retry/fallback logic |
| **LLM Prompt Templates** | `C:\Users\clint\HablaTranslate\habla\server\models\prompts.py` (~107 lines) | `get_translator_system_prompt()`, `build_translator_user_prompt()` (context window with last 10 exchanges + topic summary) |
| **Speaker Tracking** | `C:\Users\clint\HablaTranslate\habla\server\services\speaker_tracker.py` (~72 lines) | `SpeakerTracker` (get_or_create, rename, set_role_hint, get_display_name) - simple speaker profile management |
| **Configuration** | `C:\Users\clint\HablaTranslate\habla\server\config.py` (~145 lines) | `ASRConfig`, `TranslatorConfig`, `DiarizationConfig`, `AudioConfig` - environment-driven config with validation |
| **Database Schema** | `C:\Users\clint\HablaTranslate\habla\server\db\database.py` (~162 lines) | Tables: sessions, speakers, exchanges, vocab, idiom_patterns, vocab_fts (FTS5). Async SQLite with WAL mode |
| **Data Models** | `C:\Users\clint\HablaTranslate\habla\server\models\schemas.py` (~138 lines) | Pydantic models: SpeakerProfile, TranslationResult, Exchange, VocabItem, WebSocket message types |
| **Dependencies** | `C:\Users\clint\HablaTranslate\habla\requirements.txt` (~28 lines) | Core deps: whisperx, faster-whisper, silero-vad, httpx, aiosqlite, pydantic |

## Live Audio vs Static File Transcription

DupliCleaner transcribes static files (complete audio recordings on disk), not live streaming audio. This changes which tools are optimal.

### Different Priorities

| | Live Audio (Habla's use case) | Static Files (DupliCleaner's use case) |
|---|---|---|
| **Priority** | Low latency | Maximum accuracy + throughput |
| **Input** | Streaming chunks | Complete file upfront |
| **VAD** | Essential (detect silence in real-time) | Nice-to-have (skip silence for speed) |
| **Partial results** | Yes (show text as spoken) | No (just show progress %) |
| **Multiple passes** | Not possible | Can re-process for better alignment |
| **Batch processing** | One stream at a time | Process many files in a queue |

### ASR Engine Comparison for Static Files

| Engine | Speed | Accuracy | Best For | Notes |
|---|---|---|---|---|
| **insanely-fast-whisper** | Fastest (3-4x faster than faster-whisper) | Same as base Whisper | Batch processing static files on GPU | HuggingFace Transformers, FlashAttention-2, can transcribe 2.5hrs in <98s |
| **faster-whisper** (current) | 4x faster than OpenAI Whisper | Same as base Whisper | General purpose, good default | CTranslate2-based, good int8 quantization, already implemented |
| **WhisperX** (Habla uses) | Same as faster-whisper | Best timestamps | Word-level timestamps, subtitle export | Wraps faster-whisper + adds alignment and VAD |
| **OpenAI Whisper** | Baseline (slowest) | Baseline | Reference only | Not recommended for production |

### Recommended Model

**Whisper Large V3 Turbo** - 6x faster than Large V3 with only 1-2% accuracy loss (809M params). Drop-in model swap compatible with all engines above.

### Recommended Engine Strategy

| Phase | Engine | Why |
|---|---|---|
| Phase 1-3 (now) | **faster-whisper** (already implemented) | Works, proven, connect UI and ship |
| Speed upgrade | **insanely-fast-whisper** | 3-4x faster batch processing for "transcribe this whole folder" |
| Timestamps/subtitles | **WhisperX** | Only if word-level timestamps or .srt/.vtt export needed |
| Diarization | **Pyannote** (from Habla) | Best option regardless of ASR engine choice |

### Key Insight

Habla's tools (WhisperX + Silero VAD + streaming ffmpeg) are optimized for real-time streaming. For DupliCleaner's batch-of-files use case, **insanely-fast-whisper** is purpose-built and significantly faster. Pyannote for speaker diarization and Silero VAD for silence skipping are still useful regardless of ASR engine.

### Sources

- [Choosing between Whisper variants (Modal)](https://modal.com/blog/choosing-whisper-variants)
- [Best open source STT model in 2026 (Northflank)](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [I Tested Every Whisper Variant (SubSmith)](https://subsmith.app/blog/whisper-variants-explained)
- [Whisper Large V3 Turbo (HuggingFace)](https://huggingface.co/openai/whisper-large-v3-turbo)
- [insanely-fast-whisper (GitHub)](https://github.com/Vaibhavs10/insanely-fast-whisper)

## What's Incomplete

### 1. UI Settings Not Connected to Backend

**Current state:** UI controls exist for Whisper model, device, and compute type (TAG_AUDIO_WHISPER_MODEL, TAG_AUDIO_WHISPER_DEVICE, TAG_AUDIO_WHISPER_COMPUTE) but the analysis run callback is stubbed.

**Needed:**
- Read Whisper settings from UI controls when analysis starts
- Pass settings to ContentSummarizer configuration
- Persist settings to config file

### 2. No Standalone Transcription Mode

**Current state:** Audio transcription only runs as part of the full batch summarization pipeline.

**Needed:**
- "Transcribe Audio" as a standalone action (without requiring full summarization)
- Right-click context menu on audio files: "Transcribe this file"
- Batch transcribe a folder of audio files
- Option to save transcription as a text file alongside the audio

### 3. Transcription Display in UI

**Current state:** Transcriptions are stored in the database but not easily viewable.

**Needed:**
- Show transcription text in file details panel (Files tab)
- Searchable via FTS5 (may already work if summaries are indexed)
- Audio player integration: display transcription alongside playback controls
- Word-level timestamps for transcript navigation (faster-whisper supports this)

### 4. Speaker Diarization (Not Implemented)

**Needed for multi-speaker recordings:**
- Identify different speakers in a recording
- Label transcript segments by speaker (Speaker 1, Speaker 2, etc.)
- Optional: match speaker voices to known people
- Libraries: pyannote-audio (proven in Habla project), NeMo

### 5. VAD-Based Speech Segmentation (Not Implemented)

**Current state:** Entire audio file is passed to Whisper as one unit.

**Habla approach:** Silero VAD segments audio into speech chunks before ASR, skipping silence. This improves accuracy and speed for recordings with long pauses (meetings, lectures, voice memos).

### 6. LLM Error Correction (Not Implemented)

**Current state:** Raw Whisper output is stored directly.

**Habla approach:** Passes ASR output through an LLM with context to fix common transcription errors (proper nouns, technical terms, homophones). DupliCleaner already has LLM integration that could be reused.

## Implementation Phases

### Phase 1: Connect UI to Backend

- Wire `_on_run_analysis()` to read Whisper UI settings
- Pass audio configuration to ContentSummarizer
- Ensure audio files are processed when "Include Audio" is checked
- Display transcription progress in status panel
- Save/load Whisper settings to config

### Phase 2: Standalone Transcription

- Add "Transcribe" action to file context menus and Files tab
- Single-file transcription with result displayed immediately
- Batch transcription for selected folder
- Export options: save as .txt, .srt (subtitles), .vtt (web subtitles)
- Progress reporting per file (faster-whisper provides segment-level progress)

### Phase 3: Transcription Display and Search

- Transcription viewer in file details panel
- Full-text search across all transcriptions (verify FTS5 indexes audio summaries)
- Highlight search terms within transcription text
- Link from search results to specific audio file and transcript location

### Phase 4: VAD + LLM Post-Processing (from Habla)

- **Silero VAD integration** - Segment audio into speech chunks before ASR
  - Skip silence (faster), isolate utterances (more accurate)
  - Parameters proven in Habla: 0.35 threshold, 600ms silence, 400ms min speech
  - CPU-only, ~2MB model, no GPU impact
- **LLM error correction** - Pass raw transcription through LLM to fix:
  - Proper nouns and names
  - Technical terms and jargon
  - Homophones and context-dependent words
  - Reuse existing LMStudio/Ollama/cloud LLM integration

### Phase 5: Speaker Diarization (from Habla)

- **Pyannote 3.1** - CPU-based speaker identification (proven in Habla)
  - Requires HuggingFace token for model access
  - Labels speakers (Speaker A, Speaker B, etc.)
  - Runs on CPU (zero GPU impact)
- Speaker-labeled transcript display
- Optional: match speaker voice embeddings to known people
- Export speaker-separated transcripts

### Phase 6: Advanced Audio Features

- **WhisperX** - Upgrade from faster-whisper for word-level timestamp alignment
- **Language detection** - Auto-detect language before transcription
- **Translation** - Whisper can translate non-English audio to English
- **Audio quality assessment** - Flag low-quality recordings that may produce poor transcriptions
- **Meeting/interview mode** - Optimized settings for spoken word vs music
- **Timestamp navigation** - Click on transcript text to jump to that point in audio

## Technical Considerations

### Model Size vs Accuracy

| Model | Size | Speed | Accuracy | VRAM |
|-------|------|-------|----------|------|
| tiny | 39 MB | Very fast | Low | ~1 GB |
| base | 74 MB | Fast | Moderate | ~1 GB |
| small | 244 MB | Medium | Good | ~2 GB |
| medium | 769 MB | Slow | Very good | ~5 GB |
| large | 1.5 GB | Very slow | Best | ~10 GB |

- Default to "base" for speed, recommend "small" for accuracy
- Auto-detect GPU availability and suggest appropriate model

### VRAM Management

- Whisper and vision models (CLIP, InsightFace) compete for GPU memory
- ContentSummarizer already handles model loading/unloading by processing type
- Audio processed alongside text (no vision model needed), so VRAM conflict is minimal
- Large Whisper models (medium/large) may need exclusive GPU access

### Performance

- faster-whisper is 4x faster than openai-whisper with int8 quantization
- Real-time factor: base model transcribes ~10x real-time on GPU
- 1 hour of audio takes ~6 minutes with base model on GPU
- Batch processing should estimate total duration and show ETA

### File Format Handling

- faster-whisper/whisper handle most formats natively via ffmpeg
- Ensure ffmpeg is available (already a dependency for video processing)
- Large files (>1 hour): process in chunks to manage memory
- Corrupted audio: graceful failure with error message, don't crash batch
- Habla approach: ffmpeg subprocess decoder handles any format reliably

### Dependencies (New)

| Library | Purpose | GPU | Phase | Notes |
|---|---|---|---|---|
| faster-whisper (existing) | CTranslate2-based ASR | Yes | 1-3 | Already implemented, solid default |
| insanely-fast-whisper | HF Transformers batch ASR | Yes (NVIDIA) | Speed upgrade | 3-4x faster than faster-whisper, FlashAttention-2 |
| whisperx | Word-level aligned ASR | Yes | Timestamps | Wraps faster-whisper + alignment |
| silero-vad | Speech/silence segmentation | No (CPU) | 4 | ~2MB model, very fast |
| pyannote.audio | Speaker diarization | No (CPU) | 5 | Requires HuggingFace token |
| torch (existing) | Backend for all above | Optional | - | Already a dependency |

faster-whisper, whisperx, silero-vad, and pyannote are proven together in the Habla project on RTX 3060 12GB. insanely-fast-whisper is a separate upgrade path for maximum batch throughput.
