# User Interface Guide

## Overview

The app uses a modern desktop interface built with Dear PyGui, providing GPU-accelerated performance for smooth image browsing even with large collections.

## Main Window Layout

```
+------------------------------------------------------------------+
|  NAS Duplicate Cleanup Tool                          [_] [□] [X] |
+------------------------------------------------------------------+
|  [Drives] [Duplicates] [Organize] [Faces] [Search] [Settings]    |
+------------------------------------------------------------------+
|                                                                   |
|  +------------------+  +--------------------------------------+   |
|  |                  |  |                                      |   |
|  |   Left Panel     |  |         Main Content Area            |   |
|  |                  |  |                                      |   |
|  |   - Filters      |  |   (changes based on selected tab)    |   |
|  |   - Navigation   |  |                                      |   |
|  |   - Quick Stats  |  |                                      |   |
|  |                  |  |                                      |   |
|  +------------------+  +--------------------------------------+   |
|                                                                   |
+------------------------------------------------------------------+
|  Status: Ready | Files: 127,453 | Space: 892 GB | GPU: Active    |
+------------------------------------------------------------------+
```

### Top Navigation Bar

Six main tabs for different features:

| Tab | Purpose |
|-----|---------|
| **Drives** | Manage storage locations, start scans |
| **Duplicates** | View and resolve duplicate files |
| **Organize** | Photo organization tools |
| **Faces** | Face recognition and people management |
| **Search** | Find files by content, text, or metadata |
| **Settings** | Configure app behavior |

### Left Panel

Context-sensitive sidebar that changes based on active tab:

- **Filters** - Narrow down displayed items
- **Navigation** - Jump to sections
- **Quick Stats** - Summary of current view
- **Actions** - Common operations

### Main Content Area

Primary workspace showing:
- File/photo grids
- Detail views
- Lists and tables
- Preview panels

### Status Bar

Always-visible information:
- Current operation status
- Total file count
- Storage usage
- GPU status (active/inactive)
- Background task indicators

## Common UI Elements

### Image Grid

Used throughout the app for displaying photos:

```
+-------+ +-------+ +-------+ +-------+
|       | |       | |       | |       |
| [img] | | [img] | | [img] | | [img] |
|       | |       | |       | |       |
+-------+ +-------+ +-------+ +-------+
filename  filename  filename  filename
4.2 MB    3.8 MB    2.1 MB    5.6 MB
```

**Interactions:**
- Click - Select image
- Double-click - Open detail view
- Right-click - Context menu
- Ctrl+Click - Multi-select
- Shift+Click - Range select
- Scroll - Navigate grid
- Pinch/scroll zoom - Adjust thumbnail size

### File List View

Alternative to grid for detailed information:

```
NAME                    SIZE     DATE        PATH
-----------------------------------------------------------------------------
vacation_001.jpg        4.2 MB   2024-03-15  \\NAS\Photos\2024\...
vacation_002.jpg        3.8 MB   2024-03-15  \\NAS\Photos\2024\...
document.pdf            156 KB   2024-03-10  \\NAS\Documents\...
```

**Column sorting:** Click headers to sort
**Column resize:** Drag header borders
**Column visibility:** Right-click header

### Preview Panel

Shows larger preview of selected item:

```
+--------------------------------+
|                                |
|         [Large Preview]        |
|                                |
+--------------------------------+
| Filename: vacation_001.jpg     |
| Size: 4.2 MB (4032x3024)       |
| Date: March 15, 2024           |
| Location: New York, NY         |
| Camera: iPhone 15 Pro          |
| Faces: Emma, Dad               |
| Scene: Beach, Travel           |
+--------------------------------+
```

### Progress Indicators

For long-running operations:

**Progress Bar:**
```
Scanning files...
[===================>            ] 67%
45,234 / 67,543 files
```

**Spinner:**
```
Loading... [⠋]
```

**Background Task Badge:**
```
[Duplicates] [Organize] [Faces 🔄] [Search]
                         ↑
              (status bar updates during long operations like scan, hash, organize, backup)
```

## Tab-Specific Interfaces

### First-Run Setup Wizard

On first launch, a guided setup wizard appears:

