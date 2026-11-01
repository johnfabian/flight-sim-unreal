[CmdletBinding()]
param(
    [ValidateSet('Build','Prepare','Materials','Views','Reflections','Play','Editor','Package','Benchmark','Capture')][string]$Action='Play',
    [ValidateSet('Quality','Performance')][string]$Preset='Quality',
    [ValidateSet('Auto','Editor','Package')][string]$RunFrom='Auto',
    [string]$EngineRoot=$env:UE_ROOT,
    [switch]$RegenerateArt,
    [switch]$RebuildLayout,
    [switch]$RegenerateMaterials,
    [ValidateRange(0.5,8.0)][double]$SunIntensity=3.2,
    [ValidateRange(0.1,2.0)][double]$SkyIntensity=0.45
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$project=Join-Path $root 'Aeronaut.uproject'
$artifacts=Join-Path $root 'artifacts/keywest'
New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
if(-not $EngineRoot) { $EngineRoot='C:\Program Files\Epic Games\UE_5.8' }
$editor=Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor.exe'
$cmdEditor=Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$map='/Game/KeyWest/KeyWest'
$mapFile=Join-Path $root 'Content/KeyWest/KeyWest.umap'
$package=Join-Path $root 'Builds/KeyWest/Windows/Aeronaut.exe'
$python=Join-Path $root 'Tools/KeyWestPython/Scripts/python.exe'
$author=Join-Path $PSScriptRoot 'create_keywest.py'
if($Action -in @('Build','Prepare')) {
    & (Join-Path $PSScriptRoot 'Unreal.ps1') -Action Build -EngineRoot $EngineRoot
    if($Action -eq 'Build') { return }
}
if($Action -in @('Prepare','Materials')) {
    if(-not(Test-Path -LiteralPath (Join-Path $root 'Art/KeyWest/Data/scene.json'))) { throw 'Completed geographic data are missing. Run Art/FetchKeyWestData.py first.' }
    if(-not(Test-Path -LiteralPath $python)) { throw 'Key West Python tools are missing.' }
    if($RegenerateArt -or -not(Test-Path -LiteralPath (Join-Path $root 'Art/KeyWest/Exports/assets.json'))) {
        $blender=Join-Path $root 'Tools/blender-4.5.15-windows-x64/blender.exe'
        & $blender --background --factory-startup --python (Join-Path $root 'Art/GenerateKeyWest.py') -- --root $root
        if($LASTEXITCODE -ne 0) { throw 'Key West Blender generation failed.' }
    }
    & $python $author --environment $root
    if($LASTEXITCODE -ne 0) { throw 'Key West environment preparation failed.' }
    if($RebuildLayout -and (Test-Path -LiteralPath $mapFile)) {
        $backup=Join-Path $artifacts ('scene-before-regeneration-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
        New-Item -ItemType Directory -Path $backup | Out-Null
        foreach($name in @('KeyWest.umap','KeyWest_BuiltData.uasset')) {
            $source=Join-Path $root ('Content/KeyWest/'+$name)
            if(Test-Path -LiteralPath $source) {
                $resolved=(Resolve-Path -LiteralPath $source).Path
                $expected=(Join-Path $root 'Content/KeyWest')+[IO.Path]::DirectorySeparatorChar
                if(-not $resolved.StartsWith($expected,[StringComparison]::OrdinalIgnoreCase)) { throw 'Key West backup target is outside the new map directory.' }
                Move-Item -LiteralPath $resolved -Destination (Join-Path $backup $name)
            }
        }
    }
    $log=Join-Path $artifacts 'content.log'
    $arguments=@($project,'-run=pythonscript',('-script='+$author),'-unattended','-nop4','-nullrhi',('-abslog='+$log))
    if($RebuildLayout) { $arguments+='-KeyWestRebuild' }
    if($RegenerateMaterials) { $arguments+='-KeyWestMaterials' }
    if($Action -eq 'Materials') { $arguments+='-KeyWestMaterialsOnly' }
    & $cmdEditor @arguments
    $marker=if($Action -eq 'Materials') {'AERONAUT_KEYWEST_MATERIALS_READY'} else {'AERONAUT_KEYWEST_CONTENT_READY'}
    if($LASTEXITCODE -ne 0 -or -not(Select-String -LiteralPath $log -Pattern $marker -Quiet)) { throw "Key West authoring failed. Inspect $log" }
    return
}
if(-not(Test-Path -LiteralPath $mapFile)) { throw 'Prepared Key West map missing. Run Scripts\KeyWest.ps1 -Action Prepare.' }
if($Action -eq 'Views') {
    $log=Join-Path $artifacts 'views.log'
    $viewArguments=@($project,'-run=pythonscript',('-script='+$author),'-KeyWestViewsOnly','-nullrhi','-unattended','-nop4',('-abslog='+$log))
    if($PSBoundParameters.ContainsKey('SunIntensity')) { $viewArguments+=('-KeyWestSun='+$SunIntensity.ToString('0.###',[Globalization.CultureInfo]::InvariantCulture)) }
    if($PSBoundParameters.ContainsKey('SkyIntensity')) { $viewArguments+=('-KeyWestSky='+$SkyIntensity.ToString('0.###',[Globalization.CultureInfo]::InvariantCulture)) }
    & $cmdEditor @viewArguments
    if($LASTEXITCODE -ne 0 -or -not(Select-String -LiteralPath $log -Pattern 'AERONAUT_KEYWEST_VIEWS_READY' -Quiet)) { throw "Key West view preparation failed. Inspect $log" }
    return
}
if($Action -eq 'Reflections') {
    $log=Join-Path $artifacts 'reflections.log'
    & $cmdEditor $project -run=pythonscript ('-script='+$author) -KeyWestReflections -allowcommandletrendering -dx11 -unattended -nop4 ('-abslog='+$log)
    if($LASTEXITCODE -ne 0 -or -not(Select-String -LiteralPath $log -Pattern 'AERONAUT_KEYWEST_REFLECTIONS_READY' -Quiet)) { throw "Key West reflection preparation failed. Inspect $log" }
    return
}
if($Action -eq 'Package') {
    $uat=Join-Path $EngineRoot 'Engine/Build/BatchFiles/RunUAT.bat'
    & $uat BuildCookRun "-project=$project" -noP4 -utf8output -platform=Win64 -clientconfig=Development -build -cook -stage -pak -archive "-archivedirectory=$(Join-Path $root 'Builds/KeyWest')" '-map=/Game/KeyWest/KeyWest+/Game/Showcase/CoastalShowcase+/Game/Aeronaut/FlightMap' -prereqs
    if($LASTEXITCODE -ne 0 -or -not(Test-Path -LiteralPath $package)) { throw 'Key West Windows packaging failed.' }
    $packageRoot=Split-Path $package -Parent
    # The existing default map remains unchanged for the old game. The dedicated
    # launchers pass KeyWest explicitly to the standalone executable.
    @'
@echo off
"%~dp0Aeronaut.exe" /Game/KeyWest/KeyWest -dx11 -windowed -ResX=1280 -ResY=720 -AeronautPreset=Quality
'@ | Set-Content -LiteralPath (Join-Path $packageRoot 'PlayKeyWest.cmd') -Encoding ascii
    @'
@echo off
"%~dp0Aeronaut.exe" /Game/KeyWest/KeyWest -dx11 -windowed -ResX=1280 -ResY=720 -AeronautPreset=Performance
'@ | Set-Content -LiteralPath (Join-Path $packageRoot 'PlayKeyWestPerformance.cmd') -Encoding ascii
    $dataDestination=Join-Path $packageRoot 'KeyWest-source-data'
    New-Item -ItemType Directory -Force -Path $dataDestination | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $root 'Art/KeyWest/Data') | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $dataDestination -Recurse -Force }
    Copy-Item -LiteralPath (Join-Path $root 'Art/KeyWest/README_DATA.md') -Destination (Join-Path $packageRoot 'GEOGRAPHIC-DATA.md')
    Copy-Item -LiteralPath (Join-Path $root 'Art/Textures/CC0/manifest.json') -Destination (Join-Path $packageRoot 'CC0-asset-records.json')
    @'
KEY WEST / STOCK ISLAND - Windows Development

Run PlayKeyWest.cmd (Quality) or PlayKeyWestPerformance.cmd.
Keep the entire Windows folder together. No editor or network is required.
Enter/A starts airborne flight. T/View starts the geographic guided tour.
C/Y camera, P/Esc/Menu pause, R reset, F2 HUD, F3 timing, F4 preset.
S/W pitch, A/D bank, Q/E rudder, Shift/Ctrl power. Alt+F4 quits.
Controller: left stick fly, LB/RB rudder, RT/LT power.
Existing assisted controls are preserved; takeoff/landing are not implemented.
Quality is 1280x720 at 100% internal resolution, capped at 30 FPS.
Performance is 1280x720 at 85%, with reduced foliage/shadows.

Geographic layout: OpenStreetMap contributors, ODbL; source and derived data
are included in KeyWest-source-data with attribution and license records.
Land imagery: USGS/USDA NAIP public domain, local acquisition 2023-01-16.
Architecture and missing heights, flat island elevation, seabed depth/color,
airport tower, palms and boat placements are modeled rather than surveyed.
Original Blender art and editable Unreal source remain in the local project.
The sky/aircraft CC0 source records are in CC0-asset-records.json.
'@ | Set-Content -LiteralPath (Join-Path $packageRoot 'README.txt') -Encoding utf8
    return
}
$arguments=@($map,'-dx11','-windowed','-ResX=1280','-ResY=720','-nosplash',"-AeronautPreset=$Preset")
if($Action -eq 'Editor') {
    Start-Process -FilePath $editor -ArgumentList (@(('"{0}"' -f $project))+$arguments) -WorkingDirectory $root
    return
}
if($RunFrom -eq 'Package' -and -not(Test-Path -LiteralPath $package)) { throw 'Key West standalone package missing. Run Package first.' }
if($RunFrom -ne 'Editor' -and (Test-Path -LiteralPath $package)) { $exe=$package } else { $exe=$editor; $arguments=@(('"{0}"' -f $project))+$arguments+@('-game') }
if($Action -in @('Benchmark','Capture')) {
    $log=Join-Path $artifacts "$($Preset.ToLower())-$($Action.ToLower()).log"
    $arguments+=@('-AeronautBenchmark','-AeronautAutoTour','-AeronautShots','-AeronautSelfTest','-RenderOffScreen','-ForceRes','-unattended',('-abslog="{0}"' -f $log))
    if($exe -eq $editor) { $arguments+='-ini:Engine:[DevOptions.Shaders]:bAllowAsynchronousShaderCompiling=False' }
    if($Action -eq 'Capture') { $arguments+='-AeronautCaptureOnly' }
    $gpuProbe=$null
    try {
        $smi=Get-Command nvidia-smi -ErrorAction SilentlyContinue
        if($smi) { $gpuProbe=Start-Process -FilePath $smi.Source -ArgumentList '--query-gpu=timestamp,name,memory.used,utilization.gpu,temperature.gpu --format=csv -l 1' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifacts "$($Preset.ToLower())-$($Action.ToLower())-gpu.csv") -RedirectStandardError (Join-Path $artifacts 'gpu-probe-errors.log') }
        $game=Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru
        $game.WaitForExit()
        if($game.ExitCode -ne 0) { throw "Key West process exited $($game.ExitCode). Inspect $log" }
        $marker=if($Action -eq 'Capture') {'AERONAUT_CAPTURE_COMPLETE'} else {'AERONAUT_BENCHMARK_COMPLETE'}
        foreach($required in @($marker,'AERONAUT_SELFTEST_PASS','AERONAUT_RENDER_RESOLUTION internal=')) {
            if(-not(Select-String -LiteralPath $log -Pattern $required -Quiet)) { throw "Missing verification marker $required. Inspect $log" }
        }
        if(Select-String -LiteralPath $log -Pattern 'Failed to compile Material|Default Material will be used in game|AERONAUT_SELFTEST_FAILED' -Quiet) { throw "Key West runtime/material checks failed. Inspect $log" }
    } finally { if($gpuProbe -and -not $gpuProbe.HasExited) { Stop-Process -Id $gpuProbe.Id } }
    return
}
Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $root
