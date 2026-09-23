import io
import json
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image
from werkzeug.datastructures import MultiDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import METADATA_MARGIN, create_app, password_hash
from storage import Storage, now_iso

PASSWORD='Example-password-2026'


def image_bytes(size=(300,250),fmt='JPEG',alpha=False):
    out=io.BytesIO()
    Image.new('RGBA' if alpha else 'RGB',size,(210,60,20,0) if alpha else (210,60,20)).save(out,format=fmt)
    return out.getvalue()


def login(app,username='admin'):
    client=app.test_client()
    token=client.get('/api/session').json['csrf_token']
    res=client.post('/api/login',json={'username':username,'password':PASSWORD},headers={'X-CSRF-Token':token})
    assert res.status_code==200,res.json
    return client,{'X-CSRF-Token':res.json['csrf_token']}


@pytest.fixture
def studio(tmp_path):
    def remove(source,target,*,method='smart'):
        with Image.open(source) as im:
            out=im.convert('RGBA')
            out.putalpha(128)
            out.save(target)
    app=create_app({'TESTING':True,'DATA_DIR':tmp_path/'data','RESERVE_BYTES':0,'QUOTA_BYTES':64*1024*1024,'BACKGROUND_REMOVE':remove})
    store=app.extensions['studio_storage']
    with store.db() as db:
        for username,role in [('admin','admin'),('editor','editor')]:
            db.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)',(username,password_hash(PASSWORD),role,now_iso()))
    client,headers=login(app)
    brand=client.post('/api/brands',json={'name':'AMSO'},headers=headers).json
    campaign=client.post('/api/campaigns',json={'name':'Jesień','brand_id':brand['id'],'brief':'Laptop do pracy','state':{'confirmed':True}},headers=headers).json
    yield app,store,client,headers,brand,campaign
    app.extensions['studio_jobs'].join()


def upload(client,headers,campaign,**kwargs):
    data={'kind':kwargs.get('kind','product'),'file':(io.BytesIO(kwargs.get('raw',image_bytes())),'laptop.jpg')}
    if kwargs.get('parent_id'):
        data['parent_id']=kwargs['parent_id']
    return client.post(f"/api/campaigns/{campaign['id']}/assets",data=data,headers=headers)


def export(client,headers,campaign,raw=None,manifest=None,texts=None,version=None):
    item={'name':'banner.jpg','format_id':'display_300x250','width':300,'height':250,'variant':'A','template':'split'}
    data=MultiDict([('manifest',json.dumps(manifest if manifest is not None else [item])),
        ('texts',json.dumps(texts if texts is not None else {'headlines':['Jesień'],'descriptions':[],'ctas':['Sprawdź']})),
        ('version',str(version if version is not None else campaign['version'])),
        ('files',(io.BytesIO(raw if raw is not None else image_bytes()),'banner.jpg'))])
    return client.post(f"/api/campaigns/{campaign['id']}/exports",data=data,headers=headers)


def test_authentication_csrf_and_roles(studio):
    app,store,client,headers,brand,campaign=studio
    anon=app.test_client()
    assert anon.get('/api/campaigns').status_code==401
    assert anon.post('/api/login',json={'username':'admin','password':PASSWORD}).status_code==403
    assert client.post('/api/campaigns',json={}).status_code==403
    editor,editor_headers=login(app,'editor')
    assert editor.get(f"/api/campaigns/{campaign['id']}").status_code==200
    assert editor.post('/api/brands',json={'name':'Other'},headers=editor_headers).status_code==403
    assert editor.get('/api/users').status_code==403
    assert editor.post('/api/users',json={},headers=editor_headers).status_code==403
    assert editor.post('/api/logout',headers=editor_headers).status_code==200
    assert editor.get('/api/campaigns').status_code==401


