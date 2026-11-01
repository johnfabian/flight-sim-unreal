"""Shared checked material-graph helpers for full and targeted authoring.

Importing this module does not create, clear or save any Unreal asset.
"""
import unreal

edit = unreal.MaterialEditingLibrary


def checked(value, message):
    if not value:
        raise RuntimeError(message)
    return value


def node(mat, kind):
    return checked(edit.create_material_expression(mat, kind), 'Expression creation failed '+str(kind))


def scalar(mat, value):
    n = node(mat, unreal.MaterialExpressionConstant)
    n.set_editor_property('r', value)
    return n


def color(mat, values):
    n = node(mat, unreal.MaterialExpressionConstant3Vector)
    n.set_editor_property('constant', unreal.LinearColor(*values, 1))
    return n


def prop(n, target, pin=''):
    checked(edit.connect_material_property(n, pin, target), 'Material output rejected '+str(target))


def link(a, b, input_name, pin=''):
    names = edit.get_material_expression_input_names(b)
    normalized = lambda s: str(s).replace(' ', '').replace('_', '').lower()
    match = next((name for name in names if normalized(name) == normalized(input_name)), input_name)
    checked(edit.connect_material_expressions(a, pin, b, match),
            'Material expression input rejected '+input_name+' available='+str(names))


def sample(mat, texture, uv=None):
    n = node(mat, unreal.MaterialExpressionTextureSample)
    n.set_editor_property('texture', texture)
    if texture.get_editor_property('compression_settings') == unreal.TextureCompressionSettings.TC_NORMALMAP:
        n.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    elif not texture.get_editor_property('srgb'):
        n.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    if uv:
        link(uv, n, 'UVs')
    return n


def multiply(mat, a, b):
    n = node(mat, unreal.MaterialExpressionMultiply)
    link(a, n, 'A'); link(b, n, 'B')
    return n


def mix(mat, a, b, alpha, pin=''):
    n = node(mat, unreal.MaterialExpressionLinearInterpolate)
    link(a, n, 'A'); link(b, n, 'B')
    if pin:
        mask = node(mat, unreal.MaterialExpressionComponentMask)
        for component in 'rgba':
            mask.set_editor_property(component, component.upper() in pin)
        link(alpha, mask, '')
        alpha = mask
    link(alpha, n, 'Alpha')
    return n


def custom(mat, code, inputs, output=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
    n = node(mat, unreal.MaterialExpressionCustom)
    n.set_editor_property('code', code)
    n.set_editor_property('output_type', output)
    values = []
    for name in inputs:
        item = unreal.CustomInput()
        item.set_editor_property('input_name', name)
        values.append(item)
    n.set_editor_property('inputs', values)
    for name, source in inputs.items():
        link(source, n, name)
    return n


def world_uv(mat, scale):
    p = node(mat, unreal.MaterialExpressionWorldPosition)
    return custom(mat, f'return World.xy*{scale};', {'World': p},
                  unreal.CustomMaterialOutputType.CMOT_FLOAT2)


def material_api(textures):
    return dict(unreal=unreal, node=node, scalar=scalar, color=color, prop=prop,
                link=link, sample=sample, multiply=multiply, mix=mix,
                custom=custom, world_uv=world_uv, tex=textures)
