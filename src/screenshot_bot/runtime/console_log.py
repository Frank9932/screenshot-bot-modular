from .clock import utc_now_iso


def log_line(tag, message):
    """Prints one timestamped, tagged line for console/log-file readability, e.g.
    "2026-07-08T02:16:39.414+00:00 [wechat] stable_token response: {...}". Every ad hoc print()
    used as informal logging in this codebase should go through this instead of a bare print(),
    so events scattered across a busy server.out.log can be correlated by time and source at a
    glance instead of guessing from unlabeled, timestamp-less text."""
    print(f"{utc_now_iso()} [{tag}] {message}", flush=True)
