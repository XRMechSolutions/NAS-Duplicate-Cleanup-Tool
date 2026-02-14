# Export & Reporting

## Goal

Provide comprehensive data export and report generation across all panels, giving users the ability to extract insights, share findings, and create records of their storage analysis in standard formats (CSV, JSON, HTML, PDF).

## Current Capabilities

### Action Log Export (action_log_panel.py - fully working)

- Multi-format export: CSV, JSON, HTML (lines 744-824)
- Filterable by date range and action type (lines 716-724)
- Styled HTML output with color-coded action types
- Output defaults to Desktop with timestamped filename

### Organize Preview Export (organize_panel.py - working)

- CSV export of organization preview (lines 962-1000)
- Columns: Source, Destination, Date Source, Location, Event, Burst Group, Live Photo
- File dialog for choosing save location

### Backup Plan Export (drives_panel.py - working)

- CSV export of suggested backup operations (lines 1823-1846)
- Columns: source_path, target_path, size_bytes, content_hash, target_drive_id
- Output to Desktop as `backup_plan.csv`

### Status Log Export (status_log_panel.py - working)

- Plain text export of status/progress log (lines 156-165)
- Output to Desktop as `status_log.txt`

### Redundancy Report (drives/redundancy.py - working)

- RedundancyChecker builds reports with at-risk files, redundant groups (lines 77-110)
- Displayed in UI but not directly exportable to file

### What's NOT Implemented

- No duplicate group export (the main use case - "export my duplicate analysis")
- No face/person data export
- No search results export
- No unified reporting dashboard
- No PDF report generation
- No scheduled/automated reports
- No summary statistics export across all panels
- No redundancy report file export (display-only)

## What Needs to Be Built

### 1. Duplicate Group Export

The most requested export - users want to share or review duplicate findings outside the app.

**Export contents:**
- Group ID, match type (exact/near), similarity score
- File paths, sizes, dates, hashes for each member
- Which file is marked as keeper and why
- Quality scores (if computed)
- Total space recoverable

**Formats:**
- CSV: one row per file, group_id column to associate members
- JSON: hierarchical (groups containing file arrays)
- HTML: styled report with thumbnails (optional)

### 2. Face/Person Data Export

Export person database for external use or backup.

**Export contents:**
- Person name, birth year, photo count, notes
- Face locations (file path, bounding box coordinates)
- Family relationships (if implemented)
- Cluster assignments

**Formats:**
- CSV: person roster with stats
- JSON: full person data with face details

### 3. Search Results Export

Export the results of any search query.

**Export contents:**
- Query terms used
- Matching files with paths, sizes, relevance scores
- AI summaries and tags for each match
- Export subset or all results

### 4. Unified Report Generator

A single "Generate Report" feature that combines data from multiple panels.

**Sections:**
- Storage overview: total files, total size, by type, by drive
- Duplicate summary: exact count, near count, space recoverable
- At-risk files: files with no backup across drives
- Face/person summary: people found, photo counts
- Organization summary: sorted vs unsorted files
- Action history: operations performed, space recovered

### 5. Redundancy Report Export

The redundancy report is currently display-only. Add file export.

**Export contents:**
- At-risk files (single-drive only) with paths and sizes
- Redundant files (multi-drive) with drive locations
- Summary statistics
- Backup recommendations

## Implementation Phases

### Phase 1: Duplicate Group Export

- Add "Export" button to duplicates panel toolbar
- Export dialog with format selection (CSV, JSON, HTML)
- CSV format: group_id, match_type, similarity, file_path, file_size, file_date, hash, is_keeper, keeper_reason
- JSON format: `{ groups: [{ id, match_type, similarity, files: [...], keeper: {...} }] }`
- Filter options: all groups, selected groups, unresolved only, resolved only
- Include quality scores when available

### Phase 2: Search and Face Export

- Add export button to search results panel
- Add export button to faces panel (person roster)
- Reuse export dialog pattern from action log panel
- Search export includes query metadata
- Face export includes person stats and optionally face coordinates

### Phase 3: Redundancy Report Export

- Add export button to redundancy report section of drives panel
- CSV with at-risk files, redundant files, and summary stats
- JSON with full report structure
- HTML with formatted tables and statistics

### Phase 4: Unified Summary Report

- New "Generate Report" button in app toolbar or menu
- Aggregates data from all panels into single document
- HTML report with sections, tables, and optional thumbnails
- PDF generation using weasyprint or reportlab (optional dependency)
- Include charts/graphs if matplotlib is available

### Phase 5: Scheduled Reports

- Option to auto-generate report after scan completion
- Configurable output directory (default: Desktop)
- Report naming convention: `duplicleaner_report_YYYY-MM-DD.html`
- Email integration (optional, via SMTP)

## Technical Considerations

### Consistent Export Pattern

All panels should use a shared export utility:

```python
class ExportManager:
    """Shared export logic for all panels."""

    def export_csv(self, rows: list[dict], filepath: str, columns: list[str]) -> None: ...
    def export_json(self, data: Any, filepath: str) -> None: ...
    def export_html(self, title: str, sections: list[HTMLSection], filepath: str) -> None: ...

    def show_export_dialog(self, panel_name: str, callback: Callable) -> None:
        """Show standard export dialog with format selection."""
```

### Performance

- Large exports (100K+ files) should show progress bar
- Stream CSV writing for memory efficiency
- HTML report with thumbnails should limit image count or use lazy loading
- JSON export should handle large datasets without loading all into memory

### File Paths

- Default export location: user's Desktop
- File dialog for custom location
- Prevent overwriting existing files (append timestamp or increment suffix)
- Handle long file paths in export data (truncate display, keep full path in data)

### Data Privacy

- Export may contain full file paths (could reveal directory structure)
- Option to anonymize paths in export (replace user-specific prefixes)
- Face data export should warn about PII (person names, locations)

## Integration Points

- **Storage Analytics** (storage-analytics.md) - Analytics panel should have "Export Stats" button
- **Action Engine** - Export action log already works, extend to include transaction groups
- **Database** - All export queries come from existing database methods
- **Config** - Export preferences (default format, default location) stored in config
