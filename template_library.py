"""A bounded, data-only recipe for reusable compositions.

Recipes deliberately cannot carry campaign text, image references or a Brand Kit.
Keep this allowlist aligned with static/template-recipes.js when adding a style.
"""
import json
import math
import re

from storage import ApiError


MAX_RECIPE_BYTES = 256 * 1024
MAX_TEMPLATES = 100
BASE_TEMPLATES = frozenset(('split', 'spotlight', 'minimal', 'catalog', 'benefits',
                          'label', 'backdrop', 'bundle', 'bold'))
COLORS = frozenset(('@brand.color', '@brand.secondary_color', '@brand.text_color',
                    '@contrast.background'))
FONTS = frozenset(('@brand.font', 'Arial', 'Helvetica', 'Verdana', 'Georgia', 'Tahoma',
                   'Trebuchet MS', 'Times New Roman', 'sans-serif', 'serif', 'monospace'))
DECORATION_IDS = frozenset(('ribbon-paper', 'ribbon-panel', 'ribbon-content', 'brand-rule',
                           'text-panel', 'product-panel', 'lower-panel', 'catalog-shelf',
                           'catalog-rule', 'benefits-photo', 'benefits-description', 'benefits-rule',
                           'label-rule', 'label-product', 'backdrop-copy', 'bundle-hero', 'bundle-rule',
                           'bold-field', 'bold-product', 'bold-logo'))
COMMON_FIELDS = frozenset(('id', 'type', 'role', 'x', 'y', 'w', 'h', 'opacity', 'hidden', 'locked'))
STYLE_FIELDS = {
    'image': frozenset(('slot', 'fit', 'cropX', 'cropY')),
    'text': frozenset(('color', 'fontFamily', 'fontSize', 'baseFontSize', 'fontWeight',
                       'align', 'verticalAlign', 'backgroundColor', 'radius', 'cornerRadius',
                       'borderColor', 'borderWidth')),
    'rect': frozenset(('color', 'radius', 'cornerRadius', 'borderColor', 'borderWidth', 'shape')),
}
NUMBERS = {
    'x': (-16384, 16384), 'y': (-16384, 16384), 'w': (0, 16384), 'h': (0, 16384),
    'opacity': (0, 1), 'cropX': (0, 1), 'cropY': (0, 1),
    'fontSize': (1, 2000), 'baseFontSize': (1, 2000), 'fontWeight': (100, 900),
    'radius': (0, 8192), 'cornerRadius': (0, 1), 'borderWidth': (0, 1000),
}


def invalid():
    raise ApiError('Szablon ma nieprawidłową strukturę. Zapisz ponownie układ w edytorze.',
                   code='invalid_template_recipe')


def object_keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or not value.keys() <= set(required) | set(optional):
        invalid()


