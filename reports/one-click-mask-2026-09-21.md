# One-click removal of remaining background

Implemented the approved contiguous area tool in the existing mask editor. Polish UI: **Popraw maskę → Usuń obszar**, color tolerance 0–100% (default 8%), existing undo/restore and PNG save. Brush controls are hidden in area mode. Changing tolerance affects the next click; the hint explains undo and retry.

## Behavior

Four-neighbor scanline fill compares original RGB to the fixed clicked color. Original and current transparency form boundaries. Only alpha changes, with original dimensions and RGB retained. One successful click adds one undo step and commits a new refinement baseline; transparent/outside clicks are no-ops. Typed work stack is bounded at512KiB and traversal at1M spans; an excessive-complexity failure leaves the entire mask/history unchanged and shows a Polish error.

## Verification

- Actual browser harness:21 passed, including five new area-removal cases and optional20MP test. Covers actual pointer mapping, enclosed white area, disconnected white detail, diagonal separation, fixed-seed gradient, tolerance, source/current alpha, undo/reset/refinement and PNG export.
- Actual20MP uniform region removed in456ms in the local browser, including mask commit; full-image undo passed. This is one machine/fixture, not a universal timing guarantee.40MB byte masks plus existing editor/canvas buffers and regionRGBA; stack at most512KiB.
- Independent reviewer:1,500 randomized fixtures agree with a separate DFS oracle; complex4.25MP pattern safely aborts without mutation.
- Three existing Node suites passed: material selection/replacement and SVG guards, format synchronization, uploads/retries. JS syntax checks passed.
- Full backend suite:90 passed in15.69s.
- Real local UI: open cutout → area mode → click enclosed white region → undo restores → change tolerance → click → save PNG → save campaign → reload → reopen saved PNG. Transparent pocket persists. No original user image was altered.
- Standards and specification reviews found no release blockers.

## Deployment

Release:/home/ubuntu/google-ads-assets/releases/20260921-143618
Service:google-ads-assets.service; active/running,0 unexpected restarts after deployment.
Production static app.js/canvas.js/sync.js byte comparison passed. The PNG saved in the actual browser was uploaded through the authenticated production asset endpoint in a temporary campaign;800×600 dimensions, pocket alpha0 and unchanged dark product pixels verified after download. Campaign selected-material state persisted. Temporary campaign/assets/brand were removed after the check.

First local HTTP verification timed out because browser test tabs used the local server connection cap; closing test tabs released connections and the same check passed. No production mutation occurred in that failed attempt.

The attached monitor-arm image was a screenshot; fixtures reproduce its enclosed-white-background symptom. No claim is made that the original product asset was tested. Connected product pixels similar to the selected background can be included at high tolerance; lower tolerance/undo/restore remain available.
