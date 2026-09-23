## Problem Statement

Designers using Google Ads Assets Studio need three improvements to finish campaign assets without leaving the tool:

- Uploaded photos cannot be deleted individually. Deselecting a material or deleting its layer removes it from a composition but leaves the source file in the campaign and consumes storage.
- Performance Max images lose the composition's text. The current implementation intentionally produces clean PMax images and exports copy separately, so a designer's headline, description and CTA disappear from the rendered result.
- Designers cannot add basic geometric shapes directly. They must upload a separate graphic or work around the existing template decorations.

These gaps create repeated work, clutter campaign materials and make the relationship between the editor and exported files harder to understand.

## Solution

Extend the existing editor with explicit campaign-file deletion, a clearly labelled Performance Max composition mode that retains text, and native editable shapes.

Designers can delete unnecessary campaign materials after reviewing their impact, choose whether PMax images contain the full composition or clean imagery, and add shapes without uploading files. All three features work with saved campaigns, linked format edits and reusable team templates.

The specification is written in English. Product labels and messages remain Polish.

## User Stories

1. As a designer, I want a distinct Delete file action on a campaign material, so that I can remove an unwanted upload rather than merely hide its layer.
2. As a designer, I want to delete product photos, background images, cutouts and uploaded Elements, so that all campaign image materials can be managed consistently.
3. As a designer, I want SVG campaign materials to support the same deletion action, so that vector uploads do not become permanent clutter.
4. As a designer, I want deletion to identify the file and affected compositions before I confirm, so that I understand what will change.
5. As a designer, I want the confirmation to identify any derived cutouts that will also be removed, so that dependent files are never deleted silently.
6. As a designer, I want to cancel deletion without changing my campaign, so that I can safely review its impact.
7. As a designer, I want deletion of a cutout to preserve its original photo and sibling cutouts, so that I retain independent alternatives.
8. As a designer, I want unrelated photos, text, styles and geometry to remain unchanged, so that cleaning materials does not undo my design work.
9. As a designer, I want every saved format and material selection to reflect deletion, so that the deleted image does not reappear in another size.
10. As a designer, I want a clear message if deleting a file makes an output incomplete, so that I can replace the missing material before export.
11. As a designer, I want released storage capacity to become visible after deletion, so that I know whether I can upload more files.
12. As a team member, I want stale edits to be detected during deletion, so that my action cannot silently overwrite another person's work.
13. As a designer, I want deletion to wait for affected background-removal work to finish, so that processing cannot recreate an image I just removed.
14. As a designer, I want undo and historical version restoration to explain unavailable deleted files, so that they never pretend to recover an image that no longer exists.
15. As a team member, I want shared templates to remain reusable after their source photos are deleted, so that material cleanup does not destroy the template library.
16. As a designer, I want to know that existing exported ZIPs remain separate snapshots, so that deleting a source image does not unexpectedly invalidate a previously delivered package.
17. As a designer, I want Performance Max images to retain the headline, description and CTA visible in the composition when I choose a composed output, so that my message survives export.
18. As a designer, I want an explicit choice between composed and clean PMax images, so that the output matches my intended use.
19. As a designer, I want the editor, format previews and exported PMax files to use the same mode, so that text does not disappear only at export time.
20. As a designer, I want composed PMax outputs to preserve the composition's other visible layers, so that logos, Elements and shapes are not unexpectedly removed.
21. As a designer, I want clean PMax outputs to remain available, so that I can also prepare images without overlays.
22. As a designer, I want existing campaigns to retain their previous PMax output mode until I change it, so that reopening a campaign does not silently alter its deliverables.
23. As a designer, I want PMax text edits and format-specific adjustments to respect the synchronization switch, so that I can choose between linked changes and individual corrections.
24. As a designer, I want composed PMax text variants to appear in the export count and filenames, so that I know exactly how many files will be produced.
25. As a campaign editor, I want separate PMax text assets to remain included in the export package, so that image overlays do not replace the copy needed when assembling an asset group.
26. As a designer, I want mixed Display, RDA and PMax exports to apply each profile's selected rendering behaviour, so that changing PMax does not change my RDA files.
27. As a designer, I want to add a square, rectangle, circle, ellipse, triangle or diamond from the editor, so that I can create simple visual accents without uploading a graphic.
28. As a designer, I want a Shape to appear as an independent named layer, so that I can distinguish it from an uploaded Element and select it easily.
29. As a designer, I want to move, resize, recolour and adjust the opacity of a shape, so that it fits the composition.
30. As a designer, I want to reorder shapes behind or in front of other layers, so that I can build panels, highlights and decorative accents.
31. As a designer, I want squares and circles to keep their proportions, so that resizing or changing banner dimensions does not turn them into unintended rectangles or ellipses.
32. As a designer, I want to delete a shape and undo the change, so that experimenting with a layout is reversible.
33. As a designer, I want shapes to remain in other aspect ratios when format synchronization is enabled, so that my design does not lose decorative layers during adaptation.
34. As a designer, I want a shape edit to stay local when synchronization is disabled, so that a correction for one format does not disturb others.
35. As a team member, I want shapes and their styles to survive saving, reopening and version restoration, so that they behave like the rest of the composition.
36. As a team member, I want shapes to be included in saved team templates, so that a reusable layout retains its visual structure.
37. As a designer, I want brand-linked shape colours to follow the new campaign's Brand Kit while explicit custom colours stay unchanged, so that template reuse preserves the intended style.
38. As a designer, I want exported JPG and PNG files to match the shape geometry and transparency shown in the preview, so that the final creative is predictable.
39. As a team member, I want older campaigns and templates to continue working, so that these improvements do not force existing work to be recreated.

