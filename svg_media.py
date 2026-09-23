"""Bounded static SVG input: vectors stay vectors; documents never fetch resources."""
from __future__ import annotations
import base64
import math
import re
import xml.etree.ElementTree as ET
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
import tinycss2
from storage import ApiError

SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
XML = 'http://www.w3.org/XML/1998/namespace'
ET.register_namespace('', SVG)
ET.register_namespace('xlink', XLINK)
MAX_SVG = 2 * 1024 * 1024
MAX_NODES, MAX_WORK = 5000, 40000
TAGS = set('svg g defs symbol path rect circle ellipse line polyline polygon text tspan textPath use image linearGradient radialGradient stop clipPath mask pattern marker filter feGaussianBlur feOffset feFlood feBlend feComposite feMerge feMergeNode feColorMatrix title desc style'.split())
PROPS = set('fill fill-rule fill-opacity stroke stroke-width stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset stroke-opacity opacity color display visibility font-family font-size font-style font-weight font-stretch font-variant letter-spacing word-spacing text-anchor text-decoration dominant-baseline alignment-baseline baseline-shift clip-path clip-rule mask filter marker-start marker-mid marker-end stop-color stop-opacity flood-color flood-opacity color-interpolation color-interpolation-filters shape-rendering text-rendering image-rendering vector-effect paint-order transform transform-origin transform-box overflow isolation mix-blend-mode'.split())
ATTRS = PROPS | set('id class style x y x1 x2 y1 y2 dx dy width height viewBox preserveAspectRatio version d points cx cy r rx ry fx fy fr pathLength gradientUnits gradientTransform spreadMethod offset clipPathUnits maskUnits maskContentUnits patternUnits patternContentUnits patternTransform markerUnits markerWidth markerHeight refX refY orient textLength lengthAdjust startOffset method spacing rotate filterUnits primitiveUnits in in2 result stdDeviation edgeMode mode operator k1 k2 k3 k4 type values'.split())
FUNCTIONS = set('rgb rgba hsl hsla matrix matrix3d translate translatex translatey scale scalex scaley rotate skew skewx skewy'.split())
FRAGMENT = re.compile(r'#[A-Za-z_][\w.:-]*\Z')
SELECTOR = re.compile(r'[A-Za-z0-9_#.\s,>+~*\-]+\Z')
LENGTH = re.compile(r'([+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+\-]?\d+)?)(px|pt|pc|mm|cm|in)?\Z', re.I)


def invalid(message='Plik zawiera elementy, których nie obsługujemy.'):
    return ApiError('Nie można użyć SVG. '+message+' Zapisz statyczny SVG bez skryptów i zewnętrznych plików albo prześlij PNG.', code='svg_invalid')


def _local_name(name):
    if name.startswith('{'):
        namespace, local = name[1:].split('}', 1)
        return namespace, local
    return '', name


def _length(value):
    if value is None or value.strip().endswith('%'):
        return None
    match = LENGTH.fullmatch(value.strip())
    if not match:
        raise invalid('Nieprawidłowe wymiary grafiki.')
    number = float(match[1]) * {'px':1,'pt':96/72,'pc':16,'mm':96/25.4,'cm':96/2.54,'in':96}.get((match[2] or '').lower(),1)
    if not math.isfinite(number) or not 0 < number <= 10_000_000:
        raise invalid('Nieprawidłowe wymiary grafiki.')
    return number


