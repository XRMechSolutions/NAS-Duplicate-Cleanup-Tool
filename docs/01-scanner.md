# File Scanner

## What It Does

The File Scanner discovers all files on your drives and network shares. It's the first step in finding duplicates - before the app can identify duplicates, it needs to know what files exist and where they are.

When you scan a location, the app walks through every folder, records information about each file (size, dates, type), and stores this in its database. This catalog is then used by all other features: duplicate detection, photo organization, face recognition, and more.

## Getting Started

### Adding Your First Drive

1. Open the app and go to the **Drives** tab
2. Click the **Add Drive** button
3. Enter a folder path or UNC path like `\\LS210D11E\share\Photos`
4. Give it a friendly name (optional)
5. Click **Add**

The location appears in your drives list with a "Not Scanned" status.

### Starting a Scan

1. Select a drive from the list
2. Click **Quick Scan**, **Deep Scan**, or **Full Analysis**
3. Choose your scan type:
   - **Quick Scan** - Only checks new and modified files (fast, use after first scan)
   - **Deep Scan** - Re-examines all files even if unchanged (thorough but slower)
   - **Full Analysis** - Deep scan plus AI analysis of all images
4. The scan starts immediately

You can also use **Scan All** to run the same scan mode across every registered drive, one at a time.

### What You'll See During Scanning

The scan progress panel shows:

```
Scanning: \\LS210D11E\share\Photos\2023\Summer
Files found: 45,231
Folders processed: 1,247
Speed: 342 files/sec
Elapsed: 2m 15s

[=============================>          ] 73%

[Pause]  [Cancel]
```

- **Files found** - Running count of files discovered
- **Current path** - The folder being scanned right now
- **Speed** - How fast files are being cataloged
- **Progress bar** - Estimated completion (based on previous scans or folder count)

### Pausing and Resuming

Click **Pause** to temporarily stop the scan. The app saves its position so you can:
- Close the app and resume later
- Let the NAS rest if it's getting hot
- Use your computer for other things

To resume, go to Drives tab and click **Resume Scan** on the paused drive.

If the app crashes or you force-close it during a scan, you'll see **Resume Scan** enabled for that drive the next time you open the app. Starting a new scan clears the saved resume point.

**Note:** Resume is best-effort. The scanner saves its last known path and continues from there, which can re-scan a small section if the drive changed while the app was closed.

## Handling Network Drives

### Connecting to Your NAS

The app works with any network share accessible from Windows, including:
- Buffalo LinkStation (`\\LS210D11E\share`)
- Synology DiskStation (`\\diskstation\volume1`)
- QNAP (`\\qnap\multimedia`)
- Any SMB/CIFS share

Just enter the UNC path (the `\\server\share` format) when adding the location.

**Tip:** Prefer UNC paths for network shares. Mapped drive letters are treated as separate locations.

### When the Network Disconnects

If your NAS becomes unreachable during a scan (unplugged, network issue, NAS went to sleep):

1. The scan pauses automatically
2. The Drives tab status updates to reflect the disconnect
3. You can cancel or resume once the drive is reachable again

When the NAS comes back online, the scan resumes from where it left off.

### Performance Tips for NAS Scanning

Network drives are slower than local drives. To get the best performance:

- **Wired connection** - Ethernet is much faster than WiFi for large scans
- **Wake your NAS** - If it has sleep mode, wake it before scanning
- **Off-peak hours** - Scan when no one else is using the NAS
- **Start with specific folders** - If you only care about Photos, scan just that folder instead of the entire share

## What Gets Scanned (and What Doesn't)

### Automatically Skipped

The app skips system and temporary files that you don't need to deduplicate:

**System Folders:**
- Recycle Bin (`$RECYCLE.BIN`)
- System Volume Information
- Windows folder
- Program files and app data

**Development Junk:**
- `.git` folders (version control)
- `node_modules` (JavaScript packages)
- `__pycache__` (Python cache)
- Build and dist folders

**Temporary Files:**
- `*.tmp` files
- Thumbs.db, desktop.ini
- Browser caches

### Customizing What's Skipped

Go to **Settings > Scanner > Ignore Patterns** to customize:

**To skip additional items:**
1. Click **Add Pattern**
2. Enter a pattern:
   - `*.log` - Skip all .log files
   - `backup_old/*` - Skip a specific folder
   - `*.bak` - Skip backup files
3. Click **Save**

**To scan something normally skipped:**
1. Find the pattern in the list
2. Uncheck it or click **Remove**
3. Re-scan the location

### About Symbolic Links

By default, the app does not follow symbolic links or Windows junctions. This prevents:
- Infinite loops if links point to parent folders
- Scanning the same files multiple times
- Unexpected results from links pointing elsewhere

If you need to follow symlinks, enable it in **Settings > Scanner > Follow Symbolic Links**. The app will track where it's been to avoid cycles.

## Understanding Scan Results

After a scan completes, you'll see a summary:

```
Scan Complete: NAS Photos

Files discovered:    127,453
  Images:            98,234
  Videos:            12,341
  Documents:          8,567
  Other:              8,311

New files:           3,421
Modified files:        847
Removed files:         156

Errors:                  23
  Permission denied:     21
  Unreadable:             2

Time elapsed: 12m 34s
```

### About Errors

Some errors are normal:
- **Permission denied** - System files you can't access. Usually fine to ignore.
- **Path too long** - Extremely deep folder structures. The app tries extended paths but some may still fail.
- **Unreadable** - Corrupted files or disk errors. Consider checking your drive health.

Click **View Error Log** to see exactly which files had problems.

## Scan Types Explained

### Quick Scan (Default After First Scan)

The fastest option. The app checks each file's modification date:
- **Unchanged files** - Uses cached information from the last scan
- **New files** - Fully processes them
- **Modified files** - Re-processes them
- **Deleted files** - Removes them from the database

Use Quick Scan for regular maintenance when you've added some new files.

### Deep Scan

Re-examines every file regardless of whether it appears unchanged. Use this when:
- You suspect file contents changed without the date updating
- You've recovered files from backup
- You want to verify the database is accurate
- Something seems wrong with duplicate detection

### Full Analysis

Like Deep Scan, but also runs AI analysis on all images:
- Face detection and recognition
- Scene classification
- Quality scoring
- Object detection

Use this after major changes or when you want to refresh all AI-generated metadata.

### Face Analysis While Scanning

If face recognition is enabled and the model is installed, the app can start face analysis on images as soon as they're discovered during a scan. It keeps processing new images while the scan runs and finishes any remaining items after the scan completes.

## Behind the Scenes

### How Scanning Works

1. **Directory Walking** - The app uses efficient OS calls to list folder contents
2. **Metadata Collection** - For each file: size, creation date, modification date, file type
3. **Database Storage** - Files are batched and written to the database every few seconds
4. **Progress Tracking** - Position is saved regularly for crash recovery

### What's Stored

For each file, the scanner records:
- Full path
- Which drive/share it's on
- File size (bytes)
- Creation and modification timestamps
- File extension and MIME type
- When it was last scanned

Content hashes and AI analysis are done by other modules after the scan.

### Technical Details

- Uses `os.scandir()` for memory-efficient directory listing
- Extended path support (`\\?\`) for paths over 260 characters
- Database writes batched in groups of 1,000 files
- Progress saved to disk every 5 seconds for crash recovery