def test_admin_invariants_and_password_session_revocation(studio):
    app,store,client,headers,brand,campaign=studio
    users=client.get('/api/users').json['items']
    assert all('password_hash' not in u for u in users)
    admin=next(u for u in users if u['role']=='admin')
    editor_user=next(u for u in users if u['role']=='editor')
    assert client.put(f"/api/users/{admin['id']}",json={'active':False},headers=headers).status_code==409
    assert client.put(f"/api/users/{admin['id']}",json={'role':'editor'},headers=headers).status_code==409
    editor,eh=login(app,'editor')
    assert client.put(f"/api/users/{editor_user['id']}",json={'password':'Changed-password-2026'},headers=headers).status_code==200
    assert editor.get('/api/session').json['user'] is None
    assert editor.get('/api/campaigns').status_code==401
    assert client.post('/api/users',json={'username':'new','password':'short','role':'editor'},headers=headers).status_code==400


def test_login_rate_limit(studio):
    app,*_=studio
    client=app.test_client()
    h={'X-CSRF-Token':client.get('/api/session').json['csrf_token']}
    for _ in range(8):
        assert client.post('/api/login',json={'username':'does-not-exist','password':'wrong'},headers=h).status_code==401
    assert client.post('/api/login',json={'username':'does-not-exist','password':'wrong'},headers=h).status_code==429


def test_version_conflict_shared_edit_and_restore(studio):
    app,store,client,headers,brand,campaign=studio
    editor,eh=login(app,'editor')
    endpoint=f"/api/campaigns/{campaign['id']}"
    changed=editor.put(endpoint,json={'version':1,'name':'Nowa nazwa','state':{'confirmed':False}},headers=eh)
    assert changed.status_code==200
    assert changed.json['version']==2 and changed.json['updater_name']=='editor'
    assert changed.json['expires_at']==campaign['expires_at']
    assert client.put(endpoint,json={'version':1,'name':'Stara karta'},headers=headers).status_code==409
    restored=client.post(endpoint+'/versions/1/restore',json={'version':2},headers=headers)
    assert restored.status_code==200 and restored.json['version']==3
    assert restored.json['name']==campaign['name']
    versions=client.get(endpoint+'/versions').json['items']
    assert [v['version'] for v in versions]==[3,2,1]
    assert versions[1]['author']=='editor'


def test_uploaded_images_are_decoded_and_private(studio):
    app,store,client,headers,brand,campaign=studio
    assert upload(client,headers,campaign,raw=b'<html>bad</html>').status_code==400
    res=upload(client,headers,campaign,raw=image_bytes(fmt='PNG',alpha=True))
    assert res.status_code==201
    asset=res.json
    assert asset['width']==300 and asset['height']==250
    assert app.test_client().get(asset['url']).status_code==401
    response=client.get(asset['url'])
    assert response.mimetype=='image/png'
    with Image.open(io.BytesIO(response.data)) as image:
        assert image.mode=='RGBA'
    other=client.post('/api/campaigns',json={'name':'Inna','brand_id':brand['id']},headers=headers).json
    assert upload(client,headers,other,parent_id=asset['id'],kind='cutout').status_code==400
    assert client.put(f"/api/campaigns/{campaign['id']}",json={'version':1,'state':{'scene':{'src':'https://example.com/photo.jpg'}}},headers=headers).status_code==400


def test_font_signature_and_brand_ownership(studio):
    app,store,client,headers,brand,campaign=studio
    endpoint=f"/api/brands/{brand['id']}/assets"
    assert client.post(endpoint,data={'kind':'font','file':(io.BytesIO(b'<svg>hi</svg>'),'font.woff2')},headers=headers).status_code==400
    font=client.post(endpoint,data={'kind':'font','file':(io.BytesIO(b'wOF2'+b'\0'*40),'brand.woff2')},headers=headers)
    assert font.status_code==201
    assert client.get(font.json['url']).mimetype=='font/woff2'
    other=client.post('/api/brands',json={'name':'Other'},headers=headers).json
    assert client.put('/api/brands/'+other['id'],json={'font_asset_id':font.json['id']},headers=headers).status_code==400


