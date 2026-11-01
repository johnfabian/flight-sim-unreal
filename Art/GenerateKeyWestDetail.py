"""Isolated detail export; importing this module creates nothing.

Fleet generation/GEOS validation runs in Tools/KeyWestPython first. Blender
requires that exact validated file, exports only KWD_/KWB_, and never opens or
rewrites the completed Key West blend/catalog/FBX files.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)
    return value


def fleet_contract(fleet, scene_hash):
    require(type(fleet.get('schema')) is int and fleet['schema'] == 1 and fleet.get('units') == 'metres', 'Unsupported fleet schema/units')
    require(fleet.get('axes') == {'x': 'north', 'y': 'east', 'z': 'up'}, 'Fleet axes must be north/east/up')
    source = fleet.get('source_scene_sha256', '')
    require(isinstance(source, str) and len(source) == 64 and all(c in '0123456789abcdefABCDEF' for c in source), 'Fleet source hash must be 64 hex characters')
    require(source.lower() == scene_hash.lower(), 'Fleet geographic source changed')
    records = fleet.get('placements', [])
    require(isinstance(records, list) and 80 <= len(records) <= 120, 'Fleet count must be 80..120')
    ids = [r.get('id') for r in records]
    require(all(isinstance(i, str) and i.strip() for i in ids) and len(set(ids)) == len(ids), 'Fleet IDs must be unique nonempty strings')
    known = {m['asset'] for m in fleet.get('models', [])}
    require(len(known) >= 5, 'At least five original vessel types are required')
    for r in records:
        require(r.get('asset') in known, 'Unknown fleet asset')
        require(not r.get('route'), 'Translating boat traffic is outside this edition')
        require(r.get('state', r.get('fleet_state', 'anchored')) in ('anchored', 'moored'), 'Fleet must stay anchored/moored')
        require(len(r.get('position_m', [])) == 3 and len(r.get('scale', [])) == 3, 'Invalid fleet transform')
        require(all(math.isfinite(float(v)) for v in r['position_m']+r['scale']+[r['yaw_deg']]), 'Non-finite fleet transform')
        require(r['position_m'][2] == 0 and all(.8 <= v <= 1.1 for v in r['scale']), 'Invalid fleet waterline/scale')
    require(len({r['asset'] for r in records}) >= 5, 'At least five vessel types must actually be placed')
    return fleet


class Batch:
    """Double-precision recorder matching the validated boat geometry API."""
    def __init__(self):
        self.vertices = []; self.faces = []; self.slots = []; self.face_slots = []; self.colors = []

    def face(self, points, material, color=(1, 1, 1)):
        require(len(points) >= 3 and all(math.isfinite(float(v)) for p in points for v in p), 'Invalid detail face')
        start = len(self.vertices); self.vertices.extend(tuple(p) for p in points)
        self.faces.append(tuple(range(start, start+len(points))))
        if material not in self.slots:
            self.slots.append(material)
        self.face_slots.append(self.slots.index(material)); self.colors.append(tuple(color))

    def box(self, center, size, material, color=(1, 1, 1)):
        x, y, z = center; a, b, c = [v/2 for v in size]
        vs = [(x+sx*a, y+sy*b, z+sz*c) for sx, sy, sz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        for f in [(3,2,1,0),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)]:
            self.face([vs[i] for i in f], material, color)

    def rod(self, a, b, radius, material, sides=8, tip=None):
        def cross(x, y):
            return (x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0])
        def unit(x):
            length = math.sqrt(sum(v*v for v in x)); require(length > 1e-9, 'Degenerate rod')
            return tuple(v/length for v in x)
        axis = unit(tuple(y-x for x, y in zip(a, b))); u = cross(axis, (0,0,1))
        if sum(v*v for v in u) < .0001:
            u = cross(axis, (0,1,0))
        u = unit(u); v = cross(axis, u); tip = radius if tip is None else tip
        rings = [[tuple(center[k]+r*(u[k]*math.cos(j*math.tau/sides)+v[k]*math.sin(j*math.tau/sides)) for k in range(3)) for j in range(sides)] for center, r in [(a,radius),(b,tip)]]
        self.face(list(reversed(rings[0])), material); self.face(rings[1], material)
        for j in range(sides):
            k = (j+1) % sides; self.face([rings[0][j],rings[0][k],rings[1][k],rings[1][j]], material)


def input_paths(root):
    return root/'Art/KeyWest/Data/scene.json', root/'Art/KeyWestDetail/Data/fleet.json'


DOCK_MATERIALS = {
    'KWD_DockWood': dict(color=[.49,.43,.33],roughness=.83),
    'KWD_DockRubber': dict(color=[.035,.043,.041],roughness=.92),
    'KWD_DockMetal': dict(color=[.23,.26,.25],roughness=.55,metallic=.68),
}


def dock_details(scene, BatchType, export):
    """Bounded inferred fixtures on open OSM piers, never shore defenses.

    The source mixed pier mesh is left alone: separate deck/fascia skins keep
    breakwaters from acquiring wood grain. Supports are modeled below sea,
    not claimed to follow measured bathymetry. Keep every fixture inside the
    boat validator's existing buffered pier exclusion.
    """
    def inside(p, ring):
        odd = False
        for a,b in zip(ring,ring[1:]+ring[:1]):
            if (a[1]>p[1]) != (b[1]>p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
                odd = not odd
        return odd
    land_polys = [(poly, [min(p[i] for p in poly['outer']) for i in range(2)], [max(p[i] for p in poly['outer']) for i in range(2)]) for poly in scene['land_polygons']]
    def land(p):
        return any(all(lo[i]<=p[i]<=hi[i] for i in range(2)) and inside(p,poly['outer']) and not any(inside(p,h) for h in poly.get('holes',[])) for poly,lo,hi in land_polys)
    def distance(p,a,b):
        delta = [b[i]-a[i] for i in range(2)]; size = sum(v*v for v in delta)
        t = max(0,min(1,sum((p[i]-a[i])*delta[i] for i in range(2))/size)) if size else 0
        return math.hypot(*(p[i]-a[i]-t*delta[i] for i in range(2)))
    def crosses(a,b,c,d):
        turn = lambda p,q,r:(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
        return (min(a[0],b[0])<=max(c[0],d[0]) and min(c[0],d[0])<=max(a[0],b[0]) and min(a[1],b[1])<=max(c[1],d[1]) and min(c[1],d[1])<=max(a[1],b[1]) and turn(a,b,c)*turn(a,b,d)<=0 and turn(c,d,a)*turn(c,d,b)<=0)
    def shore_intersects(rect):
        lo = [min(p[i] for p in rect) for i in range(2)]; hi = [max(p[i] for p in rect) for i in range(2)]
        for poly,pmin,pmax in land_polys:
            if any(hi[i]<pmin[i] or lo[i]>pmax[i] for i in range(2)):
                continue
            for ring in [poly['outer']]+poly.get('holes',[]):
                if any(crosses(a,b,c,d) for a,b in zip(rect,rect[1:]+rect[:1]) for c,d in zip(ring,ring[1:]+ring[:1])):
                    return True
                # A small island can fit entirely between the sampled corners.
                if ring and inside(ring[0],rect):
                    return True
        return False
    bridges = [(a,b,float(r.get('width_m',6))/2+8) for r in scene['roads'] if r.get('bridge') for a,b in zip(r['points'],r['points'][1:])]
    groups = {}; sources = set(); stations = 0; skipped = 0
    # Stable hash order spreads the finite budget across real waterfronts.
    for pier in sorted(scene['piers'],key=lambda p:hashlib.sha256(str(p.get('id')).encode()).digest()):
        points = pier.get('points',[]); kind = str(pier.get('kind','')).lower()
        if kind != 'pier' or pier.get('bridge') or len(points)<2 or points[0] == points[-1]:
            skipped += 1; continue
        width = min(8,max(1.5,float(pier.get('width_m',3))))
        for a,b in zip(points,points[1:]):
            length = math.hypot(b[0]-a[0],b[1]-a[1])
            if length < 7:
                continue
            u = ((b[0]-a[0])/length,(b[1]-a[1])/length); v = (-u[1],u[0])
            for step in range(max(1,int(length/12))):
                t = (step+.5)/max(1,int(length/12)); p = (a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]))
                # Whole support/deck footprint wet-side tests, not center-only.
                half = min(5.9,length/2-.2)
                probes = [(p[0]+u[0]*x+v[0]*y,p[1]+u[1]*x+v[1]*y) for x in (-half,0,half) for y in (-width/2-.3,0,width/2+.3)]
                rect = [probes[i] for i in (0,6,8,2)]
                if shore_intersects(rect) or any(land(q) or any(distance(q,c,d)<gap for c,d,gap in bridges) for q in probes):
                    continue
                tile = tuple(math.floor(x/256) for x in p)
                batch = groups.setdefault(tile,BatchType()); origin = (tile[0]*256,tile[1]*256)
                def pos(x,y,z):
                    return (p[0]-origin[0]+u[0]*x+v[0]*y,p[1]-origin[1]+u[1]*x+v[1]*y,z)
                # Slightly proud of the legacy 1.15m deck; shallow fascia hides
                # the old infinitely thin ribbon along the dressed sections.
                batch.face([pos(-half,-width/2,1.175),pos(half,-width/2,1.175),pos(half,width/2,1.175),pos(-half,width/2,1.175)],'KWD_DockWood')
                for side in (-1,1):
                    y = side*width/2
                    face = [pos(-half,y,.91),pos(half,y,.91),pos(half,y,1.175),pos(-half,y,1.175)]
                    batch.face(face if side == -1 else list(reversed(face)),'KWD_DockWood')
                    yy = side*(width/2-.23)
                    batch.rod(pos(0,yy,-2),pos(0,yy,1.59),.18,'KWD_DockWood',sides=8)
                    batch.rod(pos(0,side*(width/2+.04),.30),pos(0,side*(width/2+.04),1.05),.14,'KWD_DockRubber',sides=8)
                    batch.rod(pos(0,side*(width/2-.55),1.175),pos(0,side*(width/2-.55),1.53),.075,'KWD_DockMetal',sides=8)
                    batch.rod(pos(-.20,side*(width/2-.55),1.47),pos(.20,side*(width/2-.55),1.47),.055,'KWD_DockMetal',sides=8)
                sources.add(str(pier.get('id'))); stations += 1
                # 230 triangles/station including closed eight-sided fixtures.
                if stations == 180:
                    break
            if stations == 180:
                break
        if stations == 180:
            break
    triangles = sum(sum(len(f)-2 for f in b.faces) for b in groups.values())
    require(triangles <= 50000,'Dock detail triangle budget exceeded')
    for (n,e),batch in sorted(groups.items()):
        label = lambda x:('p' if x>=0 else 'm')+f'{abs(x):03d}'
        export('KWD_Dock_N'+label(n)+'_E'+label(e),batch,position=(n*256,e*256,0),collision=False,derived=True,role='dock_detail',metadata=dict(cull_distance_m=900,source_pier_ids=sorted(sources),provenance_detail='Inferred deck skins/piles/fenders/bollards on open OSM piers; wet-side and bridge-corridor rejection; support bottoms modeled at -2m, not measured'))
    return dict(stations=stations,source_piers=len(sources),source_pier_ids=sorted(sources),tiles=len(groups),triangles=triangles,triangle_budget=50000,skipped_closed_or_nonpier=skipped,support_bottom_m=-2,bridge_exclusion_segments=len(bridges))


def validate_inputs(root, write_stamp=False):
    import KeyWestBoats as boats
    source, fleet_file = input_paths(root)
    fleet = fleet_contract(json.loads(fleet_file.read_text()), digest(source))
    require(fleet.get('boat_generator_sha256') == digest(root/'Art/KeyWestBoats.py'), 'Fleet boat source hash changed')
    scene = json.loads(source.read_text())
    require(scene.get('axes') == fleet['axes'] and scene.get('units') == 'metres', 'Geographic contract changed')
    geometry = boats.validate_fleet(scene, fleet)
    stamp = dict(scene_sha256=digest(source), fleet_sha256=digest(fleet_file), boat_module_sha256=digest(root/'Art/KeyWestBoats.py'), validation=geometry)
    if write_stamp:
        (fleet_file.parent/'fleet-validation.json').write_text(json.dumps(stamp, indent=2), encoding='utf-8')
    return scene, fleet, stamp


def export_details(root):
    # Blender does not add the --python script directory to sys.path.
    sys.path.insert(0, str(root/'Art'))
    import bpy
    import bmesh
    from mathutils import Matrix
    import KeyWestArchitecture as architecture
    import KeyWestBoats as boats
    import KeyWestShells as shells
    import KeyWestPalms as palms
    from GenerateKeyWest import projected_uv
    source, fleet_file = input_paths(root)
    fleet = fleet_contract(json.loads(fleet_file.read_text()), digest(source))
    stamp = json.loads((fleet_file.parent/'fleet-validation.json').read_text())
    require(stamp['scene_sha256'] == digest(source) and stamp['fleet_sha256'] == digest(fleet_file) and stamp['boat_module_sha256'] == digest(root/'Art/KeyWestBoats.py') and stamp['validation']['passed'], 'Run the external fleet validation on these exact inputs before Blender')
    scene = json.loads(source.read_text()); out = root/'Art/KeyWestDetail/Exports'; out.mkdir(parents=True, exist_ok=True)
    definitions = {**architecture.MATERIALS, **boats.MATERIALS, **DOCK_MATERIALS, **palms.MATERIALS}
    require(len(definitions) == len(architecture.MATERIALS)+len(boats.MATERIALS)+len(DOCK_MATERIALS)+len(palms.MATERIALS), 'Detail material namespace collision')
    # A factory-startup process owns this separate blend; no old .blend is opened.
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = 'METRIC'; bpy.context.scene.unit_settings.scale_length = 1
    mats = {}
    for name, spec in definitions.items():
        m = bpy.data.materials.new(name); m.diffuse_color = (*spec['color'], 1); m.use_nodes = True
        bsdf = m.node_tree.nodes.get('Principled BSDF'); bsdf.inputs['Base Color'].default_value = (*spec['color'], 1)
        bsdf.inputs['Roughness'].default_value = spec.get('roughness', .65); bsdf.inputs['Metallic'].default_value = spec.get('metallic', 0)
        if spec.get('vertex_color'):
            attr = m.node_tree.nodes.new('ShaderNodeVertexColor'); attr.layer_name = 'Color'
            mix = m.node_tree.nodes.new('ShaderNodeMixRGB'); mix.blend_type = 'MULTIPLY'; mix.inputs[0].default_value = 1; mix.inputs[1].default_value = (*spec['color'], 1)
            m.node_tree.links.new(attr.outputs['Color'], mix.inputs[2]); m.node_tree.links.new(mix.outputs[0], bsdf.inputs['Base Color'])
        mats[name] = m
    assets = []; placements = []

    def export(name, batch, position=(0,0,0), collision=False, foliage=False, derived=False, role='boat', metadata=None):
        shell = role == 'city_shell' and name.startswith('KWD_City_') and (metadata or {}).get('source_city_asset', '').startswith('KW_City_')
        require(name.startswith(('KWD_', 'KWB_')) and (not collision or shell) and batch.faces, 'Invalid new detail export')
        mesh = bpy.data.meshes.new(name); mesh.from_pydata(batch.vertices, [], batch.faces); mesh.update()
        for slot in batch.slots:
            mesh.materials.append(mats[slot])
        colors = mesh.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER'); uv = mesh.uv_layers.new(name='UVMap')
        for poly, slot, tint in zip(mesh.polygons, batch.face_slots, batch.colors):
            poly.material_index = slot
            for li in poly.loop_indices:
                colors.data[li].color = (*tint, 1)
                uv.data[li].uv = projected_uv(mesh.vertices[mesh.loops[li].vertex_index].co, poly.normal)
        if role in ('boat','palm'):
            # Weld only boats/palms for curved highlights. Open palm blades keep
            # their authored winding; BMesh preserves corner UV/color attributes.
            before = [[min(v.co[i] for v in mesh.vertices) for i in range(3)], [max(v.co[i] for v in mesh.vertices) for i in range(3)]]
            bm = bmesh.new(); bm.from_mesh(mesh)
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
            if role == 'boat':
                bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            bm.normal_update()
            curved = {'KWB_Gelcoat','KWB_Blue','KWB_Teal','KWB_Antifoul'} if role == 'boat' else {'KWD_PalmTrunk'}
            for face in bm.faces:
                face.smooth = batch.slots[face.material_index] in curved
            limit = math.cos(math.radians(35))
            for edge in bm.edges:
                adjacent = list(edge.link_faces)
                edge.smooth = (len(adjacent) == 2 and all(f.smooth for f in adjacent) and adjacent[0].material_index == adjacent[1].material_index and adjacent[0].normal.dot(adjacent[1].normal) >= limit)
            bm.to_mesh(mesh); bm.free(); mesh.update()
            after = [[min(v.co[i] for v in mesh.vertices) for i in range(3)], [max(v.co[i] for v in mesh.vertices) for i in range(3)]]
            require(max(abs(x-y) for a,b in zip(before,after) for x,y in zip(a,b)) < 1e-5, 'Boat weld changed model bounds')
            require('Color' in mesh.color_attributes and len(mesh.color_attributes['Color'].data) == len(mesh.loops) and len(mesh.uv_layers) == 1, 'Boat weld lost corner UV/color attributes')
            metadata = {**(metadata or {}), ('boat_shading' if role=='boat' else 'palm_shading'):dict(weld_distance_m=1e-6,sharp_angle_degrees=35,material_boundaries_sharp=True,analytical_winding_preserved=role=='palm')}
        ob = bpy.data.objects.new(name, mesh); bpy.context.collection.objects.link(ob); ob.location = position
        bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
        copy = mesh.copy(); ob.data = copy; copy.transform(Matrix.Diagonal((1,-1,1,1)))
        bm = bmesh.new(); bm.from_mesh(copy); bmesh.ops.reverse_faces(bm, faces=bm.faces); bm.to_mesh(copy); bm.free(); ob.location = (0,0,0)
        bpy.ops.export_scene.fbx(filepath=str(out/(name+'.fbx')), use_selection=True, object_types={'MESH'}, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', axis_forward='X', axis_up='Z', bake_space_transform=True, use_mesh_modifiers=True, mesh_smooth_type='EDGE' if role in ('boat','palm') else 'FACE', add_leaf_bones=False, bake_anim=False)
        ob.data = mesh; bpy.data.meshes.remove(copy); ob.location = position; ob.select_set(False)
        bounds = [[min(p[i] for p in batch.vertices) for i in range(3)], [max(p[i] for p in batch.vertices) for i in range(3)]]
        assets.append(dict(name=name, pivot=[0,0,0], materials=batch.slots, collision=bool(collision), foliage=bool(foliage), triangles=sum(len(f)-2 for f in batch.faces), bounds_m=bounds, dimensions_m=[bounds[1][i]-bounds[0][i] for i in range(3)], role=role, provenance='OSM-derived inferred architecture' if derived else 'Original procedural geometry', lod_policy='preserve_closed_shell', file_sha256=digest(out/(name+'.fbx')), **(metadata or {})))
        if derived:
            placements.append(dict(id=name, asset=name, position_m=list(position), yaw_deg=0, scale=[1,1,1]))

    stats = architecture.build(scene, Batch, export)
    city_shells = shells.build(scene, Batch, export)
    palm_stats = palms.build(Batch, export)
    docks = dock_details(scene,Batch,export)
    rendered_models = boats.make_models(Batch, export)
    require(len(rendered_models) == len(fleet['models']), 'Boat model count mismatch')
    for expected, actual in zip(fleet['models'], rendered_models):
        require(expected['asset'] == actual['asset'] and expected['triangles'] == actual['triangles'], 'Boat geometry/catalog mismatch')
        require(max(abs(x-y) for a,b in zip(expected['bounds_m'], actual['bounds_m']) for x,y in zip(a,b)) < .001, 'Boat export exceeds validated model bounds')
    placements.extend(fleet['placements'])
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'Art/KeyWestDetail/KeyWestDetail.blend'))
    catalog = dict(schema=1, units='metres', axes=scene['axes'], source_scene_sha256=digest(source), fleet_sha256=digest(fleet_file), material_definitions=definitions, assets=assets, placements=placements, architecture=stats, city_shells=city_shells, palms=palm_stats, waterfront=docks, fleet_statistics=fleet['statistics'], hero_cluster=fleet['hero_cluster'], source_modules={name:digest(root/'Art'/name) for name in ('GenerateKeyWestDetail.py','KeyWestArchitecture.py','KeyWestBoats.py','KeyWestShells.py','KeyWestPalms.py','GenerateKeyWest.py')})
    (out/'assets.json').write_text(json.dumps(catalog, indent=2), encoding='utf-8')
    print('AERONAUT_KEYWEST_DETAIL_ART_READY '+json.dumps(dict(assets=len(assets), architecture_triangles=stats.get('triangles'), boats=len(fleet['placements']))))


def self_test():
    h = 'a'*64
    valid = dict(schema=1, units='metres', axes={'x':'north','y':'east','z':'up'}, source_scene_sha256=h, models=[{'asset':str(i)} for i in range(6)], placements=[dict(id=str(i),asset=str(i%6),position_m=[0,0,0],scale=[1,1,1],yaw_deg=0,route=[]) for i in range(80)])
    fleet_contract(valid, h)
    for field, value in [('schema',2),('schema',True),('units','feet'),('axes',{'x':'east','y':'north','z':'up'}),('source_scene_sha256','z'*64),('source_scene_sha256','b'*64),('placements',valid['placements'][:79])]:
        broken = {**valid,field:value}
        try:
            fleet_contract(broken, h)
        except ValueError:
            pass
        else:
            raise AssertionError('Rejected fleet metadata accepted: '+field)
    duplicate = json.loads(json.dumps(valid)); duplicate['placements'][-1]['id'] = '0'
    try:
        fleet_contract(duplicate, h)
    except ValueError:
        pass
    else:
        raise AssertionError('Duplicate ID accepted')
    for replacement in [dict(id=''),dict(route=[[0,0,0],[10,0,0]]),dict(position_m=[0,0,float('nan')]),dict(scale=[1,1,2])]:
        broken = json.loads(json.dumps(valid)); broken['placements'][0].update(replacement)
        try:
            fleet_contract(broken,h)
        except ValueError:
            pass
        else:
            raise AssertionError('Unsafe fleet transform/metadata accepted')
    b = Batch(); b.rod((0,0,0),(0,0,1),.1,'test')
    require(len(b.faces) == 10 and all(math.isfinite(v) for p in b.vertices for v in p), 'Double-precision rod contract failed')
    import KeyWestBoats as boats
    require(boats.make_models(Batch,lambda *a,**k:None) == boats.make_models(boats._TestBatch,lambda *a,**k:None), 'Integration geometry differs from canonical validated boat bounds/footprints')
    fixtures = dict(land_polygons=[dict(outer=[[-10,-10],[10,-10],[10,10],[-10,10]],holes=[])],roads=[dict(bridge=True,width_m=6,points=[[80,-20],[80,20]])],piers=[dict(id='safe',kind='pier',points=[[30,0],[54,0]],width_m=4),dict(id='dry',kind='pier',points=[[-7,0],[7,0]],width_m=4),dict(id='bridge',kind='pier',points=[[70,0],[92,0]],width_m=4),dict(id='stone',kind='breakwater',points=[[30,20],[54,20]],width_m=4)])
    exports = []; dock = dock_details(fixtures,Batch,lambda name,batch,**kw:exports.append((batch,kw)))
    require(dock['source_pier_ids']==['safe'] and dock['stations']==2 and dock['triangles']<50000,'Dock wet-side/bridge/kind safety failed')
    require(all(min(v[2] for v in b.vertices)==-2 and not k['collision'] and k['role']=='dock_detail' for b,k in exports),'Dock support sea-level/collision contract failed')
    print('PASS strict fleet metadata/count/unique-ID/hash/axes gate and double-precision geometry')
    print('PASS bounded wet-side pier decks/supports; shore defense and bridge rejection')


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(); parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1]); parser.add_argument('--validate-inputs', action='store_true'); parser.add_argument('--self-test', action='store_true'); args = parser.parse_args(argv)
    if args.self_test:
        self_test()
    elif args.validate_inputs:
        validate_inputs(args.root.resolve(), True); print('AERONAUT_KEYWEST_DETAIL_FLEET_VALID')
    else:
        export_details(args.root.resolve())
