"""Reusable recipes never depend on a source campaign or retain its content."""
import copy
import json

import pytest

from test_api import PASSWORD, login, studio, upload
from app import FORMAT_BY_ID
from storage import ApiError, Storage, now_iso
from template_library import MAX_RECIPE_BYTES, encode_recipe


def recipe():
    scene = {
        'width': 1200, 'height': 1200, 'background': '@brand.secondary_color', 'clean': False,
        'layers': [
            {'id': 'product-panel', 'type': 'rect', 'role': 'decoration', 'x': .5, 'y': .1,
             'w': .45, 'h': .8, 'color': '#FFFFFF', 'radius': .025},
            {'id': 'product', 'type': 'image', 'role': 'product', 'slot': 0, 'x': .55, 'y': .2,
             'w': .4, 'h': .6, 'fit': 'contain', 'opacity': 1, 'cropX': .5, 'cropY': .5},
            {'id': 'element-slot-1', 'type': 'image', 'role': 'element', 'slot': 0, 'x': .8, 'y': .1,
             'w': .1, 'h': .1, 'hidden': False, 'locked': False},
            {'id': 'logo', 'type': 'image', 'role': 'logo', 'slot': 0, 'x': .05, 'y': .05,
             'w': .3, 'h': .1},
            {'id': 'headline', 'type': 'text', 'role': 'headline', 'x': .05, 'y': .25,
             'w': .4, 'h': .4, 'fontSize': 72, 'baseFontSize': 72, 'fontWeight': 700,
             'fontFamily': '@brand.font', 'color': '@brand.text_color', 'align': 'left'},
            {'id': 'cta', 'type': 'text', 'role': 'cta', 'x': .05, 'y': .85,
             'w': .4, 'h': .1, 'fontSize': 32, 'fontFamily': 'Georgia',
             'backgroundColor': '@brand.color', 'color': '@contrast.background',
             'borderColor': '#222222', 'borderWidth': 2, 'cornerRadius': .3,
             'verticalAlign': 'middle', 'align': 'center'},
        ],
        'productOrder': ['product'], 'omitted': ['description'],
    }
    small = copy.deepcopy(scene)
    small.update(width=300, height=250)
    return {'version': 1, 'base_template': 'split', 'master': scene, 'formats': {'display_300x250': small}}


def save(client, headers, value=None, name='Układ produktów'):
    return client.post('/api/templates', json={'name': name, 'recipe': recipe() if value is None else value}, headers=headers)


def test_shared_recipes_are_immutable_and_available_to_other_editors(studio):
    app, store, admin, ah, brand, campaign = studio
    first, fh = login(app, 'editor')
    second_user = admin.post('/api/users', json={'username': 'second-editor', 'password': PASSWORD, 'role': 'editor'}, headers=ah)
    assert second_user.status_code == 201
    second, sh = login(app, 'second-editor')
    created = save(first, fh)
    assert created.status_code == 201, created.json
    entry = created.json
    assert entry['recipe'] == recipe()
    assert entry['name'] == 'Układ produktów' and entry['author_name'] == 'editor'
    assert entry['can_manage'] and not entry['archived']
    shared = second.get('/api/templates').json['items']
    assert len(shared) == 1 and shared[0]['recipe'] == recipe() and not shared[0]['can_manage']
    assert 'password_hash' not in json.dumps(shared)
    # Applying a shared recipe creates ordinary independent campaign state.
    new_campaign = second.post('/api/campaigns', json={'name': 'Inna kampania', 'brand_id': brand['id'],
        'state': {'saved_template': {'id': entry['id'], 'recipe': shared[0]['recipe']}}}, headers=sh)
    assert new_campaign.status_code == 201
    assert second.patch(f"/api/templates/{entry['id']}", json={'recipe': recipe()}, headers=sh).status_code == 400
    assert first.put(f"/api/templates/{entry['id']}", json={'recipe': recipe()}, headers=fh).status_code == 405
    second_copy = save(first, fh)
    assert second_copy.status_code == 201 and second_copy.json['id'] != entry['id']


