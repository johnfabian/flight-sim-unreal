"""Original, distance-culled architecture over the preserved Key West shells.

Contract: MATERIALS; build(scene, Batch, export) -> JSON-safe statistics.
No Blender imports, file writes, downloads, or geographic edits occur here.
Coordinates are metres, X north / Y east / Z up. Geographic placement is
OSM-derived; the mouldings and inferred architectural treatments are original.
Run with ordinary Python --self-test for geometry and placement checks.
--check-window-guards PATH checks the real grid against generated pane bounds.
"""
import hashlib
import math
import random
import sys
from collections import Counter, defaultdict


MATERIALS = {
    "KWD_Wall": {"color": [.72, .67, .53], "roughness": .82, "vertex_color": True},
    "KWD_Roof": {"color": [.45, .48, .47], "roughness": .58, "vertex_color": True},
    "KWD_Trim": {"color": [.88, .87, .81], "roughness": .63},
    "KWD_Shutter": {"color": [.82, .83, .78], "roughness": .74, "vertex_color": True},
    "KWD_Door": {"color": [.27, .35, .30], "roughness": .72, "vertex_color": True},
    "KWD_Glass": {"color": [.055, .115, .15], "roughness": .19, "metallic": .18, "opaque": True},
    "KWD_Metal": {"color": [.39, .43, .44], "roughness": .50, "metallic": .65},
}
WALL_PALETTE = [(1, .94, .78), (.78, .96, .87), (1, .76, .63), (.75, .87, 1), (.94, .82, .95)]
ROOF_PALETTE = [(.78, .85, .87), (.53, .60, .61), (.66, .48, .35), (.85, .80, .66)]
TILE_SIZE = 256
MAX_TRIANGLES = 1_950_000
CULL_DISTANCE_M = 1250
EPS = 1e-8


def _area(r):
    return .5 * sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(r, r[1:]+r[:1]))


