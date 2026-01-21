# Document Version Tracking

## What It Does

The Document Version Tracking feature maintains a history of changes to your documents over time. Instead of keeping multiple copies of files that change frequently (report_v1.docx, report_v2.docx, report_final.docx, report_final_FINAL.docx), the app tracks changes efficiently using Git's delta compression.

**Key benefits:**
- **Space efficient** - Only stores differences between versions, not full copies
- **Complete history** - See every change, when it happened, and restore any version
- **Duplicate reduction** - Eliminates the need for manual versioning copies
- **Standard format** - Uses Git internally, so you can also access history with Git tools

## How It Works

### Under the Hood

The app uses Git (via libgit2/GitPython) as a storage engine:

1. **Tracked folders** become Git repositories (hidden .git folder)
2. **File changes** are automatically detected and committed
3. **Delta compression** stores only what changed between versions
4. **History** is preserved indefinitely in the .git folder

You never need to interact with Git directly - the app handles everything through its own interface.

### What Gets Tracked

You choose which folders to track. Good candidates:
- Documents you edit frequently
- Project files that evolve over time
- Configuration files
- Notes and writing

The app tracks all files in selected folders that you choose to include.

## Setting Up Version Tracking

### Enabling for a Folder

1. Go to **Settings > Version Tracking**
2. Click **Add Tracked Folder**
3. Browse to select a folder
4. Configure options (see below)
5. Click **Enable Tracking**

```
ADD TRACKED FOLDER

Folder: [\\NAS\Documents\Work           ] [Browse]

TRACKING OPTIONS

Track these file types:
[x] Text files (.txt, .md, .csv)
[x] Documents (.docx, .xlsx, .pptx, .pdf)
[x] Code files (.py, .js, .html, .css, .json)
[ ] All files

Automatic commit:
(•) When file is saved (immediate)
( ) Every [5] minutes
( ) Daily at [midnight]
( ) Manual only

[ ] Include subfolders

[Cancel] [Enable Tracking]
```

Notes:
- Tracking is local-only (stored in a hidden `.git` folder inside the tracked folder).
- Auto-commit defaults to on-save with a short debounce window to avoid noisy history.

### First-Time Setup

When you enable tracking on an existing folder:

1. App creates a hidden .git folder
2. All matching files are added to initial commit
3. This becomes "Version 1" of everything

For large folders, this may take a moment.

## Using Version Tracking

### Viewing File History

Right-click any tracked file and select **View History**:

```
VERSION HISTORY: quarterly_report.docx

VERSION    DATE                 SIZE      CHANGE
--------------------------------------------------------------
v12        2024-03-15 14:32    156 KB    +2.3 KB (Added Q1 summary)
v11        2024-03-14 09:15    154 KB    +1.1 KB (Updated charts)
v10        2024-03-10 16:45    153 KB    -0.5 KB (Removed draft notes)
v9         2024-03-08 11:20    153 KB    +4.2 KB (Added financials)
v8         2024-03-05 14:00    149 KB    +0.8 KB (Formatting)
...

[View Selected] [Restore Selected] [Compare Versions] [Export Version]
```

The Settings panel also provides a quick file picker + **View History** button for ad-hoc lookups.

### Comparing Versions

Select two versions and click **Compare**:

For text files, you see a diff:
```
COMPARE: report.md  v8 → v12

Line 45:
- Revenue increased by 10% in Q4
+ Revenue increased by 15% in Q4, exceeding projections

Line 67-72:
+ ## Q1 2024 Outlook
+
+ Based on current trends, we expect continued growth
+ in the following areas:
+ - Product line expansion
+ - International markets
```

For binary files (Word, Excel), you see:
- Size changes
- Modification dates
- Option to export both versions and compare externally

In the current UI, a lightweight diff preview is shown for text-like files. Binary formats show
“Diff preview not available.”

### Restoring a Previous Version

To go back to an earlier version:

1. View file history
2. Select the version you want
3. Click **Restore**

```
RESTORE VERSION

Restore quarterly_report.docx to version 8?

Current version: v12 (156 KB, 2024-03-15)
Restore to: v8 (149 KB, 2024-03-05)

This will:
- Replace the current file with version 8
- Create a new version (v13) so you can undo if needed
- NOT delete any version history

[Cancel] [Restore]
```

### Viewing All Changes

See all recent changes across all tracked folders:

**Settings > Version Tracking > Recent Changes:**

```
RECENT CHANGES

FOLDER: \\NAS\Documents\Work

Today:
  quarterly_report.docx - v12 (14:32) - Added Q1 summary
  budget_2024.xlsx - v5 (11:15) - Updated projections
  meeting_notes.md - v3 (09:00) - Added action items

Yesterday:
  quarterly_report.docx - v11 (09:15) - Updated charts
  project_plan.docx - v8 (16:30) - Added milestones

This Week:
  ... 23 more changes

[View All] [Search Changes]
```

In the Settings panel, a “Recent Changes” table shows the latest commits across tracked folders.

## Storage and Efficiency

### How Space is Saved

Git's delta compression is very efficient:

**Example: 100 versions of a 1 MB document**

| Storage Method | Space Used |
|----------------|------------|
| 100 separate files | 100 MB |
| Git delta compression | ~5-15 MB |

The savings depend on how much changes between versions. Small edits = huge savings.

