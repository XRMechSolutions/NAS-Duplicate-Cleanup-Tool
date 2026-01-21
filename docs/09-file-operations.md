# File Operations

## What It Does

The File Operations system safely executes changes to your files - deleting duplicates, organizing photos, copying for backup. Every operation is logged and most are reversible, so you can undo mistakes.

## Operation Types

### Move to Quarantine

Moves files to a special quarantine folder instead of deleting them.

**How it works:**
1. Files moved to: `[QuarantineFolder]/[Date]/[OriginalPath]/filename`
2. Original folder structure preserved within quarantine
3. A manifest file records original locations

**Best for:**
- Cautious cleanup - review before permanent deletion
- Testing your duplicate resolution settings
- Situations where you might need files back

**Example:**
```
Original: \\NAS\Photos\vacation.jpg
Quarantine: C:\Quarantine\2024-03-15\NAS_Photos\vacation.jpg
```

**Quarantine folder location:** Set in **Settings > Actions > Quarantine Folder**

### Move to System Trash

Sends files to the Windows Recycle Bin or system trash.

**How it works:**
1. Files sent to Recycle Bin using system API
2. Can be restored through normal Windows interface
3. Limited by Recycle Bin size settings

**Best for:**
- Normal cleanup with OS-level safety net
- Smaller batches of files
- Local drives (network drives may not support)

**Limitations:**
- Recycle Bin has size limits
- Network drives may not support trash
- Very large files might bypass Recycle Bin

### Permanent Delete

Immediately deletes files from disk.

**How it works:**
1. Files deleted directly (bypass Recycle Bin)
2. Space freed immediately
3. Detailed audit log records what was deleted

**Best for:**
- Large cleanup operations
- When Quarantine/Trash aren't practical
- Experienced users confident in selections

**Warning:** This is irreversible (without backup). The app asks for confirmation.

### Copy Files

Creates copies of files to another location.

**How it works:**
1. Files duplicated to destination
2. Original files unchanged
3. Verification ensures copy matches original

**Best for:**
- Creating backups
- Ensuring redundancy across drives
- Distributing files to multiple locations

### Move Files

Relocates files to another location.

**How it works:**
1. Files moved to destination
2. Original location emptied
3. More efficient than copy+delete (on same drive)

**Best for:**
- Organization operations
- Consolidating to one drive
- Cleaning up source locations

### Create Hard Links

Instead of duplicates, create hard links so multiple paths point to one file.

**How it works:**
1. One physical file on disk
2. Multiple directory entries point to it
3. Saves space while keeping both "copies" accessible

**Best for:**
- Same file needed in multiple folders
- Massive space savings with no data loss
- NTFS local drives only

**Limitations:**
- Only works on same drive/volume
- Not supported on network shares
- Some applications don't handle hard links well

### Create Symbolic Links

Create shortcuts that point to the original file.

**How it works:**
1. Original file stays in place
2. Symlink at second location points to original
3. Accessing symlink accesses original file

**Best for:**
- Cross-drive "duplicates"
- When you want one canonical location

**Limitations:**
- If original is moved/deleted, symlink breaks
- Some applications don't follow symlinks
- May require administrator privileges on Windows

## Executing Operations

### The Pending Actions Queue

Before anything happens to your files, actions go into a pending queue:

```
PENDING ACTIONS

Ready to execute: 3,456 file operations

SUMMARY:
  Quarantine: 3,234 files (45.2 GB)
  Delete: 0 files
  Move: 222 files (2.1 GB)
  Copy: 0 files

[Review List] [Change Action Type] [Execute All] [Clear All]
```

### Changing Action Types

You can change what happens to pending files:

1. Select files in the pending list
2. Click **Change Action**
3. Choose: Quarantine, Trash, Delete, Cancel

```
CHANGE ACTION

Selected: 500 files currently set to "Quarantine"

Change to:
( ) Move to Trash
( ) Permanent Delete
(•) Cancel (remove from pending)

[Apply Change]
```

### Execution Process

Click **Execute All** to process pending actions:

```
EXECUTING ACTIONS

Processing: 3,456 files

Phase 1: Verifying files exist...
Phase 2: Executing operations...

Completed: 2,341 / 3,456
Current: Moving vacation_2019/IMG_001.jpg

Successful: 2,339
Failed: 2 (permission denied)

[===================>            ] 68%

[Pause] [Cancel]
```

### Handling Failures

If some files fail:

```
OPERATION COMPLETE (with errors)

Successful: 3,452 files
Failed: 4 files

FAILED OPERATIONS:
- \\NAS\Photos\locked.jpg - Permission denied
- \\NAS\Documents\open.docx - File in use
- E:\Archive\missing.jpg - File not found
- D:\Temp\corrupt.bin - I/O error

[Retry Failed] [Skip Failed] [View Details]
```

**Options:**
- **Retry Failed** - Try again (maybe file is no longer in use)
- **Skip Failed** - Mark as skipped, continue with rest
- **View Details** - See full error information

## The Action Log

### What's Recorded

Every operation is logged with:

| Field | Description |
|-------|-------------|
| Timestamp | When the action occurred |
| Action Type | Delete, Quarantine, Move, Copy, etc. |
| Source Path | Original file location |
| Destination | Where file went (if applicable) |
| File Size | Size of the file |
| File Hash | SHA-256 hash for verification |
| Status | Success, Failed, Undone |
| User | Who initiated the action |

### Viewing the Action Log

Go to **Action Log** tab:

