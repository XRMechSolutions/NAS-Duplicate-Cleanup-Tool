# Duplicate Resolution

## What It Does

Once duplicates are found, you need to decide which copies to keep and which to remove. The Duplicate Resolution system helps you make these decisions efficiently - either automatically using smart rules, or manually with full control.

## Resolution Strategies

### Keep Newest

Keeps the file with the most recent modification date. Removes older copies.

**Best for:**
- Files that might have been updated over time
- When newer usually means better/more current
- Working documents that evolve

**Example:**
```
report_final.docx (modified 2024-03-15) ← KEEP
report_final.docx (modified 2024-01-10) ← REMOVE
report_final.docx (modified 2023-12-01) ← REMOVE
```

### Keep Oldest

Keeps the file with the oldest modification date. Removes newer copies.

**Best for:**
- Original files you want to preserve
- Photos where the original capture matters
- Avoiding accidentally-modified copies

**Example:**
```
IMG_4521.jpg (created 2020-06-15) ← KEEP (original)
IMG_4521.jpg (created 2022-03-10) ← REMOVE (backup copy)
IMG_4521.jpg (created 2024-01-05) ← REMOVE (another copy)
```

### Keep Largest

Keeps the largest file (by size). Removes smaller copies.

**Best for:**
- Images where larger = higher resolution
- Videos where larger = higher quality
- Avoiding compressed/degraded copies

**Example:**
```
photo.jpg (4032x3024, 4.2 MB) ← KEEP (full resolution)
photo.jpg (1920x1440, 890 KB) ← REMOVE (resized)
photo.jpg (800x600, 156 KB) ← REMOVE (thumbnail)
```

### Keep Best Quality

Uses AI quality scoring to keep the best quality version.

**Best for:**
- Near-duplicates with different quality
- Burst photos where one is sharper
- Photos from different sources

**Example:**
```
IMG_4521.jpg (quality: 9.2) ← KEEP (sharp, well-exposed)
IMG_4522.jpg (quality: 7.8) ← REMOVE (slightly blurry)
IMG_4523.jpg (quality: 6.5) ← REMOVE (underexposed)
```

### Keep on Specific Drive

Keeps copies on your preferred drive, removes from others.

**Best for:**
- Consolidating files to one location
- Cleaning up backup drives
- Organizing by storage type (SSD vs NAS)

**Example:**
```
Preferred drive: NAS Photos

\\NAS\Photos\vacation.jpg ← KEEP (on preferred drive)
D:\Backup\vacation.jpg ← REMOVE
E:\Old\vacation.jpg ← REMOVE
```

### Keep Shortest Path

Keeps the file with the simplest/shortest path. Removes deeply nested copies.

**Best for:**
- Cleaning up organizational mess
- When duplicates are in nested backup folders
- Preferring primary locations over archives

**Example:**
```
\\NAS\Photos\2024\beach.jpg ← KEEP (clean path)
\\NAS\Backup\Old\Archive\2024\Unsorted\beach.jpg ← REMOVE (messy path)
```

### Keep Longest Path (Reverse)

Keeps files in more specific locations, removes from general ones.

**Best for:**
- When organized copies are in detailed folder structures
- Removing dumps in favor of curated collections

### Manual Selection

No automatic rule - you decide each duplicate individually.

**Best for:**
- Important files requiring careful review
- When automatic rules don't fit
- Learning what duplicates you have

## Using Strategies

### Apply to All Duplicates

1. Go to **Duplicates** tab
2. Click **Auto-Select** dropdown
3. Choose a strategy
4. Review the selections
5. Click **Apply**

```
AUTO-SELECT STRATEGY

Choose how to automatically select which files to keep:

( ) Keep Newest
( ) Keep Oldest
(•) Keep Largest
( ) Keep Best Quality
( ) Keep on Drive: [NAS Photos ▼]
( ) Keep Shortest Path
( ) Manual (no auto-selection)

Preview: This will mark 4,567 files for removal
         Estimated space savings: 23.4 GB

[Preview] [Apply] [Cancel]
```

### Apply to Selected Groups

Select specific duplicate groups, then apply a strategy just to them:

1. Check the boxes next to duplicate groups you want to process
2. Click **Auto-Select for Selected**
3. Choose strategy
4. Review and confirm

### Different Strategies for Different Types

You can set default strategies by file type:

**Settings > Resolution > Default Strategies:**

| File Type | Default Strategy |
|-----------|-----------------|
| Images | Keep Largest |
| Videos | Keep Largest |
| Documents | Keep Newest |
| Music | Keep Largest |
| Archives | Keep Oldest |
| Other | Manual |

When you click Auto-Select, it uses the appropriate strategy for each file type.

## Reviewing Selections

### The Selection Preview

Before applying any resolution, you see a preview:

```
RESOLUTION PREVIEW

Strategy: Keep Largest

Groups affected: 2,341
Files to keep: 2,341
Files to remove: 5,678

Space to recover: 34.5 GB

BY FILE TYPE:
  Images: 4,234 files removed (28.9 GB)
  Videos: 1,123 files removed (5.2 GB)
  Documents: 321 files removed (0.4 GB)

[View Full List] [Modify Selections] [Confirm] [Cancel]
```

### Modifying Selections

After auto-selection, you can manually adjust:

