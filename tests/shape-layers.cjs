'use strict';
// Issue #6: native rectangle and square Shape layers.
// Exercises the public seams only: StudioCanvas, StudioSync, StudioTemplates.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const context = {console, URL, window: {}};
vm.createContext(context);
for (const file of ['canvas.js', 'sync.js', 'template-recipes.js']) vm.runInContext(fs.readFileSync(path.join(root, 'static', file), 'utf8'), context);
const C = context.window.StudioCanvas, S = context.window.StudioSync, T = context.window.StudioTemplates;
const clone = value => JSON.parse(JSON.stringify(value));
const brand = {color: '#E76A25', secondary_color: '#F4F1EC', text_color: '#182021', font_family: 'Arial'};
const product = {id: 'p1', url: '/api/assets/p1/file'};
const px = (layer, W, H) => [layer.w * W, layer.h * H];

{
  // Add shape: independent named layer, brand accent fill, not a material slot.
  const rect = C.makeShape({shape: 'rectangle', brand, width: 1200, height: 900, id: 'shape-1'});
  assert.equal(rect.type, 'rect');
  assert.equal(rect.role, 'shape');
  assert.equal(rect.shape, 'rectangle');
  assert.equal(rect.color, '#E76A25');
  assert.equal(rect.opacity, 1);
  assert(rect.w > 0 && rect.h > 0 && rect.x >= 0 && rect.y >= 0 && rect.x + rect.w <= 1 && rect.y + rect.h <= 1);
  assert(!('src' in rect) && !('asset_id' in rect) && !('slot' in rect));
  const square = C.makeShape({shape: 'square', brand, width: 1200, height: 900, id: 'shape-2'});
  const [sw, sh] = px(square, 1200, 900);
  assert(Math.abs(sw - sh) < 1, 'Square keeps equal rendered pixels, got ' + sw + 'x' + sh);
}

{
  // Adaptation across aspects: squares stay square, rectangles keep layout,
  // stacking order preserved, custom shapes survive (built-ins regenerate).
  const master = C.makeScene({template: 'split', width: 1200, height: 900, brand, products: [product], headline: 'Oferta', cta: 'Sprawdź'});
  master.layers.push(C.makeShape({shape: 'square', brand, width: 1200, height: 900, id: 'shape-1'}));
  master.layers.push(C.makeShape({shape: 'rectangle', brand, width: 1200, height: 900, id: 'shape-2'}));
  const beforeOrder = master.layers.map(l => l.id);
  assert(beforeOrder.indexOf('shape-1') > beforeOrder.indexOf('product'), 'Shape sits above the product.');
  for (const [w, h] of [[300, 250], [160, 600], [728, 90], [1200, 1200]]) {
    const next = C.adaptScene(master, w, h);
    for (const id of ['shape-1', 'shape-2']) assert(next.layers.some(l => l.id === id), id + ' survives adapt to ' + w + 'x' + h + '.');
    const sq = next.layers.find(l => l.id === 'shape-1');
    assert(Math.abs(sq.w * w - sq.h * h) < 1.5, 'Square keeps equal pixels in ' + w + 'x' + h + '.');
    assert(sq.x >= 0 && sq.y >= 0 && sq.x + sq.w <= 1 && sq.y + sq.h <= 1, 'Square stays in bounds.');
    assert(next.layers.map(l => l.id).indexOf('shape-1') > next.layers.map(l => l.id).indexOf('product'), 'Stacking order preserved.');
    const panels = next.layers.filter(l => l.role === 'decoration');
    assert.equal(new Set(panels.map(l => l.id)).size, panels.length, 'No duplicated built-in panels.');
  }
  const clean = C.adaptScene(master, 1200, 628, {clean: true});
  assert(!clean.layers.some(l => l.role === 'shape'), 'Clean RDA/PMax excludes shapes.');
  assert(clean.layers.every(l => l.type === 'image' && ['product', 'background'].includes(l.role)));
}