```
Welcome to DupliCleaner

Step 1: Add a drive or folder to scan
  Path: [C:\Photos] [Add]
  Label (optional)
  Registered Drives: [ ... ]

Step 2: AI Settings
  [x] Enable AI features
  [x] Use GPU acceleration

Step 3: Download AI Models (optional)
  [x] Face recognition (InsightFace)
  [x] Scene search (CLIP)
  [x] Object detection (YOLO)
  [x] OCR (EasyOCR)

Step 4: Setup Complete
  You're ready to start scanning.
```

Model downloads run in the background and are stored in the app's models directory.

### Drives Tab

```
+------------------+----------------------------------------+
| DRIVES           | DRIVE DETAILS                          |
|                  |                                        |
| > NAS Photos     | Name: NAS Photos                       |
|   [Connected]    | Path: \\LS210D11E\share\Photos        |
|                  | Status: Connected                      |
| > Backup Drive   | Files: 127,453                        |
|   [Connected]    | Size: 892 GB used, 108 GB free        |
|                  | Last scan: 2 hours ago                |
| > Old External   |                                        |
|   [Disconnected] | [Scan] [Quick Scan] [Full Analysis]   |
|                  |                                        |
| [+ Add Drive]    | REDUNDANCY & BACKUPS                   |
|                  | - Generate redundancy report           |
| SUMMARY          | - At-risk files listed below           |
| Files: 234,567   | - Source + targets + exclude patterns  |
| Drives: 4        | - Build + execute backup plan          |
|                  | - Analyze exclusions                   |
| Drives: 4        |                                        |
+------------------+----------------------------------------+
```

When a scan is paused or interrupted, a **Resume Scan** button appears in the Drives tab for that drive.

### Log Tab

```
STATUS LOG

[12:01:04] [INFO] Scanning NAS Photos (full)
[12:03:22] [INFO] Hashing complete
[12:04:05] [INFO] Redundancy report ready
[12:05:11] [INFO] Backup plan complete
[12:06:02] [WARN] No image files to analyze
[12:06:30] [ERROR] Search failed
```

The log supports filtering by level and exporting to a text file.

### Duplicates Tab

```
+------------------+----------------------------------------+
| FILTERS          | DUPLICATE GROUPS                       |
|                  |                                        |
| Type:            | [Group 1] vacation.jpg - 3 copies      |
| [x] Exact        | +---+ +---+ +---+                      |
| [x] Near-Image   | |   | |   | |   |  4.2 MB each        |
| [ ] Near-Video   | +---+ +---+ +---+  Total: 12.6 MB     |
|                  | [Select to Keep...]                    |
| Scope:           |----------------------------------------|
| [All Groups ▼]   | [Group 2] photo.png - 2 copies         |
| Drive:           |                                        |
| [All Drives ▼]   |                                        |
|                  | +---+ +---+                            |
| Size:            | |   | |   |     4.2 MB + 890 KB       |
| Min: [____] MB   | +---+ +---+     Total: 5.1 MB         |
|                  | [Select to Keep...]                    |
| QUICK ACTIONS    |----------------------------------------|
| [Auto-Select ▼]  | Showing 50 of 2,341 groups            |
| [Apply]          |                                        |
|                  | Space recoverable: 45.2 GB             |
+------------------+----------------------------------------+
```

### Organize Tab

```
+------------------+----------------------------------------+
| ORGANIZE         | PREVIEW                                |
|                  |                                        |
| Source:          | 2024/                                  |
| [\\NAS\Unsorted] |   01-January/                          |
| [Browse]         |     2024-01-15_NewYork/ (234 photos)  |
|                  |     2024-01-22/ (45 photos)           |
| Destination:     |   02-February/                         |
| [\\NAS\Sorted  ] |     2024-02-14_Valentine/ (67 photos) |
| [Browse]         |   ...                                  |
|                  |                                        |
| OPTIONS          | FILES TO ORGANIZE                      |
| Format:          | +---+ +---+ +---+ +---+                |
| [YYYY/MM     ▼]  | |   | |   | |   | |   | ...          |
|                  | +---+ +---+ +---+ +---+                |
| [x] By Location  | IMG_4521.jpg → 2024/01/NewYork/001.jpg|
| [x] Smart Rename |                                        |
| [ ] Separate     | Ready to organize: 45,234 files        |
|     Screenshots  |                                        |
|                  | [Preview] [Dry Run] [Organize]         |
+------------------+----------------------------------------+
```

