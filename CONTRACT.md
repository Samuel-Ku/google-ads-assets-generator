# Implementation contract (2026-09-21)

Approved scope: SPEC.md. Plain Flask + SQLite + Pillow backend; vanilla JS / Canvas frontend. Rendering takes place in browser, identical for editing and export. No server Chromium, no paid APIs, no external data integrations. All app assets self-hosted. Root owns deployment, background.py, integration and final verification. Backend owner owns app.py, storage.py (if needed), requirements.txt, tests/test_api.py. Frontend owner owns templates/index.html, static/app.js, static/style.css. Canvas owner owns static/canvas.js. Keep separate ownership; communicate contract changes.

## JSON and authentication

Every error: `{error: "Polish message", ...}`. Successful object endpoints return object directly; list endpoints `{items:[...]}`. `/api/session` GET -> `{user:null|{id,username,role},csrf_token}`. All modifying requests including login require `X-CSRF-Token`. JSON otherwise or multipart below. POST `/api/login` `{username,password}` -> `{user,csrf_token}`; POST `/api/logout`. POST `/api/account/password` `{current_password,password}`. Passwords hashed. Session secret persists privately. CLI `python app.py create-admin USERNAME --password-file PATH`; no public first-admin signup.

## Brands

GET `/api/brands` -> items. POST `/api/brands`, PUT `/api/brands/<id>` admin-only accepts `{name,color,secondary_color,text_color,font_family,tone,logo_asset_id?,font_asset_id?}`. Defaults #E76A25, #F4F1EC, #182021, `Arial`. Returns brand object. POST `/api/brands/<id>/assets` multipart `{file,kind:logo|font}` -> asset object; backend updates corresponding brand asset id. Fonts: TTF/OTF/WOFF/WOFF2, signature validated, content served with proper type. Brand objects contain `logo_url`, `font_url` as applicable, in addition to ids/settings.

## Campaigns

GET `/api/campaigns` -> items. POST `/api/campaigns` `{name,brand_id,brief,state:{}}` -> campaign. GET `/api/campaigns/<id>` -> full campaign `{id,name,brand_id,brief,state,version,created_at,updated_at,expires_at,expired,created_by,updated_by,assets:[...],exports:[...]}`. PUT same endpoint `{name,brand_id,brief,state,version}` requires exact current version; mismatch 409. All editors share campaigns. Every save records immutable state/author revision. GET `/api/campaigns/<id>/versions` -> items; POST `/api/campaigns/<id>/versions/<version>/restore` `{version: currentVersion}` -> new campaign revision (normal concurrency check). DELETE campaign endpoint can delete app-owned campaign/files with frontend confirmation (optional frontend).

`state` is bounded JSON; primary fields defined by frontend. Recommended `{confirmed:false,headlines:[],descriptions:[],ctas:[],long_headline:'',business_name:'',template:'split',product_asset_id:null,product_asset_ids:[],element_asset_ids:[],background_asset_id:null,sync_formats:true,template_scenes:{},scenes:{},selected_formats:[],scene:null}`. Commercial confirmation boolean required before export. State text values are user-authored, never trusted HTML. Any image src in scene is generated from local asset metadata, not remote URLs.

## Files / processing

POST `/api/campaigns/<id>/assets` multipart `{file,kind:product|background|element|cutout,parent_id?}` -> asset `{id,name,kind,url,width,height,size,parent_id?,campaign_id?,brand_id?,created_at}`. Images JPEG/PNG/WebP verified/decoded and sanitized; input limit <=12MiB / 60MP; sanitize sources above20MP to working images <=20MP while preserving aspect ratio, EXIF orientation and alpha. Sources at/below20MP retain dimensions. Reject source dimensions with code image_dimensions and corrupt data with code image_decode; no HTML uploads; SVG accepted through the static vector sanitizer described below. Strict export validation never resizes images. Assets protected by session, URL `/api/assets/<id>/file`, optional `?download=1`. Expired campaign media 410. Parent asset must belong to same campaign.

POST `/api/assets/<id>/remove-background` JSON `{method:"smart"|"ai"}` (default smart) -> job `{id,status:'queued',method}`. GET `/api/jobs/<id>` -> `{id,status:queued|running|done|error,method,error?,asset?}`. Single background processing thread. Backend imports `from background import remove_background` and calls `remove_background(input_path:Path, output_path:Path, *, method="smart")`; root implements inference. Mask editing is in browser: frontend uploads corrected PNG via campaign asset upload kind=cutout (or element for an Element),parent_id=<original asset id>. Do not discard original. GET `/api/storage` -> `{used_bytes,quota_bytes,free_bytes,reserve_bytes,can_upload,retention_days:7}`. Quota accounts for all app media incl brands, plus free-space reserve, checked before writes under process lock. Ephemeral partial files cleaned on errors. Cleanup expires only this app's campaign assets/exports after 7 days, retains brands and JSON history; fixed expiry from creation. Serialize capacity-changing work. Cap image/job count. Status messages in Polish.

## Exports / formats

