"""Original waterline-centered boats and deterministic, conservative wet berths.

Blender integration: MATERIALS; make_models(Batch, export). No Shapely/Blender
imports at module load. Placement CLI runs outside Blender using Shapely:
python KeyWestBoats.py --scene scene.json --output fleet.json
All craft are anchored: no translating routes, wakes or navigation claims.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random


MATERIALS = {
    'KWB_Gelcoat': {'color': [.78, .82, .80], 'roughness': .29},
    'KWB_Blue': {'color': [.035, .13, .22], 'roughness': .31},
    'KWB_Teal': {'color': [.08, .31, .29], 'roughness': .36},
    'KWB_Antifoul': {'color': [.065, .085, .105], 'roughness': .68},
    'KWB_Deck': {'color': [.63, .66, .61], 'roughness': .74},
    'KWB_Teak': {'color': [.32, .21, .105], 'roughness': .63},
    'KWB_Metal': {'color': [.58, .62, .64], 'roughness': .25, 'metallic': .88},
    'KWB_Glass': {'color': [.025, .07, .095], 'roughness': .15, 'opaque': True},
    'KWB_Rubber': {'color': [.018, .022, .025], 'roughness': .73},
    'KWB_Canvas': {'color': [.68, .73, .70], 'roughness': .83},
    'KWB_Seat': {'color': [.72, .68, .55], 'roughness': .62},
    'KWB_Orange': {'color': [.83, .17, .035], 'roughness': .58},
}
SEED = 20261031
BOUND = 4400.0
CLEARANCE = {'coast_m': 4.0, 'pier_m': 1.8, 'bridge_m': 12.0, 'between_boats_m': 8.0}
SPECS = [
    ('KWB_CenterConsole', 'center_console_fishing', 8.6, 2.85, .58, .62, 1.45),
    ('KWB_Sportfisher', 'sportfisher', 13.4, 4.25, .82, .90, 1.65),
    ('KWB_WorkFishing', 'working_fishing_lobster', 12.0, 4.1, .85, .82, 2.0),
    ('KWB_Sailboat', 'sailboat_furled', 11.8, 3.65, .86, .65, 2.45),
    ('KWB_MotorCruiser', 'motor_cruiser', 14.2, 4.35, .85, .91, 1.7),
    ('KWB_Skiff', 'recreational_skiff', 6.2, 2.15, .42, .43, 1.5),
]


def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def unit(v):
    length = math.sqrt(dot(v, v))
    if length < 1e-9: raise ValueError('Degenerate geometric direction')
    return tuple(x/length for x in v)


def _solid(batch, points, thickness, material):
    """A closed thin panel, never a one-sided glass/sail polygon."""
    normal = unit(cross(sub(points[1], points[0]), sub(points[2], points[0])))
    low = [tuple(p[i]-normal[i]*thickness/2 for i in range(3)) for p in points]
    high = [tuple(p[i]+normal[i]*thickness/2 for i in range(3)) for p in points]
    batch.face(list(reversed(low)), material); batch.face(high, material)
    for j in range(len(points)):
        k = (j+1) % len(points)
        batch.face([low[j], low[k], high[k], high[j]], material)


def _bevel_box(batch, center, size, material, bevel=.08):
    x, y, z = center; a, b, c = [v/2 for v in size]
    bevel = min(bevel, a*.35, b*.35, c*.35)
    rings = []
    for dz, inset in [(-c, bevel), (-c+bevel, 0), (c-bevel, 0), (c, bevel)]:
        aa, bb = a-inset, b-inset
        ring = []
        for cx, cy, angle in [(aa-bevel, bb-bevel, 0), (-aa+bevel, bb-bevel, 90),
                              (-aa+bevel, -bb+bevel, 180), (aa-bevel, -bb+bevel, 270)]:
            for j in range(4):
                t = math.radians(angle+j*30)
                ring.append((x+cx+bevel*math.cos(t), y+cy+bevel*math.sin(t), z+dz))
        rings.append(ring)
    batch.face(list(reversed(rings[0])), material); batch.face(rings[-1], material)
    for lower, upper in zip(rings, rings[1:]):
        for j in range(len(lower)):
            k = (j+1) % len(lower)
            batch.face([lower[j], lower[k], upper[k], upper[j]], material)


def _section(length, beam, draft, freeboard, power, t, sides=32):
    width = beam*.5*(.84+.16*math.sin(math.pi*t))*(1-.985*t**4.2)
    sheer = freeboard + .24*t**3
    depth = draft*(.78+.22*math.sin(math.pi*t))*(1-.78*t**5)
    result = []
    for j in range(sides+1):
        angle = math.pi*j/sides
        u = math.cos(angle)
        x = length*(t-.48)-length*.075*t**6*(1-abs(u))
        result.append((x, width*u, -depth+(sheer+depth)*abs(u)**power))
    return result


def _hull(batch, length, beam, draft, freeboard, power, material):
    """Closed 40-station, 32-section loft with raked stem and true transom."""
    rings = [_section(length, beam, draft, freeboard, power, i/40) for i in range(41)]
    for lower, upper in zip(rings, rings[1:]):
        for j in range(len(lower)):
            k = (j+1) % len(lower)
            points = [lower[j], upper[j], upper[k], lower[k]]
            mat = 'KWB_Deck' if j == len(lower)-1 else 'KWB_Antifoul' if sum(p[2] for p in points)/4 < -.12 else material
            batch.face(points, mat)
    for ring, reverse in [(rings[0], False), (rings[-1], True)]:
        center = tuple(sum(p[i] for p in ring)/len(ring) for i in range(3))
        points = list(reversed(ring)) if reverse else ring
        for j in range(len(points)):
            batch.face([center, points[j], points[(j+1) % len(points)]], material)
    return rings


def _gunwales(batch, rings, rail=True):
    for side in (0, -1):
        line = [(r[side][0], r[side][1], r[side][2]+.045) for r in rings]
        # A flat fiberglass cap follows the sheer; it is not an oversized pipe.
        rims=[]
        for x,y,z in line:
            inside=y-math.copysign(min(.13,abs(y)*.45),y)
            ring=[(x,y,z+.035),(x,inside,z+.035),(x,inside,z-.025),(x,y,z-.025)]
            rims.append(list(reversed(ring)) if y>0 else ring)
        batch.face(rims[0],'KWB_Gelcoat');batch.face(list(reversed(rims[-1])),'KWB_Gelcoat')
        for a,b in zip(rims,rims[1:]):
            for j in range(4):
                k=(j+1)%4;batch.face([a[j],b[j],b[k],a[k]],'KWB_Gelcoat')
        if rail:
            top = [(p[0], p[1], p[2]+.53) for p in line[14:]]
            for a, b in zip(top, top[1:]): batch.rod(a, b, .018, 'KWB_Metal', sides=6)
            for j in range(14, len(line), 5):
                a = line[j]; batch.rod(a, (a[0], a[1], a[2]+.53), .018, 'KWB_Metal', sides=6)


def _outboard(batch, x, y, z, scale=1):
    _bevel_box(batch, (x, y, z+.42*scale), (.68*scale, .48*scale, .82*scale), 'KWB_Rubber', .12*scale)
    batch.box((x+.27*scale, y, z), (.3*scale, .38*scale, .2*scale), 'KWB_Metal')
    batch.rod((x, y, z+.15*scale), (x-.12*scale, y, z-.70*scale), .095*scale, 'KWB_Rubber', sides=10, tip=.06*scale)
    batch.rod((x-.05*scale, y, z-.64*scale), (x-.36*scale, y, z-.64*scale), .065*scale, 'KWB_Metal', sides=10)
    for angle in (0, 120, 240):
        t=math.radians(angle); a=(x-.3*scale,y,z-.64*scale)
        b=(a[0],a[1]+.20*scale*math.cos(t),a[2]+.20*scale*math.sin(t))
        batch.rod(a,b,.033*scale,'KWB_Metal',sides=6,tip=.012*scale)


def _seats(batch, x, y, z, count=1):
    for j in range(count):
        yy=y+(j-(count-1)/2)*.58
        batch.rod((x,yy,z),(x,yy,z+.37),.045,'KWB_Metal',sides=8)
        _bevel_box(batch,(x,yy,z+.43),(.52,.49,.14),'KWB_Seat',.04)
        _bevel_box(batch,(x-.22,yy,z+.70),(.11,.48,.45),'KWB_Seat',.04)


def _console(batch, x, z, width=.8):
    _bevel_box(batch,(x,0,z+.48),(.85,width,.96),'KWB_Gelcoat',.10)
    _solid(batch,[(x+.36,-width*.43,z+.84),(x+.36,width*.43,z+.84),
                  (x+.21,width*.43,z+1.37),(x+.21,-width*.43,z+1.37)],.035,'KWB_Glass')
    batch.box((x-.45,-.16,z+.8),(.045,.27,.18),'KWB_Glass')
    # Steering wheel is a ring of closed rod segments, plus spokes.
    wheel=[(x-.47,.18+.18*math.cos(t*math.tau/16),z+.83+.18*math.sin(t*math.tau/16)) for t in range(16)]
    for a,b in zip(wheel,wheel[1:]+wheel[:1]):batch.rod(a,b,.014,'KWB_Metal',sides=6)
    for j in (0,5,10):batch.rod((x-.47,.18,z+.83),wheel[j],.012,'KWB_Metal',sides=6)


def _canopy(batch, x, z, length, beam, material='KWB_Canvas'):
    for xx in (x-length*.32,x+length*.32):
        for yy in (-beam*.40,beam*.40):batch.rod((xx,yy,z-1.55),(xx,yy,z-.05),.025,'KWB_Metal',sides=8)
    _bevel_box(batch,(x,0,z),(length,beam,.13),material,.05)


def _cabin(batch, x0, x1, width, z, height):
    profile=[(x0,z),(x1,z),(x1,z+height*.48),(x1-.42,z+height*.90),
             (x0+.25,z+height),(x0,z+height*.83)]
    port=[(x,-width/2,zz) for x,zz in profile]; star=[(x,width/2,zz) for x,zz in profile]
    batch.face(port,'KWB_Gelcoat');batch.face(list(reversed(star)),'KWB_Gelcoat')
    for j in range(len(port)):
        k=(j+1)%len(port);batch.face([port[j],star[j],star[k],port[k]],'KWB_Gelcoat')
    for side in (-1,1):
        y=side*(width/2+.02)
        _solid(batch,[(x0+.23,y,z+.38*height),(x1-.47,y,z+.38*height),
                      (x1-.60,y,z+.79*height),(x0+.28,y,z+.83*height)],.025,'KWB_Glass')
        for x in (x0+.27,(x0+x1)/2,x1-.53):
            batch.rod((x,y+side*.02,z+.36*height),(x,y+side*.02,z+.82*height),.023,'KWB_Gelcoat',sides=6)
    _solid(batch,[(x1+.02,-width*.43,z+height*.50),(x1+.02,width*.43,z+height*.50),
                  (x1-.39,width*.43,z+height*.87),(x1-.39,-width*.43,z+height*.87)],.03,'KWB_Glass')
    batch.rod((x1+.05,0,z+height*.49),(x1-.38,0,z+height*.89),.025,'KWB_Gelcoat',sides=6)
    batch.box((x0-.015,-width*.20,z+.60),(.035,.52,1.15),'KWB_Teak')
    batch.box((x0-.04,-width*.20,z+.87),(.025,.37,.36),'KWB_Glass')


def _fittings(batch, length, beam, z, fishing=False):
    for x in (-length*.31,length*.30):
        for side in (-1,1):
            y=side*beam*.42
            batch.rod((x-.12,y,z+.12),(x+.12,y,z+.12),.025,'KWB_Metal',sides=8)
            batch.rod((x,y,z+.02),(x,y,z+.13),.025,'KWB_Metal',sides=8)
    for side in (-1,1):
        batch.rod((-length*.05,side*beam*.49,z+.18),(-length*.05,side*beam*.49,z-.30),.11,'KWB_Rubber',sides=10)
        if fishing:
            for j in range(2):
                a=(-length*.28+j*.43,side*beam*.34,z+.20)
                b=(a[0]-1.2,side*(beam*.42+.55),z+2.6+j*.14)
                batch.rod(a,b,.018,'KWB_Rubber',sides=6,tip=.006)
                batch.rod(a,(a[0]-.10,a[1],a[2]+.40),.035,'KWB_Metal',sides=8)
    # Stern boarding ladder.
    for y in (-.30,.30):batch.rod((-length*.49,y,z-.40),(-length*.49,y,z+.23),.025,'KWB_Metal',sides=6)
    for level in (-.25,0,.20):batch.rod((-length*.49,-.30,z+level),(-length*.49,.30,z+level),.023,'KWB_Metal',sides=6)


def _trap(batch, center):
    x,y,z=center; a,b,c=.46,.34,.25
    for xx in (x-a,x+a):
        for yy in (y-b,y+b):batch.rod((xx,yy,z-c),(xx,yy,z+c),.025,'KWB_Teak',sides=6)
    for zz in (z-c,z+c):
        for yy in (y-b,y+b):batch.rod((x-a,yy,zz),(x+a,yy,zz),.025,'KWB_Teak',sides=6)
        for xx in (x-a,x+a):batch.rod((xx,y-b,zz),(xx,y+b,zz),.025,'KWB_Teak',sides=6)
    for off in (-.22,0,.22):batch.rod((x+off,y-b,z+c),(x+off,y+b,z+c),.014,'KWB_Teak',sides=6)


def _convex_hull(points):
    # Keep original vertices: rounding inward would understate a rotated hull.
    points=sorted(set((float(p[0]),float(p[1])) for p in points))
    def turn(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower=[];upper=[]
    for p in points:
        while len(lower)>1 and turn(lower[-2],lower[-1],p)<=0:lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper)>1 and turn(upper[-2],upper[-1],p)<=0:upper.pop()
        upper.append(p)
    return [list(p) for p in lower[:-1]+upper[:-1]]


def make_models(Batch, export):
    """Export six original closed assemblies. Return footprint/model records."""
    models=[]
    for name,kind,length,beam,draft,deck,power in SPECS:
        batch=Batch()
        hullmat='KWB_Teal' if 'Work' in name else 'KWB_Blue' if 'Center' in name or 'Skiff' in name else 'KWB_Gelcoat'
        rings=_hull(batch,length,beam,draft,deck,power,hullmat)
        _gunwales(batch,rings,rail='Work' not in name)
        _fittings(batch,length,beam,deck,fishing='Console' in name or 'Sport' in name or 'Work' in name)
        if 'Center' in name:
            _console(batch,.35,deck);_seats(batch,-.65,0,deck,2);_canopy(batch,.25,deck+2.3,2.6,2.1)
            for y in (-.43,.43):_outboard(batch,-length*.49-.28,y,deck-.38,.85)
            _bevel_box(batch,(length*.25,0,deck+.18),(1.5,1.35,.32),'KWB_Seat')
        elif 'Sport' in name:
            _cabin(batch,-1.4,3.4,beam*.72,deck,1.8)
            _bevel_box(batch,(-.25,0,deck+1.88),(3.8,3.2,.15),'KWB_Gelcoat')
            _console(batch,.05,deck+1.97,1.0);_seats(batch,-.85,0,deck+1.97,2)
            _canopy(batch,-.10,deck+4.0,3.4,3.0,'KWB_Gelcoat')
            for y in (-beam*.43,beam*.43):batch.rod((-.7,y,deck+2.2),(-5.4,y*1.6,deck+4.1),.025,'KWB_Metal',sides=8,tip=.010)
            _bevel_box(batch,(-3.8,0,deck+.18),(1.2,2.5,.30),'KWB_Deck')
        elif 'Work' in name:
            _cabin(batch,.25,3.5,beam*.74,deck,1.9)
            for x in (-3.25,-2.2):
                for y in (-.75,.75):_trap(batch,(x,y,deck+.28))
            batch.rod((-1.3,1.25,deck),(-1.3,1.25,deck+2.8),.075,'KWB_Metal',sides=10)
            batch.rod((-1.3,1.25,deck+2.8),(-2.0,1.90,deck+2.7),.06,'KWB_Metal',sides=8)
            batch.rod((-2.0,1.90,deck+2.7),(-2.0,1.90,deck+.5),.010,'KWB_Rubber',sides=6)
            for y in (-1.45,1.45):_bevel_box(batch,(-.5,y,deck+.28),(.8,.52,.55),'KWB_Orange',.05)
        elif 'Sail' in name:
            _cabin(batch,-2.4,2.4,beam*.60,deck,.80)
            batch.rod((.65,0,deck),(.65,0,13.2),.085,'KWB_Metal',sides=12,tip=.035)
            batch.rod((.65,0,2.30),(-3.8,0,2.30),.055,'KWB_Metal',sides=10)
            # Anchored craft have furled canvas, not full sails under no wind.
            batch.rod((.4,0,2.35),(-3.7,0,2.35),.16,'KWB_Canvas',sides=12,tip=.12)
            for a in [(-4.6,0,deck),(5.5,0,deck+.3),(0,beam*.47,deck),(0,-beam*.47,deck)]:
                batch.rod(a,(.65,0,12.7),.009,'KWB_Metal',sides=6)
            batch.rod((5.5,0,deck+.3),(.65,0,12.7),.05,'KWB_Canvas',sides=8,tip=.035)
            _solid(batch,[(-1.2,0,-.5),(1.0,0,-.5),(.50,0,-1.85),(-.65,0,-1.85)],.22,'KWB_Antifoul')
            _bevel_box(batch,(-3.45,0,deck+.26),(1.2,1.55,.45),'KWB_Teak')
        elif 'Cruiser' in name:
            _cabin(batch,-2.9,3.6,beam*.73,deck,1.65)
            _bevel_box(batch,(-1.05,0,deck+1.76),(3.8,3.1,.20),'KWB_Gelcoat')
            _console(batch,-.35,deck+1.90,1.1);_seats(batch,-1.4,0,deck+1.90,2)
            _canopy(batch,-.9,deck+3.9,3.6,3.2,'KWB_Canvas')
            _bevel_box(batch,(3.95,0,deck+.20),(1.55,2.0,.30),'KWB_Seat')
            _bevel_box(batch,(-5.7,0,deck-.08),(1.2,3.0,.12),'KWB_Teak')
        else:
            _outboard(batch,-length*.49-.22,0,deck-.20,.70)
            for x in (-1.2,.45):_bevel_box(batch,(x,0,deck+.20),(.55,1.5,.25),'KWB_Seat',.06)
            _console(batch,-.35,deck,.62)
        vertices=batch.vertices
        bounds=[[min(p[i] for p in vertices) for i in range(3)], [max(p[i] for p in vertices) for i in range(3)]]
        footprint=_convex_hull(vertices)
        triangles=sum(len(f)-2 for f in batch.faces)
        metadata={'boat_type':kind,'waterline_m':0,'footprint_local_m':footprint,
                  'hull_dimensions_m':[length,beam,draft+deck], 'fleet_state':'anchored',
                  'hull_construction':'40-station raked-stem/chine loft with closed transom/deck',
                  'source_art':'Original procedural boat geometry; no external boat model'}
        export(name,batch,collision=False,role='boat',metadata=metadata)
        models.append(dict(asset=name,boat_type=kind,bounds_m=bounds,footprint_local_m=footprint,
                           triangles=triangles,waterline_m=0,dimensions_m=[bounds[1][i]-bounds[0][i] for i in range(3)]))
    return models


class _TestBatch:
    """Pure recorder matching the integration Batch API, with closed rod caps."""
    def __init__(self):self.vertices=[];self.faces=[];self.slots=[]
    def face(self,points,material,color=(1,1,1)):
        if material not in MATERIALS:raise ValueError('Undeclared boat material '+material)
        start=len(self.vertices);self.vertices.extend(tuple(p) for p in points)
        self.faces.append(tuple(range(start,start+len(points))));self.slots.append(material)
    def box(self,center,size,material,color=(1,1,1)):
        x,y,z=center;a,b,c=[v/2 for v in size]
        vs=[(x+sx*a,y+sy*b,z+sz*c) for sx,sy,sz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        for f in [(3,2,1,0),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)]:self.face([vs[i] for i in f],material)
    def rod(self,a,b,radius,material,sides=8,tip=None):
        axis=unit(sub(b,a));u=cross(axis,(0,0,1))
        if dot(u,u)<.0001:u=cross(axis,(0,1,0))
        u=unit(u);v=cross(axis,u);tip=radius if tip is None else tip
        rings=[]
        for center,r in [(a,radius),(b,tip)]:
            rings.append([tuple(center[k]+r*(u[k]*math.cos(j*math.tau/sides)+v[k]*math.sin(j*math.tau/sides)) for k in range(3)) for j in range(sides)])
        self.face(list(reversed(rings[0])),material);self.face(rings[1],material)
        for j in range(sides):
            k=(j+1)%sides;self.face([rings[0][j],rings[0][k],rings[1][k],rings[1][j]],material)


def _world_footprint(model, record):
    from shapely.geometry import Polygon
    angle=math.radians(record['yaw_deg']);c,s=math.cos(angle),math.sin(angle)
    n,e,_=record['position_m'];sx,sy,_=record['scale']
    return Polygon([(n+c*x*sx-s*y*sy,e+s*x*sx+c*y*sy) for x,y in model['footprint_local_m']])


def _obstacles(scene):
    """Shapely is deliberately lazy: this is an outside-Blender operation."""
    from shapely.geometry import Polygon,LineString,box
    from shapely.ops import unary_union
    from shapely.prepared import prep
    if (scene.get('schema')!=1 or scene.get('units') not in ('metres','meters') or
            scene.get('axes')!={'x':'north','y':'east','z':'up'} or scene.get('sea_level_m')!=0):
        raise ValueError('Expected the pinned north/east/up, zero-sea geographic contract')
    if any(key not in scene for key in ('land_polygons','piers','roads')):
        raise ValueError('Missing land/pier/road obstacle collections')
    land=[]
    for p in scene['land_polygons']:
        shape=Polygon(p['outer'],p.get('holes',[]))
        if not shape.is_valid or shape.is_empty:raise ValueError('Invalid source land; cannot infer safe water')
        land.append(shape)
    if not land:raise ValueError('Missing real coastline; no water fallback')
    pier_shapes=[];bridge_shapes=[]
    for key,collection,extra in [('piers',pier_shapes,CLEARANCE['pier_m']),('roads',bridge_shapes,CLEARANCE['bridge_m'])]:
        for line in scene.get(key,[]):
            if key=='roads' and not line.get('bridge'):continue
            pts=line.get('points',[])
            if len(pts)<2:raise ValueError('Invalid pier/bridge source line')
            width=float(line.get('width_m',5))
            if not math.isfinite(width) or width<=0:raise ValueError('Invalid obstacle width')
            collection.append(LineString(pts).buffer(width/2+extra,cap_style=1,join_style=1))
    coast=unary_union(land).buffer(CLEARANCE['coast_m'])
    blocked=unary_union([coast]+pier_shapes+bridge_shapes)
    return {'blocked':blocked,'prepared':prep(blocked),'bounds':box(-BOUND,-BOUND,BOUND,BOUND),
            'coast':coast,'piers':unary_union(pier_shapes),'bridges':unary_union(bridge_shapes),
            'counts':{'land_polygons':len(land),'pier_corridors':len(pier_shapes),'bridge_corridors':len(bridge_shapes)}}


def _reason(shape,obstacles,accepted):
    if not shape.is_valid or shape.is_empty:return 'invalid_hull'
    if not obstacles['bounds'].covers(shape.buffer(CLEARANCE['coast_m'])):return 'bounds'
    if obstacles['prepared'].intersects(shape):return 'land_pier_or_bridge'
    if any(shape.distance(other)<CLEARANCE['between_boats_m'] for other in accepted):return 'separation'
    return None


def validate_fleet(scene,fleet):
    obstacles=_obstacles(scene);models={m['asset']:m for m in fleet['models']};accepted=[]
    expected={m['asset']:m for m in make_models(_TestBatch,lambda *a,**k:None)}
    if models!=expected:raise ValueError('Stale/modified model footprint catalog')
    if fleet.get('clearance_m')!=CLEARANCE:raise ValueError('Unexpected clearance policy')
    if len(fleet['placements'])<80 or len({r['asset'] for r in fleet['placements']})<5:
        raise ValueError('At least80 placements and5 types are required')
    for r in fleet['placements']:
        if r.get('state')!='anchored' or r.get('route')!=[]:raise ValueError('Only anchored, route-free fleet is permitted')
        if r['asset'] not in models:raise ValueError('Unknown model')
        if not all(math.isfinite(v) for v in r['position_m']+r['scale']+[r['yaw_deg']]):raise ValueError('Nonfinite boat transform')
        if r['position_m'][2]!=0 or any(v<.80 or v>1.10 for v in r['scale']):raise ValueError('Invalid waterline/scale')
        shape=_world_footprint(models[r['asset']],r);reason=_reason(shape,obstacles,accepted)
        if reason:raise ValueError('Unsafe boat '+str(r.get('id'))+': '+reason)
        accepted.append(shape)
    return {'passed':True,'checked_placements':len(accepted),'full_rotated_all_parts_footprint':True,
            'minimum_pair_separation_m':min((a.distance(b) for i,a in enumerate(accepted) for b in accepted[i+1:]),default=None),
            'minimum_coast_gap_after_required_buffer_m':min((s.distance(obstacles['coast']) for s in accepted),default=None),
            'obstacles':obstacles['counts'],'no_under_bridge_placements':True,'moving_routes':0}


def place_fleet(scene):
    from shapely.geometry import Point
    models=make_models(_TestBatch,lambda *a,**k:None)
    obstacles=_obstacles(scene);rng=random.Random(SEED);accepted=[];placements=[];rejected=Counter()
    # First location is beside the existing southern tour leg. Each candidate is
    # checked against actual geography; this is not a forced berth fallback.
    hero=None
    for center in [(-2250,-1100),(-2350,300),(-2250,1300),(-1400,3850),(-250,-3500)]:
        disk=Point(center).buffer(125)
        if obstacles['bounds'].covers(disk) and not obstacles['prepared'].intersects(disk):hero=center;break
    if hero is None:raise ValueError('No safe full-water hero cluster in supplied geography')
    hero_disk=Point(hero).buffer(125)
    zones=[('hero_cluster',hero,(100,100),12),('old_town_harbour',(-180,-3400),(600,500),26),
           ('stock_island_marinas',(-1050,3720),(440,400),26),('north_anchorage',(800,-2350),(900,1050),28),
           ('coastal_fishing',(-2950,400),(1200,1800),28)]
    for zone,center,spread,wanted in zones:
        count=0
        for attempt in range(5000):
            if count>=wanted:break
            model=models[(len(placements)+attempt%3)%len(models)]
            n=center[0]+rng.gauss(0,spread[0]*.55);e=center[1]+rng.gauss(0,spread[1]*.55)
            yaw=rng.uniform(0,360) if zone=='coastal_fishing' else 35+rng.gauss(0,24)
            scale=round(rng.uniform(.86,1.07),5)
            r={'id':f'boat-{len(placements):03d}','asset':model['asset'],
               'position_m':[round(n,4),round(e,4),0],'yaw_deg':round(yaw%360,4),'scale':[scale]*3,
               'state':'anchored','route':[],'placement_zone':zone,
               'placement_source':'Inferred stationary berth/anchorage, verified against OSM land, piers and bridges; not AIS'}
            shape=_world_footprint(model,r);reason=_reason(shape,obstacles,accepted)
            if reason is None and zone=='hero_cluster' and not hero_disk.covers(shape):reason='hero_radius'
            if reason:rejected[reason]+=1;continue
            accepted.append(shape);placements.append(r);count+=1
    counts=Counter(r['asset'] for r in placements)
    if len(placements)<80 or len(counts)<5:raise ValueError('Fewer than80 safe varied berths; never force boats onto land')
    fleet={'schema':1,'units':'metres','axes':{'x':'north','y':'east','z':'up'},'seed':SEED,
           'models':models,'placements':placements,'clearance_m':CLEARANCE,
           'hero_cluster':{'center_ne_m':list(hero),'radius_m':125,'placement_ids':[r['id'] for r in placements if r['placement_zone']=='hero_cluster']},
           'statistics':{'placements':len(placements),'types':dict(sorted(counts.items())),
                         'zones':dict(sorted(Counter(r['placement_zone'] for r in placements).items())),
                         'rejections':dict(sorted(rejected.items()))},
           'provenance':{'boat_art':'Original code-authored geometry; no downloaded boat meshes/textures',
                         'placements':'Inferred, OSM-derived water/obstacle validation; retain geographic attribution',
                         'geographic_source':'https://www.openstreetmap.org/copyright',
                         'geographic_license':'ODbL-1.0',
                         'motion':'Anchored/moored only; no routes, wakes or sailing/navigation simulation'}}
    fleet['validation']=validate_fleet(scene,fleet)
    return fleet


def _closed_mesh(batch):
    edges=Counter();directed=Counter();volume=0
    for face in batch.faces:
        points=[batch.vertices[i] for i in face]
        if len(points)<3 or not all(math.isfinite(v) for p in points for v in p):raise AssertionError('Invalid face')
        normal=cross(sub(points[1],points[0]),sub(points[2],points[0]))
        if dot(normal,normal)<1e-17:raise AssertionError('Degenerate face')
        for a,b in zip(points,points[1:]+points[:1]):
            a=tuple(round(v,7) for v in a);b=tuple(round(v,7) for v in b)
            edges[tuple(sorted((a,b)))]+=1
            directed[a,b]+=1
        for j in range(1,len(points)-1):volume+=dot(points[0],cross(points[j],points[j+1]))/6
    if any(v!=2 for v in edges.values()):raise AssertionError('Hull/panel boundary is not closed')
    if any(directed[a,b]!=directed[b,a] for a,b in directed):raise AssertionError('Inconsistent face winding')
    if volume<=0:raise AssertionError('Inward shell normals')
    return volume


def self_test():
    batches={}
    models=make_models(_TestBatch,lambda name,batch,**kw:batches.update({name:batch}))
    for model,spec in zip(models,SPECS):
        assert 3000<=model['triangles']<=15000,(model['asset'],model['triangles'])
        b=batches[model['asset']]
        assert all(math.isfinite(v) for p in b.vertices for v in p)
        assert model['bounds_m'][0][2]<-.3 and model['bounds_m'][1][2]>.7
        for f in b.faces:
            p=[b.vertices[i] for i in f];assert dot(cross(sub(p[1],p[0]),sub(p[2],p[0])),cross(sub(p[1],p[0]),sub(p[2],p[0])))>1e-17
        hull=_TestBatch();_hull(hull,*spec[2:],'KWB_Gelcoat');_closed_mesh(hull)
        rim=_TestBatch();_gunwales(rim,[_section(*spec[2:],i/40) for i in range(41)],rail=False);_closed_mesh(rim)
        assert min(abs(p[1]) for p in hull.vertices if p[0]>spec[2]*.50)<spec[3]*.05
    panel=_TestBatch();_solid(panel,[(0,0,0),(2,0,0),(2,0,1),(0,0,1)],.04,'KWB_Glass');_closed_mesh(panel)
    bevel=_TestBatch();_bevel_box(bevel,(0,0,0),(2,1,1),'KWB_Gelcoat');_closed_mesh(bevel)
    print('PASS six model budgets, finite faces, shaped bow, waterline, closed outward hulls/panels',flush=True)
    from shapely.geometry import Polygon,box,LineString
    from shapely.prepared import prep
    # A center-point probe misses this concave shore finger; whole hull must fail.
    coast=Polygon([(0,0),(20,0),(20,3),(3,3),(3,20),(0,20)])
    hole=Polygon([(40,0),(60,0),(60,20),(40,20)],holes=[[(44,4),(56,4),(56,16),(44,16)]])
    block=coast.union(hole);obs={'blocked':block,'prepared':prep(block),'bounds':box(-100,-100,100,100)}
    model={'footprint_local_m':[[-7,-1],[7,-1],[7,1],[-7,1]]}
    rec={'position_m':[7,7,0],'yaw_deg':45,'scale':[1,1,1]}
    assert not block.contains(__import__('shapely').geometry.Point(7,7))
    assert _reason(_world_footprint(model,rec),obs,[])=='land_pier_or_bridge'
    small={'footprint_local_m':[[-1,-1],[1,-1],[1,1],[-1,1]]}
    rec={'position_m':[50,10,0],'yaw_deg':30,'scale':[1,1,1]}
    assert _reason(_world_footprint(small,rec),obs,[]) is None
    pier=LineString([(0,-20),(0,20)]).buffer(2)
    obs['prepared']=prep(pier)
    rec={'position_m':[4,0,0],'yaw_deg':0,'scale':[1,1,1]}
    assert _reason(_world_footprint(model,rec),obs,[])=='land_pier_or_bridge'
    obs['prepared']=prep(Polygon())
    shape=_world_footprint(small,rec)
    assert _reason(shape,obs,[shape])=='separation'
    assert _reason(_world_footprint(model,{'position_m':[99,0,0],'yaw_deg':90,'scale':[1,1,1]}),obs,[])=='bounds'
    fixture={'schema':1,'units':'metres','axes':{'x':'north','y':'east','z':'up'},'sea_level_m':0,
             'land_polygons':[{'outer':[[-100,-100],[100,-100],[100,100],[-100,100]],'holes':[]}],
             'piers':[{'points':[[-180,0],[180,0]],'width_m':3}],
             'roads':[{'points':[[0,-220],[0,220]],'width_m':8,'bridge':True}]}
    first=place_fleet(fixture);second=place_fleet(fixture)
    assert json.dumps(first,sort_keys=True)==json.dumps(second,sort_keys=True)
    assert first['validation']['passed'] and len(first['placements'])>=80
    assert first['validation']['obstacles']['bridge_corridors']==1
    obstacles=_obstacles(fixture)
    crossing=_world_footprint(model,{'position_m':[22,150,0],'yaw_deg':0,'scale':[1,1,1]})
    assert crossing.intersects(obstacles['bridges']) and not crossing.intersects(obstacles['coast'])
    assert _reason(crossing,obstacles,[])=='land_pier_or_bridge'
    broken=json.loads(json.dumps(first));broken['placements'][0]['state']='moving'
    try:validate_fleet(fixture,broken)
    except ValueError:pass
    else:raise AssertionError('Moving fleet unexpectedly accepted')
    broken=json.loads(json.dumps(first));broken['placements'][0]['route']=[[0,0,0],[10,10,0]]
    try:validate_fleet(fixture,broken)
    except ValueError:pass
    else:raise AssertionError('Translating route unexpectedly accepted')
    broken=json.loads(json.dumps(first));broken['models'][0]['footprint_local_m']=[[-.1,-.1],[.1,-.1],[0,.1]]
    try:validate_fleet(fixture,broken)
    except ValueError:pass
    else:raise AssertionError('Shrunk hull metadata unexpectedly accepted')
    broken=json.loads(json.dumps(first));broken['placements']=broken['placements'][:10]
    try:validate_fleet(fixture,broken)
    except ValueError:pass
    else:raise AssertionError('Undersized fleet unexpectedly accepted')
    bad=dict(fixture);bad['land_polygons']=[]
    try:place_fleet(bad)
    except ValueError:pass
    else:raise AssertionError('Missing coastline accepted as open ocean')
    print('PASS rotated concave shore, water hole, pier crossing, bounds, separation, bridge, anchored state and deterministic fleet',flush=True)
    print(json.dumps({'models':[{k:m[k] for k in ('asset','triangles','dimensions_m')} for m in models],
                      'fixture_placements':len(first['placements'])}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:self_test();return
    if args.scene is None or args.output is None:parser.error('--scene and --output are required')
    source=args.scene.read_bytes();scene=json.loads(source.decode('utf-8-sig'))
    fleet=place_fleet(scene);fleet['source_scene_sha256']=hashlib.sha256(source).hexdigest()
    fleet['boat_generator_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(fleet,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print('KEYWEST_BOATS_READY '+json.dumps(fleet['statistics'],sort_keys=True),flush=True)


if __name__=='__main__':main()