def test_expiry_cleanup_preserves_brand_metadata_and_recovery(studio):
    app,store,client,headers,brand,campaign=studio
    asset=upload(client,headers,campaign).json
    logo=client.post(f"/api/brands/{brand['id']}/assets",data={'kind':'logo','file':(io.BytesIO(image_bytes()),'logo.jpg')},headers=headers).json
    bundle=export(client,headers,campaign).json
    with store.db() as db:
        db.execute('UPDATE campaigns SET expires_at=? WHERE id=?',('2020-01-01T00:00:00+00:00',campaign['id']))
        db.execute('UPDATE exports SET expires_at=? WHERE campaign_id=?',('2020-01-01T00:00:00+00:00',campaign['id']))
    assert client.get(asset['url']).status_code==410
    assert client.get(bundle['url']).status_code==410
    assert upload(client,headers,campaign).status_code==410
    assert export(client,headers,campaign).status_code==410
    store.cleanup(force=True)
    with store.db() as db:
        assert db.execute('SELECT expired FROM assets WHERE id=?',(asset['id'],)).fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM versions WHERE campaign_id=?',(campaign['id'],)).fetchone()[0]==1
    assert client.get(logo['url']).status_code==200
    copy=client.post(f"/api/campaigns/{campaign['id']}/duplicate",json={},headers=headers)
    assert copy.status_code==201 and not copy.json['expired'] and not copy.json['state']['confirmed']
    assert copy.json['assets']==[]
    assert upload(client,headers,copy.json).status_code==201


def test_storage_quota_and_free_space_do_not_leave_partial_files(studio,monkeypatch):
    app,store,client,headers,brand,campaign=studio
    store.quota_bytes=10
    assert upload(client,headers,campaign).status_code==507
    assert list(store.media.iterdir())==[] and list(store.temp.iterdir())==[]
    store.quota_bytes=64*1024*1024
    disk_usage=__import__('shutil').disk_usage(store.root)
    monkeypatch.setattr('storage.shutil.disk_usage',lambda _:type(disk_usage)(10000,9990,10))
    store.reserve_bytes=20
    assert upload(client,headers,campaign).status_code==507
    assert not client.get('/api/storage').json['can_upload']


def test_concurrent_uploads_respect_quota(studio):
    app,store,client,headers,brand,campaign=studio
    # Sanitization fixes the exact retained JPEG size. Only one copy fits.
    noisy=io.BytesIO()
    Image.effect_noise((1000,1000),100).convert('RGB').save(noisy,format='JPEG',quality=95,optimize=True)
    raw=noisy.getvalue()
    first=upload(client,headers,campaign,raw=raw).json
    # Include transport staging and SQLite's live WAL/SHM overhead. A second
    # retained image is substantially larger than that database headroom.
    store.quota_bytes=store.capacity()['used_bytes']+first['size']+len(raw)+METADATA_MARGIN+128*1024
    clients=[login(app),login(app)]
    barrier=threading.Barrier(2)
    def run(pair):
        barrier.wait()
        return upload(*pair,campaign,raw=raw).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(run,clients))
    assert 507 in statuses and all(status in (201,507) for status in statuses)
    # Simultaneous staging may conservatively reject both; a serial retry must fit.
    if 201 not in statuses:
        assert upload(client,headers,campaign,raw=raw).status_code==201
    assert store.capacity()['used_bytes']<=store.quota_bytes
    assert list(store.temp.iterdir())==[]


def test_export_validates_bytes_manifest_and_confirmation(studio):
    app,store,client,headers,brand,campaign=studio
    assert export(client,headers,campaign,raw=image_bytes(size=(200,200))).status_code==400
    assert export(client,headers,campaign,raw=image_bytes(fmt='PNG')).status_code==400
    bad=[{'name':'../attack.jpg','format_id':'display_300x250','width':300,'height':250,'variant':'A'}]
    assert export(client,headers,campaign,manifest=bad).status_code==400
    bad[0]['format_id']=[]
    assert export(client,headers,campaign,manifest=bad).status_code==400
    assert export(client,headers,campaign,version=999).status_code==409
    changed=client.put(f"/api/campaigns/{campaign['id']}",json={'version':1,'state':{'confirmed':False}},headers=headers).json
    assert export(client,headers,changed).status_code==400
    assert list(store.media.iterdir())==[]


