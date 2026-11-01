[CmdletBinding()]
param(
    [ValidateSet('Build','Prepare','Surfaces','Bake','Reflections','Play','Editor','Package','Benchmark','Capture')][string]$Action='Play',
    [ValidateSet('Quality','Performance')][string]$Preset='Quality',
    [ValidateSet('Auto','Editor','Package')][string]$RunFrom='Auto',
    [string]$EngineRoot=$env:UE_ROOT,
    [switch]$RegenerateArt,
    [switch]$RegenerateScene,
    [switch]$RebuildLayout,
    [switch]$RegenerateMaterials,
    [string[]]$UpdateMaterials=@()
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$project=Join-Path $root 'Aeronaut.uproject'
$artifacts=Join-Path $root 'artifacts'
New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
if(-not $EngineRoot) { $EngineRoot='C:\Program Files\Epic Games\UE_5.8' }
$editor=Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor.exe'
$cmdEditor=Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$map='/Game/Showcase/CoastalShowcase'
$mapFile=Join-Path $root 'Content/Showcase/CoastalShowcase.umap'
$package=Join-Path $root 'Builds/CoastalShowcase/Windows/Aeronaut.exe'
if($Action -in @('Build','Prepare')) {
    & (Join-Path $PSScriptRoot 'Unreal.ps1') -Action Build -EngineRoot $EngineRoot
    if($Action -eq 'Build') { return }
}
if($Action -eq 'Prepare') {
    $blender=Join-Path $root 'Tools/blender-4.5.15-windows-x64/blender.exe'
    if(-not(Test-Path $blender) -or -not(Test-Path (Join-Path $root 'Art/Textures/CC0/manifest.json'))) { & (Join-Path $PSScriptRoot 'GetShowcaseAssets.ps1') }
    if($RegenerateArt -or -not(Test-Path (Join-Path $root 'Art/Exports/assets.json'))) {
        & $blender --background --factory-startup --python (Join-Path $root 'Art/GenerateShowcase.py')
        if($LASTEXITCODE -ne 0) { throw 'Blender generation failed.' }
        & python (Join-Path $root 'Art/MakeDialTextures.py')
        if($LASTEXITCODE -ne 0) { throw 'Instrument artwork generation failed.' }
    }
    $contentLog=Join-Path $artifacts 'showcase-content.log'
    if(($RegenerateScene -or $RebuildLayout) -and (Test-Path -LiteralPath (Join-Path $root 'Content/Showcase/CoastalShowcase.umap'))) {
        $backup=Join-Path $artifacts ('scene-before-regeneration-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
        New-Item -ItemType Directory -Path $backup | Out-Null
        foreach($name in @('CoastalShowcase.umap','CoastalShowcase_BuiltData.uasset')) {
            $source=Join-Path $root ('Content/Showcase/'+$name)
            if(Test-Path -LiteralPath $source) {
                $resolved=(Resolve-Path -LiteralPath $source).Path
                if(-not $resolved.StartsWith($root+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Scene backup path is outside the project.' }
                Move-Item -LiteralPath $resolved -Destination (Join-Path $backup $name)
            }
        }
    }
    $argsList=@($project,'-run=pythonscript',('-script='+ (Join-Path $PSScriptRoot 'create_showcase.py')),'-unattended','-nop4','-nullrhi',('-abslog='+$contentLog))
    if($RegenerateScene) { $argsList+='-ShowcaseRegenerate' }
    if($RebuildLayout) { $argsList+='-ShowcaseRebuildLayout' }
    if($RegenerateMaterials) { $argsList+='-ShowcaseRegenerateMaterials' }
    foreach($material in $UpdateMaterials) {
        if($material -notmatch '^[A-Za-z][A-Za-z0-9]*$') { throw 'Invalid material name.' }
        $argsList+=('-ShowcaseMaterial='+$material)
    }
    & $cmdEditor @argsList
    if($LASTEXITCODE -ne 0 -or -not(Select-String $contentLog -Pattern 'AERONAUT_SHOWCASE_CONTENT_READY' -Quiet)) { throw "Showcase preparation failed. Inspect $contentLog" }
    return
}
if(-not(Test-Path $mapFile)) { throw 'Showcase content is missing. Run Scripts\Showcase.ps1 -Action Prepare first.' }
if($Action -eq 'Surfaces') {
    $log=Join-Path $artifacts 'coastal-surfaces/material-update.log'
    New-Item -ItemType Directory -Force -Path (Split-Path $log -Parent) | Out-Null
    $surfaceArgs=@($project,'-run=pythonscript',('-script='+ (Join-Path $PSScriptRoot 'update_coastal_surfaces.py')),'-nullrhi','-unattended','-nop4',('-abslog='+$log))
    foreach($material in $UpdateMaterials) {
        if($material -notin @('Landscape','Rock','Foliage','Water')) { throw "Unknown coastal surface $material" }
        $surfaceArgs+=('-ShowcaseSurface='+$material)
    }
    & $cmdEditor @surfaceArgs
    if($LASTEXITCODE -ne 0 -or -not(Select-String $log -Pattern 'AERONAUT_COASTAL_SURFACES_READY' -Quiet)) { throw "Surface update failed. Inspect $log" }
    return
}
if($Action -eq 'Reflections') {
    $log=Join-Path $artifacts 'showcase-direct-reflections.log'
    & $cmdEditor $project -run=pythonscript ('-script='+ (Join-Path $PSScriptRoot 'build_showcase_reflections.py')) -allowcommandletrendering -dx11 -unattended -nop4 ('-abslog='+$log)
    if($LASTEXITCODE -ne 0 -or -not(Select-String $log -Pattern 'AERONAUT_REFLECTIONS_SAVED' -Quiet)) { throw "Reflection build failed. See $log" }
    return
}
if($Action -eq 'Bake') {
    $log=Join-Path $artifacts 'showcase-lighting.log'
    $started=(Get-Date).ToUniversalTime()
    & $cmdEditor $project -run=ResavePackages -buildlighting -buildreflectioncaptures -quality=Production -allowcommandletrendering "-map=$map" -ProjectOnly -IgnoreChangelist -dx11 -unattended -nop4 "-abslog=$log"
    if($LASTEXITCODE -ne 0) { throw "Lightmass failed. See $log" }
    $data=Join-Path $root 'Content/Showcase/CoastalShowcase_BuiltData.uasset'
    if(-not(Test-Path -LiteralPath $data) -or (Get-Item -LiteralPath $data).LastWriteTimeUtc -lt $started) { throw 'Lightmass did not save fresh lighting data.' }
    if(Select-String $log -Pattern 'Skipping Lighting Build|\[REPORT\] Failed building lighting|Lighting build failed|Failed to save package' -Quiet) { throw "Lighting was skipped or failed. See $log" }
    if(-not(Select-String $log -Pattern 'Lights with unbuilt interactions: 0' -Quiet) -or -not(Select-String $log -Pattern 'Primitives with unbuilt interactions: 0' -Quiet)) { throw "Zero unbuilt lighting interactions were not verified. See $log" }
    return
}
if($Action -eq 'Package') {
    if(-not(Test-Path -LiteralPath (Join-Path $root 'Content/Showcase/CoastalShowcase_BuiltData.uasset'))) { throw 'Saved lighting is missing. Run Bake before packaging.' }
    $uat=Join-Path $EngineRoot 'Engine/Build/BatchFiles/RunUAT.bat'
    & $uat BuildCookRun "-project=$project" -noP4 -utf8output -platform=Win64 -clientconfig=Development -build -cook -stage -pak -archive "-archivedirectory=$(Join-Path $root 'Builds/CoastalShowcase')" '-map=/Game/Showcase/CoastalShowcase+/Game/Aeronaut/FlightMap' -prereqs
    if($LASTEXITCODE -ne 0 -or -not(Test-Path $package)) { throw 'Windows packaging failed. Inspect the AutomationTool log.' }
    $packageRoot=Split-Path $package -Parent
    Copy-Item -LiteralPath (Join-Path $root 'Art/Textures/CC0/manifest.json') -Destination (Join-Path $packageRoot 'CC0-asset-records.json')
    @'
NORTH COAST FLIGHT SHOWCASE - Windows Development

Run Aeronaut.exe. Unreal Editor is not required.
Starts airborne. Enter/A starts flight. T/View starts the 150-second tour.
C/Y changes chase/cockpit/wing camera. P/Esc/Menu pauses. R resets.
S/W pitch, A/D bank, Q/E rudder, Shift/Ctrl power.
Controller: left stick fly, LB/RB rudder, RT/LT power.
F2 hides HUD. F3 shows timing. F4 switches Quality/Performance.
Alt+F4 quits. Plug the laptop into power for a representative test.

Quality: 1280x720, 100% internal resolution, 30 FPS cap.
Performance: 1280x720, 85% internal resolution, reduced vegetation/shadows.
This prototype has assisted airborne flight; takeoff/landing are not implemented.

Keep the entire Windows folder together. If needed, install the bundled
Microsoft runtime from Engine/Extras/Redist/en-us/UEPrereqSetup_x64.exe.
External asset provenance is in CC0-asset-records.json.
Editable Blender/Unreal sources and full results remain in the source project.
'@ | Set-Content -LiteralPath (Join-Path $packageRoot 'README.txt') -Encoding utf8
    return
}
$argsList=@($map,'-dx11','-windowed','-ResX=1280','-ResY=720','-nosplash',"-AeronautPreset=$Preset")
if($Action -eq 'Editor') {
    Start-Process -FilePath $editor -ArgumentList (@(('"{0}"' -f $project))+$argsList) -WorkingDirectory $root
    return
}
if($RunFrom -eq 'Package' -and -not(Test-Path $package)) { throw 'The standalone package is missing. Run Package first.' }
if($RunFrom -ne 'Editor' -and (Test-Path $package)) { $exe=$package } else { $exe=$editor; $argsList=@(('"{0}"' -f $project))+$argsList+@('-game') }
Write-Host "Launching $exe (built $((Get-Item -LiteralPath $exe).LastWriteTime))"
if($Action -in @('Benchmark','Capture')) {
    $log=Join-Path $artifacts "showcase-$($Preset.ToLower())-$($Action.ToLower()).log"
    $argsList+=@('-AeronautBenchmark','-AeronautAutoTour','-AeronautShots','-AeronautSelfTest','-RenderOffScreen','-ForceRes','-unattended',('-abslog="{0}"' -f $log))
    if($exe -eq $editor) { $argsList+='-ini:Engine:[DevOptions.Shaders]:bAllowAsynchronousShaderCompiling=False' }
    if($Action -eq 'Capture') { $argsList+='-AeronautCaptureOnly' }
    $gpuProbe=$null
    try {
        $smi=Get-Command nvidia-smi -ErrorAction SilentlyContinue
        if($smi) { $gpuProbe=Start-Process -FilePath $smi.Source -ArgumentList '--query-gpu=timestamp,name,memory.used,utilization.gpu,temperature.gpu --format=csv -l 1' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifacts "showcase-$($Preset.ToLower())-gpu.csv") -RedirectStandardError (Join-Path $artifacts 'gpu-probe-errors.log') }
        $game=Start-Process -FilePath $exe -ArgumentList $argsList -WorkingDirectory $root -WindowStyle Hidden -PassThru
        $game.WaitForExit()
        if($game.ExitCode -ne 0) { throw "Showcase process exited $($game.ExitCode). Inspect $log" }
        $marker=if($Action -eq 'Capture') {'AERONAUT_CAPTURE_COMPLETE'} else {'AERONAUT_BENCHMARK_COMPLETE'}
        if(-not(Select-String $log -Pattern $marker -Quiet)) { throw "Expected completion marker missing. Inspect $log" }
        if(-not(Select-String $log -Pattern 'AERONAUT_SELFTEST_PASS' -Quiet)) { throw "Showcase runtime checks failed. Inspect $log" }
        if(-not(Select-String $log -Pattern 'AERONAUT_RENDER_RESOLUTION internal=' -Quiet)) { throw "Actual render resolution was not verified. Inspect $log" }
        if(Select-String $log -Pattern 'Failed to compile Material|Default Material will be used in game' -Quiet) { throw "A material failed to compile. Inspect $log" }
    } finally { if($gpuProbe -and -not $gpuProbe.HasExited) { Stop-Process -Id $gpuProbe.Id } }
    return
}
# Visible interactive game requested by the user. Ordinary play never generates art or lighting.
Start-Process -FilePath $exe -ArgumentList $argsList -WorkingDirectory $root
