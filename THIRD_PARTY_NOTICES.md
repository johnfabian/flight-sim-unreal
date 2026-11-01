# Third-party sources and runtime notices

Original project code and artwork have no project-wide open-source license selected. The following external components retain their own terms.

## Unreal Engine

Built with Unreal Engine 5.8.4. Unreal Engine is a trademark or registered trademark of Epic Games, Inc. in the United States of America and elsewhere. Unreal Engine, Copyright 1998–2026, Epic Games, Inc. All rights reserved.

Engine use and redistribution are governed by [Epic's Unreal Engine agreement](https://www.unrealengine.com/eula/unreal). Obtain the engine through Epic for source development. Engine source, editor applications, debug symbols and development installations are not included in this repository or its asset archive. The Windows game includes its required runtime components and their supplied notices.

## OpenStreetMap geographic data

© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). Raw and derived geographic data retain [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) terms and attribution. Source and derived datasets accompany the game/editor downloads under `KeyWest-source-data`, `KeyWestDetail-data` or their `Art` source directories. Source records identify the actual requests and modifications. Buildings and elevations are inferred for this visual prototype.

## USGS/USDA aerial imagery

Public-domain NAIP imagery, acquired January 16, 2023. Service and image records are retained in the downloads, including `Ground-imagery-records.json` and `Art/KeyWestDetail/Ground/Data/imagery.json`. The [USGS service metadata](https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer) identifies the imagery source. This is not current navigation data.

## Poly Haven textures

Downloaded textures are [CC0](https://polyhaven.com/license). The detailed manifest records each author, source URL, downloaded filename, hash and modifications. Records are included as `Original-CC0-records.json` and `KeyWestDetail-CC0-records.json` with the game, and under `Art/Textures/CC0` and `Art/KeyWestDetail/Textures/CC0` with the editable assets.

Sources include asphalt, forest floor, coastal rock, pine bark/branch and cloud textures, plus Painted Plaster Wall (Amal Kumar), White Planks Clean (Rob Tuytel) and Corrugated Iron (Dimitrios Savva / Jenelle van Heerden). Tree and aircraft meshes are original geometry.

## Optional browser infrastructure

EpicGamesExt/PixelStreamingInfrastructure is a separately installed MIT-licensed dependency. Its upstream source and installed packages are not vendored here. Keep its upstream LICENSE when installing it; see [dependency instructions](Streaming/DEPENDENCIES.md).

## Runtime redistributables

The Windows download retains supplied engine/third-party runtime licenses and the Microsoft Visual C++ runtime installer. Those components are governed by their respective supplied terms, rather than a project-source license.
