"""Original Aeronaut art. Run with Blender 4.5 --background --python this-file.
All distances are metres. Authoring X is aircraft forward, Y right, Z up.
FBX exports are centred on each animation pivot. Source meshes remain editable.
"""
import bpy, bmesh, math, random, json, struct
from pathlib import Path
from mathutils import Vector, Matrix
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'Art'/'Exports'; OUT.mkdir(parents=True,exist_ok=True)
TEX=ROOT/'Art'/'Textures'/'Original'; TEX.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
for datablock in list(bpy.data.materials): bpy.data.materials.remove(datablock)
bpy.context.scene.unit_settings.system='METRIC'
bpy.context.scene.unit_settings.scale_length=1
random.seed(271828)
materials={}; exports=[]

def material(name,color,rough=.5,metal=0):
    m=bpy.data.materials.new(name); m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=rough; bs.inputs['Metallic'].default_value=metal
    m.diffuse_color=(*color,1); materials[name]=m; return m

material('Paint',(.73,.76,.72),.31,.0)
material('Orange',(.62,.14,.035),.32)
material('Metal',(.3,.32,.31),.3,.85)
material('DarkMetal',(.035,.045,.045),.42,.65)
material('Rubber',(.018,.02,.02),.8)
material('Interior',(.055,.065,.06),.68)
material('Leather',(.16,.12,.075),.64)
material('Glass',(.12,.24,.28),.08)
material('Dial',(.01,.015,.015),.7)
material('Needle',(.92,.69,.26),.45)
material('Markings',(.8,.79,.69),.7)
material('Runway',(.12,.13,.12),.8)
material('Concrete',(.38,.37,.32),.86)
material('Wood',(.2,.15,.09),.85)
material('Hangar',(.24,.31,.3),.6,.25)
material('Roof',(.12,.16,.16),.46,.5)
material('Rock',(.3,.31,.28),.9)
material('Bark',(.19,.14,.09),.92)
material('Foliage',(.095,.17,.09),.9)
material('Grass',(.17,.22,.09),.95)
material('RedLight',(.8,.025,.015),.3)
material('GreenLight',(.025,.65,.15),.3)
material('WhiteLight',(.9,.86,.65),.3)

def finish(obj,mat,smooth=True):
    obj.data.materials.append(materials[mat])
    if smooth:
        for p in obj.data.polygons: p.use_smooth=True
    return obj

def box(p,size,mat,bevel=.02):
    bpy.ops.mesh.primitive_cube_add(size=1,location=p); o=bpy.context.object; o.scale=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if bevel:
        mod=o.modifiers.new('Manufactured edges','BEVEL'); mod.width=bevel; mod.segments=2
        bpy.ops.object.modifier_apply(modifier=mod.name)
        mod=o.modifiers.new('Weighted normals','WEIGHTED_NORMAL'); mod.keep_sharp=True
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return finish(o,mat,False)

def mesh(name,verts,faces,mat,smooth=True,recalc=True):
    d=bpy.data.meshes.new(name); d.from_pydata(verts,[],faces); d.update()
    if recalc:
        bm=bmesh.new(); bm.from_mesh(d); bmesh.ops.recalc_face_normals(bm,faces=bm.faces); bm.to_mesh(d); bm.free()
    o=bpy.data.objects.new(name,d); bpy.context.collection.objects.link(o); return finish(o,mat,smooth)

def ellipsoid(p,r,mat,segments=32,rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments,ring_count=rings,location=p)
    o=bpy.context.object; o.scale=r; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return finish(o,mat)

def rod(a,b,r,mat,vertices=12,r2=None):
    a,b=Vector(a),Vector(b); v=b-a
    bpy.ops.mesh.primitive_cone_add(vertices=vertices,radius1=r,radius2=r if r2 is None else r2,depth=v.length,location=(a+b)/2)
    o=bpy.context.object; o.rotation_euler=v.to_track_quat('Z','Y').to_euler(); return finish(o,mat)

