# Folder Watching & Auto-Organization

## Goal

Automatically detect new files added to monitored folders (NAS directories, phone sync folders, download directories) and trigger scanning, deduplication, and organization without requiring manual intervention. When new photos are dumped from a phone, they should be automatically sorted, duplicates flagged, and AI analysis queued.

## Current Capabilities

### Drive Monitoring (drives/manager.py - working)

- Polling-based drive status monitoring (lines 367-407)
- 30-second configurable interval
- Threaded with clean shutdown via `threading.Event`
- Detects drive connect/disconnect status changes
- Notifies on status changes via callback

### Versioning Service Monitor (core/versioning_service.py - working)

- Polling-based file change detection (lines 49-108)
- 5-second poll interval, 60-second debounce
- Detects modified files in watched directories
- Triggers version snapshots on file changes
- Threaded with clean shutdown

### What's NOT Implemented

- No file system event-based watching (watchdog library)
- No auto-scan trigger on new files
- No auto-organization of incoming files
- No "inbox" folder concept
- No auto-deduplication on arrival
- No auto-AI analysis trigger
- No notifications for new file processing
- No configurable watch rules (which folders, what actions)

## What Needs to Be Built

### 1. File System Watcher

Replace or supplement polling with event-based file system monitoring.

**Options:**
- **watchdog** library (cross-platform, Python): FileSystemEventHandler for created/modified/moved events
- **Polling** (current approach): Works everywhere but higher latency and CPU usage
- **Hybrid**: watchdog for real-time events, polling as fallback for network drives where watchdog is unreliable

**NAS consideration:** Network shares (SMB/NFS) often don't support inotify/ReadDirectoryChanges. Polling may be the only reliable option for NAS paths. Use watchdog for local paths and polling for network paths.

### 2. Watch Folder Configuration

Users define which folders to monitor and what should happen when files arrive.

**Per-folder settings:**
- Watch path (local or network)
- Watch mode: real-time (watchdog) or polling (configurable interval)
- Enabled/disabled toggle
- Actions on new file:
  - Scan and hash (always)
  - Check for duplicates (compare against existing database)
  - Run AI analysis (faces, scenes, objects, quality)
  - Auto-organize (move to date/location folders)
  - Generate AI summary
- Notification preferences

### 3. Inbox Folder Pattern

A designated "inbox" folder where users can dump unsorted files. The system processes and organizes them automatically.

