import io
import json
import sqlite3
import zipfile

from PIL import Image
from werkzeug.datastructures import MultiDict

from test_api import image_bytes, studio, upload
from storage import Storage


def save_state(client, headers, campaign, state):
    return client.put(f"/api/campaigns/{campaign['id']}",
                      json={'version': campaign['version'], 'state': state}, headers=headers)


def shape_layer(**overrides):
    layer = {'id': 'shape-1', 'type': 'rect', 'role': 'shape', 'shape': 'rectangle',
             'x': 0.30, 'y': 0.38, 'w': 0.40, 'h': 0.20, 'color': '#E76A25', 'opacity': 1}
    layer.update(overrides)
    return layer


def test_shape_layers_round_trip_through_campaign_save(studio):
    app, store, client, headers, brand, campaign = studio
    state = {'confirmed': True, 'scene': {'template': 'split', 'width': 1200, 'height': 900,
                                          'background': '#ffffff', 'layers': [shape_layer(),
                                                                              shape_layer(id='shape-2', shape='square', x=.55, y=.55, w=.2, h=.2, radius=.25, opacity=.4, color='#112233')]}}
    saved = save_state(client, headers, campaign, state)
    assert saved.status_code == 200, saved.json
    assert client.get(f"/api/campaigns/{campaign['id']}").json['state'] == state


def test_shape_layers_reject_unsupported_and_unbounded_payloads(studio):
    app, store, client, headers, brand, campaign = studio
    endpoint = f"/api/campaigns/{campaign['id']}"
    bad_states = [
        ('unsupported kind', shape_layer(shape='oval')),
        ('shape kind not a string', shape_layer(shape=['rectangle'])),
        ('negative width', shape_layer(w=-0.1)),
        ('unbounded width', shape_layer(w=10 ** 6)),
        ('unbounded x', shape_layer(x=-10 ** 6)),
        ('opacity out of range', shape_layer(opacity=1.5)),
        ('radius unbounded', shape_layer(radius=10 ** 5)),
        ('geometry not numeric', shape_layer(x='0.1')),
        ('boolean geometry', shape_layer(w=True)),
        ('color not hex', shape_layer(color='brand.color')),
        ('color with payload', shape_layer(color='#E76A25; url(evil)')),
        ('file reference on shape', shape_layer(src='/api/assets/' + 'a' * 24 + '/file')),
        ('asset id on shape', shape_layer(asset_id='a' * 24)),
    ]
    current_version = campaign['version']
    for reason, layer in bad_states:
        state = {'confirmed': True, 'scene': {'layers': [layer]}}
        rejected = save_state(client, headers, campaign, state)
        assert rejected.status_code == 400, (reason, rejected.json)
        # The failed save must not damage the saved work.
        assert client.get(endpoint).json['version'] == current_version, reason


def test_non_finite_shape_geometry_fails(studio):
    app, store, client, headers, brand, campaign = studio
    version = client.get(f"/api/campaigns/{campaign['id']}").json['version']
    for value in ('NaN', 'Infinity'):
        payload = ('{"version": %d, "state": {"confirmed": true, "scene": {"layers": [{"id": "shape-1", '
                   '"type": "rect", "role": "shape", "shape": "rectangle", "x": %s, "y": 0, "w": 0.1, "h": 0.1}]}}}'
                   % (version, value))
        rejected = client.put(f"/api/campaigns/{campaign['id']}", data=payload,
                              content_type='application/json', headers=headers)
        assert rejected.status_code == 400, rejected.json


def test_all_six_shape_kinds_round_trip_and_fail_predictably(studio):
    app, store, client, headers, brand, campaign = studio
    state = {'confirmed': True, 'scene': {'layers': [
        shape_layer(shape='circle', x=.55, y=.35, w=.2, h=.2),
        shape_layer(shape='ellipse', x=.1, y=.6, w=.3, h=.18, opacity=.7),
        shape_layer(shape='triangle', x=.1, y=.05, w=.2, h=.15),
        shape_layer(shape='diamond', x=.35, y=.62, w=.18, h=.18, color='#334455')]}}
    saved = save_state(client, headers, campaign, state)
    assert saved.status_code == 200, saved.json
    current = client.get(f"/api/campaigns/{campaign['id']}").json
    assert current['state'] == state
    for bad in ('pentagon', 'star', 'RECTANGLE', None, 3):
        rejected = save_state(client, headers, {**current, 'version': current['version']},
                              {'confirmed': True, 'scene': {'layers': [shape_layer(shape=bad)]}})
        assert rejected.status_code == 400, (bad, rejected.json)
        current['version'] = current['version']


