# Photo Organization

## What It Does

The Photo Organization feature transforms chaotic dumps of photos and videos into a clean, browsable folder structure. Instead of thousands of IMG_0001.jpg files scattered everywhere, you get organized folders by date, location, and event.

Common scenarios it solves:
- Phone dumps with no organization
- Years of photos with inconsistent naming
- Multiple cameras mixing their numbering schemes
- Photos from family members' devices all merged together

## The Photos Tab (Photo Organizer)

### Main Interface

The Photos tab (Photo Organizer) shows your unorganized media and previews how it will be sorted:

```
PHOTO ORGANIZER
===============

Source: [\\NAS\Photos\Unsorted          ] [Browse]
Destination: [\\NAS\Photos\Organized    ] [Browse]

Unorganized files found: 45,234 images, 2,341 videos

ORGANIZATION PREVIEW
--------------------
2024/
  01-January/
    2024-01-15_NewYork/           (234 photos)
    2024-01-22/                   (45 photos)
  02-February/
    2024-02-14_Valentine/         (67 photos)
    ...
2023/
  12-December/
    2023-12-25_Christmas/         (456 photos)
    ...

[Settings]  [Preview]  [Organize Now]
```

## Organization Options

### Date-Based Sorting

The foundation of organization - put photos in folders by when they were taken.

**Date Source Priority:**
1. EXIF DateTimeOriginal (most reliable - actual capture time)
2. EXIF DateTimeDigitized (when digitized, usually same as original)
3. File creation date (less reliable but usable fallback)
4. File modification date (last resort)

**Folder Format Options:**

| Format | Example | Best For |
|--------|---------|----------|
| `YYYY/MM` | 2024/01/ | Large collections, quick browsing |
| `YYYY/MM-Month` | 2024/01-January/ | Easy to read month names |
| `YYYY/MM/DD` | 2024/01/15/ | Very detailed, daily organization |
| `YYYY/YYYY-MM-DD` | 2024/2024-01-15/ | Sortable, detailed |

Configure in **Settings > Organization > Date Format**.

### Location-Based Sorting

Add location names to folders based on where photos were taken.

**How It Works:**
1. Read GPS coordinates from photo EXIF data
2. Look up the location name (reverse geocoding)
3. Add city/country to folder names

**Example:**
```
2024/
  01-January/
    2024-01-15_NewYork/
    2024-01-22_Boston/
  02-February/
    2024-02-10_Paris_France/
```

**Location Detail Options:**
- **City Only**: "NewYork"
- **City + Country**: "NewYork_USA"
- **City + State + Country**: "NewYork_NY_USA"

Configure with the **Location Detail** dropdown in the Photo Organizer settings.

**Note:** Location lookup requires internet connection. Results are cached locally so each location is only looked up once.

### Event Clustering

Automatically group photos taken around the same time into events.

**How It Works:**
1. Sort photos by capture time
2. When there's a gap longer than the threshold (default: 4 hours), start a new event
3. Photos within the gap are grouped as one event

**Example:**
```
You take 50 photos between 2pm and 4pm -> one event
You don't take photos for 6 hours
You take 30 photos between 10pm and 11pm -> separate event
```

**Event Naming:**
- With location: "2024-01-15_NewYork"
- Without location: "2024-01-15_Event1", "2024-01-15_Event2"

**Configure the time gap** in **Settings > Organization > Event Gap** (1-48 hours).

### File Renaming

Transform cryptic camera names into meaningful filenames.

**Before:**
```
IMG_4521.jpg
DSC_0001.jpg
20240115_143022.jpg
```

**After:**
```
2024-01-15_NewYork_001.jpg
2024-01-15_NewYork_002.jpg
2024-01-15_NewYork_003.jpg
```

**Rename Pattern Options:**

| Pattern | Example |
|---------|---------|
| `{date}_{seq}` | 2024-01-15_001.jpg |
| `{date}_{location}_{seq}` | 2024-01-15_NewYork_001.jpg |
| `{date}_{time}_{seq}` | 2024-01-15_1430_001.jpg |
| `{original}` | Keep original name |

**Sequence Numbers:**
- Reset per folder: Each folder starts at 001
- Global sequence: Continues across folders
- Preserve order: Photos sorted by capture time before numbering

## Special File Handling

### Screenshots

The app automatically detects screenshots and can separate them:

**Detection Methods:**
- Exact screen dimensions (1920x1080, 2560x1440, phone resolutions)
- No EXIF camera data
- Filename patterns (Screenshot_*, Screen Shot*)
- Metadata indicating screen capture

**Options:**
- **Mix with photos** - Screenshots stay with regular photos
- **Separate folder** - Move to a "Screenshots/" subfolder

### Burst Photos

When your phone takes burst mode photos (many photos in rapid succession):

**Detection:**
- Photos taken within 2 seconds of each other
- At least 3 photos in sequence to qualify as a burst

**Options:**
- **Keep all** - Sort normally, keep every frame in the same folder
- **Subfolder** - Put bursts in subfolders: "Burst_001/", "Burst_002/", etc.
- **Flag for review** - Mark bursts in the preview so you can review them later

### Live Photos (iPhone)

iPhone Live Photos are a still image + short video clip:

