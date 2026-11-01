"""Pacific coastal water graph; called only by the targeted material generator.

Contract: build_water(api, material). Importing this module creates/saves nothing.
The integration owner clears, compiles and saves the material. No scene, sky,
geometry, rendering configuration or external texture is changed here.
"""
import math


# Wavelength metres, normalized wind direction, peak normal slope. Normal-only
# gravity waves suggest scale without moving the coarse ocean mesh or collision.
_WAVES = (
    (31.7, (0.92, 0.39), 0.024),
    (18.3, (0.68, 0.73), 0.020),
    (11.1, (0.99, -0.11), 0.018),
    (6.7, (0.79, 0.61), 0.016),
    (4.1, (0.38, 0.92), 0.012),
    (2.3, (0.97, 0.24), 0.010),
    (1.1, (0.76, -0.65), 0.007),
    (0.53, (0.53, 0.85), 0.004),
)

# Four hashes per cell, smooth interpolation; two shared uses in the graph.
# This coarse value noise avoids a texture dependency and large fractal stacks.
_VALUE_NOISE = """
float2 cell=floor(UV), f=frac(UV); f=f*f*(3.0-2.0*f);
float4 x=cell.x+float4(0,1,0,1);
float4 y=cell.y+float4(0,0,1,1);
float4 h=frac(sin(x*127.1+y*311.7)*43758.5453);
return lerp(lerp(h.x,h.y,f.x),lerp(h.z,h.w,f.x),f.y);
"""


def _normal_code():
    lines = [
        "float2 p=P.xy*0.01;",  # Unreal centimetres -> metres.
        "float distanceM=max(0.0,Depth*0.01);",
        "float warp=(Macro-0.5)*1.3; float2 slope=float2(0,0);",
    ]
    for i, (wavelength, direction, amplitude) in enumerate(_WAVES):
        length = math.hypot(*direction)
        x, y = (v / length for v in direction)
        k = 2.0 * math.pi / wavelength
        omega = math.sqrt(9.81 * k)
        fade = ("1.0" if i < 2 else
                "(1.0-smoothstep(250.0,1100.0,distanceM))" if i < 4 else
                "(1.0-smoothstep(70.0,350.0,distanceM))")
        lines += [
            f"float phase{i}=dot(p,float2({x:.8f},{y:.8f}))*{k:.8f}"
            f"-Time*{omega:.8f}+warp*{0.55 + i * .19:.5f}"
            f"+(Breakup-0.5)*{2.4 + i * .31:.5f}+{i * 4.13:.5f};",
            # Suppress subpixel wave sparkle before it becomes a moire band.
            f"float filter{i}=saturate(1.0-fwidth(phase{i})*0.55)*{fade};",
            f"slope+=float2({x:.8f},{y:.8f})*cos(phase{i})"
            f"*{amplitude:.8f}*filter{i};",
        ]
    lines += [
        "slope*=lerp(1.0,0.45,smoothstep(1800.0,6500.0,distanceM));",
        "return normalize(float3(-slope,1.0));",
    ]
    return "\n".join(lines)