def _viewport(root):
    box = None
    if 'viewBox' in root.attrib:
        try:
            box = [float(x) for x in re.split(r'[\s,]+',root.get('viewBox').strip())]
        except ValueError as exc:
            raise invalid('Nieprawidłowy viewBox.') from exc
        if len(box)!=4 or any(not math.isfinite(n) or abs(n)>10_000_000 for n in box) or min(box[2:])<=0:
            raise invalid('Nieprawidłowy viewBox.')
    width, height = _length(root.get('width')), _length(root.get('height'))
    if box:
        width = width if width is not None else (height*box[2]/box[3] if height is not None else box[2])
        height = height if height is not None else width*box[3]/box[2]
    if width is None or height is None:
        raise invalid('Dodaj viewBox albo dodatnią szerokość i wysokość.')
    # A finite viewBox can still derive infinite or underflowed dimensions when
    # its aspect ratio is extreme. Reject before dividing or rounding the size.
    if any(not math.isfinite(n) or not 0.000001 <= n <= 10_000_000 for n in (width,height)):
        raise invalid('Nieprawidłowe wymiary grafiki.')
    if box is None:
        root.set('viewBox',f'0 0 {width:g} {height:g}')
    scale = min(1,8192/width,8192/height,(20_000_000/(width*height))**.5)
    width,height=max(1,int(width*scale)),max(1,int(height*scale))
    root.set('width',str(width));root.set('height',str(height))
    return width,height


def _css_value(tokens, references, depth=0):
    if depth>12:
        raise invalid('Zbyt złożony styl.')
    for token in tokens:
        if token.type in ('error','at-keyword','{} block','[] block','() block'):
            raise invalid('Nieobsługiwany styl.')
        if token.type in ('number','percentage','dimension') and (not math.isfinite(token.value) or abs(token.value)>10_000_000):
            raise invalid('Wartość stylu przekracza dozwolony zakres.')
        url=None
        if token.type=='url':
            url=token.value
        elif token.type=='function':
            if token.lower_name=='url':
                args=[t for t in token.arguments if t.type not in ('whitespace','comment')]
                if len(args)!=1 or args[0].type not in ('string','hash'):
                    raise invalid('Nieprawidłowe odwołanie w stylu.')
                url=args[0].value if args[0].type=='string' else '#'+args[0].value
            elif token.lower_name in FUNCTIONS:
                _css_value(token.arguments,references,depth+1)
            else:
                raise invalid('Nieobsługiwana funkcja stylu.')
        if url is not None:
            if not FRAGMENT.fullmatch(url):
                raise invalid('Grafika odwołuje się do zewnętrznego pliku.')
            references.add(url[1:])
    return tinycss2.serialize(tokens)


def _declarations(text,references):
    result=[]
    for item in tinycss2.parse_declaration_list(text,skip_comments=True,skip_whitespace=True):
        if item.type!='declaration' or item.lower_name not in PROPS:
            raise invalid('Nieobsługiwana reguła stylu.')
        value=_css_value(item.value,references)
        result.append(f'{item.lower_name}:{value}'+('!important' if item.important else ''))
    return ';'.join(result)


def _stylesheet(text,references):
    result=[]
    for rule in tinycss2.parse_stylesheet(text,skip_comments=True,skip_whitespace=True):
        if rule.type!='qualified-rule':
            raise invalid('Zewnętrzne style, fonty i animacje nie są obsługiwane.')
        selector=tinycss2.serialize(rule.prelude).strip()
        if len(selector)>300 or not SELECTOR.fullmatch(selector):
            raise invalid('Nieobsługiwany selektor stylu.')
        result.append(selector+'{'+_declarations(rule.content,references)+'}')
    return ''.join(result)