**Detection:**
- Matching filename with .jpg/.heic and .mov/.mp4 extensions
- Files in the same folder with the same base name

**Options:**
- **Keep together** - Photo and video stay in same folder
- **Video subfolder** - Move video clips to a "LivePhoto_Videos/" subfolder

## AI Analysis (Optional)

If enabled, the organizer can add lightweight AI analysis during preview:
- **Object detection**: Adds tags for images (e.g., "dog", "car").
- **Document classification**: Uses OCR to flag images that look like documents.
- **Videos**: Extracts a single frame to generate a thumbnail and optional tags.

These tags appear in the preview gallery and are stored with the organized files.

## Preview and Dry Run

### Preview Changes

Before organizing, click **Preview Changes** to see exactly what will happen:

```
ORGANIZATION PREVIEW

Files to organize: 45,234
  Will be moved: 43,891
  Will be renamed: 45,234
  Will stay in place: 1,343 (already organized)

Folders to create: 234
Burst Groups: 12          (shown in orange when bursts detected)
Live Photos: 156          (shown in blue when Live Photos detected)

SAMPLE CHANGES (showing first 500):
  Source          | Destination                                          | Date | Location | Burst | Live
  IMG_4521.jpg    | 2024/01-January/2024-01-15_NewYork/2024-01-15_001.jpg| exif | NewYork  |       |
  IMG_4522.jpg    | 2024/01-January/2024-01-15_NewYork/2024-01-15_002.jpg| exif | NewYork  | #1    |
  IMG_4523.jpg    | 2024/01-January/2024-01-15_NewYork/2024-01-15_003.jpg| exif | NewYork  | #1    |
  IMG_0001.jpg    | 2024/02-February/2024-02-10/2024-02-10_001.jpg       | exif |          |       | Yes
  IMG_0001.mov    | 2024/02-February/2024-02-10/LivePhoto_Videos/...     | file |          |       | Yes
  ...

[Export as CSV]  [Organize Now]
```

The preview table shows:
- **Source**: Original filename
- **Destination**: Where the file will be organized to
- **Date**: Source of date information (exif, file, or undated)
- **Location**: Location name if GPS data available
- **Burst**: Burst group number (e.g., #1, #2) if part of a burst sequence
- **Live**: "Yes" if file is part of a Live Photo pair

### Dry Run Mode

Enable **Dry Run** to:
- See all changes that would be made
- Export the change list
- Verify organization looks correct
- No files are actually moved

Perfect for testing your settings before committing.

## Handling Edge Cases

### Photos Without Dates

When a photo has no EXIF date and no reliable file date:

**Options:**
- **Undated folder** - Move to "Undated/" folder for manual review
- **Use file date** - Trust file modification date (less reliable)
- **Skip** - Leave in place, don't organize

### Photos Without Location

When location-based organization is enabled but GPS data is missing:

- Folder name omits location: "2024-01-15/" instead of "2024-01-15_NewYork/"
- Photos without GPS are organized by date only

### Conflicting Filenames

When the destination filename already exists:

**Options:**
- **Add sequence number** - photo_001.jpg, photo_002.jpg
- **Add timestamp** - photo_143022.jpg
- **Skip** - Don't move, report conflict
- **Overwrite if identical** - Replace if same hash, skip if different

## Reversibility

### Undo Organization

Every organization operation is logged. To undo:

1. Go to **Action Log**
2. Find the organization operation
3. Click **Undo**

Files are moved back to their original locations with original names.

**Limitation:** Undo works as long as files haven't been further modified or deleted.

### Organization History

The app tracks:
- Original path of every organized file
- When it was organized
- What settings were used

This lets you re-organize with different settings or undo changes months later.

## Libraries Used

### Pillow / PIL

Image loading and EXIF extraction:
- Reads EXIF data from JPEG, PNG, HEIC, TIFF
- Handles image orientation correction
- Cross-platform compatibility

### exifread

Robust EXIF parser:
- Handles malformed EXIF data gracefully
- Extracts GPS coordinates
- Reads camera-specific tags

### python-dateutil

Date parsing:
- Handles various EXIF date formats
- Timezone-aware date handling
- Fuzzy parsing for unusual formats

### geopy

Reverse geocoding:
- Converts GPS coordinates to location names
- Uses free services (Nominatim/OpenStreetMap)
- Caches results to avoid API limits

## Settings Reference

| Setting | Default | Description |
|---------|---------|-------------|
| Date Format | YYYY/MM-Month | Folder structure pattern |
| Include Location | Off | Add location to folder names |
| Location Detail | City Only | Level of detail for location names |
| Event Clustering | Off | Group by time proximity |
| Event Gap | 4 hours | Time gap to separate events (1-48 hours) |
| Rename Files | On | Rename to date-based names |
| Rename Pattern | {date}_{seq} | Filename pattern |
| Conflict Resolution | Add Sequence Number | How to handle filename conflicts |
| Screenshot Handling | Separate Folder | How to handle screenshots |
| Burst Handling | Keep All | How to handle burst photos |
| Live Photo Handling | Keep Together | How to handle Live Photos |
| Undated Photos | Undated Folder | How to handle photos without dates |
| Move vs Copy | Move | Move files or copy them |
| Dry Run | Off | Preview only, don't move |
