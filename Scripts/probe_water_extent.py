import unreal
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.load_level('/Game/Showcase/CoastalShowcase')
for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    label=actor.get_actor_label()
    if label=='Pacific coastal ocean': actor.set_actor_scale3d(unreal.Vector(16000,16000,1))
    if label=='Coastal sky backdrop': actor.set_actor_scale3d(unreal.Vector(15000,15000,15000))
    if isinstance(actor,unreal.StaticMeshActor) and actor.static_mesh_component.get_editor_property('static_mesh') and actor.static_mesh_component.get_editor_property('static_mesh').get_name()=='Sphere':
        unreal.log('AERONAUT_SKY_EXTENT '+label+' '+str(actor.get_actor_scale3d()))
        actor.set_actor_scale3d(unreal.Vector(15000,15000,15000))
assert levels.save_current_level()
unreal.log('AERONAUT_WATER_EXTENT_PROBE_READY')
