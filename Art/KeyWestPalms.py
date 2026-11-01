"""Original palm kit: closed bent trunks and individual pinnate leaflets.

Pure Python geometry only. Coordinates are metres, Z up, trunk base at zero.
Keep the authored winding when exporting: leaflet surfaces are intentionally
open, upward-facing quads for a two-sided foliage material. No external models,
downloads, Blender state or original Key West assets are changed here.
"""
import json
import math
import random
from collections import Counter


MATERIALS = {
    "KWD_PalmTrunk": {"color": [.31, .265, .18], "roughness": .91, "vertex_color": True},
    "KWD_PalmLeaf": {"color": [.065, .185, .040], "roughness": .72,
                     "vertex_color": True, "two_sided": True, "foliage": True,
                     "subsurface_color": [.10, .24, .035]},
}
VARIANTS = (
    {"height": 9.0, "bend": .38, "reach": 3.08, "fronds": 20, "stations": 12, "kind": "coconut"},
    {"height": 11.6, "bend": .18, "reach": 3.35, "fronds": 24, "stations": 13, "kind": "royal"},
    {"height": 14.2, "bend": 1.16, "reach": 3.58, "fronds": 22, "stations": 14, "kind": "coconut"},
)


def _add(a, b):
    return tuple(x+y for x, y in zip(a, b))


def _scale(a, value):
    return tuple(x*value for x in a)


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _unit(a):
    length = math.sqrt(sum(x*x for x in a))
    if length < 1e-10:
        raise ValueError("Degenerate palm direction")
    return _scale(a, 1/length)


def _tube(batch, rings, material, colors):
    """CCW rings viewed along the axis; side and end winding is explicit."""
    batch.face(list(reversed(rings[0])), material, colors[0])
    sides = len(rings[0])
    for j, (lower, upper) in enumerate(zip(rings, rings[1:])):
        for k in range(sides):
            nxt = (k+1) % sides
            batch.face([lower[k], lower[nxt], upper[nxt], upper[k]], material, colors[j])
    batch.face(rings[-1], material, colors[-1])


def _fruit(batch, center, size, tint):
    sides = 8
    rings = [[(center[0]+size[0]*math.cos(a)*math.cos(lat),
               center[1]+size[1]*math.sin(a)*math.cos(lat),
               center[2]+size[2]*math.sin(lat))
              for a in (i*math.tau/sides for i in range(sides))]
             for lat in (-math.pi/4, 0, math.pi/4)]
    lower, upper = _add(center, (0, 0, -size[2])), _add(center, (0, 0, size[2]))
    for k in range(sides):
        nxt = (k+1) % sides
        batch.face([lower, rings[0][nxt], rings[0][k]], "KWD_PalmTrunk", tint)
        batch.face([rings[-1][k], rings[-1][nxt], upper], "KWD_PalmTrunk", tint)
    for a, b in zip(rings, rings[1:]):
        for k in range(sides):
            nxt = (k+1) % sides
            batch.face([a[k], a[nxt], b[nxt], b[k]], "KWD_PalmTrunk", tint)


