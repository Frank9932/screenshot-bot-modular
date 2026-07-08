<#
.SYNOPSIS
Single entry point for the day-to-day operational commands: webhook process, browser/Chrome,
and the optional quick tunnel.

.DESCRIPTION
Run with no arguments (or 'help', '-h', '--help', '-?') to see full usage.

.EXAMPLE
scripts\Bot.ps1 status
scripts\Bot.ps1 webhook restart
scripts\Bot.ps1 browser restart
scripts\Bot.ps1 browser warmup -Teams "1,2"
scripts\Bot.ps1 tunnel start
scripts\Bot.ps1 help
#>
param(
    [Parameter(Position = 0)]
    [string]$Command = "help",

    [Parameter(Position = 1)]
    [string]$Action = "",

    [string]$ConfigPath = "",
    [int]$Tail = 80,

    # Comma-separated team ids (e.g. "1,2") to scope "webhook start/restart" and "browser
    # warmup/restart" to -- omitted/empty means all configured teams (unchanged default
    # behavior). An unlisted team still works fine on its first real request; it just is not
    # proactively opened/logged in ahead of time. Note: "browser restart" always kills and
    # restarts the one shared Chrome/webhook process for everyone regardless of -Teams -- that
    # part cannot be scoped, since there is only one Chrome process for all teams. -Teams only
    # limits which teams get proactively re-warmed afterward.
    [string]$Teams = "",

    [Alias("h", "?")]
    [switch]$Help
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

# Command -> allowed actions (empty array means the command takes no action).
$script:Commands = [ordered]@{
    status  = @{ Actions = @(); Description = "Show webhook, tunnel, and Chrome status in one shot" }
    webhook = @{ Actions = @("start", "stop", "restart", "status", "logs"); Description = "Manage the WeChat webhook process" }
    browser = @{ Actions = @("restart", "warmup"); Description = "Manage the shared Chrome browser/tabs" }
    tunnel  = @{ Actions = @("start", "stop", "status"); Description = "Manage the optional public quick tunnel" }
}

function Show-Help {
    Write-Output @"
Bot.ps1 - operate the screenshot bot (webhook, browser, tunnel)

USAGE
    scripts\Bot.ps1 <command> [action] [-ConfigPath <path>] [-Tail <n>] [-Teams <csv>]

COMMANDS
    status                     Show webhook, tunnel, and Chrome status in one shot
    webhook <action>           Manage the WeChat webhook process
                                 actions: start | stop | restart | status | logs
    browser <action>           Manage the shared Chrome browser/tabs
                                 actions: restart | warmup
    tunnel <action>            Manage the optional public quick tunnel
                                 actions: start | stop | status
    help                       Show this help (also: -h, --help, -?, or no arguments)

OPTIONS
    -ConfigPath <path>         Path to config.json (default: <repo root>\config.json)
    -Tail <n>                  Number of log lines to show for 'webhook logs' (default: 80)
    -Teams <csv>               Comma-separated team ids, e.g. "1,2" -- scopes which teams
                                 "webhook start/restart" and "browser warmup/restart" proactively
                                 open/log in. Omit for all configured teams (default, unchanged
                                 behavior). An unlisted team still works on its first real
                                 request, it just is not opened ahead of time. Does NOT scope the
                                 kill step of "browser restart"/"webhook restart" -- that always
                                 stops the one shared webhook/Chrome process for every team,
                                 since there is only one Chrome process for all of them.

EXAMPLES
    scripts\Bot.ps1 status
    scripts\Bot.ps1 webhook restart
    scripts\Bot.ps1 webhook logs -Tail 200
    scripts\Bot.ps1 browser restart
    scripts\Bot.ps1 browser warmup -Teams "1,2"
    scripts\Bot.ps1 tunnel start
"@
}

$script:NormalizedCommand = $Command.Trim().ToLowerInvariant()

if ($Help -or [string]::IsNullOrWhiteSpace($Command) -or $script:NormalizedCommand -in @("help", "-h", "--help", "-?", "/?")) {
    Show-Help
    exit 0
}

if (-not $script:Commands.Contains($script:NormalizedCommand)) {
    Write-Warning "Unknown command: '$Command'. Valid commands: $($script:Commands.Keys -join ', ')"
    Show-Help
    exit 1
}
$Command = $script:NormalizedCommand

$script:AllowedActions = $script:Commands[$Command].Actions
if ($script:AllowedActions.Count -gt 0) {
    $script:NormalizedAction = $Action.Trim().ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($Action) -or $script:NormalizedAction -notin $script:AllowedActions) {
        Write-Warning "'$Command' requires an action. Valid actions: $($script:AllowedActions -join ', ')"
        Show-Help
        exit 1
    }
    $Action = $script:NormalizedAction
}

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
    & (Join-Path $PSScriptRoot "Start-WebhookBackground.ps1") -ConfigPath $ConfigPath -WarmupTeams $Teams
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

function ConvertTo-PythonTeamsLiteral {
    param([string]$TeamsCsv)
    if ([string]::IsNullOrWhiteSpace($TeamsCsv)) { return "None" }
    $teamList = ($TeamsCsv -split ",") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    return "[" + (($teamList | ForEach-Object { '"' + $_ + '"' }) -join ",") + "]"
}