def build_water(api, material):
    """Build one SLW output with the existing R-foam/G-depth shoreline texture."""
    required = ("unreal", "node", "scalar", "color", "prop", "link", "sample",
                "mix", "custom", "tex")
    missing = [name for name in required if name not in api]
    if missing:
        raise RuntimeError("Water helper API missing: " + ", ".join(missing))
    u = api["unreal"]
    node, scalar, color = (api[k] for k in ("node", "scalar", "color"))
    prop, link, sample = (api[k] for k in ("prop", "link", "sample"))
    mix, custom = api["mix"], api["custom"]
    m = material
    m.set_editor_property("shading_model", u.MaterialShadingModel.MSM_SINGLE_LAYER_WATER)
    m.set_editor_property("blend_mode", u.BlendMode.BLEND_OPAQUE)
    m.set_editor_property("tangent_space_normal", False)

    p = node(m, u.MaterialExpressionWorldPosition)
    time = node(m, u.MaterialExpressionTime)
    depth = node(m, u.MaterialExpressionPixelDepth)
    macro_uv = custom(m, "return P.xy*0.01/180.0;", {"P": p},
                      u.CustomMaterialOutputType.CMOT_FLOAT2)
    foam_uv = custom(m, "return P.xy*0.01/9.0+Time*float2(0.017,0.009);",
                     {"P": p, "Time": time}, u.CustomMaterialOutputType.CMOT_FLOAT2)
    lace_uv = custom(m, "return P.xy*0.01/1.6+Time*float2(0.045,-0.027);",
                     {"P": p, "Time": time}, u.CustomMaterialOutputType.CMOT_FLOAT2)
    macro = custom(m, _VALUE_NOISE, {"UV": macro_uv},
                   u.CustomMaterialOutputType.CMOT_FLOAT1)
    breakup = custom(m, _VALUE_NOISE, {"UV": foam_uv},
                     u.CustomMaterialOutputType.CMOT_FLOAT1)
    lace = custom(m, _VALUE_NOISE, {"UV": lace_uv},
                  u.CustomMaterialOutputType.CMOT_FLOAT1)
    coast_uv = custom(m, "return (P.xy+151200.0)/302400.0;", {"P": p},
                      u.CustomMaterialOutputType.CMOT_FLOAT2)
    coast = sample(m, api["tex"]["ShoreMask"], coast_uv)
    shallow = custom(m, "return 1.0-smoothstep(0.7,9.0,saturate(Coast.g)*30.0);",
                     {"Coast": coast}, u.CustomMaterialOutputType.CMOT_FLOAT1)
    foam = custom(m, """
// Existing mask: R is a soft nearshore envelope; G encodes depth / 30 metres.
// Do not rely on a sub-metre stripe in a mask sampled from a 3 m heightfield.
float d=saturate(Coast.g)*30.0;
float envelope=smoothstep(0.012,0.48,Coast.r)*(1.0-smoothstep(2.0,5.0,d));
float front=sin(d*2.1-Time*0.85+(Breakup-0.5)*3.4+(Macro-0.5)*1.1);
float crest=smoothstep(0.20,0.94,front);
float patches=smoothstep(0.24,0.77,Breakup);
float fragments=smoothstep(0.42,0.66,Lace);
return saturate(envelope*patches*crest*fragments*1.3);
""", {"Coast": coast, "Time": time, "Breakup": breakup, "Macro": macro, "Lace": lace},
                  u.CustomMaterialOutputType.CMOT_FLOAT1)
    normal = custom(m, _normal_code(),
                    {"P": p, "Time": time, "Depth": depth, "Macro": macro, "Breakup": breakup})

    # Restrained linear colors: dark Pacific blue-green, muddy-green shallows.
    water_color = custom(m, """
float3 deep=float3(0.012,0.039,0.052);
float3 shoal=float3(0.026,0.079,0.070);
float3 c=lerp(deep,shoal,Shallow)*(0.86+Macro*0.28);
float horizonBlend=smoothstep(180000.0,650000.0,Depth);
return lerp(c,float3(0.025,0.052,0.066),horizonBlend*0.30);
""", {"Shallow": shallow, "Macro": macro, "Depth": depth})
    roughness = custom(m, """
float farRoughness=smoothstep(50000.0,350000.0,Depth);
return clamp(0.29+(Macro-0.5)*0.045+farRoughness*0.075,0.25,0.40);
""", {"Macro": macro, "Depth": depth}, u.CustomMaterialOutputType.CMOT_FLOAT1)
    prop(normal, u.MaterialProperty.MP_NORMAL)
    prop(mix(m, water_color, color(m, (0.55, 0.60, 0.57)), foam),
         u.MaterialProperty.MP_BASE_COLOR)
    prop(mix(m, roughness, scalar(m, 0.72), foam), u.MaterialProperty.MP_ROUGHNESS)
    prop(scalar(m, 0.25), u.MaterialProperty.MP_SPECULAR)
    prop(mix(m, scalar(m, 0.18), scalar(m, 0.98), foam), u.MaterialProperty.MP_OPACITY)

    # Coefficients are inverse centimetres: engine optical depth multiplies them
    # by world-space water thickness. Avoid emissive color or a tropical cyan floor.
    output = node(m, u.MaterialExpressionSingleLayerWaterMaterialOutput)
    link(color(m, (0.00055, 0.0018, 0.0021)), output, "ScatteringCoefficients")
    link(color(m, (0.0060, 0.0028, 0.0016)), output, "AbsorptionCoefficients")
    link(scalar(m, 0.15), output, "PhaseG")
    link(color(m, (0.78, 0.90, 0.88)), output, "ColorScaleBehindWater")
    outputs = [e for e in u.MaterialEditingLibrary.get_material_expressions(m)
               if isinstance(e, u.MaterialExpressionSingleLayerWaterMaterialOutput)]
    if len(outputs) != 1:
        raise RuntimeError("Water requires exactly one Single Layer Water output")


def _verify_math():
    """Engine-free bounds/unit checks for the authored spectrum and shader text."""
    assert len(_WAVES) == 8 and sum(w[2] for w in _WAVES) < 0.13
    for wavelength, direction, slope in _WAVES:
        k = 2 * math.pi / wavelength
        assert abs(k * wavelength - 2 * math.pi) < 1e-12
        assert math.isfinite(math.sqrt(9.81 * k)) and math.hypot(*direction) > 0
        assert 0 < slope < 0.06
    # The slope bound guarantees an upward, finite world normal even at alignment.
    bound = sum(w[2] for w in _WAVES)
    assert 1 / math.sqrt(1 + bound * bound) > 0.99
    code = _normal_code()
    assert code.count("float phase") == 8 and "P.xy*0.01" in code
    assert "fwidth" in code and "normalize(float3(-slope,1.0))" in code
    print("PASS: eight metre-scaled waves, finite dispersion, bounded upward normals, distance/footprint filtering")


if __name__ == "__main__":
    _verify_math()
