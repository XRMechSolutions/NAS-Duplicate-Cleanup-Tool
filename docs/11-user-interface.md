# User Interface Guide

## Overview

The app uses a modern desktop interface built with Dear PyGui, providing GPU-accelerated performance for smooth image browsing even with large collections.

## Main Window Layout

```
+------------------------------------------------------------------+
|  NAS Duplicate Cleanup Tool                          [_] [□] [X] |
+------------------------------------------------------------------+
|  [Drives] [Duplicates] [Photos] [Faces] [Search] [Settings]      |
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
| **Photos** | Photo organizer - sort unorganized photos into folders |
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
[Duplicates] [Photos] [Faces 🔄] [Search]
                        ↑
              (status bar updates during long operations like scan, hash, photo organization, backup)
```

## Tooltips

Tooltips provide contextual help when hovering over UI elements. They explain what buttons, checkboxes, and input fields do without cluttering the interface.

### Using Tooltips

Hover over any UI element to see its tooltip. Tooltips appear after a brief delay and contain:
- Brief description of the feature
- What happens when you click/change it
- Tips for when to use the feature

### Implementation (for developers)

Tooltips use the `duplicleaner.ui.tooltips` module:

```python
from duplicleaner.ui.tooltips import add_tooltip, DRIVE_TOOLTIPS

# After creating a widget:
btn = dpg.add_button(label="Quick Scan", callback=...)
add_tooltip(btn, DRIVE_TOOLTIPS["quick_scan"])

# Or with custom text:
add_tooltip(some_widget, "Custom tooltip explaining this feature.")
```

**Adding tooltips to a new panel:**

1. Import the tooltip module
2. Define tooltip text in `tooltips.py` (e.g., `MY_PANEL_TOOLTIPS` dict)
3. Call `add_tooltip(widget, text)` after creating each widget

**Tooltip text guidelines:**
- First line: What the feature does
- Additional lines: When/why to use it
- Keep under 4 lines total
- Use `\n` for line breaks in the dict values

