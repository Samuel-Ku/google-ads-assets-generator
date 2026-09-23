## Parent

[Spec #1: delete campaign images, preserve PMax text, and add editable shapes](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/1)

## What to build

Make Performance Max preserve the visible headline, description and CTA from a Campaign Composition through editing, preview, saving and real image export. Add a visible saved choice between Composition with text and Clean image, with consistent behaviour across all three existing PMax aspect ratios.

This slice delivers the primary text pair end to end. The UI and export count must clearly describe that scope until “Export composed PMax A/B text variants” adds automatic A/B variants; do not imply that all text combinations are already rendered.

Introduce the smallest shared profile/mode rendering decision before changing behaviour, so editing, adaptation, synchronization and export cannot independently strip different layers. Keep this refactoring inside the complete user-facing slice.

## Acceptance criteria

- [ ] The Polish UI exposes and saves the per-campaign PMax image mode. New campaigns default to composed mode; existing campaigns with no saved setting keep their prior clean output until the editor changes it.
- [ ] Composed PMax editing, previews and exported pixels preserve the primary headline, description and CTA, including direct text edits, as well as all other currently supported visible composition layers.
- [ ] Clean PMax still contains only products/background. RDA stays clean and standalone logo exports stay logo-only; the UI accurately explains excluded overlays.
- [ ] All three PMax aspect ratios adapt without stretching photos or silently dropping text. Text-fit, bounds, image type, dimensions and existing file-size checks apply consistently to preview and export.
- [ ] Linked edits respect the synchronization switch, while isolated changes preserve unrelated format overrides. Editing a clean profile never removes full layers from composed PMax.
- [ ] Composed → clean → composed preserves saved composed edits. Mode-specific adjustments and the full source composition remain separate; a cached clean scene cannot replace the composed source.
- [ ] Save/reopen, version restoration and Team Template save/apply preserve the mode-aware behaviour. Old template PMax overrides remain readable and resolve correctly under the destination campaign's selected mode.
- [ ] The real ZIP contains the selected PMax rendering mode under unambiguous profile/composition/mode/variant paths, dimension-only image basenames and a manifest identifying mode. Preview, count and delivered primary-pair files agree.
- [ ] Separate short headlines, long headline, descriptions, CTA information and business name remain available in the text CSV. The UI makes that file easy to find without describing it as an automatic Google Ads import format.
- [ ] Existing clean-image deduplication and legacy exports remain compatible. Present overlay guidance as guidance, with no blanket text-overlay rejection or claim that validation guarantees ad approval.
- [ ] An isolated browser journey verifies visible text in exported PMax pixels, clean/composed switching, all aspect ratios, reload, mixed-profile export and Team Template reuse. Existing synchronization, recipe and export API tests cover the corresponding compatibility boundaries.

## Blocked by

None — can start immediately.

Coordination: this ticket and “Add reusable rectangle and square Shape layers” may start independently. Whichever lands second verifies all then-supported native shapes through PMax mode switching, Team Template reuse and real export. This is an integration responsibility, not a blocking edge.