def finite(value, minimum, maximum, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum or not math.isfinite(value):
        invalid()
    if integer and not isinstance(value, int):
        invalid()


def enum(value, choices):
    if not isinstance(value, str) or value not in choices:
        invalid()


def color(value, contrast=True):
    if not isinstance(value, str) or not (re.fullmatch(r'#[0-9A-Fa-f]{6}', value) or value in COLORS):
        invalid()
    if not contrast and value == '@contrast.background':
        invalid()


def canonical_id(layer):
    identifier, role, kind = layer['id'], layer['role'], layer['type']
    if not isinstance(identifier, str) or len(identifier) > 48:
        invalid()
    if kind == 'rect':
        if role == 'shape':
            if not re.fullmatch(r'shape-slot-(?:[1-9][0-9]?|100)', identifier):
                invalid()
        elif role != 'decoration' or not (identifier in DECORATION_IDS or re.fullmatch(r'decoration-slot-(?:[1-9][0-9]?|100)', identifier)):
            invalid()
    elif kind == 'text':
        enum(role, ('headline', 'description', 'cta'))
        if identifier != role and not re.fullmatch(re.escape(role) + r'-slot-(?:[1-9][0-9]?|100)', identifier):
            invalid()
    else:
        enum(role, ('product', 'element', 'background', 'logo'))
        finite(layer.get('slot'), 0, 99, integer=True)
        slot = layer['slot']
        expected = role if slot == 0 and role != 'element' else f'{role}-slot-{slot + 1}'
        if identifier != expected:
            invalid()


def validate_layer(layer):
    if not isinstance(layer, dict):
        invalid()
    kind = layer.get('type')
    enum(kind, STYLE_FIELDS)
    required = {'id', 'type', 'role', 'x', 'y', 'w', 'h'} | ({'slot'} if kind == 'image' else set())
    object_keys(layer, required, COMMON_FIELDS | STYLE_FIELDS[kind])
    canonical_id(layer)
    for key, value in layer.items():
        if key in NUMBERS:
            finite(value, *NUMBERS[key])
        elif key in ('hidden', 'locked'):
            if not isinstance(value, bool):
                invalid()
        elif key in ('color', 'backgroundColor', 'borderColor'):
            color(value, contrast=key == 'color')
        elif key == 'shape':
            enum(value, ('rectangle', 'square', 'circle', 'ellipse', 'triangle', 'diamond'))
        elif key == 'fontFamily':
            enum(value, FONTS)
        elif key == 'align':
            enum(value, ('left', 'center', 'right'))
        elif key == 'verticalAlign':
            enum(value, ('top', 'middle', 'bottom'))
        elif key == 'fit':
            enum(value, ('contain', 'cover'))


def validate_scene(scene, dimensions=None):
    object_keys(scene, ('width', 'height', 'background', 'clean', 'layers'), ('productOrder', 'omitted'))
    finite(scene['width'], 1, 8192, integer=True)
    finite(scene['height'], 1, 8192, integer=True)
    if scene['width'] * scene['height'] > 20_000_000:
        invalid()
    if dimensions and (scene['width'], scene['height']) != dimensions:
        invalid()
    color(scene['background'], contrast=False)
    if not isinstance(scene['clean'], bool) or not isinstance(scene['layers'], list) or len(scene['layers']) > 100:
        invalid()
    ids, products = set(), set()
    for layer in scene['layers']:
        validate_layer(layer)
        if layer['id'] in ids:
            invalid()
        ids.add(layer['id'])
        if layer['role'] == 'product':
            products.add(layer['id'])
    if 'productOrder' in scene:
        order = scene['productOrder']
        if not isinstance(order, list) or len(order) > 100 or any(not isinstance(value, str) for value in order):
            invalid()
        if len(set(order)) != len(order) or not set(order) <= products:
            invalid()
    if 'omitted' in scene:
        omitted = scene['omitted']
        if not isinstance(omitted, list) or len(omitted) > 3:
            invalid()
        for role in omitted:
            enum(role, ('headline', 'description', 'cta'))
        if len(set(omitted)) != len(omitted):
            invalid()


def encode_recipe(recipe, formats):
    """Validate every persisted field and return canonical, finite JSON."""
    try:
        encoded = json.dumps(recipe, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        encoded_size = len(encoded.encode('utf-8'))
    except (ValueError, TypeError, RecursionError, OverflowError):
        invalid()
    if encoded_size > MAX_RECIPE_BYTES:
        raise ApiError('Szablon jest zbyt duży (maks. 256 KB). Ogranicz liczbę warstw i dopasowań formatów.',
                       413, code='template_recipe_too_large')
    object_keys(recipe, ('version', 'base_template', 'master', 'formats'))
    if type(recipe['version']) is not int or recipe['version'] != 1:
        invalid()
    enum(recipe['base_template'], BASE_TEMPLATES)
    validate_scene(recipe['master'])
    overrides = recipe['formats']
    if not isinstance(overrides, dict) or len(overrides) > 20:
        invalid()
    for format_id, scene in overrides.items():
        if format_id not in formats:
            invalid()
        spec = formats[format_id]
        validate_scene(scene, (spec['width'], spec['height']))
    return encoded