def _ring(points):
    r = []
    for p in points:
        q = (float(p[0]), float(p[1]))
        if not all(math.isfinite(v) for v in q):
            raise ValueError("Non-finite footprint coordinate")
        if not r or math.dist(q, r[-1]) > 1e-5:
            r.append(q)
    if len(r) > 1 and math.dist(r[0], r[-1]) < 1e-5:
        r.pop()
    if len(r) < 3 or abs(_area(r)) < .05:
        raise ValueError("Degenerate footprint")
    return r


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _closest(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    den = dx*dx+dy*dy
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
    return (a[0]+t*dx, a[1]+t*dy)


def _point_distance(p, a, b):
    return math.dist(p, _closest(p, a, b))


def _intersects(a, b, c, d):
    ca, cb, cc, cd = _cross(a,b,c), _cross(a,b,d), _cross(c,d,a), _cross(c,d,b)
    if ((ca > EPS and cb < -EPS) or (ca < -EPS and cb > EPS)) and ((cc > EPS and cd < -EPS) or (cc < -EPS and cd > EPS)):
        return True
    return any(abs(k) < EPS and _point_distance(p,q,r) < 1e-7
               for k,p,q,r in ((ca,c,a,b),(cb,d,a,b),(cc,a,c,d),(cd,b,c,d)))


def _segment_distance(a, b, c, d):
    if _intersects(a,b,c,d):
        return 0
    return min(_point_distance(a,c,d),_point_distance(b,c,d),_point_distance(c,a,b),_point_distance(d,a,b))


def _inside(p, r):
    # Boundary is deliberately included; safety checks separately reject touching.
    result = False
    for a,b in zip(r,r[1:]+r[:1]):
        if abs(_cross(a,b,p)) < EPS and min(a[0],b[0])-EPS <= p[0] <= max(a[0],b[0])+EPS and min(a[1],b[1])-EPS <= p[1] <= max(a[1],b[1])+EPS:
            return True
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
            result = not result
    return result


def _in_shape(p, shape):
    return _inside(p,shape[0]) and not any(_inside(p,h) for h in shape[1])


def _bbox(points, padding=0):
    return (min(p[0] for p in points)-padding,min(p[1] for p in points)-padding,
            max(p[0] for p in points)+padding,max(p[1] for p in points)+padding)


def _overlaps(a,b):
    return a[0]<=b[2] and b[0]<=a[2] and a[1]<=b[3] and b[1]<=a[3]


def _edges(r):
    return zip(r,r[1:]+r[:1])


class _Grid:
    def __init__(self, size=64):
        self.size = size
        self.cells = defaultdict(list)

    def keys(self, bounds):
        for n in range(math.floor(bounds[0]/self.size),math.floor(bounds[2]/self.size)+1):
            for e in range(math.floor(bounds[1]/self.size),math.floor(bounds[3]/self.size)+1):
                yield n,e

    def add(self, key, bounds):
        for cell in self.keys(bounds):
            self.cells[cell].append(key)

    def query(self, bounds):
        return sorted({k for cell in self.keys(bounds) for k in self.cells.get(cell,())})


class _Safety:
    """Conservative whole-polygon tests, no optional Shapely/Blender dependency."""
    def __init__(self, scene):
        self.land = [(_ring(p["outer"]),[_ring(h) for h in p.get("holes",[])]) for p in scene["land_polygons"]]
        self.land_boxes = [_bbox(s[0]) for s in self.land]
        self.land_edges = []
        self.coast_boxes = []
        self.coast = _Grid(128)
        self.land_cells = {}
        for shape in self.land:
            for ring in [shape[0]]+shape[1]:
                for a,b in _edges(ring):
                    self.coast.add(len(self.land_edges),_bbox((a,b)))
                    self.land_edges.append((a,b))
                    self.coast_boxes.append(_bbox((a,b)))
        self.buildings = [(_ring(b["outer"]),[_ring(h) for h in b.get("holes",[])]) for b in scene["buildings"]]
        self.building_boxes = [_bbox(s[0],.2) for s in self.buildings]
        self.neighbours = _Grid()
        for i,shape in enumerate(self.buildings):
            self.neighbours.add(i,self.building_boxes[i])
        self.roads = []
        self.road_boxes = []
        self.road_grid = _Grid()
        # Runways/pier corridors are also forbidden for porches and awnings.
        for collection,width in (("roads",6),("runways",35),("piers",3)):
            for line in scene.get(collection,[]):
                radius = max(.3,float(line.get("width_m",width))/2)+.6
                for a,b in zip(line.get("points",[]),line.get("points",[])[1:]):
                    if math.dist(a[:2],b[:2]) < .01:
                        continue
                    self.road_grid.add(len(self.roads),_bbox((a,b),radius))
                    self.roads.append((tuple(a[:2]),tuple(b[:2]),radius))
                    self.road_boxes.append(_bbox((a,b),radius))

    def on_land(self,p):
        cell = (math.floor(p[0]/64),math.floor(p[1]/64))
        if cell in self.land_cells:
            return self.land_cells[cell]
        result = any(bb[0] <= p[0] <= bb[2] and bb[1] <= p[1] <= bb[3] and _in_shape(p,s)
                     for bb,s in zip(self.land_boxes,self.land))
        cell_bounds = (cell[0]*64,cell[1]*64,(cell[0]+1)*64,(cell[1]+1)*64)
        if not self.coast.query(cell_bounds):
            self.land_cells[cell] = result
        return result

    def clear(self, polygon, own):
        """Entire polygon must clear coast, roads and all footprints, including own."""
        bounds = _bbox(polygon,.12)
        if not self.on_land(polygon[0]):
            return False
        # Catch concave coasts and islands/holes fully enclosed by the rectangle.
        for i in self.coast.query(bounds):
            if not _overlaps(bounds,self.coast_boxes[i]):
                continue
            a,b = self.land_edges[i]
            if _inside(a,polygon) or any(_intersects(a,b,c,d) for c,d in _edges(polygon)):
                return False
        for i in self.neighbours.query(bounds):
            if not _overlaps(bounds,self.building_boxes[i]):
                continue
            shape = self.buildings[i]
            if any(_in_shape(p,shape) for p in polygon) or any(_inside(p,polygon) for p in shape[0]):
                return False
            margin = .04 if i == own else .12
            if any(_segment_distance(a,b,c,d) < margin for ring in [shape[0]]+shape[1]
                   for a,b in _edges(ring) for c,d in _edges(polygon)):
                return False
        for i in self.road_grid.query(bounds):
            if not _overlaps(bounds,self.road_boxes[i]):
                continue
            a,b,radius = self.roads[i]
            if _inside(a,polygon) or _inside(b,polygon) or any(_segment_distance(a,b,c,d) < radius for c,d in _edges(polygon)):
                return False
        return True

    def road_score(self, segment):
        q,r = segment
        p = ((q[0]+r[0])/2,(q[1]+r[1])/2)
        length = math.dist(q,r)
        outward = ((r[1]-q[1])/length,-(r[0]-q[0])/length)
        score = 200
        for i in self.road_grid.query(_bbox((p,),65)):
            a,b,radius = self.roads[i]
            near = _closest(p,a,b)
            delta = (near[0]-p[0],near[1]-p[1])
            score = min(score,math.hypot(*delta)-radius+(45 if sum(delta[j]*outward[j] for j in range(2)) < 0 else 0))
        return score


def _model(b):
    """Keep inference, longest-edge ridge and split wall segments identical to base."""
    outer = _ring(b["outer"])
    holes = [_ring(h) for h in b.get("holes",[])]
    height_given, levels = b.get("height_m"),b.get("levels")
    ground,kind = float(b.get("ground_m",2.0)),str(b.get("kind","")).lower()
    if height_given is not None and float(height_given) > 0:
        height = max(2.5,min(65,float(height_given)))
    else:
        floors = float(levels) if levels is not None and float(levels)>0 else (3 if any(k in kind for k in ("hotel","apart","office")) else 1.5)
        height = max(3,min(45,floors*3.0))
    a,c = max(list(_edges(outer)),key=lambda pair:math.dist(*pair))
    length = math.dist(a,c)
    u = ((c[0]-a[0])/length,(c[1]-a[1])/length)
    v = (-u[1],u[0])
    coords = [p[0]*v[0]+p[1]*v[1] for p in outer]
    mid,half = (min(coords)+max(coords))*.5,(max(coords)-min(coords))*.5
    area = abs(_area(outer))-sum(abs(_area(h)) for h in holes)
    pitched = str(b.get("roof_shape","")).lower() not in ("flat","terrace","dome") and area < 650 and not any(k in kind for k in ("hotel","industrial","commercial")) and half>1
    rise = min(2.2,height*.26,half*.40) if pitched else 0
    def signed(p):
        return p[0]*v[0]+p[1]*v[1]-mid
    def top(p):
        return ground+height-rise*min(1,abs(signed(p))/max(half,.1))
    segments = []
    for index,ring in enumerate([outer]+holes):
        ring = ring if (_area(ring)>0)==(index==0) else list(reversed(ring))
        for a,c in _edges(ring):
            points = [a,c]
            if pitched and signed(a)*signed(c)<-1e-8:
                t = signed(a)/(signed(a)-signed(c))
                points.insert(1,(a[0]+(c[0]-a[0])*t,a[1]+(c[1]-a[1])*t))
            for q,r in zip(points,points[1:]):
                segments.append((q,r,index==0))
    rng = random.Random(str(b.get("id")))
    return dict(outer=outer,holes=holes,ground=ground,height=height,rise=rise,top=top,
                pitched=pitched,segments=segments,area=area,kind=kind,
                wall_color=rng.choice(WALL_PALETTE),roof_color=rng.choice(ROOF_PALETTE))


def _windows(model,q,r):
    length = math.dist(q,r)
    if length <= 4:
        return []
    result = []
    for t in range(2,max(3,int(length)-1),4):
        for floor in range(max(1,min(5,int((model["height"]-model["rise"])/3)))):
            z = model["ground"]+1.0+floor*3
            if z+1.0 < min(model["top"](q),model["top"](r))-.1:
                result.append((t,z,floor))
    return result


class _Geometry:
    def __init__(self):
        self.faces = []
        self.triangles = 0

    def face(self,points,material,color=(1,1,1)):
        if len(points)<3:
            return
        if not all(math.isfinite(v) for p in points for v in p):
            raise ValueError("Non-finite detail vertex")
        self.faces.append((list(points),material,color))
        self.triangles += len(points)-2

    def box(self,center,size,material,color=(1,1,1)):
        v = [tuple(center[i]+sign[i]*size[i]/2 for i in range(3)) for sign in
             [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        for f in [(3,2,1,0),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)]:
            self.face([v[i] for i in f],material,color)


class _Facade:
    def __init__(self,geometry,q,r):
        self.g,self.q,self.r = geometry,q,r
        self.length = math.dist(q,r)
        self.u = ((r[0]-q[0])/self.length,(r[1]-q[1])/self.length)
        self.n = (self.u[1],-self.u[0])  # right of CCW exterior = outward

    def point(self,t,d,z):
        return (self.q[0]+self.u[0]*t+self.n[0]*d,self.q[1]+self.u[1]*t+self.n[1]*d,z)

    def face(self,points,material,color=(1,1,1)):
        self.g.face([self.point(*p) for p in points],material,color)

    def box(self,t,d,z,width,depth,height,material,color=(1,1,1)):
        # Transform an ordinary closed box; determinant(u,n,up) = -1.
        temp = _Geometry()
        temp.box((t,d,z),(width,depth,height),material,color)
        for points,mat,col in temp.faces:
            self.face(list(reversed(points)),mat,col)

    def strip(self,start,end,near,far):
        return [self.point(start,near,0)[:2],self.point(end,near,0)[:2],
                self.point(end,far,0)[:2],self.point(start,far,0)[:2]]


def _window(f,t,z,shutters=True,shutter_color=(.21,.37,.30)):
    """Exactly the base .96 x 1m pane, raised from .025 to .055m; no second grid."""
    x0,x1,y0,y1 = t-.48,t+.48,z,z+1
    # Front border and recessed inner jambs are real 3-D geometry.
    outer = [(x0-.095,y0-.095),(x1+.095,y0-.095),(x1+.095,y1+.095),(x0-.095,y1+.095)]
    inner = [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
    for i in range(4):
        j = (i+1)%4
        f.face([(outer[i][0],.105,outer[i][1]),(outer[j][0],.105,outer[j][1]),
                (inner[j][0],.105,inner[j][1]),(inner[i][0],.105,inner[i][1])],"KWD_Trim")
        f.face([(inner[i][0],.105,inner[i][1]),(inner[j][0],.105,inner[j][1]),
                (inner[j][0],.055,inner[j][1]),(inner[i][0],.055,inner[i][1])],"KWD_Trim")
        f.face([(outer[j][0],.105,outer[j][1]),(outer[i][0],.105,outer[i][1]),
                (outer[i][0],.020,outer[i][1]),(outer[j][0],.020,outer[j][1])],"KWD_Trim")
    f.face([(x0,.055,y0),(x1,.055,y0),(x1,.055,y1),(x0,.055,y1)],"KWD_Glass")
    f.face([(t-.025,.11,y0),(t+.025,.11,y0),(t+.025,.11,y1),(t-.025,.11,y1)],"KWD_Trim")
    f.face([(x0,.11,z+.47),(x1,.11,z+.47),(x1,.11,z+.53),(x0,.11,z+.53)],"KWD_Trim")
    if shutters:
        for side in (-1,1):
            a = t+side*.61
            # Raised-panel shutters read at flight distance without tiny slats.
            f.face([(a-.105,.075,z-.04),(a+.105,.075,z-.04),(a+.105,.075,z+1.04),(a-.105,.075,z+1.04)],"KWD_Shutter",shutter_color)
            f.face([(a-.075,.105,z+.12),(a+.075,.105,z+.12),(a+.075,.105,z+.88),(a-.075,.105,z+.88)],"KWD_Shutter",tuple(c*.88 for c in shutter_color))


def _door(f,t,ground):
    f.box(t,.085,ground+1.12,1.05,.13,2.24,"KWD_Trim")
    f.face([(t-.43,.16,ground+.08),(t+.43,.16,ground+.08),(t+.43,.16,ground+2.1),(t-.43,.16,ground+2.1)],"KWD_Door")
    for z in (.55,1.48):
        f.box(t,.18,ground+z,.60,.06,.62,"KWD_Door",(.85,.92,.84))
    f.box(t+.30,.225,ground+1.05,.07,.08,.10,"KWD_Metal")


def _porch(f,center,width,ground,balcony=False):
    z = ground+(.25 if not balcony else 3.15)
    f.box(center,.90,z,width,1.80,.22,"KWD_Trim")
    # A restrained metal roof, broad fascia, and square posts create readable depth.
    f.box(center,.93,z+2.55,width+.24,1.96,.16,"KWD_Roof",(.85,.80,.66))
    for t in (center-width/2+.12,center+width/2-.12):
        f.box(t,1.62,z+1.28,.14,.14,2.5,"KWD_Trim")
        f.box(t,1.62,z+.22,.23,.23,.35,"KWD_Trim")
    if not balcony:
        f.box(center,2.02,ground+.10,width*.58,.55,.20,"KWD_Trim")
    # Leave the centre entrance open; railings span only the two side wings.
    for side in (-1,1):
        start,end = center+side*.65,center+side*(width/2-.1)
        if abs(end-start)<.3:
            continue
        f.box((start+end)/2,1.69,z+.95,abs(end-start),.09,.10,"KWD_Trim")
        for k in range(max(2,int(abs(end-start)/.45)+1)):
            t = start+(end-start)*k/max(1,int(abs(end-start)/.45))
            f.box(t,1.69,z+.49,.065,.065,.85,"KWD_Trim")


def _roof_edges(g,model,safety,own,counts):
    top = model["top"]
    for q,r,exterior in model["segments"]:
        if not exterior or math.dist(q,r)<1.2:
            continue
        f = _Facade(g,q,r)
        # Open-backed bands: no concealed triangles under the preserved roof.
        if not safety.clear(f.strip(.08,f.length-.08,.07,.32),own):
            continue
        zq,zr = top(q),top(r)
        if model["pitched"]:
            f.face([(0,.30,zq+.045),(f.length,.30,zr+.045),(f.length,0,zr+.045),(0,0,zq+.045)],"KWD_Roof",model["roof_color"])
            f.face([(0,.30,zq-.20),(f.length,.30,zr-.20),(f.length,.30,zr+.045),(0,.30,zq+.045)],"KWD_Trim")
            f.face([(f.length,0,zr-.20),(f.length,.30,zr-.20),(0,.30,zq-.20),(0,0,zq-.20)],"KWD_Trim")
        else:
            # Flat commercial roofs get a genuine raised parapet/coping silhouette.
            f.face([(0,.08,zq),(f.length,.08,zr),(f.length,.08,zr+.40),(0,.08,zq+.40)],"KWD_Wall",model["wall_color"])
            f.face([(f.length,-.11,zr),(0,-.11,zq),(0,-.11,zq+.40),(f.length,-.11,zr+.40)],"KWD_Wall",model["wall_color"])
            f.face([(0,-.14,zq+.41),(0,.12,zq+.41),(f.length,.12,zr+.41),(f.length,-.14,zr+.41)],"KWD_Trim")
        counts["roof_edge_segments"] += 1


def _details(building,model,safety,own):
    g,counts = _Geometry(),Counter()
    anchor = None
    _roof_edges(g,model,safety,own,counts)
    candidates = [(q,r) for q,r,outside in model["segments"] if outside and math.dist(q,r)>4]
    candidates.sort(key=lambda qr:(safety.road_score(qr),-math.dist(*qr),qr))
    stable = int(hashlib.sha256(str(building.get("id")).encode()).hexdigest()[:12],16)
    for q,r in candidates:
        f = _Facade(g,q,r)
        # Current grid keeps full frames/shutters inside this guard tangentially.
        # Their 2cm wall attachment is within its existing 4cm own-wall setback.
        if not safety.clear(f.strip(.75,f.length-.75,.055,.17),own):
            continue
        # A raised skirt and its top lip give contact/shadow without a new shell.
        if safety.clear(f.strip(.20,f.length-.20,.055,.08),own):
            f.face([(.20,.06,model["ground"]+.02),(f.length-.20,.06,model["ground"]+.02),
                    (f.length-.20,.06,model["ground"]+.29),(.20,.06,model["ground"]+.29)],"KWD_Trim")
            f.face([(.20,.06,model["ground"]+.29),(f.length-.20,.06,model["ground"]+.29),
                    (f.length-.20,0,model["ground"]+.29),(.20,0,model["ground"]+.29)],"KWD_Trim")
            counts["foundation_skirts"] += 1
        windows = _windows(model,q,r)
        # Six exact panes per frontage; ground floor first, spread on long walls.
        selected = sorted(windows,key=lambda w:(w[2],abs(w[0]-f.length/2),w[0]))[:6]
        for t,z,floor in selected:
            shutter_color = ((.21,.37,.30),(.60,.66,.65),(1,1,1))[stable%3]
            _window(f,t,z,shutters=model["pitched"] and model["area"]<420,shutter_color=shutter_color)
            counts["framed_windows"] += 1
        door_candidates = [f.length/2]+[t+2 for t,z,floor in windows if floor==0]
        door = next((t for t in door_candidates if 1.3<t<f.length-1.3 and
                     all(abs(t-w[0])>1.10 for w in windows if w[2]==0)),None)
        if door is not None and min(model["top"](q),model["top"](r))>model["ground"]+2.6:
            _door(f,door,model["ground"])
            counts["doors"] += 1
            if safety.clear(f.strip(door-.69,door+.69,.07,.90),own):
                f.box(door,.46,model["ground"]+.08,1.30,.86,.16,"KWD_Trim")
                counts["entrance_steps"] += 1
        if door is not None and model["pitched"] and model["area"]<360 and stable%7==0:
            width = min(5.3,2*min(door-.5,f.length-door-.5))
            safe = width>=2.8 and safety.clear(f.strip(door-width/2-.15,door+width/2+.15,.07,2.38),own)
            if safe and min(model["top"](q),model["top"](r))>model["ground"]+3.15:
                _porch(f,door,width,model["ground"])
                counts["porches"] += 1
                if model["height"]-model["rise"]>6.6 and stable%3==0:
                    _porch(f,door,width,model["ground"],True)
                    counts["balconies"] += 1
            else:
                counts["unsafe_porches_skipped"] += 1
        elif not model["pitched"] and f.length>7 and stable%3==0:
            center,width = f.length/2,min(6.5,f.length-2)
            if safety.clear(f.strip(center-width/2,center+width/2,.07,1.22),own):
                z = model["ground"]+2.60
                f.face([(center-width/2,1.16,z),(center+width/2,1.16,z),(center+width/2,.10,z+.28),(center-width/2,.10,z+.28)],"KWD_Shutter",(.28,.43,.34))
                f.face([(center-width/2,1.16,z-.18),(center+width/2,1.16,z-.18),(center+width/2,1.16,z),(center-width/2,1.16,z)],"KWD_Trim")
                counts["awnings"] += 1
        counts["frontages"] += 1
        anchor = dict(building_id=str(building.get("id")),zone=str(building.get("zone","unknown")),
                      facade_center_m=list(f.point(f.length/2,0,model["ground"])),
                      outward_ne=list(f.n),facade_width_m=f.length,height_m=model["height"],
                      legacy_frontage_panes=len(windows),framed_frontage_complete=len(selected)==len(windows),
                      framed_pane_grid=[list(pane) for pane in selected],
                      door_center_m=list(f.point(door,0,model["ground"])) if door is not None else None,
                      features=dict(counts),source="inferred street-facing treatment on actual OSM footprint")
        break
    # Equipment sits wholly inside a flat roof, never over a courtyard.
    if not model["pitched"] and model["area"]>100 and stable%4==0:
        c = tuple(sum(p[i] for p in model["outer"])/len(model["outer"]) for i in range(2))
        footprint = [(c[0]+a,c[1]+b) for a,b in ((-1.1,-.7),(1.1,-.7),(1.1,.7),(-1.1,.7))]
        shape = (model["outer"],model["holes"])
        if all(_in_shape(p,shape) for p in footprint) and not any(_inside(h[0],footprint) for h in shape[1]) and not any(_intersects(a,b,q,r) for ring in [shape[0]]+shape[1] for a,b in _edges(ring) for q,r in _edges(footprint)):
            z = model["ground"]+model["height"]
            g.box((c[0],c[1],z+.36),(2.2,1.4,.72),"KWD_Metal")
            g.box((c[0],c[1],z+.76),(2.28,1.48,.10),"KWD_Trim")
            counts["roof_equipment"] += 1
    return g,counts,anchor


def build(scene, Batch, export):
    """Export separate 256m detail overlays; baseline meshes remain untouched."""
    if scene.get("axes") != {"x":"north","y":"east","z":"up"} or scene.get("units") not in ("metres","meters"):
        raise ValueError("Architecture requires the pinned metre/NEU scene contract")
    safety = _Safety(scene)
    tiles,totals,zones = {},Counter(),Counter()
    anchors = []
    # Hash order distributes the hard geometry budget across all districts.
    order = sorted(range(len(scene["buildings"])),key=lambda i:hashlib.sha256(str(scene["buildings"][i].get("id")).encode()).digest())
    for i in order:
        building = scene["buildings"][i]
        model = _model(building)
        geo,counts,anchor = _details(building,model,safety,i)
        if not geo.faces:
            totals["buildings_without_safe_details"] += 1
            continue
        if totals["triangles"]+geo.triangles > MAX_TRIANGLES:
            totals["buildings_skipped_triangle_budget"] += 1
            continue
        center = tuple(sum(p[j] for p in model["outer"])/len(model["outer"]) for j in range(2))
        tile = tuple(math.floor(v/TILE_SIZE) for v in center)
        if tile not in tiles:
            tiles[tile] = (Batch(),Counter())
        batch,tile_stats = tiles[tile]
        for points,material,color in geo.faces:
            batch.face([(p[0]-tile[0]*TILE_SIZE,p[1]-tile[1]*TILE_SIZE,p[2]) for p in points],material,color)
        totals.update(counts)
        totals["triangles"] += geo.triangles
        totals["buildings_detailed"] += 1
        tile_stats["triangles"] += geo.triangles
        tile_stats["buildings"] += 1
        zones[str(building.get("zone","unknown"))] += 1
        if anchor is not None and counts["doors"] and counts["framed_windows"]>=2:
            anchors.append(anchor)
    for (n,e),(batch,tile_stats) in sorted(tiles.items()):
        label = lambda value:("p" if value>=0 else "m")+f"{abs(value):03d}"
        export(f"KWD_Architecture_N{label(n)}_E{label(e)}",batch,
               position=(n*TILE_SIZE,e*TILE_SIZE,0),collision=False,derived=True,
               role="architecture_detail",metadata={"cull_distance_m":CULL_DISTANCE_M,
               "tile_size_m":TILE_SIZE,"detail_statistics":dict(tile_stats),
               "detail_lod_policy":"preserve_architectural_detail",
               "provenance_detail":"Original procedural mouldings and inferred treatments placed on OSM-derived footprints; retain ODbL geographic attribution"})
    anchors.sort(key=lambda a:(not a["framed_frontage_complete"],-a["features"].get("porches",0),-a["features"].get("balconies",0),
                               -a["features"].get("roof_edge_segments",0),a["building_id"]))
    return dict(schema=1,**dict(totals),tiles=len(tiles),zone_buildings=dict(zones),review_anchors=anchors[:12],
                triangle_budget=MAX_TRIANGLES,cull_distance_m=CULL_DISTANCE_M,
                placement_policy="Conservative whole-polygon coast/road/neighbour rejection; unsafe external features omitted",
                inferred_art="Roof-edge profiles, facade/front-door selection, shutters, porches/balconies and equipment are modeled, not surveyed")


def _pane_projection_bounds(shutters):
    """Verification uses the generated vertices, not a second size definition."""
    geometry = _Geometry()
    _window(_Facade(geometry,(0,0),(20,0)),0,0,shutters=shutters)
    vertices = [p for points,material,color in geometry.faces for p in points]
    return (min(p[0] for p in vertices),max(p[0] for p in vertices),
            min(-p[1] for p in vertices),max(-p[1] for p in vertices))


def _guard_coverage(length,t,bounds):
    tangential = min(t+bounds[0]-.75,length-.75-(t+bounds[1]))
    normal_gap = max(0,.055-bounds[2],bounds[3]-.17)
    assert tangential >= -EPS, "Generated pane extends beyond frontage guard"
    # Both .04m own-wall and .12m neighbour setbacks cover the .035m frame back.
    assert normal_gap < .04-EPS, "Wall attachment exceeds existing clearance"
    return tangential,normal_gap


def self_test():
    rect = [(0,0),(12,0),(12,8),(0,8)]
    b = dict(id="test-house",outer=rect,holes=[],height_m=7,ground_m=2,roof_shape="gable",kind="house",zone="old_town")
    model = _model(b)
    assert model["height"]==7 and abs(model["rise"]-1.6)<1e-8
    assert model["top"]((6,4))==9 and abs(model["top"]((6,0))-7.4)<1e-8
    # Ridge split: end walls are split at the same y=4 point as the base.
    assert len(model["segments"])==6
    q,r = model["segments"][0][:2]
    assert _windows(model,q,r)==[(2,3.0,0),(6,3.0,0),(10,3.0,0)]
    reverse = _model(dict(b,outer=list(reversed(rect))))
    assert sorted((tuple(q),tuple(r)) for q,r,_ in model["segments"])==sorted((tuple(q),tuple(r)) for q,r,_ in reverse["segments"])
    f = _Facade(_Geometry(),q,r)
    assert not _inside(f.point(6,.1,0)[:2],rect)
    _window(f,2,3)
    panes = [points for points,mat,col in f.g.faces if mat=="KWD_Glass"]
    assert len(panes)==1 and all(abs((p[0]-q[0])*f.n[0]+(p[1]-q[1])*f.n[1]-.055)<1e-8 for p in panes[0])
    assert sorted(round(math.dist(panes[0][j],panes[0][(j+1)%4]),6) for j in range(4))==[.96,.96,1,1]
    land = dict(outer=[(-10,-10),(30,-10),(30,30),(-10,30)],holes=[])
    scene = dict(units="metres",axes=dict(x="north",y="east",z="up"),buildings=[b],land_polygons=[land],roads=[],piers=[],runways=[])
    safety = _Safety(scene)
    roof_geometry = _Geometry()
    _roof_edges(roof_geometry,model,safety,0,Counter())
    for points,material,color in roof_geometry.faces:
        if material=="KWD_Roof":
            assert _cross(points[0],points[1],points[2]) > 0, "Eave roof must face up"
    assert safety.clear([(1,-2),(5,-2),(5,-.1),(1,-.1)],0)
    assert not safety.clear([(1,-2),(5,-2),(5,1),(1,1)],0)
    assert not safety.clear([(1,-12),(5,-12),(5,-10.1),(1,-10.1)],0)
    road_scene = dict(scene,roads=[dict(points=[(-5,-2),(20,-2)],width_m=2)])
    assert not _Safety(road_scene).clear([(1,-3),(5,-3),(5,-.1),(1,-.1)],0)
    neighbour = dict(b,id="neighbour",outer=[(0,-4),(8,-4),(8,-1),(0,-1)])
    assert not _Safety(dict(scene,buildings=[b,neighbour])).clear([(1,-3),(5,-3),(5,-.1),(1,-.1)],0)
    # A cropped frontage guard cannot stand in for an individual pane's extent.
    # Deliberately exercise a pane close to the corner independently of grid spacing.
    corner_house = dict(b,id="corner-house",outer=[(0,0),(7.01,0),(7.01,8),(0,8)],roof_shape="flat",height_m=5.5)
    corner_neighbour = dict(b,id="corner-neighbour",outer=[(6.45,-.04),(10.45,-.04),(10.45,-.01),(6.45,-.01)])
    corner_scene = dict(scene,buildings=[corner_house,corner_neighbour])
    corner_safety = _Safety(corner_scene)
    corner_f = _Facade(_Geometry(),(0,0),(7.01,0))
    assert corner_safety.clear(corner_f.strip(.75,corner_f.length-.75,.055,.17),0)
    _window(corner_f,6,3)
    assert any(_in_shape(p[:2],corner_safety.buildings[1]) for points,mat,col in corner_f.g.faces for p in points)
    try:
        _guard_coverage(7.01,6,_pane_projection_bounds(True))
    except AssertionError:
        pass
    else:
        raise AssertionError("Artificial corner pane unexpectedly meets guard invariant")
    shutter_neighbour = dict(b,id="shutter-neighbour",outer=[(6.70,-.11),(9.70,-.11),(9.70,-.07),(6.70,-.07)])
    shutter_shape = (_ring(shutter_neighbour["outer"]),[])
    assert any(_in_shape(p[:2],shutter_shape) for points,mat,col in corner_f.g.faces for p in points)
    # In current legacy spacing the real 7.01m frontage has t=2 only, not t=6.
    assert _windows(_model(corner_house),(0,0),(7.01,0))==[(2,3.0,0)]
    corner_scene["roads"] = [dict(points=[(-20,-4),(20,-4)],width_m=2)]
    corner_geo,corner_counts,corner_anchor = _details(corner_house,_model(corner_house),_Safety(corner_scene),0)
    assert corner_anchor["framed_pane_grid"]==[[2,3.0,0]] and corner_anchor["framed_frontage_complete"]
    assert corner_counts["framed_windows"]==1
    neighbour_shape = corner_safety.buildings[1]
    assert not any(_in_shape(p[:2],neighbour_shape) for points,mat,col in corner_geo.faces for p in points)
    assert not any(_intersects(a[:2],c[:2],q,r) for points,mat,col in corner_geo.faces
                   for a,c in zip(points,points[1:]+points[:1]) for q,r in _edges(neighbour_shape[0]))
    # Exercise integer endpoints of Python's exclusive-stop range, both sides.
    for shutters in (False,True):
        bounds = _pane_projection_bounds(shutters)
        for integer in range(4,65):
            for length in (integer-1e-6,float(integer),integer+1e-6):
                for t,z,floor in _windows(model,(0,0),(length,0)):
                    _guard_coverage(length,t,bounds)
    # All corners on land is insufficient: this rectangle crosses a concave bay.
    notch = dict(outer=[(-10,-10),(30,-10),(30,30),(4,30),(4,-1),(3,-1),(3,30),(-10,30)],holes=[])
    assert not _Safety(dict(scene,land_polygons=[notch])).clear([(1,-2),(6,-2),(6,1),(1,1)],0)
    courtyard = dict(outer=land["outer"],holes=[[(1,-3),(1,-1),(3,-1),(3,-3)]])
    assert not _Safety(dict(scene,land_polygons=[courtyard])).clear([(0,-4),(4,-4),(4,-.1),(0,-.1)],0)
    class TestBatch:
        def __init__(self): self.faces=[]
        def face(self,points,material,color=(1,1,1)): self.faces.append((points,material,color))
    def run():
        exports=[]
        stats=build(scene,TestBatch,lambda name,batch,**kw:exports.append((name,batch.faces,kw)))
        return stats,exports
    a,first=run()
    c,second=run()
    assert a==c and first==second and a["triangles"]>0 and a["triangles"]<=MAX_TRIANGLES
    assert first[0][2]["collision"] is False and first[0][2]["role"]=="architecture_detail"
    assert all(len(anchor["framed_pane_grid"])==anchor["features"]["framed_windows"] for anchor in a["review_anchors"])
    assert not _intersects((0,0),(1,0),(2,0),(3,0)) and _intersects((0,0),(2,2),(0,2),(2,0))
    print("PASS: exact gable/ridge/window grid, full generated pane/attachment guard coverage, actual near-corner details, coast/road/neighbour rejection, deterministic bounded exports")


def check_scene(path):
    """Read-only CPU validation of the real scene; never creates asset files."""
    import json
    import time
    from pathlib import Path
    class CheckedBatch:
        def __init__(self):
            self.triangles = 0
        def face(self,points,material,color=(1,1,1)):
            if material not in MATERIALS or not all(math.isfinite(v) for p in points for v in p):
                raise AssertionError("Invalid material or coordinate")
            normal = [sum((a[(k+1)%3]-b[(k+1)%3])*(a[(k+2)%3]+b[(k+2)%3])
                          for a,b in zip(points,points[1:]+points[:1])) for k in range(3)]
            if sum(x*x for x in normal)<1e-14:
                raise AssertionError("Degenerate detail face")
            self.triangles += len(points)-2
    costs = []
    def export(name,batch,**kw):
        assert not kw["collision"] and kw["derived"] and kw["role"]=="architecture_detail"
        reserved = {"name","pivot","materials","collision","foliage","triangles","bounds_m","dimensions_m","role","provenance","lod_policy"}
        assert not reserved.intersection(kw["metadata"]), "Base export metadata key collision"
        costs.append(batch.triangles)
    start = time.perf_counter()
    scene = json.loads(Path(path).read_text(encoding="utf-8"))
    stats = build(scene,CheckedBatch,export)
    assert sum(costs)==stats["triangles"]<=MAX_TRIANGLES
    print(json.dumps(dict(result="PASS",check="real-scene finite/nondegenerate geometry, materials, tile/export contract and budget",
                          seconds=round(time.perf_counter()-start,3),max_tile_triangles=max(costs,default=0),statistics=stats)),flush=True)


def check_window_guards(path):
    """Cheap read-only proof of guard coverage for every real legacy pane."""
    import json
    from pathlib import Path
    scene = json.loads(Path(path).read_text(encoding="utf-8"))
    bounds = {value:_pane_projection_bounds(value) for value in (False,True)}
    minimum,maximum,count = float("inf"),0,0
    for building in scene["buildings"]:
        model = _model(building)
        shutters = model["pitched"] and model["area"]<420
        for q,r,exterior in model["segments"]:
            for t,z,floor in _windows(model,q,r):
                tangential,normal = _guard_coverage(math.dist(q,r),t,bounds[shutters])
                minimum,maximum = min(minimum,tangential),max(maximum,normal)
                count += 1
    print(json.dumps(dict(result="PASS",buildings=len(scene["buildings"]),panes=count,
                          minimum_tangential_guard_margin_m=minimum if count else None,
                          maximum_attachment_gap_m=maximum,
                          own_wall_clearance_m=.04,neighbour_clearance_m=.12,
                          check="Actual generated frame/shutter bounds covered by current grid and footprint setbacks")),flush=True)


if __name__=="__main__":
    if sys.argv[1:]==["--self-test"]:
        self_test()
    elif len(sys.argv)==3 and sys.argv[1]=="--check-scene":
        check_scene(sys.argv[2])
    elif len(sys.argv)==3 and sys.argv[1]=="--check-window-guards":
        check_window_guards(sys.argv[2])
    else:
        raise SystemExit("Import build(scene, Batch, export), or use --self-test / --check-scene PATH / --check-window-guards PATH")
