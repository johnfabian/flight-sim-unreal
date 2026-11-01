"""Restore the authored ocean after the isolated diagnostic."""
import unreal
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.load_level('/Game/Showcase/CoastalShowcase')
ocean=next(a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors() if a.get_actor_label()=='Pacific coastal ocean')
ocean.static_mesh_component.set_material(0,unreal.load_asset('/Game/Showcase/Materials/M_Water'))
assert levels.save_current_level()
unreal.log('AERONAUT_AUTHORED_WATER_RESTORED')