### Faces Tab

```
+------------------+----------------------------------------+
| PEOPLE           | EMMA - 456 PHOTOS                      |
|                  |                                        |
| > Emma (456)     | AGE TIMELINE                           |
| > Dad (234)      | 2015  2017  2019  2021  2023  2024    |
| > Mom (198)      | |-----|-----|-----|-----|-----|       |
| > Jake (145)     |                                        |
| > Grandma (167)  | +---+ +---+ +---+ +---+ +---+ +---+   |
|                  | |   | |   | |   | |   | |   | |   |   |
| Unknown Clusters | +---+ +---+ +---+ +---+ +---+ +---+   |
| > Cluster 1 (89) |  0yr   2yr   4yr   6yr   8yr   9yr   |
| > Cluster 2 (67) |                                        |
| > Cluster 3 (45) | [View All] [Find More] [Edit Person]  |
|                  |                                        |
| [Analyze Photos] | RECENT ADDITIONS                       |
| [Merge People]   | +---+ +---+ +---+                      |
|                  | | ? | | ? | | ? |  3 faces to review  |
+------------------+----------------------------------------+
```

### Search Tab

```
+------------------+----------------------------------------+
| SEARCH           | RESULTS                                |
|                  |                                        |
| Query:           | "sunset beach vacation"                |
| [sunset beach   ]| 234 results                            |
| [vacation       ]|                                        |
| [Search]         | +---+ +---+ +---+ +---+ +---+          |
|                  | |   | |   | |   | |   | |   |          |
| FILTERS          | +---+ +---+ +---+ +---+ +---+          |
|                  | 94%   91%   89%   87%   85%            |
| Date Range:      |                                        |
| [Any        ▼]   | +---+ +---+ +---+ +---+ +---+          |
|                  | |   | |   | |   | |   | |   |          |
| Person:          | +---+ +---+ +---+ +---+ +---+          |
| [Any Person ▼]   | 82%   80%   78%   76%   74%            |
|                  |                                        |
| File Type:       | Showing 50 of 234 matches              |
| [Images Only ▼]  |                                        |
|                  | [Load More Results]                    |
| SAVED SEARCHES   |                                        |
| - Beach vacations|                                        |
| - Kids activities|                                        |
+------------------+----------------------------------------+
```

## Keyboard Shortcuts

### Global Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+1` through `Ctrl+6` | Switch to tab 1-6 |
| `Ctrl+F` | Focus search box |
| `Ctrl+S` | Save current selections |
| `Ctrl+Z` | Undo last action |
| `Ctrl+Shift+Z` | Redo |
| `F5` | Refresh current view |
| `Escape` | Cancel current operation / Close dialog |
| `F1` | Help |

### Navigation Shortcuts

| Shortcut | Action |
|----------|--------|
| `Arrow keys` | Move selection |
| `Home` / `End` | Jump to first / last item |
| `Page Up` / `Page Down` | Scroll by page |
| `Enter` | Open selected item |
| `Space` | Toggle selection / Play video |
| `Backspace` | Go back |

### Selection Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+A` | Select all |
| `Ctrl+D` | Deselect all |
| `Ctrl+Click` | Toggle individual selection |
| `Shift+Click` | Range selection |
| `Ctrl+Shift+Click` | Add range to selection |

### Image View Shortcuts

| Shortcut | Action |
|----------|--------|
| `+` / `-` | Zoom in / out |
| `0` | Reset zoom |
| `F` | Fit to window |
| `R` | Rotate right |
| `L` | Rotate left |
| `I` | Show/hide info panel |

### Duplicates Shortcuts

| Shortcut | Action |
|----------|--------|
| `K` | Mark selected to keep |
| `Delete` | Mark selected for removal |
| `N` | Next duplicate group |
| `P` | Previous duplicate group |
| `A` | Apply auto-select strategy |

## Context Menus

### File Context Menu

Right-click any file:

```
+------------------------+
| Open                   |
| Open Location          |
+------------------------+
| Copy Path              |
| Copy File              |
+------------------------+
| Mark as Keep           |
| Mark for Removal       |
| Lock (Never Delete)    |
+------------------------+
| View Details           |
| Find Similar           |
| Find in Duplicates     |
+------------------------+
| Properties             |
+------------------------+
```