GET `/api/formats` -> `{display:[...],rda:[...],pmax:[...],logos:[...]}` where each format `{id,label,width,height,max_bytes,profile}`. IDs suggested `display_300x250`, `rda_1200x628`, `pmax_960x1200`, `logo_1200x300`. Static JPG <=150*1024 bytes; assets JPG/PNG <=5120*1024. Add useful Display presets incl Polish 750x100/200/300. RDA:1200x628,1200x1200; PMax additionally960x1200. Logos1200x1200 and1200x300. RDA/PMax image rendering excludes overlaid logo/text/CTA; logo exports use only brand logo, contain, transparency. Record profile-specific field character/quantity checks, not blanket20% claims.

POST `/api/campaigns/<id>/exports` multipart: repeated `files` parts; `manifest` JSON array indexed with files `{name,format_id,width,height,variant,template}`; `texts` JSON `{headlines:[],descriptions:[],ctas:[],long_headline:'',business_name:''}`; `version` current campaign version. Require state.confirmed true, unexpired campaign and no revision conflict. Validate actual dimensions/type/size against server format allowlist; cap100 files/80MB (frontend stricter). Build ZIP atomically without permanently storing each export image; include manifest.csv and texts.csv with formula escaping. Returns `{id,url,filename,size,created_at,expires_at,file_count}`. GET `/api/exports/<id>/download` authenticated. Campaign exports field same metadata.

## Admin

GET `/api/users` -> items admin-only. POST `{username,password,role:'editor'|'admin'}` -> user. PUT `/api/users/<id>` `{role?,active?,password?}`. Never expose hashes. Protect last active admin. Admin can reset password. Render team admin screen with forms. Auth rate limit and CSRF essential. Configure single process threaded production server (waitress) to share bounded queue/storage locks.

## Canvas module API

`static/canvas.js` classic script exposes `window.StudioCanvas`.
- `templates`: `[{id:'split'|'spotlight'|'minimal'|'catalog'|'benefits'|'label'|'backdrop'|'bundle'|'bold',label,description}]`.
- `makeScene({template,width,height,brand,products:[],elements:[],product,background,headline,description,cta,clean=false})` -> scene. products/elements are arrays of asset objects with url,id,parent_id; product remains the legacy single-product fallback. Background is one asset. Brand object above. Scene `{width,height,background,layers:[...]}`.
- Layer `{id,type:'text'|'image'|'rect',role:'product'|'background'|'logo'|'headline'|'description'|'cta'|'decoration'|'element',x,y,w,h,src?,asset_id?,text?,color?,fontFamily?,fontSize?,fontWeight?,align?,opacity?,fit:'contain'|'cover',cropX?:0.5,cropY?:0.5}`. Positions/sizes normalized0..1; fontSize is in pixels of scene.height reference, adaptScene scales proportionally or regenerates suitable template. Preserve real image aspect via contain/cover, no image regeneration.
- `async render(canvas,scene,{selection:null}={})`; selected layer decorations not exported.
- `adaptScene(scene,width,height,{clean=false}={})` -> adapted clone, keep layer roles and edited text; reflow to horizontal/portrait, prevent stretching.
- `async renderBlob(scene,{type:'image/jpeg'|'image/png',maxBytes,quality:.92}={})` -> `{blob,warnings}`; enforce file size or throw Polish error. `validate(scene)` -> array `{level:'error'|'warning',message,layerId?}` (overflow/bounds/emptyimages/minfonts/text area advisory).
- `new Editor(canvas,{scene,onChange(scene),onSelect(layer)})`; methods `setScene`, `getScene`, `select(id)`, `updateSelected(props)`, `removeSelected`, `addLayer(layer)`, `destroy`. Pointer drag and resize handles, keyboard move/delete, selection update. Normal rendering must not rely on UI elsewhere. Frontend provides layer/property controls and undo via scene history.
- `new MaskEditor(canvas,{originalUrl,cutoutUrl,onChange,onError})`, await `.ready`; methods `.setBrush(mode:'erase'|'restore'|'area',size:number,hardness=.72)`, `.setAreaTolerance(percent:0..100)`, `.removeArea(x,y)` -> removed pixel count, or 0 for no-op/failure; other methods: `.applyRefinement({recovery:0..100,feather:0..3})`, `.getRefinement()`, `.undo()`, `.reset()`, `.exportBlob()` -> PNG; preserve original RGB, editable alpha; display checkerboard via CSS. Canvas natural dimensions (possibly source normalized) and pointer CSS scaling correctly handled.

## Frontend

Polish UI. Useful app chrome, campaign list, brand/admin screens, campaign tabs Materiały / Kompozycja / Eksport / Historia. Visible storage quota and deletion date. No paid AI buttons. Material upload + cutout mask modal; manual brief/text variants and required commercial confirmation. Nine built-in canvas previews and shared saved templates, choose template, visual layer editor & properties, all output formats preview and overrides; save state with version. Export images generated in browser with same canvas module, clean RDA/PMax images, logos separately, then server ZIP. Formula-safe texts server side. Loading/error/empty/expired/session-timeout states. Respect admin-only brand editing. Do not inject user values into innerHTML without escaping. Use fontFace for uploaded brand font.

