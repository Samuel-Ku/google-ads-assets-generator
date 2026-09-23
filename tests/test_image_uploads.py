"""Regressions for large, valid source images and strict export decoding."""
import io

import pytest
from PIL import Image, ImageDraw

from test_api import image_bytes, studio, upload
from app import decode_image
from storage import ApiError


@pytest.fixture(scope='module')
def large_jpeg():
    return image_bytes(size=(6000, 4000))


def assert_fitted(width, height, original_size):
    assert 19_900_000 <= width * height <= 20_000_000
    assert width <= original_size[0] and height <= original_size[1]
    # Resizing must preserve the source ratio within a single-pixel rounding error.
    assert abs(width / height - original_size[0] / original_size[1]) <= 2 / height


def jpeg_with_declared_dimensions(width, height):
    """Patch only the baseline JPEG header; no large pixel allocation is needed."""
    raw = bytearray(image_bytes(size=(16, 16)))
    marker = raw.index(b'\xff\xc0')
    raw[marker + 5:marker + 7] = height.to_bytes(2, 'big')
    raw[marker + 7:marker + 9] = width.to_bytes(2, 'big')
    return bytes(raw)


def test_24mp_background_upload_is_fitted_and_saved_as_valid_jpeg(studio, large_jpeg):
    app, store, client, headers, brand, campaign = studio
    response = upload(client, headers, campaign, raw=large_jpeg, kind='background')
    assert response.status_code == 201, response.json
    asset = response.json
    assert asset['kind'] == 'background'
    assert_fitted(asset['width'], asset['height'], (6000, 4000))
    # Merely changing returned metadata does not fix a rejected/oversized upload.
    saved = client.get(asset['url'])
    assert saved.status_code == 200 and saved.mimetype == 'image/jpeg'
    with Image.open(io.BytesIO(saved.data)) as image:
        image.load()
        assert image.size == (asset['width'], asset['height'])
        assert image.getpixel((image.width // 2, image.height // 2))[0] > 190


def test_exactly_20mp_image_keeps_its_dimensions():
    output, width, height, extension = decode_image(image_bytes(size=(5000, 4000)))
    assert (width, height, extension) == (5000, 4000, 'jpg')
    with Image.open(io.BytesIO(output)) as image:
        assert image.size == (5000, 4000)


def test_over_60mp_upload_has_dimension_error_without_decoding_pixels(studio):
    app, store, client, headers, brand, campaign = studio
    response = upload(client, headers, campaign,
                      raw=jpeg_with_declared_dimensions(10000, 6001), kind='background')
    assert response.status_code == 400
    assert response.json.get('code') == 'image_dimensions', response.json
    message = response.json['error']
    assert '60' in message, response.json
    assert 'megapik' in message.lower() or 'mp' in message.lower(), response.json
    assert 'odczytać' not in message.lower(), response.json
    assert list(store.media.iterdir()) == []
    assert list(store.temp.iterdir()) == []


def test_corrupt_upload_is_distinct_from_dimension_rejection(studio):
    app, store, client, headers, brand, campaign = studio
    response = upload(client, headers, campaign, raw=b'not a valid image', kind='background')
    assert response.status_code == 400
    assert response.json.get('code') == 'image_decode', response.json
    assert 'odczytać' in response.json['error'].lower(), response.json
    assert list(store.media.iterdir()) == []


def test_large_transparent_png_keeps_alpha_after_fitting():
    raw = io.BytesIO()
    with Image.new('RGBA', (5000, 4001), (25, 100, 220, 96)) as source:
        source.save(raw, format='PNG')
    output, width, height, extension = decode_image(raw.getvalue())
    assert extension == 'png'
    assert_fitted(width, height, (5000, 4001))
    with Image.open(io.BytesIO(output)) as image:
        assert image.mode == 'RGBA'
        assert image.getpixel((width // 2, height // 2))[3] == 96


def test_large_exif_rotated_jpeg_keeps_visual_orientation():
    raw = io.BytesIO()
    with Image.new('RGB', (6000, 4000), (220, 30, 20)) as source:
        ImageDraw.Draw(source).rectangle((3000, 0, 5999, 3999), fill=(20, 30, 220))
        exif = Image.Exif()
        exif[274] = 6  # Camera requests a 90-degree clockwise rotation.
        source.save(raw, format='JPEG', exif=exif)
    output, width, height, extension = decode_image(raw.getvalue())
    assert extension == 'jpg' and height > width
    assert_fitted(width, height, (4000, 6000))
    with Image.open(io.BytesIO(output)) as image:
        top = image.getpixel((width // 2, height // 4))
        bottom = image.getpixel((width // 2, height * 3 // 4))
        assert top[0] > 180 and top[2] < 60
        assert bottom[2] > 180 and bottom[0] < 60
        assert image.getexif().get(274, 1) == 1


def test_export_decoder_rejects_large_images_instead_of_resizing(large_jpeg):
    with pytest.raises(ApiError) as error:
        decode_image(large_jpeg, sanitize=False)
    assert '20' in error.value.message
    assert error.value.details.get('code') == 'image_dimensions'
    assert decode_image(image_bytes(size=(1200, 628)), sanitize=False) == ((1200, 628), 'JPEG')
