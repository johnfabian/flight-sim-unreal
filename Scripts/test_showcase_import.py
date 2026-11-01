"""Real Unreal reimport check for the prepared one-metre pipeline asset."""
import unreal
from pathlib import Path
root=Path(unreal.Paths.project_dir()).resolve()
path='/Game/Showcase/ImportProbe/PipelineTest'
mesh=unreal.load_asset(path)
before=unreal.ShowcaseEditor.mesh_dimensions(mesh)
task=unreal.AssetImportTask()
task.filename=str(root/'Art/Exports/PipelineTest.fbx'); task.destination_path='/Game/Showcase/ImportProbe'; task.destination_name='PipelineTest'
task.automated=True; task.replace_existing=True; task.replace_existing_settings=True; task.save=True; task.factory=unreal.FbxFactory()
options=unreal.FbxImportUI(); options.import_mesh=True; options.import_materials=False; options.import_textures=False
options.automated_import_should_detect_type=False; options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
options.static_mesh_import_data.convert_scene_unit=True; options.static_mesh_import_data.convert_scene=True
options.static_mesh_import_data.generate_lightmap_u_vs=True
task.options=options
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
mesh=unreal.load_asset(path)
after=unreal.ShowcaseEditor.mesh_dimensions(mesh)
if max(abs(after.x-100),abs(after.y-100),abs(after.z-100))>1: raise RuntimeError('Reimport changed metre scale: '+str(after))
lightmap_uv=mesh.get_editor_property('light_map_coordinate_index')
if lightmap_uv!=1: raise RuntimeError('Reimport changed the assigned lightmap UV index')
unreal.log('AERONAUT_REIMPORT_PASS before='+str(before)+' after='+str(after)+' lightmap UV assignment='+str(lightmap_uv))