def test_team_template_with_all_shape_kinds_round_trips(studio):
    app, store, client, headers, brand, campaign = studio
    scene = {'template': 'split', 'width': 1200, 'height': 900, 'background': '#ffffff', 'layers': [
        shape_layer(shape='circle', color='#E76A25'),
        shape_layer(id='shape-2', shape='diamond', color='#334455', opacity=.7)]}
    recipe_layers = [{'id': 'shape-slot-1', 'type': 'rect', 'role': 'shape', 'shape': 'circle',
                      'x': .35, 'y': .35, 'w': .3, 'h': .3, 'color': '@brand.color'},
                     {'id': 'shape-slot-2', 'type': 'rect', 'role': 'shape', 'shape': 'diamond',
                      'x': .35, 'y': .35, 'w': .3, 'h': .3, 'color': '#334455', 'opacity': .7}]
    other_brand = client.post('/api/brands', json={'name': 'Inna', 'color': '#073050'}, headers=headers).json
    created = client.post('/api/templates', json={
        'name': 'Kształty',
        'recipe': {'version': 1, 'base_template': 'split',
                   'master': {'width': 1200, 'height': 900, 'background': '@brand.secondary_color', 'clean': False, 'layers': recipe_layers},
                   'formats': {}}}, headers=headers)
    assert created.status_code == 201, created.json
    assert client.get('/api/templates').json['items'][0]['name'] == 'Kształty'


def test_legacy_rectangle_decorations_stay_readable(studio):
    app, store, client, headers, brand, campaign = studio
    state = {'confirmed': True, 'scene': {'layers': [
        {'id': 'ribbon-paper', 'type': 'rect', 'role': 'decoration', 'x': 0, 'y': 0, 'w': 1, 'h': .2,
         'color': '#F4F1EC', 'opacity': 1},
        {'id': 'brand-rule', 'type': 'rect', 'role': 'decoration', 'x': .05, 'y': .22, 'w': .2, 'h': .01,
         'color': '#E76A25', 'cornerRadius': 0, 'borderWidth': 0}]}}
    saved = save_state(client, headers, campaign, state)
    assert saved.status_code == 200, saved.json
    assert client.get(f"/api/campaigns/{campaign['id']}").json['state'] == state


def test_multi_format_state_has_bounded_room_for_layers(studio):
    app,store,client,headers,brand,campaign=studio
    endpoint=f"/api/campaigns/{campaign['id']}"
    # Fifty-one responsive scenes with extra layers exceeded the old 256 KiB cap.
    layer={'type':'text','role':'description','text':'Opis oferty '*12,'x':.123456,'y':.234567,'w':.45,'h':.15}
    state={'confirmed':True,'scenes':{f'layout-{n}':{'layers':[dict(layer,id=str(i)) for i in range(24)]} for n in range(51)}}
    assert 256*1024<len(json.dumps(state).encode())<512*1024
    saved=client.put(endpoint,json={'version':campaign['version'],'state':state},headers=headers)
    assert saved.status_code==200,saved.json
    assert client.get(endpoint).json['state']==state
    too_large=client.put(endpoint,json={'version':saved.json['version'],'state':{'notes':'x'*(512*1024)}},headers=headers)
    assert too_large.status_code==400


