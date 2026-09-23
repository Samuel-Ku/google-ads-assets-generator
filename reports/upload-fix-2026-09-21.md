# Large source upload correction — 2026-09-21

Deployed release: `/home/ubuntu/google-ads-assets/releases/20260921-121932`.

## Reproduction and cause

A valid 6000 × 4000 JPEG produced the screenshot's exact “Nie można odczytać obrazu…” error. Pillow's decompression warning fired during `Image.open`, before the application's explicit20MP check, and the general decode handler mislabeled it as corrupt input. A valid5000 × 4000 image succeeded;5000 × 4001 failed. The exact stock image shown in the screenshot was not available for inspection, so its specific dimensions/corruption status remain unverified.

## Behavior

- Accept source JPEG, PNG and WebP up to12MiB and60MP. Fit sources above20MP into working images at or below20MP, preserving aspect ratio, orientation and alpha. Smaller sources retain their dimensions. JPEG sanitization remains quality95; export dimensions/encoding rules are unchanged.
- Keep the hard source guard and serialized image processing. Distinguish dimension errors (`image_dimensions`) from corruption (`image_decode`). Strict export validation rejects oversized images instead of silently resizing them.
- Retain partial upload results and the failing filename/error. Clear the file input so selecting the same file again works, and preserve the chosen material type through upload and rerender.
- Full source files stay with the user. Working20MP images provide ample sampling resolution for current output presets; deep cropping can still expose a source-resolution limit.

## Verification

- Before the backend change, new regressions reported4 failed /3 passed. After the change, `.venv/bin/python -m pytest -q tests` reported30 passed in10.80s.
- `/Users/MARKETING1/.nvm/versions/node/v22.22.0/bin/node tests/upload-handler.cjs` passed. The harness executes the actual upload handler with DOM/API stubs. `node --check static/app.js` passed.
- On the Ubuntu VM, a60MP RGBA PNG normalized to5773 ×3464 in5.21s with930.8MiB peak RSS. Repeating after warming the local background-removal model took4.98s with1249.5MiB peak RSS, within the existing1500MiB service limit. These are bounded test measurements, not throughput guarantees.
- Through the deployed HTTP API, a24MP JPG uploaded, decoded, persisted and downloaded successfully as5476 ×3651. Separate over60MP and corrupt uploads returned their respective400 error codes without creating assets. The sequence took1.75s.
- Production tests used their own temporary campaign and brand and removed only those test records/files afterward. Existing user campaigns, Brand Kits and accounts were preserved.
- Service active with zero unexpected restarts; observed peak during the24MP HTTP test was about280MiB, about3.3GiB disk free after deployment.
- Chrome UI inspection was blocked by an open extension UI. No fresh browser upload/visual acceptance is claimed for this patch; server HTTP integration and the actual frontend handler were verified independently.
