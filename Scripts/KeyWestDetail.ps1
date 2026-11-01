[CmdletBinding()]
param(
    [ValidateSet('Build','Generate','Ground','Prepare','Materials','Reflections','Play','Editor','Package','Benchmark','Capture')][string]$Action='Play',
    [ValidateSet('Quality','Performance')][string]$Preset='Quality',
    [string]$EngineRoot=$env:UE_ROOT,
    [switch]$RegenerateArt,
    [switch]$RegenerateMaterials
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$project=Join-Path $root 'Aeronaut.uproject'
$artifacts=Join-Path $root 'artifacts/keywest-detail'
if(-not $EngineRoot) { $EngineRoot='C:\Program Files\Epic Games\UE_5.8' }
$editor=Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor.exe'
$cmdEditor=Join-Path $EngineRoot 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$python=Join-Path $root 'Tools/KeyWestPython/Scripts/python.exe'
$blender=Join-Path $root 'Tools/blender-4.5.15-windows-x64/blender.exe'
$author=Join-Path $PSScriptRoot 'create_keywest_detail.py'
$map='/Game/KeyWestDetail/KeyWestDetail'
$mapFile=Join-Path $root 'Content/KeyWestDetail/KeyWestDetail.umap'
$package=Join-Path $root 'Builds/KeyWestDetail/Windows/Aeronaut.exe'
$unused=[Math]::Max(1,[Environment]::ProcessorCount-2)
$shaderLimits=@(('-ini:Engine:[DevOptions.Shaders]:NumUnusedShaderCompilingThreads='+$unused),('-ini:Engine:[DevOptions.Shaders]:NumUnusedShaderCompilingThreadsDuringGame='+$unused),'-ini:Engine:[DevOptions.Shaders]:ShaderCompilerCoreCountThreshold=999')
New-Item -ItemType Directory -Force -Path $artifacts | Out-Null

function Build-DetailEditor {
    $build=Join-Path $EngineRoot 'Engine/Build/BatchFiles/Build.bat'
    & $build AeronautEditor Win64 Development "-Project=$project" -WaitMutex -NoHotReloadFromIDE -MaxParallelActions=2
    if($LASTEXITCODE-ne0) { throw 'Detail editor build failed.' }
}

function Compare-OldContent {
    $baseline=Import-Csv -LiteralPath (Join-Path $artifacts 'baseline/content-sha256.csv')
    if($baseline.Count-ne511) { throw 'The complete511-file pre-feature Content baseline is required.' }
    @($baseline | Where-Object { $file=Join-Path $root $_.Path; -not(Test-Path -LiteralPath $file) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash-ne$_.SHA256 })
}
function Backup-Maps {
    $backup=Join-Path $artifacts ('backups/'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    foreach($entry in @(@('old','Content/KeyWest','KeyWest'),@('new','Content/KeyWestDetail','KeyWestDetail'))) {
        $dest=Join-Path $backup $entry[0]; New-Item -ItemType Directory -Force -Path $dest|Out-Null
        foreach($suffix in @('.umap','_BuiltData.uasset')) {
            $source=Join-Path $root ($entry[1]+'/'+$entry[2]+$suffix)
            if(Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $dest ($entry[2]+$suffix)) }
        }
    }
    return $backup
}
function Restore-MapBackups([string]$Backup,[switch]$IncludeTarget) {
    foreach($name in @('KeyWest.umap','KeyWest_BuiltData.uasset')) {
        $copy=Join-Path $Backup ('old/'+$name)
        if(Test-Path -LiteralPath $copy) { Copy-Item -LiteralPath $copy -Destination (Join-Path $root ('Content/KeyWest/'+$name)) -Force }
    }
    if($IncludeTarget) {
        foreach($name in @('KeyWestDetail.umap','KeyWestDetail_BuiltData.uasset')) {
            $copy=Join-Path $Backup ('new/'+$name)
            if(Test-Path -LiteralPath $copy) { Copy-Item -LiteralPath $copy -Destination (Join-Path $root ('Content/KeyWestDetail/'+$name)) -Force }
        }
    }
}
if($Action -eq 'Build') {
    Build-DetailEditor
    return
}
if($Action-eq'Ground') {
    if(-not(Test-Path -LiteralPath $mapFile)) { throw 'Prepare the detail map before adding ground detail.' }
    $ground=Join-Path $root 'Art/KeyWestGround.py'
    & $python -B $ground --fetch --root $root
    if($LASTEXITCODE-ne0) { throw 'Verified public aerial imagery preparation failed.' }
    & $blender --background --threads 2 --factory-startup --python-exit-code 1 --python $ground -- --export --root $root
    if($LASTEXITCODE-ne0-or-not(Test-Path -LiteralPath (Join-Path $root 'Art/KeyWestDetail/Ground/Exports/assets.json'))) { throw 'Ground detail export failed.' }
}
if($Action -eq 'Generate' -or ($Action-eq'Prepare'-and($RegenerateArt-or-not(Test-Path -LiteralPath (Join-Path $root 'Art/KeyWestDetail/Exports/assets.json'))))) {
    & $python (Join-Path $root 'Art/KeyWestBoats.py') --scene (Join-Path $root 'Art/KeyWest/Data/scene.json') --output (Join-Path $root 'Art/KeyWestDetail/Data/fleet.json')
    if($LASTEXITCODE-ne0) { throw 'Fleet generation failed.' }
    & $python (Join-Path $root 'Art/GenerateKeyWestDetail.py') --root $root --validate-inputs
    if($LASTEXITCODE-ne0) { throw 'Exact incoming fleet validation failed.' }
    & $blender --background --threads 2 --factory-startup --python-exit-code 1 --python (Join-Path $root 'Art/GenerateKeyWestDetail.py') -- --root $root
    if($LASTEXITCODE-ne0) { throw 'Isolated detail geometry export failed.' }
    if(-not(Test-Path -LiteralPath (Join-Path $root 'Art/KeyWestDetail/Exports/assets.json')) -or -not(Test-Path -LiteralPath (Join-Path $root 'Art/KeyWestDetail/KeyWestDetail.blend'))) { throw 'Detail geometry outputs are missing.' }
    if($Action-eq'Generate') { return }
}
if($Action-in@('Prepare','Materials','Reflections','Ground')) {
    if(@(Compare-OldContent).Count) { throw 'Old Content differs before authoring; preserve and reconcile the baseline.' }
    # Reflections is an explicit off-screen RHI action. Ordinary Prepare stays
    # null-RHI; ordinary Play only loads the already prepared content.
    if($Action-eq'Prepare') { Build-DetailEditor }
    $backup=Backup-Maps
    $log=Join-Path $artifacts ($Action.ToLower()+'.log')
    $arguments=@($project,'-run=pythonscript',('-script='+$author),'-unattended','-nop4',('-abslog='+$log),('-KeyWestDetailBackup='+$backup))
    $arguments+=$shaderLimits
    if($Action-eq'Reflections') { $arguments+=@('-KeyWestDetailReflections','-allowcommandletrendering','-dx11','-RenderOffScreen','-nosplash') } else { $arguments+='-nullrhi' }
    if($Action-eq'Materials') { $arguments+='-KeyWestDetailMaterialsOnly' }
    if($Action-eq'Ground') { $arguments+='-KeyWestDetailGroundOnly' }
    if($RegenerateMaterials) { $arguments+='-KeyWestDetailMaterials' }
    & $cmdEditor @arguments
    $exitCode=$LASTEXITCODE
    $changed=@(Compare-OldContent)
    if($changed.Count) {
        # The commandlet has exited before restoration, so no loaded world can
        # rewrite the old registry afterward. Never accept a changed baseline.
        Restore-MapBackups $backup -IncludeTarget
        $changed|Export-Csv -LiteralPath (Join-Path $artifacts 'rejected-old-content-drift.csv') -NoTypeInformation
        throw 'Old Content drifted. Exact map backups restored; stop and reconcile every remaining mismatch.'
    }
    $marker=switch($Action) { 'Materials'{'AERONAUT_KEYWEST_DETAIL_MATERIALS_READY'} 'Reflections'{'AERONAUT_KEYWEST_DETAIL_REFLECTIONS_READY'} 'Ground'{'AERONAUT_KEYWEST_DETAIL_GROUND_READY'} default{'AERONAUT_KEYWEST_DETAIL_CONTENT_READY'} }
    if($exitCode-ne0-or-not(Select-String -LiteralPath $log -Pattern $marker -Quiet)) {
        Restore-MapBackups $backup -IncludeTarget
        throw "Detail authoring failed; map backups restored. Inspect $log"
    }
    return
}
if($Action-in@('Package','Editor')-and-not(Test-Path -LiteralPath $mapFile)) { throw 'Prepared detail map missing. Explicitly run Prepare first.' }
if($Action-eq'Package') {
    if(-not(Test-Path -LiteralPath (Join-Path $artifacts 'authored-scene.json'))) { throw 'A successful detail authoring record is required before packaging.' }
    $uat=Join-Path $EngineRoot 'Engine/Build/BatchFiles/RunUAT.bat'
    $cookLimits='-AdditionalCookerOptions=-nullrhi -unattended -nosplash '+($shaderLimits-join' ')
    & $uat BuildCookRun "-project=$project" -noP4 -utf8output -unattended -platform=Win64 -clientconfig=Development -build -cook -stage -pak -archive "-archivedirectory=$(Join-Path $root 'Builds/KeyWestDetail')" '-map=/Game/KeyWestDetail/KeyWestDetail+/Game/KeyWest/KeyWest+/Game/Showcase/CoastalShowcase+/Game/Aeronaut/FlightMap' '-UbtArgs=-MaxParallelActions=2' $cookLimits -prereqs
    if($LASTEXITCODE-ne0-or-not(Test-Path -LiteralPath $package)) { throw 'Detail package failed.' }
    $packageRoot=Split-Path $package -Parent
    foreach($entry in @(@('PlayKeyWest.cmd','Quality'),@('PlayKeyWestPerformance.cmd','Performance'))) {
        @('@echo off',('"%~dp0Aeronaut.exe" /Game/KeyWestDetail/KeyWestDetail -dx11 -windowed -ResX=1280 -ResY=720 -AeronautPreset='+$entry[1])) | Set-Content -LiteralPath (Join-Path $packageRoot $entry[0]) -Encoding ascii
    }
    foreach($entry in @(@('Art/KeyWest/Data','KeyWest-source-data'),@('Art/KeyWestDetail/Data','KeyWestDetail-data'))) {
        $dest=Join-Path $packageRoot $entry[1]; New-Item -ItemType Directory -Force -Path $dest|Out-Null
        Get-ChildItem -LiteralPath (Join-Path $root $entry[0]) | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force }
    }
    Copy-Item -LiteralPath (Join-Path $root 'Art/KeyWest/README_DATA.md') -Destination (Join-Path $packageRoot 'GEOGRAPHIC-DATA.md')
    Copy-Item -LiteralPath (Join-Path $root 'Art/KeyWestDetail/Textures/CC0/manifest.json') -Destination (Join-Path $packageRoot 'KeyWestDetail-CC0-records.json')
    Copy-Item -LiteralPath (Join-Path $root 'Art/Textures/CC0/manifest.json') -Destination (Join-Path $packageRoot 'Original-CC0-records.json')
    $groundRecords=Join-Path $root 'Art/KeyWestDetail/Ground/Data/imagery.json'
    if(Test-Path -LiteralPath $groundRecords) {
        Copy-Item -LiteralPath $groundRecords -Destination (Join-Path $packageRoot 'Ground-imagery-records.json')
    }
    @'
KEY WEST ARCHITECTURE & HARBOUR - Windows Development
Run PlayKeyWest.cmd or PlayKeyWestPerformance.cmd. Keep the whole folder.
No editor/network/data generation is needed for ordinary play.
Enter/A fly, T/View tour, C/Y camera, P/Esc/Menu pause, R reset, F2 HUD,
F3 timing, F4 preset. S/W pitch, A/D bank, Q/E rudder, Shift/Ctrl power.
The original assisted controls are unchanged. No takeoff/landing or boat driving.
The anchored decorative fleet is inferred, not real traffic/navigation data.
Buildings/elevations are inferred, not photogrammetric/surveyed replicas.
OSM/NAIP and new CC0 records/source data are included and credited in game.
'@ | Set-Content -LiteralPath (Join-Path $packageRoot 'README.txt') -Encoding utf8
    return
}
if($Action-eq'Editor') {
    Start-Process -FilePath $editor -ArgumentList @(('"'+$project+'"'),$map,'-dx11') -WorkingDirectory $root
    return
}
# Prepared package only: ordinary play never builds/imports/generates or starts
# an editor to compile source shaders.
if(-not(Test-Path -LiteralPath $package)) { throw 'Prepared detail package missing. Explicitly Prepare and Package first.' }
$arguments=@($map,'-dx11','-windowed','-ResX=1280','-ResY=720','-nosplash',"-AeronautPreset=$Preset")
if($Action-in@('Benchmark','Capture')) {
    $log=Join-Path $artifacts ($Preset.ToLower()+'-'+$Action.ToLower()+'.log')
    $arguments+=@('-AeronautBenchmark','-AeronautAutoTour','-AeronautShots','-AeronautSelfTest','-RenderOffScreen','-ForceRes','-unattended',('-abslog="'+$log+'"'))
    if($Action-eq'Capture') { $arguments+='-AeronautCaptureOnly' }
    $probe=$null
    try {
        $smi=Get-Command nvidia-smi -ErrorAction SilentlyContinue
        if($smi) { $probe=Start-Process -FilePath $smi.Source -ArgumentList '--query-gpu=timestamp,name,memory.used,utilization.gpu,temperature.gpu --format=csv -l 1' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifacts ($Preset.ToLower()+'-'+$Action.ToLower()+'-gpu.csv')) -RedirectStandardError (Join-Path $artifacts 'gpu-probe-errors.log') }
        $game=Start-Process -FilePath $package -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru
        @{Pid=$game.Id;Executable=$package;StartedUtc=$game.StartTime.ToUniversalTime().ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $artifacts 'owned-runtime-process.json')
        $game.WaitForExit()
        if($game.ExitCode-ne0) { throw 'Detail game process failed.' }
        $marker=if($Action-eq'Capture') {'AERONAUT_CAPTURE_COMPLETE'} else {'AERONAUT_BENCHMARK_COMPLETE'}
        foreach($required in @($marker,'AERONAUT_SELFTEST_PASS','AERONAUT_RENDER_RESOLUTION internal=')) {
            if(-not(Select-String -LiteralPath $log -Pattern $required -Quiet)) { throw "Missing runtime verification $required" }
        }
        if(Select-String -LiteralPath $log -Pattern 'Failed to compile Material|Default Material will be used in game|AERONAUT_SELFTEST_FAILED|AERONAUT_BENCHMARK_INVALID' -Quiet) { throw 'Detail runtime/material verification failed.' }
    } finally { if($probe-and-not$probe.HasExited) { Stop-Process -Id $probe.Id } }
    return
}
Start-Process -FilePath $package -ArgumentList $arguments -WorkingDirectory $root
