<#
.SYNOPSIS
Single entry point for the day-to-day operational commands: webhook process, browser/Chrome,
and the optional quick tunnel.

.EXAMPLE
scripts\Bot.ps1 status
scripts\Bot.ps1 webhook restart
scripts\Bot.ps1 browser restart
scripts\Bot.ps1 tunnel start
#>
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("status", "webhook", "browser", "tunnel")]
    [string]$Command,

    [Parameter(Position = 1)]
    [ValidateSet("", "start", "stop", "restart", "status", "logs", "warmup")]
    [string]$Action = "",

    [string]$ConfigPath = "",
    [int]$Tail = 80
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

# $PSScriptRoot in a param block's default-value expression isn't reliably populated depending
# on invocation style (e.g. `powershell -File relative\path\Bot.ps1`) -- compute defaults here
# in the script body instead, where $PSScriptRoot is guaranteed to be set.
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeDir = Join-Path $root "runtime"
$logsDir = Join-Path $root "logs"
if ([string]::IsNullOrWhiteSpace($ConfigPath)) { $ConfigPath = Join-Path $root "config.json" }

function Get-JsonValue {
    param([object]$Object, [string]$Name, [object]$Default = "")
    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name -and $null -ne $Object.$Name) { return $Object.$Name }
    return $Default
}

function Read-JsonFile {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        try { return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
    }
    return $null
}

function Get-WebhookPort {
    $config = Read-JsonFile $ConfigPath
    $webhook = Get-JsonValue $config "wechat_official_webhook" $null
    return [int](Get-JsonValue $webhook "port" 8791)
}

function Invoke-WebhookStatus {
    $port = Get-WebhookPort
    $ready = Read-JsonFile (Join-Path $runtimeDir "wechat-official-webhook-ready.json")
    $state = Read-JsonFile (Join-Path $runtimeDir "wechat-official-webhook-state.json")
    $health = $null
    try { $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 3 }
    catch { $health = [pscustomobject]@{ ok = $false; error = $_.Exception.Message } }
    $pids = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match [regex]::Escape("run_wechat_official_webhook.py") } |
        Select-Object -ExpandProperty ProcessId)
    [pscustomobject]@{
        ready         = $ready
        state         = $state
        local_health  = $health
        process_ids   = $pids
    }
}

function Invoke-WebhookStart {
    & (Join-Path $PSScriptRoot "Start-WebhookBackground.ps1") -ConfigPath $ConfigPath
}

function Invoke-WebhookStop {
    & (Join-Path $PSScriptRoot "Stop-WebhookBackground.ps1")
}

function Invoke-WebhookLogs {
    $paths = @(
        (Join-Path $logsDir "webhook-task.log"),
        (Join-Path $runtimeDir "wechat-official-webhook-server.out.log"),
        (Join-Path $runtimeDir "wechat-official-webhook-server.err.log"),
        (Join-Path $logsDir "wechat-official-webhook-events.jsonl")
    )
    foreach ($path in $paths) {
        Write-Output "===== $path ====="
        if (Test-Path -LiteralPath $path) { Get-Content -LiteralPath $path -Tail $Tail }
        else { Write-Output "MISSING" }
    }
}

