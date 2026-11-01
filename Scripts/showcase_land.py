"""Explicit coastal material builders; no scene, geometry or external-file writes.

Called by the integration-owned generator with its existing helper API. World
coordinates are centimetres. Reuses the verified Forest/Rock/Twig CC0 textures;
all additional variation is original deterministic shader math. Existing baked
irradiance is retained, so colors stay near the previous material's reflectance.
"""


def _noise(name, position, seed):
    """Smooth value noise without texture assets, discontinuous hashes or bands."""
    return f"""
float2 {name}q={position};
float2 {name}i=floor({name}q),{name}f=frac({name}q);
{name}f={name}f*{name}f*(3-2*{name}f);
float4 {name}h=frac(sin(float4(
 dot({name}i,float2(127.1,311.7)),
 dot({name}i+float2(1,0),float2(127.1,311.7)),
 dot({name}i+float2(0,1),float2(127.1,311.7)),
 dot({name}i+float2(1,1),float2(127.1,311.7)))+{seed})*43758.5453);
float {name}=lerp(lerp({name}h.x,{name}h.y,{name}f.x),
                 lerp({name}h.z,{name}h.w,{name}f.x),{name}f.y);
"""


def _context(api, m):
    u = api['unreal']
    p = api['node'](m, u.MaterialExpressionWorldPosition)
    n = api['node'](m, u.MaterialExpressionVertexNormalWS)
    depth = api['node'](m, u.MaterialExpressionPixelDepth)
    code = _noise('large', 'P.xy/18000', '1.73')
    code += _noise('patch', 'P.xy/3500+float2(large*1.7,-large)', '4.19')
    code += _noise('small', 'P.xy/650+float2(patch,-patch)*.6', '8.31')
    code += 'return float3(large,patch,small);'
    fields = api['custom'](m, code, {'P': p})
    return u, p, n, depth, fields


def _uv(api, m, p, scale, rotated=False):
    expr = ('float2(P.x*.83867-P.y*.54464,P.x*.54464+P.y*.83867)'
            if rotated else 'P.xy')
    return api['custom'](m, f'return {expr}*{scale}+float2(.37,.71);',
                         {'P': p}, api['unreal'].CustomMaterialOutputType.CMOT_FLOAT2)


def _out(api, m, name, node, pin=''):
    api['prop'](node, getattr(api['unreal'].MaterialProperty, 'MP_'+name), pin)


def _triplanar_rock(api, m, p, n):
    """Seamless metre-scale rock color/ARM and correctly oriented world normals."""
    u = api['unreal']
    samples = {}
    for axis, expr in [('X', 'float2(P.y*(N.x<0?-1:1),P.z)'),
                       ('Y', 'float2(P.x*(N.y<0?1:-1),P.z)'),
                       ('Z', 'float2(P.x*(N.z<0?-1:1),P.y)')]:
        uv = api['custom'](m, 'return '+expr+'/320;', {'P': p, 'N': n},
                           u.CustomMaterialOutputType.CMOT_FLOAT2)
        for suffix in ('Base', 'ARM', 'Normal'):
            samples[axis+suffix] = api['sample'](m, api['tex']['Rock'+suffix], uv)
    result = {}
    for suffix in ('Base', 'ARM'):
        result[suffix] = api['custom'](m, """
float3 w=pow(abs(N),4); w/=max(dot(w,float3(1,1,1)),.0001);
return X.rgb*w.x+Y.rgb*w.y+Z.rgb*w.z;
""", {'N': n, 'X': samples['X'+suffix], 'Y': samples['Y'+suffix],
       'Z': samples['Z'+suffix]})
    result['Normal'] = api['custom'](m, """
float3 w=pow(abs(N),4); w/=max(dot(w,float3(1,1,1)),.0001);
float3 d=float3(0,X.x*(N.x<0?-1:1),X.y)*w.x
        +float3(Y.x*(N.y<0?1:-1),0,Y.y)*w.y
        +float3(Z.x*(N.z<0?-1:1),Z.y,0)*w.z;
d-=N*dot(N,d);
return normalize(N+d*.42);
""", {'N': n, 'X': samples['XNormal'], 'Y': samples['YNormal'],
       'Z': samples['ZNormal']})
    return result