def _model(Batch, variant):
    spec = VARIANTS[variant]
    rng = random.Random(98173+variant*263)
    batch = Batch()
    height, bend, reach = spec["height"], spec["bend"], spec["reach"]
    crown_height = height-1.08
    royal = spec["kind"] == "royal"
    def trunk_center(t):
        return (bend*t*t, -.075*math.sin(t*math.pi), crown_height*t)
    rings, colors = [], []
    for j in range(17):
        t = j/16
        radius = ((.275-.095*t+.045*math.sin(t*math.pi)**2) if royal
                  else (.225-.102*t+.025*math.exp(-t*12)))
        if t > .88:
            radius *= 1-.12*(t-.88)/.12
        center = trunk_center(t)
        rings.append([_add(center, (radius*math.cos(k*math.tau/10), radius*math.sin(k*math.tau/10), 0)) for k in range(10)])
        noise = rng.uniform(.84, 1.04)
        colors.append((noise*.85, noise*.92, noise*.88) if not royal or t < .82 else (.52, .97, .43))
    _tube(batch, rings, "KWD_PalmTrunk", colors)
    trunk_faces = len(batch.faces)
    crown = trunk_center(1)

    # Retained leaf bases give the crown a physical transition into the trunk.
    for j in range(18 if royal else 22):
        angle = j*2.399963229728653+variant*.33
        t = .85+.12*(j%4)/3
        c = trunk_center(t)
        radial = (math.cos(angle), math.sin(angle), 0)
        side = (-radial[1], radial[0], 0)
        a = _add(c, _add(_scale(radial, .11), (0, 0, -.14)))
        b = _add(c, _add(_scale(radial, .24), (0, 0, .17)))
        axis = _unit(tuple(y-x for x, y in zip(a, b)))
        other = _cross(axis, side)
        boots = [[_add(p, _add(_scale(side, width*math.cos(k*math.tau/4)),
                              _scale(other, width*.55*math.sin(k*math.tau/4)))) for k in range(4)]
                 for p, width in ((a, .075), (b, .025))]
        tint = (.73, .78, .58) if royal else (.67, .62, .43)
        _tube(batch, boots, "KWD_PalmTrunk", [tint, tint])

    leaflets = 0
    leaf_start = len(batch.faces)
    for j in range(spec["fronds"]):
        angle = j*2.399963229728653+variant*.47+rng.uniform(-.08, .08)
        u = (math.cos(angle), math.sin(angle), 0)
        v = (-u[1], u[0], 0)
        young = j < 4
        length = (reach*.52 if young else reach)*rng.uniform(.88, 1.06)
        tip_z = rng.uniform(.88, 1.13) if young else -rng.uniform(.65, 1.55)
        arch = .35 if young else rng.uniform(.62, .94)
        curl = rng.uniform(-.16, .16)
        def curve(t):
            return _add(crown, _add(_scale(u, length*t),
                                   _add(_scale(v, curl*math.sin(t*math.pi)),
                                        (0, 0, arch*math.sin(t*math.pi)+tip_z*t))))
        # Thin closed rachis, rather than a full unbroken polygon frond.
        rachis = []
        for k in range(7):
            t = k/6
            tangent = _unit(_add(_scale(u, length),
                                 _add(_scale(v, curl*math.pi*math.cos(t*math.pi)),
                                      (0, 0, arch*math.pi*math.cos(t*math.pi)+tip_z))))
            w = _unit(_cross(tangent, v))
            radius = .026*(1-t)+.003
            rachis.append([_add(curve(t), _add(_scale(v, radius*math.cos(k*math.tau/4)),
                                               _scale(w, radius*math.sin(k*math.tau/4)))) for k in range(4)])
        tint = (.49, .88, .33)
        _tube(batch, rachis, "KWD_PalmTrunk", [tint]*7)
        for k in range(spec["stations"]):
            s = .115+.835*(k+.15)/spec["stations"]
            for side in (-1, 1):
                t = min(.975, s+rng.uniform(-.012, .012))
                base = curve(t)
                span = (.25+.59*math.sin(math.pi*t)**.65)*rng.uniform(.87, 1.12)*(0.74 if young else 1)
                direction = _unit(_add(_scale(v, side), _scale(u, .22+.24*t)))
                across = (-direction[1], direction[0], 0)
                droop = (.12+.27*t)*rng.uniform(.85, 1.18)
                centers = [_add(base, _add(_scale(direction, span*q),
                                          (0, 0, .10*math.sin(q*math.pi)-droop*q*q))) for q in (0, .52, 1)]
                widths = (.018, rng.uniform(.041, .061)*(0.85 if young else 1), .0012)
                light = rng.uniform(.80, 1.18)
                tint = (light*(1.06 if young else .93), light, light*(.91 if young else .83))
                for segment in range(2):
                    a, b = centers[segment:segment+2]
                    wa, wb = widths[segment:segment+2]
                    # Along blade then across blade gives +Z winding on both sides.
                    batch.face([_add(a, _scale(across, -wa)), _add(b, _scale(across, -wb)),
                                _add(b, _scale(across, wb)), _add(a, _scale(across, wa))], "KWD_PalmLeaf", tint)
                leaflets += 1

    coconuts = 0 if royal else 5+variant
    for j in range(coconuts):
        angle = j*math.tau/coconuts+.29
        c = _add(crown, (.25*math.cos(angle), .25*math.sin(angle), -.22-.08*(j%2)))
        _fruit(batch, c, (.105, .095, .14), (.75, .98, .42))
    # Heights refer to the complete mesh from soil to its highest leaflet,
    # rather than the shaft or a lower drooping frond. Preserve ground at zero.
    raw_height = max(v[2] for v in batch.vertices)
    height_scale = height/raw_height
    batch.vertices = [(x, y, height if z == raw_height else z*height_scale) for x, y, z in batch.vertices]
    bounds = [[min(v[i] for v in batch.vertices) for i in range(3)], [max(v[i] for v in batch.vertices) for i in range(3)]]
    stats = {"asset": "KWD_Palm"+str(variant), "kind": spec["kind"], "nominal_height_m": height,
             "fronds": spec["fronds"], "leaflets": leaflets, "coconuts": coconuts,
             "triangles": sum(len(f)-2 for f in batch.faces), "bounds_m": bounds,
             "mesh_height_m": bounds[1][2]-bounds[0][2], "crown_attachment_height_m": crown_height*height_scale,
             "trunk_faces": trunk_faces, "leaf_layer_first_face": leaf_start,
             "winding_policy": "closed_trunk_upward_open_leaflets"}
    return batch, stats


