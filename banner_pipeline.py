"""
Self-hosted Google Ads banner batch generator.

Workflow:
  materials/          -> your source photos/images
  config.yaml         -> your ad texts + brand settings
  output/<campaign>/   -> generated PNGs in all standard sizes + manifest.csv + zip

Requirements:
  pip install playwright pillow jinja2 pyyaml
  playwright install chromium

Run:
  python banner_pipeline.py config.yaml
"""

import asyncio
import csv
import io
import shutil
import sys
import zipfile
from pathlib import Path

import yaml
from jinja2 import Template
from PIL import Image
from playwright.async_api import async_playwright

# ---- Google Ads image specs: (width, height, max_kb, folder_tag) ----
SIZES = [
    (1200, 628, 5120, "responsive_landscape"),
    (1200, 1200, 5120, "responsive_square"),
    (960, 1200, 5120, "demandgen_vertical"),
    (1200, 300, 5120, "logo_landscape"),
    (300, 250, 150, "medium_rectangle"),
    (336, 280, 150, "large_rectangle"),
    (728, 90, 150, "leaderboard"),
    (970, 90, 150, "large_leaderboard"),
    (970, 250, 150, "billboard"),
    (160, 600, 150, "wide_skyscraper"),
    (300, 600, 150, "half_page"),
    (320, 50, 150, "mobile_leaderboard"),
]

TEMPLATE_HTML = Template("""
<html><head><style>
  * { margin:0; padding:0; box-sizing:border-box; font-family:'Arial', sans-serif; }
  body { width:{{w}}px; height:{{h}}px; overflow:hidden; position:relative; }
  .bg { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
  .overlay { position:absolute; inset:0; background:linear-gradient(180deg, rgba(0,0,0,0) 40%, rgba(0,0,0,0.65) 100%); }
  .content { position:absolute; bottom:{{pad}}px; left:{{pad}}px; right:{{pad}}px; color:#fff; }
  .headline { font-size:{{headline_size}}px; font-weight:800; line-height:1.1; margin-bottom:{{gap}}px; }
  .desc { font-size:{{desc_size}}px; font-weight:400; opacity:0.9; margin-bottom:{{gap}}px; }
  .cta { display:inline-block; background:{{brand_color}}; color:#fff; font-weight:700;
         font-size:{{cta_size}}px; padding:{{cta_pad}}px {{cta_pad_h}}px; border-radius:6px; }
  .logo { position:absolute; top:{{pad}}px; left:{{pad}}px; height:{{logo_h}}px; }
</style></head>
<body>
  <img class="bg" src="file://{{bg_image}}">
  <div class="overlay"></div>
  {% if logo %}<img class="logo" src="file://{{logo}}">{% endif %}
  <div class="content">
    <div class="headline">{{headline}}</div>
    {% if show_desc %}<div class="desc">{{description}}</div>{% endif %}
    {% if show_cta %}<div class="cta">{{cta}}</div>{% endif %}
  </div>
</body></html>
""")


def scaled_layout(w, h):
    """Pick font sizes proportionally so tiny banners (320x50) stay readable/legal (<=20% text area)."""
    scale = min(w, h) / 250
    return dict(
        pad=max(4, int(6 * scale)),
        gap=max(2, int(4 * scale)),
        headline_size=max(9, int(20 * scale)),
        desc_size=max(7, int(12 * scale)),
        cta_size=max(8, int(13 * scale)),
        cta_pad=max(2, int(5 * scale)),
        cta_pad_h=max(6, int(12 * scale)),
        logo_h=max(14, int(28 * scale)),
        show_desc=h >= 200,
        show_cta=w >= 160,
    )


async def render_png(page, html_str, w, h) -> bytes:
    await page.set_viewport_size({"width": w, "height": h})
    await page.set_content(html_str, wait_until="load")
    return await page.screenshot(type="png")


def compress_to_limit(png_bytes: bytes, max_kb: int, fmt="JPEG") -> bytes:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    quality = 90
    while quality > 20:
        buf = io.BytesIO()
        img.save(buf, format=fmt, quality=quality, optimize=True)
        if buf.tell() <= max_kb * 1024:
            return buf.getvalue()
        quality -= 10
    return buf.getvalue()  # best effort at lowest quality


async def generate_campaign(campaign: dict, materials_dir: Path, out_root: Path):
    name = campaign["name"]
    out_dir = out_root / name
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = []

    bg_image = str((materials_dir / campaign["background_image"]).resolve())
    logo = campaign.get("logo")
    logo = str((materials_dir / logo).resolve()) if logo else None

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        for w, h, max_kb, tag in SIZES:
            layout = scaled_layout(w, h)
            html_str = TEMPLATE_HTML.render(
                w=w, h=h, bg_image=bg_image, logo=logo,
                headline=campaign["headline"], description=campaign.get("description", ""),
                cta=campaign.get("cta", "Learn more"),
                brand_color=campaign.get("brand_color", "#1a73e8"),
                **layout,
            )
            png_bytes = await render_png(page, html_str, w, h)
            fmt = "PNG" if tag.startswith("logo") else "JPEG"
            final_bytes = compress_to_limit(png_bytes, max_kb, fmt=fmt) if fmt == "JPEG" else png_bytes
            ext = "jpg" if fmt == "JPEG" else "png"
            fname = f"{name}_{w}x{h}_{tag}.{ext}"
            (out_dir / fname).write_bytes(final_bytes)
            manifest_rows.append({
                "file": fname, "width": w, "height": h,
                "size_kb": round(len(final_bytes) / 1024, 1),
                "placement": tag, "campaign": name,
            })

        await browser.close()

    manifest_path = out_dir / "manifest.csv"
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "width", "height", "size_kb", "placement", "campaign"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    zip_path = out_root / f"{name}_banners.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out_dir.iterdir():
            zf.write(f, arcname=f.name)

    print(f"[OK] {name}: {len(manifest_rows)} files -> {zip_path}")


async def main(config_path: str):
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    materials_dir = Path(cfg["materials_dir"])
    out_root = Path(cfg.get("output_dir", "output"))
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    for campaign in cfg["campaigns"]:
        await generate_campaign(campaign, materials_dir, out_root)


if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    asyncio.run(main(config_file))
