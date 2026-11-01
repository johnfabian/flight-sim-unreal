"""Bound probe work to the island and size small-prop lightmaps appropriately."""
import unreal
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not levels.load_level('/Game/Showcase/CoastalShowcase'): raise RuntimeError('Map missing')
world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
settings=world.get_world_settings(); lm=settings.get_editor_property('lightmass_settings')
lm.volumetric_lightmap_detail_cell_size=1600.0; lm.volumetric_lightmap_maximum_brick_memory_mb=30.0
settings.set_editor_property('lightmass_settings',lm)
for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    if isinstance(actor,unreal.LightmassImportanceVolume):
        center,extent=actor.get_actor_bounds(False); scale=actor.get_actor_scale3d()
        if min(extent.x,extent.y,extent.z)<=0: raise RuntimeError('Empty lighting region')
        actor.set_actor_scale3d(unreal.Vector(scale.x*330000/(extent.x*2),scale.y*330000/(extent.y*2),scale.z*70000/(extent.z*2)))
        actor.set_actor_location(unreal.Vector(0,0,30000),False,False)
        unreal.log('AERONAUT_LIGHTING_REGION '+str(actor.get_actor_bounds(False)))
for name,resolution in [('Fence',32),('Cone',32),('RunwayLight',32),('Marking',32),('GrassClump',16),('Conifer0',16),('Conifer1',16),('Conifer2',16),('Conifer3',16)]:
    mesh=unreal.load_asset('/Game/Showcase/Meshes/'+name)
    mesh.set_editor_property('light_map_resolution',resolution)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
if not levels.save_current_level(): raise RuntimeError('Lighting settings save failed')
unreal.log('AERONAUT_LIGHTING_TUNED detail_cell_cm=1600 production_surface_samples_unchanged')
