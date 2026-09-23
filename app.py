"""Internal creative studio; entry point: waitress-serve --call app:create_app."""
import argparse
import csv
import hmac
import io
import json
import math
import os
import queue
import re
import secrets
import threading
import time
import tempfile
import warnings
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from flask import Flask, Request, g, jsonify, render_template, request, send_file, session
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from storage import ApiError, Storage, now_iso
from template_library import MAX_TEMPLATES, encode_recipe

MIB = 1024 * 1024
MAX_UPLOAD, MAX_PIXELS, MAX_STATE, MAX_ASSETS = 12*MIB, 20_000_000, 512*1024, 60
MAX_SOURCE_PIXELS = 60_000_000
METADATA_MARGIN = 64*1024
Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS
FORMATS = {}
for profile, sizes in {
    'display': [(300,250),(336,280),(728,90),(970,90),(970,250),(160,600),(300,600),(320,50),(320,100),(750,100),(750,200),(750,300)],
    'rda': [(1200,628),(1200,1200)], 'pmax': [(1200,628),(1200,1200),(960,1200)],
    'logos': [(1200,1200),(1200,300)],
}.items():
    FORMATS[profile] = [dict(id=f"{'logo' if profile=='logos' else profile}_{w}x{h}",
        label=f"{dict(display='Display',rda='Responsive Display',pmax='Performance Max',logos='Logo')[profile]} {w} × {h}",
        width=w, height=h, max_bytes=150*1024 if profile=='display' else 5*MIB, profile=profile) for w,h in sizes]
FORMAT_BY_ID = {f['id']:f for group in FORMATS.values() for f in group}


def identifier():
    return secrets.token_hex(12)


def text_field(value, label, limit, required=False):
    if not isinstance(value,str) or len(value)>limit or '\x00' in value:
        raise ApiError(f'Pole „{label}” ma nieprawidłową wartość (maks. {limit} znaków).')
    value=value.strip()
    if required and not value:
        raise ApiError(f'Uzupełnij pole „{label}”.')
    return value


def password_hash(password):
    if not isinstance(password,str) or not 12<=len(password)<=128:
        raise ApiError('Hasło musi mieć od 12 do 128 znaków.')
    return generate_password_hash(password)


def safe_csv(rows):
    output=io.StringIO(newline='')
    writer=csv.writer(output)
    for row in rows:
        clean=[]
        for value in row:
            value=str(value if value is not None else '')
            if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')):
                value="'"+value
            clean.append(value)
        writer.writerow(clean)
    return output.getvalue().encode('utf-8-sig')