## Validation / deployment

Backend unit/integration tests use tempfile data roots (never production retention tests). Root performs real browser journey incl upload/mask/edit/export, dimensions/size, role/session/version errors. Source control currently absent; don't force git. Deployment dedicated `/home/ubuntu/google-ads-assets`, private data directory outside source, separate service and free LAN port; existing services untouched. Resource footprint measured before install, no Docker/Chromium needed. Root supplies private bootstrap admin credentials via a local access note, never logs passwords. User explicitly approved implementation and deployment after full interview.

## Editor extension (2026-09-21)

Multiple product and Element selections are independent; each has its own stable layer. A replacement cutout replaces only the matching original in all saved scenes. Clean RDA/PMax retains products and background, excluding text, logos, CTA and Elements. CTA styles include `cornerRadius` (0..0.5 of its shorter side), border width/color and fill.

`StudioSync.applyEdit(state,{template,formatId,before,after,masterScene,formats,adaptScene})` propagates changed properties within one composition by default. Geometry uses relative motion/scale and each target's dimensions; unrelated format corrections remain. Logo outputs are independent. Switch off `sync_formats` for isolated edits. UI undo restores the linked edit state, including prior format adjustments.

Export has global select/clear controls for formats and compositions. ZIP paths are `<profile>/<template>/<variant>/<width>x<height>.<ext>`; dimensions are validated server-side, duplicate paths rejected. Different variants can share the same dimension-only basename.

Smart local background removal combines the existing semantic mask with edge-connected uniform-background detection to protect thin details. Complex backgrounds fall back to the model. AI-only mode retains the previous method. Existing source transparency and RGB are preserved. Mask controls add recovery, feather and brush hardness; preview and manual checking remain necessary.

## SVG input

`svg_media.sanitize_svg` uses defusedxml and tinycss2 to retain bounded static vectors. Input/output cap2MiB;5000XMLnodes/depth48; local href/use references reject cycles and excessive expansion. Allows basic shapes, paths, text, gradients, clip/mask, static filters, local definitions and class/inline CSS. No scripts/events/animation/foreignObject, DTD/entities, remote references, imported styles or fonts. Embedded raster images are decoded/sanitized and limited in aggregate. Root intrinsic dimensions derive from viewBox/absolute units; normalized viewport<=8192peredge/20MP with original viewBox preserved.

Asset JSON now includes `mime`. SVG stored as.svg and served only through authenticated asset URLs with image/svg+xml, nosniff and SVG-specific sandbox CSP; the app-wide header hook preserves this policy. Download name ends.svg. Canvas treats SVG as an image, retaining vectors until target-size rendering. Browser background/mask controls are omitted for SVG, and background API rejects it before queueing. Advert/export upload validation continues to require raster formats.

## One-click mask correction

`MaskEditor.setBrush('area', ...)`, `setAreaTolerance(percent)` and `removeArea(x, y)` provide four-connected fixed-seed RGB area removal. Only current visible source pixels participate. Candidate byte masks and a bounded typed scanline stack keep failure transactional; onError surfaces a Polish explanation. Each successful area operation is one undo step and a fresh refinement baseline; no-op clicks preserve history/settings. UI shows tolerance instead of brush controls in this mode. Original RGB and raster dimensions are unchanged; saved PNG uses the existing authenticated asset path and selected-material replacement. Tests include actual pointer events, alpha/RGB/undo/export, complexity rollback and an optional20MP browser case.


## Reusable templates

`GET /api/templates` returns active shared recipes; `?include_archived=1` includes archived. `POST /api/templates` accepts `{name,recipe}` and returns201. `PATCH /api/templates/<id>` accepts `{archived:boolean}`, author/admin only. Items include id/name/recipe/created_by/author_name/created_at/archived/can_manage. Auth and CSRF follow existing APIs. `shared_templates` has no source campaign dependency. Limits:100 total,256KiB recipe,100 layers/scene,20 format overrides; strict schema rejects asset IDs, URLs, old texts, resources and nonfinite geometry.

`StudioTemplates.capture({master,formats})` returns `{version:1,base_template,master,formats}` containing geometry, order, style and numbered material slots only. `instantiate(recipe,{brand,products,elements,background,headline,description,cta})` returns `{master,formats,missing,warnings}` bound to current campaign. Brand palette/font references use tokens; explicit custom styles remain. Missing images retain a `missingSlot` role:index marker and block export until supplied or removed.

Applied recipes use campaign keys `team-<libraryId>` in `state.applied_templates`, `template_scenes`, `scenes`, `template` and `selected_templates`. Each scene's `template` remains the built-in responsive base ID. Applying stores bound scene copies; archiving a recipe leaves existing campaign scenes intact. Undo, format synchronization and export operate on the campaign composition key. Saving a template stores a new immutable recipe, not a live link.
