# Multi-Drive Management

## What It Does

The Drive Manager keeps track of all your storage locations - local drives, external drives, and network shares - and helps you understand how your files are distributed across them. Its key features (current implementation):

1. **Drive Registry** - Maintain a list of all your storage locations
2. **Status Monitoring** - Know when drives are connected, disconnected, or having issues
3. **Redundancy Analysis** - Find files that exist on only one drive (at risk)
4. **Cross-Drive Deduplication** - Duplicates are grouped across all drives using content hashes
5. **Backup Suggestions** - Generate and execute a copy plan

## The Drives Tab

### Drive List View

The main Drives tab shows all your registered storage locations:

```
DRIVES                          STATUS        FILES      SPACE         LAST SCAN
---------------------------------------------------------------------------------
[NAS Photos]                    Connected     127,453    892 GB used   2 hours ago
\\LS210D11E\share\Photos                                 108 GB free

[Backup Drive D:]               Connected      89,234    456 GB used   1 day ago
D:\Backup                                                44 GB free

[Old External]                  Disconnected   45,678    --            3 weeks ago
E:\

[Documents Share]               Connected      12,341    234 GB used   5 hours ago
\\LS210D11E\share\Documents                              766 GB free
```

Use **Scan All** to apply the same scan mode across every registered drive, one at a time.

### Drive Status Indicators

Each drive shows its current status:

| Status | Meaning |
|--------|---------|
| **Connected** | Drive is accessible and ready |
| **Disconnected** | Drive is not currently available (unplugged, network down) |
| **Scanning** | Currently being scanned |
| **Error** | Drive has issues (permissions, corruption, etc.) |
| **Needs Scan** | Never scanned or data may be stale |

### Adding a Drive

1. Click **Add Drive**
2. Enter a folder path or UNC path (e.g., `C:\Photos` or `\\NAS\share`)
3. Enter a friendly name (optional)
4. Click **Add**

The drive appears in your list with "Needs Scan" status.

### Removing a Drive

1. Select a drive in the list
2. Click **Remove Selected**
3. Confirm removal

Removing a drive from the list:
- Removes all scan data for that drive from the database
- Does NOT delete any files on the drive itself
- Removes the drive from redundancy analysis

### Editing Drive Settings

Drive properties (rename, change path, primary drive, exclusions) are planned but not implemented yet.

## Redundancy Analysis

### The Problem

If a file exists on only one drive and that drive fails, the file is lost forever. The Redundancy Analysis feature identifies these "at-risk" files.

### Viewing At-Risk Files

Go to **Drives > Redundancy & Backups** and click **Generate Redundancy Report**:

```
REDUNDANCY REPORT
=================

At-Risk Files (single copy only): 23,456 files (156 GB)
Protected Files (multiple copies): 104,231 files (412 GB)

AT-RISK FILES BY DRIVE:

[NAS Photos] - 12,341 at-risk files (89 GB)
  Recent photos from 2024
  Videos/Family

[Backup Drive D:] - 8,234 at-risk files (45 GB)
  Documents/Work
  Projects

[Documents Share] - 2,881 at-risk files (22 GB)
  Archives

[Generate Redundancy Report]  [Build Backup Plan]
```

### Understanding the Report

- **At-Risk Files** - Files that exist on only ONE of your registered drives
- **Protected Files** - Files that exist on TWO OR MORE drives (backed up)

The report breaks down at-risk files by:
- Which drive they're on
- What folders contain the most at-risk data
- Total size of at-risk data

### Viewing Individual At-Risk Files

The Drives panel lists at-risk files directly below the summary:

```
AT-RISK FILES                                    DRIVE           SIZE
-------------------------------------------------------------------------
Photos/2024/January/IMG_0001.jpg                NAS Photos      4.2 MB
Photos/2024/January/IMG_0002.jpg                NAS Photos      3.8 MB
Videos/Family/Birthday_2024.mp4                 NAS Photos      2.1 GB
Documents/Tax_Returns_2024.pdf                  Backup Drive    156 KB
...

Filter/sorting controls are not implemented yet.

The summary totals reflect all hashed files; the list is a capped sample.
```

