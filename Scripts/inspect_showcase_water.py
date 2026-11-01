import json
from pathlib import Path
import unreal
mat=unreal.load_asset('/Game/Showcase/Materials/M_Water')
edit=unreal.MaterialEditingLibrary
report={p:str(mat.get_editor_property(p)) for p in ('shading_model','blend_mode','tangent_space_normal')}
report['outputs']={name:str(edit.get_material_property_input_node(mat,getattr(unreal.MaterialProperty,name))) for name in ('MP_NORMAL','MP_OPACITY','MP_ROUGHNESS','MP_BASE_COLOR','MP_EMISSIVE_COLOR')}
report['nodes']=[]
for expression in edit.get_material_expressions(mat):
    entry={'name':expression.get_name(),'class':expression.get_class().get_name(),'inputs':[str(i) for i in edit.get_inputs_for_material_expression(mat,expression)]}
    for field in ('r','constant','code','output_type','texture'):
        try: entry[field]=str(expression.get_editor_property(field))
        except Exception: pass
    report['nodes'].append(entry)
(Path(unreal.Paths.project_dir())/'artifacts/water-material-graph.json').write_text(json.dumps(report,indent=2))
unreal.log('AERONAUT_WATER_GRAPH_INSPECTED')
