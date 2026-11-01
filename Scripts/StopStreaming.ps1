$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$sessionFile=Join-Path $root 'artifacts\stream-session.json'
if(-not(Test-Path -LiteralPath $sessionFile)) { Write-Host 'No recorded streaming session.'; return }
$session=Get-Content -LiteralPath $sessionFile -Raw | ConvertFrom-Json
$unmatched=$false
foreach($record in @($session.Game,$session.Server)) {
    $running=Get-Process -Id $record.Id -ErrorAction SilentlyContinue
    # Never stop an unrelated process if Windows has reused an old PID.
    if($running -and $running.Path -eq $record.Path -and $running.StartTime.ToUniversalTime().Ticks -eq ([datetime]$record.Started).ToUniversalTime().Ticks) {
        Stop-Process -Id $running.Id
    } elseif($running) {
        $unmatched=$true
        Write-Warning "Process $($record.Id) no longer matches the recorded Aeronaut session; it was left running."
    }
}
if($unmatched) { throw 'Could not verify every recorded process. The session record was preserved; no unrelated processes were stopped.' }
Remove-Item -LiteralPath $sessionFile
Write-Host 'Aeronaut browser streaming stopped.'