**Workflow:**
1. User dumps photos from phone into `\\NAS\Photos\Inbox\`
2. Watcher detects new files within debounce period (e.g., 60 seconds after last file)
3. System scans new files, extracts metadata
4. Duplicate check against full database
5. New unique files organized into date/location structure
6. Duplicates flagged for review (not auto-deleted)
7. AI analysis queued (faces, scenes, summaries)
8. User notified: "Processed 247 new photos: 231 organized, 16 duplicates found"

### 4. Auto-Organization Pipeline

When new files are detected, run a configurable pipeline:

**Steps (each optional/configurable):**
1. Extract metadata (EXIF, dates, GPS)
2. Compute hashes
3. Check for exact duplicates
4. Check for near-duplicates (perceptual hash)
5. Organize by date/location/event
6. Run face detection
7. Run scene classification
8. Generate AI summary
9. Move processed files out of inbox

### 5. Processing Queue

New files should be queued for processing rather than processed inline.

**Queue features:**
- Priority levels: user-triggered (high) vs auto-detected (normal) vs background (low)
- Batch processing: wait for burst of new files to settle before processing
- Debounce: configurable quiet period after last file event (default 60 seconds)
- Retry on failure
- Progress tracking per batch
- Cancel/pause support

## Implementation Phases

### Phase 1: Watch Folder Configuration UI

- Add "Watch Folders" section to settings or drives panel
- Add/remove/edit watch folders
- Per-folder settings: path, mode (polling/auto), interval, enabled
- Store watch folder config in database or config.json
- Basic polling watcher using existing versioning service pattern

### Phase 2: Auto-Scan on New Files

- When watcher detects new files, trigger scan for those files only (incremental scan)
- Hash new files and check against existing database for duplicates
- Display results in status panel: "Found 12 new files in \\NAS\Photos\Inbox"
- Notification when duplicates found: "3 of 12 new files are duplicates"

### Phase 3: Auto-Organization

- After scanning, apply organization rules to new files
- Use existing organizer with configurable rules (by-date, by-location, etc.)
- Dry-run first, auto-apply if user has opted in
- Move processed files from inbox to organized location
- Handle conflicts (file exists at destination)

### Phase 4: Auto-AI Analysis

- Queue new files for AI analysis (faces, scenes, quality, summaries)
- Run in background with low priority
- Update database as analysis completes
- Notify when faces are detected that need assignment

### Phase 5: Event-Based Watching (watchdog)

- Add watchdog as optional dependency
- Use for local folder monitoring (faster, lower CPU than polling)
- Fall back to polling for network paths
- Debounce rapid file system events (many events during file copy)
- Handle watchdog edge cases: partial file writes, temp files, OS-specific quirks

## Technical Considerations

### NAS/Network Drive Challenges

- SMB/NFS shares may not support file system events (inotify, ReadDirectoryChanges)
- Polling is the reliable fallback for network drives
- Network latency means files may appear partially written
- Check file size stability before processing (wait for file to stop growing)
- Handle network disconnections gracefully (pause watching, resume on reconnect)

### Debouncing

When a user copies 500 photos from a phone, the system receives 500 individual file creation events. Without debouncing:
- 500 separate scans would be triggered
- Database writes would conflict
- UI would be overwhelmed with notifications

Debounce strategy:
- After detecting first new file, start a timer (default 60 seconds)
- Reset timer on each subsequent file event
- When timer expires (no new files for 60 seconds), process the batch
- Display "Watching... 247 new files detected, waiting for transfer to complete"

### File Locking

- Don't process files that are still being written
- Check: file size stable for N seconds, file not locked by another process
- On Windows: try opening file for read; if locked, retry after delay
- On network shares: file size polling (check size, wait, check again)

### Resource Management

- Auto-processing should not interfere with user-initiated operations
- Pause auto-processing when user is actively using the app
- Resume when app is idle or in background
- Configurable resource limits: max CPU%, max concurrent files
- Night mode: run heavy processing (AI analysis) during off-hours

### Configuration Schema

```python
@dataclass
class WatchFolder:
    path: str
    enabled: bool = True
    mode: str = "polling"  # "polling" or "watchdog"
    poll_interval_seconds: int = 60
    debounce_seconds: int = 60
    auto_scan: bool = True
    auto_organize: bool = False
    auto_ai_analysis: bool = False
    organize_format: str = "YYYY/MM"
    organize_by_location: bool = False
    detect_events: bool = False
```

## Edge Cases

| Scenario | Handling |
|---|---|
| File copied but transfer interrupted | Check file size stability before processing |
| Same file added to multiple watched folders | Dedup check catches it, process only once |
| Watched folder is on disconnected drive | Pause watching, resume when drive reconnects |
| Thousands of files dumped at once | Debounce, batch process, show progress |
| User deletes file from inbox before processing | Skip missing files gracefully |
| Temp files from OS (.DS_Store, thumbs.db) | Filter by extension, ignore known temp patterns |
| File renamed while being processed | Handle FileNotFoundError, re-scan |
| Watch folder deleted | Detect missing folder, disable watch, notify user |

## Integration Points

- **Scanner** - Incremental scan for new files only (not full directory re-scan)
- **Hasher** - Hash new files for duplicate checking
- **Comparator** - Near-duplicate check against existing database
- **Organizer** - Apply organization rules to new files
- **AI Analysis Runner** - Queue new files for face/scene/quality analysis
- **Action Engine** - Move/copy operations for auto-organization
- **Drive Manager** - Drive status affects watch folder availability
- **Notification System** - Inform user of processing results (future)
