"""Apply the reviewed horizon/fog refinement without changing baked geometry."""
import unreal
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not levels.load_level('/Game/Showcase/CoastalShowcase'): raise RuntimeError('Showcase map missing')
for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    if actor.get_actor_label()=='Pacific coastal ocean': actor.set_actor_scale3d(unreal.Vector(16000,16000,1))
    if actor.get_actor_label()=='Coastal cloud sky': actor.set_actor_scale3d(unreal.Vector(15000,15000,15000))
    if isinstance(actor,unreal.ExponentialHeightFog): actor.component.set_editor_property('fog_density',.0025)
if not levels.save_current_level(): raise RuntimeError('Atmosphere save failed')
unreal.log('AERONAUT_ATMOSPHERE_SAVED')
