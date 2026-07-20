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

    # Cloudflare named-tunnel token for "tunnel permanent-install" (from the Zero Trust
    # dashboard -> Networks -> Tunnels -> your tunnel -> install command). Installs cloudflared
    # as a Windows service bound to that tunnel -- unlike "tunnel start" (a throwaway quick
    # tunnel with a random URL that dies with the process), this survives reboots and keeps a
    # stable hostname, since the routing lives in Cloudflare's dashboard rather than a local
    # config file.
    [string]$TunnelToken = "",

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
    webhook = @{ Actions = @("start", "stop", "restart", "status", "logs", "watch"); Description = "Manage the WeChat webhook process" }
    browser = @{ Actions = @("restart", "warmup"); Description = "Manage the shared Chrome browser/tabs" }
    menu    = @{ Actions = @("set", "get"); Description = "Push or inspect the WeChat tap-to-command menu buttons" }
    tunnel  = @{ Actions = @("start", "stop", "status", "permanent-install"); Description = "Manage the public tunnel (throwaway quick tunnel, or a permanent named-tunnel service)" }
    all     = @{ Actions = @("kill", "restart"); Description = "Manage webhook + Chrome + tunnel together" }
}

function Show-Help {
    Write-Output @"
Bot.ps1 - operate the screenshot bot (webhook, browser, tunnel)

USAGE
    scripts\Bot.ps1 <command> [action] [-ConfigPath <path>] [-Tail <n>] [-Teams <csv>]

COMMANDS
    status                     Show webhook, tunnel, and Chrome status in one shot
    webhook <action>           Manage the WeChat webhook process
                                 actions: start | stop | restart | status | logs | watch
    browser <action>           Manage the shared Chrome browser/tabs
                                 actions: restart | warmup
    menu <action>              Push or inspect the WeChat tap-to-command menu buttons
                                 actions: set | get
    tunnel <action>            Manage the public tunnel
                                 actions: start | stop | status | permanent-install
    all <action>               Manage webhook + Chrome + tunnel together
                                 actions: kill | restart
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
    -TunnelToken <token>       Cloudflare named-tunnel token for "tunnel permanent-install"
                                 (Zero Trust -> Networks -> Tunnels -> your tunnel -> install
                                 command). Installs cloudflared as a Windows service bound to
                                 that tunnel -- survives reboots and keeps a stable hostname,
                                 unlike "tunnel start"'s throwaway quick tunnel.

EXAMPLES
    scripts\Bot.ps1 status
    scripts\Bot.ps1 webhook restart
    scripts\Bot.ps1 webhook logs -Tail 200
    scripts\Bot.ps1 webhook watch
    scripts\Bot.ps1 browser restart
    scripts\Bot.ps1 browser warmup -Teams "1,2"
    scripts\Bot.ps1 menu set
    scripts\Bot.ps1 menu get
    scripts\Bot.ps1 tunnel start
    scripts\Bot.ps1 tunnel permanent-install -TunnelToken "eyJhIjoi..."
    scripts\Bot.ps1 all kill
    scripts\Bot.ps1 all restart
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
    & (Join-Path $PSScriptRoot "Stop-WebhookBackground.ps1") -Port (Get-WebhookPort)
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
        if (Test-Path -LiteralPath $path) { Get-Content -LiteralPath $path -Tail $Tail -Encoding UTF8 }
        else { Write-Output "MISSING" }
    }
}

function Invoke-WebhookWatch {
    # Opens the live log watcher in its own new console window and returns immediately -- this
    # process (and whatever called it, e.g. an ansible/WinRM session) is never blocked, and the
    # watcher keeps running with its own visible output even after the parent terminal moves on
    # or closes. -NoExit keeps that new window open if the watcher errors out immediately,
    # instead of it just flashing shut with no chance to read why.
    $watcherScript = Join-Path $PSScriptRoot "Watch-WebhookLog.ps1"
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $watcherScript, "-ConfigPath", $ConfigPath
    ) -WorkingDirectory $root
    Write-Output "Log watcher opened in a new window."
}

function Get-ChromeDebugPort {
    $debugPort = 9221
    try {
        $config = Read-JsonFile $ConfigPath
        $browserTargets = Get-JsonValue $config "browser_targets" $null
        $debugPort = [int](Get-JsonValue $browserTargets "debug_port" 9221)
    } catch {
    }
    return $debugPort
}

