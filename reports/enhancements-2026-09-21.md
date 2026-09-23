# Editor extensions — verification, 2026-09-21

Released to http://192.168.15.42:8765 at `/home/ubuntu/google-ads-assets/releases/20260921-133551`.

## Delivered

- Multiple selected products and independent uploaded Elements; each remains a separate canvas layer. Cutout replacement targets only its matching original.
- CTA fill, corner rounding and border controls.
- Linked edits on by default within the same composition, across all Display/RDA/PMax formats as applicable. Geometry adapts to the destination proportions; clean profiles exclude text, CTA, logo and Elements. Logo exports remain independent.
- Optional isolated edits. An isolated master edit preserves existing/lazy format appearances. Undo restores complete prior scene and text snapshots, including local format adjustments, and survives changing the displayed format.
- Select/clear all formats and compositions. Image basenames are dimensions; separate profile/composition/variant folders prevent collisions.
- Smart background removal protects foreground detail against an edge-connected uniform background. Previous semantic-only AI mode remains available. Mask recovery, feathering and brush hardness controls preserve original RGB and existing transparency.
- Compatible jobs-table migration, corrected copying of campaigns with multiple materials, bounded512KiB project state to accommodate responsive layers. Unused duplicated material metadata removed from scene content.

## Evidence

- Full backend suite: **44 passed**.
- Node suites: linked format synchronization, frontend materials/undo and upload partial success/retry all pass; frontend syntax passes.
- Browser canvas harness: **14/14 passed**, including multiple products/Elements, clean outputs, CTA pixels, responsive style/geometry and mask adjustments/undo.
- Isolated actual app in Codex in-app browser:3 products +2 Elements; CTA rounding edited on master propagates to300×250 and300×600, survives save/reopen, and an edit on portrait propagates back to master. Undo after switching formats restores prior35% rounding. No browser console errors observed.
- Select/clear-all controls exercised for formats and compositions. Browser generated **43 images** across19 selected format presets with3 text variants. Every image filename matches decoded dimensions and every file respects its profile byte limit. ZIP has repeated dimension basenames in separate variant folders.
- Smart processing and mask dialog exercised using a product with a cable; recovery15%, feather1px and brush hardness50% saved as transparentPNG. Only the corresponding product changed; other products/Elements remained selected.
- Thin-cable deterministic model probe: old semantic-only mask median21/255 alpha, smart255/255 on tested4px cable. This measures the tested fixture, not every photograph.
- Isolated VM20MP warm-model probe:5000×4000 output,4.85s, peakRSS934.3MiB,127818bytes; below1500MiB service cap.
- Production authenticated smoke: deployedJS matches local tested files;3 product uploads, Element upload, smart job(1.92s on900×720 fixture), persisted campaign state,43-image ZIP with dimension filenames passed. Temporary campaign and brand removed by test cleanup.
- Service active, no unexpected restarts; approximately3.3GiB free disk after release.

## Review findings resolved

Independent review reproduced and fixed stale material IDs in duplicated campaigns, isolated master edits leaking into lazy formats, geometry crossing destination bounds, source-only undo losing destination overrides, and undo history clearing on format changes. A measured modest responsive state exceeded the old256KiB limit, motivating the512KiB bound. No Git repository exists locally; review used the actual module contracts and approved requirements.

## Limits

Smart can retain shadows on simple backgrounds; use AI-only mode or manual correction when appropriate. Fine detail on complex backgrounds still needs visual checking. RDA/PMax intentionally exclude Element overlays. Text-area/readability warnings remain advisory; platform acceptance is not guaranteed. Existing upload20MP working-image cap and seven-day retention remain in force.
