"""Offline high-resolution Key West ground tiles in a separate namespace.

--fetch uses public-domain pinned USGS/USDA NAIP and Pillow, never Blender.
--export uses only prepared, hash-verified files and Blender's bundled Python;
it never downloads. Geometry comes from existing validated OSM land triangles,
including holes. Ordinary game play must never invoke either preparation step.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from GenerateKeyWest import area, clean_ring, clip_rect, roof_triangles

SERVICE = 'https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer'
RASTER_IDS = list(range(34394, 34402))
REGIONS = (('oldtown', -1200.0, -3200.0), ('airport', -1300.0, 1350.0))
SPAN, PIXELS, HEIGHT = 614.4, 2048, 2.01
ROOT_PATH = Path('Art/KeyWestDetail/Ground')
ORIGIN = {'lat': 24.565, 'lon': -81.77}
NORTH_SCALE, EAST_SCALE = 110766.43773511577, 101302.57543811084
MAX_TRIANGLES = 100000


def require(value, message):
    if not value:
        raise ValueError(message)
    return value


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    return sha(Path(path).read_bytes())


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_bytes(json_bytes(value))
    temporary.replace(path)


def safe_url(url):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname == 'imagery.nationalmap.gov'
            and parsed.port in (None, 443) and not parsed.username and not parsed.password,
            'Only the official HTTPS USGS imagery host is allowed')
    return url


def url(base, params):
    return safe_url(base+'?'+urllib.parse.urlencode(params))


def extent(bounds):
    n0, e0, n1, e1 = bounds
    return [ORIGIN['lon']+e0/EAST_SCALE, ORIGIN['lat']+n0/NORTH_SCALE,
            ORIGIN['lon']+e1/EAST_SCALE, ORIGIN['lat']+n1/NORTH_SCALE]


def clip_land(triangles, bounds):
    """Clip already validated land triangles, never fill a polygon's holes."""
    result = []
    for triangle in triangles:
        if any(max(p[i] for p in triangle) < bounds[i] or min(p[i] for p in triangle) > bounds[i+2] for i in (0, 1)):
            continue
        piece = clip_rect(triangle, bounds)
        cleaned = []
        for point in piece:
            if not cleaned or math.dist(point, cleaned[-1]) > 1e-8:
                cleaned.append(tuple(point))
        if len(cleaned) > 1 and math.dist(cleaned[0], cleaned[-1]) < 1e-8:
            cleaned.pop()
        if len(cleaned) < 3:
            continue
        if area(cleaned) < 0:
            cleaned.reverse()
        for i in range(1, len(cleaned)-1):
            tri = [cleaned[0], cleaned[i], cleaned[i+1]]
            if area(tri) > 1e-8:
                result.append(tri)
    return result


def plan(scene):
    require(scene.get('schema') == 1 and scene.get('units') == 'metres' and
            scene.get('axes') == {'x':'north','y':'east','z':'up'}, 'Unexpected geographic schema')
    require(scene.get('origin_wgs84') == ORIGIN, 'Unexpected local origin')
    projection = scene.get('projection', {})
    require(projection.get('north_scale') == NORTH_SCALE and projection.get('east_scale') == EAST_SCALE,
            'Unexpected local projection')
    require(scene.get('terrain', {}).get('land_height_m') == 2.0, 'Ground overlay requires the prepared 2m land')
    triangles = []
    for polygon in scene['land_polygons']:
        require(polygon.get('triangles_ne'), 'Validated land triangles are required; no hole-filling fallback')
        triangles.extend(roof_triangles({'roof_triangles_ne':polygon['triangles_ne']},
                         clean_ring(polygon['outer']), [clean_ring(h) for h in polygon.get('holes', [])]))
    tiles = []
    for region, north, east in REGIONS:
        for row in range(4):
            for col in range(4):
                n1, n0 = north+(2-row)*SPAN, north+(1-row)*SPAN
                e0, e1 = east+(col-2)*SPAN, east+(col-1)*SPAN
                bounds = [n0, e0, n1, e1]
                clipped = clip_land(triangles, bounds)
                land_area = sum(area(t) for t in clipped)
                if land_area <= 1.0:
                    continue
                ident = f'{region}_r{row}_c{col}'
                tiles.append({'id':ident, 'asset':'KWD_Ground_'+ident, 'region':region,
                              'bounds_ne':bounds, 'extent_wgs84':extent(bounds), 'pixels':[PIXELS, PIXELS],
                              'nominal_metres_per_pixel':SPAN/PIXELS, 'land_area_m2':land_area,
                              'triangles_ne':clipped, 'position_m':[n0, e0, 0], 'height_m':HEIGHT})
    require(tiles and len({t['id'] for t in tiles}) == len(tiles), 'Empty or duplicate ground tile plan')
    require(sum(len(t['triangles_ne']) for t in tiles) < MAX_TRIANGLES, 'Land geometry budget exceeded')
    return tiles