def text(value,p,size,mat='Markings'):
    d=bpy.data.curves.new('engraving','FONT'); d.body=value; d.size=size; d.align_x='CENTER'; d.extrude=.00012
    o=bpy.data.objects.new('engraving',d); bpy.context.collection.objects.link(o); o.location=p
    # Local text XY -> instrument plane YZ, normal toward the pilot (-X).
    o.rotation_euler=(math.pi/2,0,-math.pi/2)
    o.data.materials.append(materials[mat]); bpy.context.view_layer.objects.active=o; o.select_set(True)
    bpy.ops.object.convert(target='MESH'); o.select_set(False); return o

def export_asset(name,objects,pivot=(0,0,0),collision=False,foliage=False,unwrap=True):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects: o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    bpy.ops.object.join(); o=bpy.context.object; o.name=name
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    bpy.context.scene.cursor.location=pivot; bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    if unwrap:
        bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=1.15,island_margin=.015)
        bpy.ops.object.mode_set(mode='OBJECT')
    mats=[m.name for m in o.data.materials]
    pos=o.location.copy(); o.location=(0,0,0)
    # Unreal's FBX conversion reflects Y. Correct the temporary export geometry,
    # keeping the editable source, UVs and authored animation metadata unchanged.
    source_data=o.data; export_data=source_data.copy(); o.data=export_data
    export_data.transform(Matrix.Diagonal((1,-1,1,1)))
    bm=bmesh.new(); bm.from_mesh(export_data); bmesh.ops.reverse_faces(bm,faces=bm.faces); bm.to_mesh(export_data); bm.free()
    bpy.ops.export_scene.fbx(filepath=str(OUT/(name+'.fbx')),use_selection=True,object_types={'MESH'},
        apply_unit_scale=True,apply_scale_options='FBX_SCALE_UNITS',axis_forward='X',axis_up='Z',
        bake_space_transform=True,use_mesh_modifiers=True,mesh_smooth_type='FACE',add_leaf_bones=False,bake_anim=False)
    o.data=source_data; bpy.data.meshes.remove(export_data); o.location=pos
    exports.append(dict(name=name,pivot=list(pivot),materials=mats,collision=collision,foliage=foliage,
                        triangles=sum(len(p.vertices)-2 for p in o.data.polygons)))
    o.select_set(False); return o

# The fuselage is a continuous shaped shell with an open glazed cabin.
sections=[(-3.65,.035,.065,.25),(-3.2,.13,.18,.22),(-2.4,.26,.32,.12),(-1.25,.43,.48,.02),
          (-.8,.52,.56,0),(.3,.56,.59,0),(1.3,.5,.56,0),(2.05,.43,.47,.02),(2.55,.33,.35,.04),(2.83,.27,.28,.06)]
v=[]; f=[]; n=48
for x,ry,rz,zc in sections:
    for j in range(n):
        a=2*math.pi*j/n; v.append((x,math.cos(a)*ry,math.sin(a)*rz+zc))
for i in range(len(sections)-1):
    for j in range(n):
        angle=2*math.pi*(j+.5)/n
        if i in (4,5) and math.sin(angle)>.05: continue
        f.append((i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j))
f.extend([tuple(reversed(range(n))),tuple((len(sections)-1)*n+j for j in range(n))])
body=[mesh('shaped fuselage',v,f,'Paint')]
body+=[ellipsoid((2.05,0,.05),(.6,.435,.46),'Paint'),ellipsoid((2.87,0,.06),(.3,.27,.28),'Orange')]
# Side stripes, seams, door handles, rivets and exhaust give true close-view detail.
for s in (-1,1):
    body.append(box((-.35,s*.525,-.08),(3.6,.012,.065),'Orange',.007))
    body.append(box((.0,s*.558,.22),(.22,.028,.025),'DarkMetal',.006))
    body.append(rod((-.82,s*.526,-.32),(-.82,s*.526,.5),.006,'DarkMetal',8))
    body.append(rod((.85,s*.51,-.32),(.85,s*.51,.38),.006,'DarkMetal',8))
    for x in np.arange(-2.8,2.2,.18):
        ry=float(np.interp(x,[s[0] for s in sections],[s[1] for s in sections]))
        body.append(ellipsoid((x,s*ry,-.12),(.008,.006,.008),'Metal',8,4))
    body.append(rod((1.95,s*.31,-.24),(2.04,s*.45,-.43),.045,'DarkMetal',16))
    body.append(box((2.28,s*.43,.04),(.3,.015,.12),'DarkMetal',.03))
