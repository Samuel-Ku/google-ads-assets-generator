"""SVG upload boundaries: retained vectors, private delivery and static-only input."""

import base64
import io
import xml.etree.ElementTree as ET

import pytest
from PIL import Image, PngImagePlugin

from test_api import export, studio
from app import ApiError, decode_image


SVG_NS = 'http://www.w3.org/2000/svg'


def svg(body='<path d="M0 0h120v80H0z" fill="#f80"/>', *, viewbox='0 0 120 80', attrs=''):
    return f'<svg xmlns="{SVG_NS}" viewBox="{viewbox}" {attrs}>{body}</svg>'.encode()


def upload_svg(client, headers, campaign, raw=None, kind='element', name='label.svg'):
    return client.post(f"/api/campaigns/{campaign['id']}/assets", headers=headers,
        data={'kind':kind, 'file':(io.BytesIO(svg() if raw is None else raw), name)})


@pytest.mark.parametrize('kind', ['product', 'background', 'element', 'cutout'])
def test_campaign_svg_stays_vector_and_is_served_privately(studio, kind):
    app, store, client, headers, brand, campaign = studio
    response = upload_svg(client, headers, campaign, kind=kind)
    assert response.status_code == 201, response.json
    asset = response.json
    assert (asset['width'], asset['height'], asset['kind']) == (120, 80, kind)
    assert asset['mime'] == 'image/svg+xml'
    assert app.test_client().get(asset['url']).status_code == 401
    delivery = client.get(asset['url'])
    assert delivery.status_code == 200
    assert delivery.mimetype == 'image/svg+xml'
    root = ET.fromstring(delivery.data)
    assert root.tag == f'{{{SVG_NS}}}svg'
    assert root.find(f'{{{SVG_NS}}}path') is not None
    with store.db() as db:
        stored = db.execute('SELECT path,mime FROM assets WHERE id=?', (asset['id'],)).fetchone()
    assert stored['path'].endswith('.svg')
    assert stored['mime'] == 'image/svg+xml'
    assert store.path(stored['path']).read_bytes() == delivery.data
    policy = delivery.headers['Content-Security-Policy']
    assert "default-src 'none'" in policy
    assert 'sandbox' in policy
    # The document sandbox must survive the normal global security-header hook.
    assert "default-src 'self'" in client.get('/').headers['Content-Security-Policy']


def test_brand_svg_becomes_logo_without_rasterizing(studio):
    app, store, client, headers, brand, campaign = studio
    result = client.post(f"/api/brands/{brand['id']}/assets", headers=headers,
        data={'kind':'logo', 'file':(io.BytesIO(svg()), 'logo.svg')})
    assert result.status_code == 201, result.json
    asset = result.json
    assert asset['mime'] == 'image/svg+xml'
    assert asset['brand_id'] == brand['id']
    assert client.get(asset['url']).mimetype == 'image/svg+xml'
    with store.db() as db:
        assert db.execute('SELECT logo_asset_id FROM brands WHERE id=?', (brand['id'],)).fetchone()[0] == asset['id']


def test_local_graphic_references_and_class_styles_survive_sanitizing():
    raw = svg('''<defs>
      <linearGradient id="color"><stop offset="0" stop-color="#f80"/><stop offset="1" stop-color="#fff"/></linearGradient>
      <clipPath id="clip"><rect width="110" height="70"/></clipPath>
      <mask id="mask"><rect width="120" height="80" fill="white"/></mask>
      <path id="shape" d="M0 0h120v80H0z"/>
    </defs><style>.badge { fill: url(#color); stroke: #222; stroke-width: 1; }</style>
    <g clip-path="url(#clip)" mask="url(#mask)"><use href="#shape" class="badge"/></g>''')
    content, width, height, extension = decode_image(raw)
    root = ET.fromstring(content)
    assert (width, height, extension) == (120, 80, 'svg')
    tags = {node.tag.split('}')[-1] for node in root.iter()}
    assert {'linearGradient', 'stop', 'clipPath', 'mask', 'path', 'use', 'style'} <= tags
    assert '#shape' in content.decode()
    assert '#color' in content.decode()
    assert 'badge' in content.decode()


@pytest.mark.parametrize('raw', [
    svg('<script>alert(1)</script>'),
    svg(attrs='onload="alert(1)"'),
    svg('<path d="M0 0h1" onclick="alert(1)"/>'),
    svg('<animate attributeName="x" from="0" to="10" dur="1s"/>'),
    svg('<set attributeName="href" to="https://example.com/image.svg"/>'),
    svg('<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">HTML</div></foreignObject>'),
    svg('<image href="https://example.com/image.png" width="120" height="80"/>'),
    svg('<use href="//example.com/other.svg#shape"/>'),
    svg('<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="file:///etc/passwd"/>'),
    svg(attrs='xml:base="https://example.com/"'),
    svg('<path style="fill:url(https://example.com/fill.svg#color)" d="M0 0h1"/>'),
    svg('<style>@import url("https://example.com/style.css");</style>'),
    svg('<style>.badge { fill: u\\72l(https://example.com/fill.svg#color); }</style>'),
    svg('<path style="fill: url(\\68 ttps://example.com/fill.svg#color)" d="M0 0h1"/>'),
    b'<!DOCTYPE svg [<!ENTITY payload "anything">]><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80"><text>&payload;</text></svg>',
    b'<!DOCTYPE svg SYSTEM "https://example.com/svg.dtd"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80"/>',
    svg('<defs><g id="loop"><use href="#loop"/></g></defs><use href="#loop"/>'),
])
def test_active_external_or_recursive_svg_is_rejected(raw):
    with pytest.raises(ApiError):
        decode_image(raw)