1. Click on any duplicate group
2. Change which file is selected to keep
3. Click **Save Changes**

Your manual overrides are preserved even if you re-run auto-select.

### Reviewing Individual Groups

Click **View Full List** to see every duplicate group and its selection:

```
SELECTED FOR RESOLUTION

[Search: _______________] [Filter: All ▼]

Group 1: vacation.jpg (3 copies, keeping 1)
  [x] \\NAS\Photos\vacation.jpg (4.2 MB) ← KEEPING
  [ ] D:\Backup\vacation.jpg (4.2 MB) ← REMOVING
  [ ] E:\Archive\vacation.jpg (4.2 MB) ← REMOVING

Group 2: document.pdf (2 copies, keeping 1)
  [x] \\NAS\Documents\document.pdf (156 KB, newest) ← KEEPING
  [ ] D:\Backup\document.pdf (156 KB, older) ← REMOVING

[< Previous] Page 1 of 234 [Next >]
```

### Conflict Warnings

The app warns you about potentially problematic selections:

```
WARNING: Potential Issues Detected

- 23 files would be removed from all drives (no copy kept)
  → These are marked as "keep" somewhere, please verify

- 12 files on disconnected drives selected for removal
  → Cannot verify these files exist; wait for drive or skip

[Review Warnings] [Ignore and Continue]
```

## Combining Strategies

### Priority Rules

Set up multiple rules in priority order:

```
RESOLUTION RULES (in order)

1. [x] If exists on NAS Photos, keep that copy
2. [x] Otherwise, keep largest file
3. [x] Otherwise, keep newest file
4. [ ] Fallback: keep first found

[Add Rule] [Edit] [Remove] [Save]
```

Rules are applied in order until one matches.

### Example Combined Strategy

"Keep the NAS copy if it exists, otherwise keep the best quality"

1. Check if file exists on NAS Photos
2. If yes: keep NAS copy
3. If no: use quality score to pick best

## Smart Recommendations

### AI-Powered Suggestions

For image duplicates, the app provides intelligent recommendations:

```
DUPLICATE GROUP: beach_sunset.jpg

Files: 3 copies

AI RECOMMENDATION: Keep file #1

Reasons:
- Highest resolution (4032x3024 vs 1920x1080 vs 800x600)
- Best quality score (9.1 vs 8.2 vs 7.4)
- Most complete metadata (EXIF, GPS, camera info)
- On primary drive (NAS Photos)

[Accept Recommendation] [Choose Different]
```

### Recommendation Factors

The AI considers:
1. **Resolution** - Higher is better
2. **Quality score** - Sharpness, exposure
3. **Metadata completeness** - EXIF, GPS, etc.
4. **File format** - Original formats over re-encoded
5. **Path quality** - Organized locations over dumps
6. **Drive preference** - User's preferred storage

## Exclusions and Locks

### Locking Files

Lock files to prevent them from being selected for removal:

1. Right-click a file
2. Select **Lock (Never Delete)**
3. File shows a lock icon
4. Won't be selected by any auto-strategy

### Ignoring Duplicate Groups

Mark intentional duplicates to hide them:

1. Right-click a duplicate group
2. Select **Ignore (Intentional Duplicates)**
3. Group is hidden from duplicate lists
4. Files are not suggested for removal

**Use cases:**
- Intentional backups you want to keep
- Same photo in different albums
- Working copies alongside originals

### Viewing Ignored/Locked Items

**Settings > Resolution > Manage Exclusions:**

```
LOCKED FILES: 45

\\NAS\Photos\Important\wedding.jpg
\\NAS\Photos\Important\baby_first_steps.jpg
...

[Unlock Selected] [Unlock All]

IGNORED GROUPS: 12

Group: family_photo.jpg (3 copies) - Reason: "Intentional backup"
Group: logo.png (5 copies) - Reason: "Used in multiple projects"
...

[Unignore Selected] [Unignore All]
```

## Batch Operations

### Processing Large Numbers

When you have thousands of duplicate groups:

1. **Filter first** - Narrow down by type, size, drive
2. **Auto-select** - Apply strategy to filtered results
3. **Spot check** - Review a sample of selections
4. **Process in batches** - Apply to 500 at a time

### Progress Tracking

```
APPLYING RESOLUTION

Processing: 2,341 duplicate groups

Completed: 1,456
Files marked for removal: 3,234
Current group: beach_2019/...

[=====================>           ] 62%

[Pause] [Cancel]
```

## After Resolution

### What Happens Next

After you confirm resolutions, files are marked for removal but NOT immediately deleted. You then:

1. Go to **Action Log > Pending Actions**
2. Review the pending removals
3. Choose action: Delete, Quarantine, or Trash
4. Execute the action

This two-step process prevents accidents.

### Reverting Selections

Before executing actions, you can revert:

1. Go to **Duplicates** tab
2. Click **Clear All Selections**
3. Start fresh with a different strategy

### History

All resolution decisions are logged:

```
RESOLUTION HISTORY

2024-03-15 14:32 - Applied "Keep Largest" to 2,341 groups
2024-03-14 10:15 - Manually resolved 23 groups
2024-03-10 09:00 - Applied "Keep on NAS" to 567 groups

[View Details] [Undo] [Export]
```