# Cabin structure, open panel windscreen, and restrained transparent glass.
for s in (-1,1):
    for a,b in [((-.8,s*.52,.1),(-.55,s*.5,1.28)),((1.3,s*.48,.28),(.93,s*.45,1.28)),((-.55,s*.5,1.28),(.93,s*.45,1.28))]:
        body.append(rod(a,b,.027,'Paint',12))
    body.append(rod((-.55,s*.5,1.28),(.93,s*.45,1.28),.032,'DarkMetal',12))
body.append(box((.15,0,1.29),(1.55,1.05,.08),'Paint',.06))
body.append(box((-.65,0,.13),(.16,1.05,.7),'Interior',.03))
# Close the glazed cabin against the tail cone; the original loft opens here.
body.append(mesh('rear cabin closure',[(-.8,-.52,.30),(-.8,.52,.30),(-.55,.5,1.27),(-.55,-.5,1.27)],[(3,2,1,0)],'Paint',recalc=False))
body.append(mesh('rear cabin lining',[(-.79,-.51,.30),(-.79,.51,.30),(-.54,.49,1.26),(-.54,-.49,1.26)],[(0,1,2,3)],'Interior',recalc=False))
for side in (-1,1):
    body.append(mesh('lower cabin door',[(-.79,side*.525,.02),(1.29,side*.485,.02),(1.27,side*.48,.36),(-.76,side*.52,.36)],[(0,1,2,3) if side<0 else (3,2,1,0)],'Paint',recalc=False))
for side in (-1,1):
    body.append(rod((-.25,side*.5,-.1),(.15,side*3.3,1.39),.028,'Metal'))
    body.append(rod((1.0,side*.43,-.18),(.5,side*3.3,1.39),.022,'Metal'))
    body.append(rod((.5,side*.42,-.3),(.52,side*1.1,-1.12),.045,'Metal',16))
    body.append(ellipsoid((.52,side*1.1,-1.16),(.25,.11,.25),'Rubber'))
    body.append(ellipsoid((.52,side*1.1,-1.14),(.32,.15,.17),'Paint'))
body.append(rod((2.0,0,-.3),(2.05,0,-1.14),.045,'Metal',16))
body.append(ellipsoid((2.05,0,-1.17),(.19,.1,.19),'Rubber'))
body.append(ellipsoid((2.05,0,-1.13),(.25,.13,.16),'Paint'))
body.append(ellipsoid((-3.1,0,.23),(.6,1.6,.075),'Paint'))
body.append(mesh('vertical stabilizer',[(-3.5,-.035,.22),(-2.55,-.035,.22),(-3.1,-.035,1.6),(-3.55,-.035,1.64),(-3.5,.035,.22),(-2.55,.035,.22),(-3.1,.035,1.6),(-3.55,.035,1.64)],[(0,1,2,3),(7,6,5,4),(0,4,5,1),(3,2,6,7),(0,3,7,4),(1,5,6,2)],'Orange'))
export_asset('Airframe',body)

glass=[]
glass.append(mesh('windscreen',[(1.34,-.47,.35),(1.34,.47,.35),(.92,.45,1.25),(.92,-.45,1.25)],[(0,1,2,3)],'Glass'))
for s in (-1,1):
    glass.append(mesh('side window',[(-.76,s*.52,.36),(1.27,s*.48,.36),(.89,s*.46,1.25),(-.53,s*.5,1.25)],[(0,1,2,3)],'Glass'))
export_asset('CabinGlass',glass)

def wing(side):
    verts=[]; faces=[]; rings=[(0,1.55),(1.2,1.55),(3.1,1.43),(4.8,1.2),(5.4,.9),(5.5,.25)]
    profile=[]
    for upper in (True,False):
        ts=np.linspace(0,1,25) if upper else np.linspace(1,0,25)
        for t in ts:
            thickness=5*.12*(.2969*math.sqrt(t)-.126*t-.3516*t*t+.2843*t**3-.1036*t**4)
            profile.append((t,(1 if upper else -1)*thickness+.02*math.sin(math.pi*t)))
    count=len(profile)
    for y,chord in rings:
        for t,z in profile: verts.append((.78-t*chord,side*y,1.38+y*.025+z*chord))
    for i in range(len(rings)-1):
        for j in range(count): faces.append((i*count+j,i*count+(j+1)%count,(i+1)*count+(j+1)%count,(i+1)*count+j))
    faces.extend([tuple(reversed(range(count))),tuple((len(rings)-1)*count+j for j in range(count))])
    objects=[mesh('airfoil',verts,faces,'Paint')]
    for y in (1.3,2.5,3.7,4.6): objects.append(rod((.7,side*y,1.41+y*.025),(-.6,side*y,1.43+y*.025),.004,'Metal',6))
    objects.append(ellipsoid((.15,side*5.42,1.55),(.38,.13,.075),'Orange'))
    objects.append(ellipsoid((.23,side*5.5,1.56),(.045,.045,.035),'RedLight' if side<0 else 'GreenLight',16,8))
    return objects