def image_params(tile):
    return {'bbox':','.join(f'{v:.12f}' for v in tile['extent_wgs84']), 'bboxSR':4326,
            'imageSR':4326, 'size':f'{PIXELS},{PIXELS}', 'format':'jpg', 'compressionQuality':92,
            'adjustAspectRatio':'false', 'interpolation':'RSP_BilinearInterpolation',
            'renderingRule':json.dumps({'rasterFunction':'NaturalColor'}, separators=(',', ':')),
            'mosaicRule':json.dumps({'mosaicMethod':'esriMosaicLockRaster', 'lockRasterIds':RASTER_IDS}, separators=(',', ':')),
            'f':'pjson'}


def verify_export(value, tile):
    require(not value.get('error') and type(value.get('width')) is int and type(value.get('height')) is int
            and value['width'] == value['height'] == PIXELS, 'Wrong image export dimensions')
    actual = value.get('extent', {})
    require(actual.get('spatialReference', {}).get('wkid') == 4326, 'Export projection changed')
    box = [actual.get(k) for k in ('xmin','ymin','xmax','ymax')]
    require(all(type(a) in (int, float) and math.isfinite(a) and abs(a-b) < 1e-9
                for a, b in zip(box, tile['extent_wgs84'])), 'Export extent changed')
    safe_url(value['href'])
    return box


def verify_service(service, catalog):
    require('public domain' in service.get('description', '').lower(), 'Public-domain metadata missing')
    require(service.get('maxImageWidth', 0) >= PIXELS and service.get('maxImageHeight', 0) >= PIXELS,
            'Service image limit changed')
    natural = next((f for f in service.get('rasterFunctionInfos', []) if f.get('name') == 'NaturalColor'), {})
    require('1,2,3' in natural.get('description', '').replace(' ', ''), 'NaturalColor RGB band contract changed')
    rows = {r['attributes']['OBJECTID']:r['attributes'] for r in catalog.get('features', [])}
    require(set(rows) == set(RASTER_IDS), 'Pinned eight-raster catalog changed')
    for row in rows.values():
        require(row['Name'].endswith('_20230116') and row['resolution_value'] == .3
                and row.get('band_count') == 4 and row.get('agency') == 'USDA'
                and row.get('Year') == 2022 and row.get('acquisition_date') == 1673827200000,
                'Pinned source identity/native resolution/acquisition changed')
    return rows


def verify_native(info):
    require(info.get('pixelSizeX') == info.get('pixelSizeY') == .3 and info.get('bandCount') == 4
            and info.get('pixelType') == 'U8', 'Native raster format/resolution changed')
    bounds = info.get('extent', {})
    require(bounds.get('spatialReference', {}).get('wkid') == 26917, 'Native source projection changed')
    sizes = [(bounds.get(b, 0)-bounds.get(a, 0))/.3 for a, b in (('xmin','xmax'), ('ymin','ymax'))]
    require(all(math.isfinite(s) and s > PIXELS and abs(s-round(s)) < 1e-6 for s in sizes), 'Invalid native raster extent')
    return {'pixel_m':.3, 'native_epsg':26917, 'inferred_source_pixels':list(map(round, sizes)), 'band_count':4}


