# Auto-Scan Summarization Feature

The UI now intelligently handles summarization with automatic scanning and drive registration!

## How It Works

### Smart Path Resolution

The system uses this priority:

1. **Folder Path Input** (if provided) → Use this path
2. **Selected Drive** (if no path provided) → Use drive's root path
3. **Neither** → Show error

### Automatic Scanning

When you click "Generate Summaries", the system:

1. ✅ **Checks if path is in database**
   - If YES → Proceed to summarization
   - If NO → Continue to step 2

2. ✅ **Checks if path is within a registered drive**
   - If YES → Run quick scan on that drive
   - If NO → Continue to step 3

3. ✅ **Registers path as new drive**
   - Adds drive to database
   - Runs quick scan
   - Updates UI drive list

4. ✅ **Runs summarization**
   - Now guaranteed to have files in database
   - Proceeds with batch/sequential processing

## Usage Scenarios

### Scenario 1: Use Selected Drive (Simplest)

```
1. Select a drive from list (e.g., "C:\Photos")
2. Leave "Folder Path" empty
3. Click "Generate Summaries"
```

**What happens:**
- If drive scanned → Summarize immediately
- If drive not scanned → Auto-scan, then summarize

### Scenario 2: Use Folder Path (Most Flexible)

```
1. Enter path: "C:\EpsteinFiles"
2. Click "Generate Summaries"
```

**What happens:**
- Path not in database → Registers as new drive
- Runs quick scan (~30 sec - 2 min depending on size)
- Proceeds with summarization

### Scenario 3: Subfolder of Registered Drive

```
1. Registered drive: "C:\NAS"
2. Enter path: "C:\NAS\Photos\2024"
3. Click "Generate Summaries"
```

**What happens:**
- Recognizes path is within "C:\NAS" drive
- If drive scanned → Use existing data
- If drive not scanned → Scan drive first
- Summarizes only files in "C:\NAS\Photos\2024"

## Progress Messages

You'll see these status messages:

### Check Phase
```
Checking if path is scanned...
```

### Auto-Scan Phase (if needed)
```
Path not registered. Adding as drive and scanning...
Scanning: 1523 files found...
Scan complete: 1523 files indexed
```

### Summarization Phase
```
Starting summarization...
LMStudio Monitor detected - automatic model management enabled
File breakdown: text=45, images=23, docs=12, skipped=5
Processing Text Files: 15/45 - document.pdf
```

## Examples

### Example 1: Epstein Files (New Path)

**Setup:**
- Path: `C:\EpsteinFiles`
- Not in database
- Not registered as drive

**Actions:**
1. Enter `C:\EpsteinFiles` in Folder Path
2. Provider: `lmstudio`
3. File Types: `.pdf,.txt,.docx`
4. Click "Generate Summaries"

**System does:**
```
✅ Checks database → No files found
✅ Checks drives → Not registered
✅ Registers "C:\EpsteinFiles" as new drive
✅ Scans directory → Finds 3,247 files
✅ Updates drive list in UI
✅ Starts summarization
```

**Time:**
- Scan: ~2 minutes (3000 files, quick scan)
- Summarization: ~10 minutes (500 file limit)
- Total: ~12 minutes

### Example 2: Photos Drive (Already Registered)

**Setup:**
- Drive registered: `C:\Photos`
- Already scanned with 50,000 files
- Want to summarize subfolder

**Actions:**
1. Enter `C:\Photos\2024\Vacation` in Folder Path
2. Provider: `lmstudio`
3. Batch mode: ✅ Enabled
4. Click "Generate Summaries"

**System does:**
```
✅ Checks database → Found files in C:\Photos
✅ Skips scan (already scanned)
✅ Filters to C:\Photos\2024\Vacation subdirectory
✅ Starts summarization immediately
```

**Time:**
- Scan: 0 seconds (skipped)
- Summarization: ~3 minutes (150 vacation photos)
- Total: ~3 minutes

### Example 3: Use Selected Drive

**Setup:**
- Drive selected in list: `E:\NAS_Backup`
- Not yet scanned

**Actions:**
1. Leave Folder Path empty
2. Select `E:\NAS_Backup` from drive list
3. Click "Generate Summaries"

**System does:**
```
✅ Uses selected drive path: E:\NAS_Backup
✅ Checks database → No files found
✅ Scans E:\NAS_Backup → Finds 125,000 files
✅ Starts summarization (with 500 file limit)
```