def test_exponential_local_use_expansion_is_rejected():
    # A tiny document can otherwise expand to millions of painted elements.
    groups = ['<g id="n0"><path d="M0 0h1"/></g>']
    groups += [f'<g id="n{i}"><use href="#n{i-1}"/><use href="#n{i-1}"/></g>' for i in range(1, 25)]
    raw = svg('<defs>' + ''.join(groups) + '</defs><use href="#n24"/>')
    with pytest.raises(ApiError):
        decode_image(raw)


@pytest.mark.parametrize('viewbox', ['0 0 0 80', '0 0 -120 80', '0 0 120 nan', '0 0 120 inf'])
def test_invalid_intrinsic_dimensions_are_rejected(viewbox):
    with pytest.raises(ApiError):
        decode_image(svg(viewbox=viewbox))


def test_large_intrinsic_dimensions_are_normalized_without_flattening():
    content, width, height, extension = decode_image(svg(viewbox='0 0 40000 30000'))
    assert 0 < width <= 8192 and 0 < height <= 8192
    assert width * height <= 20_000_000
    assert abs(width / height - 4 / 3) < .002
    assert extension == 'svg'
    root = ET.fromstring(content)
    assert root.attrib['viewBox'] == '0 0 40000 30000'
    assert root.find(f'{{{SVG_NS}}}path') is not None


def test_svg_upload_limit_and_rejection_leave_no_asset_or_staged_file(studio):
    app, store, client, headers, brand, campaign = studio
    too_large = svg('<!--' + 'a' * (2 * 1024 * 1024) + '-->')
    for raw in (too_large, svg('<script>alert(1)</script>'), b'<svg broken'):
        response = upload_svg(client, headers, campaign, raw)
        assert response.status_code in (400, 413), response.json
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 0
    assert list(store.media.iterdir()) == []
    assert list(store.temp.iterdir()) == []


def test_svg_cannot_be_enqueued_for_background_removal_or_exported_as_banner(studio):
    app, store, client, headers, brand, campaign = studio
    result = upload_svg(client, headers, campaign)
    assert result.status_code == 201, result.json
    response = client.post(f"/api/assets/{result.json['id']}/remove-background", json={'method':'smart'}, headers=headers)
    assert response.status_code == 400
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
    # Final advertisements stay JPG/PNG, even with a matching 300x250 viewport.
    assert export(client, headers, campaign, raw=svg(viewbox='0 0 300 250')).status_code == 400
    with pytest.raises(ApiError):
        decode_image(svg(), sanitize=False)


def test_embedded_png_is_redecoded_but_preserves_its_pixels_and_transparency():
    source = Image.new('RGBA', (4, 3), (210, 60, 20, 180))
    source.putpixel((0, 0), (10, 20, 30, 0))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('Comment', 'Untrusted source metadata must not be retained')
    original = io.BytesIO()
    source.save(original, format='PNG', pnginfo=metadata)
    encoded = base64.b64encode(original.getvalue()).decode()
    raw = svg(f'<image href="data:image/png;base64,{encoded}" width="120" height="80"/>')
    content, width, height, extension = decode_image(raw)
    root = ET.fromstring(content)
    embedded = root.find(f'{{{SVG_NS}}}image')
    assert (width, height, extension) == (120, 80, 'svg')
    prefix, encoded = embedded.attrib['href'].split(',', 1)
    assert prefix == 'data:image/png;base64'
    sanitized = base64.b64decode(encoded, validate=True)
    assert sanitized != original.getvalue()
    with Image.open(io.BytesIO(sanitized)) as restored:
        assert restored.format == 'PNG'
        assert restored.size == source.size
        assert restored.convert('RGBA').tobytes() == source.tobytes()
        assert 'Comment' not in restored.info


@pytest.mark.parametrize('mime', ['image/svg+xml', 'image/png', 'text/html'])
def test_embedded_nonraster_data_is_rejected_even_when_named_png(mime):
    encoded = base64.b64encode(svg()).decode()
    with pytest.raises(ApiError):
        decode_image(svg(f'<image href="data:{mime};base64,{encoded}" width="120" height="80"/>'))


def test_absolute_unit_dimensions_without_viewbox_keep_their_coordinate_space():
    raw = f'<svg xmlns="{SVG_NS}" width="2in" height="25.4mm"><rect width="192" height="96" fill="#f80"/></svg>'.encode()
    content, width, height, extension = decode_image(raw)
    assert (width, height, extension) == (192, 96, 'svg')
    root = ET.fromstring(content)
    assert root.attrib['width'] == '192'
    assert root.attrib['height'] == '96'
    assert [float(value) for value in root.attrib['viewBox'].split()] == [0, 0, 192, 96]
    rect = root.find(f'{{{SVG_NS}}}rect')
    assert (rect.attrib['width'], rect.attrib['height']) == ('192', '96')
