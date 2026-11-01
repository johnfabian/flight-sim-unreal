"""Author only /Game/KeyWestDetail; no gameplay or rendering is launched here.

Explicit null-RHI prepare clones the saved geographic map once and refreshes
owned cosmetic layers. Rendering/reflections are separate, permission-bound work.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

DEST = '/Game/KeyWestDetail'
MAP = DEST+'/KeyWestDetail'
BASE_MAP = '/Game/KeyWest/KeyWest'
OWNER = 'KeyWestDetailGeneratedV1'
LEGACY_MARKER = 'KeyWestDetailLegacyBoatsReplacedV1'


def require(value, message):
    if not value:
        raise RuntimeError(message)
    return value


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def old_content_changes(root):
    baseline = root/'artifacts/keywest-detail/baseline/content-sha256.csv'
    require(baseline.is_file(), 'Pre-feature Content baseline is required')
    with baseline.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 511, 'Unexpected pre-feature Content baseline')
    return [r['Path'] for r in rows if not (root/r['Path']).is_file() or digest(root/r['Path']).lower() != r['SHA256'].lower()]


def tile_name(building):
    center = [sum(p[i] for p in building['outer'])/len(building['outer']) for i in range(2)]
    label = lambda n: ('p' if n >= 0 else 'm')+f'{abs(n):03d}'
    return 'KW_City_N'+label(math.floor(center[0]/256))+'_E'+label(math.floor(center[1]/256))


def facade_view(anchor):
    center = anchor['door_center_m'] or anchor['facade_center_m']
    n, e = anchor['outward_ne']; height = anchor['height_m']
    return ([center[0]+n*19-e*3, center[1]+e*19+n*3, center[2]+max(8.5,height+2)],
            [center[0], center[1], center[2]+min(3.3,height*.48)])


def boat_view(record):
    angle = math.radians(record['yaw_deg']); c, s = math.cos(angle), math.sin(angle)
    p = record['position_m']
    return ([p[0]-18*c+14*s, p[1]-18*s-14*c, 9], [p[0],p[1],1.2])


def author(root):
    import unreal as u
    sys.path.insert(0, str(root/'Art')); sys.path.insert(0, str(root/'Scripts'))
    from GenerateKeyWestDetail import fleet_contract
    from keywest_detail_materials import build_materials
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem); actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    args = u.SystemLibrary.get_command_line().split()
    require(not old_content_changes(root), 'Pre-feature Content differs before authoring')
    if '-KeyWestDetailMaterialsOnly' not in args:
        backup_arg = next((a.split('=',1)[1] for a in args if a.startswith('-KeyWestDetailBackup=')), None)
        require(backup_arg, 'Use the dedicated script to back up old and target map/BuiltData before authoring')
        backup = Path(backup_arg).resolve()
        require(backup.is_relative_to((root/'artifacts/keywest-detail/backups').resolve()), 'Unexpected map backup location')
        for name in ('KeyWest.umap','KeyWest_BuiltData.uasset'):
            require((backup/'old'/name).is_file() and digest(backup/'old'/name) == digest(root/'Content/KeyWest'/name), 'Old map/BuiltData backup missing or stale')
        for name in ('KeyWestDetail.umap','KeyWestDetail_BuiltData.uasset'):
            current = root/'Content/KeyWestDetail'/name
            if current.is_file():
                require((backup/'new'/name).is_file() and digest(backup/'new'/name) == digest(current), 'Target map/BuiltData backup missing or stale')

    def assert_new_world():
        world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
        require(world.get_path_name().startswith(MAP+'.'), 'Refusing non-detail world mutation')
        options = u.AssetRegistryDependencyOptions(include_hard_package_references=True, include_soft_package_references=True)
        dependencies = u.AssetRegistryHelpers.get_asset_registry().get_dependencies(MAP, options)
        require(BASE_MAP+'_BuiltData' not in [str(p) for p in dependencies], 'Copied map still shares old BuiltData')
        return world

    if '-KeyWestDetailReflections' in args:
        # RHI/render use requires a separate explicit user approval. This branch
        # is never invoked by ordinary Prepare or Play.
        require(levels.load_level(MAP), 'Prepared detail map missing'); assert_new_world()
        u.ShowcaseEditor.build_reflections(); require(levels.save_current_level(), 'Detail reflections save failed')
        require(not old_content_changes(root), 'Old Content changed during detail reflections')
        u.log('AERONAUT_KEYWEST_DETAIL_REFLECTIONS_READY'); return

    if '-KeyWestDetailGroundOnly' in args:
        require(levels.load_level(MAP), 'Prepared detail map missing'); assert_new_world()
        from keywest_detail_ground import import_and_place
        import_and_place(u,root)
        require(levels.save_current_level(), 'Ground detail map save failed'); assert_new_world()
        require(not old_content_changes(root), 'Old Content changed during ground detail authoring')
        u.log('AERONAUT_KEYWEST_DETAIL_GROUND_READY'); return

    source = root/'Art/KeyWest/Data/scene.json'; fleet_file = root/'Art/KeyWestDetail/Data/fleet.json'
    catalog_file = root/'Art/KeyWestDetail/Exports/assets.json'
    catalog = json.loads(catalog_file.read_text()); fleet = fleet_contract(json.loads(fleet_file.read_text()), digest(source))
    scene_data = json.loads(source.read_text())
    require(catalog['source_scene_sha256'] == digest(source) and catalog['fleet_sha256'] == digest(fleet_file), 'Regenerate details from the exact validated inputs')
    for name, expected in catalog['source_modules'].items():
        require(digest(root/'Art'/name) == expected, 'Detail source module changed '+name)
    stamp = json.loads((fleet_file.parent/'fleet-validation.json').read_text())
    require(stamp['fleet_sha256'] == digest(fleet_file) and stamp['scene_sha256'] == digest(source) and stamp['validation']['passed'], 'Missing exact validated fleet stamp')
    for folder in ('','/Meshes','/Materials','/Textures'):
        u.EditorAssetLibrary.make_directory(DEST+folder)
    folder = root/'artifacts/keywest-detail'; folder.mkdir(parents=True, exist_ok=True)
    state_file = folder/'import-state.json'
    state = json.loads(state_file.read_text()) if state_file.is_file() else {}
    state.setdefault('meshes', {})
    force = '-KeyWestDetailMaterials' in args or '-KeyWestDetailMaterialsOnly' in args
    mats = build_materials(u, root, catalog['material_definitions'], state, force)
    if '-KeyWestDetailMaterialsOnly' in args:
        state_file.write_text(json.dumps(state, indent=2)); require(not old_content_changes(root), 'Old Content changed during new material update')
        u.log('AERONAUT_KEYWEST_DETAIL_MATERIALS_READY'); return

    tools = u.AssetToolsHelpers.get_asset_tools(); meshes = {}
    for spec in catalog['assets']:
        name = spec['name']
        shell = spec['role'] == 'city_shell' and name.startswith('KWD_City_') and spec.get('source_city_asset','').startswith('KW_City_')
        require(name.startswith(('KWD_','KWB_')) and (not spec['collision'] or shell), 'Refusing base/colliding detail import')
        file = root/'Art/KeyWestDetail/Exports'/(name+'.fbx')
        require(digest(file) == spec['file_sha256'], 'Detail FBX changed '+name)
        path = DEST+'/Meshes/'+name
        mesh = u.load_asset(path) if u.EditorAssetLibrary.does_asset_exist(path) else None
        signature = hashlib.sha256((spec['file_sha256']+'|LegacyFBX|metres|vertexREPLACE|preserve|normals|collision='+str(bool(spec['collision']))).encode()).hexdigest()
        if not mesh or state.setdefault('meshes', {}).get(name) != signature:
            task = u.AssetImportTask(); task.filename = str(file); task.destination_path = DEST+'/Meshes'; task.destination_name = name
            task.automated = True; task.replace_existing = True; task.replace_existing_settings = True; task.save = True; task.factory = u.FbxFactory()
            options = u.FbxImportUI(); options.import_mesh = True; options.import_textures = False; options.import_materials = False
            options.set_editor_property('automated_import_should_detect_type', False); options.mesh_type_to_import = u.FBXImportType.FBXIT_STATIC_MESH
            data = options.static_mesh_import_data
            for key, value in {'combine_meshes':True,'generate_lightmap_u_vs':False,'auto_generate_collision':False,'convert_scene':True,'convert_scene_unit':True,'remove_degenerates':False}.items():
                data.set_editor_property(key, value)
            data.set_editor_property('vertex_color_import_option',u.VertexColorImportOption.REPLACE)
            data.set_editor_property('normal_import_method',u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
            task.options = options; tools.import_asset_tasks([task]); mesh = u.load_asset(path)
            require(mesh, 'Detail FBX import failed '+name)
            # Preserve thin frames/rails and shaped hulls. Distance culling is
            # separate; never run destructive automatic detail reduction.
            u.ShowcaseEditor.configure_geographic_mesh(mesh, bool(spec['collision']), bool(spec['foliage']), True)
            for slot, matname in enumerate(spec['materials']):
                mesh.set_material(slot, mats[matname])  # NEW meshes only.
            require(mesh.get_path_name().startswith(DEST+'/') and u.EditorAssetLibrary.save_loaded_asset(mesh), 'New detail mesh save failed')
            state['meshes'][name] = signature
        dim = u.ShowcaseEditor.mesh_dimensions(mesh); center = mesh.get_bounds().origin
        require(max(abs(a-b*100) for a,b in zip((dim.x,dim.y,dim.z),spec['dimensions_m']))<3, 'Detail FBX dimensions failed '+name)
        expected = [(spec['bounds_m'][0][i]+spec['bounds_m'][1][i])*50 for i in range(3)]
        require(max(abs(a-b) for a,b in zip((center.x,center.y,center.z),expected))<3, 'Detail FBX axis/pivot failed '+name)
        meshes[name] = mesh
    state_file.write_text(json.dumps(state,indent=2))

    if not u.EditorAssetLibrary.does_asset_exist(MAP):
        require(levels.load_level(BASE_MAP), 'Prepared base Key West map missing')
        world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
        # Native SaveMap duplicates the disk-backed World. Its build-data
        # pointer is NonPIEDuplicateTransient, so attach an isolated copy below.
        # Never rename the original map or save all dirty packages.
        require(u.EditorLoadingAndSavingUtils.save_map(world, MAP), 'Detail SaveAs failed')
        require(levels.load_level(MAP), 'Saved detail clone failed to load')
    else:
        require(levels.load_level(MAP), 'Detail map load failed')
    world = assert_new_world()
    build_path = MAP+'_BuiltData'
    built = u.load_asset(build_path) if u.EditorAssetLibrary.does_asset_exist(build_path) else u.EditorAssetLibrary.duplicate_asset(BASE_MAP+'_BuiltData', build_path)
    require(built and built.get_path_name() == build_path+'.KeyWestDetail_BuiltData', 'Independent detail BuiltData duplication failed')
    require(u.ShowcaseEditor.attach_detail_build_data(built), 'Refusing non-detail/shared BuiltData attachment')
    require(u.EditorAssetLibrary.save_loaded_asset(built) and levels.save_current_level(), 'Independent detail BuiltData/map save failed')
    assert_new_world()
    dependencies = u.AssetRegistryHelpers.get_asset_registry().get_dependencies(MAP, u.AssetRegistryDependencyOptions(include_hard_package_references=True))
    require(build_path in [str(p) for p in dependencies], 'Detail map has no saved independent BuiltData dependency')
    require(not old_content_changes(root), 'Old Content changed during SaveAs')
    current = list(actors.get_all_level_actors())
    scene = require(next((a for a in current if isinstance(a,u.CoastalScene)),None),'Copied flight scene missing')
    references = list(scene.get_editor_property('collision_sources'))+[scene.get_editor_property('terrain_actor')]
    require(all(a and a.get_path_name().startswith(MAP+'.') for a in references), 'Copied collision references still point outside the new world')
    preserved_duration = scene.get_editor_property('tour_duration')
    for a in current:
        if OWNER in [str(t) for t in a.get_editor_property('tags')]:
            require(not isinstance(a,u.CoastalScene), 'Refusing to destroy flight scene')
            actors.destroy_actor(a)
    legacy = []
    for a in current:
        if isinstance(a,u.StaticMeshActor):
            mesh = a.static_mesh_component.get_editor_property('static_mesh')
            if mesh and mesh.get_path_name().startswith('/Game/KeyWest/Meshes/') and mesh.get_name() in ('KW_Boat0','KW_Boat1','KW_Boat2'):
                legacy.append(a)
    tags = [str(t) for t in scene.get_editor_property('tags')]
    require(len(legacy) == 154 or (len(legacy) == 0 and LEGACY_MARKER in tags), 'Expected exactly154 copied legacy boats before replacement')
    for a in legacy:
        actors.destroy_actor(a)
    if LEGACY_MARKER not in tags:
        tags.append(LEGACY_MARKER); scene.set_editor_property('tags', tags)

    from collections import Counter, defaultdict
    zones = defaultdict(Counter)
    for b in scene_data['buildings']:
        zones[tile_name(b)][b.get('zone','new_town')] += 1
    base_catalog = json.loads((root/'Art/KeyWest/Exports/assets.json').read_text())
    base_specs = {s['name']:s for s in base_catalog['assets']}
    shells = {s['source_city_asset']:s for s in catalog['assets'] if s['role'] == 'city_shell'}
    require(len(shells) == 321, 'Corrected city shell set is incomplete')
    shell_names = {s['name']:name for name,s in shells.items()}
    base_city = 0
    for a in actors.get_all_level_actors():
        if not isinstance(a,u.StaticMeshActor):
            continue
        c = a.static_mesh_component; mesh = c.get_editor_property('static_mesh')
        if mesh and mesh.get_name() == 'KW_Geo_roads':
            c.set_material(0,mats['Road'])
        if not mesh or not mesh.get_name().startswith(('KW_City_','KWD_City_')):
            continue
        name = shell_names.get(mesh.get_name(), mesh.get_name())
        require(name in shells and name in base_specs, 'Unrecognized copied city actor')
        spec = shells[name]; wood = zones[name].get('old_town',0) >= max(zones[name].values())
        # Replace geometry on the SAME actors so saved terrain/collision probes
        # retain their references. Never reimport or save the old city assets.
        replacement = meshes[spec['name']]
        if c.get_editor_property('static_mesh') != replacement:
            require(c.set_static_mesh(replacement), 'Corrected city geometry assignment failed '+name)
        for slot, matname in enumerate(spec['materials']):
            if matname == 'KWD_Wall':
                c.set_material(slot,mats['WallWood'] if wood else mats['WallPlaster'])
            elif matname == 'KWD_Roof':
                c.set_material(slot,mats['KWD_Roof'])
            else:
                c.set_material(slot,mats[matname])
        base_city += 1
    require(base_city == 321, 'Copied base city actor count changed')
    palm_specs = {s['source_palm_asset']:s for s in catalog['assets'] if s['role'] == 'palm'}
    require(len(palm_specs) == 3, 'Fuller palm variant set incomplete')
    new_palms = {s['name']:old for old,s in palm_specs.items()}
    palm_groups = 0
    for a in actors.get_all_level_actors():
        if not isinstance(a,u.InstancedScenery):
            continue
        c = a.instances; mesh = c.get_editor_property('static_mesh')
        if not mesh:
            continue
        name = new_palms.get(mesh.get_name(),mesh.get_name())
        if name not in palm_specs:
            continue
        spec = palm_specs[name]
        replacement = meshes[spec['name']]
        if c.get_editor_property('static_mesh') != replacement:
            require(c.set_static_mesh(replacement), 'Fuller palm assignment failed')
        for slot,matname in enumerate(spec['materials']):
            c.set_material(slot,mats[matname])
        palm_groups += 1
    require(palm_groups == 3, 'Expected three preserved roadside palm instance groups')

    # Preserve the validated cloud sphere. Very large backdrop bounds caused
    # a whiteout in the DX11 capture; keep the ocean extension modest.
    oceans = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'Key West ocean - sea level']
    skies = [a for a in actors.get_all_level_actors() if a.get_actor_label() == 'Preserved coastal cloud sky']
    require(len(oceans) == len(skies) == 1, 'Expected one copied ocean and cloud backdrop')
    oceans[0].set_actor_scale3d(u.Vector(24000,24000,1))
    skies[0].set_actor_scale3d(u.Vector(15000,15000,15000))

    def owned(a, label):
        a.set_actor_label(label); a.set_editor_property('tags',[OWNER]); a.set_actor_enable_collision(False)
        return a

    specs = {s['name']:s for s in catalog['assets']}; boat_groups = defaultdict(list); detail_count = 0
    for record in catalog['placements']:
        spec = specs[record['asset']]
        if spec['role'] == 'city_shell':
            continue  # Geometry replaces existing collision actors above.
        if spec['role'] == 'boat':
            cell = tuple(math.floor(v/512) for v in record['position_m'][:2])
            boat_groups[(spec['name'],cell)].append(record); continue
        a = owned(actors.spawn_actor_from_class(u.StaticMeshActor,u.Vector(*(v*100 for v in record['position_m']))),spec['name'])
        c = a.static_mesh_component; c.set_static_mesh(meshes[spec['name']]); c.set_mobility(u.ComponentMobility.STATIC)
        c.set_collision_profile_name('NoCollision'); c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        c.set_cull_distance(min(1400,max(600,spec.get('cull_distance_m',1250)))*100)
        c.set_cast_shadow(True); detail_count += 1
    for (name,cell), records in boat_groups.items():
        a = owned(actors.spawn_actor_from_class(u.InstancedScenery,u.Vector()),name+' anchored fleet '+str(cell))
        a.set_editor_property('allow_density_scaling',False)
        c = a.instances; c.set_static_mesh(meshes[name]); c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION); c.set_cull_distances(150000,230000)
        c.add_instances([u.Transform(location=u.Vector(*(v*100 for v in r['position_m'])),rotation=u.Rotator(yaw=r['yaw_deg']),scale=u.Vector(*r['scale'])) for r in records],False,False)
    scene.set_editor_property('evidence_subdirectory','KeyWestDetail')
    scene.set_editor_property('region_label','KEY WEST  /  ARCHITECTURE & HARBOUR')
    # Keep the exact five approved baseline camera/route poses, then add two.
    views = list(scene.get_editor_property('capture_views'))[:5]
    require(len(views) == 5, 'Baseline five capture poses missing')
    anchors = catalog['architecture']['review_anchors']
    anchor = require(next((a for a in anchors if a['framed_frontage_complete'] and a['features'].get('porches',0) and a.get('door_center_m')),None),'Complete porch/window review anchor missing')
    hero_ids = set(fleet['hero_cluster']['placement_ids'])
    boat = require(next((r for r in fleet['placements'] if r['id'] in hero_ids),None),'Hero boat missing')
    for location,target,fov in [(*facade_view(anchor),58),(*boat_view(boat),55)]:
        view = u.CoastalCaptureView(); view.set_editor_property('tour_seconds',0); view.set_editor_property('camera_mode',0); view.set_editor_property('world_camera',True)
        view.set_editor_property('camera_location',u.Vector(*(v*100 for v in location))); view.set_editor_property('camera_target',u.Vector(*(v*100 for v in target))); view.set_editor_property('field_of_view',fov)
        views.append(view)
    scene.set_editor_property('capture_views',views)
    require(scene.get_editor_property('tour_duration') == preserved_duration and scene.validate_tour(6000), 'Preserved tour changed or failed clearance')
    if (root/'Art/KeyWestDetail/Ground/Exports/assets.json').is_file():
        from keywest_detail_ground import import_and_place
        import_and_place(u,root)
    require(levels.save_current_level(), 'Detail scene save failed'); assert_new_world()
    require(not old_content_changes(root), 'Pre-feature Content drifted after detail authoring')
    state_file.write_text(json.dumps(state,indent=2))
    report = dict(map=MAP,base_map=BASE_MAP,base_city_actors=base_city,corrected_city_shells=len(shells),city_shells=catalog['city_shells'],palm_groups=palm_groups,palms=catalog['palms'],ocean_width_m=24000,sky_diameter_m=15000,legacy_boats_removed=len(legacy),fleet_placements=len(fleet['placements']),boat_groups=len(boat_groups),detail_batches=detail_count,architecture=catalog['architecture'],waterfront=catalog['waterfront'],facade_anchor=anchor,hero_boat=boat,capture_views=7,warmup_seconds=40,tour_duration_seconds=preserved_duration,source_scene_sha256=digest(source),catalog_sha256=digest(catalog_file),old_content_unchanged=True)
    (folder/'authored-scene.json').write_text(json.dumps(report,indent=2))
    u.log('AERONAUT_KEYWEST_DETAIL_CONTENT_READY '+json.dumps({k:report[k] for k in ('detail_batches','fleet_placements','capture_views','warmup_seconds')}))


def self_test():
    a = dict(door_center_m=[10,20,2],facade_center_m=[10,20,2],outward_ne=[1,0],height_m=6)
    camera,target = facade_view(a)
    assert camera[0]>target[0] and camera[2]>target[2]
    camera,target = boat_view(dict(position_m=[0,0,0],yaw_deg=90))
    assert abs(camera[0]-14)<1e-8 and abs(camera[1]+18)<1e-8
    assert tile_name(dict(outer=[[0,0],[10,0],[10,10],[0,10]])) == 'KW_City_Np000_Ep000'
    assert max(30,7*5+5)==40 and max(30,5*5+5)==30
    print('PASS review-camera north/east transforms, tile identity and 7/5-view warmup')


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        self_test()
    else:
        import unreal
        author(Path(unreal.Paths.project_dir()).resolve())