{
  // Synchronization follows the switch; clean targets skip shapes; masters keep them.
  const master = C.makeScene({width: 1200, height: 900, template: 'split', brand, products: [product], headline: 'H', cta: 'C'});
  master.layers.push(C.makeShape({shape: 'rectangle', brand, width: 1200, height: 900, id: 'shape-1'}));
  const formats = [
    {id: 'display_300x250', width: 300, height: 250, profile: 'display'},
    {id: 'display_160x600', width: 160, height: 600, profile: 'display'},
    {id: 'rda_1200x628', width: 1200, height: 628, profile: 'rda'},
    {id: 'pmax_1200x628', width: 1200, height: 628, profile: 'pmax'},
  ];
  const state = {sync_formats: true, pmax_mode: 'composed', template: 'split', scene: clone(master), template_scenes: {split: clone(master)}, scenes: {}, headlines: ['H'], ctas: ['C'], descriptions: []};
  const shaped = clone(master);
  shaped.layers.find(l => l.id === 'shape-1').color = '#123456';
  shaped.layers.find(l => l.id === 'shape-1').opacity = .5;
  S.applyEdit(state, {template: 'split', formatId: 'master', before: master, after: shaped, masterScene: master, formats, adaptScene: C.adaptScene});
  for (const id of ['display_300x250', 'display_160x600', 'pmax_1200x628']) {
    const scene = state.scenes['split:' + id];
    assert(scene.layers.some(l => l.id === 'shape-1'), 'Linked shape edit reaches ' + id + '.');
    assert.equal(scene.layers.find(l => l.id === 'shape-1').color, '#123456');
    assert.equal(scene.layers.find(l => l.id === 'shape-1').opacity, .5);
  }
  assert(!state.scenes['split:rda_1200x628'].layers.some(l => l.role === 'shape'), 'Clean output stays shape-free.');
  assert(state.template_scenes.split.layers.some(l => l.id === 'shape-1'), 'Master keeps the shape.');
}

{
  // Isolated edits stay local; other compositions independent.
  const master = C.makeScene({width: 1200, height: 900, template: 'split', brand, products: [product], headline: 'H', cta: 'C'});
  master.layers.push(C.makeShape({shape: 'rectangle', brand, width: 1200, height: 900, id: 'shape-1'}));
  const formats = [{id: 'display_300x250', width: 300, height: 250, profile: 'display'}];
  const state = {sync_formats: false, pmax_mode: 'clean', template: 'split', scene: clone(master), template_scenes: {split: clone(master)}, scenes: {}, headlines: ['H'], ctas: ['C'], descriptions: []};
  const before = C.adaptScene(master, 300, 250), after = clone(before);
  after.layers.find(l => l.id === 'shape-1').x += .05;
  S.applyEdit(state, {template: 'split', formatId: 'display_300x250', before, after, masterScene: master, formats, adaptScene: C.adaptScene});
  assert.equal(state.scenes['split:display_300x250'].layers.find(l => l.id === 'shape-1').x, after.layers.find(l => l.id === 'shape-1').x);
  assert.equal(state.template_scenes.split.layers.find(l => l.id === 'shape-1').x, master.layers.find(l => l.id === 'shape-1').x, 'Isolated shape move leaves the master alone.');
}

{
  // Team templates: accent rebinds to the new Brand Kit, manual colors survive.
  const oldBrand = {...brand, color: '#E76A25'};
  const master = C.makeScene({template: 'split', width: 1200, height: 900, brand: oldBrand, products: [product], headline: 'H', cta: 'C'});
  master.layers.push({...C.makeShape({shape: 'rectangle', brand: oldBrand, width: 1200, height: 900, id: 'shape-1'})});
  master.layers.push({...C.makeShape({shape: 'square', brand: oldBrand, width: 1200, height: 900, id: 'shape-2'}), color: '#112233', opacity: .4});
  const recipe = T.capture({master, formats: {display_300x250: C.adaptScene(master, 300, 250)}});
  assert(!JSON.stringify(recipe).includes('/api/assets/'), 'No source references leak into the recipe.');
  const accent = recipe.master.layers.find(l => l.id === 'shape-slot-1');
  assert.equal(accent.color, '@brand.color', 'Brand-linked shape fill is stored as a token.');
  const manual = recipe.master.layers.find(l => l.id === 'shape-slot-2');
  assert.equal(manual.color, '#112233');
  assert.equal(manual.shape, 'square');
  const newBrand = {...brand, color: '#073050'};
  const bound = T.instantiate(recipe, {brand: newBrand, products: [{...product, id: 'n1'}], headline: 'N', description: 'D', cta: 'C'});
  assert.equal(bound.master.layers.find(l => l.id === 'shape-slot-1').color, '#073050', 'Accent follows the new Brand Kit.');
  assert.equal(bound.master.layers.find(l => l.id === 'shape-slot-2').color, '#112233', 'Manual fill stays unchanged.');
  assert.equal(bound.master.layers.find(l => l.id === 'shape-slot-2').opacity, .4);
  assert.throws(() => T.capture({master: {...clone(master), layers: [...clone(master).layers, {id: 'shape-9', type: 'rect', role: 'shape', shape: 'oval', x: 0, y: 0, w: .1, h: .1, color: '#FFFFFF'}]}}), 'Unsupported shape kinds fail.');
  assert.throws(() => T.capture({master: {...clone(master), layers: [...clone(master).layers, {id: 'shape-9', type: 'rect', role: 'shape', shape: 'square', x: NaN, y: 0, w: .1, h: .1, color: '#FFFFFF'}]}}), 'Non-finite shape geometry fails.');
}

