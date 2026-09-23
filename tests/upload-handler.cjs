'use strict';

// Exercise the application's actual upload handler with a minimal DOM and API.
// No browser, server, credentials, network, or third-party packages are used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'app.js'), 'utf8');
const start = source.indexOf('  function bindMaterials(){');
const end = source.indexOf('  function sceneBase(', start);
assert(start >= 0 && end > start, 'Could not locate the actual bindMaterials function.');

function element(value = '') {
  return {
    value, disabled: false, files: [], innerHTML: '', handlers: {},
    addEventListener(type, handler) { this.handlers[type] = handler; },
  };
}

function freshDOM(kind = 'product') {
  return {
    '#asset-upload': element(),
    '#upload-kind': element(kind),
    '#upload-status': element(),
  };
}

let dom = freshDOM('background');
let rejectBadFile = true;
let activeInput;
let activeKind;
const requests = [];
const renderedAssetIds = [];
const notifications = [];
const context = {
  R: {
    user: { id: 1 }, view: 'campaign', tab: 'materials',
    campaign: {
      id: 'campaign-a', assets: [],
      state: { product_asset_id: null, background_asset_id: null },
    },
  },
  $: selector => dom[selector],
  $$: () => [],
  collectDraft() {},
  marked() {},
  syncSceneMaterial() {},
  refreshStorage: async () => {},
  notify: (...args) => notifications.push(args),
  esc: value => String(value).replace(/[<>]/g, ''),
  icon: () => '',
  FormData: class {
    constructor() { this.data = {}; }
    append(key, value) { this.data[key] = value; }
  },
};

context.api = async (url, { body }) => {
  assert.equal(activeInput.disabled, true, 'File chooser must be disabled while uploading.');
  assert.equal(activeKind.disabled, true, 'Kind chooser must be disabled while uploading.');
  requests.push({ url, kind: body.data.kind, name: body.data.file.name });
  // Even an external value change must not change the captured kind mid-batch.
  activeKind.value = 'product';
  if (body.data.file.name === 'bad.png' && rejectBadFile) {
    throw new Error('Przekroczono limit miejsca.');
  }
  return {
    id: 'asset-' + requests.length,
    kind: body.data.kind,
    name: body.data.file.name,
    url: '/api/assets/example/file',
  };
};

context.renderCampaign = () => {
  renderedAssetIds.push(context.R.campaign.assets.map(asset => asset.id));
  // A real rerender discards the old status element and chooser values.
  dom = freshDOM();
  context.bindMaterials();
};

vm.createContext(context);
vm.runInContext(source.slice(start, end), context, { filename: 'app.js:bindMaterials' });
context.bindMaterials();

async function selectFiles(names, expectedKind = 'background') {
  activeInput = dom['#asset-upload'];
  activeKind = dom['#upload-kind'];
  activeInput.files = names.map(name => ({ name }));
  activeInput.value = '/fake/' + names[0];
  const previousInput = activeInput;
  const previousKind = activeKind;
  await previousInput.handlers.change({ target: previousInput });
  assert.equal(previousInput.value, '', 'Old input must be cleared for same-file retry.');
  assert.equal(previousInput.disabled, false, 'Old input must leave its pending state.');
  assert.equal(previousKind.disabled, false, 'Kind chooser must leave its pending state.');
  assert.equal(dom['#asset-upload'].value, '', 'Newly rendered input must also be empty.');
  assert.equal(dom['#asset-upload'].disabled, false, 'New chooser must accept retry.');
  assert.equal(dom['#upload-kind'].value, expectedKind, 'Selected kind must survive rerender.');
}

async function main() {
  await selectFiles(['good.png', 'bad.png', 'pending.png']);
  assert.equal(requests.length, 2, 'Stop the batch at its first failed file.');
  assert(requests.every(request => request.kind === 'background'));
  assert(requests.every(request => request.url === '/api/campaigns/campaign-a/assets'));
  assert.equal(context.R.campaign.assets.length, 1);
  assert.equal(context.R.campaign.state.background_asset_id, 'asset-1');
  assert.equal(renderedAssetIds[0].join(','), 'asset-1', 'Successful upload card must render.');
  const partialStatus = dom['#upload-status'].innerHTML;
  assert(partialStatus.includes('Dodano 1 z 3'));
  assert(partialStatus.includes('bad.png'), 'Failure must identify the rejected file.');
  assert(partialStatus.includes('Przekroczono limit miejsca.'), 'Backend reason must remain visible.');
  assert(partialStatus.includes('niewysłane pliki: 1'), 'Unattempted files must be counted.');
  assert(partialStatus.includes('role="alert"'));

  rejectBadFile = false;
  await selectFiles(['bad.png']);
  assert.equal(context.R.campaign.assets.length, 2, 'Retry must preserve the previous upload.');
  assert.equal(requests[2].name, 'bad.png', 'The same filename must be accepted on retry.');
  assert.equal(requests[2].kind, 'background');
  assert.equal(renderedAssetIds[1].length, 2);
  assert(dom['#upload-status'].innerHTML.includes('Dodano 1 z 1'));
  assert(!dom['#upload-status'].innerHTML.includes('note error'), 'Successful retry clears stale error.');

  rejectBadFile = true;
  await selectFiles(['bad.png']);
  assert.equal(context.R.campaign.assets.length, 2, 'Failed first file must not remove older uploads.');
  assert.equal(renderedAssetIds[2].length, 2);
  assert(dom['#upload-status'].innerHTML.includes('bad.png'));
  assert(!dom['#upload-status'].innerHTML.includes('note success'), 'Zero successes must not show success.');
  assert.equal(notifications.length, 3);
  assert.equal(notifications[0][1], true, 'Partial failure must also produce an error notification.');
  rejectBadFile = false;
  dom['#upload-kind'].value = 'product';
  dom['#upload-kind'].handlers.change();
  await selectFiles(['product-a.png', 'product-b.png', 'product-c.png'], 'product');
  assert.equal(context.R.campaign.state.product_asset_ids.length, 3, 'All three products should be active together.');
  assert.equal(context.R.campaign.state.product_asset_id, context.R.campaign.state.product_asset_ids[0], 'Legacy first product remains valid.');
  const productIds = context.R.campaign.state.product_asset_ids.join(',');
  dom['#upload-kind'].value = 'element';
  dom['#upload-kind'].handlers.change();
  await selectFiles(['label.png', 'badge.png'], 'element');
  assert.equal(context.R.campaign.state.element_asset_ids.length, 2, 'Elements are independently selected.');
  assert.equal(context.R.campaign.state.product_asset_ids.join(','), productIds, 'Elements must preserve selected products.');
  assert.equal(context.R.campaign.state.background_asset_id, 'asset-1', 'Multiple materials must preserve the background.');
  console.log('PASS: partial upload/retry, captured kind, pending states and automatic multi-product/element selection.');
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
