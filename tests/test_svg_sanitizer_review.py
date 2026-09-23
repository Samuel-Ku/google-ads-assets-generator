import xml.etree.ElementTree as ET

import pytest

from storage import ApiError
from svg_media import sanitize_svg


def test_inline_exporter_styles_keep_local_gradient_and_stroke():
    raw = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
    <defs><linearGradient id="paint"><stop offset="0" stop-color="red"/></linearGradient></defs>
    <path style="fill:url(#paint);stroke:#123456;stroke-width:.5" d="M0 0H24V24Z"/>
    </svg>'''
    content, width, height, extension = sanitize_svg(raw)
    path = ET.fromstring(content).find('{http://www.w3.org/2000/svg}path')
    assert 'fill:url(#paint)' in path.get('style')
    assert 'stroke:#123456' in path.get('style')
    assert (width, height, extension) == (24, 24, 'svg')


@pytest.mark.parametrize('style', [
    'fill:url(https://example.invalid/image)',
    r'fill:u\72l(https://example.invalid/image)',
    'fill:url("data:image/svg+xml;base64,PHN2Zy8+")',
    'background-image:url(#paint)',
    'fill:var(--paint)',
])
def test_inline_style_rejects_remote_or_unsupported_values(style):
    root = ET.Element('svg', viewBox='0 0 24 24')
    ET.SubElement(root, 'path', style=style, d='M0 0H24V24Z')
    with pytest.raises(ApiError):
        sanitize_svg(ET.tostring(root))


@pytest.mark.parametrize('dimensions', [
    'width="1e-300" height="1e-300"',
    'viewBox="0 0 1e-300 1e-300"',
    'width="1" viewBox="0 0 1e-320 100"',
    'height="1" viewBox="0 0 100 1e-320"',
])
def test_extreme_intrinsic_geometry_is_rejected_as_validation_error(dimensions):
    with pytest.raises(ApiError):
        sanitize_svg(f'<svg {dimensions}><path d="M0 0H24V24Z"/></svg>'.encode())