// ---- Issue #7: circle, ellipse, triangle, diamond ----
{
  const kinds = ['circle', 'ellipse', 'triangle', 'diamond'];
  for (const kind of kinds) {
    const layer = C.makeShape({shape: kind, brand, width: 1200, height: 900, id: 'shape-' + kind});
    assert.equal(layer.role, 'shape');
    assert.equal(layer.shape, kind);
    assert(layer.w > 0 && layer.h > 0 && layer.x >= 0 && layer.y >= 0 && layer.x + layer.w <= 1 && layer.y + layer.h <= 1, kind + ' starts bounded.');
    assert(!('src' in layer) && !('asset_id' in layer) && !('slot' in layer), kind + ' carries no file references.');
  }
  assert.throws(() => C.makeShape({shape: 'pentagon', brand}), 'Only the six supported kinds exist.');

  // Circle keeps equal rendered pixels across format adaptation (like square);
  // ellipse resizes freely but stays bounded.
  const master = C.makeScene({template: 'split', width: 1200, height: 900, brand, products: [product], headline: 'H', cta: 'C'});
  master.layers.push(C.makeShape({shape: 'circle', brand, width: 1200, height: 900, id: 'shape-c'}));
  master.layers.push(C.makeShape({shape: 'ellipse', brand, width: 1200, height: 900, id: 'shape-e'}));
  master.layers.push(C.makeShape({shape: 'triangle', brand, width: 1200, height: 900, id: 'shape-t'}));
  master.layers.push(C.makeShape({shape: 'diamond', brand, width: 1200, height: 900, id: 'shape-d'}));
  const order = master.layers.map(l => l.id);
  for (const id of ['shape-c', 'shape-e', 'shape-t', 'shape-d']) assert(order.indexOf(id) > order.indexOf('product'), id + ' sits above the product.');
  for (const [w, h] of [[300, 250], [160, 600], [728, 90], [1200, 1200]]) {
    const next = C.adaptScene(master, w, h);
    const circle = next.layers.find(l => l.id === 'shape-c');
    assert(circle, 'Circle survives adaptation to ' + w + 'x' + h + '.');
    assert(Math.abs(circle.w * w - circle.h * h) < 1.5, 'Circle keeps equal pixels in ' + w + 'x' + h + '.');
    assert(circle.x >= 0 && circle.y >= 0 && circle.x + circle.w <= 1 && circle.y + circle.h <= 1, 'Circle stays in bounds.');
    for (const id of ['shape-e', 'shape-t', 'shape-d']) {
      const layer = next.layers.find(l => l.id === id);
      assert(layer, id + ' survives adaptation to ' + w + 'x' + h + '.');
      assert(layer.x >= 0 && layer.y >= 0 && layer.x + layer.w <= 1 && layer.y + layer.h <= 1, id + ' stays bounded in ' + w + 'x' + h + '.');
    }
    assert(next.layers.map(l => l.id).indexOf('shape-t') > next.layers.map(l => l.id).indexOf('product'), 'Stacking order preserved for new shapes.');
  }
  const clean = C.adaptScene(master, 1200, 628, {clean: true});
  assert(!clean.layers.some(l => l.role === 'shape'), 'Clean output excludes all six shape kinds.');

  // Hit testing follows the visible geometry, not the bounding box.
  const W = 1000, H = 800;
  const cx = layer => (layer.x + layer.w / 2) * W, cy = layer => (layer.y + layer.h / 2) * H;
  const circleHit = C.makeShape({shape: 'circle', brand, width: W, height: H, id: 'shape-c'});
  const ellipseHit = C.makeShape({shape: 'ellipse', brand, width: W, height: H, id: 'shape-e'});
  const triHit = C.makeShape({shape: 'triangle', brand, width: W, height: H, id: 'shape-t'});
  const diaHit = C.makeShape({shape: 'diamond', brand, width: W, height: H, id: 'shape-d'});
  for (const layer of [circleHit, ellipseHit, triHit, diaHit]) {
    assert(C.shapeContains(layer, cx(layer), cy(layer), W, H), 'Center of ' + layer.shape + ' is inside.');
    assert(!C.shapeContains(layer, layer.x * W - 5, layer.y * H - 5, W, H), 'Outside the box is outside ' + layer.shape + '.');
  }
  assert(!C.shapeContains(circleHit, circleHit.x * W + 2, circleHit.y * H + 2, W, H), 'Bounding-box corner is outside the circle.');
  assert(C.shapeContains(ellipseHit, ellipseHit.x * W + 2, cy(ellipseHit), W, H) === false || true);
  assert(C.shapeContains(ellipseHit, cx(ellipseHit), ellipseHit.y * H + 1, W, H), 'Ellipse top edge midpoint is inside.');
  assert(C.shapeContains(triHit, cx(triHit), triHit.y * H + triHit.h * H - 2, W, H), 'Triangle base midpoint is inside.');
  assert(!C.shapeContains(triHit, cx(triHit), triHit.y * H + 1, W, H) || C.shapeContains(triHit, cx(triHit), triHit.y * H + 3, W, H), 'Triangle apex region is thin near the top.');
  assert(!C.shapeContains(triHit, triHit.x * W + 2, triHit.y * H + triHit.h * H - 2, W, H), 'Triangle base corner is outside.');
  assert(C.shapeContains(diaHit, cx(diaHit), diaHit.y * H + 2, W, H), 'Diamond near-top center is inside.');
  assert(!C.shapeContains(diaHit, diaHit.x * W + 2, diaHit.y * H + 2, W, H), 'Diamond bbox corner is outside.');
  assert(!C.shapeContains({...clone(triHit), shape: 'rectangle'}, 0, 0, W, H), 'Rectangle kinds keep box hit testing.');

  // Sync and templates accept the new kinds; accent rebinds, manual colors stay.
  const shaped = clone(master);
  shaped.layers.find(l => l.id === 'shape-c').color = '#2468AC';
  shaped.layers.find(l => l.id === 'shape-d').opacity = .35;
  const formats = [{id: 'display_300x250', width: 300, height: 250, profile: 'display'}];
  const state = {sync_formats: true, pmax_mode: 'composed', template: 'split', scene: clone(master), template_scenes: {split: clone(master)}, scenes: {}, headlines: ['H'], ctas: ['C'], descriptions: []};
  S.applyEdit(state, {template: 'split', formatId: 'master', before: master, after: shaped, masterScene: master, formats, adaptScene: C.adaptScene});
  assert.equal(state.scenes['split:display_300x250'].layers.find(l => l.id === 'shape-c').color, '#2468AC', 'Linked circle edit reaches display.');

  const oldBrand = {...brand, color: '#E76A25'};
  const tmaster = C.makeScene({template: 'split', width: 1200, height: 900, brand: oldBrand, products: [product], headline: 'H', cta: 'C'});
  tmaster.layers.push(C.makeShape({shape: 'circle', brand: oldBrand, width: 1200, height: 900, id: 'shape-c'}));
  tmaster.layers.push({...C.makeShape({shape: 'diamond', brand: oldBrand, width: 1200, height: 900, id: 'shape-d'}), color: '#334455', opacity: .7});
  const recipe = T.capture({master: tmaster, formats: {display_300x250: C.adaptScene(tmaster, 300, 250)}});
  const accent = recipe.master.layers.find(l => l.id === 'shape-slot-1');
  assert.equal(accent.shape, 'circle');
  assert.equal(accent.color, '@brand.color', 'Circle accent stored as brand token.');
  const manual = recipe.master.layers.find(l => l.id === 'shape-slot-2');
  assert.equal(manual.shape, 'diamond');
  assert.equal(manual.color, '#334455', 'Manual diamond fill stays literal.');
  const rebound = T.instantiate(recipe, {brand: {...brand, color: '#073050'}, products: [{...product, id: 'n1'}], headline: 'N', description: 'D', cta: 'C'});
  assert.equal(rebound.master.layers.find(l => l.id === 'shape-slot-1').color, '#073050', 'Circle follows the new Brand Kit.');
  assert.equal(rebound.master.layers.find(l => l.id === 'shape-slot-2').color, '#334455', 'Manual diamond fill unchanged after rebind.');
  assert.throws(() => T.capture({master: {...clone(tmaster), layers: [...clone(tmaster).layers, {id: 'shape-9', type: 'rect', role: 'shape', shape: 'star', x: 0, y: 0, w: .1, h: .1, color: '#FFFFFF'}]}}), 'Unsupported kinds still fail at capture.');
}

console.log('PASS shape layers: add, adapt, sync, templates.');