Use **Build Backup Plan** to preview targets, then **Execute Plan** to copy.

## Cross-Drive Duplicate Consolidation

### The Scenario

You have the same files scattered across multiple drives:
- Original photos on your NAS
- A copy on your external backup drive
- Another copy on your laptop

You want to consolidate: keep ONE copy in your preferred location and free up space on other drives.

### How to Consolidate

1. Go to **Duplicates** tab
2. Use **Scope: Cross-Drive Only** to view groups spanning multiple drives
3. Use existing resolution strategies to keep your preferred copy

### Consolidation Preview

Before removing anything, you'll see a preview:

```
CONSOLIDATION PREVIEW

Keeping files on: NAS Photos
Removing duplicates from: Backup Drive D:, Old External

Files to remove: 34,567
Space to free: 89.2 GB

By drive:
  Backup Drive D: - 23,456 files (67.3 GB)
  Old External   -  11,111 files (21.9 GB)

[Preview Removal List]  [Confirm & Remove]  [Cancel]
```

## Backup Suggestions (Current UI)

### Generating a Backup Plan

The app can suggest what to backup and where:

1. Go to **Drives > Redundancy & Backups**
2. Set a **Backup source** folder
3. Select one or more **Backup targets**
4. Optional: add **Exclude patterns** (temp/build caches)
5. Click **Build Backup Plan**

Use **Analyze Exclusions** to see how much space each exclude pattern would save.
The app also detects common project types (Unity, Unreal, Android/Gradle, Node.js, .NET, Python, CMake) within the source
folder and suggests additional exclude patterns you can review and apply manually.

### The Backup Plan

```
BACKUP PLAN
===========

To achieve full redundancy, copy:

FROM: NAS Photos → TO: Backup Drive D:
  12,341 files (89 GB)
  Mostly: Recent photos (2024), Family videos

FROM: Backup Drive D: → TO: NAS Photos
  3,456 files (12 GB)
  Mostly: Documents, Work files

Total data to copy: 101 GB
Estimated time: ~20 minutes (over gigabit network)

[Execute Plan]
```

### Executing the Backup Plan

Click **Execute Plan** to start copying. The app:
- Copies files in the background
- Verifies copies match originals (hash check)
- Logs the operation in the action log

You can pause or cancel the backup operation from the Drives tab.

You can also export the plan to CSV or open the selected backup target folders.

If a target drive is disconnected, the plan skips it and will sync automatically when it reconnects.

## Drive Health Monitoring

### What's Monitored

The app keeps track of:
- **Connection status** - Is the drive accessible?
- **Free space** - How much room is left?
- **Last scan date** - How fresh is the data?
- **Error history** - Any recent access problems?

### Notifications

Notifications are not implemented yet. Drive status is visible in the Drives list.

### Network Drive Reconnection

If your NAS disconnects:
1. The app pauses any operations on that drive
2. Shows a notification: "NAS Photos is disconnected"
3. Periodically checks if it's back online
4. Automatically resumes operations when reconnected

## Drive Synchronization (Future Feature)

Planned for a future release:
- Two-way sync between drives
- Scheduled automatic syncing
- Conflict resolution for files changed on multiple drives
- Mirror mode (exact copy)

## Technical Details

### Drive Identification

Drives are identified by:
- **Local drive roots**: Volume serial number (survives drive letter changes)
- **Local subfolders**: Volume serial number + folder path
- **Network shares**: UNC path normalized to consistent format
- **Friendly name**: User-assigned label for display

### Path Mapping

Mapped drive letters and UNC paths are currently treated as separate locations. Prefer UNC paths for network shares to avoid duplicates.

### Database Storage

For each drive, the database stores:
- Unique drive identifier
- Friendly name and path
- Total and free space
- Last scan timestamp
- All files discovered on that drive

### Performance Considerations

Operations spanning multiple drives:
- Compare files across drives using cached hashes (fast)
- Copy operations limited by slowest drive's speed
- Network drives will be slower than local SSDs
