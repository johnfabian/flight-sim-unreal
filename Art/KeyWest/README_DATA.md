# Key West offline geographic data

Run the isolated fetcher with the locally installed GIS environment:

```powershell
.\Tools\KeyWestPython\Scripts\python.exe .\Art\FetchKeyWestData.py --root .
```

The script writes only `Art/KeyWest/Data` and `artifacts/keywest/data-validation.json`. Requests and original responses are cached; game/editor play needs no data connection. `scene-vectors.json` is an intermediate geometry checkpoint; `scene.json` with `ready:true` is the complete art-pipeline input.

The frame is a 12,096 m square around WGS84 (24.565, -81.77). Local coordinates are metres, X=north, Y=east, Z=up. The affine scales are 110766.43773511577 m/degree north and 101302.57543811084 m/degree east. Both raster exports and vectors use this exact approximation. Image U increases east; V increases south. Imagery filenames are relative to `Art/KeyWest/Data`. This is a local visual map, not a surveyed coordinate system.

USGS/USDA NAIP imagery is public domain, as stated by the actual [USGS service metadata](https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer). Eight catalog raster IDs 34394–34401 are pinned to acquisition 2023-01-16 (native 0.3 m; catalog program Year is 2022). Sixteen 2048 px natural-color JPEG exports each cover 3024 m, about 1.477 m/pixel. Returned geographic extents are verified with aspect-ratio adjustment disabled. Save the metadata/request/hash records, not the transient server-generated image URLs alone. Aerial imagery must be used only on actual land; offshore photographs have visible mosaic seams.

Buildings, roads, piers, runways, landmarks and coastlines come from the official [OpenStreetMap read API](https://wiki.openstreetmap.org/wiki/API_v0.6), cached as original JSON. The [copyright page](https://www.openstreetmap.org/copyright) identifies ODbL 1.0 and attribution obligations. Keep raw and derived geographic data under ODbL, retain the supplied license and attribution, and show ©OpenStreetMap contributors with the copyright link in the game credits/data information. Original architectural art is separate from this derived geographic database.

Coastlines are joined in their original direction before clipping; clockwise water rings and mapped inland water are subtracted. The official API extract adapts to its node limit. Real endpoint-connected coast ways outside the initial buffer are fetched to close relevant islands (including Boca Chica); continuation is bounded to 64 rounds and a 35 km local radius. An unresolved chain touching the frame stops the pipeline rather than being replaced by a fictional closure. Constrained triangulations preserve courtyard and water holes, with area/coverage validation. The source data retain OSM node IDs, tags and object identifiers.

Building height tags or levels are used where present; other heights are explicitly inferred low-rise defaults. Ground and landmark elevations are modeled flat at 2 m above the game sea level. No surveyed DEM or measured bathymetry is claimed. NOAA has an optional [2016 Key West 1 m topobathymetric DEM](https://coast.noaa.gov/htdata/raster2/elevation/NGS_FL_key_west_DEM_2016_6366/) of approximately 485 MB, but this bounded initial pipeline does not use it.

Python dependencies are NumPy, Pillow, Shapely 2.2 (with constrained Delaunay support), pyproj and rasterio; the last two are reserved for optional future DEM work. No API credentials, certificate bypass or paid imagery are used. A failed/incomplete geographic fetch stops the pipeline and writes diagnostics. Completion requires at least five named real controls, valid land/building triangulations, road/runway geometry, exact raster extents and nonblank imagery over land.
