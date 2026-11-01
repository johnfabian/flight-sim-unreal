"""Selective aircraft reimport, retaining the static scene and saved lighting."""
import json
from pathlib import Path
import unreal

root=Path(unreal.Paths.project_dir()).resolve()
record=next(a for a in json.loads((root/'Art/Exports/assets.json').read_text())['assets'] if a['name']=='Airframe')
before=unreal.ShowcaseEditor.mesh_dimensions(unreal.load_asset('/Game/Showcase/Meshes/Airframe'))
task=unreal.AssetImportTask(); task.filename=str(root/'Art/Exports/Airframe.fbx')
task.destination_path='/Game/Showcase/Meshes'; task.destination_name='Airframe'
task.automated=True; task.replace_existing=True; task.replace_existing_settings=True; task.save=True; task.factory=unreal.FbxFactory()
options=unreal.FbxImportUI(); options.import_mesh=True; options.import_materials=False; options.import_textures=False
options.automated_import_should_detect_type=False; options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
options.static_mesh_import_data.convert_scene=True; options.static_mesh_import_data.convert_scene_unit=True
options.static_mesh_import_data.remove_degenerates=False
options.static_mesh_import_data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
options.static_mesh_import_data.generate_lightmap_u_vs=True
task.options=options; unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
asset=unreal.load_asset('/Game/Showcase/Meshes/Airframe')
unreal.ShowcaseEditor.configure_mesh(asset,False,False)
asset.set_editor_property('never_stream',True)
for index,name in enumerate(record['materials']): asset.set_material(index,unreal.load_asset('/Game/Showcase/Materials/M_'+name))
after=unreal.ShowcaseEditor.mesh_dimensions(asset)
assert max(abs(after.x-before.x),abs(after.y-before.y),abs(after.z-before.z))<1, str((before,after))
assert unreal.EditorAssetLibrary.save_loaded_asset(asset)
# The baked tangent-space map follows this export's freshly packed UVs.
normal_task=unreal.AssetImportTask(); normal_task.filename=str(root/'Art/Textures/Original/aircraft_surface_normal.png')
normal_task.destination_path='/Game/Showcase/Textures'; normal_task.destination_name='AircraftNormal'
normal_task.automated=True; normal_task.replace_existing=True; normal_task.save=True
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([normal_task])
normal=unreal.load_asset('/Game/Showcase/Textures/AircraftNormal')
normal.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP)
normal.set_editor_property('srgb',False); normal.set_editor_property('flip_green_channel',True)
normal.set_editor_property('max_texture_size',2048)
assert unreal.EditorAssetLibrary.save_loaded_asset(normal)
unreal.log('AERONAUT_AIRCRAFT_REIMPORT_PASS '+str(after))
