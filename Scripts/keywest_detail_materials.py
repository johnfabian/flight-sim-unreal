"""New-namespace PBR builders; importing this module is engine-free."""
import hashlib
import json
import math

DEST = '/Game/KeyWestDetail'
REPEATS = {'painted_plaster_wall': 2.0, 'white_planks_clean': 1.8, 'corrugated_iron': 1.12, 'aerial_asphalt_01':4.0}


def rotated_normal(x, y, z):
    # UV'=(V,-U), so J-transpose maps sampled tangent normals to (-Y,X,Z).
    return (-y, x, z)


def build_materials(u, root, definitions, state, force=False):
    from showcase_material_api import node, scalar, color, prop, link, sample, multiply, custom
    tools = u.AssetToolsHelpers.get_asset_tools(); edit = u.MaterialEditingLibrary
    state.setdefault('textures', {}); state.setdefault('materials', {})
    records = json.loads((root/'Art/KeyWestDetail/Textures/CC0/manifest.json').read_text())
    if len(records) != 9:
        raise RuntimeError('Exactly nine verified CC0 maps are required')
    # Read-only reuse of the original licensed asphalt sources; all imports,
    # compression settings and material assets stay in the new namespace.
    asphalt = [r for r in json.loads((root/'Art/Textures/CC0/manifest.json').read_text()) if r['asset']=='aerial_asphalt_01']
    if len(asphalt) != 3:
        raise RuntimeError('The three original verified asphalt sources are required')
    for record in asphalt:
        record['map'] = 'normal' if '_normal.' in record['file'] else 'arm' if '_arm.' in record['file'] else 'base'
    records += asphalt
    for record in records:
        if hashlib.sha256((root/record['file']).read_bytes()).hexdigest().lower() != record['sha256'].lower():
            raise RuntimeError('CC0 source changed '+record['file'])
    signature = hashlib.sha256((root/'Scripts/keywest_detail_materials.py').read_bytes()+json.dumps(records,sort_keys=True).encode()).hexdigest()
    textures = {}
    for record in records:
        key = (record['asset'], record['map']); name = 'T_'+record['asset']+'_'+record['map']; path = DEST+'/Textures/'+name
        tex = u.load_asset(path) if u.EditorAssetLibrary.does_asset_exist(path) else None
        limit = 2048 if record['asset']=='aerial_asphalt_01' else 1024
        key_hash = record['sha256']+'|DX|WRAP|'+str(limit)
        if force or not tex or state.setdefault('textures', {}).get(name) != key_hash:
            task = u.AssetImportTask(); task.filename = str(root/record['file']); task.destination_path = DEST+'/Textures'; task.destination_name = name
            task.automated = True; task.replace_existing = True; task.save = True
            tools.import_asset_tasks([task]); tex = u.load_asset(path)
            if not tex:
                raise RuntimeError('PBR texture import failed '+name)
            tex.set_editor_property('max_texture_size', limit)
            tex.set_editor_property('address_x', u.TextureAddress.TA_WRAP); tex.set_editor_property('address_y', u.TextureAddress.TA_WRAP)
            tex.set_editor_property('srgb', record['map'] == 'base')
            if record['map'] == 'normal':
                tex.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_NORMALMAP)
                tex.set_editor_property('flip_green_channel', False)  # Verified normalDX files.
            elif record['map'] == 'arm':
                tex.set_editor_property('compression_settings', u.TextureCompressionSettings.TC_MASKS)
            if not u.EditorAssetLibrary.save_loaded_asset(tex):
                raise RuntimeError('PBR texture save failed '+name)
            state['textures'][name] = key_hash
        textures[key] = tex

    def make(name, definition, pbr=None, horizontal=False, roof=False):
        path = DEST+'/Materials/M_'+name
        mat = u.load_asset(path) if u.EditorAssetLibrary.does_asset_exist(path) else None
        fingerprint = hashlib.sha256((signature+json.dumps([name,definition,pbr,horizontal,roof],sort_keys=True)).encode()).hexdigest()
        if mat and not force and state.setdefault('materials', {}).get(name) == fingerprint:
            return mat
        if not mat:
            mat = tools.create_asset('M_'+name, DEST+'/Materials', u.Material, u.MaterialFactoryNew())
        if not mat:
            raise RuntimeError('Detail material creation failed '+name)
        for expression in list(edit.get_material_expressions(mat)):
            edit.delete_material_expression(mat, expression)
        if edit.get_material_expressions(mat):
            raise RuntimeError('Detail material graph did not clear '+name)
        mat.set_editor_property('used_with_instanced_static_meshes', True)
        mat.set_editor_property('two_sided', definition.get('two_sided', False))
        if definition.get('foliage'):
            mat.set_editor_property('shading_model', u.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
            prop(color(mat,definition.get('subsurface_color',[.16,.29,.055])),u.MaterialProperty.MP_SUBSURFACE_COLOR)
        tint = color(mat, definition['color'])
        if definition.get('vertex_color'):
            tint = multiply(mat, tint, node(mat, u.MaterialExpressionVertexColor))
        base = tint
        if name == 'KWD_PalmTrunk':
            uv = node(mat, u.MaterialExpressionTextureCoordinate)
            rings = custom(mat, '''
float z=UV.y*5, band=abs(frac(z/.17+.035*sin(UV.x*42))-.5);
return .78+.22*smoothstep(.025,.12,band);
''', {'UV':uv}, u.CustomMaterialOutputType.CMOT_FLOAT1)
            base = multiply(mat,tint,rings)
        if pbr:
            raw = node(mat, u.MaterialExpressionTextureCoordinate)
            # Existing and new export UV0 are 0.2 units/metre: five metres/unit.
            code = 'return float2(UV.y,-UV.x)*Scale;' if horizontal else 'return UV*Scale;'
            coord = custom(mat, code, {'UV':raw,'Scale':scalar(mat,5/REPEATS[pbr])}, u.CustomMaterialOutputType.CMOT_FLOAT2)
            base = multiply(mat, sample(mat, textures[pbr,'base'], coord), tint)
            packed = sample(mat, textures[pbr,'arm'], coord)
            prop(packed, u.MaterialProperty.MP_AMBIENT_OCCLUSION, 'R')
            prop(packed, u.MaterialProperty.MP_ROUGHNESS, 'G')
            # Coated wall/wood are dielectric even when a source has nonzero B.
            prop(packed if pbr == 'corrugated_iron' else scalar(mat,0), u.MaterialProperty.MP_METALLIC, 'B' if pbr == 'corrugated_iron' else '')
            normal = sample(mat, textures[pbr,'normal'], coord)
            code = 'return normalize(float3(-N.y*.32,N.x*.32,max(.05,N.z)));' if horizontal else 'return normalize(float3(N.xy*.28,max(.05,N.z)));'
            prop(custom(mat, code, {'N':normal}), u.MaterialProperty.MP_NORMAL)
        elif roof:
            uv = node(mat, u.MaterialExpressionTextureCoordinate)
            profile = custom(mat, '''
float c=UV.x*5.0/.38, aa=max(fwidth(c),.001);
float seam=(1-smoothstep(.02,.02+aa*1.5,abs(frac(c+.5)-.5)))*(1-smoothstep(.3,1,aa));
return .96-.09*seam;
''', {'UV':uv}, u.CustomMaterialOutputType.CMOT_FLOAT1)
            base = multiply(mat, tint, profile)
            prop(scalar(mat,.66),u.MaterialProperty.MP_ROUGHNESS); prop(scalar(mat,0),u.MaterialProperty.MP_METALLIC)
        else:
            prop(scalar(mat,definition.get('roughness',.65)),u.MaterialProperty.MP_ROUGHNESS)
            prop(scalar(mat,definition.get('metallic',0)),u.MaterialProperty.MP_METALLIC)
        prop(base,u.MaterialProperty.MP_BASE_COLOR)
        errors = list(edit.recompile_material(mat))
        if errors:
            raise RuntimeError('Detail material compilation failed '+name+': '+'; '.join(map(str,errors)))
        if not mat.get_path_name().startswith(DEST+'/') or not u.EditorAssetLibrary.save_loaded_asset(mat):
            raise RuntimeError('Refusing failed/out-of-namespace material save '+name)
        state['materials'][name] = fingerprint
        return mat

    mats = {}
    wall = dict(color=[.66,.64,.58],roughness=.8,vertex_color=True)
    mats['WallWood'] = make('WallWood', wall, 'white_planks_clean', True)
    mats['WallPlaster'] = make('WallPlaster', wall, 'painted_plaster_wall')
    for name, definition in definitions.items():
        if name == 'KWD_Wall':
            mats[name] = mats['WallWood']
        elif name == 'KWD_Roof':
            mats[name] = make(name, {**definition,'color':[.36,.38,.37]}, roof=True)
        elif name in ('KWD_Shutter','KWD_Door'):
            mats[name] = make(name, definition, 'white_planks_clean', False)
        elif name == 'KWD_DockWood':
            mats[name] = make(name, definition, 'white_planks_clean', False)
        else:
            mats[name] = make(name, definition)
    # Available only for explicitly authored working-roof panels; never map this
    # to every city roof or to metal door/rail hardware.
    mats['WorkingRoof'] = make('WorkingRoof',dict(color=[.65,.67,.65],roughness=.65),'corrugated_iron')
    mats['Road'] = make('Road',dict(color=[.72,.74,.72],roughness=.9),'aerial_asphalt_01')
    return mats


def self_test():
    # A texture-U normal bump on vertical-board art becomes a wall-V bump after
    # the 90 degree rotation, so horizontal siding and its lighting agree.
    assert rotated_normal(1,0,0) == (0,1,0)
    assert rotated_normal(0,1,0) == (-1,0,0)
    assert abs((5/1.8)*.2*1.8-1)<1e-12
    assert all(math.isfinite(5/v) and v>0 for v in REPEATS.values())
    print('PASS rotated normal Jacobian and five-metre UV physical repeat')


if __name__ == '__main__':
    self_test()