def decode_image(raw, sanitize=True):
    if sanitize and raw.lstrip().startswith((b'<',b'\xef\xbb\xbf',b'\xff\xfe',b'\xfe\xff',b'\x00\x00\xfe\xff')):
        from svg_media import sanitize_svg
        return sanitize_svg(raw,raster_decoder=decode_image)
    pixel_limit=MAX_SOURCE_PIXELS if sanitize else MAX_PIXELS

    def dimension_error():
        return ApiError(f'Obraz przekracza limit {pixel_limit//1_000_000} megapikseli. '
            'Zmniejsz jego rozdzielczość i prześlij ponownie.',code='image_dimensions')

    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                fmt=image.format
                if fmt not in ('JPEG','PNG','WEBP') or getattr(image,'n_frames',1)!=1:
                    raise ApiError('Prześlij pojedynczy obraz JPG, PNG lub WebP.')
                pixels=image.width*image.height
                if pixels>pixel_limit:
                    raise dimension_error()
                image.load()
                if not sanitize:
                    return image.size,fmt
                alpha=image.mode in ('RGBA','LA') or 'transparency' in image.info
                mode='RGBA' if alpha else 'RGB'
                if image.mode!=mode:
                    image=image.convert(mode)
                if pixels>MAX_PIXELS:
                    scale=(MAX_PIXELS/pixels)**.5
                    width=max(1,min(MAX_PIXELS,int(image.width*scale)))
                    height=max(1,min(MAX_PIXELS//width,int(image.height*scale)))
                    image.thumbnail((width,height),Image.Resampling.LANCZOS,reducing_gap=3.0)
                # Resize before rotating to avoid another full-resolution copy on the VM.
                ImageOps.exif_transpose(image,in_place=True)
                output=io.BytesIO()
                image.save(output,format='PNG' if alpha else 'JPEG',**({} if alpha else {'quality':95,'optimize':True}))
                return output.getvalue(),image.width,image.height,'png' if alpha else 'jpg'
    except (Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise dimension_error() from exc
    except (UnidentifiedImageError,OSError,ValueError) as exc:
        raise ApiError('Nie można odczytać obrazu. Plik może być uszkodzony. '
            'Zapisz go ponownie jako JPG, PNG lub WebP i spróbuj jeszcze raz.',code='image_decode') from exc


def create_app(config=None):
    app=Flask(__name__)
    app.config.update(DATA_DIR=os.environ.get('ADS_DATA_DIR',str(Path(__file__).parent/'instance')),
        QUOTA_BYTES=int(os.environ.get('ADS_QUOTA_BYTES',512*MIB)),
        RESERVE_BYTES=int(os.environ.get('ADS_RESERVE_BYTES',256*MIB)),
        MAX_CONTENT_LENGTH=82*MIB, MAX_FORM_MEMORY_SIZE=MIB, MAX_FORM_PARTS=120,
        SESSION_COOKIE_NAME='ads_studio', SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('ADS_COOKIE_SECURE','0')=='1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12), START_CLEANUP_THREAD=True, RECOVER_JOBS=True)
    if os.environ.get('ADS_TRUSTED_HOSTS'):
        app.config['TRUSTED_HOSTS']=[x.strip() for x in os.environ['ADS_TRUSTED_HOSTS'].split(',') if x.strip()]
    if config:
        app.config.update(config)
    store=Storage(app.config['DATA_DIR'],app.config['QUOTA_BYTES'],app.config['RESERVE_BYTES'],recover=app.config['RECOVER_JOBS'])
    app.secret_key=app.config.get('SECRET_KEY') or store.secret()
    app.extensions['studio_storage']=store
    processing_lock=threading.RLock()
    app.extensions['studio_processing_lock']=processing_lock

    def decode_media(raw,sanitize=True):
        with processing_lock:
            return decode_image(raw,sanitize=sanitize)
    class LimitedUploadStream:
        """Account for transport staging as it is written, before image decoding."""
        def __init__(self):
            with store.lock:
                self.file=tempfile.NamedTemporaryFile(mode='w+b',prefix='upload-',dir=store.temp,delete=True)

        def write(self,data):
            with store.lock:
                store.ensure_capacity(len(data))
                result=self.file.write(data)
                self.file.flush()
                return result

        def close(self):
            with store.lock:
                self.file.close()

        def __getattr__(self,name):
            return getattr(self.file,name)

    class StudioRequest(Request):
        def _get_file_stream(self,total_content_length,content_type,filename=None,content_length=None):
            stream=LimitedUploadStream()
            g.upload_streams.append(stream)
            return stream

    app.request_class=StudioRequest
    jobs=queue.Queue(maxsize=8)
    thread_lock=threading.Lock()
    worker=None
    login_attempts={}
    login_lock=threading.Lock()
    dummy_hash=generate_password_hash(secrets.token_hex(24))

    def public_user(row):
        return {k:row[k] for k in ('id','username','role','active','created_at')}

    def csrf():
        if 'csrf' not in session:
            session['csrf']=secrets.token_urlsafe(32)
        return session['csrf']

    @app.before_request
    def protect_request():
        g.upload_streams=[]
        store.cleanup()
        g.user=None
        if session.get('user_id'):
            with store.db() as db:
                user=db.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
            if user and user['active'] and user['auth_version']==session.get('auth_version'):
                g.user=user
            else:
                session.clear()
        if request.path.startswith('/api/'):
            if request.method not in ('GET','HEAD','OPTIONS'):
                token=request.headers.get('X-CSRF-Token','')
                if not session.get('csrf') or not hmac.compare_digest(token.encode(),session['csrf'].encode()):
                    raise ApiError('Sesja formularza wygasła. Odśwież stronę i spróbuj ponownie.',403,code='csrf')
            if request.path not in ('/api/session','/api/login') and not g.user:
                raise ApiError('Zaloguj się ponownie, aby kontynuować.',401)
            if request.is_json and request.content_length and request.content_length>MIB:
                raise ApiError('Dane formularza są zbyt duże.',413)

    @app.teardown_request
    def close_uploads(error):
        for stream in g.get('upload_streams',[]):
            stream.close()

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['X-Frame-Options']='DENY'
        response.headers.setdefault('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; font-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        if request.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        return response

    @app.errorhandler(ApiError)
    def api_error(exc):
        return jsonify(error=exc.message,**exc.details),exc.status

    @app.errorhandler(HTTPException)
    def http_error(exc):
        messages={400:'Nieprawidłowe dane żądania.',404:'Nie znaleziono zasobu.',405:'Ta operacja nie jest dostępna.',
            413:'Przekroczono maksymalny rozmiar przesyłanych danych.',415:'Prześlij dane w formacie JSON.'}
        return jsonify(error=messages.get(exc.code,'Nie udało się wykonać żądania.')),exc.code

    @app.errorhandler(Exception)
    def unexpected_error(exc):
        app.logger.exception('Unhandled application error')
        return jsonify(error='Wystąpił błąd serwera. Spróbuj ponownie.'),500

    def require_admin():
        if not g.user or g.user['role']!='admin':
            raise ApiError('Ta operacja wymaga uprawnień administratora.',403)

    def payload():
        try:
            value=request.get_json()
        except RecursionError as exc:
            raise ApiError('Struktura formularza jest zbyt złożona.') from exc
        if not isinstance(value,dict):
            raise ApiError('Dane muszą być obiektem JSON.')
        return value

    def get_campaign(db,campaign_id,live=False):
        row=db.execute('SELECT c.*,u.username AS creator_name,v.username AS updater_name FROM campaigns c JOIN users u ON c.created_by=u.id JOIN users v ON c.updated_by=v.id WHERE c.id=?',(campaign_id,)).fetchone()
        if not row:
            raise ApiError('Nie znaleziono kampanii.',404)
        if live and row['expires_at']<=now_iso():
            raise ApiError('Pliki tej kampanii wygasły. Skopiuj kampanię i prześlij materiały ponownie.',410)
        return row

    def get_asset(db,asset_id,live=False):
        if not isinstance(asset_id,str):
            raise ApiError('Nieprawidłowy identyfikator pliku.')
        row=db.execute('SELECT * FROM assets WHERE id=?',(asset_id,)).fetchone()
        if not row:
            raise ApiError('Nie znaleziono pliku.',404)
        if live:
            if row['campaign_id']:
                get_campaign(db,row['campaign_id'],live=True)
            if row['expired']:
                raise ApiError('Ten plik wygasł i został usunięty.',410)
        return row

    def asset_json(row):
        result={k:row[k] for k in ('id','name','kind','mime','width','height','size','parent_id','campaign_id','brand_id','created_at')}
        result.update(url=f"/api/assets/{row['id']}/file",expired=bool(row['expired']))
        return result

    def export_json(row):
        return dict(id=row['id'],url=f"/api/exports/{row['id']}/download",filename=row['filename'],size=row['size'],
            file_count=row['file_count'],created_at=row['created_at'],expires_at=row['expires_at'],
            expired=bool(row['expired']) or row['expires_at']<=now_iso())

    def brand_json(row):
        data=dict(row)
        data['logo_url']=f"/api/assets/{row['logo_asset_id']}/file" if row['logo_asset_id'] else None
        data['font_url']=f"/api/assets/{row['font_asset_id']}/file" if row['font_asset_id'] else None
        return data

    def campaign_json(db,row,full=True):
        data=dict(row)
        data['state']=json.loads(data['state'])
        data['expired']=data['expires_at']<=now_iso()
        if full:
            data['assets']=[asset_json(a) for a in db.execute('SELECT * FROM assets WHERE campaign_id=? ORDER BY created_at,id',(row['id'],))]
            data['exports']=[export_json(e) for e in db.execute('SELECT * FROM exports WHERE campaign_id=? ORDER BY created_at DESC',(row['id'],))]
        else:
            data['state']={'confirmed':data['state'].get('confirmed') is True}
        return data

    def validate_state(state,campaign_id=None):
        if not isinstance(state,dict):
            raise ApiError('Stan kampanii musi być obiektem JSON.')
        try:
            encoded=json.dumps(state,ensure_ascii=False,allow_nan=False)
        except (ValueError,TypeError,RecursionError) as exc:
            raise ApiError('Stan kampanii zawiera nieprawidłowe wartości.') from exc
        if len(encoded.encode())>MAX_STATE:
            raise ApiError('Projekt jest zbyt duży. Ogranicz liczbę zapisanych formatów i warstw.')
        # Only files that still exist in this app may be referenced; deleted or
        # expired uploads must not come back through saves or version restores.
        existing=set()
        if campaign_id:
            with store.db() as db:
                existing={a['id'] for a in db.execute('SELECT id FROM assets')}
            referenced=[]
            def collect(node):
                if isinstance(node,dict):
                    for key,val in node.items():
                        if isinstance(val,str):
                            if (key in ('asset_id','parent_id') or key.endswith('_asset_id')) and val:
                                referenced.append(val)
                            elif key in ('src','url','originalUrl','cutoutUrl') and val.startswith('/api/assets/'):
                                stem=val.split('?')[0][len('/api/assets/'):-len('/file')]
                                if stem:
                                    referenced.append(stem)
                        elif isinstance(val,list) and key.endswith('_asset_ids'):
                            referenced.extend(item for item in val if isinstance(item,str) and item)
                    for val in node.values():
                        collect(val)
                elif isinstance(node,list):
                    for val in node:
                        collect(val)
            collect(state)
            if any(value not in existing for value in referenced):
                raise ApiError('Projekt odwołuje się do pliku, którego już nie ma w aplikacji. '
                    'Usuń warstwy z niedostępnymi plikami lub wczytaj najnowszą wersję kampanii.',code='asset_unavailable')
        def walk(node,depth=0):
            if depth>30:
                raise ApiError('Struktura projektu jest zbyt złożona.')
            if isinstance(node,dict):
                if node.get('type')=='rect' and node.get('role')=='shape':
                    validate_shape_layer(node)
                for key,val in node.items():
                    if key in ('src','url','originalUrl','cutoutUrl') and val not in (None,''):
                        if not isinstance(val,str) or not re.fullmatch(r'/api/assets/[a-f0-9]{24}/file(?:\?download=1)?',val):
                            raise ApiError('Projekt może używać tylko plików przesłanych do aplikacji.')
                    walk(val,depth+1)
            elif isinstance(node,list):
                for val in node:
                    walk(val,depth+1)
        walk(state)
        return encoded

    def validate_shape_layer(layer):
        """Native shape layers carry bounded geometry and style only — never
        executable content or file references. Unsupported payloads fail the
        whole save without damaging stored work (validated before any write)."""
        if layer.get('shape') not in ('rectangle','square','circle','ellipse','triangle','diamond'):
            raise ApiError('Kształt musi być jednym z: prostokąt, kwadrat, koło, elipsa, trójkąt, romb.')
        for key in ('x','y'):
            value=layer.get(key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not -16<=value<=16:
                raise ApiError('Geometria kształtu jest nieprawidłowa.')
        for key in ('w','h'):
            value=layer.get(key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=16:
                raise ApiError('Geometria kształtu jest nieprawidłowa.')
        opacity=layer.get('opacity',1)
        if isinstance(opacity,bool) or not isinstance(opacity,(int,float)) or not math.isfinite(opacity) or not 0<=opacity<=1:
            raise ApiError('Przezroczystość kształtu jest nieprawidłowa.')
        radius=layer.get('radius',0)
        if isinstance(radius,bool) or not isinstance(radius,(int,float)) or not math.isfinite(radius) or not 0<=radius<=0.5:
            raise ApiError('Zaokrąglenie kształtu jest nieprawidłowe.')
        for key in ('color',):
            value=layer.get(key)
            if value is None:
                continue
            if not isinstance(value,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',value):
                raise ApiError('Kolor kształtu musi być zapisany w formacie #RRGGBB.')
        for key in ('src','asset_id','url','originalUrl','cutoutUrl','slot','fit','cropX','cropY'):
            if key in layer and layer[key] not in (None,''):
                raise ApiError('Kształt nie może odwoływać się do plików ani materiałów.')

    def validate_campaign(data,current=None,campaign_id=None):
        name=text_field(data.get('name',current['name'] if current else ''),'Nazwa kampanii',120,True)
        brief=text_field(data.get('brief',current['brief'] if current else ''),'Brief',12000)
        brand_id=data.get('brand_id',current['brand_id'] if current else None)
        if not isinstance(brand_id,str):
            raise ApiError('Wybierz Brand Kit kampanii.')
        state=validate_state(data.get('state',json.loads(current['state']) if current else {}),campaign_id=campaign_id or (current['id'] if current else None))
        return name,brand_id,brief,state

    def revision(db,row,author_id):
        db.execute('INSERT INTO versions(campaign_id,version,name,brand_id,brief,state,author_id,created_at) VALUES(?,?,?,?,?,?,?,?)',
            (row['id'],row['version'],row['name'],row['brand_id'],row['brief'],row['state'],author_id,row['updated_at']))

    def check_version(current,value):
        if isinstance(value,str) and value.isdigit():
            value=int(value)
        if isinstance(value,bool) or value!=current['version']:
            raise ApiError('Kampania została zmieniona przez inną osobę. Wczytaj najnowszą wersję przed zapisaniem.',409,current_version=current['version'])

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/api/session')
    def session_info():
        return jsonify(user=public_user(g.user) if g.user else None,csrf_token=csrf())

    @app.post('/api/login')
    def login():
        data=payload()
        username=text_field(data.get('username',''),'Login',80,True)
        password=data.get('password','')
        if not isinstance(password,str) or len(password)>128:
            raise ApiError('Nieprawidłowy login lub hasło.',401)
        ip=request.remote_addr or 'unknown'
        keys=('ip:'+ip,'user:'+username.casefold())
        clock=time.monotonic()
        with login_lock:
            for key in list(login_attempts):
                login_attempts[key]=[x for x in login_attempts[key] if clock-x<900]
                if not login_attempts[key]:
                    del login_attempts[key]
            if any(len(login_attempts.get(k,[]))>=(30 if k.startswith('ip:') else 8) for k in keys):
                raise ApiError('Zbyt wiele nieudanych prób logowania. Spróbuj ponownie za 15 minut.',429)
        with store.db() as db:
            user=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        valid=check_password_hash(user['password_hash'] if user else dummy_hash,password)
        if not valid or not user or not user['active']:
            with login_lock:
                for key in keys:
                    login_attempts.setdefault(key,[]).append(clock)
            raise ApiError('Nieprawidłowy login lub hasło.',401)
        with login_lock:
            login_attempts.pop(keys[1],None)
        session.clear()
        session.update(user_id=user['id'],auth_version=user['auth_version'])
        session.permanent=True
        return jsonify(user=public_user(user),csrf_token=csrf())

    @app.post('/api/logout')
    def logout():
        session.clear()
        return jsonify(user=None,csrf_token=csrf())

    @app.post('/api/account/password')
    def change_password():
        data=payload()
        old=data.get('current_password','')
        if not isinstance(old,str) or not check_password_hash(g.user['password_hash'],old):
            raise ApiError('Obecne hasło jest nieprawidłowe.')
        hashed=password_hash(data.get('password'))
        with store.lock,store.db() as db:
            store.ensure_capacity(METADATA_MARGIN)
            db.execute('UPDATE users SET password_hash=?,auth_version=auth_version+1 WHERE id=?',(hashed,g.user['id']))
            session['auth_version']=db.execute('SELECT auth_version FROM users WHERE id=?',(g.user['id'],)).fetchone()[0]
        return jsonify(ok=True)

    @app.get('/api/users')
    def list_users():
        require_admin()
        with store.db() as db:
            return jsonify(items=[public_user(u) for u in db.execute('SELECT * FROM users ORDER BY username')])

    @app.post('/api/users')
    def add_user():
        require_admin()
        data=payload()
        username=text_field(data.get('username',''),'Login',80,True)
        if not re.fullmatch(r'[\w.@+-]{3,80}',username):
            raise ApiError('Login musi mieć 3–80 znaków: litery, cyfry, kropki, @, +, - lub _.')
        role=data.get('role','editor')
        if role not in ('editor','admin'):
            raise ApiError('Wybierz rolę administratora lub redaktora.')
        hashed=password_hash(data.get('password'))
        with store.lock,store.db() as db:
            store.ensure_capacity(METADATA_MARGIN)
            if db.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone():
                raise ApiError('Ten login jest już zajęty.',409)
            cur=db.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)',(username,hashed,role,now_iso()))
            return jsonify(public_user(db.execute('SELECT * FROM users WHERE id=?',(cur.lastrowid,)).fetchone())),201

    @app.put('/api/users/<int:user_id>')
    def update_user(user_id):
        require_admin()
        data=payload()
        hashed=password_hash(data['password']) if data.get('password') else None
        with store.lock,store.db() as db:
            store.ensure_capacity(METADATA_MARGIN)
            user=db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
            if not user:
                raise ApiError('Nie znaleziono użytkownika.',404)
            role,active=data.get('role',user['role']),data.get('active',bool(user['active']))
            if role not in ('editor','admin') or not isinstance(active,bool):
                raise ApiError('Nieprawidłowe uprawnienia użytkownika.')
            if user['role']=='admin' and user['active'] and (role!='admin' or not active):
                if db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<=1:
                    raise ApiError('Nie można wyłączyć ani zmienić roli ostatniego aktywnego administratora.',409)
            changed=hashed is not None or role!=user['role'] or active!=bool(user['active'])
            db.execute('UPDATE users SET role=?,active=?,password_hash=?,auth_version=auth_version+? WHERE id=?',
                (role,int(active),hashed or user['password_hash'],int(changed),user_id))
            return jsonify(public_user(db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()))

    @app.get('/api/brands')
    def list_brands():
        with store.db() as db:
            return jsonify(items=[brand_json(b) for b in db.execute('SELECT * FROM brands ORDER BY name')])

    @app.route('/api/brands',methods=['POST'])
    @app.route('/api/brands/<brand_id>',methods=['PUT'])
    def save_brand(brand_id=None):
        require_admin()
        data=payload()
        with store.lock,store.db() as db:
            store.ensure_capacity(METADATA_MARGIN)
            old=db.execute('SELECT * FROM brands WHERE id=?',(brand_id,)).fetchone() if brand_id else None
            if brand_id and not old:
                raise ApiError('Nie znaleziono Brand Kitu.',404)
            values=dict(old) if old else dict(name='',color='#E76A25',secondary_color='#F4F1EC',text_color='#182021',font_family='Arial',tone='',logo_asset_id=None,font_asset_id=None)
            fields=('name','color','secondary_color','text_color','font_family','tone','logo_asset_id','font_asset_id')
            for key in fields:
                if key in data:
                    values[key]=data[key]
            values['name']=text_field(values['name'],'Nazwa marki',100,True)
            values['font_family']=text_field(values['font_family'],'Czcionka',100,True)
            values['tone']=text_field(values['tone'],'Zasady komunikacji',4000)
            for key in ('color','secondary_color','text_color'):
                if not isinstance(values[key],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',values[key]):
                    raise ApiError('Kolory muszą mieć format #RRGGBB.')
            for key,kind in (('logo_asset_id','logo'),('font_asset_id','font')):
                if values[key]:
                    asset=get_asset(db,values[key],live=True)
                    if asset['brand_id']!=brand_id or asset['kind']!=kind:
                        raise ApiError('Plik nie należy do tego Brand Kitu.')
            stamp=now_iso()
            brand_id=brand_id or identifier()
            params=[values[k] for k in fields]
            if old:
                db.execute('UPDATE brands SET name=?,color=?,secondary_color=?,text_color=?,font_family=?,tone=?,logo_asset_id=?,font_asset_id=?,updated_at=? WHERE id=?',(*params,stamp,brand_id))
            else:
                db.execute('INSERT INTO brands(name,color,secondary_color,text_color,font_family,tone,logo_asset_id,font_asset_id,created_at,updated_at,id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(*params,stamp,stamp,brand_id))
            return jsonify(brand_json(db.execute('SELECT * FROM brands WHERE id=?',(brand_id,)).fetchone())),200 if old else 201

    @app.get('/api/campaigns')
    def list_campaigns():
        with store.db() as db:
            rows=db.execute('SELECT c.*,u.username AS creator_name,v.username AS updater_name FROM campaigns c JOIN users u ON c.created_by=u.id JOIN users v ON c.updated_by=v.id ORDER BY updated_at DESC LIMIT 1000')
            return jsonify(items=[campaign_json(db,c,full=False) for c in rows])

    def template_json(row):
        return dict(id=row['id'], name=row['name'], recipe=json.loads(row['recipe']),
                    created_by=row['created_by'], author_name=row['author_name'],
                    created_at=row['created_at'], archived=bool(row['archived']),
                    can_manage=g.user['role']=='admin' or row['created_by']==g.user['id'])

    def template_row(db, template_id):
        row=db.execute('SELECT t.*,u.username AS author_name FROM shared_templates t JOIN users u ON u.id=t.created_by WHERE t.id=?',
                       (template_id,)).fetchone()
        if not row:
            raise ApiError('Nie znaleziono szablonu.',404)
        return row

    @app.get('/api/templates')
    def list_templates():
        include_archived=request.args.get('include_archived')=='1'
        with store.db() as db:
            rows=db.execute('SELECT t.*,u.username AS author_name FROM shared_templates t JOIN users u ON u.id=t.created_by '
                            'WHERE (? OR t.archived=0) ORDER BY t.created_at DESC,t.id', (int(include_archived),))
            return jsonify(items=[template_json(row) for row in rows])

    @app.post('/api/templates')
    def save_template():
        data=payload()
        if set(data)!={'name','recipe'}:
            raise ApiError('Podaj nazwę i układ szablonu.')
        name=text_field(data['name'],'Nazwa szablonu',100,True)
        if any(ord(char)<32 for char in name):
            raise ApiError('Nazwa szablonu nie może zawierać znaków sterujących.')
        try:
            name.encode('utf-8')
        except UnicodeError as exc:
            raise ApiError('Nazwa szablonu zawiera nieprawidłowy znak.') from exc
        recipe=encode_recipe(data['recipe'],FORMAT_BY_ID)
        with store.lock,store.db() as db:
            # The limit includes archived entries: archiving does not delete a recipe.
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM shared_templates').fetchone()[0]>=MAX_TEMPLATES:
                raise ApiError('Biblioteka osiągnęła limit 100 zapisanych szablonów, łącznie z archiwum. Skontaktuj się z administratorem.',
                               409,code='template_library_full')
            store.ensure_capacity(len(recipe.encode('utf-8'))*2+METADATA_MARGIN)
            template_id=identifier()
            db.execute('INSERT INTO shared_templates(id,name,recipe,created_by,created_at) VALUES(?,?,?,?,?)',
                       (template_id,name,recipe,g.user['id'],now_iso()))
            return jsonify(template_json(template_row(db,template_id))),201

    @app.patch('/api/templates/<template_id>')
    def archive_template(template_id):
        data=payload()
        if set(data)!={'archived'} or not isinstance(data['archived'],bool):
            raise ApiError('Podaj stan archiwizacji szablonu.')
        with store.lock,store.db() as db:
            row=template_row(db,template_id)
            if g.user['role']!='admin' and row['created_by']!=g.user['id']:
                raise ApiError('Szablon może archiwizować lub przywrócić jego autor albo administrator.',403)
            if bool(row['archived'])!=data['archived']:
                store.ensure_capacity(METADATA_MARGIN)
                db.execute('UPDATE shared_templates SET archived=? WHERE id=?',(int(data['archived']),template_id))
            return jsonify(template_json(template_row(db,template_id)))

    def new_campaign(db,name,brand_id,brief,state):
        if not db.execute('SELECT id FROM brands WHERE id=?',(brand_id,)).fetchone():
            raise ApiError('Wybierz istniejący Brand Kit.')
        store.ensure_capacity(len(state.encode())*2+METADATA_MARGIN)
        stamp=now_iso()
        expiry=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(timespec='seconds')
        campaign_id=identifier()
        db.execute('INSERT INTO campaigns VALUES(?,?,?,?,?,?,?,?,?,?,?)',(campaign_id,name,brand_id,brief,state,1,stamp,stamp,expiry,g.user['id'],g.user['id']))
        row=get_campaign(db,campaign_id)
        revision(db,row,g.user['id'])
        return campaign_json(db,row)

    @app.post('/api/campaigns')
    def create_campaign():
        data=payload()
        with store.lock,store.db() as db:
            return jsonify(new_campaign(db,*validate_campaign(data))),201

    @app.get('/api/campaigns/<campaign_id>')
    def read_campaign(campaign_id):
        with store.db() as db:
            return jsonify(campaign_json(db,get_campaign(db,campaign_id)))

    @app.put('/api/campaigns/<campaign_id>')
    def update_campaign(campaign_id):
        data=payload()
        with store.lock,store.db() as db:
            current=get_campaign(db,campaign_id)
            check_version(current,data.get('version'))
            name,brand_id,brief,state=validate_campaign(data,current,campaign_id)
            if not db.execute('SELECT id FROM brands WHERE id=?',(brand_id,)).fetchone():
                raise ApiError('Wybierz istniejący Brand Kit.')
            store.ensure_capacity(len(state.encode())*2+METADATA_MARGIN)
            db.execute('UPDATE campaigns SET name=?,brand_id=?,brief=?,state=?,version=version+1,updated_at=?,updated_by=? WHERE id=?',(name,brand_id,brief,state,now_iso(),g.user['id'],campaign_id))
            row=get_campaign(db,campaign_id)
            revision(db,row,g.user['id'])
            return jsonify(campaign_json(db,row))

    def campaign_descendant_ids(db,asset_id):
        """Live asset ids in the subtree rooted at the given asset (every derived generation).

        The frontier stops at expired rows: their bytes are gone, there is nothing
        left to delete below them, and the cascade must not resurrect them.
        """
        seen={asset_id}
        frontier=[asset_id]
        while frontier:
            placeholders=','.join('?' for _ in frontier)
            rows=db.execute(f'SELECT id FROM assets WHERE parent_id IN ({placeholders}) AND expired=0',frontier).fetchall()
            frontier=[row['id'] for row in rows if row['id'] not in seen]
            seen.update(frontier)
        return seen

    @app.delete('/api/campaigns/<campaign_id>/assets/<asset_id>')
    def delete_campaign_asset(campaign_id,asset_id):
        """Delete a campaign file and its confirmed derived subtree, reconciling every saved composition.

        A single file needs no extra confirmation; deleting undisclosed
        descendants requires the client to confirm the exact affected set, and
        the server rechecks it against the live subtree before destroying bytes.
        """
        data=payload() if request.is_json else {}
        if data and not isinstance(data.get('version'),(int,str)) or isinstance(data.get('version'),bool):
            raise ApiError('Nieprawidłowy numer wersji kampanii.')
        confirmed=data.get('confirmed_asset_ids')
        if confirmed is not None and (not isinstance(confirmed,list) or
                                      any(not isinstance(item,str) for item in confirmed)):
            raise ApiError('Lista potwierdzonych plików musi być listą identyfikatorów.')
        # store.lock serializes this against job enqueueing and the worker's
        # final persist phase, so no in-flight job can recreate deleted output.
        with store.lock,store.db() as db:
            campaign=get_campaign(db,campaign_id,live=True)
            check_version(campaign,data.get('version'))
            asset=get_asset(db,asset_id)
            if asset['campaign_id']!=campaign_id or not asset['campaign_id']:
                raise ApiError('Ten plik nie należy do tej kampanii.',404)
            if asset['brand_id']:
                raise ApiError('Pliki Brand Kit usuwa administrator w Brand Kit.',400)
            if asset['expired']:
                raise ApiError('Ten plik już wygasł i został usunięty.',410)
            descendants=campaign_descendant_ids(db,asset_id)
            # Finished jobs may have produced derived files after the impact was
            # confirmed; live outputs join the required set, so a stale
            # confirmation is refreshed instead of deleting undisclosed files.
            placeholders=','.join('?' for _ in descendants)
            live_outputs={row['output_asset_id'] for row in db.execute(
                f"SELECT DISTINCT output_asset_id FROM jobs WHERE asset_id IN ({placeholders}) AND status='done' "
                'AND output_asset_id IS NOT NULL',tuple(descendants))}
            live_outputs.intersection_update({row['id'] for row in db.execute('SELECT id FROM assets')})
            merged=descendants|live_outputs
            if len(merged)>1:
                # Undisclosed cascade requires an explicit, exact confirmation.
                if not isinstance(confirmed,list):
                    raise ApiError('Ten plik ma pliki pochodne (np. wycięcie tła). '
                        'Usuń najpierw te pliki; ich lista jest widoczna w potwierdzeniu usunięcia.',409,code='descendants')
                required=sorted(merged)
                if sorted(confirmed)!=required:
                    raise ApiError('Zakres usunięcia zmienił się od potwierdzenia. '
                        'Odśwież podgląd i potwierdź ponownie.',409,code='impact_changed',
                        required_asset_ids=required)
            # Any active job over the whole affected set blocks the deletion;
            # the worker re-verifies sources under store.lock.
            active=db.execute(f'SELECT id FROM jobs WHERE asset_id IN ({placeholders}) AND status IN (\'queued\',\'running\')',
                              tuple(descendants)).fetchone()
            if active:
                raise ApiError('Poczekaj na zakończenie przetwarzania tego pliku.',409,code='job_active')
            delete_ids=sorted(descendants)
            state=json.loads(campaign['state'])
            strip_media(state,delete_ids)
            encoded=json.dumps(state,ensure_ascii=False)
            if len(encoded.encode())>MAX_STATE:
                raise ApiError('Projekt po usunięciu plików jest zbyt duży. Ogranicz liczbę zapisanych formatów.',413)
            store.ensure_capacity(len(encoded.encode())+METADATA_MARGIN)
            paths={row['id']:row['path'] for row in db.execute(
                f'SELECT id,path FROM assets WHERE id IN ({placeholders})',tuple(descendants))}
            if any(not store.path(paths[asset_id]).is_file() for asset_id in delete_ids):
                raise ApiError('Plik nie jest już dostępny. Odśwież listę materiałów.',410,code='file_gone')
            for asset_id in delete_ids:
                store.path(paths[asset_id]).unlink()
                db.execute('DELETE FROM jobs WHERE asset_id=?',(asset_id,))
                db.execute('DELETE FROM assets WHERE id=?',(asset_id,))
            db.execute('UPDATE campaigns SET state=?,version=version+1,updated_at=?,updated_by=? WHERE id=?',
                (encoded,now_iso(),g.user['id'],campaign_id))
            row=get_campaign(db,campaign_id)
            revision(db,row,g.user['id'])
            return jsonify(ok=True,deleted_ids=delete_ids,version=row['version'],
                updated_at=row['updated_at'],updated_by=g.user['id'])

    @app.get('/api/campaigns/<campaign_id>/versions')
    def versions(campaign_id):
        with store.db() as db:
            get_campaign(db,campaign_id)
            items=[]
            for row in db.execute('SELECT v.*,u.username AS author FROM versions v JOIN users u ON u.id=v.author_id WHERE campaign_id=? ORDER BY version DESC',(campaign_id,)):
                item=dict(row)
                item['state']=json.loads(item['state'])
                items.append(item)
            return jsonify(items=items)

    @app.post('/api/campaigns/<campaign_id>/versions/<int:old_version>/restore')
    def restore(campaign_id,old_version):
        data=payload()
        with store.lock,store.db() as db:
            current=get_campaign(db,campaign_id)
            check_version(current,data.get('version'))
            old=db.execute('SELECT * FROM versions WHERE campaign_id=? AND version=?',(campaign_id,old_version)).fetchone()
            if not old:
                raise ApiError('Nie znaleziono tej wersji kampanii.',404)
            # A historical revision must not resurrect files deleted after it was saved.
            reconciled=json.loads(old['state'])
            strip_media(reconciled,missing_asset_ids(db,reconciled))
            store.ensure_capacity(len(old['state'].encode())*2+METADATA_MARGIN)
            db.execute('UPDATE campaigns SET name=?,brand_id=?,brief=?,state=?,version=version+1,updated_at=?,updated_by=? WHERE id=?',
                (old['name'],old['brand_id'],old['brief'],json.dumps(reconciled,ensure_ascii=False),now_iso(),g.user['id'],campaign_id))
            row=get_campaign(db,campaign_id)
            revision(db,row,g.user['id'])
            return jsonify(campaign_json(db,row))

    def missing_asset_ids(db,state):
        """Asset ids referenced by the given state whose rows no longer exist."""
        known={a['id'] for a in db.execute('SELECT id FROM assets')}
        known_urls={f'/api/assets/{asset_id}/file' for asset_id in known}
        missing=set()
        def visit(node):
            if isinstance(node,dict):
                for key,val in node.items():
                    if isinstance(val,str) and (key in ('asset_id','parent_id') or key.endswith('_asset_id')) and val and val not in known:
                        missing.add(val)
                    elif isinstance(val,str) and key in ('src','url','originalUrl','cutoutUrl') and val.startswith('/api/assets/') and val.split('?')[0] not in known_urls:
                        stem=val.split('?')[0][len('/api/assets/'):-len('/file')]
                        if stem:
                            missing.add(stem)
                    elif isinstance(val,list) and key.endswith('_asset_ids'):
                        for item in val:
                            if isinstance(item,str) and item and item not in known:
                                missing.add(item)
                    elif isinstance(val,(dict,list)):
                        visit(val)
            elif isinstance(node,list):
                for item in node:
                    visit(item)
        visit(state)
        return missing

    def strip_media(state,ids):
        """Remove references to the given asset ids from a campaign state copy.

        Selections end in None/empties; composition layers lose their file
        reference but keep their geometry so no other image is substituted.
        """
        targets=set(ids)
        if not targets:
            return state
        urls={f'/api/assets/{asset_id}/file' for asset_id in targets}
        def clear(node):
            if isinstance(node,dict):
                for key,val in list(node.items()):
                    is_target_id=isinstance(val,str) and val in targets
                    is_target_url=isinstance(val,str) and val.split('?')[0] in urls
                    if key.endswith('_asset_ids') and isinstance(val,list):
                        node[key]=[item for item in val if not (isinstance(item,str) and item in targets)]
                        clear(node[key])
                    elif (key in ('asset_id','parent_id') or key.endswith('_asset_id')) and is_target_id:
                        node[key]=None
                    elif key in ('src','url','originalUrl','cutoutUrl') and is_target_url:
                        node[key]=None
                    else:
                        clear(val)
            elif isinstance(node,list):
                for val in node:
                    clear(val)
        clear(state)
        # Keep the legacy single-product mirror pointing at the first survivor,
        # matching the frontend normalizeState migration.
        if 'product_asset_ids' in state:
            ids=state.get('product_asset_ids')
            state['product_asset_id']=ids[0] if isinstance(ids,list) and ids else None
        return state

    @app.post('/api/campaigns/<campaign_id>/duplicate')
    def duplicate_campaign(campaign_id):
        with store.lock,store.db() as db:
            original=get_campaign(db,campaign_id)
            state=json.loads(original['state'])
            old_ids={a['id'] for a in db.execute('SELECT id FROM assets WHERE campaign_id=?',(campaign_id,))}
            strip_media(state,old_ids)
            state['confirmed']=False
            return jsonify(new_campaign(db,original['name'][:110]+' — kopia',original['brand_id'],original['brief'],validate_state(state))),201

    @app.delete('/api/campaigns/<campaign_id>')
    def delete_campaign(campaign_id):
        with store.lock,store.db() as db:
            get_campaign(db,campaign_id)
            if db.execute("SELECT id FROM jobs WHERE campaign_id=? AND status IN ('queued','running')",(campaign_id,)).fetchone():
                raise ApiError('Poczekaj na zakończenie przetwarzania przed usunięciem kampanii.',409)
            for row in db.execute('SELECT path FROM assets WHERE campaign_id=? UNION ALL SELECT path FROM exports WHERE campaign_id=?',(campaign_id,campaign_id)):
                store.path(row['path']).unlink(missing_ok=True)
            db.execute('DELETE FROM campaigns WHERE id=?',(campaign_id,))
        return jsonify(ok=True)

    def persist_asset(db,content,name,kind,ext,mime,width=None,height=None,campaign_id=None,brand_id=None,parent_id=None):
        asset_id=identifier()
        filename=f'{asset_id}.{ext}'
        store.ensure_capacity(len(content)+METADATA_MARGIN)
        store.write(filename,content)
        try:
            db.execute('INSERT INTO assets(id,name,kind,path,mime,width,height,size,campaign_id,brand_id,parent_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (asset_id,name,kind,filename,mime,width,height,len(content),campaign_id,brand_id,parent_id,now_iso()))
        except Exception:
            store.path(filename).unlink(missing_ok=True)
            raise
        return asset_json(get_asset(db,asset_id))

    def read_upload():
        upload=request.files.get('file')
        if not upload or not upload.filename:
            raise ApiError('Wybierz plik do przesłania.')
        raw=upload.stream.read(MAX_UPLOAD+1)
        if not raw or len(raw)>MAX_UPLOAD:
            raise ApiError('Plik może mieć maksymalnie 12 MB.',413)
        name=Path(upload.filename.replace('\\','/')).name[:180]
        return raw,name

    @app.post('/api/campaigns/<campaign_id>/assets')
    def upload_campaign_asset(campaign_id):
        kind=request.form.get('kind','product')
        if kind not in ('product','background','cutout','element'):
            raise ApiError('Nieprawidłowy rodzaj obrazu.')
        raw,name=read_upload()
        content,width,height,ext=decode_media(raw)
        if len(content)>MAX_UPLOAD:
            raise ApiError('Obraz po przetworzeniu przekracza 12 MB. Zmniejsz jego rozdzielczość.',413)
        parent_id=request.form.get('parent_id') or None
        with store.lock,store.db() as db:
            get_campaign(db,campaign_id,live=True)
            if db.execute('SELECT COUNT(*) FROM assets WHERE campaign_id=? AND expired=0',(campaign_id,)).fetchone()[0]>=MAX_ASSETS:
                raise ApiError('Kampania może zawierać maksymalnie 60 plików.')
            if parent_id:
                parent=get_asset(db,parent_id,live=True)
                if parent['campaign_id']!=campaign_id:
                    raise ApiError('Oryginał musi należeć do tej samej kampanii.')
            return jsonify(persist_asset(db,content,name,kind,ext,{'svg':'image/svg+xml','png':'image/png','jpg':'image/jpeg'}[ext],
                width,height,campaign_id=campaign_id,parent_id=parent_id)),201

    @app.post('/api/brands/<brand_id>/assets')
    def upload_brand_asset(brand_id):
        require_admin()
        raw,name=read_upload()
        kind=request.form.get('kind')
        width=height=None
        if kind=='logo':
            content,width,height,ext=decode_media(raw)
            mime={'svg':'image/svg+xml','png':'image/png','jpg':'image/jpeg'}[ext]
            if len(content)>MAX_UPLOAD:
                raise ApiError('Logo po przetworzeniu przekracza 12 MB.',413)
        elif kind=='font':
            ext=Path(name).suffix.lower().lstrip('.')
            signatures={'ttf':(b'\x00\x01\x00\x00',b'true'),'otf':(b'OTTO',),'woff':(b'wOFF',),'woff2':(b'wOF2',)}
            if ext not in signatures or raw[:4] not in signatures[ext] or len(raw)<28 or len(raw)>5*MIB:
                raise ApiError('Prześlij poprawną czcionkę TTF, OTF, WOFF lub WOFF2 do 5 MB.')
            content=raw
            mime={'ttf':'font/ttf','otf':'font/otf','woff':'font/woff','woff2':'font/woff2'}[ext]
        else:
            raise ApiError('Wybierz logo albo czcionkę.')
        with store.lock,store.db() as db:
            if not db.execute('SELECT id FROM brands WHERE id=?',(brand_id,)).fetchone():
                raise ApiError('Nie znaleziono Brand Kitu.',404)
            if db.execute('SELECT COUNT(*) FROM assets WHERE brand_id=?',(brand_id,)).fetchone()[0]>=30:
                raise ApiError('Brand Kit osiągnął limit 30 zapisanych plików.')
            asset=persist_asset(db,content,name,kind,ext,mime,width,height,brand_id=brand_id)
            field='logo_asset_id' if kind=='logo' else 'font_asset_id'
            db.execute(f'UPDATE brands SET {field}=?,updated_at=? WHERE id=?',(asset['id'],now_iso(),brand_id))
            return jsonify(asset),201

    @app.get('/api/assets/<asset_id>/file')
    def asset_file(asset_id):
        with store.lock,store.db() as db:
            asset=get_asset(db,asset_id,live=True)
            path=store.path(asset['path'])
            if not path.is_file():
                raise ApiError('Plik nie jest już dostępny. Prześlij materiał ponownie.',410)
            name=asset['name']
            if asset['mime']=='image/svg+xml':
                name=Path(name).stem+'.svg'
            response=send_file(path,mimetype=asset['mime'],as_attachment=request.args.get('download')=='1',download_name=name,conditional=False)
            if asset['mime']=='image/svg+xml':
                response.headers['Content-Security-Policy']="sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            return response

    def job_json(db,row):
        if not row:
            raise ApiError('Nie znaleziono zadania przetwarzania.',404)
        data={k:row[k] for k in ('id','status','method','created_at','updated_at')}
        if row['error']:
            data['error']=row['error']
        if row['output_asset_id']:
            asset=db.execute('SELECT * FROM assets WHERE id=?',(row['output_asset_id'],)).fetchone()
            if asset:
                data['asset']=asset_json(asset)
        return data

    def process_jobs():
        while True:
            job_id=jobs.get()
            input_path=store.temp/f'{job_id}-input'
            output_path=store.temp/f'{job_id}-output.png'
            reservation=0
            try:
                with store.lock,store.db() as db:
                    job=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
                    if not job:
                        continue
                    asset=get_asset(db,job['asset_id'],live=True)
                    needed=asset['size']+asset['width']*asset['height']*4+MIB
                    store.ensure_capacity(needed)
                    reservation=needed
                    store.reserved_bytes+=reservation
                    input_path.write_bytes(store.path(asset['path']).read_bytes())
                    os.chmod(input_path,0o600)
                    db.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?",(now_iso(),job_id))
                if app.config.get('BACKGROUND_REMOVE'):
                    remove_background=app.config['BACKGROUND_REMOVE']
                else:
                    from background import remove_background
                with processing_lock:
                    remove_background(input_path,output_path,method=job['method'])
                    if not output_path.is_file() or output_path.stat().st_size>MAX_UPLOAD:
                        raise ApiError('Wynik usuwania tła jest zbyt duży. Zmniejsz rozdzielczość obrazu.')
                    content,width,height,ext=decode_media(output_path.read_bytes())
                if ext!='png':
                    raise ApiError('Usuwanie tła nie zwróciło obrazu z przezroczystością.')
                with store.lock,store.db() as db:
                    get_campaign(db,asset['campaign_id'],live=True)
                    # The source may have been deleted while the model ran; it
                    # must not come back as a derived file of a removed asset.
                    if not db.execute('SELECT id FROM assets WHERE id=?',(asset['id'],)).fetchone():
                        raise ApiError('Plik źródłowy został usunięty podczas przetwarzania. Wynik nie został zapisany.',409)
                    input_path.unlink(missing_ok=True)
                    output_path.unlink(missing_ok=True)
                    store.reserved_bytes-=reservation
                    reservation=0
                    if db.execute('SELECT COUNT(*) FROM assets WHERE campaign_id=? AND expired=0',(asset['campaign_id'],)).fetchone()[0]>=MAX_ASSETS:
                        raise ApiError('Kampania osiągnęła limit 60 plików.')
                    output_kind='element' if asset['kind']=='element' else 'cutout'
                    result=persist_asset(db,content,Path(asset['name']).stem+'-bez-tla.png',output_kind,'png','image/png',
                        width,height,campaign_id=asset['campaign_id'],parent_id=asset['id'])
                    db.execute("UPDATE jobs SET status='done',output_asset_id=?,updated_at=? WHERE id=?",(result['id'],now_iso(),job_id))
            except Exception as exc:
                app.logger.warning('Background removal failed (%s)',type(exc).__name__)
                message=exc.message if isinstance(exc,ApiError) else 'Nie udało się usunąć tła. Sprawdź zdjęcie lub spróbuj ponownie; administrator może sprawdzić dostępność modelu.'
                if isinstance(exc,ValueError) and str(exc).startswith('Zdjęcie jest jednolite.'):
                    message=str(exc)
                with store.lock,store.db() as db:
                    db.execute("UPDATE jobs SET status='error',error=?,updated_at=? WHERE id=?",(message,now_iso(),job_id))
            finally:
                with store.lock:
                    input_path.unlink(missing_ok=True)
                    output_path.unlink(missing_ok=True)
                    if reservation:
                        store.reserved_bytes-=reservation
                jobs.task_done()

    @app.post('/api/assets/<asset_id>/remove-background')
    def enqueue_background(asset_id):
        nonlocal worker
        data=payload() if request.is_json else {}
        method=data.get('method','smart')
        if method not in ('smart','ai'):
            raise ApiError('Wybierz metodę usuwania tła: inteligentną albo AI.')
        with store.lock,store.db() as db:
            asset=get_asset(db,asset_id,live=True)
            if asset['mime']=='image/svg+xml':
                raise ApiError('SVG zachowuje przezroczystość i ostrość. Zmień jego tło w pliku źródłowym lub prześlij PNG do usuwania tła.',code='svg_background')
            if not asset['campaign_id'] or asset['kind'] not in ('product','background','cutout','element'):
                raise ApiError('Usuwanie tła jest dostępne dla obrazów kampanii.')
            pending=db.execute("SELECT * FROM jobs WHERE asset_id=? AND method=? AND status IN ('queued','running')",(asset_id,method)).fetchone()
            if pending:
                return jsonify(job_json(db,pending)),202
            if db.execute('SELECT COUNT(*) FROM assets WHERE campaign_id=? AND expired=0',(asset['campaign_id'],)).fetchone()[0]>=MAX_ASSETS:
                raise ApiError('Kampania osiągnęła limit 60 plików.')
            if jobs.full():
                raise ApiError('Kolejka usuwania tła jest pełna. Spróbuj po zakończeniu bieżących zadań.',429)
            store.ensure_capacity(asset['size']+asset['width']*asset['height']*4+MIB+METADATA_MARGIN)
            job_id=identifier()
            stamp=now_iso()
            db.execute("INSERT INTO jobs(id,asset_id,campaign_id,status,method,created_at,updated_at) VALUES(?,?,?,'queued',?,?,?)",(job_id,asset_id,asset['campaign_id'],method,stamp,stamp))
            db.commit()
            jobs.put_nowait(job_id)
        with thread_lock:
            if worker is None or not worker.is_alive():
                worker=threading.Thread(target=process_jobs,name='studio-background',daemon=True)
                worker.start()
        return jsonify(id=job_id,status='queued',method=method),202

    @app.get('/api/jobs/<job_id>')
    def read_job(job_id):
        with store.db() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if row:
                get_campaign(db,row['campaign_id'],live=True)
            return jsonify(job_json(db,row))

    @app.get('/api/storage')
    def capacity():
        return jsonify(store.capacity())

    @app.get('/api/formats')
    def formats():
        return jsonify(FORMATS)

    def validate_texts(texts,profiles):
        if not isinstance(texts,dict):
            raise ApiError('Tabela tekstów ma nieprawidłowy format.')
        result={}
        for key,label in (('headlines','Nagłówki'),('descriptions','Opisy'),('ctas','CTA')):
            vals=texts.get(key,[])
            if not isinstance(vals,list) or len(vals)>30:
                raise ApiError(f'Pole „{label}” może zawierać maksymalnie 30 tekstów.')
            result[key]=[text_field(v,label,500,True) for v in vals]
        result['long_headline']=text_field(texts.get('long_headline',''),'Długi nagłówek',500)
        result['business_name']=text_field(texts.get('business_name',''),'Nazwa firmy',100)
        if profiles & {'rda','pmax'}:
            for key,label,maxlen in (('headlines','Nagłówek',30),('descriptions','Opis',90)):
                if any(len(s)>maxlen for s in result[key]):
                    raise ApiError(f'{label} dla Responsive Display / Performance Max może mieć maksymalnie {maxlen} znaków.')
            if not 1<=len(result['long_headline'])<=90:
                raise ApiError('Dodaj długi nagłówek o długości 1–90 znaków.')
            if not 1<=len(result['business_name'])<=25:
                raise ApiError('Nazwa firmy dla materiałów Google Ads musi mieć 1–25 znaków.')
            if not result['headlines'] or not result['descriptions']:
                raise ApiError('Dodaj przynajmniej jeden nagłówek i opis.')
            if len(result['headlines'])>15 or len(result['descriptions'])>5:
                raise ApiError('Eksport materiałów może zawierać do 15 nagłówków i 5 opisów.')
            if 'rda' in profiles and len(result['headlines'])>5:
                raise ApiError('Responsive Display obsługuje maksymalnie 5 krótkich nagłówków w jednym zestawie.')
        return result

    @app.post('/api/campaigns/<campaign_id>/exports')
    def create_export(campaign_id):
        try:
            manifest=json.loads(request.form.get('manifest','null'))
            texts=json.loads(request.form.get('texts','null'))
        except (ValueError,RecursionError) as exc:
            raise ApiError('Manifest lub tabela tekstów nie jest poprawnym JSON.') from exc
        uploads=request.files.getlist('files')
        if not isinstance(manifest,list) or not 1<=len(manifest)<=100 or len(uploads)!=len(manifest):
            raise ApiError('Eksport wymaga 1–100 plików i zgodnego manifestu.')
        # Always acquire the CPU gate before the storage lock when both are needed.
        with processing_lock,store.lock,store.db() as db:
            campaign=get_campaign(db,campaign_id,live=True)
            check_version(campaign,request.form.get('version'))
            if json.loads(campaign['state']).get('confirmed') is not True:
                raise ApiError('Potwierdź poprawność oferty, cen, rabatów i dat przed eksportem.')
            if db.execute('SELECT COUNT(*) FROM exports WHERE campaign_id=? AND expired=0',(campaign_id,)).fetchone()[0]>=20:
                raise ApiError('Kampania może zawierać maksymalnie 20 pakietów eksportu.')
            valid=[]
            names=set()
            total=0
            profiles=set()
            for item,upload in zip(manifest,uploads):
                if not isinstance(item,dict) or not isinstance(item.get('format_id'),str) or item['format_id'] not in FORMAT_BY_ID:
                    raise ApiError('Manifest zawiera nieznany format Google Ads.')
                fmt=FORMAT_BY_ID[item['format_id']]
                raw=upload.stream.read(fmt['max_bytes']+1)
                if not raw or len(raw)>fmt['max_bytes']:
                    raise ApiError(f"Plik w formacie {fmt['label']} przekracza dopuszczalny rozmiar.",413)
                total+=len(raw)
                if total>80*MIB:
                    raise ApiError('Pakiet eksportu może mieć maksymalnie 80 MB.',413)
                dimensions,image_format=decode_media(raw,sanitize=False)
                allowed=('JPEG',) if fmt['profile']=='display' else ('JPEG','PNG')
                if image_format not in allowed or dimensions!=(fmt['width'],fmt['height']):
                    raise ApiError(f"Plik nie spełnia wymagań formatu {fmt['label']} (wymiary lub typ).")
                if item.get('width')!=fmt['width'] or item.get('height')!=fmt['height']:
                    raise ApiError('Wymiary manifestu nie zgadzają się z formatem pliku.')
                name=item.get('name','')
                if not isinstance(name,str) or len(name)>180 or '/' in name or '\\' in name or name.startswith('.'):
                    raise ApiError('Nazwa pliku w manifeście jest nieprawidłowa.')
                extension='jpg' if image_format=='JPEG' else 'png'
                variant=text_field(str(item.get('variant','1')),'Wariant',80,True)
                template=text_field(str(item.get('template','')),'Kompozycja',80)
                raw_mode=item.get('mode','')
                if fmt['profile']=='pmax':
                    mode=str(raw_mode or '').strip()
                    if not mode:
                        mode='czysty'
                    if mode not in ('kompozycja','czysty'):
                        raise ApiError('Manifest zawiera nieprawidłowy tryb obrazu Performance Max.')
                    archive_name=f"{fmt['profile']}/{secure_filename(template) or 'uklad'}/{mode}/{secure_filename(variant) or 'wariant'}/{fmt['width']}x{fmt['height']}.{extension}"
                else:
                    mode=''
                    archive_name=f"{fmt['profile']}/{secure_filename(template) or 'uklad'}/{secure_filename(variant) or 'wariant'}/{fmt['width']}x{fmt['height']}.{extension}"
                if archive_name.casefold() in names:
                    raise ApiError('Manifest zawiera powtórzone nazwy plików.')
                names.add(archive_name.casefold())
                profiles.add(fmt['profile'])
                valid.append((archive_name,raw,fmt,variant,template,mode))
            texts=validate_texts(texts,profiles)
            export_warnings=[]
            if 'pmax' in profiles:
                if len(texts['headlines'])<3 or len(texts['descriptions'])<2:
                    export_warnings.append('Performance Max: biblioteka ma mniej niż 3 krótkie nagłówki lub 2 opisy. Uzupełnij teksty przed utworzeniem pełnej grupy zasobów.')
                if not any(len(headline)<=15 for headline in texts['headlines']):
                    export_warnings.append('Performance Max: dodaj przynajmniej jeden nagłówek o długości do 15 znaków.')
            for profile in ('rda','pmax'):
                if profile in profiles:
                    exported={fmt['id'] for _,_,fmt,_,_,_ in valid}
                    if not {f'{profile}_1200x628',f'{profile}_1200x1200'}<=exported:
                        export_warnings.append(f'{profile.upper()}: wybrano część formatów. Pełny zestaw obrazów wymaga formatu poziomego i kwadratowego.')
            rows=[['plik','profil','szerokosc','wysokosc','bajty','wariant','kompozycja','tryb']]
            text_rows=[['typ','numer','tekst']]
            for key in ('headlines','descriptions','ctas'):
                text_rows.extend([key,i+1,val] for i,val in enumerate(texts[key]))
            text_rows.extend([['long_headline',1,texts['long_headline']],['business_name',1,texts['business_name']]])
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as archive:
                for name,raw,fmt,variant,template,mode in valid:
                    archive.writestr(name,raw)
                    rows.append([name,fmt['profile'],fmt['width'],fmt['height'],len(raw),variant,template,mode])
                archive.writestr('manifest.csv',safe_csv(rows))
                archive.writestr('texts.csv',safe_csv(text_rows))
                archive.writestr('validation.csv',safe_csv([['poziom','uwaga']]+[['ostrzezenie',message] for message in export_warnings]))
                archive.writestr('README.txt','Materiały przygotowane do ręcznej weryfikacji i przesłania. Tabela tekstów nie jest plikiem importu Google Ads. Sprawdź treść, logo, kadrowanie i czytelność przed użyciem. Walidacja techniczna nie gwarantuje akceptacji reklamy.\n')
            content=output.getvalue()
            export_id=identifier()
            path=f'{export_id}.zip'
            filename=(secure_filename(campaign['name']) or 'kampania')+'-materialy.zip'
            store.ensure_capacity(len(content)+METADATA_MARGIN)
            store.write(path,content)
            try:
                db.execute('INSERT INTO exports(id,campaign_id,path,filename,size,file_count,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)',
                    (export_id,campaign_id,path,filename,len(content),len(valid),now_iso(),campaign['expires_at']))
            except Exception:
                store.path(path).unlink(missing_ok=True)
                raise
            result=export_json(db.execute('SELECT * FROM exports WHERE id=?',(export_id,)).fetchone())
            result['warnings']=export_warnings
            return jsonify(result),201

    @app.get('/api/exports/<export_id>/download')
    def download_export(export_id):
        with store.lock,store.db() as db:
            row=db.execute('SELECT * FROM exports WHERE id=?',(export_id,)).fetchone()
            if not row:
                raise ApiError('Nie znaleziono eksportu.',404)
            get_campaign(db,row['campaign_id'],live=True)
            if row['expired'] or not store.path(row['path']).is_file():
                raise ApiError('Ten eksport wygasł i nie jest już dostępny.',410)
            return send_file(store.path(row['path']),mimetype='application/zip',as_attachment=True,download_name=row['filename'],conditional=False)

    def cleanup_loop():
        while True:
            time.sleep(60)
            try:
                store.cleanup(force=True)
            except Exception:
                app.logger.exception('Campaign cleanup failed')

    if app.config['START_CLEANUP_THREAD'] and not app.testing:
        threading.Thread(target=cleanup_loop,name='studio-cleanup',daemon=True).start()
    app.extensions['studio_jobs']=jobs
    return app


def main():
    parser=argparse.ArgumentParser(description='Google Ads Assets Studio')
    sub=parser.add_subparsers(dest='command',required=True)
    admin=sub.add_parser('create-admin')
    admin.add_argument('username')
    admin.add_argument('--password-file',required=True)
    serve=sub.add_parser('serve')
    serve.add_argument('--host',default='127.0.0.1')
    serve.add_argument('--port',type=int,default=8094)
    sub.add_parser('cleanup')
    args=parser.parse_args()
    app=create_app({'START_CLEANUP_THREAD':args.command=='serve','RECOVER_JOBS':args.command=='serve'})
    store=app.extensions['studio_storage']
    if args.command=='create-admin':
        username=text_field(args.username,'Login',80,True)
        if not re.fullmatch(r'[\w.@+-]{3,80}',username):
            parser.error('Login musi mieć 3–80 bezpiecznych znaków.')
        password=Path(args.password_file).read_text().rstrip('\r\n')
        hashed=password_hash(password)
        with store.lock,store.db() as db:
            store.ensure_capacity(METADATA_MARGIN)
            if db.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone():
                parser.error('Ten użytkownik już istnieje; hasła nie zmieniono.')
            db.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,'admin',?)",(username,hashed,now_iso()))
        print('Utworzono konto administratora.')
    elif args.command=='cleanup':
        store.cleanup(force=True)
        print('Usunięto wygasłe pliki aplikacji.')
    else:
        from waitress import serve
        serve(app,host=args.host,port=args.port,threads=4,max_request_body_size=82*MIB)


if __name__=='__main__':
    main()
