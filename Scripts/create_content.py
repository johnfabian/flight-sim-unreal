"""Run inside Unreal Editor after compiling the Aeronaut module."""
import unreal

ROOT = '/Game/Aeronaut'
unreal.EditorAssetLibrary.make_directory(ROOT)
path = ROOT + '/M_Surface'
material = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
if not material:
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'M_Surface', ROOT, unreal.Material, unreal.MaterialFactoryNew())
if not material:
    raise RuntimeError('Unable to create M_Surface')

# M_Surface is generated content. Rebuild its graph in place, keeping asset identity.
edit = unreal.MaterialEditingLibrary
edit.delete_all_material_expressions(material)
material.set_editor_property('two_sided', True)
vertex = edit.create_material_expression(material, unreal.MaterialExpressionVertexColor)
roughness = edit.create_material_expression(material, unreal.MaterialExpressionConstant)
roughness.set_editor_property('r', 0.82)
ambient = edit.create_material_expression(material, unreal.MaterialExpressionMultiply)
ambient.set_editor_property('const_b', 0.22)
# The first VertexColor output is unnamed; 'RGB' is not a valid API pin name.
connections = [
    edit.connect_material_property(vertex, '', unreal.MaterialProperty.MP_BASE_COLOR),
    edit.connect_material_property(roughness, '', unreal.MaterialProperty.MP_ROUGHNESS),
    edit.connect_material_expressions(vertex, '', ambient, 'A'),
    edit.connect_material_property(ambient, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR),
]
if not all(connections):
    raise RuntimeError('A generated material connection was rejected: ' + str(connections))
edit.recompile_material(material)
if not unreal.EditorAssetLibrary.save_loaded_asset(material):
    raise RuntimeError('Unable to save M_Surface')

# Generated water: world-space ripples continue smoothly over the entire sea.
def generated_material(name):
    asset_path = ROOT + '/' + name
    asset = unreal.load_asset(asset_path) if unreal.EditorAssetLibrary.does_asset_exist(asset_path) else None
    if not asset:
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, ROOT, unreal.Material, unreal.MaterialFactoryNew())
    edit.delete_all_material_expressions(asset)
    return asset

def connect(node, prop):
    if not edit.connect_material_property(node, '', prop):
        raise RuntimeError('Material connection rejected: ' + str(prop))

water = generated_material('M_Ocean')
water.set_editor_property('tangent_space_normal', False)
world = edit.create_material_expression(water, unreal.MaterialExpressionWorldPosition)
time = edit.create_material_expression(water, unreal.MaterialExpressionTime)
def water_expression(code):
    node = edit.create_material_expression(water, unreal.MaterialExpressionCustom)
    node.set_editor_property('code', code)
    node.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    inputs = []
    for name in ['World', 'Clock']:
        item = unreal.CustomInput()
        item.set_editor_property('input_name', name)
        inputs.append(item)
    node.set_editor_property('inputs', inputs)
    if not edit.connect_material_expressions(world, '', node, 'World') or not edit.connect_material_expressions(time, '', node, 'Clock'):
        raise RuntimeError('Water input connection failed')
    return node
normal = water_expression('float2 p=World.xy; float warp=sin(p.x*.00031+p.y*.00027)+sin(p.y*.00071-p.x*.00019); float a=cos(dot(p,float2(.0012,.00063))+warp*2+Clock*.7)*.035; float b=cos(dot(p,float2(-.0021,.0033))+warp+Clock*.95)*.014; float c=sin(dot(p,float2(.007,.0023))+warp*3-Clock*1.2)*.008; return normalize(float3(a*.85-b*.5+c,a*.45+b*.85+c*.3,1));')
color = water_expression('float v=sin(World.x*.000007+sin(World.y*.000009)); return lerp(float3(.015,.20,.26),float3(.025,.29,.32),v*.5+.5);')
connect(normal, unreal.MaterialProperty.MP_NORMAL)
connect(color, unreal.MaterialProperty.MP_BASE_COLOR)
rough = edit.create_material_expression(water, unreal.MaterialExpressionConstant)
rough.set_editor_property('r', .30)
connect(rough, unreal.MaterialProperty.MP_ROUGHNESS)
edit.recompile_material(water)
unreal.EditorAssetLibrary.save_loaded_asset(water)

gate = generated_material('M_Gate')
gate_color = edit.create_material_expression(gate, unreal.MaterialExpressionConstant3Vector)
gate_color.set_editor_property('constant', unreal.LinearColor(1.0, .38, .075, 1))
connect(gate_color, unreal.MaterialProperty.MP_BASE_COLOR)
connect(gate_color, unreal.MaterialProperty.MP_EMISSIVE_COLOR)
edit.recompile_material(gate)
unreal.EditorAssetLibrary.save_loaded_asset(gate)

# A real Blueprint child: its defaults survive subsequent content regeneration.
# Open Class Defaults in Unreal to tune handling, chase camera, paint and HUD.
bp_path = '/Game/Blueprints/BP_AeronautPawn'
if not unreal.EditorAssetLibrary.does_asset_exist(bp_path):
    unreal.EditorAssetLibrary.make_directory('/Game/Blueprints')
    factory = unreal.BlueprintFactory()
    factory.set_editor_property('parent_class', unreal.load_class(None, '/Script/Aeronaut.FlightPawn'))
    blueprint = unreal.AssetToolsHelpers.get_asset_tools().create_asset('BP_AeronautPawn', '/Game/Blueprints', unreal.Blueprint, factory)
    if not blueprint or not unreal.EditorAssetLibrary.save_loaded_asset(blueprint):
        raise RuntimeError('Unable to create flight tuning Blueprint')

map_path = ROOT + '/FlightMap'
if not unreal.EditorAssetLibrary.does_asset_exist(map_path):
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not levels.new_level(map_path):
        raise RuntimeError('Unable to create FlightMap')
    if not levels.save_current_level():
        raise RuntimeError('Unable to save FlightMap')

for asset_path in [path, map_path, ROOT + '/M_Ocean', ROOT + '/M_Gate', bp_path]:
    if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        raise RuntimeError('Missing generated asset: ' + asset_path)

unreal.log('AERONAUT_CONTENT_READY')