export_asset('WingLeft',wing(-1)); export_asset('WingRight',wing(1))
for s,label in [(-1,'Left'),(1,'Right')]:
    export_asset('Aileron'+label,[box((-.58,s*3.65,1.44),(.32,2.35,.035),'Paint',.012)],(-.42,s*3.65,1.44))
    export_asset('Elevator'+label,[box((-3.3,s*.83,.27),(.33,1.4,.028),'Paint',.01)],(-3.14,s*.83,.27))
export_asset('Rudder',[box((-3.55,0,.98),(.25,.055,1.23),'Orange',.008)],(-3.42,0,.98))
prop=[ellipsoid((3.02,0,.06),(.35,.22,.22),'Paint')]
for s in (-1,1):
    prop.append(ellipsoid((2.97,s*.52,.06),(.035,.51,.095),'DarkMetal'))
    prop.append(ellipsoid((2.97,s*.94,.06),(.035,.08,.10),'Markings'))
export_asset('Propeller',prop,(2.97,0,.06))

# Interior is independent of exterior visibility. Real meshes remain in the pilot camera.
inside=[box((.1,0,-.25),(1.9,1.0,.08),'Interior',.02),box((1.12,0,.38),(.18,1.02,.56),'Interior',.09)]
for s in (-1,1):
    inside.extend([box((-.15,s*.27,-.05),(.57,.42,.18),'Leather',.08),box((-.48,s*.27,.25),(.15,.44,.63),'Leather',.07)])
    inside.append(rod((-.49,s*.42,.54),(-.12,s*.12,-.01),.015,'DarkMetal'))
for y in np.linspace(-.43,.43,12): inside.append(box((1.016,float(y),.2),(.018,.025,.025),'Metal',.004))
inside.append(box((.9,0,.02),(.5,.13,.12),'DarkMetal',.025))
for s in (-1,1): inside.append(rod((.95,s*.34,-.16),(1.15,s*.34,-.16),.035,'DarkMetal',12))
export_asset('Cockpit',inside)

