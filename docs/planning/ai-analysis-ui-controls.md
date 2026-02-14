# AI Analysis UI Controls

## Goal

Wire up the six stubbed AI analysis UI callbacks in app.py to the fully implemented backend analysis engine (BatchContentSummarizer, FaceAnalyzer, PetAnalyzer, etc.). The UI controls exist and the backend is ready - they just need to be connected.

## Current State

### UI Controls (Created, Not Wired)

The following UI elements exist in app.py but their callbacks only log warning messages:

| Control | Tag | Stub Method | Purpose |
|---------|-----|-------------|---------|
| Refresh Models button | - | `_refresh_model_status()` | Show download/load status of all AI models |
| Verify Models button | - | `_verify_models()` | Check model file integrity (checksums) |
| Install AI Deps button | - | `_install_ai_dependencies()` | Install optional AI packages |
| Deps Variant dropdown | - | `_on_ai_deps_variant_changed()` | Select CUDA vs CPU variants |
| Run Analysis button | TAG_ANALYSIS_RUN | `_on_run_analysis()` | Start full AI analysis pipeline |
| Cancel Analysis button | TAG_ANALYSIS_CANCEL | `_on_cancel_analysis()` | Cancel running analysis |

### Analysis Configuration Controls (Created, Need Reading)

These settings UI elements exist and need to be read by the run callback:

- Include Images checkbox (TAG_ANALYSIS_INCLUDE_IMAGES)
- Include Documents checkbox (TAG_ANALYSIS_INCLUDE_DOCS)
- Include Data Files checkbox (TAG_ANALYSIS_INCLUDE_DATA)
- Document extensions field (TAG_ANALYSIS_DOC_EXTENSIONS)
- Data extensions field (TAG_ANALYSIS_DATA_EXTENSIONS)
- Scan before full analysis checkbox (TAG_ANALYSIS_SCAN_BEFORE_FULL)
- Re-analyze existing checkbox (TAG_ANALYSIS_REANALYZE)
- Audio Whisper model/device/compute type selectors

### Backend (Fully Implemented)

- `BatchContentSummarizer` in content_summarizer.py - processes images, documents, video, audio
- `FaceAnalyzer` in faces.py - face detection, clustering, recognition
- `PetAnalyzer` in pets.py - pet detection and clustering
- `AnalysisRunner` in analysis_runner.py - orchestrates multi-step analysis
- `ModelManager` in model_manager.py - model lifecycle management

## Implementation Plan

### Phase 1: Model Management Controls

#### _refresh_model_status()
- Query ModelManager for status of each AI model (InsightFace, YOLO, CLIP, Whisper, etc.)
- Display in a status table: model name, downloaded (yes/no), loaded (yes/no), size, path
- Show GPU memory usage if models are loaded
- Update status text in UI

#### _verify_models()
- For each downloaded model, verify file exists and size matches expected
- Optionally compute checksum for known models
- Report results: all good, or list of corrupted/missing models
- Offer to re-download failed models

#### _install_ai_dependencies()
- Read selected variant (CUDA/CPU) from dropdown
- Build pip install command for optional AI packages
- Run in subprocess with progress output to status panel
- Packages: insightface, onnxruntime-gpu/onnxruntime, ultralytics, faster-whisper, easyocr
- Update model status after installation

#### _on_ai_deps_variant_changed()
- Update which packages will be installed (GPU vs CPU versions)
- Show estimated download size
- Warn if switching from GPU to CPU or vice versa

### Phase 2: Analysis Run/Cancel

#### _on_run_analysis()
- Read all configuration from UI controls (checkboxes, extensions, options)
- Build analysis configuration object
- If "scan before analysis" is checked, run scan first
- Launch analysis in background thread (must not block UI)
- Update TAG_ANALYSIS_STATUS with progress (files processed, current phase)
- Disable Run button, enable Cancel button during execution
- Pipeline order:
  1. (Optional) Scan for new files
  2. Face detection and clustering
  3. Pet detection and clustering
  4. Scene classification and object detection
  5. OCR for documents
  6. Audio transcription
  7. Content summarization
- On completion: re-enable Run, disable Cancel, show summary of results

#### _on_cancel_analysis()
- Set cancellation flag on the running analysis
- Analysis runner checks flag between phases and between files
- Graceful shutdown: finish current file, don't start next
- Update status: "Analysis cancelled. Processed X of Y files."
- Re-enable Run button

### Phase 3: Progress Reporting

- Real-time progress bar in Analysis section
- Current phase indicator (Faces / Pets / Scenes / OCR / Summaries)
- Files processed / total count
- Estimated time remaining
- Errors/warnings accumulated during run
- Final summary report when complete

### Phase 4: Selective Re-Analysis

- Allow re-running specific phases (just faces, just summaries, etc.)
- "Re-analyze existing" option to overwrite previous results
- "Analyze new files only" as the fast default
- Per-folder analysis scope selection

## Technical Considerations

### Threading

- All analysis MUST run in a background thread
- UI updates via DearPyGUI's thread-safe callback mechanism
- Progress updates throttled to avoid UI lag (max 10 updates/second)
- Cancellation must be cooperative (check flag, not thread kill)

### Error Handling

- Individual file failures should not stop the batch
- Accumulate errors and present summary at end
- GPU out-of-memory: catch, reduce batch size, retry
- Model download failures: clear error message with retry option

### State Management

- Track analysis state: idle, running, cancelling, complete
- Persist "last analysis" timestamp per scan/drive
- Show which files have been analyzed vs pending