def build(Batch, export):
    models = []
    for variant in range(3):
        batch, stats = _model(Batch, variant)
        if stats["triangles"] > 6000:
            raise ValueError("Palm variant exceeds its triangle budget")
        export(stats["asset"], batch, collision=False, foliage=True, derived=False, role="palm",
               metadata={"source_palm_asset": "KW_Palm"+str(variant), "palm_geometry": stats})
        models.append(stats)
    return {"variants": models, "model_triangles": sum(m["triangles"] for m in models),
            "placement_policy": "replace_existing_2200_instances"}


def self_test():
    from GenerateKeyWest import Batch
    def normal(points):
        return _cross(tuple(b-a for a, b in zip(points[0], points[1])),
                      tuple(b-a for a, b in zip(points[0], points[2])))
    outputs = []
    result = build(Batch, lambda *a, **k: outputs.append((a, k)))
    assert len(outputs) == 3 and len({m["triangles"] for m in result["variants"]}) == 3
    fingerprints = set()
    for variant, ((name, batch), settings) in enumerate(outputs):
        stats = result["variants"][variant]
        assert name == "KWD_Palm"+str(variant) and settings["metadata"]["source_palm_asset"] == "KW_Palm"+str(variant)
        assert settings["foliage"] and not settings["collision"] and not settings["derived"]
        assert settings["role"] == "palm" and 3000 <= stats["triangles"] <= 6000
        assert all(math.isfinite(x) for v in batch.vertices for x in v)
        assert set(batch.slots) == set(MATERIALS) and min(v[2] for v in batch.vertices) == 0
        assert abs(stats["mesh_height_m"]-stats["nominal_height_m"]) < 1e-10
        assert abs(stats["bounds_m"][1][2]-VARIANTS[variant]["height"]) < 1e-10
        assert all(stats["bounds_m"][1][i]-stats["bounds_m"][0][i] > 5 for i in (0, 1))
        assert all(len(face) >= 3 and sum(x*x for x in normal([batch.vertices[i] for i in face])) > 1e-14 for face in batch.faces)
        edges = Counter()
        for face in batch.faces[:stats["trunk_faces"]]:
            points = [tuple(round(x, 8) for x in batch.vertices[i]) for i in face]
            for a, b in zip(points, points[1:]+points[:1]):
                edges[tuple(sorted((a, b)))] += 1
        assert set(edges.values()) == {2}, "Trunk has an open edge"
        volume = 0
        for face in batch.faces[:stats["trunk_faces"]]:
            p = [batch.vertices[i] for i in face]
            for j in range(1, len(p)-1):
                cross = _cross(p[j], p[j+1])
                volume += sum(a*b for a, b in zip(p[0], cross))/6
        assert volume > .25, "Closed trunk winding must enclose positive volume"
        assert normal([batch.vertices[i] for i in batch.faces[0]])[2] < 0
        assert normal([batch.vertices[i] for i in batch.faces[stats["trunk_faces"]-1]])[2] > 0
        leaves = [[batch.vertices[i] for i in f] for f, s in zip(batch.faces, batch.face_slots) if batch.slots[s] == "KWD_PalmLeaf"]
        assert len(leaves) == stats["leaflets"]*2 and stats["fronds"] >= 18 and stats["leaflets"] >= 480
        assert all(normal(face)[2] > 0 for face in leaves)
        leaf_vertices = [v for f in leaves for v in f]
        assert max(v[2] for v in leaf_vertices)-min(v[2] for v in leaf_vertices) > 2
        assert min(v[2] for v in leaf_vertices) < stats["mesh_height_m"]-2
        assert min(v[2] for v in leaf_vertices) > stats["mesh_height_m"]-4
        cx = VARIANTS[variant]["bend"]
        sectors = {int((math.atan2(v[1], v[0]-cx)+math.pi)/math.tau*12) % 12 for v in leaf_vertices if math.hypot(v[0]-cx, v[1]) > 1}
        assert len(sectors) == 12, "Crown has an empty angular sector"
        repeat, repeat_stats = _model(Batch, variant)
        assert repeat.vertices == batch.vertices and repeat.faces == batch.faces and repeat.colors == batch.colors
        assert repeat_stats == stats
        fingerprints.add(tuple(batch.vertices))
    assert len(fingerprints) == 3
    assert MATERIALS["KWD_PalmLeaf"]["two_sided"] and MATERIALS["KWD_PalmLeaf"]["foliage"]
    json.dumps(result)
    print("PASS three distinct closed ground-based trunks, volume crowns, individual curved leaflets, winding, materials, finite geometry and budgets")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        raise SystemExit("Import build(Batch, export), or use --self-test")