# Face meshes get an original texture atlas created by MakeDialTextures.py.
dials=[('Airspeed',-.32,.55),('Attitude',-.105,.55),('Altitude',.11,.55),('Heading',-.32,.315),('VerticalSpeed',-.105,.315),('RPM',.11,.315)]
dial_layout=[]
for index,(name,y,z) in enumerate(dials):
    radius=.088
    bezel=rod((1.015,y,z),(.99,y,z),radius*1.13,'DarkMetal',48)
    # A circle in YZ: texture U follows +Y, V follows +Z.
    verts=[(.984,y,z)]+[(.984,y+radius*math.sin(2*math.pi*j/64),z+radius*math.cos(2*math.pi*j/64)) for j in range(64)]
    face=mesh('gauge face',verts,[(0,j+1,(j+1)%64+1) for j in range(64)],'Dial',False,recalc=False)
    uv=face.data.uv_layers.new(name='UVMap')
    for p in face.data.polygons:
        for li in p.loop_indices:
            pt=face.data.vertices[face.data.loops[li].vertex_index].co
            u=(pt.y-y)/radius*.5+.5; vv=(pt.z-z)/radius*.5+.5
            uv.data[li].uv=((index%3+u)/3,(1-index//3+vv)/2)
    export_asset('Dial'+name,[bezel,face],unwrap=False)
    pivot=(.975,y,z)
    if name!='Attitude':
        needle=mesh('instrument needle',[(.974,y-.004,z-.013),(.974,y+.004,z-.013),(.974,y+.0015,z+.067),(.974,y-.0015,z+.067)],[(0,1,2,3)],'Needle',False)
        export_asset('Needle'+name,[needle],pivot)
    else:
        # The moving artificial horizon is a small sky/ground card behind a fixed reticle.
        # Its circular texture alpha clips it to the dial opening in Unreal.
        card=mesh('attitude horizon',[(.973,y-.077,z-.077),(.973,y+.077,z-.077),(.973,y+.077,z+.077),(.973,y-.077,z+.077)],[(0,1,2,3)],'Dial',False)
        uv=card.data.uv_layers.new(name='UVMap')
        for p in card.data.polygons:
            for li in p.loop_indices:
                co=card.data.vertices[card.data.loops[li].vertex_index].co
                uv.data[li].uv=((co.y-y)/.154+.5,(co.z-z)/.154+.5)
        export_asset('Horizon',[card],pivot,unwrap=False)
        reticle=[rod((.968,y-.046,z),(.968,y-.015,z),.002,'Needle',6),rod((.968,y+.015,z),(.968,y+.046,z),.002,'Needle',6)]
        export_asset('AttitudeReticle',reticle)
    dial_layout.append(dict(name=name,index=index,pivot=pivot))
yoke=[rod((.85,-.27,.22),(.64,-.27,.22),.018,'Metal',16),rod((.64,-.4,.22),(.64,-.14,.22),.018,'DarkMetal',16),rod((.64,-.4,.22),(.64,-.4,.3),.018,'DarkMetal'),rod((.64,-.14,.22),(.64,-.14,.3),.018,'DarkMetal')]
export_asset('Yoke',yoke,(.64,-.27,.22))
export_asset('Throttle',[rod((.92,.22,.22),(.75,.22,.22),.014,'Metal'),ellipsoid((.73,.22,.22),(.035,.035,.035),'DarkMetal',16,8)],(.92,.22,.22))

# A repeatable test asset establishes centimetres, material slots and mesh pivots.
export_asset('PipelineTest',[box((0,0,.5),(1,1,1),'Paint',.035)],collision=True)
export_asset('PipelineAxes',[box((1,2,3),(.2,.4,.6),'Orange',0)])

# Modular airfield assets. Individual hardware is geometry, not flat painted blocks.
hangar=[box((0,0,.1),(18,15,.2),'Concrete')]
for y in (-7.4,7.4): hangar.append(box((0,y,3.0),(18,.18,6),'Hangar'))
hangar.append(box((-8.9,0,3),(.18,15,6),'Hangar'))
for x in np.linspace(-8.5,8.5,18):
    for y in (-7.52,7.52): hangar.append(box((float(x),y,3),(.045,.05,5.8),'Metal',.005))
roof=mesh('pitched roof',[(-9,-7.8,6),(-9,0,8),(-9,7.8,6),(9,-7.8,6),(9,0,8),(9,7.8,6)],[(0,3,4,1),(1,4,5,2)],'Roof',False); hangar.append(roof)
for y in (-6.8,-3.4,0,3.4,6.8): hangar.append(box((9.0,y,3),(.14,3.3,5.8),'Hangar',.015))
for z in np.arange(.3,6,.3): hangar.append(box((9.09,0,float(z)),(.025,14,.025),'Metal',.003))
export_asset('Hangar',hangar,collision=True)
office=[box((0,0,1.55),(8,5,3.1),'Wood'),box((0,0,3.2),(8.6,5.6,.22),'Roof')]
for y in (-2.52,2.52):
    for x in (-2.4,0,2.4):
        office.append(box((x,y,1.85),(1.5,.045,1.1),'DarkMetal',.03)); office.append(box((x,y*1.002,1.85),(1.35,.02,.95),'Glass',.005))
for z in np.arange(.2,3,.16): office.append(box((0,-2.54,float(z)),(8,.025,.025),'Wood',.002))
export_asset('ServiceBuilding',office,collision=True)
export_asset('FuelTank',[rod((0,0,1.3),(3,0,1.3),.8,'Markings',32),box((.4,0,.4),(.2,1.6,.8),'DarkMetal'),box((2.6,0,.4),(.2,1.6,.8),'DarkMetal'),rod((1.5,0,2),(1.5,0,2.35),.12,'Metal',16)],collision=True)
export_asset('Fence',[rod((0,0,0),(0,0,1.7),.04,'Wood'),rod((3,0,0),(3,0,1.7),.04,'Wood'),rod((0,0,1.4),(3,0,1.4),.025,'Metal'),rod((0,0,.7),(3,0,.7),.025,'Metal')],collision=True)
windsock=[rod((0,0,0),(0,0,7),.045,'Metal',16)]
for j in range(8):
    a=j*.28; windsock.append(rod((a,0,6.9-a*.15),(a+.28,0,6.9-(a+.28)*.15),.30-j*.025,'Orange' if j%2==0 else 'Markings',16,r2=.275-j*.025))
export_asset('Windsock',windsock)
export_asset('RunwayLight',[rod((0,0,0),(0,0,.4),.04,'Metal'),ellipsoid((0,0,.43),(.085,.085,.06),'WhiteLight',16,8)])
export_asset('Cone',[rod((0,0,.05),(0,0,.6),.21,'Orange',16,r2=.035),box((0,0,.025),(.5,.5,.05),'Rubber',.02)])
export_asset('RunwaySlab',[box((0,0,-.08),(1,1,.16),'Runway',0)],collision=True)
export_asset('Marking',[box((0,0,.006),(1,1,.012),'Markings',0)])

for variant in range(5):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3,radius=1)
    rock=bpy.context.object
    for vert in rock.data.vertices:
        p=vert.co.copy(); rnd=random.uniform(.80,1.18)
        vert.co=(p.x*(2.8+variant*.6)*rnd,p.y*(2.1+variant*.3)*rnd,p.z*(2.5+variant*.2)*rnd+1.0)
    finish(rock,'Rock',False); export_asset('CoastalRock'+str(variant),[rock],collision=True)

# Original low-poly conifers use source branch/bark textures, not the 17M-triangle source model.
for variant in range(4):
    height=18+variant*2.5; radius=height*.19
    tree=[rod((0,0,0),(0,0,height),.35,'Bark',14,r2=.025)]
    cards_v=[]; cards_f=[]
    for level in range(12):
        z=height*(.15+level*.061); reach=radius*(1-level/13)**.65
        for j in range(6):
            a=j*math.tau/6+level*.55+variant*.7
            start=Vector((0,0,z)); end=Vector((math.cos(a)*reach,math.sin(a)*reach,z-.6))
            tree.append(rod(start,end,.045*(1-level/15),'Bark',6,r2=.012))
            side=Vector((-math.sin(a),math.cos(a),.13))*reach*.46
            k=len(cards_v); cards_v.extend([tuple(start-side*.25+Vector((0,0,.4))),tuple(end-side),tuple(end+side),tuple(start+side*.25+Vector((0,0,.4)))])
            cards_f.append((k,k+1,k+2,k+3))
            # A second angled card gives volume from the cockpit and above the forest.
            side=Vector((-math.sin(a)*.4,math.cos(a)*.4,1))*reach*.40
            k=len(cards_v); cards_v.extend([tuple(start-side*.2),tuple(end-side),tuple(end+side),tuple(start+side*.2)])
            cards_f.append((k,k+1,k+2,k+3))
    leaves=mesh('needle bough cards',cards_v,cards_f,'Foliage',False)
    uv=leaves.data.uv_layers.new(name='UVMap')
    for p in leaves.data.polygons:
        for i,li in enumerate(p.loop_indices): uv.data[li].uv=((.01,.55),(.01,.98),(.24,.98),(.24,.55))[i]
    tree.append(leaves); export_asset('Conifer'+str(variant),tree,foliage=True,unwrap=False)

grass=[]
for i in range(16):
    a=random.random()*math.tau; x,y=random.uniform(-.35,.35),random.uniform(-.35,.35); h=random.uniform(.25,.65)
    grass.append(mesh('grass blade',[(x,y,0),(x+.035,y,0),(x+math.cos(a)*.12,y+math.sin(a)*.12,h)],[(0,1,2)],'Grass',False))
export_asset('GrassClump',grass,foliage=True)
log=[rod((-2,0,.3),(2,0,.3),.32,'Bark',16),rod((-.3,0,.4),(.1,.7,.8),.1,'Bark',8,r2=.02)]
export_asset('Driftwood',log,collision=True)

# Fine authored roughness variations are baked into the aircraft's tangent normal map.
airframe=bpy.data.objects['Airframe']; bpy.ops.object.select_all(action='DESELECT')
airframe.select_set(True); bpy.context.view_layer.objects.active=airframe
normal=bpy.data.images.new('AircraftSurfaceNormal',width=1024,height=1024,alpha=False)
normal.colorspace_settings.name='Non-Color'
for mat in airframe.data.materials:
    nt=mat.node_tree; bs=nt.nodes.get('Principled BSDF')
    noise=nt.nodes.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value=95; noise.inputs['Detail'].default_value=2
    bump=nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=.16; bump.inputs['Distance'].default_value=.001
    nt.links.new(noise.outputs['Fac'],bump.inputs['Height']); nt.links.new(bump.outputs['Normal'],bs.inputs['Normal'])
    target=nt.nodes.new('ShaderNodeTexImage'); target.image=normal; nt.nodes.active=target
bpy.context.scene.render.engine='CYCLES'; bpy.context.scene.cycles.device='CPU'; bpy.context.scene.cycles.samples=4
bpy.ops.object.bake(type='NORMAL',margin=8)
normal.filepath_raw=str(TEX/'aircraft_surface_normal.png'); normal.file_format='PNG'; normal.save()

# A coherent, repeatable 1009x1009 heightfield. The imported Unreal landscape is authoritative.
axis=np.linspace(-1512,1512,1009); xx,yy=np.meshgrid(axis,axis)
r=np.sqrt(((xx-150)/1350)**2+((yy-200)/1050)**2)
shape=(1+.06*np.sin(np.arctan2(yy-200,xx-150)*5)+.035*np.cos(np.arctan2(yy-200,xx-150)*9))
edge=np.maximum(0,1-r*shape)
detail=np.sin(xx*.009+yy*.004)*18+np.sin(xx*.022-yy*.017)*5+np.cos(yy*.043)*2
height=edge**1.38*390+detail*np.minimum(1,edge*6)-12
height-=np.exp(-(((xx-400)/450)**2+((yy+680)/390)**2))*85
plateau=np.clip(np.minimum(410-np.abs(xx+430),155-np.abs(yy+475))/65,0,1)
plateau=plateau*plateau*(3-2*plateau)
height=height*(1-plateau)+22*plateau
height=np.clip(height,-30,470)
# Unreal height units: two centimetres at landscape Z scale 256.
raw=np.rint(height*50+32768).clip(0,65535).astype('<u2')
raw.tofile(OUT/'coast.r16')
np.save(OUT/'heightfield.npy',height.astype('float32'))

(OUT/'assets.json').write_text(json.dumps(dict(assets=exports,dials=dial_layout,
    coordinate_system='metres: X forward, Y right, Z up',heightfield=dict(size=1009,spacing=3,origin=[-1512,-1512],zscale=256)),indent=2))
catalog=0
for obj in list(bpy.data.objects):
    group='Aircraft' if obj.name in [a['name'] for a in exports[:26]] else 'Environment catalog'
    collection=bpy.data.collections.get(group) or bpy.data.collections.new(group)
    if collection.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(collection)
    for old in list(obj.users_collection): old.objects.unlink(obj)
    collection.objects.link(obj)
    if group=='Environment catalog': obj.location+=Vector((30+(catalog%6)*24,(catalog//6)*30,0)); catalog+=1
bpy.context.scene.cursor.location=(0,0,0)
for mat_name,filename in [('Rock','coast_land_rocks_01_base.jpg'),('Runway','aerial_asphalt_01_base.jpg'),('Bark','tree_bark_base.jpg'),('Foliage','tree_twig_base.png')]:
    mat=materials[mat_name]; node=mat.node_tree.nodes.new('ShaderNodeTexImage')
    node.image=bpy.data.images.load(str(ROOT/'Art/Textures/CC0'/filename),check_existing=True)
    mat.node_tree.links.new(node.outputs['Color'],mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'Art'/'AeronautCoast.blend'))
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'Art'/'AeronautCoast.blend'))
print('AERONAUT_BLENDER_ASSETS_READY',len(exports))
