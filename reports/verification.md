# Verification — 2026-09-21

Status: deployed and checked at http://192.168.15.42:8765. Access is through the office LAN or corporate VPN.

## Automated checks

- Latest run: 30 Python tests passed — 20 API/storage tests, seven large-upload regressions and three background-processing tests. Initial deployment had23 tests.
- Upload handler regression passed in Node: partial success, retained filename/error, retry of the same file, retained material type and disabled controls during uploads. See upload-fix-2026-09-21.md.
- API coverage includes authentication, CSRF, roles, last-admin protection, session revocation, rate limiting, shared revision conflicts, restoration, uploads, font signatures, expiry, recovery, quota and free-space limits, bounded multipart uploads, concurrent processing, validated ZIPs and CSV formula escaping.
- Nine real-browser Canvas tests passed: adaptive templates, image proportions, clean RDA/PMax assets, background-only campaigns, edited layers, text/file guards, brand checks, mask RGB/undo/restore and CSS coordinates, keyboard editing and exports without selection handles.
- JavaScript syntax checks passed. All eight state markers found in the static coverage check; see state-coverage.json. This is supplementary evidence, not a substitute for browser testing.

## Browser acceptance

Using Codex CUA and a separate local test account, completed:

1. Login and creation of Brand Kit with a logo.
2. Campaign creation, manual brief and Polish text variants, offer confirmation.
3. Upload of the camera photo from the user's public catalog example.
4. CPU background removal, visual preview, erase/restore strokes and undo, saving a transparent PNG.
5. Template selection, headline editing, keyboard movement and a separate CTA edit for the 320 × 100 format.
6. Browser rendering and server ZIP export of 31 images.
7. Reloading saved work and restoring an earlier version as a new revision, retaining history.

The final ZIP contained 24 Display JPGs, five clean RDA/PMax JPGs and two transparent logo PNGs, plus text/manifest/validation tables and instructions. All image dimensions matched their profiles. The largest Display file was 14,997 bytes, below 150 KiB. The custom CTA was retained in the relevant format. Logo and clean PMax outputs were visually inspected.

Desktop 1280 × 800 and mobile 390 × 844 were inspected. Long ZIP names initially caused horizontal overflow and were fixed. The final mobile document width equaled the available viewport width (375 px, excluding the browser scrollbar). Screenshots were inspected through CUA; no private screenshot was uploaded to an external service.

Browser tests found and resolved constructor precedence errors that initially prevented Editor/MaskEditor initialization, plus compact CTA fields. Independent review found and resolved database quota accounting, concurrent image-processing memory limits and partial PMax warnings.

## Production checks

- Ubuntu 24.04.5, Python 3.12, isolated pinned environment: 182 MiB.
- Model U²-NetP: 4,574,861 bytes. SHA256 matches the pinned checksum and upstream MD5. Apache 2.0 license and provenance included in third_party/.
- Standalone VM processing of 1500 × 1125: 2.09 s including cold load, peak RSS 377.75 MiB, no swap.
- Through the deployed service: admin authentication, all 19 format presets, upload, background removal and authenticated ZIP download passed. The processing/check sequence took 2.94 s. Temporary test campaigns and brand were removed; the team starts with an empty workspace.
- Service enabled for boot, no unexpected restarts or warnings. Approximately 3.4 GiB free disk remained; measured service peak after processing was about 369 MiB.
- Data quota 1 GiB, free-space reserve 1 GiB. Quota includes media, temporary uploads, SQLite and journal files. Heavy image operations are serialized.
- Session/account persistence checked across a service restart. Credentials stored in the local mode-600 ACCESS-PRIVATE.txt; bootstrap password removed from VM.
- Existing nginx sites and other services were not changed.

## Explicit scope and omitted checks

- No public DNS/TLS, paid API, external data integration or ad publishing was configured. Internal access uses HTTP on the private VM address; it is not intended for public port forwarding.
- Backups of media are not configured in the constrained pilot. Export final files within the visible seven-day window. Brand Kit and metadata persist.
- SEO, analytics, sitemaps and public indexing checks do not apply to this authenticated internal tool.
- The skill's standalone Playwright script was skipped: browser interaction must use CUA. Equivalent browser acceptance was performed as described above.
- This workspace has no Git repository. Review used approved SPEC.md/CONTRACT.md and the preserved original prototype in legacy/ instead of a Git diff.

Rollback and operator guidance: ../DEPLOY.md. Current runtime release: /home/ubuntu/google-ads-assets/releases/20260921-142308. Upload follow-up evidence: upload-fix-2026-09-21.md.

Editor extension evidence: [enhancements-2026-09-21.md](enhancements-2026-09-21.md), including automatic format synchronization and bulk export.

SVG input evidence: [svg-support-2026-09-21.md](svg-support-2026-09-21.md).