### Person Context Menu

Right-click a person in Faces:

```
+------------------------+
| View All Photos        |
| View Timeline          |
+------------------------+
| Find More Photos       |
| Add Photos Manually    |
+------------------------+
| Rename Person          |
| Merge with Another     |
| Split Person           |
+------------------------+
| Export Photos          |
| Delete Person          |
+------------------------+
```

### Duplicate Group Context Menu

Right-click a duplicate group:

```
+------------------------+
| Preview All            |
| Compare Side by Side   |
+------------------------+
| Auto-Select Best       |
| Keep Newest            |
| Keep Largest           |
| Keep on [Drive]    >   |
+------------------------+
| Ignore This Group      |
| Not Really Duplicates  |
+------------------------+
| Process Now            |
+------------------------+
```

## Dialogs

### Confirmation Dialogs

For important actions:

```
+----------------------------------------+
|  Delete 234 files?                     |
|                                        |
|  This will permanently delete the      |
|  selected files.                       |
|                                        |
|  Space to recover: 1.2 GB              |
|                                        |
|  [ ] Don't ask again for this session  |
|                                        |
|  [Cancel]              [Delete]        |
+----------------------------------------+
```

### Progress Dialogs

For long operations:

```
+----------------------------------------+
|  Scanning Files                        |
|                                        |
|  [========================>     ] 78%  |
|                                        |
|  Files scanned: 45,234                 |
|  Current: Photos/2024/vacation/...     |
|  Time remaining: ~2 minutes            |
|                                        |
|  [Run in Background]    [Cancel]       |
+----------------------------------------+
```

### Settings Dialogs

For configuration:

```

AI Models are managed from Settings with per-model status, download buttons, a verify action, and the install command for AI dependencies.

Scan Optimization settings let you tune near-duplicate checks, max file size, and video processing.
+----------------------------------------+
|  Scan Settings                     [X] |
+----------------------------------------+
|  Ignore Patterns                       |
|  +----------------------------------+  |
|  | $RECYCLE.BIN                 [x] |  |
|  | System Volume Information    [x] |  |
|  | node_modules                 [x] |  |
|  | .git                         [x] |  |
|  | *.tmp                        [x] |  |
|  +----------------------------------+  |
|  [Add Pattern]                         |
|                                        |
|  [ ] Follow symbolic links             |
|  [ ] Scan hidden files                 |
|                                        |
|  [Cancel]       [Apply]     [OK]       |
+----------------------------------------+
```

## Themes and Appearance

### Theme Options

**Settings > Appearance > Theme:**

- **Dark** (default) - Easy on eyes, good for long sessions
- **Light** - Brighter, traditional appearance
- **System** - Match Windows theme

### Thumbnail Size

**Settings > Appearance > Thumbnails:**

- Small (100px) - See more at once
- Medium (150px) - Balanced
- Large (200px) - Better preview
- Extra Large (300px) - Maximum detail

Or use mouse scroll wheel while holding Ctrl.

### Font Size

**Settings > Appearance > Font Size:**

- Small - Compact interface
- Medium (default)
- Large - Better readability
- Extra Large - Accessibility

### Panel Layout

Customize the interface:

- **Left panel width** - Drag border to resize
- **Preview panel** - Bottom, right, or hidden
- **Status bar** - Show/hide

## Notifications

### In-App Notifications

Appear in bottom-right corner:

```
+--------------------------------+
| ✓ Scan complete                |
|   127,453 files indexed        |
|   Found 234 new duplicates     |
|                   [Dismiss]    |
+--------------------------------+
```

### System Notifications

When app is in background:
- Scan completed
- Large operation finished
- Error occurred
- Drive disconnected

Configure in **Settings > Notifications**.

## Performance Tips

### For Large Collections

- **Use list view** instead of grid for faster scrolling
- **Apply filters** to reduce displayed items
- **Process in batches** rather than all at once
- **Use SSD** for database storage

### For Smooth Image Browsing

- **GPU acceleration** should show "Active" in status bar
- **Reduce thumbnail size** if scrolling is choppy
- **Clear thumbnail cache** if using too much disk space

### Background Operations

- Long operations can run in background
- Status shown in status bar
- Can continue using other features
- Notification when complete
