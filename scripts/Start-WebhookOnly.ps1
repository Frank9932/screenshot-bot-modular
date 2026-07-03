param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "..\config.example.json"),
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8790,
    [string]$Path = "/wechat/official/webhook"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$secrets = Join-Path $root "secrets.local.ps1"
if (Test-Path -LiteralPath $secrets) {
    . $secrets
}

$env:PYTHONPATH = (Join-Path $root "src")
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    throw "Python not found."
}

& $python.Source (Join-Path $root "scripts\run_wechat_official_webhook.py") `
    --config-path $ConfigPath `
    --host $HostName `
    --port $Port `
    --path $Path `
    --ready-file (Join-Path $root "runtime\wechat-official-webhook-ready.json")
