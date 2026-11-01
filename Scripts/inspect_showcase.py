import unreal
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
levels.load_level('/Game/Showcase/CoastalShowcase')
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
for a in actors:
    if isinstance(a,(unreal.Landscape,unreal.CoastalScene)) or a.get_actor_label() in ['Pacific coastal ocean','West hangar','Coastal cloud sky'] or a.get_name()=='StaticMeshActor_313':
        unreal.log('SCENE_INSPECT '+a.get_name()+' '+a.get_actor_label()+' pos='+str(a.get_actor_location())+' rot='+str(a.get_actor_rotation())+' bounds='+str(a.get_actor_bounds(False)))
        if isinstance(a,unreal.StaticMeshActor): unreal.log('COLLISION_INSPECT '+a.get_name()+' '+str(a.static_mesh_component.get_collision_enabled()))
unreal.log('ROTATOR_PROBE '+str(unreal.Rotator(0,90,0)))
for name in ['Airframe','Cockpit','DialAirspeed','NeedleAirspeed','WingLeft']:
    sm=unreal.load_asset('/Game/Showcase/Meshes/'+name)
    unreal.log('MESH_INSPECT '+name+' bounds='+str(sm.get_bounds())+' slots='+str([str(s.material_slot_name)+':'+str(s.material_interface.get_name()) for s in sm.static_materials]))