## Implementation Decisions

### Campaign material deletion

- Add a campaign-scoped authenticated deletion operation to the existing material API, requiring CSRF protection and the current campaign version. Editors retain the project's shared-campaign permissions. Brand Kit logos and fonts are excluded.
- Product photos, backgrounds, cutouts and uploaded Elements, including SVG, use the same deletion lifecycle. Removing a layer and deselecting a material remain separate, reversible composition actions; neither operation deletes a source file.
- The deletion confirmation shows the selected file, affected compositions and any derived descendants. Deleting an original removes its derived descendants only as part of this explicitly disclosed action. Deleting a derived file does not remove its parent or siblings.
- Reject deletion while an affected asset participates in a queued or running processing job. Check this under the existing processing/storage coordination so a job cannot race deletion and recreate output.
- Apply the operation to the latest version of the campaign: remove deleted asset selections and references from the base composition, every stored composition and format override. Preserve unrelated content and create a new authored campaign revision. Never automatically substitute another photo.
- Retain minimal unavailable/deleted metadata where historical references need to be explained; remove the actual file bytes and refresh storage usage. A completed deletion must make protected file downloads and new processing requests unavailable. A retry must not corrupt the campaign or delete unrelated files.
- Later saves, undo and version restoration must not resurrect usable references to deleted files. Reconcile unavailable material references and show a clear replacement warning. Historical campaign metadata is retained, but it does not promise recovery of physically deleted media.
- Deleting a file does not invalidate a content-free team template or erase previously generated ZIP snapshots. ZIPs keep their existing retention period; already downloaded copies are outside the application's control.

### Performance Max rendering

- Introduce an explicit per-campaign PMax image mode: **Composition with text** or **Clean image**. The mode applies consistently to PMax editing, adaptation, preview, export planning and final rendering.
- In composed mode, retain the selected campaign composition's text, logo, Elements and native shapes. In clean mode, retain the existing product/background-only rendering. Do not use one shared unconditional clean filter for both RDA and PMax.
- Preserve clean rendering for existing campaigns with no explicit saved mode. New campaigns expose composed mode as the default for this requested workflow. The mode is visible and saved; no silent migration of old exports is required.
- PMax composed outputs reuse the existing Display variant semantics: selected headlines × selected CTAs, with descriptions paired cyclically by headline index. There is no additional headline × description cross-product. Each combination is rendered and counted; the primary pair respects direct composition edits. Clean outputs remain independent of text variants and retain existing image deduplication behaviour.
- Keep mode-specific format adjustments separate from the complete source composition. Switching composed → clean → composed must preserve the composed text and edits; a cached clean override must never become the source for a composed output. Team-template PMax overrides must be resolved under the destination campaign mode, with a backwards-compatible representation for old clean overrides.
- Export paths distinguish profile, composition, rendering mode and variant while retaining dimension-only image basenames. Actual file dimensions, image type, byte limits and the existing frontend export-count cap continue to apply. The manifest identifies the chosen mode.
- Keep the existing separate text export available for PMax, including short headlines, long headline, descriptions and business name. Make its presence clear in the export summary. Overlay copy is not a substitute for these text assets, and CSV is not advertised as an automatic Google Ads import file.
- RDA remains clean and separate logo exports remain logo-only. Format synchronization must preserve full PMax layers only in composed mode, including when the user edits a clean format elsewhere in the same campaign.
- Reuse existing validation for text fit, clipping, dimensions and file size; visible overlays must not cause an automatic blanket rejection. Present current Google guidance accurately as guidance, not a guarantee of approval.

### Native shapes