def test_only_author_or_admin_can_archive_and_restore(studio):
    app, store, admin, ah, brand, campaign = studio
    editor, eh = login(app, 'editor')
    entry = save(admin, ah).json
    endpoint = f"/api/templates/{entry['id']}"
    assert editor.patch(endpoint, json={'archived': True}, headers=eh).status_code == 403
    assert admin.patch(endpoint, json={'archived': True}, headers=ah).json['archived'] is True
    assert editor.get('/api/templates').json['items'] == []
    archived = editor.get('/api/templates?include_archived=1').json['items']
    assert len(archived) == 1 and archived[0]['archived'] and not archived[0]['can_manage']
    assert admin.patch(endpoint, json={'archived': False}, headers=ah).json['archived'] is False
    own = save(editor, eh).json
    own_endpoint = f"/api/templates/{own['id']}"
    assert editor.patch(own_endpoint, json={'archived': True}, headers=eh).status_code == 200
    assert admin.patch(own_endpoint, json={'archived': False}, headers=ah).status_code == 200
    assert editor.delete(own_endpoint, headers=eh).status_code == 405
    assert editor.get('/api/templates').json['items'][0]['recipe'] == recipe()
    assert admin.patch('/api/templates/missing', json={'archived': True}, headers=ah).status_code == 404


def test_authentication_csrf_and_disabled_users(studio):
    app, store, client, headers, brand, campaign = studio
    anon = app.test_client()
    assert anon.get('/api/templates').status_code == 401
    anonymous_headers = {'X-CSRF-Token': anon.get('/api/session').json['csrf_token']}
    assert save(anon, anonymous_headers).status_code == 401
    assert save(client, {}).status_code == 403
    entry = save(client, headers).json
    assert client.patch(f"/api/templates/{entry['id']}", json={'archived': True}).status_code == 403
    editor, eh = login(app, 'editor')
    with store.db() as db:
        db.execute("UPDATE users SET active=0 WHERE username='editor'")
    assert editor.get('/api/templates').status_code == 401
    assert save(editor, eh).status_code == 403  # Session revocation also clears its CSRF token.


