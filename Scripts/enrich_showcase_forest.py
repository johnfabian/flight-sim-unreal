"""Explicit saved-forest art pass. Re-bake lighting after running this script."""
import array, math, random
from pathlib import Path
import unreal
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.load_level('/Game/Showcase/CoastalShowcase')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
scene=next(a for a in actors if isinstance(a,unreal.CoastalScene))
tags=list(scene.get_editor_property('tags'))
if 'AeronautForestDensityV1' not in [str(t) for t in tags]:
    raw=array.array('H'); raw.frombytes((Path(unreal.Paths.project_dir())/'Art/Exports/coast.r16').read_bytes())
    def height(x,y):
        fx=max(0,min(1008,(x+1512)/3)); fy=max(0,min(1008,(y+1512)/3))
        ix=min(1007,int(fx)); iy=min(1007,int(fy)); ax=fx-ix; ay=fy-iy
        value=(raw[iy*1009+ix]*(1-ax)+raw[iy*1009+ix+1]*ax)*(1-ay)+(raw[(iy+1)*1009+ix]*(1-ax)+raw[(iy+1)*1009+ix+1]*ax)*ay
        return (value-32768)/50
    groups=[next(a for a in actors if a.get_actor_label()=='Forest conifer '+str(j)) for j in range(4)]
    batches=[[] for _ in groups]; rng=random.Random(810221)
    for j in range(31000):
        x,y=rng.uniform(-1450,1450),rng.uniform(-1450,1450); z=height(x,y)
        in_airfield=abs(x+430)<455 and abs(y+475)<185
        slope=max(abs(height(x+3,y)-height(x-3,y)),abs(height(x,y+3)-height(x,y-3)))/6
        cluster=math.sin(x*.0047+math.sin(y*.0031))*math.cos(y*.0053)
        if 18<z<550 and not in_airfield and slope<.85 and cluster>-.4:
            scale=rng.uniform(.72,1.35)
            batches[j%4].append(unreal.Transform(location=unreal.Vector(x*100,y*100,z*100),rotation=unreal.Rotator(yaw=rng.uniform(0,360)),scale=unreal.Vector(scale,scale,scale)))
    for group,batch in zip(groups,batches): group.instances.add_instances(batch,False,False)
    tags.append('AeronautForestDensityV1'); scene.set_editor_property('tags',tags)
    assert levels.save_current_level()
    unreal.log('AERONAUT_FOREST_ENRICHED added='+str(sum(len(b) for b in batches))+' total='+str(sum(g.instances.get_instance_count() for g in groups)))
else: unreal.log('AERONAUT_FOREST_ALREADY_ENRICHED')
