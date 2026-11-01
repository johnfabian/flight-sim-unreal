"""Explicit isolated Key West authoring; ordinary play never runs generation.

Outside Unreal: --environment ROOT builds a modeled shore/depth mask;
--self-test checks coordinate and route math without starting Unreal.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

DEST = '/Game/KeyWest'
SPAN = 12096.0
ROUTE = [(-1080, -300, 170), (-1080, 1300, 170), (-700, 3000, 185),
         (100, 3900, 190), (700, 2800, 200), (650, 900, 195),
         (250, -900, 190), (50, -2550, 180), (-550, -3850, 165),
         (-1600, -3900, 175), (-2350, -2850, 180), (-2250, -1100, 170),
         (-1700, 200, 165)]


def checked(value, message):
    if not value:
        raise RuntimeError(message)
    return value


def uv(north, east, bounds):
    return ((east-bounds[1])/(bounds[3]-bounds[1]),
            (bounds[2]-north)/(bounds[2]-bounds[0]))


def in_ring(p, ring):
    inside = False
    for a, b in zip(ring, ring[1:]+ring[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def on_land(p, scene):
    return any(in_ring(p, poly['outer']) and not any(in_ring(p, h) for h in poly.get('holes', [])) for poly in scene['land_polygons'])


def segment_distance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/max(1e-12, dx*dx+dy*dy)))
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def footprint_bounds(scene):
    return [(min(p[0] for p in b['outer']), min(p[1] for p in b['outer']),
             max(p[0] for p in b['outer']), max(p[1] for p in b['outer'])) for b in scene['buildings']]


def clear_ground(p, scene, bounds, margin):
    if not all(on_land((p[0]+a, p[1]+b), scene) for a, b in [(0, 0), (margin, 0), (-margin, 0), (0, margin), (0, -margin)]):
        return False
    if any(b[0]-margin < p[0] < b[2]+margin and b[1]-margin < p[1] < b[3]+margin for b in bounds):
        return False
    for line in scene['roads']+scene['runways']:
        width = line.get('width_m', 6)/2+margin
        if any(segment_distance(p, a, b) < width for a, b in zip(line['points'], line['points'][1:])):
            return False
    return True


def tower_position(scene):
    bounds = footprint_bounds(scene)
    for n in (-1300, -1380, -1460, -1220, -1540):
        for e in (1100, 1180, 1260, 1340, 1420, 1500, 1580, 1660):
            if clear_ground((n, e), scene, bounds, 16):
                return (n, e, 2.0)
    raise RuntimeError('No clear airport land patch for the modeled tower')


def load_scene(root):
    path = root/'Art/KeyWest/Data/scene.json'
    scene = json.loads(path.read_text(encoding='utf-8'))
    checked(scene['schema'] == 1 and scene['axes'] == {'x': 'north', 'y': 'east', 'z': 'up'}, 'Geographic schema/axes mismatch')
    checked(scene['span_m'] == SPAN and len(scene['imagery_tiles']) == 16, 'Complete 16-tile geographic input is required')
    for tile in scene['imagery_tiles']:
        file = root/'Art/KeyWest/Data'/tile['file']
        checked(file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() == tile['sha256'], 'Missing/changed NAIP tile '+tile['id'])
        b = tile['bounds_ne']
        checked(len(b) == 4 and abs(b[2]-b[0]-3024) < .01 and abs(b[3]-b[1]-3024) < .01, 'Incorrect returned tile extent')
    checked(len(scene['landmarks']) >= 5 and scene['land_polygons'] and scene['buildings'], 'Required controls/geometry missing')
    return scene


def prepare_environment(root):
    from PIL import Image, ImageDraw, ImageFilter, ImageChops
    scene = load_scene(root); size = 1024
    land = Image.new('L', (size, size))
    def ring(points):
        return [(round(a*(size-1)), round(b*(size-1))) for a, b in (uv(*p, (-SPAN/2, -SPAN/2, SPAN/2, SPAN/2)) for p in points)]
    for poly in scene['land_polygons']:
        layer = Image.new('L', land.size); draw = ImageDraw.Draw(layer)
        draw.polygon(ring(poly['outer']), fill=255)
        for hole in poly.get('holes', []):
            draw.polygon(ring(hole), fill=0)
        land = ImageChops.lighter(land, layer)
    near = land.filter(ImageFilter.GaussianBlur(22))
    foam = land.filter(ImageFilter.GaussianBlur(2.5))
    depth = near.point(lambda v: max(0, min(255, 255-v*1.8)))
    output = root/'Art/KeyWest/Exports/shore-model.png'; output.parent.mkdir(parents=True, exist_ok=True)
    Image.merge('RGB', (foam, depth, near)).save(output)
    (output.parent/'environment-model.json').write_text(json.dumps({
        'mode': 'modeled flat sand/seagrass seabed, not surveyed bathymetry',
        'bed_elevation_m': -6, 'mask_span_m': SPAN, 'mask_uv': 'u=east,v=south',
        'shore_blur_m': 22*SPAN/size,
        'source_scene_sha256': hashlib.sha256((root/'Art/KeyWest/Data/scene.json').read_bytes()).hexdigest()
    }, indent=2), encoding='utf-8')
    print('AERONAUT_KEYWEST_ENVIRONMENT_READY '+str(output))


def apply_capture_views(u, scene):
    scene.set_editor_property('attribution_line1', '\u00a9 OpenStreetMap contributors | openstreetmap.org/copyright')
    scene.set_editor_property('attribution_line2', 'Imagery: USGS/USDA NAIP, 2023-01-16, public domain')
    duration = scene.get_editor_property('tour_duration'); views = []
    for seconds, camera, location, target, fov in [(0, 0, None, None, 68),
        (6, 1, None, None, 78), (duration*.56, 0, (-1050, -3890, 95), (-1300, -3370, 8), 68),
        (duration*.22, 0, (-800, 4250, 110), (-320, 3820, 8), 68),
        (duration*.7, 0, (-400, 0, 6700), (-400, 0, 0), 80)]:
        view = u.CoastalCaptureView(); view.set_editor_property('tour_seconds', seconds); view.set_editor_property('camera_mode', camera)
        view.set_editor_property('field_of_view', fov); view.set_editor_property('world_camera', location is not None)
        if location:
            checked(math.sqrt(sum(v*v for v in location))<7150, 'Capture exceeds preserved sky margin')
            view.set_editor_property('camera_location', u.Vector(*(v*100 for v in location))); view.set_editor_property('camera_target', u.Vector(*(v*100 for v in target)))
        views.append(view)
    scene.set_editor_property('capture_views', views)


def author(root):
    import unreal as u
    if '-KeyWestViewsOnly' in u.SystemLibrary.get_command_line().split():
        levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
        checked(levels.load_level(DEST+'/KeyWest'), 'Key West map missing')
        scene = checked(next((a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors() if isinstance(a, u.CoastalScene)), None), 'Key West scene missing')
        apply_capture_views(u, scene)
        sun_arg = next((a.split('=', 1)[1] for a in u.SystemLibrary.get_command_line().split() if a.startswith('-KeyWestSun=')), None)
        if sun_arg is not None:
            value = float(sun_arg); checked(math.isfinite(value) and .5 <= value <= 8, 'Invalid Key West sun intensity')
            lights = [a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors() if isinstance(a, u.DirectionalLight)]
            checked(len(lights) == 1, 'Expected one Key West directional light')
            lights[0].light_component.set_intensity(value)
            u.log('AERONAUT_KEYWEST_SUN '+str(value))
        sky_arg = next((a.split('=', 1)[1] for a in u.SystemLibrary.get_command_line().split() if a.startswith('-KeyWestSky=')), None)
        if sky_arg is not None:
            value = float(sky_arg); checked(math.isfinite(value) and .1 <= value <= 2, 'Invalid Key West skylight intensity')
            lights = [a for a in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors() if isinstance(a, u.SkyLight)]
            checked(len(lights) == 1, 'Expected one Key West skylight')
            lights[0].light_component.set_intensity(value)
            u.log('AERONAUT_KEYWEST_SKY '+str(value))
        checked(levels.save_current_level(), 'Key West view save failed')
        u.log('AERONAUT_KEYWEST_VIEWS_READY'); return
    if '-KeyWestReflections' in u.SystemLibrary.get_command_line().split():
        levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
        checked(levels.load_level(DEST+'/KeyWest'), 'Key West map missing')
        u.ShowcaseEditor.build_reflections()
        checked(levels.save_current_level(), 'Key West reflection save failed')
        u.log('AERONAUT_KEYWEST_REFLECTIONS_READY'); return
    scene_data = load_scene(root); source = root/'Art/KeyWest/Data/scene.json'
    catalog = json.loads((root/'Art/KeyWest/Exports/assets.json').read_text(encoding='utf-8'))
    checked(catalog['source_scene_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest(), 'Regenerate art from the exact completed scene.json')
    checked(catalog['axes'] == scene_data['axes'], 'Art geographic axes mismatch')
    checked((root/'Art/KeyWest/Exports/shore-model.png').is_file(), 'Run environment preparation first')
    args = u.SystemLibrary.get_command_line().split()
    rebuild = '-KeyWestRebuild' in args; materials_only = '-KeyWestMaterialsOnly' in args
    refresh = '-KeyWestMaterials' in args or rebuild or materials_only
    tools = u.AssetToolsHelpers.get_asset_tools(); edit = u.MaterialEditingLibrary
    actors = u.get_editor_subsystem(u.EditorActorSubsystem); levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    for folder in ('', '/Meshes', '/Materials', '/Textures'):
        u.EditorAssetLibrary.make_directory(DEST+folder)
    sys.path.insert(0, str(root/'Scripts'))
    from showcase_material_api import node, scalar, color, prop, link, sample, custom, multiply
    from showcase_water import _normal_code, _VALUE_NOISE

    def existing(path):
        return u.load_asset(path) if u.EditorAssetLibrary.does_asset_exist(path) else None

    def save(asset):
        checked(asset.get_path_name().startswith(DEST+'/'), 'Refusing to save an old/shared asset')
        checked(u.EditorAssetLibrary.save_loaded_asset(asset), 'Asset save failed '+asset.get_name())

    def texture(file, name, linear=False):
        path = DEST+'/Textures/'+name; tex = existing(path)
        if not tex or refresh:
            task = u.AssetImportTask(); task.filename = str(file); task.destination_path = DEST+'/Textures'; task.destination_name = name
            task.automated = True; task.replace_existing = True; task.save = True
            tools.import_asset_tasks([task]); tex = checked(u.load_asset(path), 'Texture import failed '+name)
            tex.set_editor_property('max_texture_size', 2048)
            tex.set_editor_property('address_x', u.TextureAddress.TA_CLAMP); tex.set_editor_property('address_y', u.TextureAddress.TA_CLAMP)
            if linear:
                tex.set_editor_property('srgb', False); tex.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_MASKS)
            save(tex)
        return tex

    def material(name, build, instanced=False):
        path = DEST+'/Materials/M_'+name; m = existing(path)
        if m and not refresh:
            return m
        if not m:
            m = tools.create_asset('M_'+name, DEST+'/Materials', u.Material, u.MaterialFactoryNew())
        checked(m, 'Material creation failed '+name)
        for expression in list(edit.get_material_expressions(m)):
            edit.delete_material_expression(m, expression)
        checked(not edit.get_material_expressions(m), 'Material graph did not clear '+name)
        m.set_editor_property('used_with_instanced_static_meshes', instanced)
        build(m)
        if name == 'Water':
            outputs = [e for e in edit.get_material_expressions(m) if isinstance(e, u.MaterialExpressionSingleLayerWaterMaterialOutput)]
            checked(len(outputs) == 1, 'Key West water requires exactly one Single Layer Water output')
        errors = list(edit.recompile_material(m))
        checked(not errors, 'Material compilation failed '+name+': '+'; '.join(str(e) for e in errors))
        save(m)
        return m

    mats = {}
    for name, definition in catalog['material_definitions'].items():
        def build(m, d=definition, material_name=name):
            m.set_editor_property('two_sided', d.get('two_sided', False)); base = color(m, d['color'])
            if d.get('vertex_color'):
                base = multiply(m, base, node(m, u.MaterialExpressionVertexColor))
            if material_name in ('KW_Wall', 'KW_Roof'):
                base = multiply(m, base, scalar(m, .84 if material_name == 'KW_Wall' else .74))
                p = node(m, u.MaterialExpressionWorldPosition)
                if material_name == 'KW_Roof':
                    normal = node(m, u.MaterialExpressionVertexNormalWS)
                    detail = custom(m, '''
float2 p=P.xy*.01;
float2 h=N.xy; h=length(h)>.1?normalize(h):float2(1,0);
float c=dot(p,float2(-h.y,h.x))/.55;
float aa=max(fwidth(c),.001);
float seam=(1-smoothstep(.012,.012+aa*1.5,abs(frac(c+.5)-.5)))*(1-smoothstep(.3,1,aa));
float weather=.96+.04*sin(p.x*.11+sin(p.y*.07));
return saturate(weather-.10*seam);
''', {'P': p, 'N': normal}, u.CustomMaterialOutputType.CMOT_FLOAT1)
                else:
                    detail = custom(m, '''
float c=P.z*.01/.22, aa=max(fwidth(c),.001);
float seam=(1-smoothstep(.02,.02+aa*1.5,abs(frac(c+.5)-.5)))*(1-smoothstep(.3,1,aa));
return .98-.045*seam;
''', {'P': p}, u.CustomMaterialOutputType.CMOT_FLOAT1)
                base = multiply(m, base, detail)
            if d.get('texture_file'):
                tex = texture(root/Path(d['texture_file']), material_name.replace('KW_', 'T_'))
                b = d['bounds_ne']; p = node(m, u.MaterialExpressionWorldPosition)
                code = f'return float2((P.y*0.01-({b[1]:.9f}))/{b[3]-b[1]:.9f},({b[2]:.9f}-P.x*0.01)/{b[2]-b[0]:.9f});'
                # NAIP already contains sunlight and shadows; lower its surface
                # albedo so fixed scene lighting does not wash those values out.
                base = multiply(m, sample(m, tex, custom(m, code, {'P': p}, u.CustomMaterialOutputType.CMOT_FLOAT2)), scalar(m, .48))
            prop(base, u.MaterialProperty.MP_BASE_COLOR)
            prop(scalar(m, d.get('roughness', .8)), u.MaterialProperty.MP_ROUGHNESS)
            prop(scalar(m, d.get('metallic', 0)), u.MaterialProperty.MP_METALLIC)
        mats[name] = material(name, build, True)
    shore = texture(root/'Art/KeyWest/Exports/shore-model.png', 'T_ShoreModel', True)

    def coast(m, p):
        coord = custom(m, f'return float2((P.y+{SPAN*50})/{SPAN*100},({SPAN*50}-P.x)/{SPAN*100});', {'P': p}, u.CustomMaterialOutputType.CMOT_FLOAT2)
        return sample(m, shore, coord)

    def water(m):
        m.set_editor_property('shading_model', u.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
        m.set_editor_property('blend_mode', u.BlendMode.BLEND_OPAQUE); m.set_editor_property('tangent_space_normal', False)
        p = node(m, u.MaterialExpressionWorldPosition); time = node(m, u.MaterialExpressionTime); depth = node(m, u.MaterialExpressionPixelDepth)
        mask = coast(m, p)
        macro_uv = custom(m, 'return P.xy*.01/180.0;', {'P': p}, u.CustomMaterialOutputType.CMOT_FLOAT2)
        detail_uv = custom(m, 'return P.xy*.01/9.0+Time*float2(.017,.009);', {'P': p, 'Time': time}, u.CustomMaterialOutputType.CMOT_FLOAT2)
        macro = custom(m, _VALUE_NOISE, {'UV': macro_uv}, u.CustomMaterialOutputType.CMOT_FLOAT1)
        breakup = custom(m, _VALUE_NOISE, {'UV': detail_uv}, u.CustomMaterialOutputType.CMOT_FLOAT1)
        prop(custom(m, _normal_code(), {'P': p, 'Time': time, 'Depth': depth, 'Macro': macro, 'Breakup': breakup}), u.MaterialProperty.MP_NORMAL)
        prop(custom(m, 'return lerp(float3(.018,.105,.115),float3(.010,.040,.065),Mask.g)*(0.9+.16*Macro);', {'Mask': mask, 'Macro': macro}), u.MaterialProperty.MP_BASE_COLOR)
        prop(custom(m, 'return .27+.07*smoothstep(50000,350000,Depth);', {'Depth': depth}, u.CustomMaterialOutputType.CMOT_FLOAT1), u.MaterialProperty.MP_ROUGHNESS)
        prop(scalar(m, .25), u.MaterialProperty.MP_SPECULAR); prop(scalar(m, .22), u.MaterialProperty.MP_OPACITY)
        output = node(m, u.MaterialExpressionSingleLayerWaterMaterialOutput)
        link(custom(m, 'return lerp(float3(.0013,.0028,.0023),float3(.0003,.0008,.0012),Mask.g);', {'Mask': mask}), output, 'ScatteringCoefficients')
        link(custom(m, 'return lerp(float3(.0025,.00045,.00028),float3(.012,.0045,.0028),Mask.g);', {'Mask': mask}), output, 'AbsorptionCoefficients')
        link(scalar(m, .15), output, 'PhaseG'); link(color(m, (.85, .95, .92)), output, 'ColorScaleBehindWater')
    water_mat = material('Water', water)

    def bottom(m):
        p = node(m, u.MaterialExpressionWorldPosition); mask = coast(m, p)
        grain = custom(m, 'float2 q=P.xy*.01; return .5+.18*sin(q.x*.11+sin(q.y*.08)*1.4)+.12*sin(q.y*.037+q.x*.019);', {'P': p}, u.CustomMaterialOutputType.CMOT_FLOAT1)
        prop(custom(m, 'return lerp(float3(.12,.19,.09),float3(.54,.49,.30),smoothstep(.35,.7,Grain))*(1-.55*Mask.g);', {'Grain': grain, 'Mask': mask}), u.MaterialProperty.MP_BASE_COLOR)
        prop(scalar(m, .95), u.MaterialProperty.MP_ROUGHNESS)
    bottom_mat = material('ModeledSeabed', bottom)
    if materials_only:
        u.log('AERONAUT_KEYWEST_MATERIALS_READY'); return

    meshes = {}
    for spec in catalog['assets']:
        name = spec['name']; checked(name.startswith('KW_'), 'Refusing non-KeyWest mesh import')
        path = DEST+'/Meshes/'+name; mesh = existing(path)
        if not mesh or rebuild:
            if mesh:
                checked(u.EditorAssetLibrary.delete_asset(path), 'Could not replace KeyWest mesh '+name)
            task = u.AssetImportTask(); task.filename = str(root/'Art/KeyWest/Exports'/(name+'.fbx')); task.destination_path = DEST+'/Meshes'; task.destination_name = name
            task.automated = True; task.replace_existing = True; task.replace_existing_settings = True; task.save = True; task.factory = u.FbxFactory()
            options = u.FbxImportUI(); options.import_mesh = True; options.import_textures = False; options.import_materials = False
            options.set_editor_property('automated_import_should_detect_type', False); options.mesh_type_to_import = u.FBXImportType.FBXIT_STATIC_MESH
            data = options.static_mesh_import_data
            for key, value in {'combine_meshes': True, 'generate_lightmap_u_vs': False, 'auto_generate_collision': False, 'convert_scene': True, 'convert_scene_unit': True, 'remove_degenerates': False}.items():
                data.set_editor_property(key, value)
            data.set_editor_property('vertex_color_import_option', u.VertexColorImportOption.REPLACE)
            data.set_editor_property('normal_import_method', u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
            task.options = options; tools.import_asset_tasks([task]); mesh = checked(u.load_asset(path), 'FBX import failed '+name)
            u.ShowcaseEditor.configure_geographic_mesh(mesh, spec['collision'], spec['foliage'], spec['lod_policy'] == 'preserve_closed_shell')
            for slot, matname in enumerate(spec['materials']):
                mesh.set_material(slot, mats[matname])
            save(mesh)
        dim = u.ShowcaseEditor.mesh_dimensions(mesh); expected = spec['dimensions_m']
        checked(max(abs(v-e*100) for v, e in zip((dim.x, dim.y, dim.z), expected)) < 3, 'Geographic FBX scale/axes mismatch '+name)
        center = mesh.get_bounds().origin
        expected_center = [(spec['bounds_m'][0][j]+spec['bounds_m'][1][j])*50 for j in range(3)]
        checked(max(abs(v-e) for v, e in zip((center.x, center.y, center.z), expected_center)) < 3, 'Geographic FBX pivot/orientation mismatch '+name)
        meshes[name] = mesh
    map_path = DEST+'/KeyWest'
    if existing(map_path) and not rebuild:
        u.log('AERONAUT_KEYWEST_CONTENT_READY existing map preserved'); return
    checked(levels.new_level(map_path), 'Could not create Key West map')
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world(); settings = world.get_world_settings()
    mode = checked(u.load_class(None, '/Game/Showcase/Blueprints/BP_CoastalGameMode.BP_CoastalGameMode_C'), 'Preserved aircraft game mode missing')
    settings.set_editor_property('default_game_mode', mode); settings.set_editor_property('force_no_precomputed_lighting', True)

    def actor(label, mesh, position, scale=(1, 1, 1), yaw=0, collision=False, material_override=None):
        a = actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector(*(v*100 for v in position)), u.Rotator(yaw=yaw))
        checked(a, 'Actor creation failed '+label); a.set_actor_label(label)
        c = a.static_mesh_component; c.set_static_mesh(mesh); c.set_mobility(u.ComponentMobility.STATIC)
        c.set_collision_profile_name('BlockAll' if collision else 'NoCollision')
        c.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS if collision else u.CollisionEnabled.NO_COLLISION)
        a.set_actor_enable_collision(collision); a.set_actor_scale3d(u.Vector(*scale))
        if material_override:
            c.set_material(0, material_override)
        return a

    specs = {s['name']: s for s in catalog['assets']}; geographic = {}; groups = {}
    sources = []; land_actors = []
    for placement in catalog['placements']:
        spec = specs[placement['asset']]
        if spec['role'] == 'palm':
            groups.setdefault(spec['name'], []).append(placement); continue
        a = actor(spec['name'], meshes[spec['name']], placement['position_m'], placement['scale'], placement['yaw_deg'], spec['collision'])
        geographic[spec['name']] = a
        if spec['collision']:
            sources.append(a)
        if spec['role'] == 'land':
            land_actors.append((spec, a))
    for name, placements in groups.items():
        a = actors.spawn_actor_from_class(u.InstancedScenery, u.Vector()); a.set_actor_label(name+' roadside palms')
        a.set_editor_property('allow_density_scaling', True)
        c = a.instances; c.set_static_mesh(meshes[name]); c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        c.set_cull_distances(100000, 180000); c.set_cast_shadow(True)
        c.add_instances([u.Transform(location=u.Vector(*(v*100 for v in p['position_m'])), rotation=u.Rotator(yaw=p['yaw_deg']), scale=u.Vector(*p['scale'])) for p in placements], False, False)
    plane = checked(u.load_asset('/Engine/BasicShapes/Plane'), 'Engine plane missing')
    ocean = actor('Key West ocean - sea level', plane, (0, 0, 0), (16000, 16000, 1), material_override=water_mat)
    ocean.static_mesh_component.set_cast_shadow(False)
    bed = actor('Modeled sand and seagrass bottom - not surveyed', plane, (0, 0, -6), (16000, 16000, 1), material_override=bottom_mat)
    bed.static_mesh_component.set_cast_shadow(False)
    sphere = checked(u.load_asset('/Engine/BasicShapes/Sphere'), 'Engine sky sphere missing')
    sky_material = checked(u.load_asset('/Game/Showcase/Materials/M_Sky'), 'Preserved sky material missing')
    sky_texture = checked(u.load_asset('/Game/Showcase/Textures/Sky'), 'Preserved HDR sky missing')
    sky = actor('Preserved coastal cloud sky', sphere, (0, 0, 0), (15000, 15000, 15000), material_override=sky_material)
    sky.static_mesh_component.set_cast_shadow(False); sky.static_mesh_component.set_mobility(u.ComponentMobility.MOVABLE)
    sun = actors.spawn_actor_from_class(u.DirectionalLight, u.Vector(), u.Rotator(pitch=-38, yaw=-35))
    sun.set_actor_label('Fixed Key West sun - movable conventional shadows')
    light = sun.light_component; light.set_mobility(u.ComponentMobility.MOVABLE); light.set_intensity(3.2)
    light.set_light_color(u.LinearColor(1, .91, .79)); light.set_editor_property('dynamic_shadow_distance_movable_light', 65000)
    light.set_editor_property('dynamic_shadow_cascades', 3)
    ambient = actors.spawn_actor_from_class(u.SkyLight, u.Vector()); ambient.set_actor_label('Preserved HDR ambient - movable')
    ambient.light_component.set_mobility(u.ComponentMobility.MOVABLE)
    ambient.light_component.set_editor_property('source_type', u.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
    ambient.light_component.set_editor_property('cubemap', sky_texture); ambient.light_component.set_intensity(.45)
    fog = actors.spawn_actor_from_class(u.ExponentialHeightFog, u.Vector(0, 0, 1500))
    fog.component.set_editor_property('fog_density', .0013); fog.component.set_editor_property('fog_height_falloff', .12)
    fog.component.set_fog_inscattering_color(u.LinearColor(.55, .65, .69))
    capture = actors.spawn_actor_from_class(u.SphereReflectionCapture, u.Vector(0, 0, 5000))
    capture.capture_component.set_editor_property('influence_radius', 12000000)
    capture.capture_component.set_editor_property('reflection_source_type', u.ReflectionSourceType.SPECIFIED_CUBEMAP)
    capture.capture_component.set_editor_property('cubemap', sky_texture)
    scene = actors.spawn_actor_from_class(u.CoastalScene, u.Vector()); scene.set_actor_label('Key West flight scene and geographic tour')
    scene.set_editor_property('region_label', 'KEY WEST  /  FLORIDA KEYS')
    scene.set_editor_property('briefing_label', 'K E Y   W E S T   /   S T O C K   I S L A N D')
    scene.set_editor_property('briefing_title', 'The Keys are calling.')
    scene.set_editor_property('briefing_subtitle', 'Island streets, tropical shallows and open sky.')
    scene.set_editor_property('start_label', 'ENTER / A    FLY KEY WEST'); scene.set_editor_property('evidence_subdirectory', 'KeyWest')
    scene.set_editor_property('flight_bounds', u.Vector(500000, 500000, 95000))
    scene.set_editor_property('airborne_spawn', u.Vector(*(v*100 for v in ROUTE[0]))); scene.set_editor_property('spawn_rotation', u.Rotator(yaw=90))
    spline = scene.tour; spline.clear_spline_points(False)
    for point in ROUTE:
        spline.add_spline_point(u.Vector(*(v*100 for v in point)), u.SplineCoordinateSpace.WORLD, False)
    spline.set_closed_loop(True, True)
    duration = spline.get_spline_length()/100/60; scene.set_editor_property('tour_duration', duration)
    checked(scene.validate_tour(6000), 'Key West tour bounds/60m swept clearance failed')
    scene.set_editor_property('terrain_actor', land_actors[0][1]); scene.set_editor_property('collision_sources', sources)

    # Actual OSM building geometry and explicit target actors make native checks
    # independent of the sea floor and the flight-bounds early-out.
    building = max((b for b in scene_data['buildings'] if b.get('roof_triangles_ne') and all(abs(v)<4500 for p in b['outer'] for v in p)), key=lambda b: abs(sum(a[0]*c[1]-c[0]*a[1] for a, c in zip(b['outer'], b['outer'][1:]+b['outer'][:1]))))
    tri = max(building['roof_triangles_ne'], key=lambda t: abs((t[1][0]-t[0][0])*(t[2][1]-t[0][1])-(t[1][1]-t[0][1])*(t[2][0]-t[0][0])))
    bp = [sum(p[j] for p in tri)/3 for j in range(2)]; center = [sum(p[j] for p in building['outer'])/len(building['outer']) for j in range(2)]
    label = lambda v: ('p' if v>=0 else 'm')+f'{abs(v):03d}'
    city_name = 'KW_City_N'+label(math.floor(center[0]/catalog['tile_size_m']))+'_E'+label(math.floor(center[1]/catalog['tile_size_m']))
    building_actor = checked(geographic.get(city_name), 'Building probe tile missing')
    tower_p = tower_position(scene_data)
    tower = actor('Modeled airport tower - inferred architecture and placement', meshes['KW_AirportTower'], tower_p, collision=True)
    sources.append(tower); scene.set_editor_property('collision_sources', sources)
    gp = None; bounds = footprint_bounds(scene_data)
    for dx, dy in [(30, 0), (-30, 0), (0, 30), (0, -30), (45, 30), (-45, -30)]:
        p = (tower_p[0]+dx, tower_p[1]+dy)
        if clear_ground(p, scene_data, bounds, 5):
            gp = p; break
    checked(gp, 'No clear geographic terrain test point')
    terrain_actor = next((a for spec, a in land_actors if spec['bounds_ne'][0]<gp[0]<spec['bounds_ne'][2] and spec['bounds_ne'][1]<gp[1]<spec['bounds_ne'][3]), None)
    checked(terrain_actor, 'Terrain probe tile missing')

    def probe(name, target, start, end):
        p = u.CoastalCollisionProbe(); p.set_editor_property('name', name); p.set_editor_property('target', target)
        p.set_editor_property('start', u.Vector(*(v*100 for v in start))); p.set_editor_property('end', u.Vector(*(v*100 for v in end)))
        return p
    scene.set_editor_property('collision_probes', [probe('Geographic land collision', terrain_actor, (*gp, 15), (*gp, 2.4)),
        probe('Actual footprint building collision', building_actor, (*bp, 95), (*bp, 4)),
        probe('Modeled airport tower collision', tower, (tower_p[0], tower_p[1], 35), (tower_p[0], tower_p[1], 10))])
    scene.set_editor_property('wing_probe', probe('Airport tower wing-only collision', tower, (tower_p[0]-8, tower_p[1]+4, 6), (tower_p[0], tower_p[1]+4, 6)))
    apply_capture_views(u, scene)
    controls = []
    for key, landmark in scene_data['landmarks'].items():
        north = (landmark['lat']-scene_data['origin_wgs84']['lat'])*scene_data['projection']['north_scale']
        east = (landmark['lon']-scene_data['origin_wgs84']['lon'])*scene_data['projection']['east_scale']
        checked(math.hypot(north-landmark['position_m'][0], east-landmark['position_m'][1]) < .05, 'Geographic control failed '+key)
        marker = actors.spawn_actor_from_class(u.TargetPoint, u.Vector(north*100, east*100, 200)); marker.set_actor_label('CONTROL '+key+' | '+landmark['name'])
        controls.append({'key': key, 'name': landmark['name'], 'lat': landmark['lat'], 'lon': landmark['lon'], 'unreal_cm': [north*100, east*100, 200], 'source': landmark['source']})
        u.log('AERONAUT_KEYWEST_CONTROL '+json.dumps(controls[-1]))
    actors.spawn_actor_from_class(u.PlayerStart, scene.get_editor_property('airborne_spawn'))
    checked(levels.save_current_level(), 'Key West map save failed')
    # Do not save all dirty packages: old maps/materials must remain byte-identical.
    evidence = {'map': map_path, 'tour_duration_seconds': duration, 'tour_speed_m_s': 60, 'tour_points_ne_m': ROUTE,
        'named_controls': controls, 'modeled_tower_position_m': tower_p, 'terrain_probe_m': gp,
        'building_probe_id': building['id'], 'building_probe_actor': city_name, 'city_statistics': catalog['statistics'],
        'source_scene_sha256': catalog['source_scene_sha256'],
        'modeling_limits': 'Flat 2m islands; inferred missing heights/roofs, tower placement and -6m seabed; no surveyed DEM/bathymetry'}
    folder = root/'artifacts/keywest'; folder.mkdir(parents=True, exist_ok=True)
    (folder/'authored-scene.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    u.log('AERONAUT_KEYWEST_CONTENT_READY '+json.dumps({'tour_duration': duration, 'controls': len(controls), 'meshes': len(meshes)}))


def self_test():
    bounds = (-6048, -6048, 6048, 6048)
    assert uv(6048, -6048, bounds) == (0, 0) and uv(-6048, 6048, bounds) == (1, 1)
    assert uv(0, 0, bounds) == (.5, .5)
    assert all(abs(n)<4600 and abs(e)<4600 and 60<z<950 for n, e, z in ROUTE)
    assert all(math.sqrt(n*n+e*e+z*z)+350<7500 for n, e, z in ROUTE)
    assert abs(segment_distance((5, 2), (0, 0), (10, 0))-2)<1e-9
    assert in_ring((1, 1), [(0, 0), (2, 0), (2, 2), (0, 2)])
    length = sum(math.dist(a, b) for a, b in zip(ROUTE, ROUTE[1:]+ROUTE[:1]))
    assert 240 < length/60 < 400
    print('PASS Key West north/east/south UV, bounds/sky margin, clearance math and tour duration')


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        self_test()
    elif '--environment' in sys.argv:
        prepare_environment(Path(sys.argv[sys.argv.index('--environment')+1]).resolve())
    else:
        import unreal
        author(Path(unreal.Paths.project_dir()).resolve())
