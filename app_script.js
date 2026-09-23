// Place this file at: static/app.js

const variationsEl = document.getElementById("variations");
const template = document.getElementById("variation-template");
let variationCount = 0;

function addVariation() {
  variationCount++;
  const clone = template.content.cloneNode(true);
  const card = clone.querySelector(".variation");
  card.dataset.index = variationCount;
  clone.querySelector(".var-index").textContent = variationCount;

  const dropZone = clone.querySelector(".bg-drop");
  const input = clone.querySelector(".bg-input");
  const label = clone.querySelector(".bg-label");
  const preview = clone.querySelector(".bg-preview");

  setupFileDrop(dropZone, input, (file) => {
    label.textContent = file.name;
    const reader = new FileReader();
    reader.onload = (e) => {
      preview.src = e.target.result;
      preview.hidden = false;
    };
    reader.readAsDataURL(file);
  });

  clone.querySelector(".btn-remove").addEventListener("click", () => {
    card.remove();
    renumber();
  });

  variationsEl.appendChild(clone);
}

function renumber() {
  const cards = variationsEl.querySelectorAll(".variation");
  cards.forEach((card, i) => {
    card.querySelector(".var-index").textContent = i + 1;
  });
}

function setupFileDrop(dropZone, input, onFile) {
  dropZone.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    if (input.files[0]) onFile(input.files[0]);
  });
  ["dragover", "dragleave", "drop"].forEach((evt) => {
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.toggle("dragover", evt === "dragover");
    });
  });
  dropZone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) {
      input.files = e.dataTransfer.files;
      onFile(file);
    }
  });
}

// Logo drop
const logoDrop = document.getElementById("logo-drop");
const logoInput = document.getElementById("logo-input");
const logoLabel = document.getElementById("logo-label");
setupFileDrop(logoDrop, logoInput, (file) => {
  logoLabel.textContent = "✅ " + file.name;
});

document.getElementById("add-variation").addEventListener("click", addVariation);
addVariation(); // start with one

document.getElementById("generate-btn").addEventListener("click", async () => {
  const statusEl = document.getElementById("status");
  const resultsEl = document.getElementById("results");
  const btn = document.getElementById("generate-btn");
  resultsEl.innerHTML = "";
  statusEl.className = "";

  const cards = variationsEl.querySelectorAll(".variation");
  if (cards.length === 0) {
    statusEl.textContent = "Додай хоча б один банер.";
    statusEl.className = "error";
    return;
  }

  const formData = new FormData();
  if (logoInput.files[0]) formData.append("logo", logoInput.files[0]);

  let valid = true;
  cards.forEach((card, i) => {
    const bgFile = card.querySelector(".bg-input").files[0];
    const headline = card.querySelector(".headline-input").value.trim();
    if (!bgFile || !headline) valid = false;
    if (bgFile) formData.append(`background_${i}`, bgFile);
    formData.append(`headline_${i}`, headline);
    formData.append(`description_${i}`, card.querySelector(".description-input").value.trim());
    formData.append(`cta_${i}`, card.querySelector(".cta-input").value.trim() || "Learn more");
    formData.append(`brand_color_${i}`, card.querySelector(".color-input").value);
  });

  if (!valid) {
    statusEl.textContent = "Для кожного банера потрібні фото і заголовок.";
    statusEl.className = "error";
    return;
  }

  btn.disabled = true;
  statusEl.innerHTML = '<div class="spinner"></div>Генеруємо банери, зачекай кілька секунд...';

  try {
    const res = await fetch("/generate", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      statusEl.textContent = data.error || "Щось пішло не так.";
      statusEl.className = "error";
      btn.disabled = false;
      return;
    }

    statusEl.textContent = "";
    let html = `<div class="preview-grid">`;
    data.previews.forEach((p) => {
      html += `<div class="preview-item">
        <img src="${p.url}" alt="${p.headline}">
        <div class="caption">${p.headline}</div>
      </div>`;
    });
    html += `</div>`;
    html += `<div class="download-box">
      <div>✅ Готово! Створено ${data.total_files} файлів у всіх потрібних розмірах Google Ads.</div>
      <a class="btn btn-primary" href="${data.download_url}">⬇️ Завантажити ZIP для спеціаліста</a>
    </div>`;
    resultsEl.innerHTML = html;
  } catch (err) {
    statusEl.textContent = "Помилка з'єднання із сервером.";
    statusEl.className = "error";
  } finally {
    btn.disabled = false;
  }
});
