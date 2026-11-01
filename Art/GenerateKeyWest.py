"""Original Florida kit and OSM-derived city geometry, isolated from older art.

Blender: --background --factory-startup --python this.py -- --root PROJECT
Python:  this.py --self-test (no Blender, network or generated assets required).
Coordinates are metres: X north/front, Y east/right, Z up. Y reflection exists
only on the temporary FBX export copy to match the established Unreal pipeline.
"""
import argparse
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

MATERIALS = {
    "KW_Wall": {"color": [.72, .67, .53], "roughness": .82, "vertex_color": True},
    "KW_Roof": {"color": [.45, .48, .47], "roughness": .58, "vertex_color": True},
    "KW_Trim": {"color": [.78, .77, .67], "roughness": .62},
    "KW_Glass": {"color": [.035, .075, .09], "roughness": .29, "metallic": .12, "opaque": True},
    "KW_Wood": {"color": [.24, .17, .10], "roughness": .87},
    "KW_Concrete": {"color": [.51, .49, .40], "roughness": .91},
    "KW_Road": {"color": [.105, .112, .108], "roughness": .90},
    "KW_Marking": {"color": [.71, .70, .61], "roughness": .74},
    "KW_TaxiMarking": {"color": [.78, .54, .055], "roughness": .74},
    "KW_PalmTrunk": {"color": [.28, .23, .15], "roughness": .94},
    "KW_PalmLeaf": {"color": [.075, .22, .055], "roughness": .82, "two_sided": True},
    "KW_Hull": {"color": [.76, .77, .68], "roughness": .42},
    "KW_Red": {"color": [.36, .055, .025], "roughness": .65},
}
WALL_PALETTE = [(1, .94, .78), (.78, .96, .87), (1, .76, .63), (.75, .87, 1), (.94, .82, .95)]
ROOF_PALETTE = [(.78, .85, .87), (.53, .60, .61), (.66, .48, .35), (.85, .80, .66)]


def area(ring):
    return .5 * sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(ring, ring[1:]+ring[:1]))


def clean_ring(points):
    out = []
    for point in points:
        p = tuple(float(v) for v in point[:2])
        if len(p) != 2 or not all(math.isfinite(v) for v in p):
            raise ValueError("Non-finite geographic coordinate")
        if not out or math.dist(p, out[-1]) > 1e-5:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) < 1e-5:
        out.pop()
    if len(out) < 3 or abs(area(out)) < .05:
        raise ValueError("Degenerate footprint")
    return out


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def point_in_ring(p, ring):
    inside = False
    for a, b in zip(ring, ring[1:]+ring[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]):
            if p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
                inside = not inside
    return inside


def triangulate_simple(ring):
    """Ear clipping for simple rings only. Courtyards require validated input."""
    r = ring if area(ring) > 0 else list(reversed(ring))
    indices = list(range(len(r))); result = []
    while len(indices) > 3:
        found = False
        for j, ib in enumerate(indices):
            ia, ic = indices[j-1], indices[(j+1) % len(indices)]
            a, b, c = r[ia], r[ib], r[ic]
            if cross(a, b, c) <= 1e-8:
                continue
            if any(all(x >= -1e-8 for x in (cross(a,b,r[k]), cross(b,c,r[k]), cross(c,a,r[k])))
                   for k in indices if k not in (ia, ib, ic)):
                continue
            result.append([a,b,c]); indices.pop(j); found = True; break
        if not found:
            raise ValueError("Footprint is not a triangulatable simple polygon")
    result.append([r[k] for k in indices])
    return result


def roof_triangles(building, outer, holes):
    given = building.get("roof_triangles_ne")
    if given is None:
        if holes:
            raise ValueError(f"Building {building.get('id')} has courtyard holes but no validated roof triangles")
        return triangulate_simple(outer)
    tris = [[tuple(map(float, p[:2])) for p in tri] for tri in given]
    if any(len(t) != 3 or not all(math.isfinite(v) for p in t for v in p) for t in tris):
        raise ValueError("Invalid supplied roof triangles")
    expected = abs(area(outer))-sum(abs(area(h)) for h in holes)
    actual = sum(abs(cross(*t))*.5 for t in tris)
    if not tris or abs(actual-expected) > max(.1, expected*.005):
        raise ValueError(f"Roof triangle coverage mismatch: {actual} vs {expected}")
    return tris