def build_landscape(api, m):
    """Meadow/duff/stone mosaic, weathered slopes and irregular wet coast."""
    u, p, n, depth, fields = _context(api, m)
    m.set_editor_property('tangent_space_normal', False)
    near = _uv(api, m, p, .0015)
    broad = _uv(api, m, p, .00037, True)
    forest = api['mix'](m, api['sample'](m, api['tex']['ForestBase'], near),
                        api['sample'](m, api['tex']['ForestBase'], broad),
                        api['scalar'](m, .42))
    packed = api['sample'](m, api['tex']['ForestARM'], near)
    rock = _triplanar_rock(api, m, p, n)
    masks = api['custom'](m, """
float steep=1-saturate(N.z);
float outcrop=smoothstep(.10,.46,steep+(F.g-.5)*.12);
outcrop=max(outcrop,smoothstep(27000,39000,P.z)*.58);
float coast=1-smoothstep(250,1250+F.r*500,P.z);
outcrop=max(outcrop,coast*.87);
float wet=1-smoothstep(60+F.b*70,320+F.g*180,P.z);
float meadow=smoothstep(.32,.70,F.r*.6+F.g*.4)*(1-outcrop);
return float3(outcrop,wet,meadow);
""", {'P': p, 'N': n, 'F': fields})
    base = api['custom'](m, """
float l=dot(Forest.rgb,float3(.2126,.7152,.0722));
// Duff retains the source's leaf/soil detail; meadow suppresses autumn orange.
float3 duff=lerp(Forest.rgb,l.xxx,.30)*float3(.48,.59,.37);
float3 meadow=l*float3(.40,.65,.31);
float3 soil=lerp(duff,meadow,M.b);
soil*=lerp(.84,1.12,F.g)*lerp(.94,1.04,F.b);
float3 stone=Rock.rgb*float3(.86,.92,.87);
float3 result=lerp(soil,stone,M.r);
return result*lerp(1,.64,M.g);
""", {'Forest': forest, 'Rock': rock['Base'], 'M': masks, 'F': fields})
    _out(api, m, 'BASE_COLOR', base)
    rough = api['custom'](m, """
float dry=lerp(clamp(Ground.g,.70,.98),clamp(Rock.g,.64,.95),M.r);
return lerp(dry,lerp(.30,.46,F.b),M.g*.88);
""", {'Ground': packed, 'Rock': rock['ARM'], 'M': masks, 'F': fields},
                           u.CustomMaterialOutputType.CMOT_FLOAT1)
    _out(api, m, 'ROUGHNESS', rough)
    _out(api, m, 'AMBIENT_OCCLUSION', api['custom'](m,
         'return lerp(1,lerp(Ground.r,Rock.r,M.r),.45);',
         {'Ground': packed, 'Rock': rock['ARM'], 'M': masks},
         u.CustomMaterialOutputType.CMOT_FLOAT1))
    detail = api['sample'](m, api['tex']['ForestNormal'], near)
    fine = api['sample'](m, api['tex']['ForestNormal'], _uv(api, m, p, .0091, True))
    world_normal = api['custom'](m, """
float3 reference=abs(N.z)>.15?float3(0,1,0):float3(0,0,1);
float3 t=normalize(cross(reference,N));
float3 b=normalize(cross(N,t));
float fade=1-smoothstep(6500,36000,Depth);
float micro=1-smoothstep(1800,10500,Depth);
float2 d=D.xy*lerp(.065,.30,fade)+Fine.xy*.12*micro;
float3 ground=normalize(N+(t*d.x+b*d.y));
return normalize(lerp(ground,Rock,M.r));
""", {'N': n, 'D': detail, 'Fine': fine, 'Depth': depth,
       'Rock': rock['Normal'], 'M': masks})
    _out(api, m, 'NORMAL', world_normal)