- Add a native **Shape** layer concept distinct from an uploaded **Element**. The initial shape menu contains square, rectangle, circle, ellipse, triangle and diamond; these six primitives bound the requested “other shapes” scope.
- Use the existing editor's layer selection, pointer movement, resize handles, geometry controls, ordering, deletion, keyboard movement and undo. Add shape choice, fill and opacity controls. The initial fill follows the active Brand Kit accent; existing rectangle corner styling can be reused where supported.
- Squares and circles maintain equal dimensions in rendered pixels, including across rectangular canvases. Rectangles and ellipses can resize freely. Triangle and diamond geometry is generated from bounded numeric parameters rather than executable or arbitrary path data.
- Preserve a shape's stable identity, stacking order and geometry when adapting aspect ratios. Fix the existing adaptation behaviour that drops custom decoration layers instead of allowing the new shapes to disappear.
- Extend rendering, hit testing, validation, editor property allowlists, synchronization, template capture/instantiation and server recipe validation as one compatible contract. Keep legacy rectangle decorations and saved recipes readable. Campaign JSON and team-template recipes remain the persistence mechanisms; no separate shape file storage is needed.
- Preserve brand-colour tokens and manual colours through team-template reuse. Shapes consume no uploaded-material slots and create no dependency on source photos.
- Render shapes in Display and composed PMax outputs. Exclude them from clean RDA/PMax and logo-only outputs. The UI explains when a selected output mode excludes overlays.
- Contrast checks must not treat a triangle's or circle's entire bounding rectangle as a solid fill. Validate supported geometry and visible bounds without claiming to predict ad performance.

## Testing Decisions

- Use the existing isolated browser campaign journey as the primary acceptance seam: material upload → composition editing → format switching → save/reopen → actual ZIP export. Assert what the designer sees and downloads, rather than private helper structure or screenshot presence alone.
- For deletion, upload two independent photos, derive a cutout, use it in multiple compositions and overrides, cancel once and then confirm deletion. Verify the impact message, surviving unrelated files, cleared selections, absence in all future rendered outputs, unavailable file download and released storage. Reopen the campaign, attempt undo and restore an earlier revision; none may silently restore the deleted media.
- Extend the existing authenticated HTTP integration tests for deletion-specific permissions, CSRF, wrong-campaign identifiers, stale versions, processing-job races, descendant handling, retry behaviour and history reconciliation. These are observable API behaviours that cannot be proven by one browser account alone.
- For PMax, use recognisable text and verify pixels in the real exported images as well as the text CSV. Test both modes, composed → clean → composed switching without edit loss, all three existing aspect ratios, A/B variants, primary-pair edits, format synchronization on/off, save/reopen, saved team-template overrides and mixed-profile exports. Confirm old campaigns still use clean mode and text is not stripped between preview and download.
- For shapes, add all six primitives, change their fill/opacity, move and reorder them, remove one and undo. Check pixel proportions, transparent corners and stacking in rendered outputs. Switch between wide, square and tall formats and ensure custom shapes survive.
- Round-trip a composition containing shapes through campaign storage and a team template applied to another Brand Kit. Verify identity, geometry, manual styles and brand-linked colours, while unrelated templates and materials remain unchanged.
- Reuse the existing Canvas browser harness, format-synchronization tests, frontend material tests, recipe round-trip tests and authenticated template API tests for targeted regressions. Add no new public test-only endpoints or separate rendering engine.
- Test malformed or unsupported shape values, non-finite geometry and legacy recipes through the existing public validation boundaries. Verify rejection is controlled and leaves prior saved work intact.
- All automated and browser fixtures use isolated temporary data. Any later deployment checks use explicitly created test records and preserve real campaigns, accounts and files.

## Out of Scope

- Implementing or deploying the features as part of this specification-writing task.
- Paid AI generation, automatic copywriting, Bitrix24/Google Sheets integration, or direct publication to Google Ads.
- A full vector editor: freehand drawing, arbitrary paths, SVG node editing, boolean shape operations, general rotation, gradients, shadows and a new stroke/border system.
- Bulk deletion, a media trash/recovery service, or extending the existing seven-day file retention period.
- Brand Kit asset deletion, deletion of other campaigns' files, or rewriting immutable exported ZIPs.
- Predictive creative scoring or guarantees of Google Ads approval and campaign performance.

## Further Notes

- Vocabulary: a **Built-in Layout** is a responsive preset; a **Team Template** stores reusable layout/styles without source media or commercial copy; a **Material Slot** is a placeholder for a campaign material; an **Element** is an uploaded supporting graphic; a **Shape** is native editable geometry; a **Campaign Composition** contains the current campaign's bound materials, text and styling.
- Google currently permits PMax images with overlays and recommends including at least one image without overlays for each aspect ratio. This supports offering both rendering modes rather than presenting clean images as a universal PMax restriction. Source reviewed on 22 September 2026: [Google Ads Help — image assets for Performance Max](https://support.google.com/google-ads/answer/14530211?hl=en).
- The asset dependency policy, six-shape starter set and backwards-compatible PMax mode are implementation decisions synthesized from the requested outcomes and existing architecture. They are not claims that these capabilities already exist.
- Acceptance-scope check completed on 22 September 2026. The user explicitly selected text visible on PMax images, preserving the headline, description and CTA. The proposed editor → save/reopen → export acceptance flow was presented with that choice.