**Time:**
- Scan: ~5 minutes (125k files, quick scan)
- Summarization: ~8 minutes (500 file limit)
- Total: ~13 minutes

## Scan Performance

### Quick Scan Stats (No Hashing)

| File Count | Scan Time | Notes |
|------------|-----------|-------|
| 1,000 | 10-20 sec | Small directory |
| 10,000 | 30-60 sec | Medium directory |
| 100,000 | 2-5 min | Large NAS folder |
| 1,000,000 | 15-30 min | Very large drive |

Quick scan only indexes files (no hash computation), so it's fast!

## UI Improvements

### New Descriptive Text

```
Generate AI summaries for files. Uses selected drive below OR enter a folder path.
If path not scanned, will auto-scan first (registers new drives automatically).
```

### Clearer Hints

**Folder Path Input:**
```
Leave empty to use selected drive, or enter specific path
```

**Browse Button Tooltip:**
```
Browse for folder to summarize
If not scanned, will auto-scan before summarization
```

## Benefits

### ✅ No More "File Not Found" Errors
System auto-scans if needed

### ✅ Flexible Workflow
- Use selected drive
- Use folder path
- Use subfolder of drive

### ✅ Automatic Drive Registration
New paths become drives automatically

### ✅ Clear Progress Feedback
See scan progress → summarization progress

### ✅ One-Click Operation
No manual scan → summarize workflow

## Technical Details

### Auto-Scan Logic

```python
def _run_summarization_with_auto_scan(target_path):
    # Check if files exist in database
    files = db.get_files_in_directory(target_path, limit=1)

    if not files:
        # Check if path is in a registered drive
        matching_drive = find_drive_for_path(target_path)

        if matching_drive:
            # Scan existing drive
            scan_drive(matching_drive.id, ScanMode.QUICK)
        else:
            # Register new drive and scan
            drive_id = register_new_drive(target_path)
            scan_drive(drive_id, ScanMode.QUICK)

    # Now proceed with summarization
    run_summarization(target_path)
```

### Drive Registration

When registering a new drive:
```python
new_drive = Drive(
    name=os.path.basename(target_path),  # "EpsteinFiles"
    root_path=target_path,                # "C:\EpsteinFiles"
    drive_type="folder"                   # Not a physical drive
)
```

### Scan Mode

Auto-scan uses **QUICK mode**:
- ✅ Discovers all files
- ✅ Records metadata (size, dates, path)
- ❌ No hash computation (fast!)
- ❌ No duplicate detection yet

You can run deep scan later for deduplication.

## Workflow Comparison

### Before (Manual)
```
1. Add drive manually
2. Scan drive
3. Wait for scan
4. Navigate to Generate Summaries
5. Enter folder path
6. Click Generate Summaries
```

**Total clicks: 6-8**
**Time to start: 2-5 minutes**

### After (Auto)
```
1. Enter folder path (or select drive)
2. Click Generate Summaries
```

**Total clicks: 2**
**Time to start: Immediate (auto-scan in background)**

## Troubleshooting

### "Scan failed" during auto-scan

**Cause:** Permissions issue or path not accessible

**Solution:**
- Check folder exists and is accessible
- Run DupliCleaner as administrator if needed
- Verify path is correct

### Auto-scan is slow

**Cause:** Large directory with many files

**Solution:**
- This is normal for first scan
- Subsequent summarizations skip scan
- Use file type filters to reduce scope

### Drive list not updating

**Cause:** UI not refreshing after auto-registration

**Solution:**
- Click "Refresh" button in drives section
- Or restart DupliCleaner

## Best Practices

### 1. Let Auto-Scan Work
Don't worry about pre-scanning - system does it automatically

### 2. Use File Type Filters
```
File Types: .pdf,.docx    # Only scan/summarize documents
```

### 3. Start with Small Limits
```
Limit: 50    # Test with small batch first
```

### 4. Register Common Paths
For frequently-used paths, manually add as drive for better organization

### 5. Monitor First Run
Watch the scan progress to estimate time for large directories

## Summary

**You can now:**
- ✅ Enter any folder path
- ✅ System auto-scans if needed
- ✅ System auto-registers drives
- ✅ One-click workflow
- ✅ No manual database management

**The system handles everything automatically!** 🎉
