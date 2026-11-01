"""Import prepared ground overlays into the already loaded detail world only.

No downloads, Blender, map loading, level saving, or build-data changes. The
caller backs up and saves the new map. Importing/self-testing is engine-free;
ordinary Python tests do not establish actual Unreal API compatibility.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

MAP = '/Game/KeyWestDetail/KeyWestDetail'
WORLD = MAP+'.KeyWestDetail'
BUILT = MAP+'_BuiltData'
DEST = '/Game/KeyWestDetail/Ground'
OWNER = 'KeyWestGroundDetailV1'
SOURCE = Path('Art/KeyWestDetail/Ground')
COUNT, HEIGHT, PIXELS = 28, 2.01, 2048
AXES = {'x':'north', 'y':'east', 'z':'up'}
UV_CONTRACT = 'U=(east-e0)/(e1-e0); V=(n1-north)/(n1-n0)'
MATERIAL_RECIPE = dict(uv_channel=0, base_multiplier=.48, roughness=.93,
                       metallic=0, srgb=True, address='CLAMP', compression='DEFAULT',
                       max_texture_size=PIXELS, two_sided=False, never_stream=True)


def require(value, message):
    if not value:
        raise ValueError(message)
    return value


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def vector(value, count, label):
    require(type(value) in (list,tuple) and len(value)==count, 'Invalid '+label)
    require(all(type(v) in (int, float) and math.isfinite(v) for v in value), 'Nonfinite '+label)
    return value


def close(actual, expected, label, tolerance=1e-7):
    vector(actual, len(expected), label)
    require(all(abs(a-b)<=tolerance for a,b in zip(actual, expected)), 'Changed '+label)


def read_json(path):
    def finite(value):
        result=float(value)
        require(math.isfinite(result), 'Nonfinite JSON number')
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON constant '+value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_float=finite, parse_constant=invalid)


def source_file(root, relative, expected, size, label):
    require(type(relative) is str and relative==expected, 'Unexpected '+label+' path')
    path=(root/relative).resolve()
    require(path.is_relative_to((root/SOURCE).resolve()) and path.is_relative_to(root), label+' escaped new namespace')
    require(type(size) is int and size>0 and path.is_file() and path.stat().st_size==size, 'Changed '+label+' bytes')
    return path


def file_record(root, relative, expected, size, expected_sha, label):
    require(type(expected_sha) is str and re.fullmatch('[0-9a-f]{64}', expected_sha), 'Invalid '+label+' SHA256')
    path=source_file(root, relative, expected, size, label)
    require(digest(path)==expected_sha, 'Changed '+label+' SHA256')
    return path


def prepared(root):
    """Use the exact local preparation module, with no engine/Pillow imports."""
    path=root/'Art/KeyWestGround.py'
    spec=importlib.util.spec_from_file_location('_keywest_ground_input_contract', path)
    require(spec and spec.loader, 'Ground preparation module missing')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tiles, manifest=module.prepared(root)
    return tiles, manifest


def validate_catalog(root, tiles, manifest, catalog):
    """Pure filesystem/catalog checks, usable with temporary unit fixtures."""
    require(type(catalog) is dict and catalog.get('schema')==1 and catalog.get('units')=='metres'
            and catalog.get('axes')==AXES, 'Unexpected ground catalog schema/axes')
    require(len(tiles)==COUNT and len(manifest['tiles'])==COUNT, 'Exactly 28 prepared land tiles required')
    require(catalog.get('source_scene_sha256')==digest(root/'Art/KeyWest/Data/scene.json')
            ==manifest['source_scene_sha256'], 'Ground geographic source changed')
    require(catalog.get('generator_sha256')==digest(root/'Art/KeyWestGround.py')
            ==manifest['generator_sha256'], 'Ground generator changed')
    require(catalog.get('imagery_manifest_sha256')==digest(root/SOURCE/'Data/imagery.json'), 'Ground imagery manifest changed')
    require(catalog.get('height_m')==HEIGHT and catalog.get('nominal_metres_per_pixel')==.3,
            'Ground height/resolution changed')
    require(catalog.get('expected_unreal_uv0')==UV_CONTRACT, 'Ground UV orientation changed')
    require(catalog.get('triangle_budget')==100000, 'Ground triangle budget changed')
    file_record(root, catalog.get('blend_file'), (SOURCE/'KeyWestGround.blend').as_posix(),
                catalog.get('blend_bytes'), catalog.get('blend_sha256'), 'ground blend')
    assets, placements=catalog.get('assets'), catalog.get('placements')
    require(type(assets) is list and type(placements) is list and len(assets)==len(placements)==COUNT,
            'Incomplete/duplicate ground asset or placement set')
    require(len({a.get('name') for a in assets})==COUNT, 'Duplicate ground mesh names')
    require(len({p.get('asset') for p in placements})==COUNT, 'Duplicate ground placements')
    require([a.get('name') for a in assets]==[t['asset'] for t in tiles], 'Ground asset order/set changed')
    require([p.get('asset') for p in placements]==[t['asset'] for t in tiles], 'Ground placement order/set changed')
    total=0
    for tile,image,asset,placement in zip(tiles, manifest['tiles'], assets, placements):
        ident=tile['id']; name=tile['asset']
        require(re.fullmatch(r'(oldtown|airport)_r[0-3]_c[0-3]', ident)
                and name=='KWD_Ground_'+ident, 'Unexpected ground tile name')
        require(asset.get('id')==ident and asset.get('name')==name and asset.get('asset')==name
                and asset.get('role')=='ground_overlay' and asset.get('collision') is False
                and asset.get('foliage') is False, 'Unsafe ground asset role/name/collision')
        for key in ('region','bounds_ne','extent_wgs84','pixels','nominal_metres_per_pixel',
                    'land_area_m2','position_m','height_m'):
            require(asset.get(key)==tile[key], 'Ground tile metadata changed '+key)
        require(asset.get('texture')==image, 'Ground image record changed')
        require(image['pixels']==[PIXELS,PIXELS] and image['validation']['rgb_mode']=='RGB', 'Ground image format changed')
        image_path=file_record(root, image['file'], (SOURCE/'Textures'/(ident+'.jpg')).as_posix(),
                               image['bytes'], image['sha256'], 'ground image')
        # prepared() already verifies JPEG frame, RGB proof, source requests and
        # geography; no Pillow or decoder is imported in the Unreal commandlet.
        require(image_path.suffix=='.jpg', 'Ground image must be JPEG')
        n0,e0,n1,e1=vector(tile['bounds_ne'],4,'prepared tile bounds')
        require(abs(n1-n0-614.4)<1e-7 and abs(e1-e0-614.4)<1e-7, 'Ground tile span changed')
        close(vector(tile['position_m'],3,'prepared position'), [n0,e0,0], 'prepared pivot placement')
        vertices=[]
        for triangle in tile['triangles_ne']:
            require(type(triangle) is list and len(triangle)==3, 'Invalid prepared triangle')
            for point in triangle:
                vector(point,2,'prepared triangle vertex')
                require(n0-1e-7<=point[0]<=n1+1e-7 and e0-1e-7<=point[1]<=e1+1e-7, 'Ground triangle outside tile')
                vertices.append([point[0]-n0, point[1]-e0, HEIGHT])
        require(vertices, 'Empty ground mesh')
        expected_bounds=[[min(v[i] for v in vertices) for i in range(3)],
                         [max(v[i] for v in vertices) for i in range(3)]]
        bounds=asset.get('bounds_m')
        require(type(bounds) is list and len(bounds)==2, 'Invalid ground bounds')
        for actual,expected in zip(bounds,expected_bounds):
            close(actual,expected,'ground bounds')
        dimensions=[expected_bounds[1][i]-expected_bounds[0][i] for i in range(3)]
        require(dimensions[0]>0 and dimensions[1]>0 and dimensions[2]==0, 'Ground must be a planar XY mesh')
        close(asset.get('dimensions_m'),dimensions,'ground dimensions')
        close(asset.get('pivot'),[0,0,0],'ground FBX pivot')
        require(type(asset.get('triangles')) is int and asset['triangles']==len(tile['triangles_ne']), 'Ground triangle count changed')
        require(asset.get('materials')==['KWD_GroundTexture_'+ident], 'Ground material slots changed')
        file_record(root,asset.get('file'),(SOURCE/'Exports'/(name+'.fbx')).as_posix(),
                    asset.get('file_bytes'),asset.get('file_sha256'),'ground FBX')
        require(placement.get('asset')==name and type(placement.get('yaw_deg')) in (int,float)
                and placement['yaw_deg']==0, 'Ground placement transform changed')
        close(placement.get('scale'),[1,1,1],'ground placement scale')
        close(placement.get('position_m'),tile['position_m'],'ground placement')
        total+=asset['triangles']
    require(0<total<catalog['triangle_budget'], 'Ground triangle budget exceeded')
    return total


def validate_inputs(root):
    root=Path(root).resolve()
    tiles,manifest=prepared(root)  # Strict proof before any new asset mutation.
    catalog=read_json(root/SOURCE/'Exports/assets.json')
    triangles=validate_catalog(root,tiles,manifest,catalog)
    return catalog,triangles


def assert_world(u):
    world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    require(world and world.get_path_name()==WORLD, 'Ground importer refuses non-detail editor world')
    options=u.AssetRegistryDependencyOptions(include_hard_package_references=True, include_soft_package_references=True)
    dependencies=list(map(str,u.AssetRegistryHelpers.get_asset_registry().get_dependencies(MAP,options)))
    require(BUILT in dependencies and '/Game/KeyWest/KeyWest_BuiltData' not in dependencies,
            'Ground importer requires independent new BuiltData dependency')
    built=u.load_asset(BUILT)
    require(built and built.get_path_name()==BUILT+'.KeyWestDetail_BuiltData', 'Ground importer refuses missing/shared BuiltData')
    return world


def own_asset(asset, path):
    require(path.startswith(DEST+'/') and asset and asset.get_path_name()==path+'.'+path.rsplit('/',1)[-1],
            'Refusing missing/out-of-namespace ground asset '+path)
    return asset


def save_asset(u, asset, path):
    own_asset(asset,path)
    require(u.EditorAssetLibrary.save_loaded_asset(asset), 'Ground asset save failed '+path)


def mesh_bounds(u, mesh, asset):
    dim=u.ShowcaseEditor.mesh_dimensions(mesh); center=mesh.get_bounds().origin
    expected=[(asset['bounds_m'][0][i]+asset['bounds_m'][1][i])*50 for i in range(3)]
    require(all(math.isfinite(v) for v in (dim.x,dim.y,dim.z,center.x,center.y,center.z)), 'Nonfinite imported ground bounds')
    require(max(abs(a-b*100) for a,b in zip((dim.x,dim.y,dim.z),asset['dimensions_m']))<3,
            'Ground FBX dimensions exceed 3cm '+asset['name'])
    require(max(abs(a-b) for a,b in zip((center.x,center.y,center.z),expected))<3,
            'Ground FBX axis/pivot exceeds 3cm '+asset['name'])


def import_and_place(u, root):
    """Apply owned assets/actors; return JSON-compatible report, never save a map."""
    root=Path(root).resolve()
    assert_world(u)  # Must reject wrong world before even input/state preparation.
    catalog,triangles=validate_inputs(root)
    assert_world(u)
    from showcase_material_api import node, scalar, prop, sample, multiply
    tools=u.AssetToolsHelpers.get_asset_tools(); edit=u.MaterialEditingLibrary
    actors=u.get_editor_subsystem(u.EditorActorSubsystem)
    old=[a for a in actors.get_all_level_actors() if OWNER in map(str,a.get_editor_property('tags'))]
    for actor in old:
        require(isinstance(actor,u.StaticMeshActor) and actor.get_path_name().startswith(WORLD+':'),
                'Unexpected actor carries ground ownership tag')
        mesh=actor.static_mesh_component.get_editor_property('static_mesh')
        require(mesh and mesh.get_path_name().startswith(DEST+'/Meshes/KWD_Ground_'),
                'Refusing tagged actor with non-ground mesh')
    folder=root/'artifacts/keywest-detail'
    state_path=folder/'ground-import-state.json'
    state=read_json(state_path) if state_path.is_file() else dict(schema=1,meshes={},textures={},materials={})
    require(state.get('schema')==1 and all(type(state.get(k)) is dict for k in ('meshes','textures','materials')),
            'Invalid ground import state')
    script_sha=digest(__file__)
    graph_sha=signature([script_sha,MATERIAL_RECIPE])
    for path in (DEST,DEST+'/Meshes',DEST+'/Materials',DEST+'/Textures'):
        u.EditorAssetLibrary.make_directory(path)
    meshes={}; records=[]
    for asset in catalog['assets']:
        name=asset['name']; image=asset['texture']
        tex_name='T_'+name; tex_path=DEST+'/Textures/'+tex_name
        tex=u.load_asset(tex_path) if u.EditorAssetLibrary.does_asset_exist(tex_path) else None
        texture_key=signature([image['sha256'],graph_sha,MATERIAL_RECIPE])
        if not tex or state['textures'].get(name)!=texture_key:
            task=u.AssetImportTask(); task.filename=str(root/image['file']); task.destination_path=DEST+'/Textures'; task.destination_name=tex_name
            task.automated=True; task.replace_existing=True; task.save=True
            tools.import_asset_tasks([task]); tex=own_asset(u.load_asset(tex_path),tex_path)
            tex.set_editor_property('max_texture_size',PIXELS)
            tex.set_editor_property('address_x',u.TextureAddress.TA_CLAMP); tex.set_editor_property('address_y',u.TextureAddress.TA_CLAMP)
            tex.set_editor_property('srgb',True); tex.set_editor_property('compression_settings',u.TextureCompressionSettings.TC_DEFAULT)
            # This bounded set is about75MiB of BC1 mip chains. Hold its prepared
            # detail rather than relying on missing/new streaming scale data.
            tex.set_editor_property('never_stream',True)
            save_asset(u,tex,tex_path); state['textures'][name]=texture_key
        own_asset(tex,tex_path)
        require(tex.get_editor_property('max_texture_size')==PIXELS and tex.get_editor_property('srgb') is True
                and tex.get_editor_property('address_x')==u.TextureAddress.TA_CLAMP
                and tex.get_editor_property('address_y')==u.TextureAddress.TA_CLAMP
                and tex.get_editor_property('compression_settings')==u.TextureCompressionSettings.TC_DEFAULT,
                'Ground texture settings drifted '+name)
        require(tex.get_editor_property('never_stream') is True, 'Ground detail residency drifted '+name)
        mat_name='M_'+name; mat_path=DEST+'/Materials/'+mat_name
        mat=u.load_asset(mat_path) if u.EditorAssetLibrary.does_asset_exist(mat_path) else None
        material_key=signature([image['sha256'],graph_sha,tex_path])
        if not mat or state['materials'].get(name)!=material_key:
            mat=own_asset(mat if mat else tools.create_asset(mat_name,DEST+'/Materials',u.Material,u.MaterialFactoryNew()),mat_path)
            # Only this exact new-ground material may have its graph rebuilt.
            for expression in list(edit.get_material_expressions(mat)):
                edit.delete_material_expression(mat,expression)
            require(not edit.get_material_expressions(mat), 'Ground material graph did not clear')
            mat.set_editor_property('two_sided',False)
            uv=node(mat,u.MaterialExpressionTextureCoordinate)  # Default CoordinateIndex=0.
            prop(multiply(mat,sample(mat,tex,uv),scalar(mat,.48)),u.MaterialProperty.MP_BASE_COLOR)
            prop(scalar(mat,.93),u.MaterialProperty.MP_ROUGHNESS); prop(scalar(mat,0),u.MaterialProperty.MP_METALLIC)
            errors=list(edit.recompile_material(mat))
            require(not errors, 'Ground material compile failed '+name+': '+str(errors))
            save_asset(u,mat,mat_path); state['materials'][name]=material_key
        own_asset(mat,mat_path)
        mesh_path=DEST+'/Meshes/'+name
        mesh=u.load_asset(mesh_path) if u.EditorAssetLibrary.does_asset_exist(mesh_path) else None
        mesh_key=signature([asset['file_sha256'],image['sha256'],graph_sha,'LegacyFBX|metres|preserve|normals|NoCollision'])
        if not mesh or state['meshes'].get(name)!=mesh_key:
            task=u.AssetImportTask(); task.filename=str(root/asset['file']); task.destination_path=DEST+'/Meshes'; task.destination_name=name
            task.automated=True; task.replace_existing=True; task.replace_existing_settings=True; task.save=True; task.factory=u.FbxFactory()
            options=u.FbxImportUI(); options.import_mesh=True; options.import_textures=False; options.import_materials=False
            options.set_editor_property('automated_import_should_detect_type',False); options.mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH
            data=options.static_mesh_import_data
            for key,value in dict(combine_meshes=True,generate_lightmap_u_vs=False,auto_generate_collision=False,
                                  convert_scene=True,convert_scene_unit=True,remove_degenerates=False).items():
                data.set_editor_property(key,value)
            data.set_editor_property('normal_import_method',u.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
            task.options=options; tools.import_asset_tasks([task]); mesh=own_asset(u.load_asset(mesh_path),mesh_path)
            u.ShowcaseEditor.configure_geographic_mesh(mesh,False,False,True)
            mesh.set_material(0,mat); mesh_bounds(u,mesh,asset); save_asset(u,mesh,mesh_path)
            state['meshes'][name]=mesh_key
        own_asset(mesh,mesh_path); mesh_bounds(u,mesh,asset)
        require(mesh.get_material(0)==mat, 'Ground mesh material drifted '+name)
        meshes[name]=mesh
        records.append(dict(name=name,mesh=mesh_path,material=mat_path,texture=tex_path,
                            fbx_sha256=asset['file_sha256'],image_sha256=image['sha256'],triangles=asset['triangles'],
                            bounds_m=asset['bounds_m'],dimensions_m=asset['dimensions_m']))
    # Never remove existing overlays until every source/import/bounds check passed.
    assert_world(u)
    created=[]
    try:
        for placement in catalog['placements']:
            actor=require(actors.spawn_actor_from_class(u.StaticMeshActor,u.Vector(*(v*100 for v in placement['position_m']))), 'Ground actor creation failed')
            created.append(actor)
            actor.set_actor_label(placement['asset']+' native ground detail')
            actor.set_editor_property('tags',[OWNER]); actor.set_actor_enable_collision(False)
            actor.set_actor_scale3d(u.Vector(1,1,1))
            component=actor.static_mesh_component
            require(component.set_static_mesh(meshes[placement['asset']]), 'Ground mesh assignment failed')
            component.set_mobility(u.ComponentMobility.STATIC)
            component.set_collision_profile_name('NoCollision'); component.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
            component.set_cast_shadow(False); component.set_cull_distance(0)
            location=actor.get_actor_location()
            close([location.x,location.y,location.z],[v*100 for v in placement['position_m']], 'ground actor location',.01)
            require(component.get_collision_enabled()==u.CollisionEnabled.NO_COLLISION, 'Ground actor collision enabled')
        require(len(created)==COUNT, 'Incomplete ground actor set')
    except Exception:
        for actor in created:
            actors.destroy_actor(actor)
        raise
    for actor in old:
        require(OWNER in map(str,actor.get_editor_property('tags')), 'Ground actor ownership changed')
        require(actors.destroy_actor(actor), 'Previous owned ground actor removal failed')
    state.update(catalog_sha256=digest(root/SOURCE/'Exports/assets.json'),script_sha256=script_sha,material_graph_sha256=graph_sha)
    folder.mkdir(parents=True,exist_ok=True)
    state_path.write_text(json.dumps(state,indent=2))
    report=dict(map=MAP,world=WORLD,owner=OWNER,actors=len(created),previous_owned_actors_removed=len(old),
                meshes=len(meshes),materials=COUNT,textures=COUNT,triangles=triangles,height_m=HEIGHT,
                collision='NoCollision',actor_collision=False,cast_shadow=False,mobility='Static',far_cull_cm=0,
                texture_max_size=PIXELS,srgb=True,address='CLAMP',compression='DEFAULT',uv_channel=0,
                material_recipe=MATERIAL_RECIPE,source_scene_sha256=catalog['source_scene_sha256'],
                generator_sha256=catalog['generator_sha256'],imagery_manifest_sha256=catalog['imagery_manifest_sha256'],
                blend_sha256=catalog['blend_sha256'],catalog_sha256=state['catalog_sha256'],script_sha256=script_sha,
                material_graph_sha256=graph_sha,independent_build_data=True,built_data_modified=False,
                level_saved=False,caller_must_save_new_map=True,assets=records)
    (folder/'ground-authored.json').write_text(json.dumps(report,indent=2))
    u.log('AERONAUT_KEYWEST_DETAIL_GROUND_CONTENT_READY '+json.dumps({k:report[k] for k in ('actors','meshes','materials','textures','triangles','level_saved')}))
    return report


def self_test():
    """Temporary input fixtures and read-only engine guards; no Unreal/PIL/bpy."""
    import copy
    import tempfile
    from types import SimpleNamespace as NS

    def rejected(call,label):
        try:
            call()
        except ValueError:
            return
        raise AssertionError('Accepted '+label)

    class World:
        def __init__(self,path): self.path=path
        def get_path_name(self): return self.path
    def fake_engine(world=WORLD,deps=None,built=BUILT+'.KeyWestDetail_BuiltData'):
        return NS(UnrealEditorSubsystem=object,AssetRegistryDependencyOptions=lambda **kw:kw,
                  get_editor_subsystem=lambda kind:NS(get_editor_world=lambda:World(world)),
                  AssetRegistryHelpers=NS(get_asset_registry=lambda:NS(get_dependencies=lambda *args:deps if deps is not None else [BUILT])),
                  load_asset=lambda path:World(built) if built else None)
    assert_world(fake_engine())
    for engine in (fake_engine(world='/Game/KeyWest/KeyWest.KeyWest'),fake_engine(world=WORLD+'_Other'),
                   fake_engine(deps=[]),fake_engine(deps=[BUILT,'/Game/KeyWest/KeyWest_BuiltData']),
                   fake_engine(built='/Game/KeyWest/KeyWest_BuiltData.KeyWest_BuiltData'),fake_engine(built=None)):
        rejected(lambda:import_and_place(engine,Path('must-not-be-read')), 'wrong world/shared or missing build data')
    with tempfile.TemporaryDirectory(prefix='keywest-ground-import-') as temporary:
        root=Path(temporary)
        def write(name,data):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path
        write('Art/KeyWest/Data/scene.json',b'fixture scene')
        write('Art/KeyWestGround.py',b'fixture generator')
        write(SOURCE/'Data/imagery.json',b'fixture imagery')
        blend=write(SOURCE/'KeyWestGround.blend',b'fixture blend')
        tiles=[];images=[];assets=[];placements=[]
        for index in range(COUNT):
            region='oldtown' if index<16 else 'airport';local=index%16
            ident=f'{region}_r{local//4}_c{local%4}';name='KWD_Ground_'+ident
            n0,e0=float(index*700),10.;n1,e1=n0+614.4,e0+614.4
            tile=dict(id=ident,asset=name,region=region,bounds_ne=[n0,e0,n1,e1],extent_wgs84=[0.,0.,1.,1.],
                      pixels=[2048,2048],nominal_metres_per_pixel=.3,land_area_m2=50.,
                      position_m=[n0,e0,0],height_m=HEIGHT,triangles_ne=[[(n0,e0),(n0+10,e0),(n0,e0+10)]])
            image_path=write(SOURCE/'Textures'/(ident+'.jpg'),b'fixture verified jpeg '+str(index).encode())
            image=dict(file=image_path.relative_to(root).as_posix(),bytes=image_path.stat().st_size,sha256=digest(image_path),
                       pixels=[2048,2048],validation=dict(rgb_mode='RGB'))
            fbx=write(SOURCE/'Exports'/(name+'.fbx'),b'fixture fbx '+str(index).encode())
            asset={k:v for k,v in tile.items() if k!='triangles_ne'} | dict(name=name,pivot=[0,0,0],
                    bounds_m=[[0.,0.,HEIGHT],[10.,10.,HEIGHT]],dimensions_m=[10.,10.,0.],triangles=1,
                    materials=['KWD_GroundTexture_'+ident],collision=False,foliage=False,role='ground_overlay',texture=image,
                    file=fbx.relative_to(root).as_posix(),file_sha256=digest(fbx),file_bytes=fbx.stat().st_size)
            tiles.append(tile);images.append(image);assets.append(asset)
            placements.append(dict(asset=name,position_m=tile['position_m'],yaw_deg=0,scale=[1,1,1]))
        manifest=dict(tiles=images,source_scene_sha256=digest(root/'Art/KeyWest/Data/scene.json'),generator_sha256=digest(root/'Art/KeyWestGround.py'))
        catalog=dict(schema=1,units='metres',axes=AXES,assets=assets,placements=placements,height_m=HEIGHT,
                     nominal_metres_per_pixel=.3,expected_unreal_uv0=UV_CONTRACT,triangle_budget=100000,
                     source_scene_sha256=manifest['source_scene_sha256'],generator_sha256=manifest['generator_sha256'],
                     imagery_manifest_sha256=digest(root/SOURCE/'Data/imagery.json'),blend_file=blend.relative_to(root).as_posix(),
                     blend_bytes=blend.stat().st_size,blend_sha256=digest(blend))
        require(validate_catalog(root,tiles,manifest,catalog)==COUNT, 'Planar-zero-height fixture rejected')
        changes=[lambda c:c['assets'][0].update(name='KW_Geo_land'),lambda c:c['assets'][0].update(role='city_shell'),
                 lambda c:c['assets'][0].update(collision=True),lambda c:c['assets'][0].update(file='../escape.fbx'),
                 lambda c:c['assets'][0].update(file_bytes=0),lambda c:c['assets'][0].update(file_sha256='0'*64),
                 lambda c:c['assets'][0].update(dimensions_m=[10,10,.01]),lambda c:c['assets'][0].update(bounds_m=[[0,0,HEIGHT],[10,10,float('nan')]]),
                 lambda c:c['assets'][0].update(pivot=[1,0,0]),lambda c:c['placements'][0].update(position_m=[0,0,1]),
                 lambda c:c['placements'][0].update(yaw_deg=90),lambda c:c['placements'][0].update(scale=[1,1,2]),
                 lambda c:c.update(generator_sha256='0'*64),lambda c:c.update(source_scene_sha256='0'*64),
                 lambda c:c.update(imagery_manifest_sha256='0'*64),lambda c:c.update(blend_sha256='0'*64),
                 lambda c:c.update(assets=c['assets'][:-1]),lambda c:c['assets'][1].update(name=c['assets'][0]['name']),
                 lambda c:c['assets'][-1].update(file_sha256='0'*64),lambda c:c['placements'][-1].update(scale=[1,True,1])]
        for change in changes:
            broken=copy.deepcopy(catalog);change(broken)
            rejected(lambda:validate_catalog(root,tiles,manifest,broken), 'altered input contract')
        imported=NS(x=1000.,y=1000.,z=0.)
        center=NS(x=500.,y=500.,z=HEIGHT*100)
        mesh=NS(get_bounds=lambda:NS(origin=center))
        fake=NS(ShowcaseEditor=NS(mesh_dimensions=lambda item:imported))
        mesh_bounds(fake,mesh,assets[0])
        imported.z=3.1;rejected(lambda:mesh_bounds(fake,mesh,assets[0]), 'nonplanar imported bounds')
        imported.z=0.;center.x+=3.1;rejected(lambda:mesh_bounds(fake,mesh,assets[0]), 'wrong imported pivot')
        own_asset(World(DEST+'/Meshes/KWD_Ground_fixture.KWD_Ground_fixture'),DEST+'/Meshes/KWD_Ground_fixture')
        rejected(lambda:own_asset(World('/Game/KeyWest/Meshes/Old.Old'),DEST+'/Meshes/KWD_Ground_fixture'), 'old asset mutation')
        rejected(lambda:own_asset(World('/Game/KeyWest/Meshes/Old.Old'),'/Game/KeyWest/Meshes/Old'), 'old destination')
    print('PASS ground catalog/hash/role/path/finite-planar-bounds/placement contracts, exact-world and independent-data negative guards; Unreal API NOT EXECUTED')


if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        self_test()
    else:
        raise SystemExit('Import import_and_place(unreal, root) from the backed-up new-map caller, or use --self-test')
