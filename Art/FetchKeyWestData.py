"""Fetch and normalize the bounded offline Key West scene contract.

Uses public-domain USGS NAIP and separately licensed OpenStreetMap data. No
Unreal, Blender, TLS bypass, credentials, runtime service or invented coastline.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image
import shapely
from shapely.geometry import LineString, LinearRing, Point, Polygon, box
from shapely.ops import linemerge, unary_union

ORIGIN_LAT, ORIGIN_LON = 24.565, -81.77
NORTH_SCALE, EAST_SCALE = 110766.43773511577, 101302.57543811084
SPAN, SEA, GROUND, SEED = 12096.0, 0.0, 2.0, 20261031
NAIP = 'https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer'
OSM = 'https://api.openstreetmap.org/api/0.6/map.json'
RASTER_IDS = list(range(34394, 34402))
USER_AGENT = 'Aeronaut-KeyWest-Offline-Prototype/1.0 (bounded public data download)'


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def ne(lat, lon):
    return [(lat-ORIGIN_LAT)*NORTH_SCALE, (lon-ORIGIN_LON)*EAST_SCALE]


def ll(north, east):
    return [ORIGIN_LAT+north/NORTH_SCALE, ORIGIN_LON+east/EAST_SCALE]


def xy(lat, lon):
    north, east = ne(lat, lon)
    return (east, north)


def polygon_parts(g):
    if g.is_empty:
        return []
    if g.geom_type == 'Polygon':
        return [g]
    return [p for part in getattr(g, 'geoms', []) for p in polygon_parts(part)]


def line_parts(g):
    if g.is_empty:
        return []
    if g.geom_type in ('LineString', 'LinearRing'):
        return [g]
    return [p for part in getattr(g, 'geoms', []) for p in line_parts(part)]


class Fetcher:
    def __init__(self, root):
        self.root = root.resolve()
        self.out = self.root/'Art/KeyWest/Data'
        self.raw = self.out/'raw'
        self.images = self.out/'imagery'
        self.evidence = self.root/'artifacts/keywest'
        for path in (self.raw, self.images, self.evidence):
            path.mkdir(parents=True, exist_ok=True)
        self.requests = []
        self.diagnostics = {}

    def fetch(self, url, destination, limit=48*1024*1024, timeout=90):
        record = {'url': url, 'file': str(destination.relative_to(self.root)).replace('\\', '/'),
                  'retrieved_utc': utc(), 'cached': destination.exists()}
        if not destination.exists():
            last = None
            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
                    with urllib.request.urlopen(req, timeout=timeout) as response:
                        data = response.read(limit+1)
                        if len(data) > limit:
                            raise ValueError('Bounded response byte limit exceeded')
                        record['content_type'] = response.headers.get('Content-Type')
                    temporary = destination.with_suffix(destination.suffix+'.tmp')
                    temporary.write_bytes(data)
                    temporary.replace(destination)
                    last = None
                    break
                except urllib.error.HTTPError as exc:
                    body = exc.read(4096).decode(errors='replace')
                    record.update(error_status=exc.code, error=body)
                    if exc.code in (400, 413, 509):
                        self.requests.append(record)
                        raise RuntimeError(f'API {exc.code}: {body}') from exc
                    last = exc
                except (urllib.error.URLError, TimeoutError) as exc:
                    last = exc
                if last:
                    time.sleep(3*(attempt+1))
            if last:
                record['error'] = str(last)
                self.requests.append(record)
                raise last
        record.update(bytes=destination.stat().st_size, sha256=digest(destination),
                      cache_file_mtime_utc=dt.datetime.fromtimestamp(destination.stat().st_mtime,dt.timezone.utc).isoformat())
        self.requests.append(record)
        return destination

    def json_request(self, base, params, name, **kw):
        url = base+'?'+urllib.parse.urlencode(params)
        path = self.raw/name
        return json.loads(self.fetch(url, path, **kw).read_text(encoding='utf-8'))

    def osm_extract(self):
        """Official read API, adaptively bounded to its 50k-node map limit."""
        elements = {}
        areas = []
        half = SPAN/2+1500

        def tile(e0, n0, e1, n1, depth=0):
            south, west = ll(n0, e0)
            north, east = ll(n1, e1)
            bbox = ','.join(f'{v:.9f}' for v in (west, south, east, north))
            name = 'osm_'+hashlib.sha256(bbox.encode()).hexdigest()[:16]+'.json'
            print('OSM bbox', bbox, flush=True)
            try:
                result = self.json_request(OSM, {'bbox': bbox}, name, timeout=100)
            except (RuntimeError, TimeoutError, urllib.error.URLError, ValueError) as exc:
                if depth >= 4 or min(e1-e0, n1-n0) < 800:
                    raise RuntimeError('Unable to fetch real OSM geometry; no outline fallback') from exc
                em, nm = (e0+e1)/2, (n0+n1)/2
                for child in ((e0,n0,em,nm),(em,n0,e1,nm),(e0,nm,em,n1),(em,nm,e1,n1)):
                    tile(*child, depth+1)
                return
            if 'elements' not in result or result.get('error'):
                raise ValueError('OSM returned an error instead of map elements')
            for item in result['elements']:
                key = (item['type'], item['id'])
                if key not in elements or item.get('version', 0) > elements[key].get('version', 0):
                    elements[key] = item
            areas.append({'bbox_wgs84': [west,south,east,north], 'file': 'raw/'+name,
                          'element_count': len(result['elements'])})
            print('OSM cached', len(result['elements']), 'elements', flush=True)
            time.sleep(.7)

        tile(-half, -half, half, half)
        self.diagnostics['osm_extracts'] = areas
        self.complete_coastlines(elements)
        self.diagnostics['osm_element_counts'] = {
            kind: sum(k[0] == kind for k in elements) for kind in ('node','way','relation')}
        return elements

    def complete_coastlines(self, elements):
        """Follow real endpoint-connected coast ways outside the read bbox.

        A buffer alone can leave the Boca Chica coast open inside the frame.
        Fetch adjacent ways and their full nodes until every relevant component
        closes, rather than making an arbitrary straight map-edge closure.
        """
        frame=box(-SPAN/2,-SPAN/2,SPAN/2,SPAN/2)
        continuations=[]
        for iteration in range(65):
            ways={i:e for (k,i),e in elements.items() if k=='way' and e.get('tags',{}).get('natural')=='coastline'}
            nodes={i:e for (k,i),e in elements.items() if k=='node'}
            adjacency={}
            for ident,way in ways.items():
                for endpoint in (way['nodes'][0],way['nodes'][-1]):
                    adjacency.setdefault(endpoint,[]).append(ident)
            seen=set(); endpoints=[]
            for ident in ways:
                if ident in seen:
                    continue
                component=set(); pending=[ident]
                while pending:
                    current=pending.pop()
                    if current in component:
                        continue
                    component.add(current); seen.add(current)
                    for endpoint in (ways[current]['nodes'][0],ways[current]['nodes'][-1]):
                        pending.extend(i for i in adjacency[endpoint] if i not in component)
                component_ends=[n for n,refs in adjacency.items() if len(refs)==1 and refs[0] in component]
                if not component_ends:
                    continue
                lines=[LineString([xy(nodes[n]['lat'],nodes[n]['lon']) for n in ways[i]['nodes']]) for i in component]
                if shapely.MultiLineString(lines).intersects(frame):
                    endpoints.extend(component_ends)
            if not endpoints:
                self.diagnostics['osm_coast_continuations']=continuations
                return
            if iteration==64:
                raise ValueError('Coast continuation request bound reached; no invented closure')
            added=0
            for endpoint in sorted(set(endpoints)):
                node=nodes[endpoint]
                if max(abs(v) for v in xy(node['lat'],node['lon']))>35000:
                    raise ValueError('Coast continuation exceeded local 35km bound')
                adjacent=self.json_request(f'https://api.openstreetmap.org/api/0.6/node/{endpoint}/ways.json',
                                           {},f'osm-coast-node-{endpoint}-ways.json',timeout=100)
                for way in adjacent.get('elements',[]):
                    if way['type']!='way' or way.get('tags',{}).get('natural')!='coastline' or way['id'] in ways:
                        continue
                    full=self.json_request(f"https://api.openstreetmap.org/api/0.6/way/{way['id']}/full.json",
                                           {},f"osm-coast-way-{way['id']}-full.json",timeout=100)
                    for item in full.get('elements',[]):
                        key=(item['type'],item['id'])
                        if key not in elements or item.get('version',0)>elements[key].get('version',0):
                            elements[key]=item
                    continuations.append({'endpoint_node':endpoint,'way':way['id']})
                    ways[way['id']]=way;added+=1
                    print('OSM coastline continuation',way['id'],flush=True)
                    time.sleep(.7)
            if not added:
                raise ValueError('Real coastline has an unresolved endpoint inside frame; no invented closure')

    def imagery(self):
        service = self.json_request(NAIP, {'f': 'pjson'}, 'naip-service.json')
        assert 'public domain' in service['description'].lower(), 'Review NAIP rights metadata'
        assert service['maxImageWidth'] >= 2048 and service['maxImageHeight'] >= 2048
        catalog = self.json_request(NAIP+'/query', {
            'where': 'OBJECTID IN ('+','.join(map(str,RASTER_IDS))+')',
            'outFields': '*', 'returnGeometry': 'false', 'f': 'pjson'}, 'naip-catalog.json')
        rows = {r['attributes']['OBJECTID']: r['attributes'] for r in catalog.get('features', [])}
        assert set(rows) == set(RASTER_IDS), 'Pinned imagery rasters disappeared'
        for row in rows.values():
            assert row['Name'].endswith('_20230116') and row['resolution_value'] == .3
        result = []
        half, step = SPAN/2, SPAN/4
        for row in range(4):
            for col in range(4):
                n1, n0 = half-row*step, half-(row+1)*step
                e0, e1 = -half+col*step, -half+(col+1)*step
                south, west = ll(n0,e0)
                north, east = ll(n1,e1)
                bounds = [west,south,east,north]
                ident = f'naip_r{row}_c{col}'
                params = {'bbox': ','.join(f'{v:.12f}' for v in bounds), 'bboxSR': 4326,
                          'imageSR': 4326, 'size': '2048,2048', 'format': 'jpg',
                          'compressionQuality': 92, 'adjustAspectRatio': 'false',
                          'renderingRule': json.dumps({'rasterFunction':'NaturalColor'}),
                          'mosaicRule': json.dumps({'mosaicMethod':'esriMosaicLockRaster',
                                                   'lockRasterIds':RASTER_IDS}), 'f':'pjson'}
                exported = self.json_request(NAIP+'/exportImage', params, ident+'-export.json')
                extent = exported.get('extent', {})
                actual = [extent.get(k) for k in ('xmin','ymin','xmax','ymax')]
                assert exported.get('width') == 2048 and exported.get('height') == 2048
                assert all(a is not None and abs(a-b)<1e-9 for a,b in zip(actual,bounds)), 'Export extent changed'
                file = self.images/(ident+'.jpg')
                self.fetch(exported['href'], file, limit=16*1024*1024)
                with Image.open(file) as image:
                    assert image.size == (2048,2048) and image.format == 'JPEG'
                result.append({'id': ident, 'file': 'imagery/'+file.name,
                               'bounds_ne': [n0,e0,n1,e1], 'extent_wgs84': actual,
                               'pixels':[2048,2048], 'metres_per_pixel':step/2048,
                               'sha256':digest(file), 'acquisition_date':'2023-01-16',
                               'license':'US public domain', 'source':'USGS/USDA NAIP',
                               'export_metadata':'raw/'+ident+'-export.json'})
                print('NAIP', ident, file.stat().st_size, 'bytes', flush=True)
        return result


def normalize(elements, diagnostics):
    nodes = {ident:item for (kind,ident),item in elements.items() if kind=='node'}
    ways = {ident:item for (kind,ident),item in elements.items() if kind=='way'}
    relations = {ident:item for (kind,ident),item in elements.items() if kind=='relation'}
    frame = box(-SPAN/2,-SPAN/2,SPAN/2,SPAN/2)

    def coords(way):
        return [xy(nodes[i]['lat'],nodes[i]['lon']) for i in way.get('nodes', []) if i in nodes]

    def way_polygon(way):
        points = coords(way)
        if len(points)<4 or points[0]!=points[-1] or len(points)!=len(way['nodes']):
            return Polygon()
        return shapely.make_valid(Polygon(points))

    def relation_polygon(relation):
        rings = {'outer':[], 'inner':[]}
        for member in relation.get('members', []):
            if member['type']!='way' or member.get('role','outer') not in ('outer','inner',''):
                continue
            member_way = ways.get(member['ref'])
            if member_way is None:
                diagnostics['missing_relation_members'] = diagnostics.get('missing_relation_members',0)+1
                return Polygon()
            points = coords(member_way)
            if len(points)!=len(member_way['nodes']):
                return Polygon()
            if len(points)>=2:
                rings[member.get('role') or 'outer'].append(LineString(points))
        def polygonize(lines):
            if not lines:
                return Polygon()
            merged = linemerge(lines)
            return unary_union([Polygon(line.coords) for line in line_parts(merged) if line.is_ring])
        return shapely.make_valid(polygonize(rings['outer']).difference(polygonize(rings['inner'])))

    coast_ways = [w for w in ways.values() if w.get('tags',{}).get('natural')=='coastline']
    coast_lines = []
    for way in coast_ways:
        points = coords(way)
        if len(points)==len(way['nodes']) and len(points)>1:
            coast_lines.append(LineString(points))
    if not coast_lines:
        raise ValueError('No real coastline in source data')
    merged = shapely.line_merge(shapely.MultiLineString(coast_lines), directed=True)
    solid, holes, open_lines = [], [], []
    for line in line_parts(merged):
        if line.is_ring:
            (solid if LinearRing(line.coords).is_ccw else holes).extend(polygon_parts(shapely.make_valid(Polygon(line.coords))))
        else:
            open_lines.append(line)
    if not solid:
        raise ValueError('No counterclockwise land coastlines closed; reject invented geography')
    land = unary_union(solid).difference(unary_union(holes)).intersection(frame)
    water = []
    for way in ways.values():
        tags = way.get('tags',{})
        if tags.get('natural')=='water' or tags.get('landuse') in ('reservoir','basin'):
            water.extend(polygon_parts(way_polygon(way)))
    for relation in relations.values():
        if relation.get('tags',{}).get('natural')=='water':
            water.extend(polygon_parts(relation_polygon(relation)))
    land = shapely.make_valid(land.difference(unary_union(water)))
    diagnostics['coastline'] = {'ways':len(coast_ways),'closed_land_rings':len(solid),
        'closed_water_rings':len(holes),'open_chains':len(open_lines),
        'open_chain_endpoints_ne':[[[p[1],p[0]] for p in (list(g.coords)[0],list(g.coords)[-1])] for g in open_lines],
        'open_chain_frame_intersections':[not g.intersection(frame).is_empty for g in open_lines],
        'land_area_m2':land.area,'method':'Directed endpoint joining before frame clipping; no artificial boundary closures'}

    def ring_ne(ring):
        return [[round(y,4),round(x,4)] for x,y in list(ring.coords)[:-1]]

    def serialized(poly, triangle_key):
        triangles = list(shapely.constrained_delaunay_triangles(poly).geoms)
        area = sum(t.area for t in triangles)
        assert abs(area-poly.area) <= max(.03,poly.area*1e-8), 'Constrained triangle area mismatch'
        assert all(poly.covers(t) for t in triangles), 'Triangle crossed a courtyard/water hole'
        return {'outer':ring_ne(poly.exterior),'holes':[ring_ne(r) for r in poly.interiors],
                triangle_key:[ring_ne(t.exterior) for t in triangles]}

    land_records = [serialized(p.simplify(.15,preserve_topology=True),'triangles_ne') for p in polygon_parts(land) if p.area>30]
    building_records, road_records, pier_records, runway_records = [], [], [], []
    relation_members = {member['ref'] for r in relations.values() if 'building' in r.get('tags',{})
                        for member in r.get('members',[]) if member['type']=='way'}
    buildings = [(w,way_polygon(w)) for w in ways.values() if 'building' in w.get('tags',{}) and w['id'] not in relation_members]
    buildings += [(r,relation_polygon(r)) for r in relations.values() if 'building' in r.get('tags',{})]
    def number(value):
        match = re.match(r'^\s*(\d+(?:\.\d+)?)',str(value or ''))
        if not match:
            return None
        value_m = float(match[1])
        return value_m*.3048 if 'ft' in str(value).lower() or "'" in str(value) else value_m
    for item,geom in buildings:
        tags = item.get('tags',{})
        if tags.get('building')=='no':
            continue
        height, levels = number(tags.get('height')), number(tags.get('building:levels'))
        source = 'OSM height tag' if height else 'estimated from OSM levels' if levels else 'estimated low-rise default'
        height = min(80,max(2.4,height or (levels*3.1 if levels else 5.5)))
        for index,poly in enumerate(polygon_parts(shapely.make_valid(geom.intersection(frame)))):
            if poly.area<8:
                continue
            record = serialized(poly,'roof_triangles_ne')
            east,north = poly.centroid.coords[0]
            zone = 'stock_island' if east>2700 else 'old_town' if east<-1500 else 'new_town'
            if tags.get('building')=='hangar':
                zone='airport'
            record.update(id=f"{item['type']}/{item['id']}/{index}",ground_m=GROUND,
                ground_source='modeled flat island height, not surveyed DEM',height_m=height,levels=levels,
                roof_shape=tags.get('roof:shape',''),kind=tags.get('building','yes'),zone=zone,
                height_source=source,source_tags=tags)
            building_records.append(record)
    width_defaults = {'motorway':12,'trunk':11,'primary':10,'secondary':9,'tertiary':8,
                      'residential':6.5,'unclassified':6,'service':4,'footway':1.8,'path':1.8,'cycleway':2.2}
    for way in ways.values():
        tags=way.get('tags',{}); points=coords(way)
        if len(points)<2:
            continue
        line=LineString(points).intersection(frame)
        kind=tags.get('highway')
        for index,part in enumerate(line_parts(line)):
            ident=f"way/{way['id']}/{index}"
            positions=[[round(y,4),round(x,4)] for x,y in part.coords]
            if kind and kind not in ('proposed','construction','steps','corridor'):
                width=number(tags.get('width')) or width_defaults.get(kind,5)
                road_records.append(dict(id=ident,points=positions,width_m=min(30,max(1,width)),
                    bridge=tags.get('bridge','no') not in ('no','false','0'),kind=kind,name=tags.get('name',''),source_tags=tags))
            if tags.get('man_made') in ('pier','breakwater'):
                pier_records.append(dict(id=ident,points=positions,width_m=min(30,max(2,number(tags.get('width')) or 5)),kind=tags['man_made']))
            if tags.get('aeroway') in ('runway','taxiway'):
                runway_records.append(dict(id=ident,points=positions,width_m=number(tags.get('width')) or (46 if tags['aeroway']=='runway' else 18),kind=tags['aeroway'],source_tags=tags))

    landmark_specs = {
        'airport':('key west international airport',), 'southernmost_point':('southernmost point buoy','southernmost point'),
        'mallory_square':('mallory square',), 'hemingway_house':('hemingway home','hemingway house'),
        'fort_zachary_taylor':('fort zachary taylor',), 'smathers_beach':('smathers beach',),
        'stock_island':('stock island',), 'duval_street':('duval street',)}
    landmarks={}
    for key,names in landmark_specs.items():
        candidates=[]
        for (kind,ident),item in elements.items():
            name=item.get('tags',{}).get('name','').lower()
            matching=[i for i,term in enumerate(names) if term in name]
            if not matching:
                continue
            if kind=='node':
                pos=Point(xy(item['lat'],item['lon']))
            elif kind=='way':
                points=coords(item)
                if not points:
                    continue
                pos=LineString(points).centroid if len(points)>1 else Point(points[0])
            else:
                geom=relation_polygon(item)
                if geom.is_empty:
                    continue
                pos=geom.centroid
            if frame.covers(pos):
                candidates.append((min(matching),len(name),kind,ident,item,pos))
        if candidates:
            _,_,kind,ident,item,pos=min(candidates,key=lambda x:(x[0],x[1]))
            east,north=pos.coords[0];lat,lon=ll(north,east)
            landmarks[key]=dict(lat=lat,lon=lon,position_m=[north,east,GROUND],name=item['tags']['name'],
                elevation_source='modeled flat island height, not surveyed DEM',
                source=f'https://www.openstreetmap.org/{kind}/{ident}')
    assert len(landmarks)>=5, 'Fewer than five real named geographic controls were found'
    assert land.area>5_000_000 and len(building_records)>1000 and len(road_records)>100, 'Geographic extract is incomplete'
    assert any(r['kind']=='runway' for r in runway_records), 'Airport runway geometry missing'
    diagnostics['counts']={'land_polygons':len(land_records),'buildings':len(building_records),
        'roads':len(road_records),'piers':len(pier_records),'runways_and_taxiways':len(runway_records),'landmarks':len(landmarks)}
    return dict(land_polygons=land_records,buildings=building_records,roads=road_records,
                piers=pier_records,runways=runway_records,landmarks=landmarks),land


def validate_imagery(fetcher, tiles, land):
    checks=[]
    for tile in tiles:
        n0,e0,n1,e1=tile['bounds_ne'];intersection=land.intersection(box(e0,n0,e1,n1))
        with Image.open(fetcher.out/tile['file']) as im:
            rgb=np.asarray(im.convert('RGB').resize((256,256),Image.Resampling.BOX))
        xx=e0+(np.arange(256)+.5)*(e1-e0)/256
        yy=n1-(np.arange(256)+.5)*(n1-n0)/256
        east,north=np.meshgrid(xx,yy)
        mask=shapely.contains_xy(intersection,east,north)
        samples=int(mask.sum())
        empty=np.all(rgb>=251,axis=2)|np.all(rgb<=2,axis=2)
        fraction=float(empty[mask].mean()) if samples else 0
        assert fraction<.07, f"Suspect blank NAIP coverage on land: {tile['id']} {fraction:.2%}"
        checks.append(dict(tile=tile['id'],land_samples=samples,blank_land_fraction=fraction))
    fetcher.diagnostics['imagery_land_coverage']=checks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args();f=Fetcher(args.root)
    try:
        elements=f.osm_extract()
        data,land=normalize(elements,f.diagnostics)
        scene=dict(schema=1,seed=SEED,units='metres',axes={'x':'north','y':'east','z':'up'},
            origin_wgs84={'lat':ORIGIN_LAT,'lon':ORIGIN_LON},sea_level_m=SEA,span_m=SPAN,
            projection={'name':'local affine WGS84','north_scale':NORTH_SCALE,'east_scale':EAST_SCALE},
            imagery_uv={'u':'east','v':'south'},terrain={'mode':'modeled flat islands','land_height_m':GROUND,
            'bathymetry':'not measured; ocean depth must be explicitly modeled'},imagery_tiles=[],**data)
        write_json(f.out/'scene-vectors.json',scene)
        print('KEYWEST_VECTORS_READY',json.dumps(f.diagnostics['counts']),flush=True)
        scene['imagery_tiles']=f.imagery()
        validate_imagery(f,scene['imagery_tiles'],land)
        scene['ready']=True;scene['generated_utc']=utc()
        scene['provenance']={'imagery':'USGS/USDA NAIP US public domain, acquired 2023-01-16',
            'vectors':'OpenStreetMap contributors, ODbL 1.0; raw and derived geographic files retained',
            'building_heights':'OSM height/levels where present, otherwise inferred; not surveyed replicas',
            'elevation':'modeled 2m flat land; no DEM or measured bathymetry used'}
        license_url='https://opendatacommons.org/licenses/odbl/1-0/'
        f.fetch(license_url,f.out/'ODbL-1.0.html',limit=1024*1024)
        (f.out/'ATTRIBUTION.txt').write_text(
            'Aerial imagery: USGS/USDA NAIP, acquired 2023-01-16. US public domain.\n'
            'Geographic layout: © OpenStreetMap contributors. Open Database License 1.0.\n'
            'https://www.openstreetmap.org/copyright\nhttps://opendatacommons.org/licenses/odbl/1-0/\n'
            'Raw and derived geographic data are retained under ODbL. Building architecture/heights and land elevation are approximate.\n',encoding='utf-8')
        write_json(f.out/'sources.json',dict(generated_utc=utc(),requests=f.requests,
            licenses={'NAIP':'US public domain','OSM':'ODbL-1.0'},dem_used=False))
        # Publish the art-pipeline readiness marker only after provenance/license
        # files have been written successfully, using the same atomic replacement.
        write_json(f.out/'scene.json',scene)
        f.diagnostics.update(passed=True,verified_utc=utc(),scene_sha256=digest(f.out/'scene.json'),
            imagery_tiles=len(scene['imagery_tiles']),ground_mode='modeled flat land, 2m',no_tls_bypass=True)
        write_json(f.evidence/'data-validation.json',f.diagnostics)
        print('KEYWEST_DATA_READY',digest(f.out/'scene.json'),flush=True)
    except Exception as exc:
        f.diagnostics.update(passed=False,error=str(exc),verified_utc=utc(),requests=f.requests)
        write_json(f.evidence/'data-validation.json',f.diagnostics)
        raise


if __name__=='__main__':
    main()
