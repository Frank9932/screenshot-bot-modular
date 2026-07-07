param(
    [string]$StatePath = (Join-Path $PSScriptRoot "..\runtime\public-tunnel-state.json")
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

if (!(Test-Path -LiteralPath $StatePath)) {
    Write-Host "No public tunnel state file found: $StatePath"
    return
}

$state = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -ne $state.pid -and [int]$state.pid -gt 0) {
    Stop-Process -Id ([int]$state.pid) -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
Write-Host "Tunnel stopped."