### Storage Location

Version history is stored in:
- `.git` folder within each tracked folder
- Hidden by default (Windows hidden folder)
- Can be excluded from other backups if desired

### Viewing Storage Usage

**Settings > Version Tracking > Storage:**

```
VERSION TRACKING STORAGE

Tracked Folders: 3
Total Versions: 1,234
Storage Used: 45.2 MB

BY FOLDER:
  \\NAS\Documents\Work - 28.3 MB (567 versions)
  \\NAS\Documents\Personal - 12.1 MB (423 versions)
  \\NAS\Projects - 4.8 MB (244 versions)

[Optimize Storage] [Clean Old Versions]
```

### Cleaning Old Versions

If storage grows too large:

```
CLEAN OLD VERSIONS

Options:
( ) Keep last [30] days of history
( ) Keep last [50] versions per file
(•) Keep history under [100] MB per folder
( ) Remove history for deleted files only

Preview:
  Versions to remove: 234
  Space to recover: 12.3 MB
  Files affected: 45

[Cancel] [Clean]
```

## Advanced Features

### Manual Commits

If automatic commits are disabled, save versions manually:

1. Right-click file
2. Select **Save Version**
3. Optionally add a note

```
SAVE VERSION

File: quarterly_report.docx

Version note (optional):
[Final version for board meeting    ]

[Cancel] [Save Version]
```

In the Settings panel, **Save Version** is available for any file under a tracked folder.

### Branching (Advanced)

For advanced users, create branches for experimental changes:

1. Right-click folder
2. Select **Create Branch**
3. Name the branch

Work on the branch, then merge back or discard.

*Note: This is optional and hidden by default. Enable in Settings > Advanced.*

### External Git Access

Since tracking uses standard Git:

- View history with `git log`
- Restore with `git checkout`
- Use any Git GUI (GitKraken, SourceTree, etc.)
- Push to remote for backup (GitHub, etc.)

The app's interface is easier, but power users have full Git access.

## What Gets Tracked

### Supported File Types

**Text-based (full diff support):**
- Plain text: .txt, .md, .csv, .json, .xml
- Code: .py, .js, .html, .css, .java, .cpp, etc.
- Config: .ini, .yaml, .toml, .conf

**Binary (stored as whole files):**
- Office: .docx, .xlsx, .pptx
- PDF: .pdf
- Images: .jpg, .png (if enabled)
- Any other file type you include

### Files Automatically Excluded

- Temporary files: ~*, *.tmp, *.bak
- Lock files: ~$*, .~lock.*
- System files: Thumbs.db, .DS_Store
- The .git folder itself

### Custom Exclusions

Add patterns to exclude:

```
EXCLUSION PATTERNS

Patterns to exclude from tracking:

*.log
*.cache
build/*
temp/*

[Add Pattern] [Remove Selected]
```

## Integration with Duplicate Detection

### Versioned Files and Duplicates

Files with version tracking are handled specially:

- **Version history** doesn't count as duplicates
- **Older versions** accessible through history, not separate files
- **Manual version copies** (report_v1.docx) can still be detected

### Consolidating Manual Versions

If you have files like:
```
report_v1.docx
report_v2.docx
report_v3_final.docx
report_v3_final_FINAL.docx
```

The app can:
1. Detect these as related versions
2. Import them into proper version tracking
3. Delete the manual copies (keeping history)

```
CONSOLIDATE VERSIONS

Found potential version series:
  report_v1.docx (2024-01-15)
  report_v2.docx (2024-02-20)
  report_v3_final.docx (2024-03-01)
  report_v3_final_FINAL.docx (2024-03-15)

Consolidate into single tracked file?
- Keep: report.docx (latest version)
- Import history from all 4 files
- Delete original versioned files

[Preview] [Consolidate]
```

## Libraries Used

### GitPython

Python library for Git operations:
- Full Git repository management
- Commit, diff, log operations
- Branch and merge support

### libgit2 / pygit2 (Alternative)

Lower-level Git library:
- Faster for large repositories
- More control over operations
- Used if performance is critical

### Python difflib

For displaying text diffs:
- Line-by-line comparison
- Unified diff format
- HTML diff generation

## Troubleshooting

### "Folder already has .git"

If the folder was previously a Git repo:
- App can use existing history
- Or start fresh (archive old .git first)

### "File too large for tracking"

Very large files (>100 MB) may be excluded:
- Binary files don't compress well
- Consider using Git LFS for large media
- Or exclude large files from tracking

### "History seems incomplete"

If version history is missing:
- Check if automatic commits were enabled
- Check exclusion patterns
- Verify .git folder exists and isn't corrupted

### "Storage growing too fast"

If .git folder is large:
- Run **Optimize Storage** (git gc)
- Clean old versions
- Check for large binary files being tracked

## Settings Reference

| Setting | Default | Description |
|---------|---------|-------------|
| Tracked Folders | None | Folders with version tracking enabled |
| Auto-commit | On save | When to automatically save versions |
| Include Subfolders | Yes | Track files in subfolders |
| File Types | Text + Docs | What file types to track |
| Exclusion Patterns | (defaults) | Files to ignore |
| Max File Size | 50 MB | Skip files larger than this |
| History Retention | Forever | How long to keep old versions |
| Show .git Folders | Hidden | Whether to show .git in file browsers |