def test_export_zip_formula_safety_and_profile_text_limits(studio):
    app,store,client,headers,brand,campaign=studio
    res=export(client,headers,campaign,texts={'headlines':['=HYPERLINK("x")'],'descriptions':[],'ctas':['@sum(A1)']})
    assert res.status_code==201,res.json
    blob=client.get(res.json['url']).data
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        assert 'manifest.csv' in archive.namelist() and 'texts.csv' in archive.namelist()
        texts=archive.read('texts.csv').decode('utf-8-sig')
        assert "'=HYPERLINK" in texts and "'@sum" in texts
        assert all(not n.startswith('/') and '..' not in n for n in archive.namelist())
    item=[dict(name='asset.jpg',format_id='rda_1200x628',width=1200,height=628,variant='A',template='split')]
    res=export(client,headers,campaign,raw=image_bytes((1200,628)),manifest=item,
        texts={'headlines':['x'*31],'descriptions':['Opis'],'long_headline':'Długi nagłówek','business_name':'AMSO'})
    assert res.status_code==400


def test_background_queue_preserves_original_and_returns_png(studio):
    app,store,client,headers,brand,campaign=studio
    asset=upload(client,headers,campaign).json
    original=client.get(asset['url']).data
    job=client.post(f"/api/assets/{asset['id']}/remove-background",json={},headers=headers)
    assert job.status_code==202
    app.extensions['studio_jobs'].join()
    result=client.get('/api/jobs/'+job.json['id']).json
    assert result['status']=='done',result
    assert result['asset']['parent_id']==asset['id']
    assert client.get(asset['url']).data==original
    with Image.open(io.BytesIO(client.get(result['asset']['url']).data)) as cutout:
        assert cutout.mode=='RGBA' and cutout.getextrema()[3]==(128,128)
    assert list(store.temp.iterdir())==[] and store.reserved_bytes==0


def test_cli_storage_initialization_does_not_interrupt_server_work(studio):
    app,store,client,headers,brand,campaign=studio
    temporary=store.temp/'active-work'
    temporary.write_bytes(b'working')
    with store.db() as db:
        db.execute("INSERT INTO jobs(id,asset_id,campaign_id,status,created_at,updated_at) VALUES('job','asset',?,'running',?,?)",(campaign['id'],now_iso(),now_iso()))
    Storage(store.root,store.quota_bytes,store.reserve_bytes,recover=False)
    assert temporary.read_bytes()==b'working'
    with store.db() as db:
        assert db.execute("SELECT status FROM jobs WHERE id='job'").fetchone()[0]=='running'


def test_parallel_edits_have_one_winner(studio):
    app,store,client,headers,brand,campaign=studio
    clients=[login(app),login(app,'editor')]
    barrier=threading.Barrier(2)
    def run(pair):
        c,h=pair
        barrier.wait()
        return c.put(f"/api/campaigns/{campaign['id']}",json={'version':1,'name':'Zmieniona'},headers=h).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run,clients))==[200,409]
    assert len(client.get(f"/api/campaigns/{campaign['id']}/versions").json['items'])==2


def test_background_failure_releases_reservation(studio):
    app,store,client,headers,brand,campaign=studio
    def fail(source,target,*,method='smart'):
        target.write_bytes(b'partial')
        raise RuntimeError('Private backend details')
    app.config['BACKGROUND_REMOVE']=fail
    asset=upload(client,headers,campaign).json
    job=client.post(f"/api/assets/{asset['id']}/remove-background",json={},headers=headers).json
    app.extensions['studio_jobs'].join()
    result=client.get('/api/jobs/'+job['id']).json
    assert result['status']=='error' and 'Private' not in result['error']
    assert store.reserved_bytes==0 and list(store.temp.iterdir())==[]
    assert client.get(asset['url']).status_code==200


