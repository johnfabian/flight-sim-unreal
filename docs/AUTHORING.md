# Editing and regenerating assets

Install the prepared editor assets first using the README instructions. Ordinary editing, play and camera inspection use the saved content.

The original geometry is reproducible from the Python scripts in `Art`. Blender sources, exported FBX, texture downloads and geographic source records are retained in the editor-assets archive.

For full regeneration, the existing preparation scripts expect:

- Blender 4.5.15 LTS at `Tools/blender-4.5.15-windows-x64/blender.exe`.
- A Python environment at `Tools/KeyWestPython/Scripts/python.exe`, with NumPy, Pillow and Shapely 2.2; pyproj and rasterio are needed for optional geographic work.
- Unreal Engine at its detected/default location, or an explicit `-EngineRoot` argument.

Install these tools separately or adapt those paths for your machine. Tools are excluded from the downloads.

The detail workflow is in `Scripts/KeyWestDetail.ps1`: `Generate` exports main art, `Prepare` imports/authors the scene, `Ground` explicitly fetches/validates/prepares ground imagery, `Reflections` refreshes reflections, and `Package` cooks the game. These actions are for development, not the ordinary first-run path. The editor-assets archive includes the original-content baseline and authoring record needed by these guards.

Preserve hand edits in separate assets or back them up before regeneration. Replacing generated meshes/materials/maps can overwrite artist edits. The original scene and detail scene use separate asset namespaces.

Source data and license records live in `Art/KeyWest/Data`, `Art/KeyWestDetail/Ground/Data`, `Art/Textures/CC0` and `Art/KeyWestDetail/Textures/CC0`. Keep these records with derived exports. Unreal loads saved assets during normal play; it does not fetch imagery or invoke Blender.
