import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from screenshot_bot.browser import CdpMultiTabService, launch_chrome, wait_for_port

LOGIN_URL = "https://10.121.0.14/login.html"
APP_URL = "https://10.121.0.14/"
MAX_TABS = 5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9334)
    parser.add_argument("--profile-dir", default=str(ROOT / "runtime" / "cdp-webstation-profile"))
    parser.add_argument("--output-dir", default=str(ROOT / "runtime" / "cdp-webstation-demo"))
    parser.add_argument("--chrome-path", default="")
    parser.add_argument("--tabs", type=int, default=MAX_TABS, help=f"number of tabs to open (max {MAX_TABS})")
    parser.add_argument("--username", default=os.environ.get("CDP_LOGIN_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("CDP_LOGIN_PASSWORD", ""))
    parser.add_argument("--refresh-interval-seconds", type=int, default=300, help="0 disables auto-refresh")
    args = parser.parse_args()

    if not args.username or not args.password:
        parser.error("--username/--password required (or set CDP_LOGIN_USERNAME / CDP_LOGIN_PASSWORD)")

    tab_count = min(args.tabs, MAX_TABS)
    names = [f"tab_{i}" for i in range(tab_count)]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # This site issues a session-only cookie (cleared on browser close, regardless of profile
    # persistence) AND enforces a single active login per account: a second tab that submits
    # the login form while another tab already holds the session gets rejected with "A user is
    # already logged on to another tab". So "keep the logins" here means: log in exactly once,
    # on one tab, then point every other tab at the app itself (not login.html) so it just reuses
    # the already-authenticated session cookie shared by this one Chrome process.
    process = launch_chrome(
        args.port,
        args.profile_dir,
        chrome_path=args.chrome_path or None,
        ignore_certificate_errors=True,
    )
    service = CdpMultiTabService(args.port, max_tabs=MAX_TABS)
    try:
        wait_for_port(args.port)

        service.add_tab(names[0], LOGIN_URL)
        login_result = service.login(names[0], args.username, args.password)
        print(f"{names[0]}: logged_in={login_result['logged_in']}")

        # The app's own frontend (chunk 9855.js, useWatchDog()) pings a JSON endpoint every 60s
        # to stop its session from idling out. Our tabs mostly sit on a splash screen and never
        # trigger that polling themselves, so replicate the same ping from one tab in the
        # background — that's enough to keep the shared session alive for every tab, since they
        # all read the same server-side session cookie.
        service.start_keep_alive(names[0], interval_seconds=60)

        for name in names[1:]:
            service.add_tab(name, APP_URL)
        if len(names) > 1:
            time.sleep(2)  # let the shared-session tabs finish their own app bootstrap

        # keep_alive only needs to run once (shared session cookie), but auto-refresh is
        # per-tab: each tab has its own DOM/subscriptions, which Chrome throttles while the
        # tab is backgrounded, so every tab needs its own reload loop to stay visually fresh.
        if args.refresh_interval_seconds > 0:
            for name in names:
                service.start_auto_refresh(name, interval_seconds=args.refresh_interval_seconds)

        for name in names:
            result = service.screenshot(name, output_dir / f"{name}.png")
            print(f"{name}: {result['elapsed_ms']:.1f} ms -> {result['path']}")
    finally:
        service.stop_keep_alive(names[0])
        for name in names:
            service.stop_auto_refresh(name)
        process.terminate()


if __name__ == "__main__":
    main()
