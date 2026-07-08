# Browser Capability Module

## Responsibility
Capture a browser target through Chrome DevTools and apply watermarking. All targets are named
tabs inside one shared Chrome process (managed by `CdpMultiTabService`), not one Chrome process
per target.

## Public API
- `BrowserScreenshotService(config_path)`
- `BrowserScreenshotService.parse_team_id(text)`
- `BrowserScreenshotService.capture(team_id, tab=None, user_id=None, output_dir=None, image_name=None, timeout_seconds=15)`
- `BrowserScreenshotService.warm_up(team_ids=None)` — open/log into every configured team's own
  tab up front, or just the given `team_ids` (see "Startup warm-up")
- `BrowserScreenshotService.describe_watermark(team_id)` / `.set_watermark_field(team_id, field_index, value)` /
  `.set_watermark_opacity(team_id, opacity)` / `.reset_watermark(team_id)` — read/mutate one
  team's watermark override (see "Per-team watermark customization" below)
- `TeamWatermarkSettingsStore(path)` — the underlying per-team override store; `BrowserScreenshotService`
  owns one instance internally (`.watermark_settings`)
- `BrowserProfileManager.tab_count(target)` — how many tabs a target declares (`tab_count`, default 1)
- `BrowserTargetConfig(config_path, config=None)`
- `CdpMultiTabService(port, host="127.0.0.1", max_tabs=None)` — the underlying shared-Chrome,
  named-tab CDP client (see below); `BrowserScreenshotService` owns one instance internally.
  Also exposes `login`, `adopt_tab`, `close_untracked_tabs`, `keep_alive`/`start_keep_alive`/
  `stop_keep_alive`, and `refresh`/`start_auto_refresh`/`stop_auto_refresh` for login-gated sites
  (see "Login-gated targets", "Team-per-tab targets", "Capacity limit and login", "Session
  keep-alive", and "Background page refresh" below).

## Input
- JSON config section: `browser_targets` — `enabled`, `chrome_path`, `debug_port`, `profile_dir`,
  `raw_dir`, `store_dir` (default `storage/screenshots`), `startup_timeout_seconds`, `max_tabs`,
  `ignore_certificate_errors` (needed for self-signed-cert sites, e.g. an on-prem IP-based host),
  and a `targets` map of `team_id -> {name, start_url, app_url?, tab_count?, tab?, login?}`. All
  targets share the one `debug_port`/`profile_dir`. Several `team_id`s can point at the *same*
  physical multi-tab site by giving them identical `name`/`start_url`/`app_url`/`tab_count`/
  `login` and only varying `tab` — see "Team-per-tab targets" below, which is the production
  pattern (e.g. WeChat team numbers `1`-`5` each pinned to one tab of one login-gated site).
  Also `watermark_settings_path` (default `runtime/watermark-team-settings.json`) — where
  per-team watermark overrides persist, see "Per-team watermark customization" below.
- Text command such as `1`, `2`, `3`
- Optional `tab` index override (0-based, must be `< tab_count`); if omitted, `capture()` uses
  the requested team_id's own configured `tab` (default 0)
- Optional `user_id` (e.g. the WeChat `FromUserName`) — see "Output" below for how it affects
  storage
- Optional output directory and image file name

## Output
- PNG file path in `published_path` (watermarked, for the WeChat reply), plus two permanent
  audit copies: `store_path` (pre-watermark bytes) and `watermarked_store_path` (the exact bytes
  sent to WeChat), both filed under `screenshot_store`
- Audit storage is organized `channel_{team_id}/original/...` and `channel_{team_id}/watermarked/...`
  — everyone's captures for one channel land in that channel's two sub-folders, distinguished by
  the timestamp already in each capture's filename (no per-user or per-tab sub-folders)
- Capture metadata including target id, tab index, requester id, shared DevTools port, page
  title, page URL, capture time, and watermark data

## Dependencies
- One Chrome process with remote debugging enabled, launched and reused across all targets
- `Pillow` for watermark rendering
- `screenshot_bot.screenshot_store.ScreenshotStore` for the raw-capture audit trail
- Shared config helpers only

## Run
This module is a library module. It is started by importing and calling the public API.

## Test
```powershell
$env:PYTHONPATH="$PWD\src"
python - <<'PY'
from screenshot_bot.browser import BrowserScreenshotService
svc = BrowserScreenshotService('config.example.json')
print(svc.parse_team_id('1'))
PY
```

## Example
```python
from screenshot_bot.browser import BrowserScreenshotService

svc = BrowserScreenshotService('config.example.json')
info = svc.capture('1', user_id='oWeChatUser123', output_dir='screenshots')
print(info['published_path'], info['store_path'], info['watermarked_store_path'])
```

## Login-gated targets (production config)

A `browser_targets.targets.<id>` entry can carry a `login` block so the WeChat-facing capture
path (`BrowserScreenshotService.capture()` → `BrowserProfileManager.ensure_tab()`) logs in,
keeps the session alive, and keeps the tab's content refreshed automatically — no manual step
needed once configured. Credentials are never written to config; only the *names* of the
environment variables that hold them are, matching the existing `token_env`/`appid_env`/
`appsecret_env` pattern used for the WeChat secrets.

```json
"1": {
  "name": "webstation-test",
  "start_url": "https://10.121.0.14/login.html",
  "app_url": "https://10.121.0.14/",
  "tab_count": 5,
  "tab": 0,
  "login": {
    "enabled": true,
    "username_env": "WEBSTATION_USERNAME",
    "password_env": "WEBSTATION_PASSWORD",
    "keep_alive_interval_seconds": 60,
    "refresh_interval_seconds": 300
  }
}
```

Optional `login` keys: `username_selector`, `password_selector`, `submit_selector` (override the
`#txtUserID`/`#txtPassWord`/`#login` defaults, which match this particular site's login form,
for a different site). `keep_alive_interval_seconds`/`refresh_interval_seconds` are omitted or
`0` to disable either loop.

### Credentials

Credentials never go in `config.example.json`/`group_vars/*.yml` — only the env var *names*
that `username_env`/`password_env` point at do. Where the actual values live depends on how
this runs:

| Run mode | File to edit | Committed to Git? |
|---|---|---|
| Local (`scripts/Start-WebhookOnly.ps1`) | `secrets.local.ps1` (repo root) | No — copy from `secrets.local.example.ps1` |
| Ansible-deployed | `ansible/files/secrets.local.ps1` | No — copy from `ansible/files/secrets.local.example.ps1` |

Both example files already list `WEBSTATION_USERNAME`/`WEBSTATION_PASSWORD` alongside the
WeChat secrets — copy and fill in real values, same as the WeChat ones:

```powershell
$env:WEBSTATION_USERNAME = "paste-username-here"
$env:WEBSTATION_PASSWORD = "paste-password-here"
```

These are **optional at the process level**: `build_wechat_official_server()` doesn't check for
them at startup the way it hard-requires the WeChat secrets, since login is opt-in per target.
They're only read — and required — lazily, the first time `ensure_tab()` handles a target whose
`login.enabled` is `true`. If the named env var is unset (or the file was never sourced), that
capture fails with a clear `RuntimeError: environment variable WEBSTATION_PASSWORD is not set`
(via `_read_login_env` in `profile_manager.py`) instead of silently screenshotting the login
page. Because the failed attempt is *not* cached as "handled" (`_login_applied` only gets the
tab name added after a successful `_apply_login()`), fixing the env var and retrying — no
process restart needed — is enough; the very next capture for that target tries login again
rather than being permanently stuck.

For `ansible/secrets-status.yml`'s reporting of whether these are configured, see
`ansible/README.md`.

Verify locally before relying on it for a real (production or test) run — `warm_up()` logs into
every configured target/tab up front (see "Team-per-tab targets" → "Startup warm-up") and
returns per-target errors instead of raising, so one bad credential doesn't hide the rest:

```powershell
$env:WEBSTATION_USERNAME = "..."
$env:WEBSTATION_PASSWORD = "..."
python -c "import json; from screenshot_bot.browser import BrowserScreenshotService; svc = BrowserScreenshotService('config.example.json'); print(json.dumps(svc.warm_up(), indent=2))"
```
A successful run shows an empty `errors` list for the target and `tabs` populated for every tab
(`webstation-test`, `webstation-test_tab1`, ... up to `tab_count - 1`). Verified locally: all 5
tabs of the `webstation-test` target logged in and reported zero errors.

Only tab 0 actually attempts login (see "Team-per-tab targets"), so a missing/wrong credential
shows up as `"errors": ["tab 0: environment variable WEBSTATION_PASSWORD is not set"]` — but
tabs 1..N-1 still show up in `tabs` with no error, since opening them at `app_url` doesn't itself
check whether tab 0 ever authenticated. Verified: with `WEBSTATION_PASSWORD` unset, `tabs`
for `webstation-test` came back as `["webstation-test_tab1", ..., "webstation-test_tab4"]`
(tab 0 missing) with that one error — so for this target, only an empty `errors` list means
every tab is actually logged in; a non-empty `tabs` list on its own does not.

This was verified end-to-end against the real site through the exact production call path
(`BrowserScreenshotService.capture('4', ...)`, the same method the WeChat webhook calls): cold
start (Chrome launch + login) took ~17s, a warm capture on an already-authenticated tab took
under 1s, and the screenshot came back watermarked as usual.

`BrowserProfileManager.ensure_tab()` only calls `login()`/starts the keep-alive and refresh
loops the *first* time a given tab name is seen by the current process — not on every capture.
Because `has_tab()` state lives in process memory, a process restart (crash, redeploy, etc.)
while Chrome keeps running would otherwise look like "first time" again and open a *second*
tab for the same target — and this app rejects a second login attempt while a session is
already active ("a user is already logged on to another tab"). To avoid that,
`ensure_tab()` first calls `CdpMultiTabService.adopt_tab(name, origin)`, which matches an
already-open tab by URL origin and registers it under `name` instead of opening a duplicate;
`login()` on an adopted, already-authenticated tab is a fast no-op (see "Capacity limit and
login" below). Verified: a second, independent process pointed at the same running Chrome
adopted the existing tab and completed its capture in under 1 second, with no duplicate tab
created.

## Team-per-tab targets

A target can open more than one tab of itself via `tab_count` (default 1). Tab 0 is the one
that logs in (`start_url`) and drives `keep_alive`/`refresh`; tabs 1..N-1 are opened directly
at `app_url` (falls back to `start_url` if omitted, e.g. for non-login-gated multi-tab targets)
and simply reuse tab 0's already-authenticated session — no per-tab login is attempted.

There are two ways to pick which tab a capture uses:

1. **Explicit `tab=` argument to `capture()`** — for tooling/audit scripts that want to walk
   every tab of one target themselves: `BrowserScreenshotService.capture(team_id, tab=3)` always
   captures tab index 3, regardless of what that team_id's config says. See
   `scripts/run_webstation_multitab_capture.py`.
2. **A `"tab"` field on the target's own config** — the production pattern. Several `team_id`s
   (e.g. WeChat text triggers `1`-`5`) can point at the *same* physical site by giving each one
   an identical `name`/`start_url`/`app_url`/`tab_count`/`login` block and only varying `"tab"`:

```json
"1": {
  "name": "webstation-test",
  "start_url": "https://10.121.0.14/login.html",
  "app_url": "https://10.121.0.14/",
  "tab_count": 5,
  "tab": 0,
  "login": { "...": "..." }
},
"2": {
  "name": "webstation-test",
  "start_url": "https://10.121.0.14/login.html",
  "app_url": "https://10.121.0.14/",
  "tab_count": 5,
  "tab": 1,
  "login": { "...": "..." }
}
```
(repeat for `"3"`/`"4"`/`"5"` with `"tab": 2`/`3`/`4`)

`capture(team_id, tab=None, ...)` resolves `tab` from `target.get("tab", 0)` whenever the
caller doesn't pass one explicitly, so a WeChat user texting `"3"` transparently gets tab index
2 of `webstation-test` without the WeChat workflow layer needing to know tabs exist at all.

Each tab gets its own Chrome DevTools tab, named `<target_name>` (tab 0) or
`<target_name>_tab<N>` (tab N), and its own raw-capture history via `ScreenshotStore`:
`published_path`/`raw_path` still land in the usual flat `output_dir`/`raw_dir` (unchanged, for
the WeChat reply), but every capture is additionally saved *twice* — once pre-watermark to
`{store_dir}/channel_{team_id}/original/{timestamp}_{duration}ms.png` (returned as `store_path`),
once post-watermark to `{store_dir}/channel_{team_id}/watermarked/{timestamp}_{duration}ms.png`
(returned as `watermarked_store_path`) — regardless of who requested it or which tab it resolved to.

Verified end-to-end (against a local mock of the login-gated site, since the real
`10.121.0.14` isn't reachable from every environment): 5 different simulated WeChat users each
capturing a different team_id (`"1"`-`"5"`) triggers exactly one real login (not five) and
stores each capture under its own `channel_{team_id}/{original,watermarked}/...` directories;
`keep_alive`/`auto_refresh` keep firing in the background for as long as the owning process
stays up; and a simulated process restart (fresh `BrowserScreenshotService`, same running
Chrome) adopts all 5 existing tabs with no duplicates and no repeated login.

### Startup warm-up

`warm_up(team_ids=None)` opens (and logs into) every *requested* team's own tab before the first
real request, in a background thread right after the webhook process starts (see
`scripts/run_wechat_official_webhook.py`). `team_ids` limits which teams get proactively opened —
omit it (the default, used at webhook startup) to warm up every configured team; pass e.g.
`["3"]` to warm up just that one. An unlisted team isn't broken by being skipped — `capture()`'s
own `ensure_tab()` call opens/logs into it lazily on its first real request either way.

Crucially, warming up team `"3"` opens **only** team 3's own pinned tab, not every tab of
whatever physical target it shares with other teams. Earlier versions of this method looped
`range(tab_count)` for the first team_id reached per shared target name, which happened to work
by accident when warming up *all* teams (every tab needed to open eventually anyway) but silently
opened every other sharing team's tab too the moment scoping was introduced — asking to warm up
just team 3 would still open teams 1/2/4/5's tabs as a side effect, since they all declare the
same `tab_count`. `warm_up()` now groups by target name and opens exactly the set of tab indices
the *requested* teams actually own (`target["tab"]`), so warming up team "3" alone opens exactly
one tab. Warming up every team still behaves exactly as before (all tabs of a shared target open
once, not once per team_id) since that case naturally includes every team's own tab index.

One caveat this creates: only tab index 0 of a shared target ever actually logs in (see "Team-
per-tab targets" above) — every other tab just reuses that session. If you warm up (or capture)
a non-zero-tab team *before* tab 0 has ever been opened for that target (e.g. `-Teams "2,3"`
without also including whichever team owns `"tab": 0`), those tabs will load unauthenticated,
since no session exists yet for them to reuse. Include the tab-0 team in the scope (or let a
normal, unscoped warm-up/first request establish it first) to avoid this.

When several `team_id`s share one target `name`, only that physical target's session is
established once — not once per team_id sharing it — since a slow first login (still
mid-navigation) getting hit by concurrent `login()` attempts on the very same tab a few
milliseconds later is what produced cascading `connection aborted`/`tab not debuggable` errors
during testing before this was fixed. One team's failure (e.g. a missing login env var) is
recorded per-team_id and skipped rather than aborting the rest — `ensure_tab()` retries that
team's login on the next `capture()` or `warm_up()` call since a failed login is never marked as
applied (see `BrowserProfileManager.ensure_tab`).

### No extra default tab

Chrome opens its own blank "New Tab" on a fresh launch, since `launch_chrome()` passes no start
URL. `BrowserProfileManager` closes it automatically — but only *after* the first real tab has
been created, never before: closing a browser's only remaining tab quits the whole Chrome
process, so the ordering matters. The result is that a fresh launch ends up with exactly the
configured tabs (e.g. 5 for one `tab_count: 5` group), no stray blank tab alongside them.
Implemented via `CdpMultiTabService.close_untracked_tabs()` — closes every page the service
hasn't itself opened/adopted, meaningful only right after a fresh launch before anything else
has been added.

## Per-team watermark customization

A team's watermark (field text, background opacity) can be overridden independently of every
other team, without touching `config.json`. Overrides are keyed by `team_id`, persisted as one
small JSON file (`browser_targets.watermark_settings_path`, default
`runtime/watermark-team-settings.json`), and merged onto the global `watermark` config *only for
that team's own capture* — `resolve_watermark_config(base_config, overrides)` returns a new dict,
never mutating the shared base config or another team's result. A field's *label* is never
overridden, only its *value* — so a team customizes what a row says without needing to retype
the label.

`capture()` looks up `team_id`'s overrides on every call; if none exist it reuses the one shared
`WatermarkRenderer` instance built at startup (zero extra cost for the common case). If overrides
exist, it builds a fresh `WatermarkRenderer` for just that capture — cheap, since the renderer is
a stateless wrapper around a config dict (the font is loaded fresh on every `apply()` call
regardless of caller).

These are driven by WeChat chat commands parsed in
`workflow/watermark_commands.py` (see the root `README.md` → "Watermark customization" for the
command grammar); `BrowserScreenshotService.describe_watermark`/`set_watermark_field`/
`set_watermark_opacity`/`reset_watermark` are what the workflow layer calls in response.
`set_watermark_opacity` raises `ValueError` outside `0`-`255`; `set_watermark_field` raises
`IndexError` for a field index the team doesn't have. An empty string is a valid value —
`set_watermark_field(team_id, index, "")` clears that field's content while keeping its label —
and the two example fields (`Test Area`, `Test Item`) default to empty in `config.example.json`
and `ansible/group_vars/*.yml`.

## CdpMultiTabService

A minimal CDP client for managing several named tabs on one already-running Chrome
instance and screenshotting them without switching the foreground tab. It shares
`DevToolsWebSocket`/`http_json` from `devtools_client.py`. This is what
`BrowserScreenshotService`/`BrowserProfileManager` use internally, mapping each `team_id`
to its own named tab; it can also be used standalone (no `browser_targets` config or
watermarking) as shown below.

```python
from screenshot_bot.browser import CdpMultiTabService, launch_chrome, wait_for_port

launch_chrome(port=9333, user_data_dir="runtime/cdp-demo-profile")
wait_for_port(9333)

svc = CdpMultiTabService(port=9333)
svc.add_tab("tab_a", "https://example.com")
svc.add_tab("tab_b", "https://httpbin.org/html")
print(svc.list_tabs())
result = svc.screenshot("tab_a", output_path="runtime/tab_a.png")
print(result["elapsed_ms"])
```

See `scripts/run_cdp_multi_tab_demo.py` for a runnable end-to-end demo.

### Capacity limit and login

`CdpMultiTabService(port, max_tabs=N)` makes `add_tab` raise once `N` tabs are open —
use this to cap how many tabs of one site the service is allowed to hold.

`login(name, username, password, username_selector=..., password_selector=..., submit_selector=...)`
fills a login form (via the native `<input>` value setter + `input`/`change` events, so it
works with framework-controlled inputs) and clicks the submit selector. It's safe to call
repeatedly: if the tab already redirected away from the login page (e.g. because another tab
in the same Chrome process already authenticated), it returns `logged_in: True` immediately
instead of waiting for a login form that will never appear.

Key operational finding from testing against a real login-gated site (Schneider Electric
EcoStruxure Building Operation WebStation): a single Chrome process shares one cookie jar
across all its tabs, so logging in once is enough — every tab opened afterward inherits the
session automatically as long as it navigates to the app itself, not the login page again.
Some such apps additionally reject a *second* login attempt while a session is already active
("a user is already logged on to another tab"), so the working pattern is:

```python
from screenshot_bot.browser import CdpMultiTabService, launch_chrome, wait_for_port

launch_chrome(port=9333, user_data_dir="runtime/cdp-demo-profile", ignore_certificate_errors=True)
wait_for_port(9333)

svc = CdpMultiTabService(port=9333, max_tabs=5)
svc.add_tab("tab_0", "https://example-site/login.html")
svc.login("tab_0", "myuser", "mypassword")   # log in exactly once

for i in range(1, 5):
    svc.add_tab(f"tab_{i}", "https://example-site/")  # not login.html — reuses the session

for name in ("tab_0", "tab_1", "tab_2", "tab_3", "tab_4"):
    svc.screenshot(name, f"runtime/{name}.png")
```

A login session tied to a session-only cookie does **not** survive a full Chrome restart
regardless of `user_data_dir` persistence — that's the target server's cookie policy, not
something the client can override. Keep the Chrome process running for the session to last.

### Session keep-alive

Even with the Chrome process kept alive, a server-side session can still idle out if no
authenticated request is sent for too long. Our tabs mostly sit on a splash screen and never
trigger the app's own data polling, so that natural traffic doesn't happen on its own.

Reading the WebStation frontend bundle (`js/9855.js`, minified but not obfuscated) found the
exact mechanism the app itself relies on: a React hook called `useWatchDog()` runs

```js
const intervalHandle = setInterval(async () => {
  // Make sure the server keeps our session alive
  peekObject(PathHelper.getCurrentServerPath());
}, 60000);
```

`peekObject` ends up POSTing to `./json/POST` with a JSON-RPC-style body (`{"command": "PeekObjects", ...}`),
an `X-CSRF-Token` header read from a `#csrf` hidden `<input>` embedded in the page HTML
(`getCSRFToken()` in `login.js`), and `credentials: "same-origin"` so the session cookie rides
along. `PeekObjects` needs a valid object path to target, which our tabs don't have (they never
navigate anywhere in the object tree), so `CdpMultiTabService.keep_alive()` sends a
`GetServersInfo` command instead — a read-only command that needs no path and returns HTTP 200
just like a real app request, resetting the server's idle timer the same way:

```python
svc.keep_alive("tab_0")                                    # one-shot ping, returns {"status": 200, "ok": True}
svc.start_keep_alive("tab_0", interval_seconds=60)          # background thread, mirrors the app's own interval
svc.stop_keep_alive("tab_0")
```

Only one tab needs to run this: all tabs in the same Chrome process share the session cookie,
so a ping from any one of them keeps the whole session — and therefore every tab — alive.

### Background page refresh

`keep_alive` only protects the server-side *session* (the cookie). It doesn't protect what's
*on screen*: this app's live dashboard data comes from `PropertySubscription`/`ReadSubscription`
polling that runs on a timer inside the page's own JS, and Chrome throttles timers and network
activity for tabs that are open but not in the foreground. Since this service is explicitly built
to run several tabs in the background without switching focus between them (see the top-level
requirement not to steal foreground), a backgrounded tab's displayed data can go stale even while
its session is perfectly alive.

`refresh(name, ignore_cache=False, timeout_seconds=10)` reloads the tab via CDP `Page.reload()`.
Cookies survive a reload, so an already-authenticated tab lands right back on the authenticated
app (verified against the real site: after several reloads the tab stayed on the dashboard URL,
never bounced back to `login.html`).

`start_auto_refresh(name, interval_seconds=300)` / `stop_auto_refresh(name)` run `refresh` on a
background thread, the same way `start_keep_alive`/`stop_keep_alive` run `keep_alive`. The
difference is scope: `keep_alive` only needs to run on *one* tab because the session cookie is
shared, but each tab has its *own* DOM and subscriptions, so `start_auto_refresh` must be started
per tab — refreshing `tab_0` does nothing for `tab_1`'s staleness.

```python
for name in ("tab_0", "tab_1", "tab_2", "tab_3", "tab_4"):
    svc.start_auto_refresh(name, interval_seconds=300)  # one loop per tab

# ... later, before shutdown ...
for name in ("tab_0", "tab_1", "tab_2", "tab_3", "tab_4"):
    svc.stop_auto_refresh(name)
```

See `scripts/run_cdp_webstation_demo.py` for a runnable end-to-end demo against a real
login-gated site, including both the keep-alive loop and per-tab auto-refresh
(`--refresh-interval-seconds`, default 300; pass `0` to disable).
