## Parent

[Spec #1: delete campaign images, preserve PMax text, and add editable shapes](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/1)

## What to build

Expand the native Shape menu with circle, ellipse, triangle and diamond, completing the six-shape set from the specification. The new choices must support the same complete edit/save/template/export workflow as rectangles and squares, including correct selection and transparency outside their visible geometry.

## Acceptance criteria

- [ ] Circle, ellipse, triangle and diamond are available from the Polish shape menu and appear with clear names in the layer list.
- [ ] All four support the existing Shape movement, resizing, fill, opacity, ordering, deletion and undo controls. Hit testing and visible selection behave consistently with their actual geometry.
- [ ] Circles preserve pixel aspect ratio across resize and format adaptation; ellipses can resize freely. Triangle and diamond geometry is deterministic and bounded, without arbitrary path execution.
- [ ] Exported pixels preserve curved/slanted boundaries, transparent corners, opacity and layer order. Contrast validation does not falsely treat a non-rectangular shape's whole bounding box as a solid background.
- [ ] All four survive linked and isolated format edits, wide/square/tall adaptation, campaign reload/version restoration and Team Template round trips with brand-linked and custom colours.
- [ ] The client and server accept precisely the supported shape values and styles, reject malformed geometry predictably, and remain compatible with older rectangle/square recipes.
- [ ] Display retains these shapes; clean RDA/PMax and logo-only outputs exclude them. If composed PMax has landed, verify these shapes through mode switching and real export; otherwise keep the full-composition contract compatible so “Preserve composition text in Performance Max images” verifies them when it lands.
- [ ] Browser and existing focused regression suites verify all six primitives together, including a saved Team Template, another Brand Kit and actual mixed-profile ZIP pixels. Freehand/path editing, rotation, gradients, shadows, boolean operations and a new border system remain outside scope.

## Blocked by

- [Add reusable rectangle and square Shape layers (#6)](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/6)
