# DupliCleaner User Guide

This guide is for end users. It focuses on how to use DupliCleaner safely and efficiently, with
step-by-step workflows and UI tips. Technical and internal details remain in the main docs.

## Table of contents
1. Overview
2. First-run checklist
3. Quick workflow (scan → review → act)
4. Drives tab
5. Scan modes
6. Duplicates tab
7. Resolve strategies
8. File actions (quarantine/trash/delete)
9. Organize tab
10. Faces & pets tab
11. Search tab
12. Settings tab
13. Action log and undo
14. Troubleshooting
15. Safety guidelines
16. Screenshot checklist

---

## 1) Overview
DupliCleaner finds exact and near-duplicate files, helps you choose which to keep, and can
organize photos into clean folder structures. It is designed to be safe by default and offers
undo for most actions.

---

## 2) First-run checklist
1. Add one or more drives or folders to scan.
2. Choose a scan mode (Quick or Deep).
3. Run a scan and review duplicates.
4. Choose a keep strategy and apply actions.

Screenshot:
![First-run wizard](../resources/help/screenshots/first_run_wizard.png)

---

## 3) Quick workflow (scan → review → act)
1. Go to **Drives** and add your target folders or drives.
2. Run **Quick Scan** first to get a safe baseline.
3. Open **Duplicates** to review groups and preview files.
4. Pick a **Keep Strategy** and confirm actions (Quarantine/Trash/Delete).
5. Check **Action Log** for undo options if needed.

Screenshot:
![Quick workflow overview](../resources/help/screenshots/quick_workflow_overview.png)

---

## 4) Drives tab
Use this tab to register drives or folders and monitor scan status.

What you can do here:
- Add or remove drives.
- Start a quick/deep/full scan.
- Run **Scan All** to process every registered drive in sequence.
- See progress and basic stats.

Screenshot:
![Drives tab](../resources/help/screenshots/drives_tab.png)

---

## 5) Scan modes
- **Quick**: Skips unchanged files. Best for routine scans.
- **Deep**: Rechecks all files, detects removals.
- **Full**: Deep scan plus AI analysis (if enabled).

Screenshot:
![Scan mode selector](../resources/help/screenshots/scan_mode_selector.png)

---

## 6) Duplicates tab
This is where you review duplicate groups and decide what to keep.

Tips:
- Use filters to narrow results (size, type, drive).
- Compare files side-by-side.
- Use selection checkboxes for bulk actions.

Screenshot:
![Duplicates tab](../resources/help/screenshots/duplicates_tab.png)

---

## 7) Resolve strategies
Common strategies:
- **Keep Newest**: Good for work-in-progress files.
- **Keep Oldest**: Good for original photos or documents.
- **Keep Largest**: Often highest resolution for media.
- **Keep Shortest Path**: Keeps simpler folder organization.
- **Keep on Drive**: Keeps the copy on your preferred drive.

Screenshot:
![Resolve strategy menu](../resources/help/screenshots/resolve_strategy_menu.png)

---

## 8) File actions (quarantine/trash/delete)
Actions determine what happens to files you don’t keep.

Recommended:
- **Quarantine**: Safest. Moves files to a dated quarantine folder.
- **Trash**: Sends files to OS recycle bin.
- **Delete**: Permanent removal. Use carefully.

Screenshot:
![Action buttons](../resources/help/screenshots/action_buttons.png)

---

## 9) Organize tab
Organize photos into date-based folders and optional location/event groupings.

Common options:
- Folder patterns: `YYYY/MM`, `YYYY/MM-Month`, `YYYY/MM/DD`
- Rename patterns: `{date}_{seq}`, `{date}_{location}_{seq}`
- Dry-run to preview before making changes

Screenshot:
![Organize tab](../resources/help/screenshots/organize_tab.png)

---

## 10) Faces & pets tab
Use face/pet recognition to group photos and assign names.

**Two views available:**
- **Unknown Clusters**: Groups of unidentified faces waiting to be named
- **Named People**: People you've identified - browse their photos

**Named People actions:**
- **Photos**: Opens a photo gallery showing all photos of that person
  - Sortable by date or filename
  - Click any photo for a larger preview
  - Open in default viewer or show in Explorer
  - Remove photos from a person if misidentified
- **Timeline**: View photos organized by year with age tracking
  - Shows actual photo thumbnails grouped by year
  - Click any photo for preview
- **Find More**: Search for additional photos of this person
- **Edit**: Change name or birth year
- **Delete**: Remove person (faces return to Unknown Clusters)

**Photo Gallery features:**
- Scrollable grid of all photos for a person
- Sort options: Date (Newest/Oldest), File Name
- Preview dialog with full-size image
- Actions: Open File, Show in Explorer, Remove from Person

Tips:
- Start with a small batch to validate recognition quality.
- Rename clusters to improve future matches.
- Use the Timeline view to see how someone has changed over time.
- Use "Remove from Person" to correct misidentified photos.

Screenshot:
![Faces and pets tab](../resources/help/screenshots/faces_pets_tab.png)

---

## 11) Search tab
Find files by keywords, AI tags, or OCR text. The search panel supports both semantic search (AI-powered image understanding) and text search (summaries, OCR, tags).

**Search options:**
- **Semantic (CLIP)**: Finds images matching natural language queries like "beach sunset" or "birthday cake"
- **Text search**: Searches summaries, OCR text, and tags
- **Limit**: Controls maximum results returned (10-5000)

**Filters:**
- **Type**: All, Images, Videos, Documents, Other
- **Date range**: From/To dates in YYYY-MM-DD format
- **Person**: Filter by people detected in photos

**Sorting options:**
- Relevance (default, by similarity score)
- Date (Newest/Oldest)
- Size (Largest/Smallest)
- Name (alphabetical)

**Results display:**
- Thumbnail preview for image files
- File name, size, and modified date
- Similarity score for semantic matches
- AI-detected categories

**Actions per result:**
- **Preview**: Opens a larger preview dialog with full file details
- **Open**: Opens the file with its default application
- **Explorer**: Opens Windows Explorer with the file selected

**Selection:**
- Use checkboxes to select multiple results
- "Select All" and "Select None" buttons for bulk selection

Screenshot:
![Search tab](../resources/help/screenshots/search_tab.png)

---

## 12) Settings tab
Central place for scan rules, duplicate thresholds, AI options, and database management.

Screenshot:
![Settings tab](../resources/help/screenshots/settings_tab.png)

---

## 13) Action log and undo
Every file action is recorded. Most actions can be undone.

Screenshot:
![Action log](../resources/help/screenshots/action_log.png)

---

## 14) Troubleshooting
- **No duplicates found**: Try Deep Scan or lower similarity threshold.
- **Slow scans**: Exclude large folders or enable ignore patterns.
- **Missing AI results**: Verify AI settings and model downloads.
- **Cannot delete**: Check protected folder rules and permissions.

Screenshot:
![Troubleshooting tips](../resources/help/screenshots/troubleshooting.png)

---

## 15) Safety guidelines
- Always start with **Quarantine** until you trust your workflow.
- Use **Dry Run** in Organize before moving files.
- Review groups with **side-by-side previews** before delete.
- Keep backups for irreplaceable data.

---

## 16) Screenshot checklist
Use this list to capture UI screenshots for the help docs:
- First-run wizard
- Drives tab
- Scan mode selector
- Duplicates tab (group list + preview)
- Resolve strategy menu
- Action buttons (quarantine/trash/delete)
- Organize tab (preview panel)
- Faces & pets tab
- Search tab
- Settings tab
- Action log (with undo)
- Troubleshooting/help panel (if any)