def jpeg_header(data):
    require(data[:2] == b'\xff\xd8', 'Image is not JPEG')
    pos = 2
    while pos+4 <= len(data):
        require(data[pos] == 255, 'Invalid JPEG marker')
        while pos < len(data) and data[pos] == 255:
            pos += 1
        marker = data[pos]; pos += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        length = struct.unpack_from('>H', data, pos)[0]
        require(length >= 2 and pos+length <= len(data), 'Invalid JPEG segment')
        if marker in (0xC0, 0xC1, 0xC2):
            require(length >= 8, 'Missing JPEG frame')
            precision, height, width, channels = struct.unpack_from('>BHHB', data, pos+2)
            require((width, height, channels, precision) == (PIXELS, PIXELS, 3, 8), 'JPEG frame dimensions/channels changed')
            return width, height, channels
        require(marker != 0xDA, 'JPEG frame missing before scan')
        pos += length
    raise ValueError('JPEG frame missing')


def verify_image(data, tile):
    from PIL import Image, ImageDraw
    jpeg_header(data)
    with Image.open(io.BytesIO(data)) as image:
        require(image.format == 'JPEG' and image.mode == 'RGB' and image.size == (PIXELS, PIXELS), 'Expected actual 2048px RGB JPEG')
        orientation = image.getexif().get(274)
        require(orientation in (None, 1), 'EXIF transform would misalign geography')
        image.load()
        small = image.resize((256, 256), Image.Resampling.BOX)
    # Only rasterize supplied land triangles; white/black ocean and courtyard
    # pixels must not count as missing imagery on the land we actually draw.
    mask = Image.new('L', (256, 256)); draw = ImageDraw.Draw(mask)
    n0, e0, n1, e1 = tile['bounds_ne']
    for triangle in tile['triangles_ne']:
        draw.polygon([((p[1]-e0)/(e1-e0)*256, (n1-p[0])/(n1-n0)*256) for p in triangle], fill=255)
    samples = blank = 0
    rgb_bytes = small.tobytes()
    for index, land in enumerate(mask.tobytes()):
        if land:
            rgb = rgb_bytes[index*3:index*3+3]
            samples += 1
            blank += int(min(rgb) >= 251 or max(rgb) <= 2)
    require(samples > 0 and blank/samples < .07, 'Suspect blank imagery on actual land')
    return {'rgb_mode':'RGB', 'exif_orientation':orientation, 'land_samples':samples, 'blank_land_fraction':blank/samples}