```
ACTION LOG

Filter: [All Actions ▼] [All Dates ▼] [All Drives ▼]

TIMESTAMP           ACTION      FILE                          SIZE    STATUS
--------------------------------------------------------------------------------
2024-03-15 14:32   Quarantine  \\NAS\Photos\dup1.jpg        4.2 MB   Success
2024-03-15 14:32   Quarantine  \\NAS\Photos\dup2.jpg        4.2 MB   Success
2024-03-15 14:31   Move        \\NAS\Unsorted\photo.jpg     3.1 MB   Success
2024-03-15 10:15   Delete      D:\Temp\old_backup.zip       156 MB   Success
...

Showing 100 of 12,456 entries [Load More]

[Export Log] [Clear Old Entries]
```

### Filtering the Log

- **By action type** - Show only deletions, only moves, etc.
- **By date range** - Last 24 hours, last week, custom range
- **By drive** - Actions on specific drives
- **By status** - Successful, failed, undone

### Exporting the Log

Export for records or analysis:

- **CSV** - Spreadsheet-compatible
- **JSON** - Machine-readable
- **HTML** - Printable report

## Undo Operations

### What Can Be Undone

| Action | Undo Method |
|--------|-------------|
| Quarantine | Move back to original location |
| Trash | Restore from Recycle Bin |
| Move | Move back to original location |
| Copy | Delete the copy |
| Delete | **Cannot undo** (but logged for reference) |
| Hard Link | Remove the link |

### How to Undo

1. Go to **Action Log**
2. Find the action to undo
3. Click **Undo** (or select multiple and **Undo Selected**)

```
UNDO CONFIRMATION

Undo these actions?

- Quarantine \\NAS\Photos\dup1.jpg → Restore to original
- Quarantine \\NAS\Photos\dup2.jpg → Restore to original

This will:
- Move 2 files from quarantine back to original locations
- Mark these log entries as "Undone"

[Confirm Undo] [Cancel]
```

### Undo Limitations

Cannot undo if:
- Original action was permanent delete
- Quarantine files were emptied
- Destination already has a file with same name
- Original location no longer exists

### Bulk Undo

Undo entire operations at once:

1. Go to **Action Log > By Session**
2. Find the session (e.g., "2024-03-15 14:30 - Quarantine 3,234 files")
3. Click **Undo Entire Session**

## Quarantine Management

### Viewing Quarantine

**Action Log > Quarantine Folder:**

```
QUARANTINE CONTENTS

Folder: C:\Quarantine
Total size: 23.4 GB
Files: 3,456

BY DATE:
  2024-03-15 (today): 234 files (3.2 GB)
  2024-03-14: 567 files (5.6 GB)
  2024-03-10: 1,234 files (8.9 GB)
  2024-03-01: 1,421 files (5.7 GB)

[Browse] [Restore All] [Empty by Date] [Empty All]
```

### Browsing Quarantine

Click **Browse** to explore quarantined files:

- See original paths
- Preview images
- Select files to restore or delete

### Emptying Quarantine

**Empty by Date** - Remove files quarantined before a specific date
**Empty All** - Clear entire quarantine (permanent)

```
EMPTY QUARANTINE

This will PERMANENTLY DELETE all quarantined files.

Files to delete: 3,456
Space to recover: 23.4 GB

This action CANNOT be undone.

Type "DELETE" to confirm: [          ]

[Cancel] [Empty Quarantine]
```

### Automatic Quarantine Cleanup

Set automatic cleanup in **Settings > Actions > Quarantine**:

- **Keep forever** - Never auto-delete
- **Keep 30 days** - Delete after 30 days
- **Keep until size limit** - Delete oldest when folder exceeds X GB

## Safety Features

### Confirmation Prompts

The app asks for confirmation before:
- Any permanent deletion
- Operations on more than 100 files
- Operations that would empty a folder

### Dry Run Mode

Preview what would happen without doing it:

1. Enable **Dry Run** before executing
2. See full list of what would change
3. No files are actually modified
4. Review and adjust before real execution

### Operation Limits

Built-in safeguards:
- Cannot delete files from system folders
- Cannot delete last copy unless confirmed
- Warns if operating on currently open files
- Pauses if drive disconnects mid-operation

### Backup Reminder

Before large deletions:

```
BACKUP REMINDER

You're about to delete 45.2 GB of files.

Before proceeding, consider:
- [ ] I have verified these are duplicates
- [ ] I have a backup of important files
- [ ] I understand this frees up space permanently

[I Understand, Proceed] [Cancel]
```

## Performance

### Operation Speed

| Operation | Speed (typical) |
|-----------|-----------------|
| Delete | 1000+ files/sec (local SSD) |
| Quarantine (same drive) | 500+ files/sec |
| Quarantine (cross drive) | Limited by slower drive |
| Copy | Limited by drive speed |
| Hash verification | 100-500 MB/sec |

### Large Operations

For operations with thousands of files:
- Progress shown in real-time
- Can pause and resume
- Runs in background if desired
- Low memory usage regardless of count

### Network Operations

Operations on NAS/network drives:
- Slower due to network overhead
- Handles disconnections gracefully
- Retries automatically on timeout
- Shows network-specific status

## Settings Reference

| Setting | Default | Description |
|---------|---------|-------------|
| Default Action | Quarantine | What happens when you click "Remove" |
| Quarantine Folder | C:\Quarantine | Where quarantined files go |
| Quarantine Retention | 30 days | How long to keep quarantined files |
| Confirm Large Operations | 100 files | Ask confirmation above this count |
| Verify After Copy | On | Hash-check copies match originals |
| Log Retention | Forever | How long to keep action log |
| Dry Run by Default | Off | Start in preview mode |
