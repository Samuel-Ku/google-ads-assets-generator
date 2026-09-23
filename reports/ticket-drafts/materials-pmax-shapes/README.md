# Proposed implementation tickets

Source: https://github.com/Samuel-Ku/google-ads-assets-generator/issues/1

Approved by the user and published on22September2026. Ticket numbers in the planning table are draft identifiers; the published GitHub mapping is below. All six issues are ready-for-agent, and the three blocking edges were verified through the native dependency API. Parent specification#1 remains unchanged.

| Draft | Title | Blocked by | Demonstrable delivery |
| --- | --- | --- | --- |
| 1 | Delete individual campaign materials safely | None | Confirm deletion of a file without derived descendants; reconcile all compositions/history and release storage. |
| 2 | Delete an image with its derived cutouts | 1 | Review and delete an original's complete derived subtree without losing unrelated files. |
| 3 | Preserve composition text in Performance Max images | None | Choose composed/clean PMax, preserve mode-specific edits and export the primary text pair. |
| 4 | Export composed PMax A/B text variants | 3 | Generate headlines × CTA variants with correct counts, previews and ZIP paths. |
| 5 | Add reusable rectangle and square Shape layers | None | Add/edit/save shapes, reuse them as Team Templates and export them in Display. |
| 6 | Add circle, ellipse, triangle and diamond shapes | 5 | Complete the six-shape set with geometry-aware editing and the same reuse/export workflow. |

Tickets 1, 3 and 5 can start immediately. There are no separate backend-only, frontend-only or test-only tickets. Small preparatory refactors are included first within the feature that needs them. The shape and PMax tickets use the same generic full-composition contract. Whichever lands second verifies their combination; shared-file overlap and cross-feature verification are coordination concerns rather than extra blocking edges.

## Published issues

| Draft | GitHub issue | Blocked by |
| --- | --- | --- |
| 1 | [#2 — Delete individual campaign materials safely](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/2) | None |
| 2 | [#3 — Delete an image with its derived cutouts](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/3) | #2 |
| 3 | [#4 — Preserve composition text in Performance Max images](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/4) | None |
| 4 | [#5 — Export composed PMax A/B text variants](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/5) | #4 |
| 5 | [#6 — Add reusable rectangle and square Shape layers](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/6) | None |
| 6 | [#7 — Add circle, ellipse, triangle and diamond shapes](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/7) | #6 |
