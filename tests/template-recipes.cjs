'use strict';
// Portable recipes are exercised against the real responsive scene generator.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const context = {console, URL, window: {}};
vm.createContext(context);
for (const file of ['canvas.js', 'template-recipes.js']) vm.runInContext(fs.readFileSync(path.join(root, 'static', file), 'utf8'), context);
const C = context.window.StudioCanvas, T = context.window.StudioTemplates;
const clone = value => JSON.parse(JSON.stringify(value));
const asset = (id, kind = 'product') => ({id, kind, url: '/api/assets/' + id + '/file'});
const oldBrand = {id: 'EXPIRED_BRAND', name: 'EXPIRED_BRAND_NAME', color: '#F60', secondary_color: '#fafafa', text_color: '#172323', font_family: 'EXPIRED_FONT', font_url: '/api/assets/EXPIRED_FONT_FILE/file', logo_asset_id: 'EXPIRED_LOGO', logo_url: '/api/assets/EXPIRED_LOGO/file'};
const products = [asset('EXPIRED_PRODUCT_1'), asset('EXPIRED_PRODUCT_2'), asset('EXPIRED_PRODUCT_3')];
const elements = [asset('EXPIRED_ELEMENT', 'element')];
const master = C.makeScene({template: 'split', width: 1200, height: 900, brand: oldBrand, products, elements, background: asset('EXPIRED_BACKGROUND', 'background'), headline: 'EXPIRED_HEADLINE', description: 'EXPIRED_DESCRIPTION', cta: 'EXPIRED_CTA'});
master.content.hiddenCommercialText = 'EXPIRED_UNEXPECTED_COPY';
master.source = '/api/assets/EXPIRED_SOURCE/file';
const first = master.layers.find(layer => layer.id === 'product');
first.x = .63; first.y = .17; first.w = .19; first.h = .23; first.cropX = .23; first.cropY = .71; first.fit = 'cover'; first.hidden = false;
const second = master.layers.find(layer => layer.asset_id === products[1].id);
second.locked = true; second.opacity = .8;
// Z-order differs from material selection order; portable slot binding must not.
master.layers.splice(master.layers.indexOf(second), 1); master.layers.push(second);
const cta = master.layers.find(layer => layer.role === 'cta');
cta.cornerRadius = .24; cta.borderWidth = 4; cta.borderColor = '#123abc';
master.layers.push({...clone(master.layers.find(layer => layer.role === 'headline')), id: 'EXPIRED_EXTRA_TEXT', text: 'EXPIRED_EXTRA_COPY', x: .04, y: .52, w: .31, h: .08, color: '#AbC123', fontFamily: 'Georgia'});
master.layers.push({id: 'EXPIRED_DECORATION', type: 'rect', role: 'decoration', x: .7, y: .8, w: .1, h: .1, color: '#112233'});
const override = C.adaptScene(master, 300, 250);
override.layers.find(layer => layer.asset_id === products[1].id).cropY = .17;
override.layers.find(layer => layer.role === 'cta').cornerRadius = .07;
const clean = C.adaptScene(master, 1200, 1200, {clean: true});
const narrow = C.makeScene({template: 'split', width: 728, height: 90, brand: oldBrand, products, headline: 'EXPIRED_HEADLINE', description: 'EXPIRED_DESCRIPTION', cta: 'EXPIRED_CTA'});
const original = clone({master, formats: {display_300x250: override, rda_1200x1200: clean, display_728x90: narrow}});
const recipe = T.capture({master, formats: {display_300x250: override, rda_1200x1200: clean, display_728x90: narrow}});
assert.deepEqual(clone({master, formats: {display_300x250: override, rda_1200x1200: clean, display_728x90: narrow}}), original, 'Capture must not modify any live campaign scene.');
assert(!JSON.stringify(recipe).includes('EXPIRED'), 'Source identifiers, URLs, font names and every commercial string are absent.');
assert(!JSON.stringify(recipe).includes('/api/assets/'));
for (const scene of [recipe.master, ...Object.values(recipe.formats)]) {
  assert(!Object.hasOwn(scene, 'brand') && !Object.hasOwn(scene, 'content'));
  for (const layer of scene.layers) assert(!Object.hasOwn(layer, 'src') && !Object.hasOwn(layer, 'asset_id') && !Object.hasOwn(layer, 'text'));
}
assert.equal(recipe.master.background, '@brand.secondary_color');
assert.equal(recipe.master.layers.find(layer => layer.role === 'cta').backgroundColor, '@brand.color');
assert.equal(recipe.master.layers.find(layer => layer.role === 'cta').color, '@contrast.background');
assert.equal(recipe.master.layers.find(layer => layer.id === 'headline-slot-2').fontFamily, 'Georgia');
assert.deepEqual(clone(recipe.master.productOrder), ['product', 'product-slot-2', 'product-slot-3']);
assert.equal(recipe.master.layers.find(layer => layer.id === 'product-slot-2').slot, 1);
assert.equal(recipe.formats.display_300x250.layers.find(layer => layer.id === 'product-slot-2').slot, 1);
assert.deepEqual(clone(recipe.formats.display_728x90.omitted), ['description']);

