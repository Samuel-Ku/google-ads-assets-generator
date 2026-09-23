## Parent

[Spec #1: delete campaign images, preserve PMax text, and add editable shapes](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/1)

## What to build

Allow designers to add native rectangle and square Shape layers without uploading a graphic. Each shape must work all the way through editing, aspect-ratio changes, campaign saving, Team Template reuse and actual Display export, while preserving the full-composition contract used by composed PMax.

A Shape is editable geometry, distinct from an uploaded Element. Begin with two primitives to establish a complete compatible workflow; “Add circle, ellipse, triangle and diamond shapes” adds the remaining four. This workflow is independently usable in Display and Team Templates and does not require the PMax feature to land first.

## Acceptance criteria

- [ ] The Polish composition editor offers Add shape with rectangle and square choices. New shapes appear as independently named selectable layers with stable identity, not as uploaded materials or Material Slots.
- [ ] Pointer and keyboard controls allow selection, movement, resizing, fill changes, opacity, ordering, deletion and undo. Initial fill follows the Brand Kit accent; supported existing rectangle corner styling remains consistent.
- [ ] Squares retain equal width and height in rendered pixels during editing and adaptation; rectangles can resize freely. Geometry remains bounded and exports do not distort the intended shape.
- [ ] Shapes preserve stacking order and do not disappear when adapting between wide, square and tall formats. Correct the current custom-decoration loss as part of this user-visible behaviour without changing legacy Built-in Layouts.
- [ ] Shape additions, style changes, motion, ordering and removals follow the synchronization switch. Isolated format overrides and other Campaign Compositions remain independent.
- [ ] Shape geometry and styles survive campaign save/reopen, undo and version restoration. Team Template capture, server validation and application to a new campaign preserve shapes with brand-linked colours rebinding and manual colours unchanged.
- [ ] Older campaigns, rectangle decorations and template recipes stay readable. Shape data uses bounded supported values, never executable paths or file references; unsupported/non-finite payloads fail without damaging saved work.
- [ ] Display JPG/PNG outputs match visible shape geometry, fill, opacity and stacking. Existing clean RDA/PMax and logo-only outputs exclude shape overlays and explain that mode to the editor. When composed PMax is available, its full composition retains these shapes.
- [ ] The existing isolated browser journey and Canvas/recipe/synchronization/API test seams cover adding, editing, reordering, deleting/undoing, changing aspect ratio, save/reopen, Team Template reuse with another Brand Kit and real exported pixels. No new rendering engine or test-only endpoint is introduced.

## Blocked by

None — can start immediately.

Coordination: this ticket and “Preserve composition text in Performance Max images” share a generic full-composition rendering contract, not a blocking edge. Whichever lands second verifies shape preservation through composed/clean PMax switching and actual export; neither may regress the earlier feature.

