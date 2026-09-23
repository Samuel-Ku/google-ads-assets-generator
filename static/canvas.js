/* Local, dependency-free composition renderer. Preview and export use the same code. */
(function (global) {
  'use strict';

  const templates = [
    {id: 'split', label: 'Podział', description: 'Wyraźna oferta po jednej stronie, produkt po drugiej.'},
    {id: 'spotlight', label: 'Produkt w centrum', description: 'Duże zdjęcie i krótki komunikat w spokojnej kompozycji.'},
    {id: 'minimal', label: 'Typografia', description: 'Mocny nagłówek, dużo przestrzeni i subtelny akcent marki.'},
    {id: 'catalog', label: 'Katalog produktów', description: 'Równorzędne produkty w siatce, wspólny nagłówek i CTA.'},
    {id: 'benefits', label: 'Produkt + korzyści', description: 'Duże zdjęcie i osobny panel na opis zalet.'},
    {id: 'label', label: 'Oferta z etykietą', description: 'Wyznaczone miejsce na własny Element, np. label promocji.'},
    {id: 'backdrop', label: 'Zdjęcie w tle', description: 'Własne tło z czytelnym panelem na treść oferty.'},
    {id: 'bundle', label: 'Zestaw z akcesoriami', description: 'Pierwszy produkt jest główny, kolejne tworzą zestaw dodatków.'},
    {id: 'bold', label: 'Mocny kolor', description: 'Kolor marki i kontrastowe pole produktu.'},
  ];
  const imageCache = new Map();
  const imageErrors = new Map();
  const fontCache = new Map();
  const renderVersions = new WeakMap();
  const clone = value => JSON.parse(JSON.stringify(value));
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const roleNames = {product: 'Produkt', element: 'Element', background: 'Tło', logo: 'Logo', headline: 'Nagłówek', description: 'Opis', cta: 'Przycisk', decoration: 'Dekoracja', shape: 'Kształt'};
  const layerName = layer => roleNames[layer.role] || 'Warstwa';

  function canvasElement(width, height) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    return canvas;
  }

  function checkedSize(width, height) {
    const w = Math.round(number(width)), h = Math.round(number(height));
    if (w < 1 || h < 1 || w > 8192 || h > 8192 || w * h > 20000000) {
      throw new Error('Nieprawidłowe wymiary obrazu. Maksymalna powierzchnia wynosi 20 megapikseli.');
    }
    return [w, h];
  }

  function localSource(src) {
    if (!src || typeof src !== 'string') throw new Error('Brakuje pliku obrazu. Dodaj go ponownie w materiałach.');
    const url = new URL(src, global.location.href);
    // No remote photos, tracking URLs or script-bearing image formats in saved scenes.
    if (url.origin === global.location.origin && ['http:', 'https:', 'blob:'].includes(url.protocol)) return url.href;
    if (/^data:image\/(png|jpeg|webp);base64,[a-z0-9+/=\r\n]+$/i.test(src) && src.length < 28000000) return src;
    throw new Error('Obraz musi pochodzić z materiałów zapisanych w tym narzędziu.');
  }

  async function loadImage(src) {
    const url = localSource(src);
    if (imageCache.has(url)) return imageCache.get(url);
    const promise = new Promise((resolve, reject) => {
      const image = new Image();
      image.decoding = 'async';
      image.onload = () => { imageErrors.delete(src); resolve(image); };
      image.onerror = () => {
        imageCache.delete(url);
        imageErrors.set(src, 'Nie można odczytać pliku. Mógł wygasnąć — dodaj go ponownie.');
        reject(new Error(imageErrors.get(src)));
      };
      image.src = url;
    });
    imageCache.set(url, promise);
    if (imageCache.size > 16) imageCache.delete(imageCache.keys().next().value);
    return promise;
  }

  function color(value, fallback = '#182021') {
    return typeof value === 'string' && /^#[\da-f]{3}(?:[\da-f]{3})?$/i.test(value) ? value : fallback;
  }

  function luminance(value) {
    let hex = color(value, '#182021').slice(1);
    if (hex.length === 3) hex = Array.from(hex, c => c + c).join('');
    const rgb = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  }

  function contrastText(value) {
    const light = luminance(value);
    return (light + 0.05) / 0.05 > 1.05 / (light + 0.05) ? '#101819' : '#FFFFFF';
  }

  function canonicalColor(value) {
    const hex = color(value).slice(1).toUpperCase();
    return hex.length === 3 ? Array.from(hex, c => c + c).join('') : hex;
  }

  function brandData(brand = {}) {
    return {
      color: color(brand.color, '#E76A25'),
      secondary_color: color(brand.secondary_color, '#F4F1EC'),
      text_color: color(brand.text_color, '#182021'),
      font_family: String(brand.font_family || 'Arial').slice(0, 150),
      font_url: brand.font_url || null,
      logo_url: brand.logo_url || null,
      logo_asset_id: brand.logo_asset_id || null,
    };
  }

  function imageLayer(role, asset, box, extra = {}) {
    return Object.assign({id: role, type: 'image', role, x: box[0], y: box[1], w: box[2], h: box[3], src: asset ? asset.url : '', asset_id: asset ? asset.id : null, fit: 'contain', cropX: 0.5, cropY: 0.5, opacity: 1}, extra);
  }

  function rectLayer(id, box, fill, extra = {}) {
    return Object.assign({id, type: 'rect', role: 'decoration', x: box[0], y: box[1], w: box[2], h: box[3], color: fill, opacity: 1}, extra);
  }

  const shapeKinds = ['rectangle', 'square', 'circle', 'ellipse', 'triangle', 'diamond'];
  const pixelLockedKinds = ['square', 'circle'];
  let shapeCounter = 0;

  // Native Shape layers: editable geometry without an uploaded file. Squares
  // and circles keep equal width and height in rendered pixels; rectangles
  // and ellipses resize freely. Triangle and diamond fill a deterministic box.
  function makeShape({shape = 'rectangle', brand = {}, width = 1200, height = 1200, id = null} = {}) {
    [width, height] = checkedSize(width, height);
    if (!shapeKinds.includes(shape)) throw new Error('Wybierz jeden z sześciu kształtów.');
    brand = brandData(brand);
    const side = 0.30 * Math.min(width, height);
    const box = shape === 'square' || shape === 'circle'
      ? [0.5 - (side / width) / 2, 0.5 - (side / height) / 2, side / width, side / height]
      : shape === 'ellipse' ? [0.30, 0.34, 0.40, 0.26]
      : shape === 'diamond' ? [0.35, 0.35, 0.30, 0.30]
      : [0.30, 0.38, 0.40, 0.20];
    return {id: id || ('shape-' + (++shapeCounter)), type: 'rect', role: 'shape', shape, x: box[0], y: box[1], w: box[2], h: box[3], color: brand.color, opacity: 1};
  }

  const pixelLocked = layer => pixelLockedKinds.includes(layer.shape);

  function shapeContains(layer, px, py, sceneWidth, sceneHeight) {
    if (!layer || layer.type !== 'rect') return false;
    const w = Math.max(1, number(layer.w) * sceneWidth), h = Math.max(1, number(layer.h) * sceneHeight);
    const dx = px - number(layer.x) * sceneWidth, dy = py - number(layer.y) * sceneHeight;
    if (dx < 0 || dy < 0 || dx > w || dy > h) return false;
    if (!layer.shape || layer.shape === 'rectangle' || layer.shape === 'square') return true;
    if (layer.shape === 'circle' || layer.shape === 'ellipse') {
      const nx = (dx - w / 2) / (w / 2), ny = (dy - h / 2) / (h / 2);
      return nx * nx + ny * ny <= 1.0025;
    }
    if (layer.shape === 'triangle') {
      const fy = Math.min(1, Math.max(0, dy / h));
      const halfWidth = (w / 2) * (1 - fy);
      return dx >= w / 2 - halfWidth && dx <= w / 2 + halfWidth;
    }
    if (layer.shape === 'diamond') {
      return Math.abs(dx - w / 2) / (w / 2) + Math.abs(dy - h / 2) / (h / 2) <= 1.0025;
    }
    return true;
  }

  // Anchor-preserving square snap: keep x/y, derive h from w in rendered pixels.
  function snapSquareAnchored(layer, W, H) {
    let w = clamp(number(layer.w, 0.1), 0.012, Math.max(0.012, 1 - number(layer.x, 0)));
    let h = w * W / H;
    if (number(layer.y, 0) + h > 1) { h = Math.max(0.012, 1 - number(layer.y, 0)); w = h * H / W; }
    layer.w = w; layer.h = h;
  }

  // Center-preserving square conversion across canvas sizes: one equal
  // rendered-pixel side around the same normalized center, clamped to fit.
  function squareToPixels(layer, oldW, oldH, newW, newH) {
    const cx = number(layer.x, 0) + number(layer.w, 0.1) / 2, cy = number(layer.y, 0) + number(layer.h, 0.1) / 2;
    const s = Math.max(Math.min(Math.max(number(layer.w, 0.1) * oldW, number(layer.h, 0.1) * oldH), newW, newH), 5);
    const w = Math.min(s / newW, 1), h = Math.min(s / newH, 1);
    layer.x = clamp(cx - w / 2, 0, Math.max(0, 1 - w));
    layer.y = clamp(cy - h / 2, 0, Math.max(0, 1 - h));
    layer.w = w; layer.h = h;
  }

  // Corner-drag square snap: the corner opposite the handle stays fixed and
  // the dragged corner sets one equal rendered-pixel side.
  function snapSquareToCorner(layer, W, H, corner, fallback) {
    const minPx = 5;
    const ax = corner.includes('e') ? layer.x : layer.x + layer.w;
    const ay = corner.includes('s') ? layer.y : layer.y + layer.h;
    const dirX = corner.includes('e') ? 1 : -1, dirY = corner.includes('s') ? 1 : -1;
    const maxS = Math.min(dirX > 0 ? (1 - ax) * W : ax * W, dirY > 0 ? (1 - ay) * H : ay * H);
    if (!(maxS >= minPx)) { Object.assign(layer, {x: fallback.x, y: fallback.y, w: fallback.w, h: fallback.h}); return; }
    const cx = corner.includes('e') ? layer.x + layer.w : layer.x;
    const cy = corner.includes('s') ? layer.y + layer.h : layer.y;
    const s = Math.min(Math.max(Math.abs(cx - ax) * W, Math.abs(cy - ay) * H, minPx), maxS);
    layer.w = s / W; layer.h = s / H;
    layer.x = dirX > 0 ? ax : ax - layer.w;
    layer.y = dirY > 0 ? ay : ay - layer.h;
  }

  function textLayer(role, text, box, size, brand, extra = {}) {
    return Object.assign({id: role, type: 'text', role, text: String(text || ''), x: box[0], y: box[1], w: box[2], h: box[3], fontFamily: brand.font_family, fontSize: size, baseFontSize: size, fontWeight: role === 'description' ? 400 : 700, color: brand.text_color, align: 'left', opacity: 1}, extra);
  }

  function shape(width, height) {
    const ratio = width / height;
    if (ratio >= 4.5 || (height <= 100 && ratio >= 2.8)) return 'ribbon';
    if (ratio < 0.8) return 'portrait';
    if (ratio >= 1.55) return 'landscape';
    return 'square';
  }

  function materialId(asset, role, index) {
    if (asset && asset.layer_id) return asset.layer_id;
    if (role === 'product' && index === 0) return 'product';
    return role + '-' + String(asset && (asset.parent_id || asset.id) || index + 1);
  }

  function materialBoxes(box, count, width, height) {
    if (count <= 1) return [box.slice()];
    // Pick a compact grid in the physical space of the product panel. A tall
    // panel stacks products; a wide panel puts them side by side.
    const aspect = box[2] * width / (box[3] * height);
    let columns = 1, best = Infinity;
    for (let c = 1; c <= count; c++) {
      const rows = Math.ceil(count / c);
      const score = Math.abs(Math.log(aspect * rows / c)) + (rows * c - count) / count * .45;
      if (score < best) { best = score; columns = c; }
    }
    const rows = Math.ceil(count / columns), gap = .035;
    const cellW = box[2] / columns, cellH = box[3] / rows;
    return Array.from({length: count}, (_, i) => {
      const row = Math.floor(i / columns), inRow = Math.min(columns, count - row * columns);
      return [box[0] + (i % columns + (columns - inRow) / 2 + gap / 2) * cellW,
        box[1] + (row + gap / 2) * cellH, cellW * (1 - gap), cellH * (1 - gap)];
    });
  }

  function addProducts(scene, assets, box, accessoryBox = null) {
    const boxes = accessoryBox && assets.length > 1
      ? [box.slice(), ...materialBoxes(accessoryBox, assets.length - 1, scene.width, scene.height)]
      : materialBoxes(box, assets.length, scene.width, scene.height);
    assets.forEach((asset, index) => scene.layers.push(imageLayer('product', asset, boxes[index], {id: materialId(asset, 'product', index)})));
    scene.productOrder = assets.map((asset, index) => materialId(asset, 'product', index));
  }

  // The six added schemes have their own geometry in each aspect family.
  // Boxes use normalized coordinates; photographs always retain their aspect.
  const addedLayouts = {
    catalog: {
      square: {logo:[.055,.045,.28,.085],headline:[.055,.18,.89,.14],description:[.055,.335,.89,.08],product:[.07,.455,.86,.33],cta:[.30,.86,.40,.085],panels:[['catalog-shelf',[.045,.435,.91,.375],'white']]},
      landscape: {logo:[.045,.06,.20,.12],headline:[.285,.065,.67,.17],description:[.045,.255,.90,.10],product:[.055,.41,.62,.50],cta:[.72,.71,.235,.15],panels:[['catalog-shelf',[.025,.39,.675,.56],'white'],['catalog-rule',[.72,.42,.235,.018],'accent']]},
      portrait: {logo:[.08,.04,.62,.065],headline:[.08,.15,.84,.135],description:[.08,.305,.84,.075],product:[.08,.41,.84,.40],cta:[.10,.89,.80,.065],panels:[['catalog-shelf',[.04,.395,.92,.44],'white']]},
      ribbon: {logo:[.02,.22,.12,.56],headline:[.17,.09,.335,.82],product:[.52,.07,.265,.86],cta:[.81,.15,.165,.70],panels:[['catalog-shelf',[.515,0,.28,1],'white']]},
    },
    benefits: {
      square: {logo:[.055,.05,.29,.085],headline:[.60,.20,.35,.235],description:[.60,.495,.35,.26],product:[.055,.22,.485,.57],cta:[.56,.865,.39,.08],panels:[['benefits-photo',[.025,.185,.54,.635],'white'],['benefits-rule',[.60,.455,.10,.012],'accent']]},
      landscape: {logo:[.045,.055,.24,.11],headline:[.045,.265,.45,.225],description:[.06,.605,.42,.285],product:[.56,.085,.395,.64],cta:[.60,.82,.35,.115],panels:[['benefits-description',[.025,.57,.48,.36],'white'],['benefits-rule',[.025,.57,.009,.36],'accent']]},
      portrait: {logo:[.08,.04,.60,.065],product:[.09,.14,.82,.31],headline:[.10,.515,.80,.14],description:[.10,.685,.80,.14],cta:[.10,.895,.80,.06],panels:[['benefits-photo',[.05,.125,.90,.345],'white'],['benefits-rule',[.10,.49,.18,.008],'accent']]},
      ribbon: {logo:[.025,.16,.12,.27],headline:[.17,.08,.35,.84],product:[.55,.04,.22,.92],cta:[.81,.15,.165,.70],panels:[['benefits-photo',[.535,0,.25,1],'white'],['benefits-rule',[.025,.64,.10,.06],'accent']]},
    },
    label: {
      square: {logo:[.055,.055,.30,.08],headline:[.055,.195,.58,.205],description:[.66,.43,.29,.31],product:[.075,.445,.525,.35],element:[.71,.07,.24,.24],cta:[.10,.86,.43,.085],panels:[['label-rule',[.055,.16,.10,.009],'accent']]},
      landscape: {logo:[.05,.065,.23,.11],headline:[.05,.28,.43,.24],description:[.05,.58,.40,.17],product:[.53,.325,.425,.57],element:[.75,.045,.20,.255],cta:[.05,.835,.34,.11],panels:[['label-product',[.51,.31,.46,.61],'white']]},
      portrait: {logo:[.085,.04,.59,.065],headline:[.085,.15,.83,.145],description:[.085,.32,.83,.10],product:[.075,.50,.61,.31],element:[.71,.46,.24,.165],cta:[.10,.89,.80,.065],panels:[['label-rule',[.085,.445,.18,.007],'accent']]},
      ribbon: {logo:[.02,.20,.11,.60],headline:[.155,.08,.35,.84],product:[.52,.04,.15,.92],element:[.685,.12,.105,.76],cta:[.81,.15,.165,.70],panels:[['label-rule',[.155,.96,.635,.04],'accent']]},
    },
    backdrop: {
      square: {logo:[.075,.085,.32,.075],headline:[.075,.235,.38,.29],description:[.075,.585,.38,.18],product:[.55,.22,.40,.58],cta:[.075,.86,.37,.08],panels:[['backdrop-copy',[.04,.04,.445,.92],'paper']]},
      landscape: {logo:[.065,.105,.24,.10],headline:[.065,.285,.365,.27],description:[.065,.61,.365,.15],product:[.54,.15,.405,.70],cta:[.065,.825,.32,.11],panels:[['backdrop-copy',[.025,.045,.44,.91],'paper']]},
      portrait: {logo:[.10,.525,.58,.065],headline:[.10,.62,.80,.145],description:[.10,.79,.80,.065],product:[.12,.045,.76,.405],cta:[.10,.90,.80,.06],panels:[['backdrop-copy',[.045,.495,.91,.485],'paper']]},
      ribbon: {logo:[.035,.20,.11,.60],headline:[.18,.10,.34,.80],product:[.565,.07,.22,.86],cta:[.81,.15,.165,.70],panels:[['backdrop-copy',[.015,.045,.535,.91],'paper']]},
    },
    bundle: {
      square: {logo:[.055,.045,.28,.08],headline:[.055,.165,.89,.145],description:[.055,.365,.27,.24],product:[.365,.35,.535,.335],accessory:[.11,.73,.78,.105],cta:[.055,.875,.43,.075],panels:[['bundle-hero',[.345,.33,.60,.38],'white'],['bundle-rule',[.055,.71,.89,.008],'accent']]},
      landscape: {logo:[.05,.07,.24,.11],headline:[.05,.28,.375,.265],description:[.05,.60,.365,.16],product:[.47,.065,.465,.585],accessory:[.49,.735,.45,.205],cta:[.05,.83,.34,.12],panels:[['bundle-hero',[.45,.035,.51,.65],'white'],['bundle-rule',[.49,.70,.45,.012],'accent']]},
      portrait: {logo:[.09,.04,.60,.065],headline:[.09,.15,.82,.135],description:[.09,.31,.82,.075],product:[.11,.425,.78,.285],accessory:[.09,.755,.82,.085],cta:[.10,.90,.80,.06],panels:[['bundle-hero',[.07,.41,.86,.315],'white'],['bundle-rule',[.09,.74,.82,.006],'accent']]},
      ribbon: {logo:[.02,.20,.12,.60],headline:[.17,.08,.34,.84],product:[.525,.07,.16,.86],accessory:[.705,.19,.085,.62],cta:[.81,.15,.165,.70],panels:[['bundle-hero',[.52,0,.17,1],'white']]},
    },
    bold: {
      square: {logo:[.065,.065,.31,.075],headline:[.06,.245,.46,.32],description:[.06,.62,.43,.17],product:[.59,.335,.345,.385],cta:[.06,.865,.43,.08],panels:[['bold-field',[0,0,1,1],'accent'],['bold-product',[.555,.285,.41,.485],'white'],['bold-logo',[.045,.04,.35,.125],'white']]},
      landscape: {logo:[.065,.095,.25,.10],headline:[.065,.285,.44,.255],description:[.065,.59,.405,.15],product:[.615,.13,.32,.74],cta:[.065,.835,.34,.115],panels:[['bold-field',[0,0,.56,1],'accent'],['bold-product',[.585,.055,.38,.89],'white'],['bold-logo',[.05,.07,.29,.15],'white']]},
      portrait: {logo:[.10,.055,.59,.065],headline:[.10,.18,.80,.14],description:[.10,.345,.80,.09],product:[.135,.515,.73,.265],cta:[.10,.895,.80,.065],panels:[['bold-field',[0,0,1,1],'accent'],['bold-product',[.08,.485,.84,.325],'white'],['bold-logo',[.075,.035,.64,.105],'white']]},
      ribbon: {logo:[.025,.25,.12,.50],headline:[.18,.08,.34,.84],product:[.58,.06,.19,.88],cta:[.81,.15,.165,.70],panels:[['bold-field',[0,0,1,1],'accent'],['bold-product',[.565,0,.22,1],'white'],['bold-logo',[.015,.15,.14,.70],'white']]},
    },
  };

  function addedLayout(template, type, width, height, brand) {
    if (!addedLayouts[template]) return null;
    const spec = clone(addedLayouts[template][type]);
    const fills = {accent:brand.color,paper:brand.secondary_color,white:'#FFFFFF'};
    const panels = spec.panels.map(([id, box, fill]) => rectLayer(id, box, fills[fill], {radius:type === 'ribbon' ? 0 : .018}));
    delete spec.panels;
    // Optional labels belong to the image region, not the default top-right
    // corner, where several of these schemes place their headline. The label
    // scheme retains its separate, deliberately reserved Element area.
    if (!spec.element) {
      const [x,y,w,h] = spec.product;
      spec.element = [x + w * .50, y + h * .035, w * .46, h * .27];
    }
    let headingSize, bodySize, ctaSize;
    if (type === 'ribbon') {
      headingSize = height * .32; bodySize = height * .17; ctaSize = height * .23;
      if (width < 500) {
        // Short strips retain room for a two-line CTA and a concise headline.
        spec.cta = [.755,.09,.23,.82];
        const maxX = .735;
        for (const role of ['product','accessory','element']) {
          if (spec[role]) { spec[role][0] = .52 + (spec[role][0] - .52) * .78; spec[role][2] *= .78; spec[role][2] = Math.min(spec[role][2], maxX - spec[role][0]); }
        }
      }
    } else if (type === 'portrait') {
      headingSize = Math.min(width * .13,height * .064); bodySize = Math.min(width * .062,height * .028); ctaSize = Math.min(width * .075,height * .028);
    } else if (type === 'landscape') {
      headingSize = Math.min(height * .125,width * .06); bodySize = height * .049; ctaSize = height * .054;
    } else {
      headingSize = Math.min(width,height) * .072; bodySize = Math.min(width,height) * .032; ctaSize = Math.min(width,height) * .033;
    }
    return {boxes:spec,panels,headingSize,bodySize,ctaSize};
  }

  function makeScene({template = 'split', width = 1200, height = 1200, brand = {}, product = null, products = null, elements = [], background = null, headline = '', description = '', cta = '', clean = false, logoRequired = false} = {}) {
    [width, height] = checkedSize(width, height);
    if (!templates.some(t => t.id === template)) template = 'split';
    brand = brandData(brand);
    const materials = Array.isArray(products) ? products.filter(Boolean) : product ? [product] : [];
    const hasProduct = materials.length > 0;
    const scene = {width, height, background: brand.secondary_color, template, brand, clean: Boolean(clean), layers: [], omitted: [], content: {headline: String(headline || ''), description: String(description || ''), cta: String(cta || '')}};
    if (background) scene.layers.push(imageLayer('background', background, [0, 0, 1, 1], {fit: 'cover', locked: true}));
    else if (template === 'backdrop' && !clean) scene.layers.push(imageLayer('background', null, [0, 0, 1, 1], {fit:'cover',locked:true,missingSlot:'background:0'}));
    if (clean) {
      addProducts(scene, hasProduct ? materials : background ? [] : [null], [0.10, 0.10, 0.80, 0.80]);
      return scene;
    }

    let boxes, headingSize, bodySize, ctaSize;
    const type = shape(width, height);
    const unit = Math.min(width, height);
    const accent = brand.color;
    const paper = brand.secondary_color;
    const added = addedLayout(template, type, width, height, brand);
    // Template geometry is defined per aspect family; no photograph is stretched.
    if (added) {
      ({boxes,headingSize,bodySize,ctaSize} = added);
      scene.layers.push(...added.panels);
      if (description && (type === 'ribbon' || (type === 'portrait' && width / height < .3))) {
        delete boxes.description;
        scene.omitted.push({role:'description',message:'W wąskim formacie pominięto opis, aby zachować czytelność. Dodatkowa treść pozostaje w tabeli tekstów.'});
      }
    } else if (type === 'ribbon') {
      boxes = {logo: [0.025, 0.20, 0.13, 0.60], headline: [0.18, 0.13, 0.43, 0.74], product: [0.63, 0.045, 0.18, 0.91], cta: [0.825, 0.22, 0.15, 0.56]};
      headingSize = height * 0.32; bodySize = height * 0.17; ctaSize = height * 0.23;
      scene.layers.push(rectLayer('ribbon-paper', [0, 0, 0.63, 1], paper));
      if (template === 'split') scene.layers.push(rectLayer('ribbon-panel', [0.625, 0, 0.19, 1], '#FFFFFF'));
      if (template === 'spotlight') {
        boxes.product = [0.015, 0.035, 0.21, 0.93]; boxes.logo = [0.245, 0.10, 0.11, 0.28]; boxes.headline = [0.245, 0.43, 0.55, 0.50];
        headingSize = height * 0.29;
        scene.layers.push(rectLayer('ribbon-content', [0.235, 0, 0.765, 1], paper));
      }
      if (template === 'minimal') scene.layers.push(rectLayer('brand-rule', [0, 0.94, 1, 0.06], accent));
      if (width < 500) {
        boxes.cta = [0.735, 0.09, 0.245, 0.82];
        if (template === 'spotlight') boxes.headline[2] = 0.46;
        else { boxes.headline[2] = 0.36; boxes.product = [0.55, 0.045, 0.17, 0.91]; }
      } else boxes.cta = [0.81, 0.15, 0.165, 0.70];
      if (description) scene.omitted.push({role: 'description', message: 'Wąski baner pomija opis. Zostają nagłówek, produkt, logo i CTA; dłuższy tekst jest w tabeli tekstów.'});
    } else if (type === 'landscape') {
      headingSize = Math.min(height * 0.135, width * 0.062); bodySize = height * 0.051; ctaSize = height * 0.054;
      if (template === 'split') {
        scene.layers.push(rectLayer('text-panel', [0, 0, 0.515, 1], paper), rectLayer('product-panel', [0.535, 0.055, 0.435, 0.89], '#FFFFFF', {radius: 0.025}));
        boxes = {logo: [0.05, 0.075, 0.25, 0.11], headline: [0.05, 0.285, 0.42, 0.33], description: [0.05, 0.65, 0.40, 0.115], product: [0.55, 0.09, 0.405, 0.82], cta: [0.05, 0.825, 0.30, 0.105]};
      } else if (template === 'spotlight') {
        scene.layers.push(rectLayer('text-panel', [0.53, 0, 0.47, 1], paper), rectLayer('product-panel', [0.035, 0.07, 0.47, 0.86], '#FFFFFF', {radius: 0.045}));
        boxes = {logo: [0.57, 0.07, 0.27, 0.10], headline: [0.57, 0.275, 0.38, 0.32], description: [0.57, 0.635, 0.36, 0.14], product: [0.055, 0.10, 0.43, 0.80], cta: [0.57, 0.835, 0.30, 0.10]};
      } else {
        scene.layers.push(rectLayer('text-panel', [0, 0, 0.535, 1], paper), rectLayer('brand-rule', [0.05, 0.232, 0.065, 0.013], accent));
        boxes = {logo: [0.05, 0.07, 0.23, 0.10], headline: [0.05, 0.30, 0.45, 0.30], description: [0.05, 0.65, 0.40, 0.13], product: [0.555, 0.10, 0.40, 0.80], cta: [0.05, 0.84, 0.30, 0.095]};
        headingSize *= 1.08;
      }
    } else if (type === 'portrait') {
      const slender = width / height < 0.3;
      headingSize = Math.min(width * 0.13, height * 0.064); bodySize = Math.min(width * 0.062, height * 0.028); ctaSize = Math.min(width * 0.075, height * 0.028);
      if (template === 'split') {
        scene.layers.push(rectLayer('text-panel', [0, 0, 1, 0.47], paper), rectLayer('product-panel', [0.06, 0.48, 0.88, 0.36], '#FFFFFF', {radius: 0.02}));
        boxes = {logo: [0.10, 0.045, 0.58, 0.075], headline: [0.10, 0.165, 0.80, 0.18], description: [0.10, 0.365, 0.80, 0.095], product: [0.09, 0.495, 0.82, 0.325], cta: [0.10, 0.89, 0.80, 0.06]};
      } else if (template === 'spotlight') {
        scene.layers.push(rectLayer('product-panel', [0.06, 0.135, 0.88, 0.44], '#FFFFFF', {radius: 0.026}), rectLayer('text-panel', [0, 0.60, 1, 0.40], paper));
        boxes = {logo: [0.10, 0.045, 0.60, 0.065], product: [0.09, 0.155, 0.82, 0.40], headline: [0.10, 0.62, 0.80, 0.14], description: [0.10, 0.785, 0.80, 0.075], cta: [0.10, 0.90, 0.80, 0.06]};
      } else {
        scene.layers.push(rectLayer('text-panel', [0, 0, 1, 0.39], paper), rectLayer('lower-panel', [0, 0.755, 1, 0.245], paper), rectLayer('brand-rule', [0.10, 0.13, 0.12, 0.005], accent));
        boxes = {logo: [0.10, 0.045, 0.58, 0.065], headline: [0.10, 0.175, 0.80, 0.185], product: [0.085, 0.405, 0.83, 0.33], description: [0.10, 0.785, 0.80, 0.075], cta: [0.10, 0.90, 0.80, 0.06]};
      }
      if (slender && description) {
        delete boxes.description;
        scene.omitted.push({role: 'description', message: 'W bardzo wąskim formacie pominięto opis, aby zachować czytelność. Sprawdź nagłówek w rzeczywistym rozmiarze.'});
      }
    } else {
      headingSize = unit * 0.075; bodySize = unit * 0.033; ctaSize = unit * 0.033;
      if (template === 'split') {
        scene.layers.push(rectLayer('text-panel', [0, 0, 0.515, 1], paper), rectLayer('product-panel', [0.535, 0.16, 0.435, 0.66], '#FFFFFF', {radius: 0.028}));
        boxes = {logo: [0.065, 0.065, 0.30, 0.095], headline: [0.065, 0.24, 0.425, 0.31], description: [0.065, 0.59, 0.415, 0.16], product: [0.545, 0.195, 0.405, 0.59], cta: [0.065, 0.855, 0.37, 0.08]};
      } else if (template === 'spotlight') {
        scene.layers.push(rectLayer('product-panel', [0.15, 0.155, 0.70, 0.46], '#FFFFFF', {radius: 0.045}), rectLayer('text-panel', [0, 0.635, 1, 0.365], paper));
        boxes = {logo: [0.065, 0.055, 0.28, 0.075], product: [0.19, 0.175, 0.62, 0.42], headline: [0.08, 0.655, 0.84, 0.115], description: [0.11, 0.79, 0.78, 0.065], cta: [0.30, 0.89, 0.40, 0.07]};
        headingSize = unit * 0.065;
      } else {
        scene.layers.push(rectLayer('text-panel', [0, 0, 1, 0.375], paper), rectLayer('brand-rule', [0.065, 0.16, 0.085, 0.008], accent));
        boxes = {logo: [0.065, 0.055, 0.30, 0.075], headline: [0.065, 0.215, 0.86, 0.13], description: [0.065, 0.42, 0.24, 0.28], product: [0.34, 0.40, 0.61, 0.425], cta: [0.065, 0.885, 0.40, 0.075]};
      }
    }
    // Small outputs need a deliberate reduction of information, not microscopic copy.
    if ((Math.min(width, height) < 240 || (boxes.description && boxes.description[3] * height < 22)) && boxes.description && description) {
      delete boxes.description;
      scene.omitted.push({role: 'description', message: 'W tym małym formacie pominięto opis. Dodatkowa treść pozostaje w tabeli tekstów; użyj krótkiego nagłówka i CTA.'});
    }
    headingSize = Math.max(12, headingSize); bodySize = Math.max(10, bodySize); ctaSize = Math.max(height < 80 ? 10 : 12, ctaSize);
    if (type !== 'ribbon') {
      boxes.cta[2] = Math.max(boxes.cta[2], Math.min(0.80, 130 / width));
      boxes.cta[3] = Math.max(boxes.cta[3], Math.min(0.18, 32 / height));
      boxes.cta[1] = Math.min(boxes.cta[1], 0.965 - boxes.cta[3]);
      if (template === 'spotlight' && type === 'square') boxes.cta[0] = (1 - boxes.cta[2]) / 2;
      if (added) boxes.cta[0] = Math.min(boxes.cta[0], .965 - boxes.cta[2]);
    }
    if (background && !hasProduct) scene.layers = scene.layers.filter(layer => !['product-panel', 'ribbon-panel'].includes(layer.id));
    addProducts(scene, hasProduct ? materials : background ? [] : [null], boxes.product, boxes.accessory);
    const extras = (Array.isArray(elements) ? elements : []).filter(Boolean);
    if (template === 'label' && !extras.length) extras.push(null);
    const elementBoxes = materialBoxes(boxes.element || (extras.length > 1 ? [.55, .055, .40, .34] : [.75, .065, .20, .20]), extras.length, width, height);
    extras.forEach((asset, index) => scene.layers.push(imageLayer('element', asset, elementBoxes[index], {id: materialId(asset, 'element', index), ...(!asset ? {missingSlot:'element:' + index} : {})})));
    if (brand.logo_url || logoRequired) scene.layers.push(imageLayer('logo', {url: brand.logo_url || '', id: brand.logo_asset_id}, boxes.logo, !brand.logo_url ? {missingSlot:'logo:0'} : {}));
    const centered = template === 'spotlight' && type === 'square';
    const copyStyle = {align: centered ? 'center' : 'left'};
    if (template === 'bold') copyStyle.color = contrastText(accent);
    if (headline) scene.layers.push(textLayer('headline', headline, boxes.headline, headingSize, brand, copyStyle));
    if (description && boxes.description) scene.layers.push(textLayer('description', description, boxes.description, bodySize, brand, copyStyle));
    const buttonColor = template === 'bold' ? paper : accent;
    if (cta) scene.layers.push(textLayer('cta', cta, boxes.cta, ctaSize, brand, {align: 'center', color: contrastText(buttonColor), backgroundColor: buttonColor, radius: 0.014, verticalAlign: 'middle'}));
    return scene;
  }

  function adaptScene(source, width, height, {clean = false} = {}) {
    [width, height] = checkedSize(width, height);
    const scene = clone(source);
    if (!Array.isArray(scene.layers)) scene.layers = [];
    const oldWidth = number(scene.width, width), oldHeight = number(scene.height, height);
    const roleLayer = role => scene.layers.find(layer => layer.role === role);
    const order = scene.productOrder || scene.layers.filter(layer => layer.role === 'product').map(layer => layer.id);
    const products = scene.layers.filter(layer => layer.type === 'image' && layer.role === 'product')
      .sort((a, b) => (order.indexOf(a.id) < 0 ? 999 : order.indexOf(a.id)) - (order.indexOf(b.id) < 0 ? 999 : order.indexOf(b.id)));
    const background = roleLayer('background');
    if (clean) {
      const alreadyClean = Boolean(scene.clean);
      scene.width = width; scene.height = height; scene.clean = true; scene.omitted = [];
      scene.layers = [];
      if (background) scene.layers.push(Object.assign(background, {x: 0, y: 0, w: 1, h: 1, fit: 'cover'}));
      const boxes = materialBoxes([.10, .10, .80, .80], products.length, width, height);
      products.forEach((layer, i) => scene.layers.push(Object.assign(layer, alreadyClean ? {} : {x: boxes[i][0], y: boxes[i][1], w: boxes[i][2], h: boxes[i][3], fit: 'contain'})));
      const priorOrder = new Map(source.layers.map((layer, i) => [layer.id, i]));
      scene.layers.sort((a, b) => (priorOrder.get(a.id) ?? 999) - (priorOrder.get(b.id) ?? 999));
      scene.productOrder = products.map(layer => layer.id);
      return scene;
    }
    if (Math.abs(oldWidth / oldHeight - width / height) < 0.012 || !scene.template) {
      scene.width = width; scene.height = height;
      const aspectChanged = Math.abs(oldWidth / oldHeight - width / height) >= 0.012;
      scene.layers.forEach(layer => {
        if (layer.type === 'text') {
          layer.fontSize = number(layer.fontSize, 24) * height / oldHeight;
          if (layer.baseFontSize) layer.baseFontSize *= height / oldHeight;
        }
        if (layer.borderWidth !== undefined) layer.borderWidth = number(layer.borderWidth) * height / oldHeight;
        // Template-less scenes cannot regenerate a layout; keep squares square.
        if (aspectChanged && !scene.template && layer.role === 'shape' && pixelLocked(layer)) squareToPixels(layer, oldWidth, oldHeight, width, height);
      });
      return scene;
    }
    const text = role => {
      const layer = roleLayer(role);
      if (layer) return layer.text || '';
      if ((scene.omitted || []).some(item => item.role === role)) return (scene.content || {})[role] || '';
      return '';
    };
    const brand = brandData(scene.brand), logo = roleLayer('logo');
    brand.logo_url = logo ? logo.src : null;
    brand.logo_asset_id = logo ? logo.asset_id : null;
    const args = {template: scene.template, brand, logoRequired:Boolean(logo && !logo.src), products: products.map(layer => ({url: layer.src, id: layer.asset_id, layer_id: layer.id})), background: background ? {url: background.src, id: background.asset_id} : null, headline: text('headline'), description: text('description'), cta: text('cta')};
    if (addedLayouts[scene.template]) args.elements = scene.layers.filter(layer => layer.type === 'image' && layer.role === 'element').map(layer => ({url:layer.src,id:layer.asset_id,layer_id:layer.id}));
    const next = makeScene({...args, width, height});
    const baseline = makeScene({...args, width: oldWidth, height: oldHeight});
    next.background = scene.background;
    next.layers.forEach(layer => {
      const previous = scene.layers.find(old => old.id === layer.id && old.type === layer.type);
      if (!previous) return;
      ['color', 'fontFamily', 'fontWeight', 'align', 'opacity', 'fit', 'cropX', 'cropY', 'backgroundColor', 'verticalAlign', 'radius', 'cornerRadius', 'borderColor', 'hidden', 'locked', 'missingSlot'].forEach(key => {
        if (previous[key] !== undefined) layer[key] = previous[key];
      });
      if (previous.borderWidth !== undefined) layer.borderWidth = number(previous.borderWidth) * height / oldHeight;
      if (layer.type === 'text' && previous.baseFontSize) layer.fontSize *= number(previous.fontSize, previous.baseFontSize) / previous.baseFontSize;
      // Keep manual geometry changes relative to the appropriate layout for the
      // destination format, instead of dropping edits when its aspect changes.
      const before = baseline.layers.find(old => old.id === layer.id);
      if (before && !['decoration', 'background'].includes(layer.role)) {
        const w = clamp(layer.w * number(previous.w, before.w) / before.w, .005, 1);
        const h = clamp(layer.h * number(previous.h, before.h) / before.h, .005, 1);
        layer.x = clamp(layer.x + number(previous.x, before.x) - before.x, 0, 1 - w);
        layer.y = clamp(layer.y + number(previous.y, before.y) - before.y, 0, 1 - h);
        layer.w = w; layer.h = h;
      }
    });
    const generatedIds = new Set(next.layers.map(layer => layer.id));
    const standardIds = new Set(['product', 'background', 'logo', 'headline', 'description', 'cta']);
    scene.layers.filter(layer => !generatedIds.has(layer.id) && !standardIds.has(layer.id) && layer.role !== 'decoration').forEach(layer => {
      if (layer.type === 'text') layer.fontSize = number(layer.fontSize, 24) * height / oldHeight;
      if (layer.borderWidth !== undefined) layer.borderWidth = number(layer.borderWidth) * height / oldHeight;
      if (layer.role === 'shape' && pixelLocked(layer)) squareToPixels(layer, oldWidth, oldHeight, next.width, next.height);
      next.layers.push(layer);
    });
    // New panels are kept beneath content, while the user's order among all
    // existing layers (including products and elements) remains unchanged.
    const priorOrder = new Map(scene.layers.map((layer, index) => [layer.id, index]));
    next.layers.sort((a, b) => (priorOrder.get(a.id) ?? (a.role === 'decoration' ? -1 : 999)) - (priorOrder.get(b.id) ?? (b.role === 'decoration' ? -1 : 999)));
    return next;
  }

  async function ensureFont(scene) {
    const brand = scene.brand || {};
    if (!brand.font_url || !global.FontFace) return;
    const key = brand.font_family + '|' + brand.font_url;
    if (!fontCache.has(key)) {
      const url = localSource(brand.font_url);
      const face = new FontFace(brand.font_family || 'Arial', 'url(' + JSON.stringify(url) + ')');
      fontCache.set(key, face.load().then(loaded => { document.fonts.add(loaded); return loaded; }));
    }
    try { await fontCache.get(key); }
    catch (_) { throw new Error('Nie udało się wczytać czcionki marki. Sprawdź plik czcionki lub wybierz Arial.'); }
  }

  function fontString(layer, size) {
    const family = String(layer.fontFamily || 'Arial').replace(/["\\\n\r]/g, '').slice(0, 150);
    const weight = ['normal', 'bold', '400', '500', '600', '700', '800', '900'].includes(String(layer.fontWeight)) ? layer.fontWeight : 400;
    return weight + ' ' + size.toFixed(3) + 'px "' + family + '", Arial, sans-serif';
  }

  function wrapLines(ctx, text, width, breakWords = true) {
    const lines = [];
    for (const paragraph of String(text || '').replace(/\r\n?/g, '\n').split('\n')) {
      if (!paragraph.trim()) { lines.push(''); continue; }
      let line = '';
      for (const word of paragraph.trim().split(/\s+/)) {
        const combined = line ? line + ' ' + word : word;
        if (ctx.measureText(combined).width <= width) { line = combined; continue; }
        if (line) { lines.push(line); line = ''; }
        if (ctx.measureText(word).width <= width) { line = word; continue; }
        if (!breakWords) { line = word; continue; }
        // Unbreakable product IDs/URLs still get a deterministic, measurable layout.
        for (const character of Array.from(word)) {
          if (line && ctx.measureText(line + character).width > width) { lines.push(line); line = ''; }
          line += character;
        }
      }
      if (line) lines.push(line);
    }
    return lines;
  }

  function textLayout(ctx, layer, scene) {
    const boxWidth = number(layer.w) * scene.width, boxHeight = number(layer.h) * scene.height;
    const padding = layer.role === 'cta' || layer.backgroundColor ? Math.min(boxHeight * 0.18, boxWidth * 0.085) : 0;
    const width = Math.max(1, boxWidth - padding * 2), height = Math.max(1, boxHeight - padding * 2);
    const requested = clamp(number(layer.fontSize, scene.height * 0.06), 1, 2000);
    const minimum = Math.min(requested, scene.height < 80 ? 9 : 10);
    const lineRatio = layer.role === 'headline' ? 1.10 : 1.18;
    let size = requested, lines = [], overflow = false;
    for (let pass = 0; pass < 100; pass++) {
      ctx.font = fontString(layer, size);
      lines = wrapLines(ctx, layer.text || '', width, layer.role !== 'cta');
      const widest = Math.max(0, ...lines.map(line => ctx.measureText(line).width));
      overflow = lines.length * size * lineRatio > height + 0.2 || widest > width + 0.2;
      if (!overflow || size <= minimum + 0.001) break;
      size = Math.max(minimum, size * 0.95 - 0.08);
    }
    return {size, requested, lines, lineHeight: size * lineRatio, width, height, padding, overflow};
  }

  function roundedRect(ctx, x, y, width, height, radius) {
    const r = clamp(radius || 0, 0, Math.min(width, height) / 2);
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, width, height, r);
    else {
      ctx.moveTo(x + r, y); ctx.arcTo(x + width, y, x + width, y + height, r);
      ctx.arcTo(x + width, y + height, x, y + height, r); ctx.arcTo(x, y + height, x, y, r); ctx.arcTo(x, y, x + width, y, r);
      ctx.closePath();
    }
  }

  function drawImageLayer(ctx, image, layer, scene) {
    const x = number(layer.x) * scene.width, y = number(layer.y) * scene.height;
    const w = number(layer.w) * scene.width, h = number(layer.h) * scene.height;
    if (w <= 0 || h <= 0) return;
    const iw = image.naturalWidth || image.width, ih = image.naturalHeight || image.height;
    const cx = clamp(number(layer.cropX, 0.5), 0, 1), cy = clamp(number(layer.cropY, 0.5), 0, 1);
    if (layer.fit === 'cover') {
      const scale = Math.max(w / iw, h / ih);
      const sw = w / scale, sh = h / scale;
      ctx.drawImage(image, (iw - sw) * cx, (ih - sh) * cy, sw, sh, x, y, w, h);
    } else {
      const scale = Math.min(w / iw, h / ih);
      const dw = iw * scale, dh = ih * scale;
      ctx.drawImage(image, x + (w - dw) * cx, y + (h - dh) * cy, dw, dh);
    }
  }

  function drawMissingImage(ctx, layer, scene) {
    const x = number(layer.x) * scene.width, y = number(layer.y) * scene.height, w = number(layer.w) * scene.width, h = number(layer.h) * scene.height;
    if (w <= 0 || h <= 0) return;
    ctx.fillStyle = '#E8EBE8'; ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = '#B9C1BC'; ctx.lineWidth = Math.max(1, Math.min(w, h) * 0.004);
    ctx.setLineDash([Math.max(3, w * 0.025), Math.max(3, w * 0.015)]);
    ctx.strokeRect(x + 1, y + 1, w - 2, h - 2); ctx.setLineDash([]);
    const size = Math.max(9, Math.min(w / 12, h / 14));
    ctx.fillStyle = '#53625A'; ctx.font = '400 ' + size + 'px Arial'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const prompt = layer.src ? 'Dodaj plik ponownie' : layer.role === 'background' ? 'Dodaj tło' : layer.role === 'element' ? 'Dodaj Element' : 'Dodaj zdjęcie';
    ctx.fillText(prompt, x + w / 2, y + h / 2, Math.max(1, w * 0.88));
  }

  function drawText(ctx, layer, scene) {
    if (!layer.text) return;
    const x = number(layer.x) * scene.width, y = number(layer.y) * scene.height, w = number(layer.w) * scene.width, h = number(layer.h) * scene.height;
    if (w <= 0 || h <= 0) return;
    const layout = textLayout(ctx, layer, scene);
    if (layer.backgroundColor) {
      ctx.fillStyle = color(layer.backgroundColor, '#E76A25');
      const radius = layer.cornerRadius !== undefined ? clamp(number(layer.cornerRadius), 0, .5) * Math.min(w, h) : number(layer.radius, .01) * Math.min(scene.width, scene.height);
      roundedRect(ctx, x, y, w, h, radius); ctx.fill();
      const border = clamp(number(layer.borderWidth), 0, Math.min(w, h) / 2);
      if (border > 0) {
        ctx.lineWidth = border; ctx.strokeStyle = color(layer.borderColor, '#182021');
        roundedRect(ctx, x + border / 2, y + border / 2, w - border, h - border, Math.max(0, radius - border / 2)); ctx.stroke();
      }
    }
    ctx.font = fontString(layer, layout.size);
    ctx.fillStyle = color(layer.color);
    ctx.textAlign = ['left', 'center', 'right'].includes(layer.align) ? layer.align : 'left';
    ctx.textBaseline = 'alphabetic';
    const startX = ctx.textAlign === 'center' ? x + w / 2 : ctx.textAlign === 'right' ? x + w - layout.padding : x + layout.padding;
    const middle = layer.verticalAlign === 'middle' || layer.role === 'cta';
    const startY = y + layout.padding + (middle ? Math.max(0, (layout.height - layout.lines.length * layout.lineHeight) / 2) : 0);
    const metrics = ctx.measureText('ĄĘŚgj');
    const ascent = metrics.actualBoundingBoxAscent || layout.size * 0.80;
    const descent = metrics.actualBoundingBoxDescent || layout.size * 0.20;
    const baseline = (layout.lineHeight - ascent - descent) / 2 + ascent;
    const maxLines = Math.max(1, Math.floor(layout.height / layout.lineHeight));
    const lines = layout.overflow ? layout.lines.slice(0, maxLines) : layout.lines;
    // Overflow is visible as an ellipsis in preview and is a blocking export error.
    if (layout.overflow && lines.length) {
      let end = lines[lines.length - 1];
      while (end && ctx.measureText(end + '…').width > layout.width) end = Array.from(end).slice(0, -1).join('');
      lines[lines.length - 1] = end + '…';
    }
    ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
    lines.forEach((line, i) => ctx.fillText(line, startX, startY + baseline + i * layout.lineHeight));
  }

  function selectionHandles(layer, canvas, scene) {
    const rect = canvas.getBoundingClientRect();
    const scale = rect.width > 0 ? scene.width / rect.width : 1;
    const x = number(layer.x) * scene.width, y = number(layer.y) * scene.height, w = number(layer.w) * scene.width, h = number(layer.h) * scene.height;
    return {x, y, w, h, scale, points: [{corner: 'nw', x, y}, {corner: 'ne', x: x + w, y}, {corner: 'se', x: x + w, y: y + h}, {corner: 'sw', x, y: y + h}]};
  }

  async function render(canvas, source, {selection = null} = {}) {
    const scene = clone(source);
    [scene.width, scene.height] = checkedSize(scene.width, scene.height);
    const version = (renderVersions.get(canvas) || 0) + 1;
    renderVersions.set(canvas, version);
    await ensureFont(scene);
    const images = new Map();
    await Promise.all((scene.layers || []).filter(layer => layer.type === 'image' && layer.src).map(async layer => {
      try { images.set(layer.id, await loadImage(layer.src)); }
      catch (error) { imageErrors.set(layer.src, error.message); }
    }));
    if (renderVersions.get(canvas) !== version) return;
    if (canvas.width !== scene.width) canvas.width = scene.width;
    if (canvas.height !== scene.height) canvas.height = scene.height;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, scene.width, scene.height);
    ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    if (scene.background && scene.background !== 'transparent') { ctx.fillStyle = color(scene.background, '#FFFFFF'); ctx.fillRect(0, 0, scene.width, scene.height); }
    for (const layer of scene.layers || []) {
      if (layer.hidden || number(layer.opacity, 1) <= 0) continue;
      ctx.save(); ctx.globalAlpha = clamp(number(layer.opacity, 1), 0, 1);
      if (layer.type === 'image') {
        if (images.has(layer.id)) drawImageLayer(ctx, images.get(layer.id), layer, scene);
        else drawMissingImage(ctx, layer, scene);
      } else if (layer.type === 'rect') {
        ctx.fillStyle = color(layer.color, '#FFFFFF');
        const rx = number(layer.x) * scene.width, ry = number(layer.y) * scene.height;
        const rw = Math.max(0, number(layer.w) * scene.width), rh = Math.max(0, number(layer.h) * scene.height);
        if (layer.role === 'shape' && (layer.shape === 'circle' || layer.shape === 'ellipse')) {
          ctx.beginPath(); ctx.ellipse(rx + rw / 2, ry + rh / 2, rw / 2, rh / 2, 0, 0, Math.PI * 2); ctx.fill();
        } else if (layer.role === 'shape' && layer.shape === 'triangle') {
          ctx.beginPath(); ctx.moveTo(rx + rw / 2, ry); ctx.lineTo(rx + rw, ry + rh); ctx.lineTo(rx, ry + rh); ctx.closePath(); ctx.fill();
        } else if (layer.role === 'shape' && layer.shape === 'diamond') {
          ctx.beginPath(); ctx.moveTo(rx + rw / 2, ry); ctx.lineTo(rx + rw, ry + rh / 2); ctx.lineTo(rx + rw / 2, ry + rh); ctx.lineTo(rx, ry + rh / 2); ctx.closePath(); ctx.fill();
        } else {
          roundedRect(ctx, rx, ry, rw, rh, number(layer.radius) * Math.min(scene.width, scene.height)); ctx.fill();
        }
      } else if (layer.type === 'text') drawText(ctx, layer, scene);
      ctx.restore();
    }
    const selected = (scene.layers || []).find(layer => layer.id === (typeof selection === 'object' && selection ? selection.id : selection));
    if (selected) {
      const handle = selectionHandles(selected, canvas, scene);
      ctx.save(); ctx.strokeStyle = '#186749'; ctx.fillStyle = '#FFFFFF'; ctx.lineWidth = 1.5 * handle.scale;
      ctx.strokeRect(handle.x, handle.y, handle.w, handle.h);
      handle.points.forEach(point => { const s = 7 * handle.scale; ctx.fillRect(point.x - s / 2, point.y - s / 2, s, s); ctx.strokeRect(point.x - s / 2, point.y - s / 2, s, s); });
      ctx.restore();
    }
  }

  function validate(scene) {
    const results = [];
    const add = (level, message, layer) => results.push(Object.assign({level, message}, layer ? {layerId: layer.id} : {}));
    try { checkedSize(scene.width, scene.height); }
    catch (error) { add('error', error.message); return results; }
    const ctx = canvasElement(1, 1).getContext('2d');
    const layers = (scene.layers || []).filter(layer => !layer.hidden && number(layer.opacity, 1) > 0);
    const textLayers = [];
    let textArea = 0;
    if (!layers.some(layer => layer.type === 'image')) add('error', 'Dodaj zdjęcie produktu, tło lub logo do tego formatu.');
    for (const layer of layers) {
      const name = layerName(layer);
      if (!['text', 'image', 'rect'].includes(layer.type)) { add('error', name + ': nieobsługiwany typ warstwy.', layer); continue; }
      if (![layer.x, layer.y, layer.w, layer.h].every(value => Number.isFinite(Number(value))) || number(layer.w) <= 0 || number(layer.h) <= 0) {
        add('error', name + ': ustaw prawidłowy rozmiar i pozycję.', layer); continue;
      }
      if (number(layer.x) < -0.0001 || number(layer.y) < -0.0001 || number(layer.x) + number(layer.w) > 1.0001 || number(layer.y) + number(layer.h) > 1.0001) add('error', name + ': warstwa wychodzi poza obszar obrazu. Zmniejsz ją lub przesuń.', layer);
      if (layer.type === 'image') {
        if (!layer.src) add('error', name + ': brakuje materiału. Dodaj ' + (layer.role === 'background' ? 'tło' : layer.role === 'element' ? 'Element' : 'zdjęcie') + ' przed eksportem.', layer);
        else {
          try { localSource(layer.src); }
          catch (error) { add('error', name + ': ' + error.message, layer); }
          if (imageErrors.has(layer.src)) add('error', name + ': ' + imageErrors.get(layer.src), layer);
        }
        if (layer.role === 'product' && layer.fit === 'cover') add('warning', 'Produkt jest kadrowany. Sprawdź, czy kadr nie ucina ważnych części.', layer);
        if (scene.clean && layer.role === 'product' && (layer.x < 0.099 || layer.y < 0.099 || layer.x + layer.w > 0.901 || layer.y + layer.h > 0.901)) add('warning', 'Produkt wychodzi poza środkowe 80% obrazu. W reklamie elastycznej brzegi mogą zostać przycięte.', layer);
      }
      if (layer.type === 'text' && String(layer.text || '').trim()) {
        const layout = textLayout(ctx, layer, scene);
        if (layout.overflow) add('error', name + ': tekst nie mieści się w polu. Skróć go lub powiększ pole. Podgląd pokazuje wielokropek.', layer);
        else if (layout.size < 10.5) add('warning', name + ': tekst ma mniej niż 11 px w pliku wynikowym. Sprawdź czytelność w rzeczywistym rozmiarze.', layer);
        else if (layout.size < layout.requested * 0.72) add('warning', name + ': tekst został mocno pomniejszony, aby zmieścić się w polu. Rozważ krótszą wersję.', layer);
        if (scene.brand && layer.fontFamily && layer.fontFamily !== scene.brand.font_family) add('warning', name + ': wybrana czcionka różni się od czcionki Brand Kit.', layer);
        if (scene.brand) {
          const palette = [scene.brand.color, scene.brand.secondary_color, scene.brand.text_color, '#000000', '#FFFFFF', '#101819'].filter(Boolean).map(canonicalColor);
          if (layer.color && !palette.includes(canonicalColor(layer.color))) add('warning', name + ': kolor tekstu jest spoza palety Brand Kit.', layer);
          if (layer.backgroundColor && !palette.includes(canonicalColor(layer.backgroundColor))) add('warning', name + ': kolor pola jest spoza palety Brand Kit.', layer);
        }
        // Assess contrast only on a known solid fill. Photographic contrast is not guessed.
        let solid = scene.background && scene.background !== 'transparent' ? color(scene.background) : null;
        for (const lower of layers.slice(0, layers.indexOf(layer))) {
          const intersects = lower.x < layer.x + layer.w && lower.x + lower.w > layer.x && lower.y < layer.y + layer.h && lower.y + lower.h > layer.y;
          if (!intersects) continue;
          if (lower.type === 'image') solid = null;
          if (lower.type === 'rect' && number(lower.opacity, 1) >= 0.99 && lower.x <= layer.x && lower.y <= layer.y && lower.x + lower.w >= layer.x + layer.w && lower.y + lower.h >= layer.y + layer.h) {
            const curvedShape = lower.role === 'shape' && ['circle', 'ellipse', 'triangle', 'diamond'].includes(lower.shape);
            if (!curvedShape || (lower.shape === 'circle' && lower.w === lower.h)) {
              // A curved shape's bounding box is mostly transparent: it is not a
              // solid background unless the text sits within the visible geometry.
              if (!curvedShape || shapeContains(lower, layer.x * scene.width, layer.y * scene.height, scene.width, scene.height) && shapeContains(lower, (layer.x + layer.w) * scene.width, (layer.y + layer.h) * scene.height, scene.width, scene.height)) solid = color(lower.color);
            } else solid = null;
          }
        }
        if (layer.backgroundColor) solid = color(layer.backgroundColor);
        if (solid && number(layer.opacity, 1) >= 0.99) {
          const a = luminance(layer.color), b = luminance(solid);
          const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          const threshold = layout.size >= 24 || (layout.size >= 18.66 && number(layer.fontWeight, 400) >= 700) ? 3 : 4.5;
          if (ratio < threshold) add('warning', name + ': niski kontrast tekstu na jednolitym tle (' + ratio.toFixed(1) + ':1). Wybierz ciemniejszy lub jaśniejszy kolor.', layer);
        }
        textArea += Math.max(0, number(layer.w) * number(layer.h));
        textLayers.push(layer);
      }
    }
    for (let i = 0; i < textLayers.length; i++) for (let j = i + 1; j < textLayers.length; j++) {
      const a = textLayers[i], b = textLayers[j];
      const intersection = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
      if (intersection > 0.001) add('warning', layerName(a) + ' i ' + layerName(b).toLowerCase() + ': pola tekstowe nachodzą na siebie. Sprawdź kompozycję.', b);
    }
    if (textArea > 0.35) add('warning', 'Pola tekstowe zajmują około ' + Math.round(textArea * 100) + '% obrazu. To wskazówka kompozycyjna, a nie uniwersalny limit Google Ads.');
    (scene.omitted || []).forEach(item => add('warning', item.message));
    return results;
  }

  function toBlob(canvas, type, quality) {
    return new Promise((resolve, reject) => {
      canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Przeglądarka nie mogła zapisać obrazu. Spróbuj ponownie.')), type, quality);
    });
  }

  async function renderBlob(scene, {type = 'image/jpeg', maxBytes = 5 * 1024 * 1024, quality = 0.92} = {}) {
    if (!['image/jpeg', 'image/png'].includes(type)) throw new Error('Wybierz format JPEG lub PNG.');
    const [width, height] = checkedSize(scene.width, scene.height);
    const canvas = canvasElement(width, height);
    const output = clone(scene);
    if (type === 'image/jpeg' && (!output.background || output.background === 'transparent')) output.background = '#FFFFFF';
    await render(canvas, output);
    const warnings = validate(output);
    const errors = warnings.filter(item => item.level === 'error');
    if (errors.length) throw new Error(errors.map(item => item.message).join(' '));
    const limit = Math.max(1, number(maxBytes, 5 * 1024 * 1024));
    let selectedQuality = clamp(number(quality, 0.92), 0.2, 1);
    let blob = await toBlob(canvas, type, selectedQuality);
    if (blob.size <= limit) return {blob, warnings};
    if (type === 'image/png') throw new Error('PNG przekracza limit ' + Math.round(limit / 1024) + ' KB. Zmniejsz złożoność obrazu lub wybierz inny format.');
    // Keep exact output dimensions; never quietly downsample a required Ads format.
    const minimumQuality = 0.20;
    const smallest = await toBlob(canvas, type, minimumQuality);
    if (smallest.size > limit) throw new Error('Nie można zmieścić JPEG w limicie ' + Math.round(limit / 1024) + ' KB przy wymaganych wymiarach. Uprość tło lub kompozycję.');
    let lo = minimumQuality, hi = selectedQuality, best = smallest;
    for (let i = 0; i < 7; i++) {
      const mid = (lo + hi) / 2;
      const candidate = await toBlob(canvas, type, mid);
      if (candidate.size <= limit) { best = candidate; lo = mid; } else hi = mid;
    }
    blob = best; selectedQuality = lo;
    if (selectedQuality < 0.55) warnings.push({level: 'warning', message: 'Silna kompresja JPEG była potrzebna do zachowania limitu pliku. Obejrzyj szczegóły gotowego pliku przed użyciem.'});
    return {blob, warnings};
  }

  class Editor {
    constructor(canvas, {scene, onChange = () => {}, onSelect = () => {}} = {}) {
      this.canvas = canvas; this.scene = clone(scene || makeScene()); this.onChange = onChange; this.onSelect = onSelect;
      this.selectedId = null; this._drag = null; this._destroyed = false; this._raf = null;
      this._oldTouchAction = canvas.style.touchAction; this._oldTabIndex = canvas.getAttribute('tabindex');
      canvas.style.touchAction = 'none'; canvas.tabIndex = 0;
      canvas.setAttribute('aria-label', 'Edytor kompozycji. Wybierz warstwę myszą lub na liście. Strzałki przesuwają, Shift przyspiesza, Delete usuwa.');
      this._handlers = {
        pointerdown: event => this._pointerDown(event), pointermove: event => this._pointerMove(event),
        pointerup: event => this._pointerUp(event), pointercancel: event => this._pointerUp(event),
        keydown: event => this._keyDown(event),
      };
      Object.entries(this._handlers).forEach(([name, handler]) => canvas.addEventListener(name, handler));
      this._draw();
    }

    _draw() {
      if (this._destroyed || this._raf !== null) return;
      this._raf = requestAnimationFrame(() => {
        this._raf = null;
        render(this.canvas, this.scene, {selection: this.selectedId}).catch(error => {
          if (!this._destroyed) this.canvas.dispatchEvent(new CustomEvent('studio-error', {detail: error.message, bubbles: true}));
        });
      });
    }

    _point(event) {
      const rect = this.canvas.getBoundingClientRect();
      return {x: (event.clientX - rect.left) / Math.max(1, rect.width), y: (event.clientY - rect.top) / Math.max(1, rect.height)};
    }

    _selected() { return this.scene.layers.find(layer => layer.id === this.selectedId) || null; }
    _changed() { this.onChange(this.getScene()); }

    setScene(scene) {
      this.scene = clone(scene);
      if (!this.scene.layers.some(layer => layer.id === this.selectedId)) this.selectedId = null;
      this._drag = null; this._draw();
    }

    getScene() { return clone(this.scene); }

    select(id) {
      this.selectedId = this.scene.layers.some(layer => layer.id === id) ? id : null;
      this.onSelect(this._selected() ? clone(this._selected()) : null); this._draw();
    }

    updateSelected(props) {
      const layer = this._selected(); if (!layer) return;
      const allowed = ['x', 'y', 'w', 'h', 'src', 'asset_id', 'text', 'color', 'fontFamily', 'fontSize', 'fontWeight', 'align', 'opacity', 'fit', 'cropX', 'cropY', 'backgroundColor', 'radius', 'cornerRadius', 'borderWidth', 'borderColor', 'verticalAlign', 'hidden', 'locked'];
      allowed.forEach(key => { if (Object.prototype.hasOwnProperty.call(props, key)) layer[key] = props[key]; });
      if (pixelLocked(layer) && (Object.prototype.hasOwnProperty.call(props, 'w') || Object.prototype.hasOwnProperty.call(props, 'h'))) {
        if (Object.prototype.hasOwnProperty.call(props, 'w')) snapSquareAnchored(layer, this.scene.width, this.scene.height);
        else {
          let h = clamp(number(layer.h, 0.1), 0.012, Math.max(0.012, 1 - number(layer.y, 0)));
          let w = h * this.scene.height / this.scene.width;
          if (number(layer.x, 0) + w > 1) { w = Math.max(0.012, 1 - number(layer.x, 0)); h = w * this.scene.width / this.scene.height; }
          layer.w = w; layer.h = h;
        }
      }
      if (layer.type === 'text' && this.scene.content) this.scene.content[layer.role] = String(layer.text || '');
      // Property inputs are already selected. Re-emitting onSelect here would
      // recreate the property form and steal focus after every typed character.
      this._changed(); this._draw();
    }

    addLayer(layer) {
      if (!layer || !layer.id || !['image', 'text', 'rect'].includes(layer.type)) throw new Error('Nieprawidłowa warstwa.');
      if (this.scene.layers.some(item => item.id === layer.id)) throw new Error('Ten materiał jest już w kompozycji.');
      this.scene.layers.push(clone(layer));
      if (layer.role === 'product') this.scene.productOrder = (this.scene.productOrder || []).concat(layer.id);
      this.select(layer.id); this._changed(); this._draw();
    }

    removeSelected() {
      if (!this.selectedId) return;
      this.scene.layers = this.scene.layers.filter(layer => layer.id !== this.selectedId);
      if (this.scene.productOrder) this.scene.productOrder = this.scene.productOrder.filter(id => id !== this.selectedId);
      this.selectedId = null; this.onSelect(null); this._changed(); this._draw();
    }

    _pointerDown(event) {
      if (event.button !== 0 && event.pointerType !== 'touch') return;
      const point = this._point(event);
      let selected = this._selected(), corner = null;
      if (selected && !selected.locked) {
        const h = selectionHandles(selected, this.canvas, this.scene);
        const tolerance = 11 * h.scale;
        const handle = h.points.find(item => Math.abs(point.x * this.scene.width - item.x) < tolerance && Math.abs(point.y * this.scene.height - item.y) < tolerance);
        if (handle) corner = handle.corner;
      }
      if (!corner) {
        selected = [...this.scene.layers].reverse().find(layer => !layer.hidden && !layer.locked && number(layer.opacity, 1) > 0 && (layer.type !== 'rect' || !layer.role || layer.role !== 'shape' || !layer.shape || layer.shape === 'rectangle' || layer.shape === 'square'
          ? point.x >= layer.x && point.x <= layer.x + layer.w && point.y >= layer.y && point.y <= layer.y + layer.h
          : shapeContains(layer, point.x * this.scene.width, point.y * this.scene.height, this.scene.width, this.scene.height))) || null;
        this.select(selected ? selected.id : null);
      }
      this.canvas.focus({preventScroll: true});
      if (!selected || selected.locked) return;
      event.preventDefault();
      this.canvas.setPointerCapture(event.pointerId);
      this._drag = {pointerId: event.pointerId, start: point, initial: clone(selected), corner, changed: false};
    }

    _pointerMove(event) {
      if (!this._drag || event.pointerId !== this._drag.pointerId) return;
      const layer = this._selected(); if (!layer) return;
      const point = this._point(event), drag = this._drag, initial = drag.initial;
      const dx = point.x - drag.start.x, dy = point.y - drag.start.y;
      if (drag.corner) {
        let left = initial.x, top = initial.y, right = initial.x + initial.w, bottom = initial.y + initial.h;
        const minW = Math.max(0.012, 5 / this.scene.width), minH = Math.max(0.012, 5 / this.scene.height);
        if (drag.corner.includes('e')) right = clamp(right + dx, left + minW, 1);
        else left = clamp(left + dx, 0, right - minW);
        if (drag.corner.includes('s')) bottom = clamp(bottom + dy, top + minH, 1);
        else top = clamp(top + dy, 0, bottom - minH);
        Object.assign(layer, {x: left, y: top, w: right - left, h: bottom - top});
        if (layer.shape === 'square') snapSquareToCorner(layer, this.scene.width, this.scene.height, drag.corner, initial);
        else if (layer.shape === 'circle') snapSquareToCorner(layer, this.scene.width, this.scene.height, drag.corner, initial);
      } else {
        layer.x = clamp(initial.x + dx, 0, Math.max(0, 1 - layer.w));
        layer.y = clamp(initial.y + dy, 0, Math.max(0, 1 - layer.h));
      }
      drag.changed = Math.abs(dx) + Math.abs(dy) > 0.001 || drag.changed;
      this._draw(); event.preventDefault();
    }

    _pointerUp(event) {
      if (!this._drag || event.pointerId !== this._drag.pointerId) return;
      const changed = this._drag.changed; this._drag = null;
      if (this.canvas.hasPointerCapture(event.pointerId)) this.canvas.releasePointerCapture(event.pointerId);
      if (changed) { this._changed(); this.onSelect(this._selected() ? clone(this._selected()) : null); }
    }

    _keyDown(event) {
      const layer = this._selected();
      if (event.key === 'Escape') { this.select(null); return; }
      if (!layer || layer.locked || event.ctrlKey || event.metaKey) return;
      if (['Delete', 'Backspace'].includes(event.key)) { event.preventDefault(); this.removeSelected(); return; }
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
      event.preventDefault(); const step = event.shiftKey ? 10 : 1;
      const dx = event.key === 'ArrowLeft' ? -step / this.scene.width : event.key === 'ArrowRight' ? step / this.scene.width : 0;
      const dy = event.key === 'ArrowUp' ? -step / this.scene.height : event.key === 'ArrowDown' ? step / this.scene.height : 0;
      if (event.altKey) { layer.w = clamp(layer.w + dx, 0.012, 1 - layer.x); layer.h = clamp(layer.h + dy, 0.012, 1 - layer.y); if (pixelLocked(layer)) snapSquareAnchored(layer, this.scene.width, this.scene.height); }
      else { layer.x = clamp(layer.x + dx, 0, Math.max(0, 1 - layer.w)); layer.y = clamp(layer.y + dy, 0, Math.max(0, 1 - layer.h)); }
      this._changed(); this.onSelect(clone(layer)); this._draw();
    }

    destroy() {
      this._destroyed = true;
      if (this._raf !== null) cancelAnimationFrame(this._raf);
      renderVersions.set(this.canvas, (renderVersions.get(this.canvas) || 0) + 1);
      Object.entries(this._handlers).forEach(([name, handler]) => this.canvas.removeEventListener(name, handler));
      this.canvas.style.touchAction = this._oldTouchAction;
      if (this._oldTabIndex === null) this.canvas.removeAttribute('tabindex'); else this.canvas.setAttribute('tabindex', this._oldTabIndex);
    }
  }

  class MaskEditor {
    constructor(canvas, {originalUrl, cutoutUrl, onChange = () => {}, onError = () => {}} = {}) {
      this.canvas = canvas; this.onChange = onChange; this.onError = onError; this.mode = 'erase'; this.brushSize = 50; this.brushHardness = .72; this.areaTolerance = 8; this._refinement = {recovery: 0, feather: 0}; this._refinementBase = null; this._undo = []; this._undoBytes = 0; this._stroke = null; this._destroyed = false;
      this._oldTouchAction = canvas.style.touchAction; this._oldBackground = canvas.style.background; this._oldCursor = canvas.style.cursor;
      canvas.style.touchAction = 'none'; canvas.style.cursor = 'crosshair';
      canvas.style.background = 'repeating-conic-gradient(#DCE2DC 0% 25%, #FFFFFF 0% 50%) 0 / 20px 20px';
      canvas.setAttribute('aria-label', 'Korekta maski. Użyj pędzla albo kliknij fragment w trybie Usuń obszar.');
      this._handlers = {pointerdown: event => this._down(event), pointermove: event => this._move(event), pointerup: event => this._up(event), pointercancel: event => this._up(event)};
      this.ready = this._initialize(originalUrl, cutoutUrl);
    }

    async _initialize(originalUrl, cutoutUrl) {
      const [original, cutout] = await Promise.all([loadImage(originalUrl), loadImage(cutoutUrl || originalUrl)]);
      if (this._destroyed) return;
      const [w, h] = checkedSize(original.naturalWidth, original.naturalHeight);
      this.canvas.width = w; this.canvas.height = h;
      this.ctx = this.canvas.getContext('2d', {willReadFrequently: true});
      this.mask = canvasElement(w, h); this.maskCtx = this.mask.getContext('2d', {willReadFrequently: true});
      this.ctx.drawImage(original, 0, 0, w, h);
      this.original = this.ctx.getImageData(0, 0, w, h);
      this.display = new ImageData(new Uint8ClampedArray(this.original.data), w, h);
      this.maskCtx.drawImage(cutout, 0, 0, w, h);
      const data = this.maskCtx.getImageData(0, 0, w, h);
      this.initialAlpha = new Uint8Array(w * h);
      for (let p = 0; p < w * h; p++) {
        const a = this.original.data[p * 4 + 3];
        const alpha = a ? clamp(Math.round(data.data[p * 4 + 3] * 255 / a), 0, 255) : 0;
        this.initialAlpha[p] = alpha;
        data.data[p * 4] = data.data[p * 4 + 1] = data.data[p * 4 + 2] = 255; data.data[p * 4 + 3] = alpha;
      }
      this.maskCtx.putImageData(data, 0, 0);
      this._refinementBase = this.initialAlpha;
      this._renderRegion({x: 0, y: 0, w, h});
      Object.entries(this._handlers).forEach(([name, handler]) => this.canvas.addEventListener(name, handler));
    }

    setBrush(mode, size, hardness = .72) {
      this.mode = ['restore', 'area'].includes(mode) ? mode : 'erase';
      this.brushSize = clamp(number(size, 50), 1, 1000);
      this.brushHardness = clamp(number(hardness, .72), 0, 1);
    }

    setAreaTolerance(percent = 8) { this.areaTolerance = clamp(number(percent, 8), 0, 100); }

    removeArea(x, y) {
      if (!this.maskCtx || this._stroke || this._destroyed || !Number.isFinite(x) || !Number.isFinite(y)) return 0;
      const width = this.canvas.width, height = this.canvas.height;
      x = Math.floor(x); y = Math.floor(y);
      if (x < 0 || y < 0 || x >= width || y >= height) return 0;
      const seed = y * width + x, rgb = this.original.data, visible = this.display.data;
      if (!rgb[seed * 4 + 3] || !visible[seed * 4 + 3]) return 0;
      const red = rgb[seed * 4], green = rgb[seed * 4 + 1], blue = rgb[seed * 4 + 2];
      const tolerance = this.areaTolerance * 255 / 100;
      let before, alpha, removed = 0, leftBound = width, rightBound = 0, topBound = height, bottomBound = 0;
      try {
        // Work on a byte mask until the complete region is known. A limit failure
        // leaves both the visible mask and its undo/refinement history untouched.
        before = this._snapshot(); alpha = new Uint8Array(before);
        let pending = new Int32Array(1024), length = 0, spans = 0;
        const maxPending = 131072, maxSpans = Math.min(alpha.length, 1000000);
        const matches = p => {
          const i = p * 4;
          return alpha[p] > 0 && visible[i + 3] > 0 && rgb[i + 3] > 0 &&
            Math.abs(rgb[i] - red) <= tolerance && Math.abs(rgb[i + 1] - green) <= tolerance && Math.abs(rgb[i + 2] - blue) <= tolerance;
        };
        const push = p => {
          if (length === maxPending) throw new RangeError('area-complexity');
          if (length === pending.length) { const next = new Int32Array(Math.min(maxPending, pending.length * 2)); next.set(pending); pending = next; }
          pending[length++] = p;
        };
        push(seed);
        while (length) {
          const p = pending[--length];
          if (!matches(p)) continue;
          if (++spans > maxSpans) throw new RangeError('area-complexity');
          const row = Math.floor(p / width), start = row * width;
          let left = p - start, right = left;
          while (left > 0 && matches(start + left - 1)) left--;
          while (right + 1 < width && matches(start + right + 1)) right++;
          alpha.fill(0, start + left, start + right + 1); removed += right - left + 1;
          leftBound = Math.min(leftBound, left); rightBound = Math.max(rightBound, right);
          topBound = Math.min(topBound, row); bottomBound = Math.max(bottomBound, row);
          // Only edge-sharing pixels connect regions. All comparisons retain the
          // clicked color, so a gradual color ramp cannot walk into the product.
          for (let direction = -1; direction <= 1; direction += 2) {
            const nextRow = row + direction;
            if (nextRow < 0 || nextRow >= height) continue;
            let inRun = false;
            for (let xx = left; xx <= right; xx++) {
              const q = nextRow * width + xx, match = matches(q);
              if (match && !inRun) push(q);
              inRun = match;
            }
          }
        }
      } catch (error) {
        this.onError(new Error('Ten obszar jest zbyt złożony. Zmniejsz tolerancję lub użyj pędzla. Maska nie została zmieniona.'));
        return 0;
      }
      if (!removed) return 0;
      const w = rightBound - leftBound + 1, h = bottomBound - topBound + 1;
      let region;
      try { region = this.maskCtx.getImageData(leftBound, topBound, w, h); }
      catch (error) { this.onError(new Error('Nie udało się przygotować maski. Użyj pędzla lub spróbuj ponownie. Maska nie została zmieniona.')); return 0; }
      this._remember(before);
      this._refinementBase = alpha; this._refinement = {recovery: 0, feather: 0};
      for (let yy = 0; yy < h; yy++) for (let xx = 0; xx < w; xx++) {
        const p = (topBound + yy) * width + leftBound + xx;
        region.data[(yy * w + xx) * 4 + 3] = alpha[p];
        visible[p * 4 + 3] = Math.round(rgb[p * 4 + 3] * alpha[p] / 255);
      }
      this.maskCtx.putImageData(region, leftBound, topBound);
      this.ctx.putImageData(this.display, 0, 0, leftBound, topBound, w, h); this.onChange();
      return removed;
    }

    getRefinement() { return {...this._refinement}; }

    applyRefinement({recovery = 0, feather = 0} = {}) {
      if (!this.maskCtx || this._stroke) return;
      recovery = clamp(number(recovery), 0, 100); feather = clamp(number(feather), 0, 3);
      if (recovery === this._refinement.recovery && feather === this._refinement.feather) return;
      this._remember();
      if (!this._refinementBase) this._refinementBase = this._snapshot();
      const alpha = new Uint8Array(this._refinementBase.length), lut = new Uint8Array(256);
      // Lift uncertain foreground without reviving confidently empty background.
      // Hand restoration is available for regions the model removed completely.
      for (let a = 0; a < 256; a++) lut[a] = Math.round(255 * (a / 255) ** (1 - .8 * recovery / 100));
      for (let p = 0; p < alpha.length; p++) alpha[p] = lut[this._refinementBase[p]];
      if (feather > 0) {
        const radius = Math.ceil(feather), width = this.canvas.width, height = this.canvas.height;
        const horizontal = new Uint8Array(alpha.length), blurred = new Uint8Array(alpha.length);
        const span = radius * 2 + 1;
        // Separable bounded box blur: linear work and two one-byte buffers,
        // including for large photographs. Edge pixels are extended.
        for (let y = 0; y < height; y++) {
          const row = y * width; let sum = 0;
          for (let k = -radius; k <= radius; k++) sum += alpha[row + clamp(k, 0, width - 1)];
          for (let x = 0; x < width; x++) {
            horizontal[row + x] = Math.round(sum / span);
            sum += alpha[row + clamp(x + radius + 1, 0, width - 1)] - alpha[row + clamp(x - radius, 0, width - 1)];
          }
        }
        for (let x = 0; x < width; x++) {
          let sum = 0;
          for (let k = -radius; k <= radius; k++) sum += horizontal[clamp(k, 0, height - 1) * width + x];
          for (let y = 0; y < height; y++) {
            blurred[y * width + x] = Math.round(sum / span);
            sum += horizontal[clamp(y + radius + 1, 0, height - 1) * width + x] - horizontal[clamp(y - radius, 0, height - 1) * width + x];
          }
        }
        const strength = Math.min(1, feather);
        for (let p = 0; p < alpha.length; p++) alpha[p] = Math.round(alpha[p] * (1 - strength) + blurred[p] * strength);
      }
      this._refinement = {recovery, feather}; this._applyAlpha(alpha); this.onChange();
    }

    _point(event) {
      const rect = this.canvas.getBoundingClientRect();
      return {x: (event.clientX - rect.left) * this.canvas.width / Math.max(1, rect.width), y: (event.clientY - rect.top) * this.canvas.height / Math.max(1, rect.height)};
    }

    _snapshot() {
      const data = this.maskCtx.getImageData(0, 0, this.canvas.width, this.canvas.height).data;
      const alpha = new Uint8Array(this.canvas.width * this.canvas.height);
      for (let p = 0; p < alpha.length; p++) alpha[p] = data[p * 4 + 3];
      return alpha;
    }

    _remember(alpha = this._snapshot()) {
      const base = this._refinementBase;
      const bytes = alpha.byteLength + (base ? base.byteLength : 0);
      this._undo.push({alpha, base, refinement: {...this._refinement}, bytes}); this._undoBytes += bytes;
      while (this._undo.length > 8 || (this._undoBytes > 64 * 1024 * 1024 && this._undo.length > 1)) this._undoBytes -= this._undo.shift().bytes;
    }

    _applyAlpha(alpha) {
      const w = this.canvas.width, h = this.canvas.height;
      const data = this.maskCtx.createImageData(w, h);
      for (let p = 0; p < alpha.length; p++) { data.data[p * 4] = data.data[p * 4 + 1] = data.data[p * 4 + 2] = 255; data.data[p * 4 + 3] = alpha[p]; }
      this.maskCtx.putImageData(data, 0, 0); this._renderRegion({x: 0, y: 0, w, h});
    }

    _renderRegion(rect) {
      const x = clamp(Math.floor(rect.x), 0, this.canvas.width - 1), y = clamp(Math.floor(rect.y), 0, this.canvas.height - 1);
      const w = clamp(Math.ceil(rect.x + rect.w) - x, 1, this.canvas.width - x), h = clamp(Math.ceil(rect.y + rect.h) - y, 1, this.canvas.height - y);
      const mask = this.maskCtx.getImageData(x, y, w, h).data;
      for (let yy = 0; yy < h; yy++) for (let xx = 0; xx < w; xx++) {
        const pos = ((y + yy) * this.canvas.width + x + xx) * 4 + 3;
        this.display.data[pos] = Math.round(this.original.data[pos] * mask[(yy * w + xx) * 4 + 3] / 255);
      }
      this.ctx.putImageData(this.display, 0, 0, x, y, w, h);
    }

    _paint(from, to) {
      const radius = this.brushSize / 2;
      const distance = Math.hypot(to.x - from.x, to.y - from.y);
      const count = Math.max(1, Math.ceil(distance / Math.max(1, radius * 0.25)));
      this.maskCtx.save(); this.maskCtx.globalCompositeOperation = this.mode === 'erase' ? 'destination-out' : 'source-over';
      for (let i = 0; i <= count; i++) {
        const x = from.x + (to.x - from.x) * i / count, y = from.y + (to.y - from.y) * i / count;
        if (this.brushHardness >= .999) this.maskCtx.fillStyle = '#FFFFFF';
        else {
          const gradient = this.maskCtx.createRadialGradient(x, y, radius * this.brushHardness, x, y, radius);
          gradient.addColorStop(0, '#FFFFFF'); gradient.addColorStop(1, 'rgba(255,255,255,0)');
          this.maskCtx.fillStyle = gradient;
        } this.maskCtx.beginPath(); this.maskCtx.arc(x, y, radius, 0, Math.PI * 2); this.maskCtx.fill();
      }
      this.maskCtx.restore();
      this._renderRegion({x: Math.min(from.x, to.x) - radius - 2, y: Math.min(from.y, to.y) - radius - 2, w: Math.abs(to.x - from.x) + radius * 2 + 4, h: Math.abs(to.y - from.y) + radius * 2 + 4});
    }

    _down(event) {
      if (!this.maskCtx || (event.button !== 0 && event.pointerType !== 'touch')) return;
      event.preventDefault();
      const point = this._point(event);
      if (this.mode === 'area') { this.removeArea(point.x, point.y); return; }
      this._remember(); this._refinement = {recovery: 0, feather: 0};
      this._stroke = {pointerId: event.pointerId, point}; this.canvas.setPointerCapture(event.pointerId); this._paint(point, point);
    }

    _move(event) {
      if (!this._stroke || event.pointerId !== this._stroke.pointerId) return;
      event.preventDefault(); const point = this._point(event); this._paint(this._stroke.point, point); this._stroke.point = point;
    }

    _up(event) {
      if (!this._stroke || event.pointerId !== this._stroke.pointerId) return;
      this._stroke = null;
      if (this.canvas.hasPointerCapture(event.pointerId)) this.canvas.releasePointerCapture(event.pointerId);
      this._refinementBase = this._snapshot();
      this.onChange();
    }

    undo() {
      if (!this._undo.length || !this.maskCtx) return;
      const previous = this._undo.pop(); this._undoBytes -= previous.bytes;
      this._refinementBase = previous.base; this._refinement = previous.refinement;
      this._applyAlpha(previous.alpha); this.onChange();
    }

    reset() {
      if (!this.maskCtx) return;
      this._remember(); this._refinementBase = this.initialAlpha; this._refinement = {recovery: 0, feather: 0};
      this._applyAlpha(this.initialAlpha); this.onChange();
    }

    async exportBlob() { await this.ready; return toBlob(this.canvas, 'image/png'); }

    destroy() {
      this._destroyed = true;
      Object.entries(this._handlers).forEach(([name, handler]) => this.canvas.removeEventListener(name, handler));
      this.canvas.style.touchAction = this._oldTouchAction; this.canvas.style.background = this._oldBackground; this.canvas.style.cursor = this._oldCursor;
      this._undo = []; this._undoBytes = 0; this.original = null; this.display = null; this.initialAlpha = null; this._refinementBase = null; this.mask = null; this.maskCtx = null;
    }
  }

  global.StudioCanvas = Object.freeze({templates, makeScene, makeShape, adaptScene, render, renderBlob, validate, shapeContains, Editor, MaskEditor});
})(window);
