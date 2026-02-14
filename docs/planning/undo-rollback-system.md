# Undo/Rollback System

## Goal

Provide a safety net for all destructive file operations (delete, move, quarantine) so users can reverse mistakes. When dealing with irreplaceable family photos on NAS storage, the ability to undo is critical for user confidence.

## Current Capabilities (Partially Implemented)

### Action Log (schema.sql:265-277, working)

- `action_log` table tracks all file operations with:
  - action_type: delete, quarantine, trash, link, copy, move, restore
  - source_path, dest_path, file_hash, file_size
  - reversible (boolean), reversed (boolean)
  - metadata (JSON for additional context)
  - timestamp

### Action Engine (core/actions.py, working)

- ActionStatus enum includes UNDONE state (line 27-35)
- PendingAction and ActionResult dataclasses (lines 38-59)
- Quarantine folder support (line 130-131)
- Dry-run mode (line 134)
- Protected system paths (lines 105-112)

### Database Support (database.py, partial)

- `mark_action_reversed()` method exists (line 1529)

### What's NOT Implemented

- No undo command or UI button
- No undo history viewer
- No actual file restoration logic
- No transaction grouping (batch operations are individual log entries)
- No retention policy (when to purge old quarantine files)

## Design

### Undo Strategy by Action Type

| Original Action | Undo Strategy | Reversibility |
|---|---|---|
| **Quarantine** (move to quarantine folder) | Move file back to original path | Always reversible (file still exists) |
| **Trash** (move to system recycle bin) | Restore from recycle bin | Reversible until bin is emptied |
| **Hard Delete** | Cannot undo | NOT reversible (warn user before action) |
| **Move** (reorganize) | Move file back to original path | Always reversible (file still exists) |
| **Copy** | Delete the copy | Always reversible |
| **Hard Link** | Remove the link | Always reversible (original still exists) |
| **Symbolic Link** | Remove the symlink | Always reversible |
| **Metadata Write** | Restore from backup | Reversible if backup was created |

### Transaction Grouping

When the user does "Delete all duplicates in this group" and 4 files are deleted, those 4 actions should be grouped as one transaction so they can be undone together.

```sql
CREATE TABLE action_transactions (
    id INTEGER PRIMARY KEY,
    description TEXT NOT NULL,  -- "Deleted 4 duplicates from group #127"
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    action_count INTEGER,
    total_size_bytes INTEGER,
    status TEXT DEFAULT 'completed'  -- completed, partially_undone, fully_undone
);

-- Add to existing action_log:
ALTER TABLE action_log ADD COLUMN transaction_id INTEGER REFERENCES action_transactions(id);
```

### Quarantine as Default

Quarantine should be the default delete mode (not hard delete) to maximize undo capability:

- Files moved to a quarantine folder (configurable location, default: `.duplicleaner_quarantine/`)
- Original path stored in action_log for restoration
- Quarantine retains folder structure: `quarantine/original/path/to/file.jpg`
- Retention period: configurable (default 30 days), after which quarantined files are permanently deleted
- Space monitoring: warn if quarantine folder grows too large

## Implementation Phases

### Phase 1: Undo for Quarantine Operations

- Add `undo_action(action_id)` method to ActionEngine
- For quarantine: move file from quarantine path back to original source_path
- Handle conflicts: what if another file now exists at the original path?
  - Option A: rename restored file (add suffix)
  - Option B: ask user what to do
  - Option C: restore to a recovery folder instead
- Mark action as reversed in action_log
- Update database records (un-mark file as deleted)

### Phase 2: Action History UI

- New panel or dialog: "Action History"
- Table showing recent actions: timestamp, type, file path, size, reversible status
- Group by transaction (show "Deleted 4 files" with expand to see individual files)
- "Undo" button per action and per transaction
- Filter by action type, date range, reversibility
- Search by filename
- Accessible from main menu or toolbar

### Phase 3: Transaction Grouping

- Wrap batch operations in transactions
- "Undo Transaction" reverses all actions in the group
- Partial undo: undo individual actions within a transaction
- Transaction status tracking (completed, partially_undone, fully_undone)
- Show transaction summary in action history

### Phase 4: Quarantine Management

- Quarantine browser: see what's in quarantine, when it was quarantined, when it expires
- Manual purge: permanently delete selected quarantine items
- Auto-purge: configurable retention period (30/60/90 days, never)
- Space usage display: "Quarantine is using 12.3 GB"
- Bulk restore: restore all items quarantined in a specific session
- Quarantine location settings: choose drive/folder

### Phase 5: Undo for Other Operations

- Undo move/reorganize operations
- Undo copy operations (delete the copy)
- Undo hard/symbolic link creation
- Undo metadata writes (restore from backup if available)
- Chain undo: "Undo last 5 actions"

## Technical Considerations

### File System Safety

- Always verify file exists before attempting undo
- Check file hash before and after restoration to ensure integrity
- Handle permission errors gracefully (file may be read-only, or drive may be disconnected)
- Handle disconnected drives: "Cannot undo - Drive E: is not connected"
- Never overwrite an existing file during undo without user confirmation

### Database Consistency

- When undoing a delete, restore the file record in the database
- When undoing a move, update the file path in the database
- Handle cascade: if a file was deleted and then the scan was re-run, the file may have a new record
- Atomic operations: file move + database update should succeed or fail together

### Performance

- Action log queries should be fast (index on timestamp, transaction_id)
- Quarantine operations are file moves (fast on same drive, slow cross-drive)
- Large batch undos should show progress

## Edge Cases

| Scenario | Handling |
|---|---|
| Original path no longer exists (folder deleted) | Recreate folder structure, then restore |
| Another file exists at original path | Ask user: rename, overwrite, or restore to recovery folder |
| Drive is disconnected | Show error, keep action in "pending undo" state |
| File was modified after quarantine | Warn user: "File in quarantine may differ from current version at path" |
| Quarantine drive is full | Warn before quarantining, suggest alternative location |
| Very old quarantine items (>1 year) | Show age warning, suggest permanent delete or restore |
| Undo of an undo (re-delete) | Allow re-quarantining, create new action log entry |
