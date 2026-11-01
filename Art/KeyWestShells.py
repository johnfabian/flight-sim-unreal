"""Replacement city shells for the isolated Key West detail map.

The geographic generator already authors outward wall and upward roof winding.
Its faces are disconnected on purpose. Exporters must preserve that winding;
blind connected-volume normal recalculation is unsuitable for these polygons.
This module imports original geometry without changing any original assets.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

from GenerateKeyWest import building_into, clean_ring, point_in_ring


TILE_SIZE = 256
MATERIAL_MAP = {"KW_Wall": "KWD_Wall", "KW_Roof": "KWD_Roof", "KW_Glass": "KWD_Glass"}


def _label(value):
    return ("p" if value >= 0 else "m") + f"{abs(value):03d}"


def _name(tile, prefix):
    return prefix + "City_N" + _label(tile[0]) + "_E" + _label(tile[1])


def build(scene, Batch, export):
    """Emit colliding replacements; the importer swaps existing city actors.

    Batch follows GenerateKeyWest.Batch's recorder protocol. Export receives
    role='city_shell' and source_city_asset so no duplicate actors are needed.
    Original face order, positions, colors and collision surface are retained.
    """
    stats = {"buildings": 0, "height_sources": defaultdict(int)}
    tiles = defaultdict(Batch)
    for building in scene["buildings"]:
        ring = clean_ring(building["outer"])
        center = [sum(p[i] for p in ring) / len(ring) for i in range(2)]
        tile = tuple(math.floor(v / TILE_SIZE) for v in center)
        building_into(tiles[tile], building, tuple(v * TILE_SIZE for v in tile), stats)
    triangles = 0
    names = []
    for tile, batch in sorted(tiles.items()):
        # Rename only slots: indices, vertices, face order and winding survive.
        batch.slots = [MATERIAL_MAP[name] for name in batch.slots]
        source_name = _name(tile, "KW_")
        names.append(source_name)
        triangles += sum(len(face) - 2 for face in batch.faces)
        export(_name(tile, "KWD_"), batch,
               position=(tile[0] * TILE_SIZE, tile[1] * TILE_SIZE, 0),
               collision=True, derived=True, role="city_shell",
               metadata={"source_city_asset": source_name,
                         "winding_policy": "preserve_analytical_faces",
                         "tile_size_m": TILE_SIZE})
    return {"buildings": stats["buildings"], "tiles": len(tiles),
            "triangles": triangles, "height_sources": dict(stats["height_sources"]),
            "source_city_assets": names, "winding_policy": "preserve_analytical_faces"}


def _normal(points):
    # Newell's method also covers split gable quads with collinear vertices.
    normal = [0.0, 0.0, 0.0]
    for a, b in zip(points, points[1:] + points[:1]):
        normal[0] += (a[1] - b[1]) * (a[2] + b[2])
        normal[1] += (a[2] - b[2]) * (a[0] + b[0])
        normal[2] += (a[0] - b[0]) * (a[1] + b[1])
    return normal


def _check_winding(batch, building):
    def solid(p):
        return point_in_ring(p, building["outer"]) and not any(
            point_in_ring(p, hole) for hole in building.get("holes", []))
    walls = roofs = courtyard_walls = 0
    for face, slot in zip(batch.faces, batch.face_slots):
        points = [batch.vertices[i] for i in face]
        normal = _normal(points)
        material = batch.slots[slot]
        if material == "KWD_Roof":
            assert normal[2] > 1e-8, "Roof must face upward"
            roofs += 1
        else:
            length = math.hypot(*normal[:2])
            assert length > 1e-8 and abs(normal[2]) < 1e-8
            center = [sum(p[i] for p in points) / len(points) for i in range(2)]
            # Window faces sit 25 mm outside the wall; cross that known offset.
            step = .03 if material == "KWD_Glass" else .001
            outside = [center[i] + normal[i] / length * step for i in range(2)]
            inside = [center[i] - normal[i] / length * step for i in range(2)]
            assert not solid(outside) and solid(inside), "Wall/window points into building"
            if material == "KWD_Wall":
                walls += 1
                courtyard_walls += any(point_in_ring(outside, h) for h in building.get("holes", []))
    assert walls and roofs
    return courtyard_walls


def self_test():
    from GenerateKeyWest import Batch
    rect = [(0, 0), (12, 0), (12, 8), (0, 8)]
    concave = [(0, 0), (8, 0), (8, 3), (3, 3), (3, 8), (0, 8)]
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hole = [(3, 3), (7, 3), (7, 7), (3, 7)]
    triangles = []
    for i in range(4):
        a, b, c, d = outer[i], outer[(i+1) % 4], hole[(i+1) % 4], hole[i]
        triangles.extend([[a, b, c], [a, c, d]])
    fixtures = [dict(id="gable", outer=rect, roof_shape="gable"),
                dict(id="reversed", outer=list(reversed(rect)), roof_shape="gable"),
                dict(id="concave", outer=concave, roof_shape="gable"),
                dict(id="courtyard", outer=outer, holes=[hole], roof_shape="flat", roof_triangles_ne=triangles)]
    for fixture in fixtures:
        building = {"ground_m": 2, "height_m": 7, "holes": [], **fixture}
        exports = []
        stats = build({"buildings": [building]}, Batch, lambda *a, **k: exports.append((a, k)))
        (name, batch), settings = exports[0]
        assert name == "KWD_City_Np000_Ep000" and stats["tiles"] == stats["buildings"] == 1
        assert settings["collision"] and settings["derived"] and settings["role"] == "city_shell"
        assert settings["metadata"]["source_city_asset"] == "KW_City_Np000_Ep000"
        courtyard = _check_winding(batch, building)
        assert courtyard == (4 if fixture["id"] == "courtyard" else 0)
        original = Batch()
        building_into(original, building, (0, 0), {"buildings": 0, "height_sources": defaultdict(int)})
        assert original.vertices == batch.vertices and original.faces == batch.faces
        assert original.colors == batch.colors and original.face_slots == batch.face_slots
        assert [MATERIAL_MAP[s] for s in original.slots] == batch.slots
        json.dumps(stats)
    shifted = {**fixtures[0], "id": "negative_tile", "ground_m": 2, "height_m": 7,
               "outer": [(x-257, y+511) for x, y in rect]}
    exports = []
    build({"buildings": [shifted]}, Batch, lambda *a, **k: exports.append((a, k)))
    assert exports[0][0][0] == "KWD_City_Nm001_Ep002" and exports[0][1]["position"] == (-256, 512, 0)
    print("PASS outward exterior/courtyard/window normals, upward concave/gable/flat roofs, exact geometry and negative-tile placement")


def check_scene(scene_path, catalog_path):
    """Read-only exact comparison with the preserved geographic city catalog."""
    from GenerateKeyWest import Batch
    source = Path(scene_path).read_bytes()
    scene = json.loads(source.decode("utf-8-sig"))
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8-sig"))
    assert hashlib.sha256(source).hexdigest() == catalog["source_scene_sha256"]
    specs = {a["name"]: a for a in catalog["assets"] if a["role"] == "city"}
    placements = {p["asset"]: p for p in catalog["placements"] if p["asset"] in specs}
    seen = set()
    def verify(name, batch, **settings):
        base = settings["metadata"]["source_city_asset"]
        assert base not in seen and name == base.replace("KW_", "KWD_", 1)
        seen.add(base)
        spec = specs[base]
        assert list(settings["position"]) == placements[base]["position_m"]
        bounds = [[min(v[i] for v in batch.vertices) for i in range(3)],
                  [max(v[i] for v in batch.vertices) for i in range(3)]]
        assert bounds == spec["bounds_m"]
        assert sum(len(f)-2 for f in batch.faces) == spec["triangles"]
        assert batch.slots == [MATERIAL_MAP[s] for s in spec["materials"]]
        for face, slot in zip(batch.faces, batch.face_slots):
            n = _normal([batch.vertices[i] for i in face])
            if batch.slots[slot] == "KWD_Roof":
                assert n[2] > 1e-7
            else:
                assert math.hypot(*n[:2]) > 1e-7 and abs(n[2]) < 1e-6
    stats = build(scene, Batch, verify)
    assert seen == set(specs)
    print(json.dumps({"result": "PASS", "exact_baseline_city_catalog": True, **stats}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check-scene", type=Path)
    parser.add_argument("--base-catalog", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.check_scene and args.base_catalog:
        check_scene(args.check_scene, args.base_catalog)
    else:
        parser.error("Use --self-test, or --check-scene PATH --base-catalog PATH")
