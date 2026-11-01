[CmdletBinding()]
param(
    [ValidateSet('Check','Build','Prepare','Play','Editor','Stream')][string]$Action='Play',
    [string]$EngineRoot=$env:UE_ROOT,
    [switch]$NoBrowser,
    [string]$Map='/Game/Aeronaut/FlightMap'
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$projectFile=Join-Path $projectRoot 'Aeronaut.uproject'
if (-not $EngineRoot) {
    $candidates=@()
    $manifest='C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat'
    if (Test-Path -LiteralPath $manifest) {
        $candidates+=((Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json).InstallationList | Where-Object AppName -Like 'UE_*' | ForEach-Object InstallLocation)
    }
    foreach ($base in @('C:\Program Files\Epic Games','C:\Epic Games','C:\Unreal')) {
        if (Test-Path -LiteralPath $base) { $candidates+=(Get-ChildItem -LiteralPath $base -Directory -Filter 'UE_*' | Sort-Object Name -Descending | ForEach-Object FullName) }
    }
    $EngineRoot=$candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'Engine\Binaries\Win64\UnrealEditor.exe') } | Select-Object -First 1
}
if (-not $EngineRoot) { throw 'Unreal Engine was not found. Install UE 5.8 in Epic Games Launcher, or pass -EngineRoot "D:\Epic Games\UE_5.8".' }
$EngineRoot=(Resolve-Path -LiteralPath $EngineRoot).Path
$editor=Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
$commandlet=Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$build=Join-Path $EngineRoot 'Engine\Build\BatchFiles\Build.bat'
foreach($required in @($editor,$commandlet,$build)) { if(-not(Test-Path -LiteralPath $required)) { throw "Missing Unreal component: $required" } }
Write-Host "Engine: $EngineRoot"
Write-Host "Project: $projectFile"
if($Action -eq 'Check') { return }
$artifacts=Join-Path $projectRoot 'artifacts'
New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
# Always let UBT check timestamps; it performs an incremental build when up to date.
& $build AeronautEditor Win64 Development "-Project=$projectFile" -WaitMutex -NoHotReloadFromIDE
if($LASTEXITCODE -ne 0) { throw "Unreal build failed ($LASTEXITCODE). See the UnrealBuildTool log above." }
if($Action -eq 'Build') { return }
$contentLog=Join-Path $artifacts 'content.log'
$script=Join-Path $PSScriptRoot 'create_content.py'
$mapFile=Join-Path $projectRoot 'Content\Aeronaut\FlightMap.umap'
$materialFile=Join-Path $projectRoot 'Content\Aeronaut\M_Surface.uasset'
if($Action -eq 'Prepare' -or -not(Test-Path -LiteralPath $mapFile) -or -not(Test-Path -LiteralPath $materialFile) -or -not(Test-Path -LiteralPath (Join-Path $projectRoot 'Content\Aeronaut\M_Ocean.uasset')) -or -not(Test-Path -LiteralPath (Join-Path $projectRoot 'Content\Blueprints\BP_AeronautPawn.uasset'))) {
    & $commandlet $projectFile '-run=pythonscript' "-script=$script" -unattended -nop4 -nullrhi "-abslog=$contentLog"
    if($LASTEXITCODE -ne 0 -or -not(Test-Path -LiteralPath $contentLog) -or -not (Select-String -LiteralPath $contentLog -Pattern 'AERONAUT_CONTENT_READY' -Quiet)) { throw "Content generation failed. Inspect $contentLog" }
}
if($Action -eq 'Prepare') { return }
$flightFrameCap=if($Map -in @('/Game/Showcase/CoastalShowcase','/Game/KeyWest/KeyWest','/Game/KeyWestDetail/KeyWestDetail')) {30} else {60}
$launchArgs=@(('"{0}"' -f $projectFile),$Map,'-dx11','-windowed','-ResX=1280','-ResY=720','-nosplash',('-ExecCmds="t.MaxFPS {0}"' -f $flightFrameCap))
if($Action -in @('Play','Stream')) { $launchArgs+='-game' }
if($Action -eq 'Stream') {
    $node=(Get-Command node -ErrorAction Stop).Source
    $serverFile=Join-Path $projectRoot 'Streaming\server.cjs'
    $playerBundle=Join-Path $projectRoot 'Streaming\Infrastructure\SignallingWebServer\www\player.js'
    if(-not(Test-Path -LiteralPath $playerBundle)) { throw 'Streaming dependencies are missing. See README.md for setup.' }
    if(Get-NetTCPConnection -State Listen -LocalPort 8080,8888 -ErrorAction SilentlyContinue) { throw 'A streaming port is already in use. Run StopStreaming.cmd to stop a previous Aeronaut session.' }
    $server=Start-Process -FilePath $node -ArgumentList ('"{0}"' -f $serverFile) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $artifacts 'stream-server.log') -RedirectStandardError (Join-Path $artifacts 'stream-server-errors.log')
    try {
        $ready=$false
        for($attempt=0;$attempt -lt 30;$attempt++) {
            if($server.HasExited) { throw 'Streaming server exited. See artifacts\stream-server-errors.log.' }
            try { $health=Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 1; if($health.app -eq 'Aeronaut') { $ready=$true; break } } catch { Start-Sleep -Milliseconds 200 }
        }
        if(-not $ready) { throw 'Streaming server did not start.' }
        $launchArgs+=@('-AeronautStreaming','-PixelStreamingConnectionURL=ws://127.0.0.1:8888','-PixelStreamingEncoderCodec=H264','-RenderOffScreen','-ForceRes','-AudioMixer','-Unattended',('-abslog="{0}"' -f (Join-Path $artifacts 'stream-game.log')))
        $game=Start-Process -FilePath $editor -ArgumentList $launchArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
        function Record($process,$executable) { @{Id=$process.Id;Path=$executable;Started=$process.StartTime.ToUniversalTime().ToString('o')} }
        @{Game=(Record $game $editor);Server=(Record $server $node)} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $artifacts 'stream-session.json')
        Write-Host 'Browser: http://127.0.0.1:8080/?AutoConnect=true&AutoPlayVideo=true&HoveringMouse=true'
        Write-Host 'Allow the game to load, then click the player to focus keyboard controls. StopStreaming.cmd ends the session.'
        if(-not $NoBrowser) { Start-Process 'http://127.0.0.1:8080/?AutoConnect=true&AutoPlayVideo=true&HoveringMouse=true' }
    } catch {
        if(-not $server.HasExited) { Stop-Process -Id $server.Id }
        throw
    }
    return
}
# This is the interactive game/editor window requested by the user.
Start-Process -FilePath $editor -ArgumentList $launchArgs -WorkingDirectory $projectRoot

