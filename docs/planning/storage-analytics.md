# Storage Analytics

## Goal

Provide visual analysis of where storage space is being used across NAS drives so users can make informed decisions about cleanup, organization, and backup priorities. Answer the question: "Where is my 4TB going?"

## Current Capabilities

- **Scanner** collects file metadata (size, type, dates, paths) for all scanned files
- **Drive Manager** tracks multiple drives and their contents
- **Database** stores all file records with size, extension, dates, drive assignments
- **Duplicate detection** knows how much space is wasted by duplicates
- No analytics or visualization exists

## What Needs to Be Built

### 1. Space Usage by File Type

- Breakdown of storage by category: Photos, Videos, Documents, Audio, Other
- Breakdown by extension within each category (how much .jpg vs .png vs .heic)
- Percentage and absolute size for each
- Identify surprising space hogs (e.g., "RAW files are 40% of your storage")

### 2. Space Usage by Date

- Storage consumed per year/month
- Growth trend: how much new data is added each year
- Identify "heavy" periods (vacation dumps, phone backup spikes)
- Projection: at current growth rate, when will the drive fill up

### 3. Space Usage by Folder

- Treemap visualization showing folder sizes
- Drill-down: click a folder to see its breakdown
- Identify large folders that might need cleanup
- Compare folder sizes across drives

### 4. Duplicate Space Analysis

- Total space wasted by exact duplicates
- Total space wasted by near-duplicates (estimated)
- Space recoverable if all duplicates were resolved
- Breakdown by: which drive has the most duplicates, which folders
- "If you clean up duplicates, you'll recover X GB"

### 5. Redundancy and Risk Analysis

- Files that exist on only one drive (at risk)
- Files backed up across multiple drives (safe)
- Total at-risk data volume
- Suggested backup priorities: "These 50GB of unique photos on Drive C have no backup"

### 6. File Age Analysis

- Oldest files in the collection
- Files not accessed/modified in N years
- Potential archive candidates (old, rarely accessed, large)
- "Cold storage" suggestions

## Implementation Phases

### Phase 1: Data Aggregation Queries

- SQL queries that compute storage breakdowns from existing file_records table
- Group by: extension, year, folder path, drive
- Compute: sum(size), count, avg(size)
- Cache results for fast UI display (re-compute on demand or after scan)
- Store computed analytics in a summary table for quick access

### Phase 2: Analytics Panel in UI

- New tab or section in the UI: "Storage Analytics"
- Summary cards at top:
  - Total scanned: X files, Y TB
  - Duplicates found: X files, Y GB recoverable
  - At-risk files: X files, Y GB with no backup
- Bar charts for file type breakdown
- Timeline chart for storage by year
- Table view for detailed breakdowns (sortable, filterable)

### Phase 3: Folder Treemap

- Interactive treemap showing folder hierarchy by size
- Color coding by file type or age
- Click to drill into subfolders
- Right-click to jump to that folder in Files tab
- DearPyGUI has basic drawing/plot capabilities; may need custom rendering

### Phase 4: Actionable Insights

- "Quick Wins" section: largest easy-to-recover space
  - Exact duplicates (safe to clean, no quality loss)
  - Empty folders
  - Temporary files (.tmp, .bak, thumbs.db)
  - Very large files that might be accidental (>1GB single files)
- "Recommendations" section:
  - "Drive E: is 90% full, Drive F: is only 40% full"
  - "12GB of RAW files could be moved to archive"
  - "These 847 burst photos could be reduced to 212 keepers"
- Estimated time/effort for each recommendation

### Phase 5: Trend Tracking

- Store analytics snapshots over time (per scan)
- Show storage growth trends
- "Last month you added 15GB, deleted 3GB, net +12GB"
- Drive fill prediction: "At this rate, Drive E: will be full in 6 months"
- Before/after comparison: "After cleanup, you recovered 45GB"

## UI Design

### Summary Dashboard

```
Storage Overview
+------------------+------------------+------------------+
| Total Scanned    | Duplicates       | At Risk          |
| 245,891 files    | 12,453 files     | 3,201 files      |
| 3.8 TB           | 187 GB waste     | 45 GB no backup  |
+------------------+------------------+------------------+

By Type               By Year              By Drive
[===Photos 62%===]    2024: ||||||||| 450GB  Drive C: [====75%====]
[==Videos 25%==]      2023: ||||||| 380GB    Drive E: [=======92%=]
[Docs 8%]             2022: ||||| 290GB      Drive F: [===42%===  ]
[Audio 3%]            2021: |||| 210GB
[Other 2%]            Older: |||||||| 420GB
```

### Quick Wins Panel

```
Recoverable Space:
  Exact duplicates:     187 GB (12,453 files)  [Clean Up]
  Empty folders:        0 GB (234 folders)      [Delete]
  Temp/cache files:     2.3 GB (1,892 files)   [Delete]
  Burst photo extras:   8.1 GB (3,402 files)   [Review]
  ---
  Total recoverable:    ~197 GB
```

## Technical Considerations

### Performance

- Analytics queries on 200K+ file records must be fast (<2 seconds)
- Pre-compute and cache common aggregations after each scan
- Use SQLite indexes: extension, drive_id, created_date, file_size
- Incremental updates: only recompute affected folders after partial scan

### Visualization in DearPyGUI

- Bar charts: use dpg.add_bar_series() with plot widgets
- Pie charts: not native, use stacked bars or custom drawing
- Treemap: requires custom rendering with dpg.draw_rect() on a drawlist
- Alternative: generate chart images with matplotlib, display as textures

### Data Freshness

- Analytics based on last scan results
- Show "Last scanned: 2 days ago" indicator
- Option to re-scan before viewing analytics
- Stale data warning if scan is very old

## Database Schema

```sql
CREATE TABLE analytics_snapshots (
    id INTEGER PRIMARY KEY,
    snapshot_date TEXT DEFAULT CURRENT_TIMESTAMP,
    total_files INTEGER,
    total_size_bytes INTEGER,
    duplicate_files INTEGER,
    duplicate_size_bytes INTEGER,
    at_risk_files INTEGER,
    at_risk_size_bytes INTEGER,
    breakdown_json TEXT  -- detailed breakdown as JSON
);
```

## Integration Points

- **Scanner** - Triggers analytics recomputation after scan completes
- **Drive Manager** - Provides drive-level breakdown and redundancy data
- **Duplicate Detection** - Provides waste calculation
- **Action Engine** - "Clean Up" buttons trigger standard delete/quarantine workflow
- **Organizer** - Burst detection feeds into "burst extras" space estimate
