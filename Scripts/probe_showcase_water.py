"""Temporary minimal water isolation; restore M_Water after diagnosis."""
import unreal
edit=unreal.MaterialEditingLibrary
path='/Game/ImportProbe/M_WaterDebug'
if unreal.EditorAssetLibrary.does_asset_exist(path): mat=unreal.load_asset(path)
else: mat=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_WaterDebug','/Game/ImportProbe',unreal.Material,unreal.MaterialFactoryNew())
edit.delete_all_material_expressions(mat)
mat.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
mat.set_editor_property('blend_mode',unreal.BlendMode.BLEND_OPAQUE)
mat.set_editor_property('tangent_space_normal',True)
def value(rgb):
    n=edit.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector)
    n.set_editor_property('constant',unreal.LinearColor(*rgb,1)); return n
def scalar(v):
    n=edit.create_material_expression(mat,unreal.MaterialExpressionConstant); n.set_editor_property('r',v); return n
for name,node in [('MP_BASE_COLOR',value((.02,.06,.08))),('MP_ROUGHNESS',scalar(.3)),('MP_OPACITY',scalar(.1)),('MP_NORMAL',value((0,0,1)))]:
    assert edit.connect_material_property(node,'',getattr(unreal.MaterialProperty,name))
output=edit.create_material_expression(mat,unreal.MaterialExpressionSingleLayerWaterMaterialOutput)
for pin,node in [('ScatteringCoefficients',value((.0005,.001,.002))),('AbsorptionCoefficients',value((.001,.001,.001))),('PhaseG',scalar(0)),('ColorScaleBehindWater',value((1,1,1)))]:
    actual=next(p for p in edit.get_material_expression_input_names(output) if str(p).replace(' ','')==pin)
    assert edit.connect_material_expressions(node,'',output,actual)
edit.recompile_material(mat); unreal.EditorAssetLibrary.save_loaded_asset(mat)
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem); assert levels.load_level('/Game/Showcase/CoastalShowcase')
ocean=next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors() if a.get_actor_label()=='Pacific coastal ocean')
ocean.static_mesh_component.set_material(0,mat)
assert levels.save_current_level()
unreal.log('AERONAUT_WATER_PROBE_READY')
