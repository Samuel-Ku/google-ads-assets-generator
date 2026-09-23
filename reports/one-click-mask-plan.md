# One-click mask correction — design

- [x] Inspect the current MaskEditor, toolbar, save path and regression harness.
- [x] Define the screenshot symptom: opaque background remains inside an enclosed opening between product parts.
- [x] Bound the extension to existing mask correction. No image generation, new backend service or model changes.
- [x] Compare local contiguous removal (recommended) with global similar-color removal; present the choice in the user's popup.
- [x] Receive design approval before implementation — user approved connected area around the click.
- [x] Implement selected-area removal and Polish UI controls, preserving undo, source pixels and current corrections.
- [x] Verify actual pointer-to-image coordinate mapping, disconnected light areas, tolerance, transparency, PNG export and large-image resources.
- [x] Review and deploy to the existing VM; verify deployed assets and persistence.

Proposed default: `Usuń obszar` mode in the mask dialog. One click removes the connected area whose original pixel colors resemble the seed. A tolerance control adjusts the color range for the next click. Four-neighbor connectivity and a fixed seed color avoid drifting across a gradual gradient or a diagonal border. Empty transparent pixels do not bridge separate areas. Each completed click is one undo step and becomes the baseline for subsequent mask adjustments; the source image remains available for restore strokes.

The attached image is a screenshot illustrating the enclosed white area, not an original transparent product file. Tests will reproduce the structure with an enclosed white pocket and a separate white product detail; results must not be described as a test on the user's original asset.
