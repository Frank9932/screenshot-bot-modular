param(
    [string]$StatePath = (Join-Path $PSScriptRoot "..\runtime\wechat-official-webhook-state.json")
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

if (!(Test-Path -LiteralPath $StatePath)) {
    Write-Host "No webhook state file found: $StatePath"
    return
}

$state = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -ne $state.webhook_pid -and [int]$state.webhook_pid -gt 0) {
    Stop-Process -Id ([int]$state.webhook_pid) -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
Write-Host "Webhook stopped."
