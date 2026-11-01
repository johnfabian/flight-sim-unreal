"""Import original Blender art and author a persistent, baked-lighting-ready level.
Run explicitly in UnrealEditor-Cmd -run=pythonscript -script=... -nullrhi.
An existing scene is preserved unless -ShowcaseRegenerate is supplied.
"""
import unreal, math, json, random, array, runpy, sys
from pathlib import Path
ROOT=Path(unreal.Paths.project_dir()).resolve()
DEST='/Game/Showcase'
ARGS=unreal.SystemLibrary.get_command_line().split()
FORCE='-ShowcaseRegenerate' in ARGS
FORCE_MAP=FORCE or '-ShowcaseRebuildLayout' in ARGS
FORCE_MATERIALS=FORCE or '-ShowcaseRegenerateMaterials' in ARGS
UPDATE_MATERIALS={a.split('=',1)[1] for a in ARGS if a.startswith('-ShowcaseMaterial=')}
STATIC_MATERIALS={'Landscape','Runway','Rock','Bark','Foliage','Grass','Concrete','Wood','Hangar','Roof','Markings','Metal','DarkMetal','Rubber','Glass','WhiteLight','Orange'}
tools=unreal.AssetToolsHelpers.get_asset_tools(); edit=unreal.MaterialEditingLibrary
for d in [DEST,DEST+'/Meshes',DEST+'/Materials',DEST+'/Textures',DEST+'/Blueprints',DEST+'/ImportProbe']: unreal.EditorAssetLibrary.make_directory(d)

def checked(value,message):
    if not value: raise RuntimeError(message)
    return value
def optional_asset(path): return unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None

def import_texture(path,name,normal=False,linear=False):
    existing=optional_asset(DEST+'/Textures/'+name)
    if existing and not FORCE: return existing
    task=unreal.AssetImportTask(); task.filename=str(path); task.destination_path=DEST+'/Textures'; task.destination_name=name
    task.automated=True; task.replace_existing=True; task.save=True; tools.import_asset_tasks([task])
    texture=checked(unreal.load_asset(DEST+'/Textures/'+name),'Texture import failed '+name)
    texture.set_editor_property('max_texture_size',2048 if name not in ('Sky',) else 1024)
    if normal:
        texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP)
        texture.set_editor_property('srgb',False)
        if name=='AircraftNormal': texture.set_editor_property('flip_green_channel',True)
    elif linear:
        texture.set_editor_property('srgb',False)
        texture.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_MASKS)
    unreal.EditorAssetLibrary.save_loaded_asset(texture); return texture

tex={}
for key,filename in [('Asphalt','aerial_asphalt_01'),('Forest','forest_floor'),('Rock','coast_land_rocks_01'),('Bark','tree_bark'),('Twig','tree_twig')]:
    for suffix,ext in [('Base','png' if key=='Twig' else 'jpg'),('Normal','png'),('ARM','jpg')]:
        tex[key+suffix]=import_texture(ROOT/'Art/Textures/CC0'/f'{filename}_{suffix.lower() if suffix!="Base" else "base"}.{ext}',key+suffix,normal=suffix=='Normal',linear=suffix=='ARM')
tex['TwigMask']=import_texture(ROOT/'Art/Textures/CC0/tree_twig_mask.png','TwigMask',linear=True)
tex['Dials']=import_texture(ROOT/'Art/Textures/Original/instrument_atlas.png','Dials')
tex['AircraftNormal']=import_texture(ROOT/'Art/Textures/Original/aircraft_surface_normal.png','AircraftNormal',normal=True)
tex['Sky']=import_texture(ROOT/'Art/Textures/CC0/coastal_sky.hdr','Sky')
tex['ShoreMask']=import_texture(ROOT/'Art/Textures/Original/shore_mask.png','ShoreMask',linear=True)
tex['Dials'].set_editor_property('never_stream',True)
tex['Dials'].set_editor_property('lod_group',unreal.TextureGroup.TEXTUREGROUP_UI)
tex['ShoreMask'].set_editor_property('address_x',unreal.TextureAddress.TA_CLAMP)
tex['ShoreMask'].set_editor_property('address_y',unreal.TextureAddress.TA_CLAMP)
for key in ('Dials','ShoreMask'): unreal.EditorAssetLibrary.save_loaded_asset(tex[key])