const newBrand = {id: 'new-brand', color: '#073050', secondary_color: '#E9FFFF', text_color: '#243042', font_family: 'New Brand Font', font_url: '/api/assets/new-font/file', logo_url: '/api/assets/new-logo/file', logo_asset_id: 'new-logo'};
const newProducts = [asset('new-product-1'), asset('new-product-2'), asset('new-product-3')];
const newElements = [asset('new-element', 'element')];
const args = {brand: newBrand, products: newProducts, elements: newElements, background: asset('new-background', 'background'), headline: 'Nowa oferta', description: 'Nowy opis', cta: 'Zobacz ofertę'};
const frozenRecipeCopy = clone(recipe), currentInputCopy = clone(args);
const bound = T.instantiate(recipe, args);
assert.deepEqual(clone(recipe), frozenRecipeCopy, 'Applying a shared template cannot change its saved recipe.');
assert.deepEqual(clone(args), currentInputCopy, 'Applying a template does not change the current Brand Kit or selected assets.');
assert.equal(bound.missing.length, 0);
assert.equal(bound.warnings.length, 0);
assert.equal(bound.master.template, 'split', 'Library identity never replaces the responsive base template ID.');
assert.equal(bound.master.background, newBrand.secondary_color);
assert.equal(bound.master.brand.font_url, newBrand.font_url);
assert.equal(bound.master.layers.find(layer => layer.role === 'logo').src, newBrand.logo_url);
assert.equal(bound.master.layers.find(layer => layer.id === 'product-slot-2').asset_id, 'new-product-2');
assert.equal(bound.master.layers.find(layer => layer.id === 'product').cropX, .23);
assert.equal(bound.master.layers.find(layer => layer.id === 'product').fit, 'cover');
assert.equal(bound.master.layers.at(-2).id, 'headline-slot-2');
assert.equal(bound.master.layers.at(-2).text, args.headline, 'Duplicated text layers bind to current campaign copy too.');
assert.equal(bound.master.layers.at(-2).color, '#ABC123', 'Manually chosen non-brand colors survive.');
assert.equal(bound.master.layers.at(-2).fontFamily, 'Georgia');
assert.equal(bound.master.layers.find(layer => layer.id === 'headline').fontFamily, newBrand.font_family);
assert.equal(bound.master.layers.find(layer => layer.role === 'cta').color, '#FFFFFF', 'CTA contrast adapts when a bright brand changes to a dark brand.');
assert.equal(bound.master.layers.find(layer => layer.role === 'cta').cornerRadius, .24);
assert.equal(bound.master.layers.find(layer => layer.role === 'cta').borderColor, '#123ABC');
assert.equal(bound.formats.display_300x250.layers.find(layer => layer.role === 'cta').cornerRadius, .07);
assert.equal(bound.formats.display_300x250.layers.find(layer => layer.id === 'product-slot-2').cropY, .17);
assert(!bound.formats.rda_1200x1200.layers.some(layer => ['text', 'rect'].includes(layer.type)));
assert(!JSON.stringify(bound).includes('EXPIRED'));

// Source campaign may now be deleted. A JSON round-trip is all a recipe needs.
const detachedRecipe = clone(recipe);
const expired = clone(master);
expired.layers.forEach(layer => { if (layer.type === 'image') { layer.src = ''; layer.asset_id = null; } });
const rebound = T.instantiate(detachedRecipe, args);
assert.deepEqual(clone(rebound), clone(bound));
const afterAdapt = C.adaptScene(bound.master, 160, 600);
assert.equal(afterAdapt.template, 'split');
assert.deepEqual(clone(afterAdapt.productOrder), ['product', 'product-slot-2', 'product-slot-3']);
assert.equal(afterAdapt.layers.find(layer => layer.id === 'product-slot-2').asset_id, 'new-product-2');
assert.equal(afterAdapt.layers.find(layer => layer.role === 'cta').cornerRadius, .24);
assert.equal(afterAdapt.layers.find(layer => layer.id === 'product').cropX, .23);
assert(afterAdapt.layers.some(layer => layer.id === 'element-slot-1' && layer.asset_id === 'new-element'));
const reexpanded = C.adaptScene(bound.formats.display_728x90, 1200, 900);
assert.equal(reexpanded.layers.find(layer => layer.role === 'description').text, args.description, 'Only role metadata survives omitted text and rebinds it from the new campaign.');

