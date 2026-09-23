/* Portable layout recipes. Source campaign files and copy never enter a recipe. */
(function (global) {
  'use strict';

  const builtIns = new Set(['split', 'spotlight', 'minimal', 'catalog', 'benefits', 'label', 'backdrop', 'bundle', 'bold']);
  const palette = ['color', 'secondary_color', 'text_color'];
  const imageRoles = new Set(['product', 'element', 'background', 'logo']);
  const textRoles = new Set(['headline', 'description', 'cta']);
  const decorationIds = new Set(['ribbon-paper', 'ribbon-panel', 'ribbon-content', 'brand-rule', 'text-panel', 'product-panel', 'lower-panel',
    'catalog-shelf', 'catalog-rule', 'benefits-photo', 'benefits-description', 'benefits-rule', 'label-rule', 'label-product', 'backdrop-copy', 'bundle-hero', 'bundle-rule', 'bold-field', 'bold-product', 'bold-logo']);
  const systemFonts = new Set(['Arial', 'Helvetica', 'Verdana', 'Georgia', 'Tahoma', 'Trebuchet MS', 'Times New Roman', 'sans-serif', 'serif', 'monospace']);
  const numericStyles = ['opacity', 'fontSize', 'baseFontSize', 'cropX', 'cropY', 'radius', 'cornerRadius', 'borderWidth'];
  const booleanStyles = ['hidden', 'locked'];
  const enums = {align: ['left', 'center', 'right'], verticalAlign: ['top', 'middle', 'bottom'], fit: ['contain', 'cover']};
  const defaults = {color: '#E76A25', secondary_color: '#F4F1EC', text_color: '#182021', font_family: 'Arial'};
  const clone = value => JSON.parse(JSON.stringify(value));
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const failure = () => new Error('Nie można odczytać układu szablonu.');

  function hex(value) {
    if (typeof value !== 'string' || !/^#[a-f\d]{3}(?:[a-f\d]{3})?$/i.test(value)) return null;
    const digits = value.slice(1);
    return '#' + (digits.length === 3 ? Array.from(digits, digit => digit + digit).join('') : digits).toUpperCase();
  }

  function contrast(value) {
    const color = hex(value) || '#182021';
    const channels = [1, 3, 5].map(offset => parseInt(color.slice(offset, offset + 2), 16) / 255)
      .map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4);
    const light = channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
    return (light + .05) / .05 > 1.05 / (light + .05) ? '#101819' : '#FFFFFF';
  }

  function brandData(brand = {}) {
    return {
      color: hex(brand.color) || defaults.color,
      secondary_color: hex(brand.secondary_color) || defaults.secondary_color,
      text_color: hex(brand.text_color) || defaults.text_color,
      font_family: String(brand.font_family || defaults.font_family).slice(0, 150),
      font_url: brand.font_url || null,
      logo_url: brand.logo_url || null,
      logo_asset_id: brand.logo_asset_id || null,
    };
  }

  function colorToken(value, brand, fallback = '@brand.text_color') {
    const normalized = hex(value);
    if (!normalized) return fallback;
    const key = palette.find(key => normalized === brand[key]);
    return key ? '@brand.' + key : normalized;
  }

  function resolveColor(value, brand) {
    if (typeof value === 'string' && value.startsWith('@brand.') && palette.includes(value.slice(7))) return brand[value.slice(7)];
    const normalized = hex(value);
    if (!normalized) throw failure();
    return normalized;
  }

  function canonicalId(role, slot) {
    if (role === 'element' || role === 'decoration' || role === 'shape') return role + '-slot-' + (slot + 1);
    return slot === 0 ? role : role + '-slot-' + (slot + 1);
  }

  function sourceKey(layer, index) {
    // This in-memory key is never serialized. Independent copies in format
    // overrides retain their slot even when the visible z-order differs.
    return layer.type + ':' + layer.role + ':' + String(layer.id ?? ('index-' + index));
  }

  function sceneBasics(scene) {
    if (!scene || !Array.isArray(scene.layers) || !Number.isInteger(scene.width) || !Number.isInteger(scene.height) ||
        scene.width < 1 || scene.height < 1 || scene.width > 8192 || scene.height > 8192 || scene.width * scene.height > 20000000) throw failure();
  }

  function capture({master, formats = {}} = {}) {
    sceneBasics(master);
    const base = builtIns.has(master.template) ? master.template : 'split';
    const scenes = [master, ...Object.values(formats)];
    const mappings = new Map(), nextSlot = new Map();
    for (const scene of scenes) {
      sceneBasics(scene);
      const order = Array.isArray(scene.productOrder) ? scene.productOrder : [];
      const indexed = scene.layers.map((layer, index) => ({layer, index}));
      // Product selection order is independent of layer stacking order.
      const products = indexed.filter(item => item.layer.role === 'product').sort((a, b) => {
        const first = order.indexOf(a.layer.id), second = order.indexOf(b.layer.id);
        return (first < 0 ? a.index + order.length : first) - (second < 0 ? b.index + order.length : second);
      });
      for (const {layer, index} of [...products, ...indexed.filter(item => item.layer.role !== 'product')]) {
        const key = sourceKey(layer, index);
        if (mappings.has(key)) continue;
        const role = layer.role, slot = nextSlot.get(role) || 0;
        if (!(layer.type === 'image' && imageRoles.has(role)) && !(layer.type === 'text' && textRoles.has(role)) && !(layer.type === 'rect' && (role === 'decoration' || role === 'shape'))) throw failure();
        nextSlot.set(role, slot + 1);
        const id = layer.type === 'rect' && decorationIds.has(layer.id) ? layer.id : canonicalId(role, slot);
        mappings.set(key, {id, slot});
      }
    }
    function encode(scene) {
      const brand = brandData(scene.brand || master.brand);
      const layers = scene.layers.map((source, index) => {
        const {id, slot} = mappings.get(sourceKey(source, index));
        const layer = {id, type: source.type, role: source.role};
        for (const key of ['x', 'y', 'w', 'h']) {
          if (!finite(source[key])) throw failure();
          layer[key] = source[key];
        }
        if (source.type === 'image') layer.slot = slot;
        for (const key of numericStyles) if (finite(source[key])) layer[key] = source[key];
        for (const key of booleanStyles) if (typeof source[key] === 'boolean') layer[key] = source[key];
        for (const [key, values] of Object.entries(enums)) if (values.includes(source[key])) layer[key] = source[key];
        for (const key of ['color', 'backgroundColor', 'borderColor']) {
          if (source[key] === undefined) continue;
          layer[key] = colorToken(source[key], brand);
        }
        if (source.type === 'rect' && (source.role === 'decoration' || source.role === 'shape')) {
          if (source.shape !== undefined) {
            if (!['rectangle', 'square', 'circle', 'ellipse', 'triangle', 'diamond'].includes(source.shape)) throw failure();
            layer.shape = source.shape;
          }
        }
        if (source.type === 'text') {
          layer.fontFamily = source.fontFamily === brand.font_family || !systemFonts.has(source.fontFamily) ? '@brand.font' : source.fontFamily;
          const weight = source.fontWeight === 'bold' ? 700 : source.fontWeight === 'normal' ? 400 : Number(source.fontWeight);
          if (Number.isFinite(weight) && weight >= 100 && weight <= 900) layer.fontWeight = weight;
          if (source.role === 'cta' && layer.backgroundColor?.startsWith('@brand.') && hex(source.color) === contrast(source.backgroundColor)) layer.color = '@contrast.background';
          // Bold's copy sits directly on the brand field rather than on a text
          // background. Keep its derived contrast when that field changes brand.
          if (base === 'bold' && ['headline', 'description'].includes(source.role) && !source.backgroundColor &&
              hex(scene.layers.find(item => item.id === 'bold-field')?.color) === brand.color && hex(source.color) === contrast(brand.color)) layer.color = '@contrast.background';
        }
        return layer;
      });
      const recipe = {width: scene.width, height: scene.height, background: colorToken(scene.background, brand, '@brand.secondary_color'), clean: Boolean(scene.clean), layers};
      const order = Array.isArray(scene.productOrder) ? scene.productOrder : scene.layers.filter(layer => layer.role === 'product').map(layer => layer.id);
      recipe.productOrder = order.map(id => {
        const index = scene.layers.findIndex(layer => layer.type === 'image' && layer.role === 'product' && layer.id === id);
        return index < 0 ? null : mappings.get(sourceKey(scene.layers[index], index)).id;
      }).filter(Boolean);
      const omitted = [...new Set((scene.omitted || []).map(item => item.role).filter(role => textRoles.has(role)))];
      if (omitted.length) recipe.omitted = omitted;
      return recipe;
    }
    return {version: 1, base_template: base, master: encode(master), formats: Object.fromEntries(Object.entries(formats).map(([id, scene]) => [id, encode(scene)]))};
  }

  function instantiate(recipe, {brand = {}, products = [], elements = [], background = null, headline = '', description = '', cta = '', pmax_mode = 'clean'} = {}) {
    if (!recipe || recipe.version !== 1 || !builtIns.has(recipe.base_template) || !recipe.master || !recipe.formats || Array.isArray(recipe.formats)) throw failure();
    brand = brandData(brand);
    products = Array.isArray(products) ? products.filter(Boolean) : [];
    elements = Array.isArray(elements) ? elements.filter(Boolean) : [];
    const copy = {headline: String(headline || ''), description: String(description || ''), cta: String(cta || '')};
    const missing = new Map(), warnings = new Set();
    const declared = {product: new Set(), element: new Set(), background: new Set(), logo: new Set()};
    for (const source of [recipe.master, ...Object.values(recipe.formats)]) {
      sceneBasics(source);
      for (const layer of source.layers) if (layer.type === 'image' && imageRoles.has(layer.role)) declared[layer.role].add(layer.slot);
    }
    const labels = {product: 'zdjęcie produktu', element: 'Element', background: 'tło kompozycji', logo: 'logo w Brand Kit'};
    function bind(source) {
      sceneBasics(source);
      // Reconstruct only the portable contract, even if a caller supplies
      // unknown scene properties. The authenticated API validates the same schema.
      const scene = {width: source.width, height: source.height, template: recipe.base_template, clean: Boolean(source.clean), background: resolveColor(source.background, brand), brand: clone(brand), content: {...copy}, omitted: (source.omitted || []).filter(role => textRoles.has(role)).map(role => ({role, message: 'Treść pominięta w tym formacie.'})), layers: []};
      const used = {product: new Set(), element: new Set(), background: new Set(), logo: new Set()};
      for (const stored of source.layers) {
        const layer = {id: stored.id, type: stored.type, role: stored.role};
        for (const key of ['x', 'y', 'w', 'h', ...numericStyles, ...booleanStyles, ...Object.keys(enums)]) if (stored[key] !== undefined) layer[key] = stored[key];
        for (const key of ['backgroundColor', 'borderColor', 'color']) if (stored[key] !== undefined) layer[key] = stored[key] === '@contrast.background' ? contrast(layer.backgroundColor || brand.color) : resolveColor(stored[key], brand);
        if (stored.type === 'rect' && (stored.role === 'decoration' || stored.role === 'shape') && stored.shape !== undefined) {
          if (!['rectangle', 'square', 'circle', 'ellipse', 'triangle', 'diamond'].includes(stored.shape)) throw failure();
          layer.shape = stored.shape;
        }
        if (layer.type === 'text' && textRoles.has(layer.role)) {
          layer.text = copy[layer.role];
          layer.fontFamily = stored.fontFamily === '@brand.font' ? brand.font_family : systemFonts.has(stored.fontFamily) ? stored.fontFamily : brand.font_family;
          if (stored.fontWeight !== undefined) layer.fontWeight = stored.fontWeight;
        } else if (layer.type === 'image' && imageRoles.has(layer.role) && Number.isInteger(stored.slot) && stored.slot >= 0) {
          const slot = stored.slot, role = layer.role;
          used[role].add(slot);
          const asset = role === 'product' ? products[slot] : role === 'element' ? elements[slot] : role === 'background' ? background : brand.logo_url ? {url: brand.logo_url, id: brand.logo_asset_id} : null;
          layer.src = asset?.url || '';
          layer.asset_id = asset?.id ?? null;
          if (!layer.src) {
            const key = role + ':' + slot;
            layer.missingSlot = key;
            missing.set(key, 'Uzupełnij ' + labels[role] + (role === 'product' || role === 'element' ? ' nr ' + (slot + 1) : '') + '.');
          }
        } else if (!(layer.type === 'rect' && (layer.role === 'decoration' || layer.role === 'shape'))) throw failure();
        scene.layers.push(layer);
      }
      // A template never silently deselects campaign materials. Extra assets use
      // the base layout's geometry; saved slot geometry and stacking are retained.
      const extraProducts = products.some((asset, slot) => !declared.product.has(slot));
      const extraElements = !scene.clean && elements.some((asset, slot) => !declared.element.has(slot));
      if (extraProducts || extraElements) {
        const generated = global.StudioCanvas.makeScene({template: recipe.base_template, width: scene.width, height: scene.height, brand,
          products: products.map((asset, slot) => ({...asset, layer_id: canonicalId('product', slot)})), elements: elements.map((asset, slot) => ({...asset, layer_id: canonicalId('element', slot)})), clean: scene.clean});
        for (const role of ['product', 'element']) {
          if (role === 'element' && scene.clean) continue;
          const assets = role === 'product' ? products : elements;
          assets.forEach((asset, slot) => {
            if (declared[role].has(slot)) return;
            const extra = generated.layers.find(layer => layer.role === role && layer.id === canonicalId(role, slot));
            if (!extra) return;
            const previous = scene.layers.map(layer => layer.role).lastIndexOf(role);
            const firstText = scene.layers.findIndex(layer => layer.type === 'text');
            scene.layers.splice(previous >= 0 ? previous + 1 : firstText >= 0 ? firstText : scene.layers.length, 0, clone(extra));
          });
        }
        warnings.add('Dodano materiały ponad liczbę miejsc w szablonie. Sprawdź ich rozmieszczenie.');
      }
      if (background?.url && !declared.background.size) scene.layers.unshift({id: 'background', type: 'image', role: 'background', x: 0, y: 0, w: 1, h: 1, fit: 'cover', cropX: .5, cropY: .5, opacity: 1, locked: true, src: background.url, asset_id: background.id ?? null});
      const productIds = scene.layers.filter(layer => layer.type === 'image' && layer.role === 'product').map(layer => layer.id);
      scene.productOrder = [...(source.productOrder || []).filter(id => productIds.includes(id)), ...productIds.filter(id => !(source.productOrder || []).includes(id))];
      return scene;
    }
    const master = bind(recipe.master), formats = {};
    const destPmaxClean = pmax_mode !== 'composed';
    for (const [id, source] of Object.entries(recipe.formats)) {
      let bound = bind(source);
      if (typeof id === 'string' && id.startsWith('pmax_') && Boolean(source.clean) !== destPmaxClean) {
        if (destPmaxClean) {
          bound.clean = true;
          bound.omitted = [];
          bound.layers = bound.layers.filter(layer => layer.type === 'image' && ['product', 'background'].includes(layer.role));
        } else if (global.StudioCanvas && typeof global.StudioCanvas.adaptScene === 'function') {
          const composedBase = global.StudioCanvas.adaptScene(master, bound.width, bound.height, {clean: false});
          const cleanProducts = new Map(bound.layers.filter(l => l.role === 'product').map(l => [l.id, l]));
          for (const layer of composedBase.layers) {
            const saved = cleanProducts.get(layer.id);
            if (saved && layer.role === 'product') {
              for (const key of ['x', 'y', 'w', 'h', 'fit', 'cropX', 'cropY', 'opacity']) if (saved[key] !== undefined) layer[key] = saved[key];
            }
          }
          bound = composedBase;
          bound.clean = false;
        } else {
          bound.clean = false;
        }
      }
      formats[id] = bound;
    }
    return {master, formats, missing: [...missing.values()], warnings: [...warnings]};
  }

  global.StudioTemplates = Object.freeze({capture, instantiate});
})(window);