sys.path.insert(0,str(ROOT/'Scripts'))
from showcase_material_api import node,scalar,color,prop,link,sample,multiply,mix,custom,world_uv,material_api
from showcase_land import build_landscape,build_rock,build_foliage
from showcase_water import build_water
surface_api=material_api(tex)

def generated(name,build):
    path=DEST+'/Materials/M_'+name; mat=optional_asset(path)
    if mat and not FORCE_MATERIALS and name not in UPDATE_MATERIALS: return mat
    if not mat: mat=tools.create_asset('M_'+name,DEST+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
    # UE 5.8's bulk deletion iterates the collection it removes from. Delete a
    # snapshot so repeated updates cannot leave old custom output nodes behind.
    for expression in list(edit.get_material_expressions(mat)):
        edit.delete_material_expression(mat,expression)
    checked(not edit.get_material_expressions(mat),'Material graph did not clear '+name)
    build(mat)
    if name=='Water':
        outputs=[e for e in edit.get_material_expressions(mat) if isinstance(e,unreal.MaterialExpressionSingleLayerWaterMaterialOutput)]
        checked(len(outputs)==1,'Water must have exactly one Single Layer Water output')
    if name in ('Rock','Bark','Foliage','Grass'): mat.set_editor_property('used_with_instanced_static_meshes',True)
    if name in STATIC_MATERIALS: mat.set_editor_property('used_with_static_lighting',True)
    edit.recompile_material(mat)
    checked(unreal.EditorAssetLibrary.save_loaded_asset(mat),'Material save failed '+name); return mat

palette={'Paint':((.68,.70,.66),.32,0),'Orange':((.65,.12,.028),.35,0),'Metal':((.35,.38,.37),.3,.85),'DarkMetal':((.028,.036,.034),.42,.6),
         'Rubber':((.015,.018,.017),.85,0),'Interior':((.038,.046,.041),.72,0),'Leather':((.13,.085,.045),.67,0),
         'Concrete':((.3,.29,.25),.86,0),'Wood':((.18,.12,.065),.9,0),'Hangar':((.21,.29,.27),.62,.3),'Roof':((.10,.15,.14),.5,.7),
         'Needle':((.9,.65,.16),.45,0),'Markings':((.73,.72,.62),.7,0),'Grass':((.12,.20,.055),.95,0)}
mats={}
def flat_builder(rgb,rough,metal):
    def build(m):
        if rgb in (palette['Needle'][0],palette['Grass'][0]): m.set_editor_property('two_sided',True)
        prop(color(m,rgb),unreal.MaterialProperty.MP_BASE_COLOR); prop(scalar(m,rough),unreal.MaterialProperty.MP_ROUGHNESS); prop(scalar(m,metal),unreal.MaterialProperty.MP_METALLIC)
        if rgb==palette['Paint'][0]: prop(sample(m,tex['AircraftNormal']),unreal.MaterialProperty.MP_NORMAL)
    return build
for name,(rgb,rough,metal) in palette.items(): mats[name]=generated(name,flat_builder(rgb,rough,metal))

def textured(m,prefix,uv=None):
    base=sample(m,tex[prefix+'Base'],uv); prop(base,unreal.MaterialProperty.MP_BASE_COLOR,'RGB')
    prop(sample(m,tex[prefix+'Normal'],uv),unreal.MaterialProperty.MP_NORMAL,'RGB')
    packed=sample(m,tex[prefix+'ARM'],uv)
    prop(packed,unreal.MaterialProperty.MP_AMBIENT_OCCLUSION,'R'); prop(packed,unreal.MaterialProperty.MP_ROUGHNESS,'G'); prop(packed,unreal.MaterialProperty.MP_METALLIC,'B')
mats['Rock']=generated('Rock',lambda m:build_rock(surface_api,m))
mats['Bark']=generated('Bark',lambda m:textured(m,'Bark'))
mats['Runway']=generated('Runway',lambda m:textured(m,'Asphalt',world_uv(m,.00015)))

def foliage(m):
    return build_foliage(surface_api,m)
mats['Foliage']=generated('Foliage',foliage)

def glass(m):
    m.set_editor_property('two_sided',True); m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
    prop(color(m,(.11,.19,.21)),unreal.MaterialProperty.MP_BASE_COLOR); prop(scalar(m,.10),unreal.MaterialProperty.MP_ROUGHNESS)
    prop(scalar(m,.13),unreal.MaterialProperty.MP_OPACITY); prop(scalar(m,.65),unreal.MaterialProperty.MP_SPECULAR)
mats['Glass']=generated('Glass',glass)

def dials(m):
    m.set_editor_property('two_sided',True)
    image=sample(m,tex['Dials']); prop(image,unreal.MaterialProperty.MP_BASE_COLOR,'RGB'); prop(scalar(m,.7),unreal.MaterialProperty.MP_ROUGHNESS)
    prop(multiply(m,image,scalar(m,.055)),unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mats['Dial']=generated('Dial',dials)

def horizon(m):
    m.set_editor_property('two_sided',True); m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_MASKED)
    uv=node(m,unreal.MaterialExpressionTextureCoordinate)
    pitch=node(m,unreal.MaterialExpressionScalarParameter); pitch.set_editor_property('parameter_name','Pitch')
    c=custom(m,'float y=.5-UV.y+Pitch*.26; float3 c=lerp(float3(.24,.12,.045),float3(.08,.25,.38),smoothstep(-.004,.004,y)); return lerp(c,float3(.8,.85,.76),1-smoothstep(.003,.009,abs(y)));',dict(UV=uv,Pitch=pitch))
    prop(c,unreal.MaterialProperty.MP_BASE_COLOR); prop(multiply(m,c,scalar(m,.12)),unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mask=custom(m,'return .49-length(UV-.5);',dict(UV=uv),unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    m.set_editor_property('opacity_mask_clip_value',0.0); prop(mask,unreal.MaterialProperty.MP_OPACITY_MASK)
mats['Horizon']=generated('Horizon',horizon)
for name,rgb in [('RedLight',(.8,.005,.002)),('GreenLight',(.002,.65,.08)),('WhiteLight',(.8,.73,.5))]:
    def light(m,c=rgb):
        prop(color(m,c),unreal.MaterialProperty.MP_BASE_COLOR); prop(color(m,tuple(v*3 for v in c)),unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mats[name]=generated(name,light)

def landscape(m):
    return build_landscape(surface_api,m)
mats['Landscape']=generated('Landscape',landscape)

def water(m):
    return build_water(surface_api,m)
mats['Water']=generated('Water',water)

def sky(m):
    m.set_editor_property('two_sided',True); m.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT); m.set_editor_property('is_sky',True)
    direction=multiply(m,node(m,unreal.MaterialExpressionCameraVectorWS),scalar(m,-1))
    t=node(m,unreal.MaterialExpressionTextureSample); t.set_editor_property('texture',tex['Sky']); t.set_editor_property('sampler_type',unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    link(direction,t,'UVs'); prop(multiply(m,t,scalar(m,.65)),unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mats['Sky']=generated('Sky',sky)
def damp_apron(m):
    m.set_editor_property('material_domain',unreal.MaterialDomain.MD_DEFERRED_DECAL)
    m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
    uv=node(m,unreal.MaterialExpressionTextureCoordinate)
    mask=custom(m,'float2 p=(UV-.5)*2; float edge=1-dot(p,p); float detail=sin(UV.x*27+sin(UV.y*37))*sin(UV.y*23); return saturate((edge+detail*.10)*4)*.55;',dict(UV=uv),unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    prop(color(m,(.012,.022,.020)),unreal.MaterialProperty.MP_BASE_COLOR)
    prop(scalar(m,.16),unreal.MaterialProperty.MP_ROUGHNESS)
    prop(mask,unreal.MaterialProperty.MP_OPACITY)
mats['DampApron']=generated('DampApron',damp_apron)
for name in ('Rock','Bark','Foliage','Grass'):
    if not mats[name].get_editor_property('used_with_instanced_static_meshes'):
        mats[name].set_editor_property('used_with_instanced_static_meshes',True)
        unreal.EditorAssetLibrary.save_loaded_asset(mats[name])
for name in STATIC_MATERIALS:
    if not mats[name].get_editor_property('used_with_static_lighting'):
        mats[name].set_editor_property('used_with_static_lighting',True)
        unreal.EditorAssetLibrary.save_loaded_asset(mats[name])

manifest=json.loads((ROOT/'Art/Exports/assets.json').read_text()); meshes={}
for spec in sorted(manifest['assets'],key=lambda s: s['name']!='PipelineTest'):
    name=spec['name']; folder=DEST+('/ImportProbe' if name in ('PipelineTest','PipelineAxes') else '/Meshes')
    path=folder+'/'+name; sm=optional_asset(path)
    if sm and FORCE:
        # Old Interchange import data can silently retain centimetre conversion
        # during replacement. Explicit regeneration creates a fresh legacy import.
        checked(unreal.EditorAssetLibrary.delete_asset(path),'Unable to replace generated mesh '+name)
        sm=None
    if not sm or FORCE:
        task=unreal.AssetImportTask(); task.filename=str(ROOT/'Art/Exports'/f'{name}.fbx'); task.destination_path=folder; task.destination_name=name
        task.automated=True; task.replace_existing=True; task.replace_existing_settings=True; task.save=True; task.factory=unreal.FbxFactory()
        options=unreal.FbxImportUI(); options.import_mesh=True; options.import_textures=False; options.import_materials=False
        options.set_editor_property('automated_import_should_detect_type',False); options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
        options.static_mesh_import_data.set_editor_property('combine_meshes',True)
        options.static_mesh_import_data.set_editor_property('generate_lightmap_u_vs',True)
        options.static_mesh_import_data.set_editor_property('auto_generate_collision',False)
        options.static_mesh_import_data.set_editor_property('convert_scene',True)
        options.static_mesh_import_data.set_editor_property('convert_scene_unit',True)
        options.static_mesh_import_data.set_editor_property('remove_degenerates',False)
        options.static_mesh_import_data.set_editor_property('normal_import_method',unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        task.options=options; tools.import_asset_tasks([task]); sm=checked(unreal.load_asset(path),'FBX import failed '+name)
        unreal.ShowcaseEditor.configure_mesh(sm,spec['collision'],spec['foliage'])
        for slot,matname in enumerate(spec['materials']): sm.set_material(slot,mats['Horizon'] if name=='Horizon' else mats[matname])
        unreal.EditorAssetLibrary.save_loaded_asset(sm)
    meshes[name]=sm
    if name=='PipelineTest':
        dim=unreal.ShowcaseEditor.mesh_dimensions(sm)
        unreal.log('AERONAUT_IMPORT_TEST_DIMENSIONS '+str(dim))
        checked(max(abs(dim.x-100),abs(dim.y-100),abs(dim.z-100))<1,'FBX scale test failed '+str(dim))
    if name=='PipelineAxes':
        center=sm.get_bounds().origin
        checked(max(abs(center.x-100),abs(center.y-200),abs(center.z-300))<1,'FBX axis test failed '+str(center))
        unreal.log('AERONAUT_PIPELINE_AXES_PASS '+str(center))
dim=unreal.ShowcaseEditor.mesh_dimensions(meshes['PipelineTest']); checked(max(abs(dim.x-100),abs(dim.y-100),abs(dim.z-100))<1,'FBX metre-to-centimetre scale test failed '+str(dim))
unreal.log('AERONAUT_PIPELINE_SCALE_PASS '+str(dim))
unreal.log('AERONAUT_AIRFRAME_DIMENSIONS '+str(unreal.ShowcaseEditor.mesh_dimensions(meshes['Airframe'])))
body_dim=unreal.ShowcaseEditor.mesh_dimensions(meshes['Airframe'])
checked(650<body_dim.x<750 and 600<body_dim.y<710,'Aircraft FBX scale/axes mismatch '+str(body_dim))

def blueprint(name,parent):
    path=DEST+'/Blueprints/'+name; bp=optional_asset(path)
    if not bp:
        factory=unreal.BlueprintFactory(); factory.set_editor_property('parent_class',parent)
        bp=tools.create_asset(name,DEST+'/Blueprints',unreal.Blueprint,factory)
    return checked(bp,'Blueprint failed '+name)
new_pawn=not unreal.EditorAssetLibrary.does_asset_exist(DEST+'/Blueprints/BP_CoastalAircraft')
pawn_bp=blueprint('BP_CoastalAircraft',unreal.load_class(None,'/Script/Aeronaut.FlightPawn'))
pawn_class=unreal.load_class(None,DEST+'/Blueprints/BP_CoastalAircraft.BP_CoastalAircraft_C')
defaults=unreal.get_default_object(pawn_class)
aircraft=manifest['assets'][:26]
for spec in aircraft:
    mesh=meshes[spec['name']]
    # Cooked mesh streaming must not evict the full-detail close cockpit/airframe.
    if not mesh.get_editor_property('never_stream'):
        mesh.set_editor_property('never_stream',True)
        checked(unreal.EditorAssetLibrary.save_loaded_asset(mesh),'Aircraft residency save failed '+spec['name'])
if new_pawn or FORCE_MAP:
    defaults.set_editor_property('visual_meshes',{s['name']:meshes[s['name']] for s in aircraft})
    defaults.set_editor_property('visual_pivots',{s['name']:unreal.Vector(*(v*100 for v in s['pivot'])) for s in aircraft})
    defaults.set_editor_property('chase_distance',2100.0)
    defaults.set_editor_property('cockpit_anchor',unreal.Vector(20,-20,74)); defaults.set_editor_property('cockpit_look_pitch',-13.0)
unreal.EditorAssetLibrary.save_loaded_asset(pawn_bp)
new_mode=not unreal.EditorAssetLibrary.does_asset_exist(DEST+'/Blueprints/BP_CoastalGameMode')
mode_bp=blueprint('BP_CoastalGameMode',unreal.load_class(None,'/Script/Aeronaut.FlightGameMode'))
mode_class=unreal.load_class(None,DEST+'/Blueprints/BP_CoastalGameMode.BP_CoastalGameMode_C')
if new_mode or FORCE_MAP: unreal.get_default_object(mode_class).set_editor_property('default_pawn_class',pawn_class)
unreal.EditorAssetLibrary.save_loaded_asset(mode_bp)

MAP=DEST+'/CoastalShowcase'
BUILD_MAP=not unreal.EditorAssetLibrary.does_asset_exist(MAP) or FORCE_MAP
if BUILD_MAP:
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    checked(levels.new_level(MAP),'Unable to create showcase map')
    subsystem=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    settings=world.get_world_settings(); settings.set_editor_property('default_game_mode',mode_class)
    lm=settings.get_editor_property('lightmass_settings'); lm.num_indirect_lighting_bounces=3; lm.num_sky_lighting_bounces=2; lm.indirect_lighting_quality=1.0
    lm.volumetric_lightmap_detail_cell_size=1600.0; lm.volumetric_lightmap_maximum_brick_memory_mb=30.0
    settings.set_editor_property('lightmass_settings',lm)
    land=checked(unreal.ShowcaseEditor.import_landscape(str(ROOT/'Art/Exports/coast.r16'),mats['Landscape']),'Landscape import failed')
    raw=array.array('H'); raw.frombytes((ROOT/'Art/Exports/coast.r16').read_bytes())
    def height(x,y):
        fx=max(0,min(1008,(x+1512)/3)); fy=max(0,min(1008,(y+1512)/3)); ix=min(1007,int(fx)); iy=min(1007,int(fy)); ax=fx-ix; ay=fy-iy
        h=(raw[iy*1009+ix]*(1-ax)+raw[iy*1009+ix+1]*ax)*(1-ay)+(raw[(iy+1)*1009+ix]*(1-ax)+raw[(iy+1)*1009+ix+1]*ax)*ay
        return (h-32768)/50
    def actor(name,mesh_name,p,scale=(1,1,1),yaw=0,collision=True,material=None):
        a=subsystem.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*(v*100 for v in p)),unreal.Rotator(yaw=yaw))
        a.set_actor_label(name); c=a.static_mesh_component; c.set_static_mesh(meshes[mesh_name] if isinstance(mesh_name,str) else mesh_name)
        c.set_collision_profile_name('BlockAll' if collision else 'NoCollision')
        a.set_actor_enable_collision(collision)
        c.set_mobility(unreal.ComponentMobility.STATIC); c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS if collision else unreal.CollisionEnabled.NO_COLLISION)
        if material: c.set_material(0,material)
        a.set_actor_scale3d(unreal.Vector(*scale)); return a
    # Runway ends at x=-730 and -130, with the apron and hangars north of it.
    actor('Runway 600m','RunwaySlab',(-430,-475,22.12),(600,22,1))
    actor('Apron','RunwaySlab',(-560,-423,22.10),(145,82,1))
    for x in range(-710,-130,35): actor('Runway centre marking','Marking',(x,-475,22.16),(16,.38,1),collision=False)
    for x in (-704,-156):
        for side in (-1,1):
            for k in range(4): actor('Threshold stripe','Marking',(x, -475+side*(2.0+k*1.5),22.17),(17,.65,1),collision=False)
    for y in (-485.5,-464.5): actor('Runway edge paint','Marking',(-430,y,22.16),(590,.18,1),collision=False)
    actor('West hangar','Hangar',(-605,-395,22.14),yaw=90)
    actor('East hangar','Hangar',(-552,-394,22.14),yaw=90)
    actor('Operations cabin','ServiceBuilding',(-505,-391,22.14),yaw=0)
    actor('Fuel station','FuelTank',(-480,-415,22.14))
    actor('Windsock','Windsock',(-748,-505,height(-748,-505)))
    for x in range(-740,-110,35):
        for y in (-491,-459): actor('Runway edge lamp','RunwayLight',(x,y,height(x,y)),collision=False)
    for x in range(-720,-180,3): actor('Perimeter fence','Fence',(x,-355,height(x,-355)),collision=False)
    for x in range(-625,-505,18): actor('Apron safety cone','Cone',(x,-444,22.2),collision=False)
    # A single saved instancing actor per variant keeps forest draw calls bounded.
    rng=random.Random(18281); trees=[[] for _ in range(4)]; rocks=[[] for _ in range(5)]; grasses=[]; logs=[]
    for j in range(5200):
        x,y=rng.uniform(-1450,1450),rng.uniform(-1450,1450); z=height(x,y)
        in_airfield=abs(x+430)<455 and abs(y+475)<185
        slope=max(abs(height(x+3,y)-height(x-3,y)),abs(height(x,y+3)-height(x,y-3)))/6
        if 16<z<330 and not in_airfield and slope<.8 and math.sin(x*.012)*math.cos(y*.01)>-.25:
            scale=rng.uniform(.7,1.35)
            trees[j%4].append(unreal.Transform(location=unreal.Vector(x*100,y*100,z*100),rotation=unreal.Rotator(yaw=rng.uniform(0,360)),scale=unreal.Vector(scale,scale,scale)))
        if 0<z<20 and not in_airfield and j%3==0:
            scale=rng.uniform(.6,2.4); rocks[j%5].append(unreal.Transform(location=unreal.Vector(x*100,y*100,z*100-50),rotation=unreal.Rotator(pitch=rng.uniform(-15,15),yaw=rng.uniform(0,360)),scale=unreal.Vector(scale,scale,scale)))
            if j%18==0: logs.append((x,y,z))
    for j in range(700):
        x,y=rng.uniform(-820,-60),rng.uniform(-655,-295); z=height(x,y)
        if abs(y+475)>18 and not (x<-470 and y>-455): grasses.append(unreal.Transform(location=unreal.Vector(x*100,y*100,z*100),rotation=unreal.Rotator(yaw=rng.uniform(0,360)),scale=unreal.Vector(1,1,1)))
    def instances(label,sm,transforms,cull,shadows=False,collision=False):
        a=subsystem.spawn_actor_from_class(unreal.InstancedScenery,unreal.Vector()); a.set_actor_label(label)
        c=a.instances; c.set_static_mesh(sm); c.set_cull_distances(int(cull*.8),cull); c.set_cast_shadow(shadows)
        c.set_collision_profile_name('BlockAll' if collision else 'NoCollision')
        a.set_actor_enable_collision(collision)
        a.set_editor_property('allow_density_scaling',not collision)
        c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS if collision else unreal.CollisionEnabled.NO_COLLISION)
        c.add_instances(transforms,False,False)
        return a
    for j,items in enumerate(trees): instances('Forest conifer '+str(j),meshes['Conifer'+str(j)],items,175000,True)
    for j,items in enumerate(rocks): instances('Shoreline rocks '+str(j),meshes['CoastalRock'+str(j)],items,210000,True,True)
    instances('Airfield grass',meshes['GrassClump'],grasses,18000)
    for j,p in enumerate(logs): actor('Shoreline driftwood','Driftwood',p,yaw=rng.uniform(0,360))
    # Large cliff outcrops remain substantial silhouettes rather than texture-only slopes.
    for j in range(45):
        a=j*math.tau/45; x,y=150+math.cos(a)*1120,200+math.sin(a)*850; z=height(x,y)
        if z>4 and not(abs(x+430)<460 and abs(y+475)<190): actor('Coastal cliff outcrop','CoastalRock'+str(j%5),(x,y,z-5),(rng.uniform(3,7),rng.uniform(3,6),rng.uniform(3,7)),rng.uniform(0,360))
    plane=unreal.load_asset('/Engine/BasicShapes/Plane.Plane')
    ocean=actor('Pacific coastal ocean',plane,(0,0,0),(16000,16000,1),collision=False,material=mats['Water'])
    ocean.static_mesh_component.set_cast_shadow(False)
    ocean.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sphere=unreal.load_asset('/Engine/BasicShapes/Sphere.Sphere')
    backdrop=actor('Coastal cloud sky',sphere,(0,0,0),(15000,15000,15000),collision=False,material=mats['Sky']); backdrop.static_mesh_component.set_cast_shadow(False)
    backdrop.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun=subsystem.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(),unreal.Rotator(pitch=-24,yaw=-35)); sun.set_actor_label('Late afternoon sun')
    light=sun.light_component; light.set_mobility(unreal.ComponentMobility.STATIONARY); light.set_intensity(4.5)
    light.set_light_color(unreal.LinearColor(1,.86,.69)); light.set_editor_property('dynamic_shadow_distance_stationary_light',24000)
    light.set_editor_property('dynamic_shadow_cascades',2)
    ambient=subsystem.spawn_actor_from_class(unreal.SkyLight,unreal.Vector())
    ambient.light_component.set_mobility(unreal.ComponentMobility.STATIC)
    ambient.light_component.set_editor_property('source_type',unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
    ambient.light_component.set_editor_property('cubemap',tex['Sky']); ambient.light_component.set_intensity(.55)
    fog=subsystem.spawn_actor_from_class(unreal.ExponentialHeightFog,unreal.Vector(0,0,1500)); fog.component.set_editor_property('fog_density',.0025)
    fog.component.set_editor_property('fog_height_falloff',.12); fog.component.set_fog_inscattering_color(unreal.LinearColor(.55,.65,.69))
    unreal.ShowcaseEditor.add_lighting_importance_volume()
    capture=subsystem.spawn_actor_from_class(unreal.SphereReflectionCapture,unreal.Vector(-43000,-47500,12000))
    capture.capture_component.set_editor_property('influence_radius',12000000)
    capture.capture_component.set_editor_property('reflection_source_type',unreal.ReflectionSourceType.SPECIFIED_CUBEMAP)
    capture.capture_component.set_editor_property('cubemap',tex['Sky'])
    capture.set_actor_label('Coastal HDR reflection environment')
    scene=subsystem.spawn_actor_from_class(unreal.CoastalScene,unreal.Vector())
    subsystem.spawn_actor_from_class(unreal.PlayerStart,unreal.Vector(-100000,-47500,10700))
    scene.set_editor_property('airborne_spawn',unreal.Vector(-100000,-47500,10700))
    scene.set_actor_label('Flight scene and guided route'); spline=scene.tour; spline.clear_spline_points(False)
    route=[(-1000,-475),(-700,-475),(-400,-475),(-100,-350),(150,200),(500,650),(1050,900),(1350,450),(1400,-100),(1000,-750),(300,-1050),(-500,-1050),(-1150,-950),(-1400,-700),(-1400,-475),(-1300,-475)]
    for x,y in route: spline.add_spline_point(unreal.Vector(x*100,y*100,max(107,height(x,y)+90)*100),unreal.SplineCoordinateSpace.WORLD,False)
    spline.set_closed_loop(True,True)
    for attempt in range(15):
        if scene.validate_tour(6000): break
        for point in range(spline.get_number_of_spline_points()):
            p=spline.get_location_at_spline_point(point,unreal.SplineCoordinateSpace.WORLD); p.z+=1000
            spline.set_location_at_spline_point(point,p,unreal.SplineCoordinateSpace.WORLD,False)
        spline.update_spline()
    checked(scene.validate_tour(6000),'Authored tour clearance failed')
    measured=scene.ground_height(unreal.Vector(15000,20000,0))/100
    checked(abs(measured-height(150,200))<3,'Landscape collision height mismatch '+str(measured))
    unreal.log('AERONAUT_LANDSCAPE_COLLISION_HEIGHT_PASS '+str(measured))
    unreal.log('AERONAUT_TOUR_CLEARANCE_PASS')
    checked(levels.save_current_level(),'Scene save failed')
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True,True)

checked(unreal.EditorAssetLibrary.does_asset_exist(MAP),'Saved showcase level missing')
# Migrate newly exposed scene references without changing artist-authored layout.
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem); levels.load_level(MAP)
scene_actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
scene=next((a for a in scene_actors if isinstance(a,unreal.CoastalScene)),None)
land=next((a for a in scene_actors if isinstance(a,unreal.Landscape)),None)
checked(scene and land,'Saved showcase scene is incomplete; restore or rebuild its layout')
changed=unreal.ShowcaseEditor.ensure_editor_preview()
if not scene.get_editor_property('terrain_actor'):
    scene.set_editor_property('terrain_actor',land); changed=True
if not scene.get_editor_property('collision_sources'):
    sources=[land]
    for a in scene_actors:
        c=a.static_mesh_component if isinstance(a,unreal.StaticMeshActor) else a.instances if isinstance(a,unreal.InstancedScenery) else None
        if c and a.get_actor_enable_collision() and c.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION: sources.append(a)
    scene.set_editor_property('collision_sources',sources); changed=True
# One-time detail migration; retain the marker if an artist later removes a patch.
tags=list(scene.get_editor_property('tags'))
if 'AeronautDampApronV1' not in [str(tag) for tag in tags]:
    for x,y,yaw in [(-560,-423,15),(-586,-445,-28)]:
        decal=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(unreal.DecalActor,unreal.Vector(x*100,y*100,2240),unreal.Rotator(pitch=-90,yaw=yaw))
        decal.set_actor_label('Localized damp apron'); decal.set_actor_enable_collision(False)
        component=decal.get_component_by_class(unreal.DecalComponent)
        component.set_mobility(unreal.ComponentMobility.MOVABLE); component.set_decal_material(mats['DampApron'])
        component.set_editor_property('decal_size',unreal.Vector(100,700,300))
    tags.append('AeronautDampApronV1'); scene.set_editor_property('tags',tags); changed=True
if 'AeronautSkyReflectionV1' not in [str(tag) for tag in tags]:
    captures=[a for a in scene_actors if isinstance(a,unreal.SphereReflectionCapture)]
    capture=captures[0] if len(captures)==1 else unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(unreal.SphereReflectionCapture,unreal.Vector(0,0,5000))
    capture.set_actor_label('Coastal HDR reflection environment')
    component=capture.capture_component
    component.set_editor_property('influence_radius',12000000)
    component.set_editor_property('reflection_source_type',unreal.ReflectionSourceType.SPECIFIED_CUBEMAP)
    component.set_editor_property('cubemap',tex['Sky'])
    tags.append('AeronautSkyReflectionV1'); scene.set_editor_property('tags',tags); changed=True
if changed: checked(levels.save_current_level(),'Scene reference save failed')
if BUILD_MAP: runpy.run_path(str(ROOT/'Scripts/enrich_showcase_forest.py'))
unreal.log('AERONAUT_SHOWCASE_CONTENT_READY')