def sanitize_svg(raw, raster_decoder=None):
    if len(raw)>MAX_SVG:
        raise ApiError('Plik SVG może mieć maksymalnie 2 MB.',413,code='svg_size')
    try:
        root=SafeET.fromstring(raw,forbid_dtd=True,forbid_entities=True,forbid_external=True)
    except (ET.ParseError,DefusedXmlException,ValueError) as exc:
        raise invalid('Nieprawidłowy XML lub niedozwolona deklaracja dokumentu.') from exc
    if _local_name(root.tag) not in ((SVG,'svg'),('','svg')):
        raise invalid('Dokument nie jest grafiką SVG.')
    width,height=_viewport(root)
    references={};identifiers={};nodes=[];embedded_pixels=0
    pending=[(root,0)]
    while pending:
        node,depth=pending.pop()
        if depth>48 or len(nodes)>=MAX_NODES or len(node.attrib)>64:
            raise invalid('Grafika jest zbyt złożona.')
        namespace,tag=_local_name(node.tag)
        if namespace not in ('',SVG) or tag not in TAGS:
            raise invalid(f'Nieobsługiwany element: {tag[:40]}.')
        node.tag='{'+SVG+'}'+tag
        nodes.append(node);refs=references[node]=set()
        # Editor metadata does not affect the graphic and often uses foreign XML.
        for child in list(node):
            if _local_name(child.tag)[1] in ('metadata','namedview'):
                node.remove(child)
        pending.extend((child,depth+1) for child in node)
        for key,value in list(node.attrib.items()):
            ns,name=_local_name(key)
            if name.lower().startswith('on') or (ns==XML and name=='base'):
                raise invalid('Skrypty i aktywne odwołania nie są obsługiwane.')
            if ns==XML and name in ('space','lang'):
                continue
            if ns not in ('',XLINK):
                # Inkscape/Illustrator editing hints are not rendered by SVG.
                del node.attrib[key];continue
            if name=='href' and ns in ('',XLINK):
                if tag=='image':
                    match=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\s]+)',value)
                    if not match or not raster_decoder:
                        raise invalid('Obrazy w SVG muszą być osadzone jako PNG, JPG lub WebP.')
                    try:
                        content=base64.b64decode(re.sub(r'\s','',match[2]),validate=True)
                        if not content.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8',b'RIFF')):
                            raise ValueError('Not raster')
                        content,w,h,ext=raster_decoder(content)
                    except (ValueError,ApiError) as exc:
                        raise invalid('Nieprawidłowy obraz osadzony.') from exc
                    embedded_pixels+=w*h
                    if embedded_pixels>20_000_000:
                        raise invalid('Osadzone zdjęcia przekraczają łącznie 20 megapikseli.')
                    value='data:image/'+('png' if ext=='png' else 'jpeg')+';base64,'+base64.b64encode(content).decode('ascii')
                elif tag not in ('use','linearGradient','radialGradient','pattern','textPath') or not FRAGMENT.fullmatch(value):
                    raise invalid('Dozwolone są tylko odwołania do elementów tego samego SVG.')
                else:
                    refs.add(value[1:])
                node.set(key,value);continue
            if name not in ATTRS or ns:
                raise invalid(f'Nieobsługiwany atrybut: {name[:40]}.')
            if name=='id':
                if not FRAGMENT.fullmatch('#'+value) or value in identifiers:
                    raise invalid('Nieprawidłowy lub powtórzony identyfikator elementu.')
                identifiers[value]=node
            elif name=='style':
                node.set(key,_declarations(value,refs))
            elif name not in ('id','class','d','points','viewBox','preserveAspectRatio','version'):
                _css_value(tinycss2.parse_component_value_list(value),refs)
        if tag=='style':
            node.text=_stylesheet(node.text or '',refs)
            if len(node):raise invalid('Nieprawidłowy blok stylów.')
    # Count expanded references as well as XML nodes: small recursive <use>
    # documents must not create unbounded work in a browser.
    memo={};active=set()
    def work(node,depth=0):
        if depth>64 or node in active:
            raise invalid('Cykliczne lub zbyt głębokie odwołania SVG.')
        if node in memo:return memo[node]
        active.add(node);total=1
        children=list(node)
        for ref in references[node]:
            if ref not in identifiers:raise invalid('Brakuje elementu wskazanego w SVG.')
            children.append(identifiers[ref])
        for child in children:
            total+=work(child,depth+1)
            if total>MAX_WORK:raise invalid('Grafika jest zbyt złożona po rozwinięciu odwołań.')
        active.remove(node);memo[node]=total;return total
    work(root)
    content=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    if len(content)>MAX_SVG:
        raise ApiError('SVG po przetworzeniu przekracza 2 MB. Zmniejsz osadzone zdjęcia.',413,code='svg_size')
    return content,width,height,'svg'