def split_polygon(points, value, positive):
    """Clip a convex triangle/polygon at the gable ridge, preserving its outline."""
    result = []
    for a, b in zip(points, points[1:]+points[:1]):
        va, vb = value(a), value(b)
        ina, inb = (va >= -1e-8, vb >= -1e-8) if positive else (va <= 1e-8, vb <= 1e-8)
        if ina: result.append(a)
        if ina != inb:
            t = va/(va-vb)
            result.append((a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t))
    return result


def clip_rect(points, bounds):
    result=list(points)
    for axis,bound,positive in [(0,bounds[0],True),(1,bounds[1],True),(0,bounds[2],False),(1,bounds[3],False)]:
        if len(result)<3: return []
        result=split_polygon(result,lambda p,a=axis,b=bound:p[a]-b,positive)
    return result if len(result)>=3 and abs(area(result))>1e-7 else []


def projected_uv(point, normal):
    """Face projection keeps vertical walls/windows from collapsing to UV lines."""
    axis=max(range(3),key=lambda i:abs(normal[i]))
    a,b=((1,2),(0,2),(0,1))[axis]
    return (point[a]*.2,point[b]*.2)


class Batch:
    def __init__(self):
        self.vertices=[]; self.faces=[]; self.slots=[]; self.face_slots=[]; self.colors=[]

    def face(self, points, material, color=(1,1,1)):
        if len(points) < 3: return
        start=len(self.vertices); self.vertices.extend(points)
        self.faces.append(tuple(range(start,start+len(points))))
        if material not in self.slots: self.slots.append(material)
        self.face_slots.append(self.slots.index(material)); self.colors.append(color)

    def box(self, center, size, material, color=(1,1,1)):
        x,y,z=center; a,b,c=(v*.5 for v in size)
        v=[(x+sx*a,y+sy*b,z+sz*c) for sx,sy,sz in
           [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        for f in [(3,2,1,0),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)]:
            self.face([v[i] for i in f],material,color)

    def rod(self, a, b, radius, material, sides=8, tip=None):
        import mathutils
        a,b=mathutils.Vector(a),mathutils.Vector(b); axis=(b-a).normalized()
        u=axis.cross(mathutils.Vector((0,0,1)))
        if u.length < .01: u=axis.cross(mathutils.Vector((0,1,0)))
        u.normalize(); v=axis.cross(u); tip=radius if tip is None else tip
        lower=[]; upper=[]
        for i in range(sides):
            d=u*math.cos(i*math.tau/sides)+v*math.sin(i*math.tau/sides)
            lower.append(tuple(a+d*radius)); upper.append(tuple(b+d*tip))
        self.face(list(reversed(lower)),material); self.face(upper,material)
        for i in range(sides): self.face([lower[i],lower[(i+1)%sides],upper[(i+1)%sides],upper[i]],material)


def building_into(batch, b, origin, stats):
    outer=clean_ring(b["outer"]); holes=[clean_ring(h) for h in b.get("holes",[])]
    triangles=roof_triangles(b,outer,holes)
    rng=random.Random(str(b.get("id")))
    ground=float(b.get("ground_m",2.0)); given=b.get("height_m"); levels=b.get("levels")
    kind=str(b.get("kind","")).lower()
    if given is not None and float(given)>0:
        height=max(2.5,min(65,float(given))); source=str(b.get("height_source","source height"))
    else:
        floors=float(levels) if levels is not None and float(levels)>0 else (3 if any(k in kind for k in ("hotel","apart","office")) else 1.5)
        height=max(3,min(45,floors*3.0)); source="inferred from levels" if levels else "inferred typology"
    stats["height_sources"][source]+=1
    edges=list(zip(outer,outer[1:]+outer[:1])); a,bp=max(edges,key=lambda pair:math.dist(*pair))
    length=math.dist(a,bp); u=((bp[0]-a[0])/length,(bp[1]-a[1])/length); v=(-u[1],u[0])
    coords=[p[0]*v[0]+p[1]*v[1] for p in outer]; mid=(min(coords)+max(coords))*.5; half=(max(coords)-min(coords))*.5
    footprint_area=abs(area(outer))-sum(abs(area(h)) for h in holes)
    tag=str(b.get("roof_shape","")).lower()
    pitched=tag not in ("flat","terrace","dome") and footprint_area < 650 and not any(k in kind for k in ("hotel","industrial","commercial")) and half>1
    rise=min(2.2,height*.26,half*.40) if pitched else 0
    def signed(p): return p[0]*v[0]+p[1]*v[1]-mid
    def top(p): return ground+height-rise*min(1,abs(signed(p))/max(half,.1))
    def local(p,z): return (p[0]-origin[0],p[1]-origin[1],z)
    wall_color=rng.choice(WALL_PALETTE); roof_color=rng.choice(ROOF_PALETTE)
    for ring in [outer]+holes:
        ring=ring if (area(ring)>0)==(ring is outer) else list(reversed(ring))
        for a,c in zip(ring,ring[1:]+ring[:1]):
            points=[a,c]
            if pitched and signed(a)*signed(c)<-1e-8:
                t=signed(a)/(signed(a)-signed(c)); points.insert(1,(a[0]+(c[0]-a[0])*t,a[1]+(c[1]-a[1])*t))
            for q,r in zip(points,points[1:]):
                batch.face([local(q,ground),local(r,ground),local(r,top(r)),local(q,top(q))],"KW_Wall",wall_color)
                # Recess-free opaque window quads remain cheap and readable in flight.
                dist=math.dist(q,r)
                if dist>4:
                    dx,dy=(r[0]-q[0])/dist,(r[1]-q[1])/dist; nx,ny=dy,-dx
                    for t in range(2,max(3,int(dist)-1),4):
                        x,y=q[0]+dx*t+nx*.025,q[1]+dy*t+ny*.025
                        for floor in range(max(1,min(5,int((height-rise)/3)))):
                            z=ground+1.0+floor*3
                            if z+1.0<min(top(q),top(r))-.1:
                                batch.face([local((x-dx*.48,y-dy*.48),z),local((x+dx*.48,y+dy*.48),z),local((x+dx*.48,y+dy*.48),z+1),local((x-dx*.48,y-dy*.48),z+1)],"KW_Glass")
    for tri in triangles:
        pieces=[tri] if not pitched else [split_polygon(tri,signed,True),split_polygon(tri,signed,False)]
        for piece in pieces:
            if len(piece)>=3:
                if area(piece)<0: piece=list(reversed(piece))
                batch.face([local(p,top(p)) for p in piece],"KW_Roof",roof_color)
    stats["buildings"]+=1


def make_kit(export):
    """All geometry here is original, independent of geographic source data."""
    for i in range(3):
        b=Batch(); width,depth=6+i*1.4,9+i*1.5; height=3.1 if i<2 else 5.9
        b.box((0,0,height/2+.45),(depth,width,height),"KW_Wall",WALL_PALETTE[i])
        b.box((depth/2+1.2,0,.35),(2.5,width+.7,.25),"KW_Wood")
        for y in (-width/2,width/2,0): b.rod((depth/2+2.2,y,.4),(depth/2+2.2,y,3.2),.07,"KW_Trim",6)
        b.box((depth/2+1.2,0,3.25),(2.8,width+1,.14),"KW_Roof")
        x0,x1=-depth/2-.35,depth/2+.35; y=width/2+.35; z=height+.45
        b.face([(x0,-y,z),(x1,-y,z),(x1,0,z+1.7),(x0,0,z+1.7)],"KW_Roof",ROOF_PALETTE[i])
        b.face([(x0,0,z+1.7),(x1,0,z+1.7),(x1,y,z),(x0,y,z)],"KW_Roof",ROOF_PALETTE[i])
        for side in (-1,1):
            for x in (-depth*.25,depth*.2): b.box((x,side*(width/2+.02),2.1),(1.1,.05,1.15),"KW_Glass")
        export(f"KW_ConchHouse{i}",b,collision=True)
    for name,size,floors in [("KW_Shop",(15,9),2),("KW_Hotel",(28,18),4),("KW_MarinaShed",(24,14),1),("KW_AirportTerminal",(45,18),2)]:
        b=Batch(); x,y=size; h=floors*3.0
        b.box((0,0,h/2),(x,y,h),"KW_Wall",(.92,.88,.73)); b.box((0,0,h+.15),(x+.5,y+.5,.3),"KW_Roof")
        for level in range(floors):
            for q in range(-int(y/2)+2,int(y/2),3): b.box((x/2+.03,q,1.5+level*3),(.06,1.3,1.35),"KW_Glass")
            if name in ("KW_Hotel","KW_Shop"): b.box((x/2+1,0,level*3+.3),(2.2,y,.18),"KW_Trim")
        export(name,b,collision=True)
    b=Batch(); b.box((0,0,6),(3.5,3.5,12),"KW_Wall"); b.box((0,0,13),(6,6,2),"KW_Glass"); b.box((0,0,14.2),(6.5,6.5,.3),"KW_Roof"); export("KW_AirportTower",b,collision=True)
    for variant in range(3):
        b=Batch(); h=9+variant*2.6; bend=variant*.65
        for j in range(5): b.rod((bend*(j/5)**2,0,h*j/5),(bend*((j+1)/5)**2,0,h*(j+1)/5),.22-j*.027,"KW_PalmTrunk",8,tip=.20-j*.027)
        for j in range(11):
            a=j*math.tau/11+variant*.4; ux,uy=math.cos(a),math.sin(a); vx,vy=-uy,ux
            for k in range(5):
                t=k/5; tt=(k+1)/5; reach=3.1+variant*.25
                def frond(s,side): return (bend+ux*reach*s+vx*side*.34*(1-s*.7),uy*reach*s+vy*side*.34*(1-s*.7),h+.5*math.sin(s*math.pi)-1.4*s*s)
                b.face([frond(t,-1),frond(tt,-1),frond(tt,1),frond(t,1)],"KW_PalmLeaf")
                if k>0:
                    tip=frond(tt,0)
                    for side in (-1,1): b.face([frond(t,0),frond(tt,side*1.9),tip],"KW_PalmLeaf")
        export(f"KW_Palm{variant}",b,foliage=True)
    for name,length,width in [("KW_PierSegment",8,3),("KW_DockFinger",6,1.4)]:
        b=Batch(); b.box((0,0,1.05),(length,width,.22),"KW_Wood")
        for x in (-length*.4,length*.4):
            for y in (-width*.4,width*.4): b.rod((x,y,-1.5),(x,y,1.15),.12,"KW_Wood",8)
        export(name,b,collision=True)
    b=Batch(); b.box((0,0,.65),(8,.6,1.3),"KW_Concrete"); export("KW_Seawall",b,collision=True)
    for i in range(3):
        b=Batch(); length=6+i*2.5; width=2.3+i*.4
        bow=length*.55; stern=-length*.45
        b.face([(stern,width/2,.3),(bow,0,.3),(stern,-width/2,.3)],"KW_Hull")
        b.face([(stern,-width/2,1),(stern,width/2,1),(stern,width/2,.3),(stern,-width/2,.3)],"KW_Hull")
        for s in (-1,1):
            side=[(stern,s*width/2,.3),(bow,0,.3),(bow,0,1),(stern,s*width/2,1)]
            b.face(side if s<0 else list(reversed(side)),"KW_Hull")
        b.face([(stern,-width/2,1),(bow,0,1),(stern,width/2,1)],"KW_Wood")
        b.box((-.8,0,1.6),(length*.28,width*.7,1.2),"KW_Hull"); b.box((-.7,0,1.9),(length*.29,width*.72,.55),"KW_Glass")
        if i==2: b.rod((0,0,1),(0,0,8),.045,"KW_Trim",8)
        export(f"KW_Boat{i}",b)


def main():
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    parser=argparse.ArgumentParser(); parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1]); parser.add_argument("--tile-size",type=float,default=256); parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args(argv)
    if args.self_test: self_test(); return
    import bpy,bmesh
    from mathutils import Matrix
    root=args.root.resolve(); source=root/"Art/KeyWest/Data/scene.json"; scene=json.loads(source.read_text(encoding="utf-8"))
    if scene.get("schema")!=1 or scene.get("units") not in ("metres","meters") or scene.get("axes")!={"x":"north","y":"east","z":"up"}:
        raise ValueError("Unsupported Key West geographic contract")
    if not scene.get("land_polygons") or not scene.get("buildings") or not scene.get("runways"):
        raise ValueError("Real land, buildings and runway data are required")
    if args.tile_size<64 or args.tile_size>1024: raise ValueError("Invalid city tile size")
    out=root/"Art/KeyWest/Exports"; out.mkdir(parents=True,exist_ok=True)
    ground_default=float(scene.get("default_ground_m",2.0))
    for i,tile in enumerate(scene.get("imagery_tiles",[])):
        MATERIALS[f"KW_Aerial_{i:02d}"]={"color":[1,1,1],"roughness":.93,"texture_file":str(Path("Art/KeyWest/Data")/tile["file"]),"bounds_ne":tile["bounds_ne"],"world_uv":"u=east,v=south"}
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system="METRIC"; bpy.context.scene.unit_settings.scale_length=1
    mats={}
    for name,spec in MATERIALS.items():
        m=bpy.data.materials.new(name); m.use_nodes=True; p=m.node_tree.nodes.get("Principled BSDF"); p.inputs["Base Color"].default_value=(*spec["color"],1); p.inputs["Roughness"].default_value=spec["roughness"]; p.inputs["Metallic"].default_value=spec.get("metallic",0); m.diffuse_color=(*spec["color"],1)
        if spec.get("vertex_color"):
            attr=m.node_tree.nodes.new("ShaderNodeVertexColor"); attr.layer_name="Color"
            multiply=m.node_tree.nodes.new("ShaderNodeMixRGB"); multiply.blend_type="MULTIPLY"; multiply.inputs[0].default_value=1; multiply.inputs[1].default_value=(*spec["color"],1)
            m.node_tree.links.new(attr.outputs["Color"],multiply.inputs[2]); m.node_tree.links.new(multiply.outputs[0],p.inputs["Base Color"])
        if spec.get("texture_file"):
            image=m.node_tree.nodes.new("ShaderNodeTexImage"); image.image=bpy.data.images.load(str(root/spec["texture_file"]),check_existing=True); m.node_tree.links.new(image.outputs["Color"],p.inputs["Base Color"])
        mats[name]=m
    assets=[]; placements=[]; objects=[]
    def export(name,batch,position=(0,0,0),collision=False,foliage=False,derived=False,role="kit",metadata=None):
        if not batch.faces: return
        mesh=bpy.data.meshes.new(name); mesh.from_pydata(batch.vertices,[],batch.faces); mesh.update()
        for slot in batch.slots: mesh.materials.append(mats[slot])
        for poly,slot in zip(mesh.polygons,batch.face_slots): poly.material_index=slot
        colors=mesh.color_attributes.new(name="Color",type="FLOAT_COLOR",domain="CORNER")
        for poly,c in zip(mesh.polygons,batch.colors):
            for loop in poly.loop_indices: colors.data[loop].color=(*c,1)
        uv=mesh.uv_layers.new(name="UVMap")
        for poly in mesh.polygons:
            for li in poly.loop_indices:
                co=mesh.vertices[mesh.loops[li].vertex_index].co
                if role=="land":
                    # Blender V grows north; FBX importer flips it so Unreal V grows south.
                    bn=metadata["bounds_ne"]; uv.data[li].uv=(co.y/(bn[3]-bn[1]),co.x/(bn[2]-bn[0]))
                else: uv.data[li].uv=projected_uv(co,poly.normal)
        bm=bmesh.new(); bm.from_mesh(mesh); bmesh.ops.recalc_face_normals(bm,faces=bm.faces); bm.to_mesh(mesh); bm.free()
        ob=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(ob); ob.location=position; objects.append(ob)
        bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True); bpy.context.view_layer.objects.active=ob
        original=ob.data; copy=original.copy(); ob.data=copy; copy.transform(Matrix.Diagonal((1,-1,1,1)))
        bm=bmesh.new(); bm.from_mesh(copy); bmesh.ops.reverse_faces(bm,faces=bm.faces); bm.to_mesh(copy); bm.free(); ob.location=(0,0,0)
        bpy.ops.export_scene.fbx(filepath=str(out/(name+".fbx")),use_selection=True,object_types={"MESH"},apply_unit_scale=True,apply_scale_options="FBX_SCALE_UNITS",axis_forward="X",axis_up="Z",bake_space_transform=True,use_mesh_modifiers=True,mesh_smooth_type="FACE",add_leaf_bones=False,bake_anim=False)
        ob.data=original; bpy.data.meshes.remove(copy); ob.location=position; ob.select_set(False)
        bounds=[[min(v[i] for v in batch.vertices) for i in range(3)],[max(v[i] for v in batch.vertices) for i in range(3)]]
        inferred_role=role
        if role=="kit":
            inferred_role="palm" if foliage else "boat" if "Boat" in name else "pier_kit" if any(k in name for k in ("Pier","Dock","Seawall")) else "airport_kit" if "Airport" in name else "building_kit"
        assets.append(dict(name=name,pivot=[0,0,0],materials=batch.slots,collision=collision,foliage=foliage,triangles=sum(len(f)-2 for f in batch.faces),bounds_m=bounds,dimensions_m=[bounds[1][i]-bounds[0][i] for i in range(3)],role=inferred_role,provenance="OSM-derived geographic geometry" if derived else "original procedural art",lod_policy="preserve_closed_shell" if derived else "conventional",**(metadata or {})))
        if derived: placements.append(dict(asset=name,position_m=list(position),yaw_deg=0,scale=[1,1,1]))
    make_kit(export)
    stats={"buildings":0,"height_sources":defaultdict(int)}; tiles=defaultdict(Batch)
    for b in scene["buildings"]:
        ring=clean_ring(b["outer"]); center=[sum(p[i] for p in ring)/len(ring) for i in range(2)]; tile=tuple(math.floor(v/args.tile_size) for v in center); origin=[v*args.tile_size for v in tile]
        building_into(tiles[tile],b,origin,stats)
    def tile_label(value): return ("p" if value>=0 else "m")+f"{abs(value):03d}"
    for (n,e),batch in sorted(tiles.items()): export(f"KW_City_N{tile_label(n)}_E{tile_label(e)}",batch,(n*args.tile_size,e*args.tile_size,0),collision=True,derived=True,role="city")
    land_triangles=[]
    for polygon in scene["land_polygons"]:
        ring=clean_ring(polygon["outer"]); holes=[clean_ring(h) for h in polygon.get("holes",[])]
        given={"id":"land","roof_triangles_ne":polygon["triangles_ne"]} if "triangles_ne" in polygon else {"id":"land"}
        land_triangles.extend(roof_triangles(given,ring,holes))
    for i,tile in enumerate(scene.get("imagery_tiles",[])):
        bounds=tile["bounds_ne"]; batch=Batch()
        if len(bounds)!=4 or bounds[2]<=bounds[0] or bounds[3]<=bounds[1]: raise ValueError("Invalid aerial bounds")
        for triangle in land_triangles:
            if max(p[0] for p in triangle)<bounds[0] or min(p[0] for p in triangle)>bounds[2] or max(p[1] for p in triangle)<bounds[1] or min(p[1] for p in triangle)>bounds[3]: continue
            clipped=clip_rect(triangle,bounds)
            if clipped:
                if area(clipped)<0: clipped.reverse()
                batch.face([(p[0]-bounds[0],p[1]-bounds[1],0) for p in clipped],f"KW_Aerial_{i:02d}")
        export(f"KW_Land_{i:02d}",batch,(bounds[0],bounds[1],ground_default),collision=True,derived=True,role="land",metadata={"bounds_ne":bounds,"imagery_tile_id":tile["id"],"height_source":"modeled flat island elevation"})
    for collection,default_width,material,z in [("roads",6,"KW_Road",2.04),("runways",35,"KW_Road",2.08),("piers",3,"KW_Wood",1.15)]:
        batch=Batch()
        for line in scene.get(collection,[]):
            points=line.get("points",[]); width=max(.6,float(line.get("width_m",default_width)))
            # Data ground elevations are bare-earth levels, not road-surface offsets.
            level=float(line.get("ground_m",ground_default if collection!="piers" else z))+(3 if line.get("bridge") else 0)+(.04 if collection=="roads" else .08 if collection=="runways" else 0)
            for a,b in zip(points,points[1:]):
                length=math.dist(a[:2],b[:2])
                if length<.1: continue
                dx,dy=(b[0]-a[0])/length,(b[1]-a[1])/length; nx,ny=-dy*width/2,dx*width/2
                batch.face([(a[0]+nx,a[1]+ny,level),(a[0]-nx,a[1]-ny,level),(b[0]-nx,b[1]-ny,level),(b[0]+nx,b[1]+ny,level)],material)
                if collection=="runways" and line.get("kind")=="runway":
                    for d in range(20,int(length)-20,40):
                        p=(a[0]+dx*d,a[1]+dy*d); w=.6/width
                        batch.face([(p[0]+nx*w,p[1]+ny*w,level+.025),(p[0]-nx*w,p[1]-ny*w,level+.025),(p[0]+dx*14-nx*w,p[1]+dy*14-ny*w,level+.025),(p[0]+dx*14+nx*w,p[1]+dy*14+ny*w,level+.025)],"KW_Marking")
                elif collection=="runways" and line.get("kind")=="taxiway":
                    w=.3/width
                    batch.face([(a[0]+nx*w,a[1]+ny*w,level+.025),(a[0]-nx*w,a[1]-ny*w,level+.025),(b[0]-nx*w,b[1]-ny*w,level+.025),(b[0]+nx*w,b[1]+ny*w,level+.025)],"KW_TaxiMarking")
        export("KW_Geo_"+collection,batch,collision=True,derived=True,role=collection)
    # Deterministic roadside palms; never place in a building footprint or water.
    rings=[(clean_ring(p["outer"]),[clean_ring(h) for h in p.get("holes",[])]) for p in scene["land_polygons"]]
    def on_land(point):
        return any(point_in_ring(point,r) and not any(point_in_ring(point,h) for h in holes) for r,holes in rings)
    footprints=[clean_ring(b["outer"]) for b in scene["buildings"]]; index=defaultdict(list)
    for r in footprints:
        for n in range(math.floor(min(p[0] for p in r)/64),math.floor(max(p[0] for p in r)/64)+1):
            for e in range(math.floor(min(p[1] for p in r)/64),math.floor(max(p[1] for p in r)/64)+1): index[n,e].append(r)
    rng=random.Random(scene.get("seed",20261031)); palm_count=0
    for road in scene.get("roads",[]):
        if road.get("bridge"): continue
        for a,b in zip(road.get("points",[]),road.get("points",[])[1:]):
            length=math.dist(a[:2],b[:2])
            if length<24: continue
            for d in range(12,int(length),28):
                if palm_count>=2200: break
                side=rng.choice((-1,1)); offset=float(road.get("width_m",6))/2+3.8
                x=a[0]+(b[0]-a[0])*d/length-(b[1]-a[1])/length*offset*side; y=a[1]+(b[1]-a[1])*d/length+(b[0]-a[0])/length*offset*side; p=(x,y)
                if not on_land(p): continue
                if any(point_in_ring(p,r) for r in index[math.floor(x/64),math.floor(y/64)]): continue
                s=rng.uniform(.78,1.14); placements.append(dict(asset=f"KW_Palm{palm_count%3}",position_m=[x,y,float(road.get("ground_m",2))],yaw_deg=rng.uniform(0,360),scale=[s,s,s])); palm_count+=1
    # Place modest boats alongside actual pier segments; exact berths are inferred.
    for pier in scene.get("piers",[])[:240]:
        if any(tag in str(pier.get("kind","")).lower() for tag in ("breakwater","groyne","seawall")): continue
        points=pier.get("points",[])
        if len(points)<2: continue
        a,b=points[0],points[-1]; length=math.dist(a[:2],b[:2])
        if length<8: continue
        dx,dy=(b[0]-a[0])/length,(b[1]-a[1])/length; offset=float(pier.get("width_m",3))/2+2
        for side in (1,-1):
            x=(a[0]+b[0])/2-dy*offset*side; y=(a[1]+b[1])/2+dx*offset*side
            # Check hull centre, bow/stern and beam, not just which pier side looks open.
            probes=[(x,y),(x+dx*5,y+dy*5),(x-dx*5,y-dy*5),(x-dy*1.6,y+dx*1.6),(x+dy*1.6,y-dx*1.6)]
            if any(on_land(p) for p in probes): continue
            placements.append(dict(asset=f"KW_Boat{rng.randrange(3)}",position_m=[x,y,0],yaw_deg=math.degrees(math.atan2(dy,dx)),scale=[1,1,1],placement_source="inferred wet-side berth beside OSM pier")); break
    bpy.ops.wm.save_as_mainfile(filepath=str(root/"Art/KeyWest/KeyWest.blend"))
    catalog=dict(schema=1,units="metres",axes={"x":"north","y":"east","z":"up"},origin_wgs84=scene["origin_wgs84"],tile_size_m=args.tile_size,sea_level_m=0,ground_default_m=ground_default,material_definitions=MATERIALS,assets=assets,placements=placements,statistics={**stats,"height_sources":dict(stats["height_sources"]),"palms":palm_count,"land_triangles":len(land_triangles)},source_scene_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),provenance={"original_kit":"Original code-authored Florida architecture, palms and marina kit", "geographic_shells":"OSM-derived footprints/roads/runways/piers and clipped land; preserve source ODbL attribution", "inferred":"Roof typology, missing heights, bridge elevation, palm and boat placement are modeled, not surveyed", "imagery":"USGS/USDA NAIP source files referenced by the geographic data manifest"})
    (out/"assets.json").write_text(json.dumps(catalog,indent=2),encoding="utf-8")
    print("AERONAUT_KEYWEST_ART_READY "+json.dumps(catalog["statistics"]))


