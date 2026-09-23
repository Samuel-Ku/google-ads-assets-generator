## Parent

[Spec #1: delete campaign images, preserve PMax text, and add editable shapes](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/1)

## What to build

Allow an editor to permanently delete an individual campaign material that has no derived descendants, directly from its material card. The action must remove the file, reconcile all current Campaign Compositions and explain unavailable historical references without disturbing unrelated work. This is a complete first deletion workflow, including safe cancellation, permissions, persistence and export.

Keep deselecting a material and removing a layer separate from deleting the uploaded file. Campaign materials include product photos, backgrounds, cutouts and uploaded Elements, including SVG. Brand Kit assets are excluded. Materials with derived descendants are blocked with a clear explanation in this slice; deletion of a disclosed dependency tree is delivered by “Delete an image with its derived cutouts”.

Any small refactoring needed to share material-reference reconciliation belongs at the start of this ticket and must preserve existing behaviour before enabling deletion. A separate architecture-only ticket is not required.

## Acceptance criteria

- [ ] Each eligible campaign material has a distinct Polish Delete file action. Confirmation identifies the selected file and affected compositions, explains permanence and preserves everything when cancelled.
- [ ] Deletion requires an authenticated shared-campaign editor, CSRF protection, a matching campaign/material relationship and the current campaign version. Unauthorized, malformed or stale requests leave files and campaign state unchanged.
- [ ] Materials with derived descendants are rejected without deleting any file. Deleting a leaf cutout preserves its original and sibling cutouts.
- [ ] Affected queued/running background work blocks deletion. Coordinated processing and storage operations prevent a race from recreating the deleted output; retry behaviour is safe.
- [ ] Success removes the file bytes, makes protected file reads and processing unavailable, updates the material list and selections, reconciles the base composition and every saved layout/format override, and records an authored campaign revision. No other image is silently substituted.
- [ ] Unrelated photos, geometry, text and styles remain intact. Incomplete compositions show a clear replacement warning and cannot pass off missing required material as a complete export.
- [ ] Unsaved local edits are handled explicitly: preserve/save them with normal conflict checking or require a clear user choice. Deletion must not silently discard those edits or overwrite another editor's newer revision.
- [ ] Later saves, local undo and restoration of historical campaign versions cannot resurrect downloadable references to the deleted file. Historical metadata remains useful and identifies unavailable material without promising file recovery.
- [ ] The storage meter reflects released capacity. Shared Team Templates remain reusable, existing exported ZIPs remain intact under their normal retention, and deleting one material does not extend campaign retention.
- [ ] An isolated browser journey proves cancel → delete → reopen → export → historical restore, while focused authenticated API tests cover security, stale versions, processing coordination and unavailable-file access. Assertions verify observable outcomes, not private helper structure.

## Blocked by

None — can start immediately.
