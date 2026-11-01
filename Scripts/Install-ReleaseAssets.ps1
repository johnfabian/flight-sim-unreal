[CmdletBinding()]
param(
    [ValidateSet('Editor','Windows')][string]$Target='Editor',
    [string]$Destination,
    [string]$ArchivePath,
    [switch]$VerifyOnly
)
$ErrorActionPreference='Stop'
function Get-ReleaseHash([string]$File) {
    $stream=[IO.File]::OpenRead($File)
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try { ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','') }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}
$projectRoot=Split-Path $PSScriptRoot -Parent
$manifest=Get-Content -LiteralPath (Join-Path $projectRoot 'release-manifest.json') -Raw | ConvertFrom-Json
$asset=$manifest.assets | Where-Object target -EQ $Target
if(@($asset).Count -ne 1) { throw 'Expected exactly one pinned release asset for this target.' }
if(-not $Destination) {
    $Destination=if($Target -eq 'Editor') {$projectRoot} else {Join-Path $projectRoot 'Builds/KeyWestDetail'}
}
$Destination=[IO.Path]::GetFullPath($Destination)
$destinationPrefix=$Destination.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
$cache=Join-Path $projectRoot 'artifacts/public-downloads'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
if(-not $ArchivePath) {
    $ArchivePath=Join-Path $cache $asset.file
    if(-not(Test-Path -LiteralPath $ArchivePath)) {
        if($asset.url -notmatch '^https://github\.com/johnfabian/flight-sim-unreal/releases/download/') { throw 'Unexpected release origin.' }
        $partial=$ArchivePath+'.partial'
        Invoke-WebRequest -Uri $asset.url -OutFile $partial -UseBasicParsing
        if((Get-Item -LiteralPath $partial).Length -ne $asset.bytes -or (Get-ReleaseHash $partial) -ne $asset.sha256) { throw 'Downloaded archive failed its pinned SHA256/size check.' }
        Move-Item -LiteralPath $partial -Destination $ArchivePath
    }
}
$ArchivePath=(Resolve-Path -LiteralPath $ArchivePath).Path
if((Get-Item -LiteralPath $ArchivePath).Length -ne $asset.bytes -or (Get-ReleaseHash $ArchivePath) -ne $asset.sha256) { throw 'Archive failed its pinned SHA256/size check.' }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip=[IO.Compression.ZipFile]::OpenRead($ArchivePath)
$seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$plan=@()
try {
    foreach($entry in $zip.Entries) {
        $name=$entry.FullName.Replace('\','/')
        if($name.EndsWith('/')) { continue }
        if([IO.Path]::IsPathRooted($name) -or $name.Contains(':') -or @($name.Split('/') | Where-Object {$_ -in @('..','.','')}).Count) { throw 'Unsafe archive path.' }
        if(-not $seen.Add($name)) { throw 'Duplicate archive path.' }
        if((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'Archive symlinks are not supported.' }
        $allowed=if($Target -eq 'Editor') {
            $name.StartsWith('Content/') -or $name.StartsWith('Art/') -or $name -in @('artifacts/keywest-detail/baseline/content-sha256.csv','artifacts/keywest-detail/authored-scene.json')
        } else { $name.StartsWith('Windows/') -and -not $name.Contains('/Saved/') }
        if(-not $allowed) { throw 'Archive includes a path outside its declared installation scope.' }
        $output=[IO.Path]::GetFullPath((Join-Path $Destination $name))
        if(-not $output.StartsWith($destinationPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Archive path escapes destination.' }
        $plan+=@{Name=$name;Output=$output}
    }
} finally { $zip.Dispose() }
if($plan.Count -ne $asset.files) { throw 'Archive file count differs from the pinned manifest.' }
if($VerifyOnly) { Write-Output ('Verified '+$Target+' archive: '+$plan.Count+' files; SHA256 '+$asset.sha256); return }

$stage=Join-Path $cache ('stage-'+[guid]::NewGuid().ToString('N'))
[IO.Compression.ZipFile]::ExtractToDirectory($ArchivePath,$stage)
# Preflight every file before copying any content into the project.
foreach($item in $plan) {
    if(Test-Path -LiteralPath $item.Output) {
        if(-not(Test-Path -LiteralPath $item.Output -PathType Leaf) -or (Get-ReleaseHash $item.Output) -ne (Get-ReleaseHash (Join-Path $stage $item.Name))) {
            throw ('Existing file differs; installation stopped to preserve your edits: '+$item.Name)
        }
    }
    $parent=Split-Path $item.Output -Parent
    while($parent -and $parent.StartsWith($destinationPrefix,[StringComparison]::OrdinalIgnoreCase)) {
        if(Test-Path -LiteralPath $parent) {
            $existing=Get-Item -LiteralPath $parent -Force
            if(-not $existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Destination parent is not a normal directory.' }
        }
        $parent=Split-Path $parent -Parent
    }
}
if(Test-Path -LiteralPath $Destination) {
    $destinationItem=Get-Item -LiteralPath $Destination -Force
    if(-not $destinationItem.PSIsContainer -or ($destinationItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Destination must be a normal directory.' }
}
foreach($item in $plan) {
    if(-not(Test-Path -LiteralPath $item.Output)) {
        New-Item -ItemType Directory -Path (Split-Path $item.Output -Parent) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $stage $item.Name) -Destination $item.Output
    }
}
Write-Output ('Installed '+$Target+' assets into '+$Destination)
Write-Output 'Existing identical files were retained. Download and extraction caches remain under artifacts/public-downloads.'
