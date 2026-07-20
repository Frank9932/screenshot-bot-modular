"""Local end-to-end demo (MVP Level C, see docs/MVP_DEMO.md) of the project's main business
chain: WeChat message -> message router -> equipment catalog -> numbered clarification ->
confirm -> capture -> storage -> reply.

This does NOT reimplement that chain -- it drives the real, already-existing orchestrator
(`WeChatImageReplyWorkflow.handle`, the exact entrypoint the live webhook calls) with a fake
WeChat message, so the real `message_router.route_message`, `equipment_catalog`,
`EquipmentSelectionTracker`, `UserTeamTracker`, and `ScreenshotStore` all run for real. Only two
things are replaced with local stand-ins so this script never touches a network, a real WeChat
account, or the production WebStation dashboard:
  - the WeChat API (DemoSender prints instead of calling it)
  - the Chrome/CDP browser tab (DemoBrowser renders a local placeholder PNG via
    screenshot_bot.runtime.latency_image -- the same helper the real code already uses for its
    own error-placeholder images -- instead of driving real Chrome)

Run:
    $env:PYTHONPATH="$PWD\\src"; python scripts/demo_mvp.py
"""

import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    # Windows consoles often default stdout to cp1252, which can't encode the Chinese
    # reply text this demo prints (e.g. "确认"/"获取截图"). UTF-8 output is otherwise
    # unrelated to the business logic this script demonstrates.
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from screenshot_bot.runtime.latency_image import write_latency_image  # noqa: E402
from screenshot_bot.screenshot_store import ScreenshotStore  # noqa: E402
from screenshot_bot.workflow import WeChatImageReplyWorkflow  # noqa: E402

CONFIG_PATH = ROOT / "config.mvp_demo.json"
DEMO_DIR = ROOT / "runtime" / "mvp-demo"


class DemoSender:
    """Stands in for wechat.image_sender.WeChatImageSender: prints what would be sent instead
    of calling the real WeChat API. Return shape matches what WeChatImageReplyWorkflow expects
    back from a real sender (token_ms/send_ms/upload_ms, send_response, media_id)."""

    def __init__(self):
        self.sent = []

    def send_text(self, touser, content):
        print(f"    [WeChat -> {touser}] {content}")
        self.sent.append(("text", touser, content))
        return {"send_response": {"errcode": 0}, "token_ms": 0.0, "send_ms": 0.0}

    def send_image_file(self, touser, image_path):
        print(f"    [WeChat -> {touser}] <image> {image_path}")
        self.sent.append(("image", touser, image_path))
        return {
            "media_id": "demo-media",
            "upload_response": {"errcode": 0},
            "send_response": {"errcode": 0},
            "token_ms": 0.0,
            "upload_ms": 0.0,
            "send_ms": 0.0,
        }


class DemoBrowser:
    """Stands in for browser.BrowserScreenshotService: same public surface
    WeChatImageReplyWorkflow calls (.targets.enabled/.targets/.visible_targets, .capture(),
    .describe_watermark()). Instead of driving a real Chrome tab over CDP, .capture() renders a
    local placeholder PNG and persists it through a *real* ScreenshotStore -- so storage is
    exercised for real; only the browser/CDP leg is a stand-in. Set .force_failure = True to
    exercise the real capture-error path in WeChatImageReplyWorkflow._run_capture."""

    class _Targets:
        enabled = True
        targets = {"1": {"name": "webstation-test"}, "2": {"name": "webstation-test"}}
        visible_targets = {"1": {"name": "webstation-test"}, "2": {"name": "webstation-test"}}

    def __init__(self, store_dir):
        self.targets = self._Targets()
        self.store = ScreenshotStore(base_dir=store_dir)
        self.force_failure = False

    def parse_team_id(self, text):
        return text.strip() if text.strip() in self.targets.targets else None

    def capture(
        self,
        team_id,
        tab=None,
        user_id=None,
        output_dir=None,
        image_name=None,
        timeout_seconds=15,
        equipment_path=None,
        equipment_pane_height="12%",
        equipment_settle_seconds=3.0,
    ):
        if self.force_failure:
            raise RuntimeError("demo: simulated browser/CDP failure (DemoBrowser.force_failure)")

        details = {
            "browser_team_id": team_id,
            "content": equipment_path or f"channel {team_id}",
            "capture_started_at": "demo",
        }
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = output_dir / image_name
        write_latency_image(image_path, details)
        image_bytes = image_path.read_bytes()

        store_key = f"{user_id or 'unknown'}/channel_{team_id}/original"
        record = self.store.save_screenshot(store_key, image_bytes, duration_ms=1)
        return {
            "published_path": str(image_path),
            "store_path": str(record.file_path),
            "capture_ms": 1.0,
            "equipment_path": equipment_path or "",
        }

    def describe_watermark(self, team_id):
        return {"team_id": team_id, "fields": [], "background_opacity": 100, "customized": False}


