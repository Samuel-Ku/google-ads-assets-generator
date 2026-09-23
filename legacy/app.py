"""
Web frontend for the banner pipeline.
Place this file next to banner_pipeline.py.

Folder layout expected:
  app.py
  banner_pipeline.py
  templates/index.html
  static/style.css
  static/app.js
  jobs/            (auto-created, stores uploads + outputs per session)

Requirements:
  pip install flask playwright pillow jinja2 pyyaml
  playwright install chromium

Run:
  python app.py
Then open http://localhost:5000
"""

import asyncio
import shutil
import uuid
import zipfile
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

from banner_pipeline import generate_campaign

app = Flask(__name__)
JOBS_DIR = Path("jobs")
JOBS_DIR.mkdir(exist_ok=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    job_id = uuid.uuid4().hex[:10]
    job_dir = JOBS_DIR / job_id
    materials_dir = job_dir / "materials"
    output_dir = job_dir / "output"
    materials_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    logo_path = None
    if "logo" in request.files and request.files["logo"].filename:
        logo_file = request.files["logo"]
        logo_name = secure_filename(logo_file.filename)
        logo_file.save(materials_dir / logo_name)
        logo_path = logo_name

    variations = []
    index = 0
    while f"headline_{index}" in request.form:
        bg_file = request.files.get(f"background_{index}")
        if not bg_file or not bg_file.filename:
            index += 1
            continue
        bg_name = secure_filename(bg_file.filename)
        bg_file.save(materials_dir / bg_name)

        variations.append({
            "name": f"variation_{index+1}",
            "background_image": bg_name,
            "logo": logo_path,
            "headline": request.form.get(f"headline_{index}", ""),
            "description": request.form.get(f"description_{index}", ""),
            "cta": request.form.get(f"cta_{index}", "Learn more"),
            "brand_color": request.form.get(f"brand_color_{index}", "#1a73e8"),
        })
        index += 1

    if not variations:
        return jsonify({"error": "Додай хоча б одну варіацію з фото та заголовком."}), 400

    async def run_all():
        for v in variations:
            await generate_campaign(v, materials_dir, output_dir)

    asyncio.run(run_all())

    # combine all per-variation zips + folders into one master zip
    master_zip_path = job_dir / "all_banners.zip"
    with zipfile.ZipFile(master_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in output_dir.iterdir():
            if folder.is_dir():
                for f in folder.iterdir():
                    zf.write(f, arcname=f"{folder.name}/{f.name}")

    previews = []
    for v in variations:
        folder = output_dir / v["name"]
        wide = next(folder.glob(f"{v['name']}_1200x628_*"), None)
        if wide:
            previews.append({
                "name": v["name"],
                "headline": v["headline"],
                "url": f"/preview/{job_id}/{v['name']}/{wide.name}",
            })

    return jsonify({
        "job_id": job_id,
        "previews": previews,
        "download_url": f"/download/{job_id}",
        "total_files": sum(1 for f in output_dir.rglob('*') if f.is_file()),
    })


@app.route("/preview/<job_id>/<variation>/<filename>")
def preview(job_id, variation, filename):
    path = JOBS_DIR / job_id / "output" / variation / filename
    return send_file(path)


@app.route("/download/<job_id>")
def download(job_id):
    path = JOBS_DIR / job_id / "all_banners.zip"
    return send_file(path, as_attachment=True, download_name="banners.zip")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
