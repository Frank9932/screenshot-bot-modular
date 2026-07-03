import time
import uuid
from pathlib import Path

from screenshot_bot.browser import BrowserScreenshotService
from screenshot_bot.config import get_section, load_json_config, resolve_path
from screenshot_bot.desktop import DesktopScreenshotService, VirtualDesktopSwitcher, parse_desktop_number
from screenshot_bot.runtime.clock import utc_now_iso
from screenshot_bot.runtime.latency_image import write_latency_image
from screenshot_bot.wechat.image_sender import WeChatImageSender
from screenshot_bot.wechat.webhook_server import WeChatWebhookServer


class WeChatImageReplyWorkflow:
    def __init__(self, config_path, image_sender, browser, desktop, virtual_desktop, screenshot_dir):
        self.config_path = config_path
        self.config = load_json_config(config_path)
        self.webhook_config = get_section(self.config, "wechat_official_webhook")
        self.screenshot_dir = Path(screenshot_dir)
        self.image_sender = image_sender
        self.browser = browser
        self.desktop = desktop
        self.virtual_desktop = virtual_desktop
        self.virtual_desktop_config = get_section(self.config, "virtual_desktop")
        self.capture_message_types = _parse_type_set(self.webhook_config.get("capture_message_types", "none"))
        self.ignore_message_types = _parse_type_set(self.webhook_config.get("ignore_message_types", "image"), keep_disabled_words=True)
        self.capture_timeout_seconds = int(self.webhook_config.get("capture_timeout_seconds", 15))


    def ready_payload(self):
        return {
            "browser_targets_enabled": bool(self.browser.targets.enabled),
            "browser_target_ids": sorted(self.browser.targets.targets.keys()),
            "virtual_desktop_enabled": self.virtual_desktop.enabled,
            "capture_message_types": sorted(self.capture_message_types),
            "ignore_message_types": sorted(self.ignore_message_types),
        }

    def handle(self, message, received_at, started):
        msg_type = message.get("MsgType", "")
        content = message.get("Content", "")
        touser = message.get("FromUserName", "")
        result = {
            "ok": False,
            "received_at": received_at,
            "msg_id": message.get("MsgId", ""),
            "create_time": message.get("CreateTime", ""),
            "msg_type": msg_type,
            "event": message.get("Event", ""),
            "content": content,
            "touser": touser,
        }

        image_result = self._build_response_image(message, result)
        if image_result.get("ignored"):
            result.update({"ok": True, "ignored": True, "reason": image_result.get("reason", "ignored")})
            return result
        if not touser:
            raise RuntimeError("touser missing: FromUserName is empty")

        image_path = image_result["image_path"]
        result.update(
            {
                "screenshot_done": utc_now_iso(),
                "screenshot_path": image_path,
                "capture_ms": round(float(image_result.get("capture_ms", 0.0)), 1),
                "trigger_kind": image_result["trigger_kind"],
                "response_image_kind": image_result["response_image_kind"],
            }
        )
        for key in ["browser_team_id", "requested_desktop", "desktop_switch", "capture_error", "capture_info"]:
            if image_result.get(key) not in [None, {}, ""]:
                result[key] = image_result[key]

        send_info = self.image_sender.send_image_file(touser, image_path)
        result.update({"media_upload_done": utc_now_iso(), "media_id": send_info.get("media_id", ""), "upload_response": send_info.get("upload_response", {})})
        send_result = send_info.get("send_response", {})
        result.update(
            {
                "message_send_done": utc_now_iso(),
                "send_response": send_result,
                "total_latency": round((time.perf_counter() - started) * 1000.0, 1),
                "ok": True,
            }
        )
        return result

    def _build_response_image(self, message, details):
        msg_type = message.get("MsgType", "")
        content = message.get("Content", "")
        message_text = content if msg_type == "text" else f"<{msg_type}>"
        browser_team_id = self.browser.parse_team_id(message_text) if msg_type == "text" else None
        desktop_number = None
        if msg_type == "text" and browser_team_id is None and self.virtual_desktop.enabled:
            desktop_number = parse_desktop_number(message_text, self.virtual_desktop_config)

        details["browser_team_id"] = browser_team_id
        details["requested_desktop"] = desktop_number

        if msg_type in self.ignore_message_types and not should_capture_message(msg_type, desktop_number, browser_team_id, self.capture_message_types):
            return {"ignored": True, "reason": "message_type_disabled"}

        image_name = f"wechat-official-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.png"
        image_path = self.screenshot_dir / image_name
        details["capture_started_at"] = utc_now_iso()

        if should_capture_message(msg_type, desktop_number, browser_team_id, self.capture_message_types):
            try:
                if browser_team_id is not None:
                    capture_info = self.browser.capture(
                        browser_team_id,
                        output_dir=self.screenshot_dir,
                        image_name=image_name,
                        timeout_seconds=self.capture_timeout_seconds,
                    )
                    return {
                        "trigger_kind": "browser_target",
                        "response_image_kind": "browser_screenshot",
                        "browser_team_id": browser_team_id,
                        "image_path": capture_info["published_path"],
                        "capture_ms": float(capture_info.get("capture_ms", 0.0)),
                        "capture_info": capture_info,
                    }
                if desktop_number is not None:
                    with self.virtual_desktop.exclusive_session():
                        desktop_info = self.virtual_desktop.switch_to(desktop_number)
                        capture_info = self.desktop.capture(
                            output_dir=self.screenshot_dir,
                            image_name=image_name,
                            timeout_seconds=self.capture_timeout_seconds,
                        )
                    return {
                        "trigger_kind": "virtual_desktop",
                        "response_image_kind": "desktop_screenshot",
                        "requested_desktop": desktop_number,
                        "desktop_switch": desktop_info,
                        "image_path": capture_info["published_path"],
                        "capture_ms": float(capture_info.get("capture_ms", 0.0)),
                        "capture_info": capture_info,
                    }
                capture_info = self.desktop.capture(
                    output_dir=self.screenshot_dir,
                    image_name=image_name,
                    timeout_seconds=self.capture_timeout_seconds,
                )
                return {
                    "trigger_kind": "message_type",
                    "response_image_kind": "desktop_screenshot",
                    "image_path": capture_info["published_path"],
                    "capture_ms": float(capture_info.get("capture_ms", 0.0)),
                    "capture_info": capture_info,
                }
            except Exception as exc:
                details["capture_error"] = str(exc)
                write_latency_image(image_path, details)
                return {
                    "trigger_kind": "capture_error",
                    "response_image_kind": "capture_error",
                    "image_path": str(image_path),
                    "capture_ms": 0.0,
                    "capture_error": str(exc),
                    "capture_info": {},
                }

        write_latency_image(image_path, details)
        return {
            "trigger_kind": "latency_test",
            "response_image_kind": "latency_test",
            "image_path": str(image_path),
            "capture_ms": 0.0,
            "capture_info": {},
        }


