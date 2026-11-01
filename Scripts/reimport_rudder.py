"""Reimport the repaired movable control surface without touching static scenery."""
import unreal
from pathlib import Path
root=Path(unreal.Paths.project_dir()).resolve()
task=unreal.AssetImportTask(); task.filename=str(root/'Art/Exports/Rudder.fbx')
task.destination_path='/Game/Showcase/Meshes'; task.destination_name='Rudder'
task.automated=True; task.replace_existing=True; task.replace_existing_settings=True; task.save=True; task.factory=unreal.FbxFactory()
options=unreal.FbxImportUI(); options.import_mesh=True; options.import_materials=False; options.import_textures=False
options.automated_import_should_detect_type=False; options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
options.static_mesh_import_data.convert_scene=True; options.static_mesh_import_data.convert_scene_unit=True
options.static_mesh_import_data.remove_degenerates=False
options.static_mesh_import_data.normal_import_method=unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
options.static_mesh_import_data.generate_lightmap_u_vs=True
task.options=options; unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
mesh=unreal.load_asset('/Game/Showcase/Meshes/Rudder')
unreal.ShowcaseEditor.configure_mesh(mesh,False,False)
mesh.set_material(0,unreal.load_asset('/Game/Showcase/Materials/M_Orange'))
dimensions=unreal.ShowcaseEditor.mesh_dimensions(mesh)
if abs(dimensions.z-123)>1: raise RuntimeError('Rudder reimport changed scale: '+str(dimensions))
unreal.EditorAssetLibrary.save_loaded_asset(mesh)
unreal.log('AERONAUT_RUDDER_REIMPORT_PASS '+str(dimensions))
