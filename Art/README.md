# Editable coastal art

`AeronautCoast.blend` contains the original aircraft and environment catalog, authored in metres. Blender 4.5.15 LTS is available locally in `Tools/blender-4.5.15-windows-x64`. The aircraft is approximately 11 metres across the wings. Exported FBX meshes, animation pivots and material slots are recorded in `Exports/assets.json`.

`GenerateShowcase.py` reproduces the original meshes, heightfield, UVs and baked aircraft surface normal. `MakeDialTextures.py` creates the original instrument atlas and shoreline mask. It requires Pillow (`python -m pip install Pillow`). Blender supplies its own NumPy. Generated artwork rasterizes the installed system font; font files are not distributed.

FBX exports temporarily reflect Y to compensate for Unreal's coordinate conversion. The editable source and pivot metadata retain X forward, Y right, Z up. Unreal imports centimetres. The pipeline checks a one-metre cube and an asymmetric marker at (1,2,3) metres; keep both checks when changing export settings.

The two pipeline meshes import into `/Game/Showcase/ImportProbe`, excluded from packaging. After changing the Airframe UVs, reimport its rebaked `AircraftNormal` texture as well as the FBX; `Scripts/reimport_aircraft.py` performs both steps with the required normal-map settings. Vegetation transparency uses the branch diffuse texture's fine needle alpha rather than the coarse region mask.

All downloaded images are CC0. `Textures/CC0/manifest.json` records each source, author, license, downloaded file, checksum and modification. It covers Poly Haven asphalt, forest floor, coastal rock, Pine Tree 01 bark/branch textures, and the cloud sky. No external tree meshes are included; the optimized conifers are original geometry. The source downloads are retained and are capped to the intended texture sizes during import.

Edit the Blender file and reimport selected FBX assets for artist work. Full procedural regeneration overwrites the generated `.blend`, FBX, textures, Unreal materials and level; preserve any manual edits before using it. Ordinary Play uses saved content and never runs Blender or builds lighting.

Full regeneration from the project root:

```powershell
.\Scripts\Showcase.ps1 -Action Prepare -RegenerateArt -RegenerateScene
.\Scripts\Showcase.ps1 -Action Bake
.\Scripts\Showcase.ps1 -Action Package
```

`Prepare` without regeneration flags preserves existing meshes, materials, map placement and Blueprint aircraft settings. `-RebuildLayout` replaces the entire generated map, including Landscape, lighting, route and baked data, and resets aircraft defaults; it retains imported meshes and materials. `-RegenerateMaterials` explicitly rebuilds generated material graphs. Previous generated maps are preserved under `artifacts/scene-before-regeneration-*` before replacement.
