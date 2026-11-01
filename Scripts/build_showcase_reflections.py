"""Refresh saved reflections without invalidating or rebuilding Lightmass."""
import unreal

levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.load_level('/Game/Showcase/CoastalShowcase')
unreal.ShowcaseEditor.build_reflections()
assert levels.save_current_level()
assert unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
unreal.log('AERONAUT_REFLECTIONS_SAVED')