def test_element_upload_and_selected_cutout_method(studio):
    app,store,client,headers,brand,campaign=studio
    methods=[]
    def remove(source,target,*,method='smart'):
        methods.append(method)
        with Image.open(source) as image:
            image.convert('RGBA').save(target,format='PNG')
    app.config['BACKGROUND_REMOVE']=remove
    asset=upload(client,headers,campaign,kind='element')
    assert asset.status_code==201,asset.json
    endpoint=f"/api/assets/{asset.json['id']}/remove-background"
    assert client.post(endpoint,json={'method':'unknown'},headers=headers).status_code==400
    job=client.post(endpoint,json={'method':'ai'},headers=headers)
    assert job.status_code==202,job.json
    app.extensions['studio_jobs'].join()
    result=client.get('/api/jobs/'+job.json['id']).json
    assert result['status']=='done',result
    assert result['method']=='ai'
    assert methods==['ai']
    assert result['asset']['kind']=='element'
    assert result['asset']['parent_id']==asset.json['id']


def test_dimension_filenames_preserve_each_composition_and_variant(studio):
    app,store,client,headers,brand,campaign=studio
    manifest=[]
    data=MultiDict()
    for template,variant in [('split','A'),('minimal','A'),('split','B')]:
        manifest.append(dict(name='300x250.jpg',format_id='display_300x250',width=300,height=250,template=template,variant=variant))
        data.add('files',(io.BytesIO(image_bytes()),'300x250.jpg'))
    data.add('manifest',json.dumps(manifest))
    data.add('texts',json.dumps({'headlines':['Oferta'],'descriptions':[],'ctas':[]}))
    data.add('version',str(campaign['version']))
    result=client.post(f"/api/campaigns/{campaign['id']}/exports",data=data,headers=headers)
    assert result.status_code==201,result.json
    with zipfile.ZipFile(io.BytesIO(client.get(result.json['url']).data)) as archive:
        files={name for name in archive.namelist() if name.endswith('.jpg')}
        assert files=={'display/split/A/300x250.jpg','display/minimal/A/300x250.jpg','display/split/B/300x250.jpg'}
        assert all(path in archive.read('manifest.csv').decode('utf-8-sig') for path in files)


def test_existing_job_database_gains_method_without_losing_rows(tmp_path):
    root=tmp_path/'legacy'
    root.mkdir()
    db=sqlite3.connect(root/'studio.sqlite3')
    db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,asset_id TEXT,campaign_id TEXT,status TEXT,error TEXT,output_asset_id TEXT,created_at TEXT,updated_at TEXT)')
    db.execute("INSERT INTO jobs VALUES('old-job','asset','campaign','done',NULL,NULL,'2026-01-01','2026-01-01')")
    db.commit();db.close()
    store=Storage(root,64*1024*1024,0,recover=False)
    with store.db() as db:
        row=db.execute("SELECT * FROM jobs WHERE id='old-job'").fetchone()
        assert row['method']=='smart'
        assert row['status']=='done'


def test_duplicate_clears_multi_material_selections_and_keeps_brand_assets(studio):
    app,store,client,headers,brand,campaign=studio
    products=[upload(client,headers,campaign).json for _ in range(2)]
    element=upload(client,headers,campaign,kind='element').json
    logo=client.post(f"/api/brands/{brand['id']}/assets",data={
        'kind':'logo','file':(io.BytesIO(image_bytes()),'logo.jpg')},headers=headers).json
    state={'confirmed':True,'product_asset_id':products[0]['id'],
        'product_asset_ids':[asset['id'] for asset in products],
        'element_asset_ids':[element['id']],
        'scene':{'layers':[{'id':'product','asset_id':products[0]['id'],'src':products[0]['url']},
                           {'id':'element-label','asset_id':element['id'],'src':element['url']},
                           {'id':'logo','asset_id':logo['id'],'src':logo['url']}]}}
    endpoint=f"/api/campaigns/{campaign['id']}"
    saved=client.put(endpoint,json={'version':campaign['version'],'state':state},headers=headers)
    assert saved.status_code==200,saved.json
    copied=client.post(endpoint+'/duplicate',json={},headers=headers)
    assert copied.status_code==201,copied.json
    copied_state=copied.json['state']
    assert copied_state['product_asset_ids']==[]
    assert copied_state['element_asset_ids']==[]
    assert copied_state['product_asset_id'] is None
    assert copied_state['confirmed'] is False
    assert copied_state['scene']['layers'][1]['src'] is None
    assert copied_state['scene']['layers'][2]['src']==logo['url']
    assert client.get(endpoint).json['state']==state