**Available tooltip dictionaries:**
- `DRIVE_TOOLTIPS` - Drives panel
- `DUPLICATE_TOOLTIPS` - Duplicates panel
- `FACE_TOOLTIPS` - Faces panel (placeholder)
- `ORGANIZE_TOOLTIPS` - Photo Organizer panel (Photos tab)

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
|   [Disconnected] | [Quick Scan] [Deep Scan] [Full Analysis] [Scan All...] |
|                  |                                        |
| [+ Add Drive]    | [Remove Selected] [Hash Now] [Resume Scan] |
|                  | REDUNDANCY & BACKUPS                   |
|                  | - Generate redundancy report           |
| SUMMARY          | - At-risk files listed below           |
| Files: 234,567   | - Source + targets + exclude patterns  |
| Drives: 4        | - Build + execute backup plan          |
|                  | - Analyze exclusions                   |
| Drives: 4        |                                        |
+------------------+----------------------------------------+
```

When a scan is paused or interrupted, a **Resume Scan** button appears in the Drives tab for that drive.

The Redundancy & Backups section includes project-type detection; it lists detected projects and suggests exclude patterns you can optionally apply.

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

### Photos Tab (Photo Organizer)

The Photos tab helps you organize unstructured photo collections (phone dumps, unsorted folders) into well-organized date/location-based folder structures using EXIF metadata.

```
+------------------+----------------------------------------+
| PHOTO ORGANIZER  | PREVIEW                                |
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
|                  | [Preview] [Dry Run] [Organize Now]     |
+------------------+----------------------------------------+
```

**Key Features:**
- Date-based folder organization (YYYY/MM, YYYY/MM-Month, YYYY/MM/DD)
- Location grouping using GPS data from photos
- Event clustering by time proximity
- Smart file renaming with patterns
- Screenshot, burst photo, and Live Photo handling
- Dry-run mode for safe preview before execution

### Faces Tab

The Faces tab provides two views: Unknown Clusters (faces waiting to be identified) and Named People (your identified contacts with photo browsing).

**Named People View:**
```
+------------------------------------------------------------------------+
| Faces & Pets                                                            |
+------------------------------------------------------------------------+
| [Run Face Analysis] [Run Pet Analysis] [Cluster Faces] [Refresh]       |
|                                                                         |
| View: ( ) Unknown Clusters  (x) Named People                           |
|                                                                         |
| Search: [Filter by name...] [Clear]    [ ] Show Hidden (0)             |
+------------------------------------------------------------------------+
| NAME        | PHOTOS | AGE RANGE | ACTIONS                              |
|-------------|--------|-----------|--------------------------------------|
| Emma        | 456    | ~9 years  | [Photos][Timeline][Find More][Edit][Delete] |
| Dad         | 234    | -         | [Photos][Timeline][Find More][Edit][Delete] |
| Mom         | 198    | -         | [Photos][Timeline][Find More][Edit][Delete] |
+------------------------------------------------------------------------+
```

**Photo Gallery Dialog** (opened via "Photos" button):
```
+------------------------------------------------------------------------+
| Photo Gallery                                                       [X] |
+------------------------------------------------------------------------+
| Photos of Emma                                                          |
| 456 photos | Age ~9 | Born ~2015                                       |
+------------------------------------------------------------------------+
| Sort by: [Date (Newest) v]    [Select All] [Open Selected]             |
+------------------------------------------------------------------------+
| +-------+ +-------+ +-------+ +-------+ +-------+ +-------+            |
| | thumb | | thumb | | thumb | | thumb | | thumb | | thumb |            |
| +-------+ +-------+ +-------+ +-------+ +-------+ +-------+            |
| IMG_001   IMG_002   IMG_003   IMG_004   IMG_005   IMG_006              |
| 2024-03   2024-03   2024-02   2024-02   2024-01   2024-01              |
|                                                                         |
| (scrollable grid of photos...)                                          |
+------------------------------------------------------------------------+
| [Find More Photos] [View Timeline]                          [Close]     |
+------------------------------------------------------------------------+
```

**Timeline Dialog** (shows photos organized by year with thumbnails):
```
+------------------------------------------------------------------------+
| Timeline: Emma                                                      [X] |
+------------------------------------------------------------------------+
| 2024 (Age ~9) - 45 photos                                              |
| ----------------------------------------------------------------       |
| +---+ +---+ +---+ +---+ +---+ +---+ +---+ +---+                        |
| |   | |   | |   | |   | |   | |   | |   | |   |                        |
| +---+ +---+ +---+ +---+ +---+ +---+ +---+ +---+                        |
|   +21 more photos                                                       |
|                                                                         |
| 2023 (Age ~8) - 67 photos                                              |
| ----------------------------------------------------------------       |
| +---+ +---+ +---+ +---+ +---+ +---+ +---+ +---+                        |
| |   | |   | |   | |   | |   | |   | |   | |   |                        |
| +---+ +---+ +---+ +---+ +---+ +---+ +---+ +---+                        |
+------------------------------------------------------------------------+
| [Close] [Find More Photos]                                              |
+------------------------------------------------------------------------+
```

**Photo Preview Dialog** (click any photo in gallery or timeline):
```
+------------------------------------------------------------------------+
| Photo Preview                                                       [X] |
+------------------------------------------------------------------------+
| IMG_4521.jpg | 4.2 MB | 2024-03-15 14:32                              |
+------------------------------------------------------------------------+
|                                                                         |
|              +----------------------------------+                        |
|              |                                  |                        |
|              |         (Large Preview)          |                        |
|              |                                  |                        |
|              +----------------------------------+                        |
|                                                                         |
| Path: C:\Photos\2024\03\IMG_4521.jpg                                   |
+------------------------------------------------------------------------+
| [Open File] [Show in Explorer] [Remove from Person]          [Close]    |
+------------------------------------------------------------------------+
```

**Actions:**
- **Photos**: Browse all photos of a person in a scrollable gallery
- **Timeline**: View photos grouped by year with age tracking
- **Find More**: Search for additional photos using face recognition
- **Edit**: Change name or birth year
- **Delete**: Remove person (their faces return to Unknown Clusters)

### Search Tab

The Search tab provides powerful file discovery using AI-powered semantic search and text-based search.

```
+------------------------------------------------------------------------+
| SEMANTIC SEARCH                                                         |
+------------------------------------------------------------------------+
| [Search photos, scenes, or text...                    ] [Search] [Clear]|
|                                                                         |
| [x] Semantic (CLIP)  [x] Text (summaries/OCR/tags)  Limit: [200]       |
|                                                      Sort: [Relevance v]|
|                                                                         |
| Type: [All v]  Date: [From______] [To________]  Person: [Name______]   |
|                                                                         |
| Found 234 result(s).                    [Select All] [Select None]      |
+------------------------------------------------------------------------+
| RESULTS (scrollable cards with thumbnails)                              |
|                                                                         |
| +--------------------------------------------------------------------+ |
| | [x] +-------+ vacation_001.jpg                [Preview][Open][Expl]| |
| |     | thumb | 4.2 MB  |  2024-03-15 14:32                          | |
| |     +-------+ Source: semantic  |  Score: 0.943                    | |
| |               beach (0.89), sunset (0.82), travel (0.71)           | |
| +--------------------------------------------------------------------+ |
|                                                                         |
| +--------------------------------------------------------------------+ |
| | [ ] +-------+ IMG_5234.jpg                    [Preview][Open][Expl]| |
| |     | thumb | 3.8 MB  |  2024-03-14 10:15                          | |
| |     +-------+ Source: semantic+tags  |  Score: 0.891               | |
| |               ocean (0.85), sunny (0.79)                           | |
| +--------------------------------------------------------------------+ |
+------------------------------------------------------------------------+
```

**Search Modes:**
- **Semantic (CLIP)**: AI-powered search using natural language. Finds images matching queries like "dog playing in snow" or "birthday party with cake".
- **Text Search**: Searches AI-generated summaries, OCR text from documents/screenshots, and user-assigned tags.

**Filters:**
- **Type**: All, Images, Videos, Documents, Other
- **Date Range**: From/To dates (YYYY-MM-DD format, flexible parsing)
- **Person**: Filter by people detected in photos (partial name match)

**Sorting Options:**
- **Relevance**: Semantic matches first by similarity score, then text matches
- **Date (Newest/Oldest)**: By file modification date
- **Size (Largest/Smallest)**: By file size
- **Name**: Alphabetical by filename

**Result Cards:**
Each result displays:
- Selection checkbox for batch operations
- Thumbnail preview (for images) or file type indicator
- Filename (clickable to open preview dialog)
- File size and modification date
- Search source (semantic, tags, summary, ocr)
- Similarity score (for semantic matches)
- Top AI-detected categories

**Actions:**
- **Preview**: Opens a detailed preview dialog with larger image and full metadata
- **Open**: Opens the file with its default application
- **Explorer**: Opens Windows Explorer with the file selected

**Preview Dialog:**
- Large image preview (500px max)
- Full file path and metadata
- Open and Explorer buttons
- Works for non-image files too (shows file info without preview)

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