const missing = T.instantiate(recipe, {products: [newProducts[0]], headline: 'Nowa oferta'});
assert(missing.missing.some(message => message.includes('produktu nr 2')));
assert(missing.missing.some(message => message.includes('Element nr 1')));
assert(missing.missing.some(message => message.includes('logo w Brand Kit')));
assert(missing.missing.some(message => message.includes('tło kompozycji')));
assert.equal(missing.missing.length, new Set(missing.missing).size, 'Same missing slot across formats yields one actionable message.');
const missingProduct = missing.master.layers.find(layer => layer.id === 'product-slot-2');
assert.equal(missingProduct.src, ''); assert.equal(missingProduct.asset_id, null); assert.equal(missingProduct.missingSlot, 'product:1');
assert.equal(missingProduct.locked, true); assert.equal(missingProduct.opacity, .8);
assert.deepEqual(clone(['x', 'y', 'w', 'h'].map(key => missingProduct[key])), clone(['x', 'y', 'w', 'h'].map(key => second[key])), 'Missing material retains editable slot geometry.');
const adaptedMissing = C.adaptScene(missing.master, 300, 600);
assert.equal(adaptedMissing.layers.find(layer => layer.id === 'product-slot-2').src, '');
assert.equal(adaptedMissing.layers.find(layer => layer.id === 'product-slot-2').missingSlot, 'product:1');
assert.equal(adaptedMissing.layers.find(layer => layer.role === 'logo').missingSlot, 'logo:0', 'Missing logo remains an actionable placeholder after aspect change.');
assert(!JSON.stringify(missing).includes('EXPIRED'));
const noCopy = T.instantiate(recipe, {...args, headline: '', description: '', cta: ''});
assert(noCopy.master.layers.filter(layer => layer.type === 'text').every(layer => layer.text === ''), 'Empty new campaign copy cannot restore old content.');

const extra = T.instantiate(recipe, {...args, products: [...newProducts, asset('new-product-4')], elements: [...newElements, asset('new-element-2', 'element')]});
assert(extra.master.layers.some(layer => layer.asset_id === 'new-product-4'));
assert(extra.master.layers.some(layer => layer.asset_id === 'new-element-2'));
assert(extra.formats.rda_1200x1200.layers.some(layer => layer.asset_id === 'new-product-4'));
assert(!extra.formats.rda_1200x1200.layers.some(layer => layer.role === 'element'));
assert(extra.warnings.length === 1);
assert.equal(extra.master.layers.find(layer => layer.id === 'product').x, .63, 'Extra selected assets do not erase saved manual geometry.');
assert.equal(T.capture({master: extra.master}).master.layers.find(layer => layer.id === 'product-slot-4').slot, 3, 'A used template can be saved again with newly added slots.');
assert(!bound.formats.display_728x90.layers.some(layer => layer.role === 'element'), 'A format-specific intentionally absent slot is not resurrected as an extra.');
const withoutBackground = C.makeScene({products: [products[0]], headline: 'EXPIRED_HEADLINE'});
const addedBackground = T.instantiate(T.capture({master: withoutBackground}), {...args, products: [newProducts[0]], elements: []});
assert.equal(addedBackground.master.layers[0].src, args.background.url);
assert.throws(() => T.instantiate({...recipe, version: 99}, args));
assert.throws(() => T.capture({master: {...master, width: 9000}}));

const darkBold = C.makeScene({...args, template: 'bold', brand: {...newBrand, color: '#001122', secondary_color: '#101010'}});
const boldRecipe = T.capture({master: darkBold});
const lightBold = T.instantiate(boldRecipe, {...args, brand: {...newBrand, color: '#FFFFFF', secondary_color: '#F5F5F5'}}).master;
for (const role of ['headline', 'description', 'cta']) assert.equal(lightBold.layers.find(layer => layer.role === role).color, '#101819', 'Bold ' + role + ' contrast updates across dark/light brands.');
darkBold.layers.find(layer => layer.role === 'headline').color = '#FF22AA';
assert.equal(T.instantiate(T.capture({master: darkBold}), args).master.layers.find(layer => layer.role === 'headline').color, '#FF22AA', 'Manually chosen bold text color is retained.');

// Every installed built-in must round-trip, including its decoration identifiers.
for (const template of C.templates) {
  const scene = C.makeScene({...args, template: template.id});
  const roundtrip = T.instantiate(T.capture({master: scene}), args).master;
  assert.deepEqual(clone(roundtrip.layers.map(layer => layer.id)), clone(scene.layers.map(layer => layer.id).map(id => {
    if (id.startsWith('product-new-product-')) return 'product-slot-' + id.split('-').at(-1);
    if (id === 'element-new-element') return 'element-slot-1';
    return id;
  })), template.id + ': built-in decoration identities survive for responsive adaptation.');
}

if (process.argv[2] === '--fixture') fs.writeFileSync(process.argv[3], JSON.stringify(recipe, null, 2));
console.log('PASS portable template recipes: stripping, slots, brand/text rebinding, overrides, missing assets, responsive adaptation, extras and resave.');
