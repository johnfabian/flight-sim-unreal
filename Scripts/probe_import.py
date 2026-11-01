import unreal
from pathlib import Path
root=Path(unreal.Paths.project_dir()).resolve()
tools=unreal.AssetToolsHelpers.get_asset_tools()
for name in ['PipelineTest','Airframe','WingLeft','NeedleAirspeed']:
    task=unreal.AssetImportTask();task.filename=str(root/'Art/Exports'/f'{name}.fbx');task.destination_path='/Game/Showcase/ImportProbe';task.destination_name=name
    task.automated=True;task.replace_existing=True;task.replace_existing_settings=True;task.save=True;task.factory=unreal.FbxFactory()
    options=unreal.FbxImportUI();options.import_mesh=True;options.import_materials=False;options.import_textures=False
    options.automated_import_should_detect_type=False;options.mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH
    options.static_mesh_import_data.convert_scene_unit=True;options.static_mesh_import_data.convert_scene=True
    options.static_mesh_import_data.import_uniform_scale=1.0;options.static_mesh_import_data.remove_degenerates=False
    task.options=options;tools.import_asset_tasks([task])
    mesh=unreal.load_asset('/Game/Showcase/ImportProbe/'+name)
    unreal.log('PROBE '+name+' '+str(unreal.ShowcaseEditor.mesh_dimensions(mesh)))
    unreal.log('PROBE_IMPORT_DATA '+str(mesh.get_editor_property('asset_import_data').get_editor_property('convert_scene_unit')))