function Invoke-BrowserRestart {
    # Restarting only the webhook process adopts whatever Chrome is already running (by design,
    # so a crashed/redeployed process doesn't lose an authenticated session). If Chrome itself is
    # the thing that's stuck, it has to be killed explicitly first -- this is that "kill Chrome
    # too" step, wrapped into one command instead of three manual ones.
    Write-Output "Stopping webhook..."
    Invoke-WebhookStop
    $survivors = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match [regex]::Escape("run_wechat_official_webhook.py") })
    if ($survivors.Count -gt 0) {
        Write-Warning "webhook did not fully stop (pids: $($survivors.ProcessId -join ', ')) -- continuing anyway, but the new instance may race with these."
    }
    Write-Output "Killing Chrome..."
    Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    # Wait for the debug port to actually release rather than a blind sleep -- starting a fresh
    # Chrome while the old one is still mid-shutdown (or its debug port still momentarily
    # responsive) is exactly the race that produces intermittent "tab not debuggable" errors.
    $debugPort = 9221
    try {
        $config = Read-JsonFile $ConfigPath
        $browserTargets = Get-JsonValue $config "browser_targets" $null
        $debugPort = [int](Get-JsonValue $browserTargets "debug_port" 9221)
    } catch {
    }
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        $stillUp = $false
        try { Invoke-RestMethod -Uri "http://127.0.0.1:$debugPort/json/version" -TimeoutSec 1 | Out-Null; $stillUp = $true } catch { $stillUp = $false }
        if (-not $stillUp) { break }
        Start-Sleep -Milliseconds 500
    }
    Write-Output "Starting webhook (launches a fresh Chrome + full warm_up)..."
    Invoke-WebhookStart
    Write-Output "Waiting for browser warm_up..."
    $outLog = Join-Path $runtimeDir "wechat-official-webhook-server.out.log"
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $content = Get-Content -LiteralPath $outLog -Raw -ErrorAction SilentlyContinue
        if ($content -match "browser_warm_up") { break }
        Start-Sleep -Seconds 2
    }
    Get-Content -LiteralPath $outLog -Raw -ErrorAction SilentlyContinue
}

function Invoke-BrowserWarmup {
    # Retries login/warm_up for every configured target without touching the running webhook
    # process at all -- a separate one-off process safely shares the same Chrome via
    # adopt_tab (matches existing tabs by URL origin instead of opening duplicates), so this is
    # safe to run at any time, e.g. right after fixing a credential without a full restart.
    Set-Location -LiteralPath $root
    $secretsPath = Join-Path $root "secrets.local.ps1"
    if (Test-Path -LiteralPath $secretsPath) { . $secretsPath }
    $env:PYTHONPATH = Join-Path $root "src"
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (!(Test-Path -LiteralPath $python)) { $python = "python" }
    & $python -c "import json; from screenshot_bot.browser import BrowserScreenshotService; svc = BrowserScreenshotService(r'$ConfigPath'); print(json.dumps(svc.warm_up(), indent=2))"
}

function Invoke-TunnelStart {
    & (Join-Path $PSScriptRoot "Start-PublicTunnel.ps1") -ConfigPath $ConfigPath
}

function Invoke-TunnelStop {
    & (Join-Path $PSScriptRoot "Stop-PublicTunnel.ps1")
}

function Invoke-TunnelStatus {
    $statePath = Join-Path $runtimeDir "public-tunnel-state.json"
    $state = Read-JsonFile $statePath
    $running = $false
    if ($null -ne $state -and $null -ne $state.pid) {
        $running = $null -ne (Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue)
    }
    [pscustomobject]@{ state = $state; process_running = $running }
}

function Invoke-OverallStatus {
    Write-Output "=== webhook ==="
    Invoke-WebhookStatus | ConvertTo-Json -Depth 8
    Write-Output "`n=== tunnel ==="
    Invoke-TunnelStatus | ConvertTo-Json -Depth 8
    Write-Output "`n=== chrome ==="
    $chromeCount = (Get-Process chrome -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Output "chrome.exe process count: $chromeCount"
}

switch ($Command) {
    "status" { Invoke-OverallStatus }
    "webhook" {
        switch ($Action) {
            "start" { Invoke-WebhookStart }
            "stop" { Invoke-WebhookStop }
            "restart" { Invoke-WebhookStop; Invoke-WebhookStart }
            "status" { Invoke-WebhookStatus | ConvertTo-Json -Depth 8 }
            "logs" { Invoke-WebhookLogs }
            default { throw "webhook requires an action: start|stop|restart|status|logs" }
        }
    }
    "browser" {
        switch ($Action) {
            "restart" { Invoke-BrowserRestart }
            "warmup" { Invoke-BrowserWarmup }
            default { throw "browser requires an action: restart|warmup" }
        }
    }
    "tunnel" {
        switch ($Action) {
            "start" { Invoke-TunnelStart }
            "stop" { Invoke-TunnelStop }
            "status" { Invoke-TunnelStatus | ConvertTo-Json -Depth 8 }
            default { throw "tunnel requires an action: start|stop|status" }
        }
    }
}
