# Duplicate Resolution

## Overview

Duplicate Resolution is the process of choosing which copy to keep and what to do
with the remaining files. In DupliCleaner, resolution happens in two stages:

1. **Decide** - pick a keeper for each group (manually or with a strategy)
2. **Act** - quarantine, trash, or delete the non-keeper files

## Resolution Strategies

These strategies only **mark keepers**. They do not delete files.

- **Keep Newest** - keeps the most recently modified file
- **Keep Oldest** - keeps the oldest file (original)
- **Keep Largest** - keeps the largest file (often highest quality)
- **Keep Shortest Path** - keeps the file in the simplest location
- **Keep on Drive...** - keeps files on a preferred drive (requires a drive selection)
- **Manual** - choose a keeper per group

## Recommended Workflow

### 1) Select Groups

Use the group list on the left to choose which groups to process:

- Use **Select All** or **Select None** for bulk selection
- Apply filters (Type, Status, Scope, Drive) to narrow the list

### 2) Decide Keepers

Choose a strategy and use one of the following buttons:

- **Preview** - estimates impact for selected groups (or the current view)
- **Set Keepers (Selected)** - applies the strategy to checked groups
- **Set Keepers (All Pending)** - applies to all pending groups in the view

If you select **Manual**, choose keepers directly in the group details panel.
Only one keeper is allowed per group.

### 3) Act on Non-Keepers

Use the action buttons to remove non-keepers:

- **Quarantine** (recommended, recoverable)
- **Send to Trash** (reversible)
- **Delete Permanently** (cannot be undone)

The confirmation dialog shows how many files will be affected and the total size.

## Manual Keeper Selection

In the group details panel, select one keeper per group. Selecting a new keeper
replaces the previous one. If no keeper is selected, action buttons will not run.

## Group Statuses

- **Pending** - eligible for keeper selection and actions
- **Resolved** - a keeper has been set
- **Ignored** - intentionally skipped

Use the Status filter to view resolved or ignored groups, and unignore a group
from its details panel when needed.
You can also bulk-unignore ignored groups using the group list selection and
the Unignore Selected button.

## Clearing Selections

The **Clear Selections** button resets all keeper choices and returns groups to
pending status. This is useful if you want to re-apply a different strategy.
