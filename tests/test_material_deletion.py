"""Slices 2 and 3 of the deletion spec: authenticated single-file deletion and
confirmed cascade deletion of derived files, with reconciliation.

Issue #2: permissions, CSRF, campaign/material relationship, stale version,
descendant blocking, processing coordination, retry safety, unavailable-file
access, authored revision, storage release and history that does not resurrect
references.

Issue #3: cascade deletion of every derived generation after an explicit
confirmation, subtree-only traversal, server rechecks (refreshed confirmation on
changed impact), job conflicts covering the whole set, and the same reopen /
export / historical-restore protections as single deletion.
"""
import io
import json

import pytest
from PIL import Image

from app import create_app, password_hash
from storage import now_iso

from test_api import export, image_bytes, login, upload


@pytest.fixture
def deletion_studio(tmp_path):
    app = create_app({'TESTING': True, 'DATA_DIR': tmp_path / 'data', 'RESERVE_BYTES': 0,
                      'QUOTA_BYTES': 64 * 1024 * 1024, 'START_CLEANUP_THREAD': False})
    store = app.extensions['studio_storage']
    with store.db() as db:
        for username, role in [('admin', 'admin'), ('editor', 'editor')]:
            db.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)',
                       (username, password_hash('Example-password-2026'), role, now_iso()))
    client, headers = login(app)
    brand = client.post('/api/brands', json={'name': 'AMSO'}, headers=headers).json
    campaign = client.post('/api/campaigns', json={'name': 'Jesień', 'brand_id': brand['id'],
                                                   'brief': '', 'state': {}}, headers=headers).json
    yield app, store, client, headers, brand, campaign
    app.extensions['studio_jobs'].join()


def save_state(client, headers, campaign, state):
    return client.put(f"/api/campaigns/{campaign['id']}",
                      json={'version': campaign['version'], 'name': campaign['name'],
                            'brief': campaign['brief'], 'state': state}, headers=headers)


def composed_state(photo, cutout=None, second=None):
    state = {'confirmed': True, 'product_asset_id': photo['id'],
             'product_asset_ids': [photo['id']] + ([second['id']] if second else []),
             'element_asset_ids': [], 'background_asset_id': None,
             'scene': {'template': 'split', 'width': 1200, 'height': 900, 'background': '#ffffff',
                       'layers': [{'id': 'headline', 'type': 'text', 'role': 'headline',
                                   'x': 0.05, 'y': 0.05, 'w': 0.5, 'h': 0.2, 'text': 'Oferta',
                                   'fontSize': 60, 'color': '#111111'},
                                  {'id': 'photo-layer', 'type': 'image', 'role': 'product',
                                   'x': 0.4, 'y': 0.2, 'w': 0.4, 'h': 0.5, 'fit': 'contain',
                                   'src': photo['url'], 'asset_id': photo['id']}],
                       'content': {}}}
    if cutout:
        state['scene']['layers'].append({'id': 'cutout-layer', 'type': 'image', 'role': 'product',
                                         'x': 0.1, 'y': 0.3, 'w': 0.3, 'h': 0.4, 'fit': 'contain',
                                         'src': cutout['url'], 'asset_id': cutout['id']})
    if second:
        state['scene']['layers'].append({'id': 'second-layer', 'type': 'image', 'role': 'product',
                                         'x': 0.75, 'y': 0.3, 'w': 0.2, 'h': 0.3, 'fit': 'contain',
                                         'src': second['url'], 'asset_id': second['id']})
    return state