def should_capture_message(message_type, desktop_number, browser_team_id, capture_message_types):
    if browser_team_id is not None:
        return True
    if desktop_number is not None:
        return True
    return message_type in capture_message_types


def _parse_type_set(value, keep_disabled_words=False):
    disabled = {"none", "off", "disabled"}
    result = set()
    for item in str(value or "").split(","):
        normalized = item.strip().lower()
        if not normalized:
            continue
        if not keep_disabled_words and normalized in disabled:
            continue
        result.add(normalized)
    return result



def build_wechat_official_server(config_path, host, port, path):
    import os

    config_path = str(Path(config_path).resolve())
    config = load_json_config(config_path)
    webhook = get_section(config, "wechat_official_webhook")
    token_env = webhook.get("token_env", "WECHAT_OFFICIAL_WEBHOOK_TOKEN")
    appid_env = webhook.get("appid_env", "WECHAT_APPID")
    appsecret_env = webhook.get("appsecret_env", "WECHAT_APPSECRET")
    token = os.environ.get(token_env, "")
    appid = os.environ.get(appid_env, "")
    appsecret = os.environ.get(appsecret_env, "")
    if not token:
        raise RuntimeError(f"{token_env} is required")
    if not appid or not appsecret:
        raise RuntimeError(f"{appid_env}/{appsecret_env} are required")

    screenshot_dir = resolve_path(config_path, webhook.get("screenshot_dir"), "screenshots")
    log_path = resolve_path(config_path, webhook.get("log_path"), "logs/wechat-official-webhook-events.jsonl")
    image_sender = WeChatImageSender(appid, appsecret)
    browser = BrowserScreenshotService(config_path)
    desktop = DesktopScreenshotService(
        config_path,
        webhook.get("screenshot_tool", "ScreenshotTool.exe"),
        webhook.get("screenshot_dir", "screenshots"),
    )
    virtual_desktop = VirtualDesktopSwitcher(get_section(config, "virtual_desktop"), base_dir=Path(config_path).resolve().parent)
    workflow = WeChatImageReplyWorkflow(config_path, image_sender, browser, desktop, virtual_desktop, screenshot_dir)
    return WeChatWebhookServer(
        (host, port),
        path,
        token,
        workflow,
        ready_payload={
            "has_token": bool(token),
            "has_appid": bool(appid),
            "has_appsecret": bool(appsecret),
            **workflow.ready_payload(),
        },
        log_path=log_path,
        dedupe_ttl_seconds=webhook.get("dedupe_ttl_seconds", 600),
    )
