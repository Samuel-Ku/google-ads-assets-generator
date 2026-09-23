# SVG support — verified 2026-09-21

Release: `/home/ubuntu/google-ads-assets/releases/20260921-142308`, http://192.168.15.42:8765.

User approved native-vector SVG support in the popup before dependency installation and deployment. Campaign materials and Brand Kit logos accept static SVG up to 2 MiB. Sanitized SVG remains vector; banners export as JPG/PNG at target resolution. UI labels SVG files, explains font outlines and keeps raster background-removal/mask controls unavailable for vectors. Background API rejects SVG before queueing.

## Validation

- Full backend suite:85 passed. Afterwards5 additional focused cases passed for embedded-raster sanitization, MIME spoofing and absolute-unit dimensions (no further production code changes).
- Three Node suites passed: frontend materials/undo including SVG, upload/retry, cross-format sync.
- Browser harness:15 passed, including SVG Element and logo with gradient, clipping, class styles, transparency, thin-line scaling from24-unitSVG to1200px, PNG readback and JPEG flattening.
- Actual local app browser: authenticated HTTP SVG with the SVG-specific sandbox CSP rendered to Canvas and exported at1200px, with pixel assertions. Campaign showed SVG label and omitted raster processing controls. All19 format presets generated43 images using SVG logo and Element; no console errors.
- ZIP verified:43 images; both1200×1200 and1200×300 logo PNGs retain transparent pixels and the expected exact central color from the vector.
- Production authenticated smoke: all4 campaign material kinds accept retained SVG; MIME, intrinsic dimensions, restrictive CSP and SVG background rejection verified. Existing raster processing and43-image ZIP still pass. Deployed browser scripts match tested local versions. Temporary campaign/brand cleanup completed.
- Isolated service remains active, no unexpected restarts. New pure-Python dependencies: defusedxml0.7.1 and tinycss2 1.5.1, installed only in project venvs. No database migration for SVG.

## Boundary / review

Reject scripts/events, animation, foreignObject, DTD/entities, external href/CSSURLs/imports/font sources; static XML and CSS allowlists. XML size/nodes/depth, viewport, embedded raster pixels and direct local reference expansion are bounded. Cyclic href/attribute references rejected; CSS-class-derived paint cycles are not exhaustively modeled and rely on browser painting behavior. These are static images, never injected as markup into the editor DOM.

Review found and fixed missing inline-style allowlisting and extreme viewport arithmetic that would otherwise raise server errors. Source artwork and vectors keep their geometry; unsupported constructs yield a Polish error. Fonts are local browser fonts—outline lettering when exact custom-font reproduction matters.

Design references: [MDN SVG as an image](https://developer.mozilla.org/en-US/docs/Web/SVG/Guides/SVG_as_an_image), [defusedxml](https://pypi.org/project/defusedxml/), [tinycss2](https://pypi.org/project/tinycss2/1.5.1/). MDN distinguishes image-context restrictions from direct SVG navigation; per-file CSP covers the latter as well.