function Wait-ForChromeDebugPortRelease {
    # Wait for the debug port to actually release rather than a blind sleep -- starting a fresh
    # Chrome while the old one is still mid-shutdown (or its debug port still momentarily
    # responsive) is exactly the race that produces intermittent "tab not debuggable" errors.
    param([int]$DebugPort, [int]$TimeoutSeconds = 15)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $stillUp = $false
        try { Invoke-RestMethod -Uri "http://127.0.0.1:$DebugPort/json/version" -TimeoutSec 1 | Out-Null; $stillUp = $true } catch { $stillUp = $false }
        if (-not $stillUp) { break }
        Start-Sleep -Milliseconds 500
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
    Wait-ForChromeDebugPortRelease -DebugPort (Get-ChromeDebugPort)
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

function Invoke-Menu {
    # Same secrets/PYTHONPATH setup as Invoke-BrowserWarmup -- a separate one-off python
    # process, safe to run any time (only touches WeChat's menu API, never Chrome/webhook state).
    param([string]$MenuAction)
    Set-Location -LiteralPath $root
    $secretsPath = Join-Path $root "secrets.local.ps1"
    if (Test-Path -LiteralPath $secretsPath) { . $secretsPath }
    $env:PYTHONPATH = Join-Path $root "src"
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (!(Test-Path -LiteralPath $python)) { $python = "python" }
    & $python (Join-Path $root "scripts\run_wechat_menu_sync.py") $MenuAction --config-path $ConfigPath
}

function Invoke-TunnelStart {
    & (Join-Path $PSScriptRoot "Start-PublicTunnel.ps1") -ConfigPath $ConfigPath
}

function Resolve-Cloudflared {
    $command = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    $candidates = @(
        "C:\Program Files (x86)\cloudflared\cloudflared.exe",
        "C:\Program Files\cloudflared\cloudflared.exe",
        (Join-Path $root "runtime\cloudflared\cloudflared.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw "cloudflared.exe not found. Run ansible deploy.yml first (installs it), or pass its path explicitly."
}

function Invoke-TunnelPermanentInstall {
    # Installs cloudflared as a Windows service bound to a named tunnel (token from the
    # Cloudflare Zero Trust dashboard) -- unlike "tunnel start"'s throwaway quick tunnel, this
    # survives reboots, starts automatically, and keeps a stable hostname, since routing lives
    # in Cloudflare's dashboard rather than a local config file. Re-running with a new token
    # replaces whatever tunnel was previously installed (uninstall-then-install), so this is
    # safe to call again if you need to point this host at a different tunnel.
    if ([string]::IsNullOrWhiteSpace($TunnelToken)) {
        throw "tunnel permanent-install requires -TunnelToken <token> (from Cloudflare Zero Trust -> Networks -> Tunnels -> your tunnel -> install command)"
    }
    $cloudflared = Resolve-Cloudflared
    # cloudflared logs its own INFO-level lines to stderr as a matter of course (not an error
    # signal) -- under this script's global $ErrorActionPreference = "Stop", redirecting that
    # stderr into the pipeline (2>&1) wraps each line as a terminating ErrorRecord and aborts the
    # whole script even though cloudflared itself succeeds. Relax to "Continue" just around these
    # two calls so its routine stderr chatter is displayed, not treated as fatal.
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $existing = Get-Service -Name Cloudflared -ErrorAction SilentlyContinue
        if ($null -ne $existing) {
            Write-Output "Uninstalling existing permanent tunnel service..."
            & $cloudflared service uninstall 2>&1 | ForEach-Object { Write-Output $_.ToString() }
            Start-Sleep -Seconds 2
        }
        Write-Output "Installing permanent tunnel service..."
        & $cloudflared service install $TunnelToken 2>&1 | ForEach-Object { Write-Output $_.ToString() }
        Start-Sleep -Seconds 2
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    Get-Service -Name Cloudflared -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType | Format-Table -AutoSize | Out-String | Write-Output
    Write-Output "Route a Public Hostname to http://127.0.0.1:<webhook_port> for this tunnel in the Zero Trust dashboard if you haven't already."
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
    $permanentService = Get-Service -Name Cloudflared -ErrorAction SilentlyContinue
    [pscustomobject]@{
        state = $state
        process_running = $running
        permanent_service_status = if ($null -ne $permanentService) { $permanentService.Status.ToString() } else { $null }
    }
}

function Invoke-AllKill {
    # Stops the webhook + Chrome. Does NOT touch the tunnel (quick or permanent) -- the tunnel
    # is managed independently as infrastructure (see "tunnel permanent-install"/"tunnel
    # start"/"tunnel stop"), since a bot restart has no reason to cycle ingress. Each underlying
    # stop step already tolerates "nothing running", so this is safe to run any time, not just
    # as a recovery step after a stuck state.
    Write-Output "Stopping webhook..."
    Invoke-WebhookStop
    Write-Output "Killing Chrome..."
    Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

function Invoke-AllRestart {
    Invoke-AllKill
    Wait-ForChromeDebugPortRelease -DebugPort (Get-ChromeDebugPort)
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
    # $webhook.state/.ready are $null after a full "all kill" (their JSON files get deleted along
    # with the process) -- go through Get-JsonValue everywhere below instead of dotting straight
    # into them, since Set-StrictMode throws on a property/method access against $null.
    $trackedPid = Get-JsonValue $webhook.state "webhook_pid" $null
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
    $startedAt = Get-JsonValue $webhook.state "started_at" ""
    Write-Output ("  started      : {0} (uptime {1})" -f (Format-Timestamp $startedAt), (Format-Uptime $startedAt))
    $localUrl = Get-JsonValue $webhook.state "local_url" ""
    $webhookPath = Get-JsonValue $webhook.state "webhook_path" ""
    $webhookUrl = if ($localUrl -and $webhookPath) { "$($localUrl.TrimEnd('/'))/$($webhookPath.TrimStart('/'))" } else { "n/a" }
    Write-Output ("  url          : {0}" -f $webhookUrl)
    Write-Output ("  teams        : {0}" -f ((Get-JsonValue $webhook.ready "browser_target_ids" @()) -join ", "))
    Write-Output ("  secrets      : token={0} appid={1} appsecret={2}" -f (Get-JsonValue $webhook.ready "has_token" $false), (Get-JsonValue $webhook.ready "has_appid" $false), (Get-JsonValue $webhook.ready "has_appsecret" $false))

    Write-Output ""
    Write-Output "=== Tunnel ==="
    if ($null -ne $tunnel.permanent_service_status) {
        Write-Output ("  permanent    : {0} (Cloudflared service)" -f $tunnel.permanent_service_status)
    } else {
        Write-Output "  permanent    : not installed"
    }
    if ($tunnel.process_running -and $null -ne $tunnel.state) {
        Write-Output "  quick tunnel : running"
        Write-Output ("    url        : {0}" -f $tunnel.state.tunnel_url)
        Write-Output ("    started    : {0} (uptime {1})" -f (Format-Timestamp $tunnel.state.started_at), (Format-Uptime $tunnel.state.started_at))
    } else {
        Write-Output "  quick tunnel : not running"
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
            "watch" { Invoke-WebhookWatch }
            default { throw "webhook requires an action: start|stop|restart|status|logs|watch" }
        }
    }
    "browser" {
        switch ($Action) {
            "restart" { Invoke-BrowserRestart }
            "warmup" { Invoke-BrowserWarmup }
            default { throw "browser requires an action: restart|warmup" }
        }
    }
    "menu" {
        switch ($Action) {
            "set" { Invoke-Menu -MenuAction "set" }
            "get" { Invoke-Menu -MenuAction "get" }
            default { throw "menu requires an action: set|get" }
        }
    }
    "tunnel" {
        switch ($Action) {
            "start" { Invoke-TunnelStart }
            "stop" { Invoke-TunnelStop }
            "status" { Invoke-TunnelStatus | ConvertTo-Json -Depth 8 }
            "permanent-install" { Invoke-TunnelPermanentInstall }
            default { throw "tunnel requires an action: start|stop|status|permanent-install" }
        }
    }
    "all" {
        switch ($Action) {
            "kill" { Invoke-AllKill }
            "restart" { Invoke-AllRestart }
            default { throw "all requires an action: kill|restart" }
        }
    }
}
