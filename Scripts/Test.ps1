$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$vswhere='C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
$vs=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $vs) { throw 'Visual Studio C++ tools were not found.' }
$dev=Join-Path $vs 'Common7\Tools\Launch-VsDevShell.ps1'
& $dev -Arch amd64 -HostArch amd64 -SkipAutomaticLocation | Out-Null
$out=Join-Path $root 'artifacts'
New-Item -ItemType Directory -Force -Path $out | Out-Null
Push-Location $out
try {
    & cl.exe /nologo /EHsc /std:c++17 /W4 (Join-Path $root 'Tests\simulation.cpp') /Fe:simulation-tests.exe
    if($LASTEXITCODE -ne 0) { throw 'Simulation test compilation failed.' }
    & (Join-Path $out 'simulation-tests.exe')
    if($LASTEXITCODE -ne 0) { throw 'Simulation checks failed.' }
} finally { Pop-Location }
