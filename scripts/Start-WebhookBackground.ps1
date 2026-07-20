param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "..\config.json"),
    # Comma-separated team ids to proactively warm up at startup (e.g. "1,2"). Empty means all
    # configured teams (unchanged default behavior) -- an unlisted team still works fine on its
    # first real request, it just isn't opened ahead of time.
    [string]$WarmupTeams = ""
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")

function Import-LocalSecrets {
    $secretsPath = Join-Path $root "secrets.local.ps1"
    if (Test-Path -LiteralPath $secretsPath) { . $secretsPath }
}

function Get-JsonValue {
    param([object]$Object, [string]$Name, [object]$Default = "")
    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name -and $null -ne $Object.$Name) { return $Object.$Name }
    return $Default
}

function Test-ConfiguredSecretValue {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $false }
    $trimmed = $Value.Trim()
    if ($trimmed -like "paste-*") { return $false }
    return $true
}

function Get-PythonPath {
    $localPython = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $localPython) { return $localPython }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    throw "Python not found. Run the python deployment stage first."
}

Import-LocalSecrets

$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$webhook = Get-JsonValue $config "wechat_official_webhook" $null
if ($null -eq $webhook) {
    throw "config.json is missing the wechat_official_webhook section."
}

$hostName = [string](Get-JsonValue $webhook "host" "127.0.0.1")
$port = [int](Get-JsonValue $webhook "port" 8791)
$path = [string](Get-JsonValue $webhook "path" "/wechat/official/webhook")
$tokenEnv = [string](Get-JsonValue $webhook "token_env" "WECHAT_OFFICIAL_WEBHOOK_TOKEN")
$appidEnv = [string](Get-JsonValue $webhook "appid_env" "WECHAT_APPID")
$appsecretEnv = [string](Get-JsonValue $webhook "appsecret_env" "WECHAT_APPSECRET")

foreach ($envName in @($tokenEnv, $appidEnv, $appsecretEnv)) {
    $secretValue = [Environment]::GetEnvironmentVariable($envName)
    if (!(Test-ConfiguredSecretValue $secretValue)) {
        throw "$envName is required. Put a real value in secrets.local.ps1 first."
    }
}

$runtimeDir = Join-Path $root "runtime"
$logsDir = Join-Path $root "logs"
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null

$readyFile = Join-Path $runtimeDir "wechat-official-webhook-ready.json"
$statePath = Join-Path $runtimeDir "wechat-official-webhook-state.json"
$serverOut = Join-Path $runtimeDir "wechat-official-webhook-server.out.log"
$serverErr = Join-Path $runtimeDir "wechat-official-webhook-server.err.log"

# A bare restart (schtasks re-running this script, or calling it again without stopping first)
# must not leave the previous process running: Windows lets a second process bind the same
# port via SO_REUSEADDR, so an un-killed old instance silently keeps running as an orphan
# instead of failing loudly -- and, worse, ends up racing the new one over the same shared
# Chrome profile directory (each instance's BrowserProfileManager independently decides "Chrome
# isn't running yet, I'll launch it"). Stop-WebhookBackground.ps1 kills every process actually
# running this webhook's entry script, not just the one this state file happens to remember, so
# reuse it here instead of only stopping the last known PID.
& (Join-Path $PSScriptRoot "Stop-WebhookBackground.ps1") -StatePath $statePath -Port $port
Remove-Item -LiteralPath $readyFile, $serverOut, $serverErr -Force -ErrorAction SilentlyContinue

$python = Get-PythonPath
$serverScript = Join-Path $root "scripts\run_wechat_official_webhook.py"
$serverArgs = @(
    $serverScript,
    "--config-path", $ConfigPath,
    "--host", $hostName,
    "--port", [string]$port,
    "--path", $path,
    "--ready-file", $readyFile
)
# Only add this when non-empty: PowerShell can silently drop an empty-string argument when
# handing an argument list to a native executable (python.exe here, via Start-Process), leaving
# the flag with nothing after it -- omitting the flag entirely is the reliable way to mean "no
# filter" instead of passing "" through.
if (![string]::IsNullOrWhiteSpace($WarmupTeams)) {
    $serverArgs += @("--warmup-teams", $WarmupTeams)
}
$serverProcess = Start-Process -FilePath $python -ArgumentList $serverArgs -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr

$deadline = [DateTime]::UtcNow.AddSeconds(10)
while (!(Test-Path -LiteralPath $readyFile) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 200 }
Start-Sleep -Milliseconds 300
if (!(Test-Path -LiteralPath $readyFile)) { throw "Webhook server did not become ready. See $serverErr" }
if ($serverProcess.HasExited) { throw "Webhook server exited after startup. See $serverErr" }

$state = [pscustomobject]@{
    started_at = (Get-Date).ToString("o")
    local_url = "http://$hostName`:$port/"
    webhook_path = $path
    webhook_pid = $serverProcess.Id
    log_path = $serverOut
    err_path = $serverErr
    note = "This repo does not manage a tunnel. Point an existing tunnel/reverse proxy at local_url + webhook_path."
}
$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
$state | ConvertTo-Json -Depth 5
