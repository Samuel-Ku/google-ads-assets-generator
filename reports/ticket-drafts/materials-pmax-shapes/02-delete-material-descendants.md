## Parent

[Spec #1: delete campaign images, preserve PMax text, and add editable shapes](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/1)

## What to build

Extend the individual-file deletion workflow so an editor can delete a selected campaign image together with its derived cutouts and mask results, after reviewing the exact impact. Removing a derived image deletes only its own descendant subtree; ancestors, siblings and unrelated materials remain available.

This replaces ticket 1's temporary restriction on materials with descendants and reuses its file lifecycle, revision reconciliation and history safeguards.

## Acceptance criteria

- [ ] The confirmation identifies the selected file, the count/list of derived files to be removed and affected Campaign Compositions before any destructive action.
- [ ] Cancelling leaves all files, selections and compositions unchanged; descendants are never removed silently.
- [ ] Dependency traversal stays within the selected campaign and includes every derived generation. Deleting a cutout preserves its parent and siblings while deleting only that cutout's descendants.
- [ ] The server rechecks the affected set and campaign version at execution. If new descendants or other relevant changes alter the confirmed impact, require a refreshed confirmation rather than deleting undisclosed files.
- [ ] An active job involving any affected file blocks the whole deletion. Deletion, retries and processing races cannot leave a partially active dependency chain or create fresh output for removed inputs.
- [ ] All affected selections, base compositions and format overrides are reconciled in the same authored campaign change, with the same missing-material and historical-restore protections as individual deletion.
- [ ] Removed bytes are released and storage usage is refreshed; unrelated campaign files, Brand Kits, Team Templates and previously exported ZIPs remain unchanged.
- [ ] Browser and existing API tests cover an original with multiple branches and a nested mask result, cancellation, subtree deletion, changed-impact confirmation, job conflicts, reopen/export and restoration of a historical version.

## Blocked by

- Ticket 1 — Delete individual campaign materials safely.