def build_rock(api, m):
    """World-projected stone, restrained lichen and tide-darkened lower faces."""
    u, p, n, depth, fields = _context(api, m)
    m.set_editor_property('tangent_space_normal', False)
    rock = _triplanar_rock(api, m, p, n)
    wet = api['custom'](m, """
return 1-smoothstep(65+F.b*70,310+F.g*170,P.z);
""", {'P': p, 'F': fields}, u.CustomMaterialOutputType.CMOT_FLOAT1)
    base = api['custom'](m, """
float l=dot(Rock.rgb,float3(.2126,.7152,.0722));
float moss=smoothstep(.52,.80,F.g)*(1-smoothstep(.2,.85,1-N.z))*.33;
float3 stone=Rock.rgb*float3(.90,.96,.92)*lerp(.86,1.10,F.r);
stone=lerp(stone,l*float3(.48,.66,.34),moss);
return stone*lerp(1,.61,Wet);
""", {'Rock': rock['Base'], 'N': n, 'F': fields, 'Wet': wet})
    _out(api, m, 'BASE_COLOR', base)
    _out(api, m, 'ROUGHNESS', api['custom'](m,
         'return lerp(clamp(ARM.g*lerp(.93,1.06,F.b),.61,.96),.31,Wet*.88);',
         {'ARM': rock['ARM'], 'F': fields, 'Wet': wet},
         u.CustomMaterialOutputType.CMOT_FLOAT1))
    _out(api, m, 'AMBIENT_OCCLUSION', api['custom'](m,
         'return lerp(1,ARM.r,.52);', {'ARM': rock['ARM']},
         u.CustomMaterialOutputType.CMOT_FLOAT1))
    _out(api, m, 'NORMAL', api['custom'](m,
         'return normalize(lerp(N,Detail,lerp(.3,1,1-smoothstep(9000,42000,Depth))));',
         {'N': n, 'Detail': rock['Normal'], 'Depth': depth}))


def build_foliage(api, m):
    """Preserve branch alpha/lighting/wind, add coherent per-tree green variety."""
    u = api['unreal']
    m.set_editor_property('two_sided', True)
    m.set_editor_property('blend_mode', u.BlendMode.BLEND_MASKED)
    m.set_editor_property('shading_model', u.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    m.set_editor_property('opacity_mask_clip_value', .3)
    m.set_editor_property('tangent_space_normal', True)
    m.set_editor_property('used_with_instanced_static_meshes', True)
    twig = api['sample'](m, api['tex']['TwigBase'])
    random = api['node'](m, u.MaterialExpressionPerInstanceRandom)
    center = api['node'](m, u.MaterialExpressionObjectPositionWS)
    variation = api['custom'](m, """
float region=.5+.5*sin(Center.x*.00023+sin(Center.y*.00017));
float factor=lerp(.87,1.09,Random*.72+region*.28);
return Color.rgb*lerp(float3(.91,1.0,.86),float3(1.02,.97,.91),Random)*factor;
""", {'Color': twig, 'Random': random, 'Center': center})
    _out(api, m, 'BASE_COLOR', variation)
    _out(api, m, 'OPACITY_MASK', twig, 'A')
    _out(api, m, 'NORMAL', api['sample'](m, api['tex']['TwigNormal']), 'RGB')
    arm = api['sample'](m, api['tex']['TwigARM'])
    for prop, channel in [('AMBIENT_OCCLUSION', 'R'), ('ROUGHNESS', 'G'), ('METALLIC', 'B')]:
        _out(api, m, prop, arm, channel)
    _out(api, m, 'SUBSURFACE_COLOR', api['color'](m, (.06, .11, .025)))
    p = api['node'](m, u.MaterialExpressionWorldPosition)
    time = api['node'](m, u.MaterialExpressionTime)
    # Intentionally identical to the established canopy wind.
    wind = api['custom'](m, 'float w=saturate((P.z-Center.z+500)/1600); return float3(sin(Time*1.15+P.x*.00011)*7*w,cos(Time*.85+P.y*.00013)*5*w,0);',
                         {'P': p, 'Center': center, 'Time': time})
    _out(api, m, 'WORLD_POSITION_OFFSET', wind)
