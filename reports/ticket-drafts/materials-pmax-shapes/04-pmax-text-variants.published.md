## Parent

[Spec #1: delete campaign images, preserve PMax text, and add editable shapes](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/1)

## What to build

Extend composed Performance Max export from the primary text pair to the campaign's selected A/B combinations. Designers must see an accurate file count before export and receive the same combinations in previews, manifest and ZIP, without changing clean-image behaviour.

## Acceptance criteria

- [ ] Composed PMax follows the established Display rule: selected headlines × selected CTAs, with descriptions paired cyclically by headline index. It does not multiply the number of files by every description.
- [ ] The primary pair preserves direct composition edits; subsequent combinations use the campaign's current variant text with the same styles and format adjustments.
- [ ] Count, preview labels, rendering, manifest entries and ZIP paths consistently identify each composition, PMax mode, format and variant. Dimension-only basenames are preserved without collisions.
- [ ] The existing export-count cap is checked against the full planned output before rendering. Empty/default CTA behaviour matches the current Display workflow, and invalid or overflowing variant text is identified clearly.
- [ ] Clean PMax remains independent of text variants and retains its existing deduplication. A mixed Display/RDA/PMax selection yields the correct files and separate text CSV for every selected profile.
- [ ] An isolated browser export using at least two headlines, two CTAs and different descriptions proves expected counts and real image contents across all PMax aspect ratios. Existing export tests verify unique paths, manifest agreement, size/dimension validation and the cap.

## Blocked by

- [Preserve composition text in Performance Max images (#4)](https://github.com/Samuel-Ku/google-ads-assets-generator/issues/4)