function Invoke-BrowserWarmup {
    # Retries login/warm_up for every configured target (or just -Teams, if given) without
    # touching the running webhook process at all -- a separate one-off process safely shares
    # the same Chrome via adopt_tab (matches existing tabs by URL origin instead of opening
    # duplicates), so this is safe to run at any time, e.g. right after fixing a credential
    # without a full restart.
    Set-Location -LiteralPath $root
    $secretsPath = Join-Path $root "secrets.local.ps1"
    if (Test-Path -LiteralPath $secretsPath) { . $secretsPath }
    $env:PYTHONPATH = Join-Path $root "src"
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (!(Test-Path -LiteralPath $python)) { $python = "python" }
    $teamsArg = ConvertTo-PythonTeamsLiteral -TeamsCsv $Teams
    & $python -c "import json; from screenshot_bot.browser import BrowserScreenshotService; svc = BrowserScreenshotService(r'$ConfigPath'); print(json.dumps(svc.warm_up(team_ids=$teamsArg), indent=2))"
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

function Format-Timestamp {
    param([string]$Iso)
    if ([string]::IsNullOrWhiteSpace($Iso)) { return "n/a" }
    try { return ([DateTimeOffset]::Parse($Iso)).ToString("yyyy-MM-dd HH:mm:ss zzz") }
    catch { return $Iso }
}

function Format-Uptime {
    param([string]$Iso)
    if ([string]::IsNullOrWhiteSpace($Iso)) { return "n/a" }
    try {
        $span = (Get-Date) - ([DateTimeOffset]::Parse($Iso)).LocalDateTime
        if ($span.TotalSeconds -lt 0) { return "n/a" }
        return "{0}d {1}h {2}m" -f $span.Days, $span.Hours, $span.Minutes
    } catch { return "n/a" }
}

function Get-PortOwningProcessId {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $conn) { return [int]$conn.OwningProcess }
    return $null
}

# A one-line summary hides exactly the failure mode this project keeps tripping over: a previous
# restart that didn't fully stop leaves an orphan process pair running alongside the tracked one,
# racing it over the same shared Chrome/tab state (see docs/DEBUG_HANDOFF.md). Surfacing the
# process count, the tracked pid, and who actually owns the port turns "run four ad-hoc WMI
# queries by hand" into "glance at `Bot.ps1 status`".
function Invoke-OverallStatus {
    $webhook = Invoke-WebhookStatus
    $tunnel = Invoke-TunnelStatus
    $chromeCount = (Get-Process chrome -ErrorAction SilentlyContinue | Measure-Object).Count
    $trackedPid = $webhook.state.webhook_pid
    $pids = @($webhook.process_ids)
    $healthy = ($null -ne $webhook.local_health) -and $webhook.local_health.ok
    $port = Get-WebhookPort
    $portOwner = Get-PortOwningProcessId -Port $port

    Write-Output "=== Webhook ==="
    Write-Output ("  status       : {0}" -f $(if ($healthy) { "OK" } else { "FAIL" }))
    if (-not $healthy -and $null -ne $webhook.local_health.error) {
        Write-Output ("  health error : {0}" -f $webhook.local_health.error)
    }
    Write-Output ("  tracked pid  : {0}" -f $(if ($null -ne $trackedPid) { $trackedPid } else { "n/a" }))
    Write-Output ("  processes    : {0}" -f $(if ($pids.Count -gt 0) { $pids -join ", " } else { "none" }))
    if ($pids.Count -ne 0 -and $pids.Count -ne 2) {
        Write-Warning ("found $($pids.Count) webhook process(es), expected 2 (1 parent + 1 child) -- possible orphan from an earlier restart that did not fully stop.")
    }
    if ($null -ne $trackedPid -and $pids.Count -gt 0 -and $trackedPid -notin $pids) {
        Write-Warning "tracked webhook_pid $trackedPid is not among the running processes -- state file is stale."
    }
    if ($null -ne $portOwner) {
        Write-Output ("  port owner   : {0} (port {1})" -f $portOwner, $port)
        if ($null -ne $trackedPid -and $portOwner -ne $trackedPid -and $portOwner -notin $pids) {
            Write-Warning "port $port is owned by pid $portOwner, which is not one of this webhook's own tracked processes -- possible split-brain."
        }
    } else {
        Write-Warning "nothing is listening on port $port."
    }
    Write-Output ("  started      : {0} (uptime {1})" -f (Format-Timestamp $webhook.state.started_at), (Format-Uptime $webhook.state.started_at))
    $webhookUrl = "$($webhook.state.local_url.TrimEnd('/'))/$($webhook.state.webhook_path.TrimStart('/'))"
    Write-Output ("  url          : {0}" -f $webhookUrl)
    Write-Output ("  teams        : {0}" -f ($webhook.ready.browser_target_ids -join ", "))
    Write-Output ("  secrets      : token={0} appid={1} appsecret={2}" -f $webhook.ready.has_token, $webhook.ready.has_appid, $webhook.ready.has_appsecret)

    Write-Output ""
    Write-Output "=== Tunnel ==="
    if ($tunnel.process_running -and $null -ne $tunnel.state) {
        Write-Output "  status       : running"
        Write-Output ("  url          : {0}" -f $tunnel.state.tunnel_url)
        Write-Output ("  started      : {0} (uptime {1})" -f (Format-Timestamp $tunnel.state.started_at), (Format-Uptime $tunnel.state.started_at))
    } else {
        Write-Output "  status       : not running"
    }

    Write-Output ""
    Write-Output "=== Chrome ==="
    Write-Output ("  processes    : {0}" -f $chromeCount)
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