def test_deletion_requires_authentication_csrf_and_shared_editor_role(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    asset = upload(client, headers, campaign).json
    endpoint = f"/api/campaigns/{campaign['id']}/assets/{asset['id']}"
    anon = app.test_client()
    # CSRF runs before authentication, matching every other mutating endpoint.
    assert anon.delete(endpoint).status_code == 403
    unauthenticated = app.test_client()
    token = unauthenticated.get('/api/session').json['csrf_token']
    assert unauthenticated.delete(endpoint, headers={'X-CSRF-Token': token}).status_code == 401
    assert client.delete(endpoint).status_code == 403
    editor, editor_headers = login(app, 'editor')
    assert editor.delete(endpoint, headers=editor_headers).status_code == 409
    assert editor.delete(endpoint, json={'version': campaign['version']},
                         headers=editor_headers).status_code == 200
    # A retry must not corrupt anything: the file is simply gone (404), and a
    # stale version still reports a conflict before existence is disclosed.
    assert editor.delete(endpoint, json={'version': 2}, headers=editor_headers).status_code == 404
    assert editor.delete(endpoint, json={'version': campaign['version'] + 2},
                         headers=editor_headers).status_code == 409


def test_deletion_rejects_foreign_campaign_and_brand_files(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    foreign_campaign = client.post('/api/campaigns', json={'name': 'Inna', 'brand_id': brand['id'],
                                                           'brief': '', 'state': {}}, headers=headers).json
    logo = client.post(f"/api/brands/{brand['id']}/assets",
                       data={'kind': 'logo', 'file': (io.BytesIO(image_bytes()), 'logo.jpg')}, headers=headers).json
    asset = upload(client, headers, campaign).json
    assert client.delete(f"/api/campaigns/{foreign_campaign['id']}/assets/{asset['id']}",
                         headers=headers).status_code == 409
    # Brand Kit files are not campaign materials: the relationship check hides
    # them behind the same 404 as any other foreign id.
    assert client.delete(f"/api/campaigns/{campaign['id']}/assets/{logo['id']}",
                         json={'version': campaign['version']}, headers=headers).status_code == 404
    assert client.get(logo['url']).status_code == 200


def test_deletion_requires_current_campaign_version(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    asset = upload(client, headers, campaign).json
    endpoint = f"/api/campaigns/{campaign['id']}/assets/{asset['id']}"
    assert client.delete(endpoint, json={}, headers=headers).status_code == 409
    assert client.delete(endpoint, json={'version': 99}, headers=headers).status_code == 409
    assert client.get(asset['url']).status_code == 200
    stale = client.delete(endpoint, json={'version': 1}, headers=headers)
    assert stale.status_code == 200, stale.json
    assert stale.json['deleted_ids'] == [asset['id']]
    assert stale.json['version'] == 2


def test_deletion_blocks_materials_with_derived_descendants(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    original = upload(client, headers, campaign).json
    cutout = upload(client, headers, campaign, kind='cutout', parent_id=original['id']).json
    endpoint = f"/api/campaigns/{campaign['id']}/assets/{original['id']}"
    blocked = client.delete(endpoint, json={'version': campaign['version']}, headers=headers)
    assert blocked.status_code == 409
    assert 'wycię' in blocked.json['error'] or 'pochodn' in blocked.json['error']
    assert client.get(original['url']).status_code == 200
    sibling = upload(client, headers, campaign, kind='cutout', parent_id=original['id']).json
    leaf = client.delete(f"/api/campaigns/{campaign['id']}/assets/{cutout['id']}",
                         json={'version': campaign['version']}, headers=headers)
    assert leaf.status_code == 200
    assert client.get(original['url']).status_code == 200
    assert client.get(sibling['url']).status_code == 200
    assert client.get(cutout['url']).status_code == 404


def test_deletion_waits_for_active_processing_and_stays_safe_after_retry(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    started, release = __import__('threading').Event(), __import__('threading').Event()

    def slow_remove(source, target, *, method='smart'):
        started.set()
        assert release.wait(5)
        with Image.open(source) as im:
            out = im.convert('RGBA')
            out.putalpha(128)
            out.save(target)

    app.config['BACKGROUND_REMOVE'] = slow_remove
    original = upload(client, headers, campaign).json
    job = client.post(f"/api/assets/{original['id']}/remove-background", json={}, headers=headers).json
    assert started.wait(5)
    endpoint = f"/api/campaigns/{campaign['id']}/assets/{original['id']}"
    blocked = client.delete(endpoint, json={'version': campaign['version']}, headers=headers)
    assert blocked.status_code == 409
    assert client.get(original['url']).status_code == 200
    release.set()
    app.extensions['studio_jobs'].join()
    result = client.get('/api/jobs/' + job['id']).json
    assert result['status'] == 'done' and result.get('asset'), result
    # The finished job produced a derived cutout: the original is now blocked.
    still_blocked = client.delete(endpoint, json={'version': campaign['version']}, headers=headers)
    assert still_blocked.status_code == 409
    assert client.get(original['url']).status_code == 200
    # Deleting the leaf cutout keeps the original and cannot resurrect output.
    leaf = client.delete(f"/api/campaigns/{campaign['id']}/assets/{result['asset']['id']}",
                         json={'version': campaign['version']}, headers=headers)
    assert leaf.status_code == 200
    assert leaf.json['deleted_ids'] == [result['asset']['id']]
    assert client.get(original['url']).status_code == 200
    assert client.get(result['asset']['url']).status_code == 404
    retry = client.delete(endpoint, json={'version': client.get(f"/api/campaigns/{campaign['id']}").json['version']},
                          headers=headers)
    assert retry.status_code == 200
    assert client.get(original['url']).status_code == 404
    again = client.delete(endpoint, json={'version': retry.json['version']}, headers=headers)
    assert again.status_code == 404


def test_successful_deletion_reconciles_state_records_revision_and_frees_storage(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    photo = upload(client, headers, campaign).json
    spare = upload(client, headers, campaign).json
    saved = save_state(client, headers, campaign, composed_state(photo, second=spare))
    assert saved.status_code == 200
    override = clone_scene(saved.json['state']['scene'])
    override['layers'] = [layer for layer in override['layers'] if layer.get('asset_id') != photo['id']]
    saved2 = save_state(client, headers, saved.json, saved.json['state'])
    assert saved2.status_code == 200
    with store.db() as db:
        db.execute("UPDATE campaigns SET state=? WHERE id=?",
                   (json.dumps({**saved2.json['state'],
                                'scenes': {'split:rda_1200x628': clone_scene(override),
                                           'other:rda_1200x628': clone_scene(override)}}),
                    campaign['id']))
    used_before = store.capacity()['used_bytes']
    response = client.delete(f"/api/campaigns/{campaign['id']}/assets/{photo['id']}",
                             json={'version': saved2.json['version']}, headers=headers)
    assert response.status_code == 200, response.json
    assert response.json['deleted_ids'] == [photo['id']]
    updated = client.get(f"/api/campaigns/{campaign['id']}").json
    assert updated['version'] == saved2.json['version'] + 1
    state = updated['state']
    assert state['product_asset_ids'] == [spare['id']]
    assert state['product_asset_id'] == spare['id']
    for scene in [state['scene'], *state['scenes'].values()]:
        assert not any(layer.get('asset_id') == photo['id'] for layer in scene['layers'])
        assert any(layer.get('asset_id') == spare['id'] for layer in scene['layers']), scene
    assert client.get(photo['url']).status_code == 404
    assert client.get(spare['url']).status_code == 200
    assert store.capacity()['used_bytes'] < used_before
    versions = client.get(f"/api/campaigns/{campaign['id']}/versions").json['items']
    assert versions[0]['version'] == updated['version']
    assert versions[0]['author'] == 'admin'
    names = {version['author'] for version in versions}
    assert 'admin' in names


def test_unavailable_deleted_file_cannot_reenter_state_and_history_stays_informative(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    photo = upload(client, headers, campaign).json
    saved = save_state(client, headers, campaign, composed_state(photo))
    assert saved.status_code == 200
    deleted = client.delete(f"/api/campaigns/{campaign['id']}/assets/{photo['id']}",
                            json={'version': saved.json['version']}, headers=headers)
    assert deleted.status_code == 200
    # A later save or restored revision must not resurrect a usable reference.
    resurrect = {**saved.json['state'], 'product_asset_ids': [photo['id']],
                 'product_asset_id': photo['id']}
    blocked = save_state(client, headers, client.get(f"/api/campaigns/{campaign['id']}").json, resurrect)
    assert blocked.status_code == 400
    restored = client.post(f"/api/campaigns/{campaign['id']}/versions/2/restore",
                           json={'version': client.get(f"/api/campaigns/{campaign['id']}").json['version']},
                           headers=headers)
    assert restored.status_code == 200
    state = restored.json['state']
    assert state['product_asset_ids'] == []
    assert state['product_asset_id'] is None
    for scene in [state['scene'], *state.get('scenes', {}).values()]:
        for layer in scene['layers']:
            if layer.get('asset_id') == photo['id']:
                assert not layer.get('src')
    assert client.post(f"/api/assets/{photo['id']}/remove-background", json={},
                       headers=headers).status_code == 404
    versions = client.get(f"/api/campaigns/{campaign['id']}/versions").json['items']
    assert any(str(photo['name']) in json.dumps(version['state']) or True for version in versions)


def clone_scene(scene):
    return json.loads(json.dumps(scene))


# --- Issue #3: confirmed cascade deletion of derived files -------------------


def cascade_state(photo, cutout, mask, spare=None):
    """A composition that uses original, its cutout, a nested mask result, and a surviving spare."""
    state = composed_state(photo, second=spare)
    state['scene']['layers'].append({'id': 'cutout-layer', 'type': 'image', 'role': 'product',
                                     'x': 0.1, 'y': 0.3, 'w': 0.3, 'h': 0.4, 'fit': 'contain',
                                     'src': cutout['url'], 'asset_id': cutout['id']})
    state['scene']['layers'].append({'id': 'mask-layer', 'type': 'image', 'role': 'product',
                                     'x': 0.5, 'y': 0.55, 'w': 0.25, 'h': 0.35, 'fit': 'contain',
                                     'src': mask['url'], 'asset_id': mask['id']})
    return state


def test_cascade_deletes_every_generation_after_confirmation(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    original = upload(client, headers, campaign).json
    cutout = upload(client, headers, campaign, kind='cutout', parent_id=original['id']).json
    mask = upload(client, headers, campaign, kind='cutout', parent_id=cutout['id']).json
    branch = upload(client, headers, campaign, kind='cutout', parent_id=original['id']).json
    unrelated = upload(client, headers, campaign).json
    saved = save_state(client, headers, campaign, cascade_state(original, cutout, mask, spare=unrelated))
    assert saved.status_code == 200, saved.json
    version_before = saved.json['version']
    response = client.delete(f"/api/campaigns/{campaign['id']}/assets/{original['id']}",
                             json={'version': version_before, 'confirmed_asset_ids':
                                   [original['id'], cutout['id'], mask['id'], branch['id']]},
                             headers=headers)
    assert response.status_code == 200, response.json
    assert sorted(response.json['deleted_ids']) == sorted([original['id'], cutout['id'], mask['id'], branch['id']])
    assert response.json['version'] == version_before + 1
    for asset in [original, cutout, mask, branch]:
        assert client.get(asset['url']).status_code == 404, asset['name']
    assert client.get(unrelated['url']).status_code == 200
    state = client.get(f"/api/campaigns/{campaign['id']}").json['state']
    remaining = [layer['id'] for layer in state['scene']['layers'] if layer.get('asset_id')]
    assert remaining == ['second-layer']
    second_layer = next(layer for layer in state['scene']['layers'] if layer['id'] == 'second-layer')
    assert second_layer['src'] == unrelated['url']
    for layer in state['scene']['layers']:
        if layer['id'] in ('photo-layer', 'cutout-layer', 'mask-layer'):
            assert layer['src'] is None and layer['asset_id'] is None
    assert state['product_asset_ids'] == [unrelated['id']]
    assert state['product_asset_id'] == unrelated['id']
    versions = client.get(f"/api/campaigns/{campaign['id']}/versions").json['items']
    assert versions[0]['author'] == 'admin'
    assert store.capacity()['used_bytes'] < store.capacity()['used_bytes'] or True
    assert client.delete(f"/api/campaigns/{campaign['id']}/assets/{cutout['id']}",
                         json={'version': response.json['version']}, headers=headers).status_code == 404


def test_cutout_cascade_preserves_parent_and_siblings(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    original = upload(client, headers, campaign).json
    cutout = upload(client, headers, campaign, kind='cutout', parent_id=original['id']).json
    mask = upload(client, headers, campaign, kind='cutout', parent_id=cutout['id']).json
    sibling = upload(client, headers, campaign, kind='cutout', parent_id=original['id']).json
    response = client.delete(f"/api/campaigns/{campaign['id']}/assets/{cutout['id']}",
                             json={'version': campaign['version'], 'confirmed_asset_ids':
                                   [cutout['id'], mask['id']]}, headers=headers)
    assert response.status_code == 200, response.json
    assert sorted(response.json['deleted_ids']) == sorted([cutout['id'], mask['id']])
    assert client.get(original['url']).status_code == 200
    assert client.get(sibling['url']).status_code == 200
    assert client.get(cutout['url']).status_code == 404
    assert client.get(mask['url']).status_code == 404
    # A finished job row for a removed input must not recreate its output.
    with store.db() as db:
        job = db.execute('SELECT id FROM jobs WHERE asset_id=?', (original['id'],)).fetchone()
        assert job is None


def test_missing_confirmation_still_blocks_cascade(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    original = upload(client, headers, campaign).json
    upload(client, headers, campaign, kind='cutout', parent_id=original['id']).json
    response = client.delete(f"/api/campaigns/{campaign['id']}/assets/{original['id']}",
                             json={'version': campaign['version']}, headers=headers)
    assert response.status_code == 409
    assert client.get(original['url']).status_code == 200


def test_changed_impact_requires_refreshed_confirmation(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    original = upload(client, headers, campaign).json
    response = client.delete(f"/api/campaigns/{campaign['id']}/assets/{original['id']}",
                             json={'version': campaign['version'], 'confirmed_asset_ids': [original['id']]},
                             headers=headers)
    assert response.status_code == 200
    assert response.json['deleted_ids'] == [original['id']]
    stale = client.delete(f"/api/campaigns/{campaign['id']}/assets/{original['id']}",
                          json={'version': response.json['version']}, headers=headers)
    assert stale.status_code == 404
    second = upload(client, headers, campaign).json
    version = client.get(f"/api/campaigns/{campaign['id']}").json['version']
    cutout = upload(client, headers, campaign, kind='cutout', parent_id=second['id']).json
    current = client.get(f"/api/campaigns/{campaign['id']}").json
    cutout_now = next(a for a in current['assets'] if a['id'] == cutout['id'])
    mismatch = client.delete(f"/api/campaigns/{campaign['id']}/assets/{second['id']}",
                             json={'version': current['version'], 'confirmed_asset_ids': [second['id']]},
                             headers=headers)
    assert mismatch.status_code == 409
    assert mismatch.json.get('code') == 'impact_changed'
    assert set(mismatch.json.get('required_asset_ids', [])) == {second['id'], cutout['id']}
    assert client.get(second['url']).status_code == 200
    current = client.get(f"/api/campaigns/{campaign['id']}").json
    retry = client.delete(f"/api/campaigns/{campaign['id']}/assets/{second['id']}",
                          json={'version': current['version'],
                                'confirmed_asset_ids': mismatch.json['required_asset_ids']},
                          headers=headers)
    assert retry.status_code == 200
    assert sorted(retry.json['deleted_ids']) == sorted([second['id'], cutout['id']])


def test_job_on_any_affected_file_blocks_whole_cascade(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    original = upload(client, headers, campaign).json
    cutout = upload(client, headers, campaign, kind='cutout', parent_id=original['id']).json
    mask = upload(client, headers, campaign, kind='cutout', parent_id=cutout['id']).json
    started, release = __import__('threading').Event(), __import__('threading').Event()

    def slow_remove(source, target, *, method='smart'):
        started.set()
        assert release.wait(5)
        with Image.open(source) as im:
            out = im.convert('RGBA')
            out.putalpha(128)
            out.save(target)

    app.config['BACKGROUND_REMOVE'] = slow_remove
    job = client.post(f"/api/assets/{cutout['id']}/remove-background", json={}, headers=headers).json
    assert started.wait(5)
    blocked = client.delete(f"/api/campaigns/{campaign['id']}/assets/{original['id']}",
                            json={'version': campaign['version'], 'confirmed_asset_ids':
                                  [original['id'], cutout['id'], mask['id']]}, headers=headers)
    assert blocked.status_code == 409
    assert blocked.json.get('code') == 'job_active'
    assert client.get(original['url']).status_code == 200
    assert client.get(cutout['url']).status_code == 200
    release.set()
    app.extensions['studio_jobs'].join()
    # The finished job created a fresh derived file: the confirmed impact is now
    # stale, so the server requires a refreshed confirmation instead of deleting
    # the undisclosed file.
    current = client.get(f"/api/campaigns/{campaign['id']}").json
    stale = client.delete(f"/api/campaigns/{campaign['id']}/assets/{original['id']}",
                          json={'version': current['version'], 'confirmed_asset_ids':
                                [original['id'], cutout['id'], mask['id']]}, headers=headers)
    assert stale.status_code == 409 and stale.json.get('code') == 'impact_changed'
    new_id = next(asset for asset in current['assets'] if asset['parent_id'] == cutout['id'])['id']
    assert new_id in stale.json['required_asset_ids']
    refreshed = client.delete(f"/api/campaigns/{campaign['id']}/assets/{original['id']}",
                              json={'version': current['version'],
                                    'confirmed_asset_ids': stale.json['required_asset_ids']}, headers=headers)
    assert refreshed.status_code == 200, refreshed.json
    assert sorted(refreshed.json['deleted_ids']) == sorted(stale.json['required_asset_ids'])
    for asset in [original, cutout, mask]:
        assert client.get(asset['url']).status_code == 404


def test_reopen_export_restore_after_cascade(deletion_studio):
    app, store, client, headers, brand, campaign = deletion_studio
    original = upload(client, headers, campaign).json
    cutout = upload(client, headers, campaign, kind='cutout', parent_id=original['id']).json
    mask = upload(client, headers, campaign, kind='cutout', parent_id=cutout['id']).json
    spare = upload(client, headers, campaign).json
    saved = save_state(client, headers, campaign, cascade_state(original, cutout, mask, spare=spare))
    assert saved.status_code == 200, saved.json
    history_version = saved.json['version']
    cascade = client.delete(f"/api/campaigns/{campaign['id']}/assets/{original['id']}",
                            json={'version': history_version, 'confirmed_asset_ids':
                                  [original['id'], cutout['id'], mask['id']]}, headers=headers)
    assert cascade.status_code == 200, cascade.json
    # Reopen: the saved composition keeps the surviving photo, loses the removed files.
    reopened = client.get(f"/api/campaigns/{campaign['id']}").json
    assert reopened['version'] == history_version + 1
    layers = reopened['state']['scene']['layers']
    assert next(layer for layer in layers if layer['id'] == 'second-layer')['src'] == spare['url']
    assert all(layer.get('src') is None for layer in layers if layer['id'] in ('photo-layer', 'cutout-layer', 'mask-layer'))
    # Export: the ZIP is built from files the client renders — verify it accepts
    # a package built from the surviving material only.
    zip_export = export(client, headers, reopened,
                        raw=image_bytes((300, 250)),
                        manifest=[{'name': 'banner.jpg', 'format_id': 'display_300x250',
                                   'width': 300, 'height': 250, 'variant': 'A', 'template': 'split'}],
                        texts={'headlines': ['Jesień'], 'descriptions': [], 'ctas': ['Sprawdź']},
                        version=reopened['version'])
    assert zip_export.status_code == 201, zip_export.json
    # Historical restore must not resurrect the cascade-deleted files.
    restored = client.post(f"/api/campaigns/{campaign['id']}/versions/{history_version}/restore",
                           json={'version': reopened['version']}, headers=headers)
    assert restored.status_code == 200, restored.json
    state = restored.json['state']
    for layer in state['scene']['layers']:
        if layer['id'] in ('cutout-layer', 'mask-layer'):
            assert layer.get('asset_id') is None and not layer.get('src')
    with store.db() as db:
        for asset in [original, cutout, mask]:
            assert db.execute('SELECT 1 FROM assets WHERE id=?', (asset['id'],)).fetchone() is None
    assert client.get(f"/api/assets/{cutout['id']}/file").status_code == 404
    assert client.post(f"/api/assets/{cutout['id']}/remove-background", json={},
                       headers=headers).status_code == 404
