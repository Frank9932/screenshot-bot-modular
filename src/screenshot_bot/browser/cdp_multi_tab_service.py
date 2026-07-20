import base64
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from screenshot_bot.runtime.console_log import log_line

from .devtools_client import DevToolsWebSocket, http_json
from .equipment_navigation import navigate_to_equipment_graphic


def _http_put_json(url, timeout=5):
    request = Request(url, method="PUT")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_get_text(url, timeout=5):
    with urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8")


def resolve_chrome_path(chrome_path=None):
    candidates = [
        chrome_path or "",
        str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ]
    local_app_data = os.environ.get("LocalAppData")
    if local_app_data:
        candidates.append(str(Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    raise FileNotFoundError("Chrome executable not found")


def wait_for_port(port, host="127.0.0.1", timeout_seconds=15):
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        try:
            http_json(f"http://{host}:{port}/json/version", timeout=1)
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Chrome did not open debug port {port}")


def launch_chrome(port, user_data_dir, chrome_path=None, headless=False, ignore_certificate_errors=False):
    """Launch Chrome with a persistent user_data_dir so cookies/localStorage/site permissions
    (e.g. accepted certificate exceptions) survive across restarts as long as the same profile
    directory is reused. Note this does NOT guarantee login sessions survive a restart: sites
    that issue session-only cookies (no Max-Age/Expires) have those cleared by the browser on
    close regardless of profile persistence. What a persistent profile does guarantee is that a
    login stays valid for every tab opened later in the same still-running Chrome process, since
    they all share one cookie jar."""
    user_data_dir = Path(user_data_dir).resolve()
    user_data_dir.mkdir(parents=True, exist_ok=True)
    args = [
        resolve_chrome_path(chrome_path),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        # Only the foreground tab renders at full rate by default; every other team's tab sits
        # occluded and Chrome throttles its compositor. The first Page.captureScreenshot call on
        # a tab that's been sitting occluded has to wait for it to un-throttle and produce a
        # fresh frame, which can take longer than capture_timeout_seconds -- every later call on
        # the same (now recently-active) tab is fast. These flags keep every tab rendering at
        # full rate regardless of occlusion/focus, so the first real capture isn't the one that
        # pays this cost.
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
    ]
    if headless:
        args.append("--headless=new")
    if ignore_certificate_errors:
        args.append("--ignore-certificate-errors")
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class CdpMultiTabService:
    """Minimal multi-tab screenshot service against one already-running Chrome instance."""

    def __init__(self, port, host="127.0.0.1", max_tabs=None):
        self.host = host
        self.port = port
        self.max_tabs = max_tabs
        self._tabs = {}
        self._keep_alive_threads = {}
        self._refresh_threads = {}
        self._tab_locks = {}
        self._tab_locks_guard = threading.Lock()

    def _lock_for(self, name):
        # Every CDP-issuing method below (screenshot/login/keep_alive/navigate/refresh/
        # navigate_equipment) opens its own independent DevToolsWebSocket connection to the same
        # tab, with nothing serializing them against each other -- keep_alive runs on its own
        # background thread every keep_alive_interval_seconds, auto-refresh on another every
        # refresh_interval_seconds, and a WeChat capture request can arrive on a third at any
        # time. A scheduled Page.reload() (refresh) landing while a keep_alive ping or a login()
        # fill/submit sequence is mid-flight tears down the page's JS execution context out from
        # under it -- observed live: a tab wedged permanently (every subsequent login() call
        # timing out on "login page did not become ready") starting within ~10s of that tab's
        # first scheduled hourly refresh, and never recovered on its own. Serializing every
        # operation on one tab through its own lock closes that race: at most one CDP operation
        # touches a given tab's page/JS state at a time, so a reload can no longer land mid-ping.
        with self._tab_locks_guard:
            if name not in self._tab_locks:
                self._tab_locks[name] = threading.Lock()
            return self._tab_locks[name]

    def add_tab(self, name, url):
        if name in self._tabs:
            raise ValueError(f"tab already exists: {name}")
        if self.max_tabs is not None and len(self._tabs) >= self.max_tabs:
            raise RuntimeError(f"tab limit reached ({self.max_tabs})")
        page = _http_put_json(f"http://{self.host}:{self.port}/json/new?{quote(url, safe=':/?&=%#')}")
        self._tabs[name] = page["id"]
        return page["id"]

    def has_tab(self, name):
        return name in self._tabs

    def close_untracked_tabs(self):
        """Close every page this service didn't open/adopt itself — namely the default "New
        Tab" Chrome opens on its own when launched with no start URL. Only meaningful right
        after a fresh launch_chrome(), before any add_tab()/adopt_tab() call: at that point
        every existing page is one Chrome created on its own, not one of ours."""
        tracked_target_ids = set(self._tabs.values())
        closed = []
        for target_id, page in self._pages_by_target_id().items():
            if target_id in tracked_target_ids or page.get("type") != "page":
                continue
            _http_get_text(f"http://{self.host}:{self.port}/json/close/{target_id}")
            closed.append(target_id)
        return closed

    def adopt_tab(self, name, url_prefix):
        """Register an already-open browser tab under `name` by matching a URL prefix, instead
        of opening a new one. `has_tab`/`_tabs` only exist in this process's memory, so a fresh
        process (e.g. after a restart) doesn't know about tabs a previous process already
        created and logged into — without this, ensure_tab-style callers would open a duplicate
        tab and attempt a second login on a site that only allows one active session per
        account. Returns the target id if a match was found and adopted, else None."""
        if name in self._tabs:
            return self._tabs[name]
        if self.max_tabs is not None and len(self._tabs) >= self.max_tabs:
            raise RuntimeError(f"tab limit reached ({self.max_tabs})")
        claimed_target_ids = set(self._tabs.values())
        for target_id, page in self._pages_by_target_id().items():
            if target_id in claimed_target_ids:
                continue
            if page.get("type") == "page" and page.get("url", "").startswith(url_prefix):
                self._tabs[name] = target_id
                return target_id
        return None

    def list_tabs(self):
        pages = self._pages_by_target_id()
        result = []
        for name, target_id in self._tabs.items():
            page = pages.get(target_id, {})
            result.append({
                "name": name,
                "target_id": target_id,
                "url": page.get("url", ""),
                "title": page.get("title", ""),
            })
        return result

    def screenshot(self, name, output_path=None, timeout_seconds=15):
        page = self._get_page(name)
        started = time.perf_counter()
        with self._lock_for(name), DevToolsWebSocket(page["webSocketDebuggerUrl"], timeout=timeout_seconds) as client:
            client.call("Page.enable")
            result = client.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        png_bytes = base64.b64decode(result["data"])
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(png_bytes)
        return {
            "name": name,
            "elapsed_ms": elapsed_ms,
            "path": str(output_path) if output_path else None,
            "bytes": png_bytes,
        }

    def navigate_equipment(self, name, path, pane_height="12%", settle_seconds=3.0, timeout_seconds=35):
        """Route an already-open, already-logged-in tab to one equipment's graphic page via the
        SPA's own hash routing (no full page navigation/re-login involved) and wait for it to
        render -- see equipment_navigation.navigate_to_equipment_graphic for the actual sequence."""
        page = self._get_page(name)
        with self._lock_for(name), DevToolsWebSocket(page["webSocketDebuggerUrl"], timeout=timeout_seconds) as client:
            client.call("Runtime.enable")
            navigate_to_equipment_graphic(
                client, path, pane_height=pane_height, settle_seconds=settle_seconds, timeout_seconds=timeout_seconds
            )
        return {"name": name, "path": path}

    def login(
        self,
        name,
        username,
        password,
        username_selector="#txtUserID",
        password_selector="#txtPassWord",
        submit_selector="#login",
        timeout_seconds=30,
    ):
        """Fill and submit a login form in the given tab. All tabs opened afterward in this same
        Chrome process share its cookie jar, so they inherit the resulting session automatically
        (this call is also safe to repeat on an already-authenticated tab: it detects the
        redirect away from the login page and returns immediately instead of timing out)."""
        page = self._get_page(name)
        with self._lock_for(name), DevToolsWebSocket(page["webSocketDebuggerUrl"], timeout=timeout_seconds) as client:
            client.call("Page.enable")
            client.call("Runtime.enable")
            # The static HTML ships placeholder form fields, but the app's SPA bootstrap tears
            # that DOM down and re-renders its own login form once ready, marked by the body
            # class flipping from "loading" to "loginPageLoaded". Filling/submitting before that
            # either hits elements that are about to be discarded or a page that never wires up
            # a submit handler, so this must be a hard gate, not a best-effort wait.
            # If a valid session cookie already exists (e.g. this is a second tab opened after
            # another tab already logged in, since cookies are shared within one Chrome process),
            # the app redirects away from login.html on its own without ever reaching that class
            # — that counts as already logged in, not a failure.
            state = self._wait_for_login_page_state(client, timeout_seconds)
            if state == "already_authenticated":
                return {"name": name, "logged_in": True}
            if state != "ready":
                raise RuntimeError(f"login page did not become ready after {timeout_seconds}s: {name}")
            self._wait_for_selector(client, username_selector, timeout_seconds)

            fill_script = f"""
                (function() {{
                    function setValue(selector, value) {{
                        var el = document.querySelector(selector);
                        if (!el) return false;
                        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(el, value);
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                        el.dispatchEvent(new Event('change', {{bubbles: true}}));
                        return true;
                    }}
                    return setValue({json.dumps(username_selector)}, {json.dumps(username)})
                        && setValue({json.dumps(password_selector)}, {json.dumps(password)});
                }})()
            """
            filled = client.call("Runtime.evaluate", {"expression": fill_script})
            if not filled.get("result", {}).get("value"):
                raise RuntimeError(f"login form fields not found in tab: {name}")

            submit_script = f"""
                (function() {{
                    var el = document.querySelector({json.dumps(submit_selector)});
                    if (!el) return false;
                    el.click();
                    return true;
                }})()
            """
            submitted = client.call("Runtime.evaluate", {"expression": submit_script})
            if not submitted.get("result", {}).get("value"):
                raise RuntimeError(f"login submit button not found in tab: {name}")

            logged_in = self._wait_for_login(client, username_selector, timeout_seconds)
        return {"name": name, "logged_in": logged_in}

    def keep_alive(self, name, fetch_url="./json/POST", csrf_selector="#csrf", command=None, timeout_seconds=10):
        """Send one authenticated JSON-RPC ping, replicating the request shape the app's own
        session watchdog uses (see useWatchDog() in the WebStation bundle, chunk 9855.js):
        PeekObjects on the app's own current server path -- the same command and the same path
        (read from the page's own URL hash, which is exactly what the bundle's
        PathHelper.getCurrentServerPath() resolves to) the real watchdog uses, verified against
        the live server to return the same {"PeekObjectsRes": [...]} shape it gets. An earlier
        version of this sent a GetServersInfo ping instead (a guess, since PeekObjects needs a
        valid path and this method had no way to discover one) — that guess returned a plain
        HTTP 200 forever, including for hours after the session had actually died server-side,
        because a 200 status alone does not mean the server treated the request as real
        activity.

        Raises if the server reports the session as already logged out. This server signals
        that with HTTP 200 and a body containing "...LOGGED_OUT..." (e.g.
        `{"ERROR_LOGGED_OUT": "LoggedOut", "ErrMsg": "CLIENT_HAVE_BEEN_LOGGED_OUT", ...}`) rather
        than a 4xx status, so checking only the status code — as before — silently treated an
        already-dead session as a successful ping. Raising here matters operationally too:
        start_keep_alive's loop only logs an actual exception, never inspects a plain return
        value, so a failure that doesn't raise is invisible in the logs no matter what it
        returns."""
        page = self._get_page(name)
        explicit_command_json = json.dumps(json.dumps(command)) if command is not None else "null"
        ping_script = f"""
            (async function() {{
                var csrfEl = document.querySelector({json.dumps(csrf_selector)});
                var token = csrfEl ? csrfEl.value : '';
                var explicitCmd = {explicit_command_json};
                var cmd;
                if (explicitCmd) {{
                    cmd = explicitCmd;
                }} else {{
                    var serverPath = decodeURIComponent(window.location.hash.replace(/^#/, ''));
                    cmd = JSON.stringify({{command: 'PeekObjects', data: [serverPath || '/']}});
                }}
                var resp = await fetch({json.dumps(fetch_url)}, {{
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {{'Content-Type': 'application/json', 'X-CSRF-Token': token}},
                    body: cmd
                }});
                var text = await resp.text();
                return JSON.stringify({{status: resp.status, body: text, url: location.href}});
            }})()
        """
        with self._lock_for(name), DevToolsWebSocket(page["webSocketDebuggerUrl"], timeout=timeout_seconds) as client:
            client.call("Runtime.enable")
            result = client.call("Runtime.evaluate", {"expression": ping_script, "awaitPromise": True})
        value = result.get("result", {}).get("value")
        parsed = json.loads(value) if value else {}
        status = parsed.get("status")
        body = str(parsed.get("body", ""))
        url = str(parsed.get("url", ""))
        # A 6.5h live soak test (2026-07-17) found this LOGGED_OUT-in-body check alone isn't
        # enough: once the tab has *already* fallen back to login.html (as opposed to catching
        # the transition the moment it happens), this same ping can come back HTTP 200 with a
        # body that doesn't contain "LOGGED_OUT" -- observed live, this let a dead session go
        # undetected for ~47 minutes even though the tab was provably sitting on login.html the
        # whole time (confirmed by an independent URL check outside this method), because
        # keep_alive() itself kept reporting {"ok": True}. Checking the tab's own URL closes
        # that gap directly, independent of whatever the response body happens to say.
        on_login_page = "login.html" in url
        logged_out = "LOGGED_OUT" in body or on_login_page
        if status != 200 or logged_out:
            raise RuntimeError(
                f"keep_alive ping rejected for {name} (status={status}, logged_out={logged_out}, "
                f"on_login_page={on_login_page}): {body[:200]}"
            )
        return {"name": name, "status": status, "ok": True}

    def start_keep_alive(self, name, interval_seconds=60, on_failure=None, **keep_alive_kwargs):
        """Start a background thread that calls keep_alive(name, ...) every interval_seconds —
        matching the 60-second interval the app's own watchdog uses. Only one tab needs this
        running: all tabs in this Chrome process share the same session cookie, so a ping from
        any one of them keeps the whole session (and therefore every tab) alive. Returns a
        threading.Event; call stop_keep_alive(name) to stop it.

        keep_alive() detects a dead session and raises, but a raised exception on its own does
        not get the session back — without on_failure, the loop just logs the failure and goes
        back to sleep, so every capture after the real death silently screenshots the login page
        forever (ensure_tab() only calls login() the first time a tab name is seen). on_failure,
        if given, is called with the exception so a caller that holds the credentials (e.g.
        BrowserProfileManager) can re-authenticate and hand back a fresh cookie."""
        self.stop_keep_alive(name)
        stop_event = threading.Event()

        def _loop():
            while not stop_event.wait(interval_seconds):
                try:
                    self.keep_alive(name, **keep_alive_kwargs)
                except Exception as error:
                    log_line("browser", f"keep_alive({name}) failed: {error}")
                    if on_failure is None:
                        continue
                    try:
                        on_failure(error)
                    except Exception as recovery_error:
                        log_line("browser", f"keep_alive({name}) recovery failed: {recovery_error}")

        thread = threading.Thread(target=_loop, daemon=True)
        self._keep_alive_threads[name] = (thread, stop_event)
        thread.start()
        return stop_event

    def stop_keep_alive(self, name):
        entry = self._keep_alive_threads.pop(name, None)
        if entry is None:
            return
        thread, stop_event = entry
        stop_event.set()
        thread.join(timeout=2)

    def navigate(self, name, url, timeout_seconds=10):
        """Force-navigate the tab to `url` via CDP Page.navigate(). Used before a recovery
        login() attempt: a session that died server-side (idle timeout caught by keep_alive's
        ping) doesn't necessarily redirect the tab's DOM to login.html on its own the way the
        120-minute client-side auto-logout does, so _wait_for_login_page_state() could misread
        the stale app DOM as 'already_authenticated' (its check for that state is just "URL is
        not login.html"). Navigating to the login URL first guarantees a real, current read of
        auth state instead of trusting whatever the tab happened to be showing."""
        page = self._get_page(name)
        with self._lock_for(name), DevToolsWebSocket(page["webSocketDebuggerUrl"], timeout=timeout_seconds) as client:
            client.call("Page.enable")
            client.call("Page.navigate", {"url": url})
        return {"name": name, "url": url}

    def refresh(self, name, ignore_cache=False, timeout_seconds=10):
        """Reload the tab via CDP Page.reload(). Chrome throttles timers and network activity
        for hidden/background tabs, which can stall a page's own live-data subscriptions (e.g.
        this app's PropertySubscription polling) even though the tab is technically still open.
        Reloading forces a fresh render with current data before the next screenshot. Cookies
        survive a reload, so an authenticated tab stays authenticated after this call."""
        page = self._get_page(name)
        with self._lock_for(name), DevToolsWebSocket(page["webSocketDebuggerUrl"], timeout=timeout_seconds) as client:
            client.call("Page.enable")
            client.call("Page.reload", {"ignoreCache": ignore_cache})
        return {"name": name}

    def start_auto_refresh(self, name, interval_seconds=300, **refresh_kwargs):
        """Start a background thread that reloads the tab every interval_seconds. Unlike
        keep_alive (one ping keeps the whole shared session alive), refresh is per-tab: each
        tab has its own rendered DOM/subscriptions, so this must be started separately for every
        tab whose on-screen content should stay fresh. Returns a threading.Event; call
        stop_auto_refresh(name) to stop it."""
        self.stop_auto_refresh(name)
        stop_event = threading.Event()

        def _loop():
            while not stop_event.wait(interval_seconds):
                try:
                    self.refresh(name, **refresh_kwargs)
                except Exception as error:
                    log_line("browser", f"refresh({name}) failed: {error}")

        thread = threading.Thread(target=_loop, daemon=True)
        self._refresh_threads[name] = (thread, stop_event)
        thread.start()
        return stop_event

    def stop_auto_refresh(self, name):
        entry = self._refresh_threads.pop(name, None)
        if entry is None:
            return
        thread, stop_event = entry
        stop_event.set()
        thread.join(timeout=2)

    def _wait_for_login_page_state(self, client, timeout_seconds, poll_interval=0.3):
        # location.href briefly reads "about:blank" right after add_tab(), before navigation to
        # the requested URL has even started; that also lacks "login.html" and must not be
        # mistaken for "already redirected away because already authenticated".
        check_script = """
            document.body.classList.contains('loginPageLoaded') ? 'ready'
                : (location.href !== 'about:blank' && location.href.indexOf('login.html') === -1) ? 'already_authenticated'
                : 'pending'
        """
        deadline = time.perf_counter() + timeout_seconds
        while time.perf_counter() < deadline:
            result = client.call("Runtime.evaluate", {"expression": check_script})
            value = result.get("result", {}).get("value")
            if value in ("ready", "already_authenticated"):
                return value
            time.sleep(poll_interval)
        return "pending"

    def _wait_for_js(self, client, expression, timeout_seconds, poll_interval=0.3):
        deadline = time.perf_counter() + timeout_seconds
        while time.perf_counter() < deadline:
            result = client.call("Runtime.evaluate", {"expression": expression})
            if result.get("result", {}).get("value"):
                return True
            time.sleep(poll_interval)
        return False

    def _wait_for_selector(self, client, selector, timeout_seconds):
        found = self._wait_for_js(client, f"document.querySelector({json.dumps(selector)}) !== null", timeout_seconds)
        if not found:
            raise RuntimeError(f"timed out waiting for selector: {selector}")

    def _wait_for_login(self, client, username_selector, timeout_seconds):
        return self._wait_for_js(
            client, f"document.querySelector({json.dumps(username_selector)}) === null", timeout_seconds
        )

    def _get_page(self, name, timeout_seconds=3, poll_interval=0.2):
        target_id = self._tabs.get(name)
        if target_id is None:
            raise KeyError(f"unknown tab: {name}")
        # A tab add_tab() just created can take Chrome a brief moment to fully register (its
        # devtools target may not have a webSocketDebuggerUrl yet on the very first /json/list
        # right after creation) -- retry briefly instead of failing immediately on what's often
        # just a startup timing gap, not a real problem with the tab.
        deadline = time.perf_counter() + timeout_seconds
        page = None
        while True:
            page = self._pages_by_target_id().get(target_id)
            if page is not None and page.get("webSocketDebuggerUrl"):
                return page
            if time.perf_counter() >= deadline:
                break
            time.sleep(poll_interval)
        raise RuntimeError(f"tab not debuggable: {name}")

    def _pages_by_target_id(self):
        return {page["id"]: page for page in http_json(f"http://{self.host}:{self.port}/json/list")}