def test_duplicate_keeps_brand_files_but_clears_campaign_files(studio):
    app,store,client,headers,brand,campaign=studio
    asset=upload(client,headers,campaign).json
    logo=client.post(f"/api/brands/{brand['id']}/assets",data={'kind':'logo','file':(io.BytesIO(image_bytes()),'logo.jpg')},headers=headers).json
    state={'confirmed':True,'product_asset_id':asset['id'],'scene':{'layers':[
        {'id':'product-layer','asset_id':asset['id'],'src':asset['url']},
        {'id':'logo-layer','asset_id':logo['id'],'src':logo['url']}]}}
    assert client.put(f"/api/campaigns/{campaign['id']}",json={'version':1,'state':state},headers=headers).status_code==200
    result=client.post(f"/api/campaigns/{campaign['id']}/duplicate",json={},headers=headers).json
    assert result['state']['product_asset_id'] is None
    layers=result['state']['scene']['layers']
    assert layers[0]['src'] is None and layers[0]['id']=='product-layer'
    assert layers[1]['src']==logo['url']


def test_pmax_partial_library_reports_requirements(studio):
    app,store,client,headers,brand,campaign=studio
    item=[dict(name='pmax.jpg',format_id='pmax_1200x628',width=1200,height=628,variant='A',template='split')]
    res=export(client,headers,campaign,raw=image_bytes((1200,628)),manifest=item,
        texts={'headlines':['Oferta'],'descriptions':['Opis'],'long_headline':'Dobry sprzęt do pracy','business_name':'AMSO'})
    assert res.status_code==201 and len(res.json['warnings'])==2
    with zipfile.ZipFile(io.BytesIO(client.get(res.json['url']).data)) as archive:
        assert '3 krótkie nagłówki' in archive.read('validation.csv').decode('utf-8-sig')


def test_quota_includes_sqlite_and_live_wal(studio):
    app,store,client,headers,brand,campaign=studio
    assert store.capacity()['used_bytes']>=store.database.stat().st_size>0
    with store.db() as db:
        db.execute("UPDATE brands SET tone='Zapamiętaj ton marki'")
        db.commit()
        files=[store.database,Path(str(store.database)+'-wal'),Path(str(store.database)+'-shm')]
        actual=sum(p.stat().st_size for p in files if p.exists())
        assert store.capacity()['used_bytes']>=actual
    store.quota_bytes=store.database.stat().st_size
    assert upload(client,headers,campaign).status_code==507


def test_cpu_gate_serializes_upload_decoding_with_background(studio):
    app,store,client,headers,brand,campaign=studio
    entered,release=threading.Event(),threading.Event()
    def blocking_remove(source,target,*,method='smart'):
        entered.set()
        assert release.wait(3)
        with Image.open(source) as image:
            result=image.convert('RGBA')
            result.putalpha(128)
            result.save(target)
    app.config['BACKGROUND_REMOVE']=blocking_remove
    asset=upload(client,headers,campaign).json
    job=client.post(f"/api/assets/{asset['id']}/remove-background",json={},headers=headers).json
    assert entered.wait(3)
    from concurrent.futures import TimeoutError
    with ThreadPoolExecutor(max_workers=1) as pool:
        other_client,other_headers=login(app)
        result=pool.submit(upload,other_client,other_headers,campaign)
        try:
            with pytest.raises(TimeoutError):
                result.result(timeout=0.1)
        finally:
            release.set()
        assert result.result(timeout=3).status_code==201
    app.extensions['studio_jobs'].join()
    assert client.get('/api/jobs/'+job['id']).json['status']=='done'


def test_pmax_requires_one_very_short_headline_warning(studio):
    app,store,client,headers,brand,campaign=studio
    item=[dict(name='pmax.jpg',format_id='pmax_1200x628',width=1200,height=628,variant='A',template='split')]
    result=export(client,headers,campaign,raw=image_bytes((1200,628)),manifest=item,texts={
        'headlines':['Sprzęt do pracy w biurze','Laptopy gotowe do pracy','Komputery dla Twojej firmy'],
        'descriptions':['Pierwszy opis','Drugi opis'],'long_headline':'Komputery do biura','business_name':'AMSO'})
    assert result.status_code==201
    assert any('15 znaków' in warning for warning in result.json['warnings'])