def test_recipe_survives_source_expiry_deletion_and_storage_reinitialization(studio):
    app, store, client, headers, brand, campaign = studio
    uploaded = upload(client, headers, campaign).json
    entry = save(client, headers).json
    with store.db() as db:
        path = db.execute('SELECT path FROM assets WHERE id=?', (uploaded['id'],)).fetchone()[0]
        db.execute("UPDATE campaigns SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (campaign['id'],))
    store.cleanup(force=True)
    assert not store.path(path).exists()
    assert client.get('/api/templates').json['items'][0]['recipe'] == recipe()
    assert client.delete(f"/api/campaigns/{campaign['id']}", headers=headers).status_code == 200
    Storage(store.root, store.quota_bytes, store.reserve_bytes, recover=False)
    restored = client.get('/api/templates').json['items'][0]
    assert restored['id'] == entry['id'] and restored['recipe'] == recipe()
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM campaigns').fetchone()[0] == 0
        persisted = db.execute('SELECT recipe FROM shared_templates').fetchone()[0]
    assert uploaded['id'] not in persisted and campaign['id'] not in persisted and brand['id'] not in persisted


def test_library_total_cap_includes_archived_and_metadata_consumes_quota(studio):
    app, store, client, headers, brand, campaign = studio
    original_quota = store.quota_bytes
    store.quota_bytes = 1
    assert save(client, headers).status_code == 507
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM shared_templates').fetchone()[0] == 0
    store.quota_bytes = original_quota
    with store.db() as db:
        author = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
        db.executemany('INSERT INTO shared_templates(id,name,recipe,created_by,created_at,archived) VALUES(?,?,?,?,?,1)',
            [(f'{i:024x}', 'Zarchiwizowany', encode_recipe(recipe(), FORMAT_BY_ID), author, now_iso()) for i in range(100)])
    response = save(client, headers)
    assert response.status_code == 409 and response.json['code'] == 'template_library_full'
    assert '100' in response.json['error']
    assert client.get('/api/templates').json['items'] == []
    assert len(client.get('/api/templates?include_archived=1').json['items']) == 100


def test_malformed_api_payloads_fail_without_creating_metadata(studio):
    app, store, client, headers, brand, campaign = studio
    for data in (None, [], {'name': 'x'}, {'name': [], 'recipe': recipe()}, {'name': ' ', 'recipe': recipe()},
                 {'name': 'x\x00', 'recipe': recipe()}, {'name': 'x\ny', 'recipe': recipe()},
                 {'name': 'x\ud800', 'recipe': recipe()},
                 {'name': 'x', 'recipe': recipe(), 'campaign_id': campaign['id']}, {'name': 'x', 'recipe': []}):
        response = client.post('/api/templates', json=data, headers=headers)
        assert response.status_code in (400, 415), response.json
    entry = save(client, headers).json
    for data in ({'archived': 1}, {'archived': 'true'}, {}, {'archived': False, 'recipe': recipe()}):
        assert client.patch(f"/api/templates/{entry['id']}", json=data, headers=headers).status_code == 400
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM shared_templates').fetchone()[0] == 1


@pytest.mark.parametrize('path,value', [
    (('src',), '/api/assets/aaaaaaaaaaaaaaaaaaaaaaaa/file'),
    (('master', 'brand'), {'color': '#112233'}),
    (('master', 'content'), {'headline': 'OLD SALE 99 PLN'}),
    (('master', 'layers', 1, 'src'), '/api/assets/aaaaaaaaaaaaaaaaaaaaaaaa/file'),
    (('master', 'layers', 1, 'asset_id'), 'aaaaaaaaaaaaaaaaaaaaaaaa'),
    (('master', 'layers', 1, 'url'), 'https://example.com/image.jpg'),
    (('master', 'layers', 4, 'text'), 'OLD SALE 99 PLN'),
    (('master', 'layers', 4, 'font_url'), '/api/assets/aaaaaaaaaaaaaaaaaaaaaaaa/file'),
    (('master', 'layers', 4, 'fontFamily'), 'BrandFont-aaaaaaaaaaaaaaaaaaaaaaaa'),
    (('master', 'layers', 4, 'fontFamily'), '\ud800'),
    (('master', 'layers', 0, 'color'), 'url(https://example.com)'),
    (('master', 'layers', 4, 'color'), {'x': '#FFFFFF'}),
    (('master', 'layers', 4, 'fontSize'), []),
    (('master', 'layers', 4, 'fontSize'), True),
    (('master', 'layers', 4, 'fontSize'), float('nan')),
    (('master', 'layers', 1, 'x'), float('inf')),
    (('master', 'layers', 1, 'w'), -1),
    (('master', 'layers', 1, 'x'), 10 ** 1000),
    (('master', 'layers', 1, 'fit'), 'stretch'),
    (('master', 'layers', 1, 'slot'), 1),
    (('master', 'layers', 1, 'slot'), True),
    (('master', 'layers', 1, 'id'), 'product-aaaaaaaaaaaaaaaaaaaaaaaa'),
    (('master', 'layers', 0, 'id'), 'old-campaign-sale-99PLN'),
    (('master', 'layers', 4, 'role'), 'sale'),
    (('master', 'layers', 4, 'backgroundColor'), '@contrast.background'),
    (('master', 'layers', 4, 'hidden'), 1),
    (('master', 'layers', 4, 'type'), 'html'),
    (('master', 'background'), '@contrast.background'),
    (('master', 'width'), 0),
    (('master', 'width'), True),
    (('master', 'height'), 100000),
    (('master', 'productOrder'), ['product', 'product']),
    (('master', 'productOrder'), ['logo']),
    (('master', 'omitted'), [{'role': 'description', 'message': 'OLD SALE'}]),
    (('master', 'omitted'), ['description', 'description']),
    (('version',), True),
    (('version',), 2),
    (('base_template',), 'unknown'),
    (('formats', 'display_300x250', 'width'), 1200),
])
def test_recipe_allowlist_rejects_old_content_and_malformed_nested_fields(path, value):
    data = recipe()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ApiError):
        encode_recipe(data, FORMAT_BY_ID)