class Cache:
    """Bounded official HTTPS fetches; existing data without a digest fails closed."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.folder = self.root/ROOT_PATH/'Data'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.record_file = self.folder/'requests.json'
        self.records = json.loads(self.record_file.read_text()) if self.record_file.exists() else {}

    def get(self, request_url, relative, limit=2*1024*1024):
        safe_url(request_url)
        relative = Path(relative)
        destination = (self.root/ROOT_PATH/relative).resolve()
        require(destination.is_relative_to((self.root/ROOT_PATH).resolve()), 'Cache destination escaped namespace')
        key = relative.as_posix()
        record = self.records.get(key)
        if destination.exists() or record:
            require(destination.is_file() and record and record['url'] == request_url, 'Unrecorded/stale cache entry')
            data = destination.read_bytes()
            require(0 < len(data) <= limit and len(data) == record['bytes'] and sha(data) == record['sha256'], 'Cached source digest changed')
            return data
        error = None
        for attempt in range(3):
            try:
                request = urllib.request.Request(request_url, headers={'User-Agent':'Aeronaut-KeyWestGround-Offline/1.0'})
                started = time.monotonic()
                with urllib.request.urlopen(request, timeout=45) as response:
                    safe_url(response.geturl())
                    chunks, size = [], 0
                    while True:
                        part = response.read(min(65536, limit-size+1))
                        if not part:
                            break
                        chunks.append(part); size += len(part)
                        require(size <= limit and time.monotonic()-started < 90, 'Response byte/time bound exceeded')
                    content_type = response.headers.get('Content-Type', '')
                data = b''.join(chunks)
                require(data, 'Empty source response')
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(destination.suffix+'.tmp')
                temporary.write_bytes(data); temporary.replace(destination)
                self.records[key] = {'url':request_url, 'file':str((ROOT_PATH/relative).as_posix()),
                                     'bytes':len(data), 'sha256':sha(data), 'content_type':content_type,
                                     'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
                save_json(self.record_file, self.records)
                return data
            except urllib.error.HTTPError as exc:
                if exc.code not in (408, 429, 500, 502, 503, 504):
                    raise
                error = exc
            except (urllib.error.URLError, TimeoutError) as exc:
                error = exc
            if attempt < 2:
                time.sleep(1+attempt*2)
        raise RuntimeError('Official source request failed after three bounded attempts') from error

    def get_json(self, request_url, name):
        value = json.loads(self.get(request_url, 'Data/'+name))
        require(type(value) is dict and not value.get('error'), 'Service returned an API error')
        return value


def cached_source_proof(root):
    folder = root/'Art/KeyWest/Data'
    requests = json.loads((folder/'sources.json').read_text())['requests']
    records = []
    values = []
    for name in ('naip-service.json', 'naip-catalog.json'):
        path = folder/'raw'/name
        relative = path.relative_to(root).as_posix()
        record = next(r for r in requests if r['file'] == relative)
        require(record['bytes'] == path.stat().st_size and record['sha256'] == file_sha(path), 'Original pinned metadata changed')
        safe_url(record['url'])
        records.append(record)
        values.append(json.loads(path.read_text()))
    verify_service(*values)
    return values, records


def fetch(root):
    root = Path(root).resolve()
    source = root/'Art/KeyWest/Data/scene.json'
    source_hash = file_sha(source)
    tiles = plan(json.loads(source.read_text()))
    (old_service, old_catalog), originals = cached_source_proof(root)
    cache = Cache(root)
    service = cache.get_json(url(SERVICE, {'f':'pjson'}), 'service.json')
    params = {'where':'OBJECTID IN ('+','.join(map(str, RASTER_IDS))+')', 'outFields':'*', 'returnGeometry':'false', 'f':'pjson'}
    catalog = cache.get_json(url(SERVICE+'/query', params), 'catalog.json')
    current, old = verify_service(service, catalog), verify_service(old_service, old_catalog)
    require({i:r['Name'] for i, r in current.items()} == {i:r['Name'] for i, r in old.items()}, 'Pinned source names changed')
    native = {}
    for ident in RASTER_IDS:
        info = cache.get_json(url(SERVICE+'/'+str(ident)+'/info', {'f':'pjson'}), 'native-'+str(ident)+'.json')
        native[str(ident)] = verify_native(info)
    images = []
    for tile in tiles:
        params = image_params(tile)
        export_url = url(SERVICE+'/exportImage', params)
        metadata = cache.get_json(export_url, tile['id']+'-export.json')
        actual = verify_export(metadata, tile)
        relative = 'Textures/'+tile['id']+'.jpg'
        data = cache.get(metadata['href'], relative, 16*1024*1024)
        quality = verify_image(data, tile)
        images.append({k:v for k, v in tile.items() if k != 'triangles_ne'} | {
            'file':(ROOT_PATH/relative).as_posix(), 'bytes':len(data), 'sha256':sha(data),
            'actual_extent_wgs84':actual, 'export_url':export_url, 'image_url':metadata['href'],
            'request_params':params, 'validation':quality, 'acquisition_date':'2023-01-16',
            'program_year':2022, 'source':'USGS/USDA NAIP', 'author':'USGS / USDA', 'license':'US public domain',
            'access':'Public USGS ImageServer; no account or fee',
            'modifications':'Service NaturalColor RGB, exact WGS84 window, bilinear resampling, JPEG quality92; source unchanged'})
        print('KEYWEST_GROUND_IMAGE_READY '+tile['id'], flush=True)
    require(file_sha(source) == source_hash, 'Geographic source changed during download')
    manifest = {'schema':1, 'source_scene_sha256':source_hash, 'generator_sha256':file_sha(__file__),
                'plan_sha256':sha(json_bytes(tiles)), 'original_metadata':originals, 'native_sources':native,
                'license':{'imagery':'US public domain', 'geometry':'OpenStreetMap contributors ODbL-1.0'},
                'tiles':images, 'requests':cache.records}
    save_json(root/ROOT_PATH/'Data/imagery.json', manifest)
    return manifest


def prepared(root):
    root = Path(root).resolve()
    source = root/'Art/KeyWest/Data/scene.json'
    tiles = plan(json.loads(source.read_text()))
    manifest = json.loads((root/ROOT_PATH/'Data/imagery.json').read_text())
    require(manifest.get('schema') == 1 and manifest['source_scene_sha256'] == file_sha(source)
            and manifest['generator_sha256'] == file_sha(__file__) and manifest['plan_sha256'] == sha(json_bytes(tiles)),
            'Prepared ground input/generator/plan changed; explicitly fetch/validate first')
    require([i['id'] for i in manifest['tiles']] == [t['id'] for t in tiles], 'Prepared tile set changed')
    for relative, request in manifest['requests'].items():
        path = (root/ROOT_PATH/relative).resolve()
        require(path.is_relative_to((root/ROOT_PATH).resolve()) and
                request['file'] == (ROOT_PATH/relative).as_posix(), 'Prepared request path escaped namespace')
        safe_url(request['url'])
        require(path.is_file() and path.stat().st_size == request['bytes'] and file_sha(path) == request['sha256'],
                'Prepared source metadata digest changed')
    for tile, image in zip(tiles, manifest['tiles']):
        expected_file = (ROOT_PATH/'Textures'/(tile['id']+'.jpg')).as_posix()
        require(image['file'] == expected_file and image['bounds_ne'] == tile['bounds_ne']
                and image['pixels'] == [PIXELS, PIXELS] and image['nominal_metres_per_pixel'] == .3
                and image['request_params'] == image_params(tile), 'Prepared tile contract changed')
        require(image['export_url'] == url(SERVICE+'/exportImage', image_params(tile)) and
                all(abs(a-b) < 1e-9 for a, b in zip(image['actual_extent_wgs84'], tile['extent_wgs84'])),
                'Prepared returned extent/request URL changed')
        safe_url(image['image_url'])
        data = (root/expected_file).read_bytes()
        require(len(data) == image['bytes'] and sha(data) == image['sha256'], 'Prepared image digest changed')
        jpeg_header(data)
        require(image['validation']['rgb_mode'] == 'RGB' and image['validation']['exif_orientation'] in (None, 1)
                and image['validation']['land_samples'] > 0 and image['validation']['blank_land_fraction'] < .07,
                'Image validation missing')
    return tiles, manifest


def export(root):
    """Explicit background Blender preparation. No network and no Pillow."""
    import bpy
    import bmesh
    from mathutils import Matrix
    root = Path(root).resolve()
    tiles, manifest = prepared(root)
    out = root/ROOT_PATH/'Exports'; out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = 'METRIC'; bpy.context.scene.unit_settings.scale_length = 1
    assets, placements = [], []
    for tile, record in zip(tiles, manifest['tiles']):
        n0, e0, n1, e1 = tile['bounds_ne']
        vertices = [(p[0]-n0, p[1]-e0, HEIGHT) for tri in tile['triangles_ne'] for p in tri]
        faces = [(i, i+1, i+2) for i in range(0, len(vertices), 3)]
        mesh = bpy.data.meshes.new(tile['asset']); mesh.from_pydata(vertices, [], faces); mesh.update()
        require(all(p.normal.z > .999 for p in mesh.polygons), 'Ground face must point upward')
        uv = mesh.uv_layers.new(name='UVMap')
        for poly in mesh.polygons:
            for index in poly.loop_indices:
                p = mesh.vertices[mesh.loops[index].vertex_index].co
                uv.data[index].uv = (p.y/(e1-e0), p.x/(n1-n0))
        material_name = 'KWD_GroundTexture_'+tile['id']
        material = bpy.data.materials.new(material_name); material.use_nodes = True
        image = bpy.data.images.load(str(root/record['file']), check_existing=True)
        require(tuple(image.size) == (PIXELS, PIXELS), 'Blender image size changed')
        image.colorspace_settings.name = 'sRGB'
        image.filepath = '//Textures/'+Path(record['file']).name
        node = material.node_tree.nodes.new('ShaderNodeTexImage'); node.image = image; node.extension = 'EXTEND'
        principled = material.node_tree.nodes.get('Principled BSDF')
        material.node_tree.links.new(node.outputs['Color'], principled.inputs['Base Color'])
        principled.inputs['Roughness'].default_value = .96
        mesh.materials.append(material)
        ob = bpy.data.objects.new(tile['asset'], mesh); bpy.context.collection.objects.link(ob); ob.location = tile['position_m']
        bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
        copy = mesh.copy(); ob.data = copy; copy.transform(Matrix.Diagonal((1,-1,1,1)))
        bm = bmesh.new(); bm.from_mesh(copy); bmesh.ops.reverse_faces(bm, faces=list(bm.faces)); bm.to_mesh(copy); bm.free()
        copy.update(); require(all(p.normal.z > .999 for p in copy.polygons), 'FBX reflection winding changed')
        ob.location = (0, 0, 0)
        destination = out/(tile['asset']+'.fbx')
        bpy.ops.export_scene.fbx(filepath=str(destination), use_selection=True, object_types={'MESH'},
            apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='X', axis_up='Z',
            bake_space_transform=True, use_mesh_modifiers=True, mesh_smooth_type='FACE', add_leaf_bones=False, bake_anim=False)
        ob.data = mesh; bpy.data.meshes.remove(copy); ob.location = tile['position_m']; ob.select_set(False)
        bounds = [[min(p[i] for p in vertices) for i in range(3)], [max(p[i] for p in vertices) for i in range(3)]]
        assets.append({k:v for k, v in tile.items() if k != 'triangles_ne'} | {
            'name':tile['asset'], 'pivot':[0, 0, 0], 'bounds_m':bounds,
            'dimensions_m':[bounds[1][i]-bounds[0][i] for i in range(3)], 'triangles':len(faces),
            'materials':[material_name], 'collision':False, 'foliage':False, 'role':'ground_overlay',
            'texture':record, 'file':destination.relative_to(root).as_posix(), 'file_sha256':file_sha(destination),
            'file_bytes':destination.stat().st_size,
            'provenance':'OSM-derived validated/clipped land; USGS/USDA public-domain NAIP acquired 2023-01-16'})
        placements.append({'asset':tile['asset'], 'position_m':tile['position_m'], 'yaw_deg':0, 'scale':[1, 1, 1]})
    blend = root/ROOT_PATH/'KeyWestGround.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    catalog = {'schema':1, 'units':'metres', 'axes':{'x':'north','y':'east','z':'up'},
        'source_scene_sha256':manifest['source_scene_sha256'], 'generator_sha256':file_sha(__file__),
        'imagery_manifest_sha256':file_sha(root/ROOT_PATH/'Data/imagery.json'),
        'assets':assets, 'placements':placements, 'height_m':HEIGHT, 'nominal_metres_per_pixel':.3,
        'blender_uv0':'U=(east-e0)/(e1-e0); V=(north-n0)/(n1-n0)',
        'expected_unreal_uv0':'U=(east-e0)/(e1-e0); V=(n1-north)/(n1-n0)',
        'fbx_axis_contract':'Y reflection and face reversal exactly once; legacy FBX importer V flip',
        'world_uv_reference':'U=(WorldYcm*.01-e0)/(e1-e0); V=(n1-WorldXcm*.01)/(n1-n0)',
        'blend_file':blend.relative_to(root).as_posix(), 'blend_sha256':file_sha(blend), 'blend_bytes':blend.stat().st_size,
        'licenses':manifest['license'], 'triangle_budget':MAX_TRIANGLES}
    save_json(out/'assets.json', catalog)
    print('AERONAUT_KEYWEST_GROUND_READY '+json.dumps({'assets':len(assets), 'triangles':sum(a['triangles'] for a in assets)}))
    return catalog


def self_test():
    outer = [(0,0), (10,0), (10,10), (0,10)]
    hole = [(3,3), (7,3), (7,7), (3,7)]
    triangles = []
    for i in range(4):
        a, b, c, d = outer[i], outer[(i+1)%4], hole[(i+1)%4], hole[i]
        triangles.extend([[a,b,c], [a,c,d]])
    clipped = clip_land(triangles, (2,2,8,8))
    require(abs(sum(area(t) for t in clipped)-20) < 1e-8, 'Courtyard hole was filled')
    require(all(area(t) > 0 and all(2-1e-8 <= v <= 8+1e-8 for p in t for v in p) for t in clipped), 'Clip bounds/winding failed')
    require(clip_land(triangles, (3.1,3.1,6.9,6.9)) == [], 'Hole-only tile generated land')
    require(clip_land(triangles, (11,11,12,12)) == [], 'Ocean-only tile generated land')
    sample = {'schema':1, 'units':'metres', 'axes':{'x':'north','y':'east','z':'up'},
              'origin_wgs84':ORIGIN, 'projection':{'north_scale':NORTH_SCALE, 'east_scale':EAST_SCALE},
              'terrain':{'land_height_m':2.0}, 'land_polygons':[{'outer':[(-6000,-6000),(6000,-6000),(6000,6000),(-6000,6000)],
              'holes':[], 'triangles_ne':[[(-6000,-6000),(6000,-6000),(6000,6000)],[(-6000,-6000),(6000,6000),(-6000,6000)]]}]}
    tiles = plan(sample)
    require(len(tiles) == 32 and len({t['id'] for t in tiles}) == 32, 'Two bounded 4x4 grids failed')
    require(json_bytes(tiles) == json_bytes(plan(sample)), 'Tile plan is not deterministic')
    for tile in tiles:
        n0, e0, n1, e1 = tile['bounds_ne']
        require(abs(n1-n0-SPAN) < 1e-9 and abs(e1-e0-SPAN) < 1e-9 and tile['nominal_metres_per_pixel'] == .3, 'Native-sized grid failed')
        require(HEIGHT > 2 and HEIGHT < 2.04 and all(area(t) > 0 for t in tile['triangles_ne']), 'Overlay height/winding failed')
        params = image_params(tile)
        require(params['adjustAspectRatio'] == 'false' and params['interpolation'] == 'RSP_BilinearInterpolation'
                and json.loads(params['mosaicRule'])['lockRasterIds'] == RASTER_IDS, 'Pinned image request changed')
        metadata = {'width':PIXELS, 'height':PIXELS, 'href':SERVICE+'/test.jpg',
                    'extent':dict(zip(('xmin','ymin','xmax','ymax'), tile['extent_wgs84'])) | {'spatialReference':{'wkid':4326}}}
        verify_export(metadata, tile)
        broken = json.loads(json.dumps(metadata)); broken['extent']['xmax'] += .001
        try: verify_export(broken, tile)
        except ValueError: pass
        else: raise AssertionError('Changed export extent accepted')
        # Blender V grows north; importer flips to south without swapping east.
        for n, e, expected in ((n0,e0,(0,1)), (n1,e0,(0,0)), (n1,e1,(1,0)), (n0,e1,(1,1))):
            u, v = (e-e0)/(e1-e0), (n-n0)/(n1-n0)
            require((u, 1-v) == expected, 'Imported corner UV contract failed')
    for unsafe in ('http://imagery.nationalmap.gov/a', 'https://example.com/a', 'https://imagery.nationalmap.gov@evil.test/a'):
        try: safe_url(unsafe)
        except ValueError: pass
        else: raise AssertionError('Unofficial/insecure URL accepted')
    native = {'pixelSizeX':.3, 'pixelSizeY':.3, 'bandCount':4, 'pixelType':'U8',
              'extent':{'xmin':417522, 'ymin':2716512, 'xmax':424290, 'ymax':2723868, 'spatialReference':{'wkid':26917}}}
    require(verify_native(native)['inferred_source_pixels'] == [22560, 24520], 'Native raster metadata shape failed')
    for changed in ({**native, 'pixelSizeX':.6}, {'rasterInfo':native}):
        try: verify_native(changed)
        except ValueError: pass
        else: raise AssertionError('Changed/wrapped native metadata accepted')
    # Exercise resume and corruption handling against an in-memory HTTP stub;
    # no network requests are made by self-test.
    import tempfile
    original = urllib.request.urlopen
    calls = []
    class Response(io.BytesIO):
        headers = {'Content-Type':'application/octet-stream'}
        def geturl(self):
            return SERVICE+'/test'
    def fake_open(request, timeout):
        calls.append((request.full_url, timeout))
        return Response(b'verified source')
    try:
        urllib.request.urlopen = fake_open
        with tempfile.TemporaryDirectory(prefix='keywest-ground-test-') as temporary:
            cache = Cache(Path(temporary))
            require(cache.get(SERVICE+'/test', 'Data/test.bin') == b'verified source', 'Fresh cache failed')
            require(cache.get(SERVICE+'/test', 'Data/test.bin') == b'verified source' and len(calls) == 1,
                    'Cache unnecessarily fetched again')
            (cache.folder/'test.bin').write_bytes(b'corrupt')
            try: cache.get(SERVICE+'/test', 'Data/test.bin')
            except ValueError: pass
            else: raise AssertionError('Corrupt cached bytes accepted')
            try: cache.get(SERVICE+'/test', 'Data/large.bin', limit=3)
            except ValueError: pass
            else: raise AssertionError('Unbounded response accepted')
            require(all(timeout == 45 for _, timeout in calls), 'Request timeout missing')
    finally:
        urllib.request.urlopen = original
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print('Pillow image fixture not run; use Tools/KeyWestPython for image validation tests')
    else:
        fixture = {'bounds_ne':[0,0,10,10], 'triangles_ne':triangles}
        image = Image.new('RGB', (PIXELS,PIXELS), (255,255,255)); draw = ImageDraw.Draw(image)
        for t in triangles:
            draw.polygon([(p[1]/10*PIXELS, (10-p[0])/10*PIXELS) for p in t], fill=(70,100,55))
        data = io.BytesIO(); image.save(data, format='JPEG', quality=95)
        verify_image(data.getvalue(), fixture)  # White courtyard must be ignored.
        blank = io.BytesIO(); Image.new('RGB', (PIXELS,PIXELS), (255,255,255)).save(blank, format='JPEG')
        try: verify_image(blank.getvalue(), fixture)
        except ValueError: pass
        else: raise AssertionError('Blank land imagery accepted')
        rotated = io.BytesIO(); exif = Image.Exif(); exif[274] = 6
        image.save(rotated, format='JPEG', exif=exif)
        try: verify_image(rotated.getvalue(), fixture)
        except ValueError: pass
        else: raise AssertionError('EXIF-rotated imagery accepted')
        wrong_size = io.BytesIO(); Image.new('RGB', (2047,2048)).save(wrong_size, format='JPEG')
        try: verify_image(wrong_size.getvalue(), fixture)
        except ValueError: pass
        else: raise AssertionError('Wrong JPEG dimensions accepted')
        print('PASS RGB JPEG dimensions, land-only blank checks, white courtyard exclusion and EXIF rotation rejection')
    print('PASS deterministic 32-tile plan, pinned native-resolution request, hole-preserving clipping, height, UV corners and official HTTPS bounds')


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--self-test', action='store_true'); mode.add_argument('--fetch', action='store_true'); mode.add_argument('--export', action='store_true')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
    elif args.fetch:
        fetch(args.root)
    else:
        export(args.root)
