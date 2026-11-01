$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$toolsDir=Join-Path $root 'Tools'
$assetDir=Join-Path $root 'Art/Textures/CC0'
New-Item -ItemType Directory -Force -Path $toolsDir,$assetDir | Out-Null
$blenderVersion='4.5.15'
$archive=Join-Path $toolsDir "blender-$blenderVersion-windows-x64.zip"
$exe=Join-Path $toolsDir "blender-$blenderVersion-windows-x64/blender.exe"
if(-not(Test-Path -LiteralPath $exe)) {
    if(-not(Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest "https://download.blender.org/release/Blender4.5/blender-$blenderVersion-windows-x64.zip" -OutFile $archive
    }
    $sums=Invoke-WebRequest "https://download.blender.org/release/Blender4.5/blender-$blenderVersion.sha256" -UseBasicParsing
    $entry=($sums.Content -split "`n" | Where-Object { $_ -match "blender-$([regex]::Escape($blenderVersion))-windows-x64.zip" })
    if(-not $entry) { throw 'Official Blender checksum not found.' }
    $expected=($entry.Trim() -split '\s+')[0]
    if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ine $expected) { throw 'Blender archive checksum mismatch.' }
    Expand-Archive -LiteralPath $archive -DestinationPath $toolsDir -Force
}
$records=@()
function Get-Asset($id,$kind,$resolution,$format,$localName) {
    $manifestPath=Join-Path $root "artifacts/$id-files.json"
    if(-not(Test-Path $manifestPath)) { Invoke-RestMethod "https://api.polyhaven.com/files/$id" -UserAgent 'AeronautShowcase/0.1' | ConvertTo-Json -Depth 20 | Set-Content $manifestPath }
    $manifest=Get-Content $manifestPath -Raw | ConvertFrom-Json
    $file=$manifest.$kind.$resolution.$format
    if(-not $file.url) { throw "Missing $id / $kind / $resolution / $format" }
    $dest=Join-Path $assetDir $localName
    if(-not(Test-Path $dest)) { Invoke-WebRequest $file.url -OutFile $dest }
    if($file.md5 -and (Get-FileHash $dest -Algorithm MD5).Hash -ine $file.md5) { throw "Asset checksum mismatch: $dest" }
    $infoPath=Join-Path $root "artifacts/$id-info.json"
    if(-not(Test-Path $infoPath)) { Invoke-RestMethod "https://api.polyhaven.com/info/$id" -UserAgent 'AeronautShowcase/0.1' | ConvertTo-Json -Depth 15 | Set-Content $infoPath }
    $info=Get-Content $infoPath -Raw | ConvertFrom-Json
    $script:records+=@{asset=$id;authors=@($info.authors.PSObject.Properties.Name);source="https://polyhaven.com/a/$id";license='CC0-1.0';license_url='https://polyhaven.com/license';download_url=$file.url;file="Art/Textures/CC0/$localName";sha256=(Get-FileHash $dest -Algorithm SHA256).Hash;modifications='Source file unchanged; Unreal import caps resolution. DirectX normal maps selected.'}
}
foreach($id in @('aerial_asphalt_01','forest_floor','coast_land_rocks_01')) {
    Get-Asset $id 'Diffuse' '2k' 'jpg' "$($id)_base.jpg"
    Get-Asset $id 'nor_dx' '2k' 'png' "$($id)_normal.png"
    Get-Asset $id 'arm' '2k' 'jpg' "$($id)_arm.jpg"
}
foreach($item in @(@('bark_diff','tree_bark_base.jpg','jpg'),@('bark_nor_dx','tree_bark_normal.png','png'),@('bark_arm','tree_bark_arm.jpg','jpg'),@('twig_diff','tree_twig_base.png','png'),@('twig_nor_dx','tree_twig_normal.png','png'),@('twig_arm','tree_twig_arm.jpg','jpg'),@('twig_mask','tree_twig_mask.png','png'))) {
    Get-Asset 'pine_tree_01' $item[0] '1k' $item[2] $item[1]
}
Get-Asset 'kloppenheim_06_puresky' 'hdri' '2k' 'hdr' 'coastal_sky.hdr'
$records | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $root 'Art/Textures/CC0/manifest.json')
Write-Host "Blender: $exe"
Write-Host "Downloaded and verified $($records.Count) CC0 files."