def make_workflow():
    sender = DemoSender()
    browser = DemoBrowser(store_dir=DEMO_DIR / "storage")
    incoming_store = ScreenshotStore(base_dir=DEMO_DIR / "incoming")
    workflow = WeChatImageReplyWorkflow(
        str(CONFIG_PATH),
        sender,
        browser,
        DEMO_DIR / "screenshots",
        media_downloader=None,  # this demo never sends an "image" message
        incoming_image_store=incoming_store,
    )
    return workflow, sender, browser


def send(workflow, user, msg_type, content, label):
    print(f"\n--- {label} ---")
    print(f"    [User {user} -> Bot] ({msg_type}) {content!r}")
    message = {"MsgType": msg_type, "Content": content, "FromUserName": user, "MsgId": "demo"}
    result = workflow.handle(message, received_at="demo", started=time.perf_counter())
    print(f"    result: ok={result['ok']} trigger_kind={result.get('trigger_kind', '(none)')}")
    return result


def main():
    workflow, sender, browser = make_workflow()
    user = "demo-user-001"

    print("=" * 78)
    print("Project-level MVP Demo -- Level C (local; real router/catalog/tracker/storage,")
    print("mocked WeChat API + browser/CDP)")
    print("=" * 78)

    send(workflow, user, "text", "1", "Step 1: join channel 1 (also a real plain-channel capture)")
    send(workflow, user, "text", "设备", "Step 2: start select-equipment flow -> category list")
    send(workflow, user, "text", "3", "Step 3: pick category 3 (RYG1 - DHU) -> equipment list")
    send(workflow, user, "text", "2", "Step 4: pick equipment 2 in that category -> confirm prompt")
    send(workflow, user, "text", "确认", "Step 5: confirm the selection")
    result = send(workflow, user, "text", "获取截图", "Step 6: request the screenshot")
    print(f"    screenshot_path = {result.get('screenshot_path')}")
    print(f"    equipment       = {result.get('equipment_category')} / {result.get('equipment_name')}")

    print("\n" + "=" * 78)
    print("Edge cases (same real workflow instance, no separate test harness)")
    print("=" * 78)

    send(workflow, "demo-user-002", "text", "设备", "Edge 1a: second user starts flow")
    send(workflow, "demo-user-002", "text", "99", "Edge 1b: out-of-range category digit -> re-prompt")

    send(workflow, "demo-user-003", "text", "获取截图", "Edge 2: capture requested before any selection confirmed")

    send(workflow, "demo-user-004", "text", "9", "Edge 3: bare unconfigured digit, no flow in progress -> guidance")

    original_csv_path = workflow.equipment_csv_path
    workflow.equipment_csv_path = DEMO_DIR / "does-not-exist.csv"
    send(workflow, "demo-user-005", "text", "设备", "Edge 4: equipment CSV missing -> empty-catalog fallback")
    workflow.equipment_csv_path = original_csv_path

    send(workflow, "demo-user-006", "text", "2", "Edge 5a: join channel 2 (setup)")
    browser.force_failure = True
    failure_result = send(workflow, "demo-user-006", "text", "2", "Edge 5b: recapture with simulated browser failure")
    print(f"    capture_error = {failure_result.get('capture_error')}")
    browser.force_failure = False

    print(f"\nDone. Generated files under {DEMO_DIR} (gitignored, local-only, safe to delete).")


if __name__ == "__main__":
    main()