def test_recipe_bounds_unique_layers_format_ids_and_all_builtin_schemas():
    for schema in ('split', 'spotlight', 'minimal', 'catalog', 'benefits', 'label', 'backdrop', 'bundle', 'bold'):
        data = recipe()
        data['base_template'] = schema
        assert json.loads(encode_recipe(data, FORMAT_BY_ID)) == data
    data = recipe()
    data['master']['layers'].append(copy.deepcopy(data['master']['layers'][0]))
    with pytest.raises(ApiError):
        encode_recipe(data, FORMAT_BY_ID)
    data = recipe()
    data['master']['layers'] *= 20
    with pytest.raises(ApiError):
        encode_recipe(data, FORMAT_BY_ID)
    data = recipe()
    data['formats'] = {f'unknown-{i}': data['master'] for i in range(21)}
    with pytest.raises(ApiError):
        encode_recipe(data, FORMAT_BY_ID)
    data = recipe()
    data['formats'] = {'display_123x456': data['master']}
    with pytest.raises(ApiError):
        encode_recipe(data, FORMAT_BY_ID)
    data = recipe()
    data['master']['width'], data['master']['height'] = 8192, 8192
    with pytest.raises(ApiError):
        encode_recipe(data, FORMAT_BY_ID)


def test_oversized_and_recursive_recipe_have_bounded_rejections(studio):
    app, store, client, headers, brand, campaign = studio
    data = recipe()
    data['master']['layers'][0]['color'] = 'X' * MAX_RECIPE_BYTES
    response = save(client, headers, data)
    assert response.status_code == 413 and response.json['code'] == 'template_recipe_too_large'
    nested = '{"name":"x","recipe":' + '[' * 2000 + '0' + ']' * 2000 + '}'
    response = client.post('/api/templates', data=nested, content_type='application/json', headers=headers)
    assert response.status_code == 400, response.json
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM shared_templates').fetchone()[0] == 0
    cycle = {}
    cycle['self'] = cycle
    with pytest.raises(ApiError):
        encode_recipe(cycle, FORMAT_BY_ID)


def test_shape_layers_use_brand_tokens_and_reject_unsupported_geometry():
    data = recipe()
    data['master']['layers'].append(
        {'id': 'shape-slot-1', 'type': 'rect', 'role': 'shape', 'shape': 'square',
         'x': .1, 'y': .1, 'w': .2, 'h': .2, 'color': '@brand.color', 'opacity': .5})
    data['master']['layers'].append(
        {'id': 'shape-slot-2', 'type': 'rect', 'role': 'shape', 'shape': 'rectangle',
         'x': .4, 'y': .4, 'w': .3, 'h': .15, 'color': '#112233', 'radius': .02})
    assert json.loads(encode_recipe(data, FORMAT_BY_ID)) == data
    bad_kind = copy.deepcopy(data)
    bad_kind['master']['layers'][-1]['shape'] = 'oval'
    with pytest.raises(ApiError):
        encode_recipe(bad_kind, FORMAT_BY_ID)
    bad_geometry = copy.deepcopy(data)
    bad_geometry['master']['layers'][-1]['w'] = float('nan')
    with pytest.raises(ApiError):
        encode_recipe(bad_geometry, FORMAT_BY_ID)
    legacy = copy.deepcopy(data)
    legacy['master']['layers'] = [layer for layer in legacy['master']['layers'] if layer['role'] != 'shape']
    assert json.loads(encode_recipe(legacy, FORMAT_BY_ID)) == legacy