def self_test():
    concave=[(0,0),(8,0),(8,3),(3,3),(3,8),(0,8)]
    triangles=triangulate_simple(concave)
    assert abs(sum(abs(cross(*t))*.5 for t in triangles)-area(concave))<1e-8
    b={"id":"test","outer":concave,"holes":[],"ground_m":2,"height_m":7,"roof_shape":"gable"}
    batch=Batch(); stats={"buildings":0,"height_sources":defaultdict(int)}; building_into(batch,b,(256,512),stats)
    assert stats["buildings"]==1 and set(batch.slots)=={"KW_Wall","KW_Roof","KW_Glass"}
    assert all(math.isfinite(v) for p in batch.vertices for v in p)
    assert max(p[2] for p in batch.vertices)<=9.00001 and min(p[2] for p in batch.vertices)==2
    try: roof_triangles({"id":"hole"},[(0,0),(8,0),(8,8),(0,8)],[[(2,2),(2,4),(4,4),(4,2)]])
    except ValueError: pass
    else: raise AssertionError("Courtyard without validated triangles was accepted")
    assert point_in_ring((1,1),concave) and not point_in_ring((5,5),concave)
    clipped=clip_rect([(-2,-2),(5,-2),(-2,5)],(0,0,2,2))
    assert all(0<=p[0]<=2 and 0<=p[1]<=2 for p in clipped) and abs(area(clipped))>0
    assert abs(math.degrees(math.atan2(1,0))-90)<1e-8
    for face,normal in [([(0,0,0),(0,4,0),(0,4,3)],(1,0,0)), ([(0,0,0),(4,0,0),(4,0,3)],(0,1,0)), ([(0,0,0),(4,0,0),(4,3,0)],(0,0,1))]:
        assert abs(cross(*(projected_uv(p,normal) for p in face)))>.1
    print("PASS: concave area coverage, courtyard rejection, tile-local finite shell, height bounds, north/east yaw")


if __name__=="__main__": main()
