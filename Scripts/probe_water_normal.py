import unreal
mat=unreal.load_asset('/Game/Showcase/Materials/M_Water')
edit=unreal.MaterialEditingLibrary
node=edit.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector)
node.set_editor_property('constant',unreal.LinearColor(0,0,1,1))
mat.set_editor_property('tangent_space_normal',True)
assert edit.connect_material_property(node,'',unreal.MaterialProperty.MP_NORMAL)
edit.recompile_material(mat)
assert unreal.EditorAssetLibrary.save_loaded_asset(mat)
unreal.log('AERONAUT_WATER_NORMAL_PROBE_READY')
