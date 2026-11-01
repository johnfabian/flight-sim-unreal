"""Explicitly update four saved surface materials; never open/save the level.

Run through Showcase.ps1 -Action Surfaces. Ordinary Play does not run this.
The prior indirect-lighting solution is retained, not rebaked.
"""
import json
import sys
from pathlib import Path
import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
sys.path.insert(0, str(ROOT/'Scripts'))
from showcase_material_api import checked, material_api
from showcase_land import build_landscape, build_rock, build_foliage
from showcase_water import build_water

DEST = '/Game/Showcase'
edit = unreal.MaterialEditingLibrary
textures = {}
for prefix in ('Forest', 'Rock', 'Twig'):
    for suffix in ('Base', 'Normal', 'ARM'):
        key = prefix+suffix
        textures[key] = checked(unreal.load_asset(DEST+'/Textures/'+key), 'Missing prepared texture '+key)
textures['ShoreMask'] = checked(unreal.load_asset(DEST+'/Textures/ShoreMask'), 'Missing prepared ShoreMask')
api = material_api(textures)
builders = dict(Landscape=build_landscape, Rock=build_rock, Foliage=build_foliage, Water=build_water)
selected = {arg.split('=', 1)[1] for arg in unreal.SystemLibrary.get_command_line().split()
            if arg.startswith('-ShowcaseSurface=')}
checked(not (selected-set(builders)), 'Unknown surface selection: '+str(selected-set(builders)))
if selected:
    builders = {name: builder for name, builder in builders.items() if name in selected}
materials = {name: checked(unreal.load_asset(DEST+'/Materials/M_'+name), 'Missing material '+name)
             for name in builders}
report = {'lighting': 'Prior baked indirect lighting retained; no rebake', 'materials': {}}
for name, builder in builders.items():
    mat = materials[name]
    # Bulk deletion in this installed engine mutates its own iteration array.
    for expression in list(edit.get_material_expressions(mat)):
        edit.delete_material_expression(mat, expression)
    checked(not edit.get_material_expressions(mat), 'Graph did not clear '+name)
    builder(api, mat)
    if name in ('Rock', 'Foliage'):
        mat.set_editor_property('used_with_instanced_static_meshes', True)
    if name != 'Water':
        mat.set_editor_property('used_with_static_lighting', True)
    for output in ('MP_BASE_COLOR', 'MP_NORMAL', 'MP_ROUGHNESS'):
        checked(edit.get_material_property_input_node(mat, getattr(unreal.MaterialProperty, output)),
                name+' missing '+output)
    if name == 'Water':
        outputs = [e for e in edit.get_material_expressions(mat)
                   if isinstance(e, unreal.MaterialExpressionSingleLayerWaterMaterialOutput)]
        checked(len(outputs) == 1, 'Water must have exactly one SLW output')
    errors = list(edit.recompile_material(mat))
    checked(not errors, name+' shader errors: '+str(errors))
    report['materials'][name] = {
        'path': mat.get_path_name(), 'expressions': len(edit.get_material_expressions(mat)),
        'shading_model': str(mat.get_editor_property('shading_model')),
        'compile_errors': errors,
    }
# Save only after every graph has passed connection and compilation checks.
for name, mat in materials.items():
    checked(unreal.EditorAssetLibrary.save_loaded_asset(mat), 'Material save failed '+name)
folder = ROOT/'artifacts/coastal-surfaces'
folder.mkdir(parents=True, exist_ok=True)
(folder/'material-update.json').write_text(json.dumps(report, indent=2))
unreal.log('AERONAUT_COASTAL_SURFACES_READY')
