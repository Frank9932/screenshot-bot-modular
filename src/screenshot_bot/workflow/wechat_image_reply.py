import time
import uuid
from pathlib import Path

from screenshot_bot.browser import BrowserScreenshotService
from screenshot_bot.config import get_section, load_json_config, resolve_path
from screenshot_bot.desktop import DesktopScreenshotService, VirtualDesktopSwitcher, parse_desktop_number
from screenshot_bot.runtime.clock import utc_now_iso
from screenshot_bot.runtime.latency_image import write_latency_image
from screenshot_bot.screenshot_store import ScreenshotStore
from screenshot_bot.wechat.image_sender import WeChatImageSender
from screenshot_bot.wechat.media_downloader import WeChatMediaDownloader
from screenshot_bot.wechat.webhook_server import WeChatWebhookServer

from .help_text import CHANNEL_UNASSIGNED_PROMPT, GENERAL_HELP_TEXT, GENERAL_HELP_WORDS
from .user_team_tracker import UNASSIGNED, UserTeamTracker
from .watermark_commands import HELP_TEXT as WATERMARK_HELP_TEXT
from .watermark_commands import parse_watermark_command


class WeChatImageReplyWorkflow:
    def __init__(
        self,
        config_path,
        image_sender,
        browser,
        desktop,
        virtual_desktop,
        screenshot_dir,
        media_downloader,
        incoming_image_store,
    ):
        self.config_path = config_path
        self.config = load_json_config(config_path)
        self.webhook_config = get_section(self.config, "wechat_official_webhook")
        self.screenshot_dir = Path(screenshot_dir)
        self.image_sender = image_sender
        self.browser = browser
        self.desktop = desktop
        self.virtual_desktop = virtual_desktop
        self.media_downloader = media_downloader
        self.incoming_image_store = incoming_image_store
        self.user_team_tracker = UserTeamTracker(
            resolve_path(config_path, self.webhook_config.get("user_team_tracker_path"), "runtime/user-team-tracker.json")
        )
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
        # Field order matters for readability, not just correctness: received_at/msg_type/touser
        # first is what you actually scan for skimming a busy JSONL log, "ok" last reads as the
        # final verdict on the line.
        result = {
            "received_at": received_at,
            "msg_type": msg_type,
            "touser": touser,
            "content": content,
            "msg_id": message.get("MsgId", ""),
            "create_time": message.get("CreateTime", ""),
            "event": message.get("Event", ""),
            "ok": False,
        }

        if msg_type == "text":
            if content.strip().lower() in GENERAL_HELP_WORDS:
                if not touser:
                    raise RuntimeError("touser missing: FromUserName is empty")
                send_info = self.image_sender.send_text(touser, GENERAL_HELP_TEXT)
                result.update(
                    {
                        "ok": True,
                        "reply_text": GENERAL_HELP_TEXT,
                        "send_response": send_info.get("send_response", {}),
                        "total_latency": round((time.perf_counter() - started) * 1000.0, 1),
                    }
                )
                return result

            watermark_command = parse_watermark_command(content)
            if watermark_command is not None:
                if not touser:
                    raise RuntimeError("touser missing: FromUserName is empty")
                reply_text = self._handle_watermark_command(watermark_command)
                send_info = self.image_sender.send_text(touser, reply_text)
                result.update(
                    {
                        "ok": True,
                        "watermark_command": watermark_command,
                        "reply_text": reply_text,
                        "send_response": send_info.get("send_response", {}),
                        "total_latency": round((time.perf_counter() - started) * 1000.0, 1),
                    }
                )
                return result

        if msg_type == "image":
            self._store_incoming_image(message, touser, result)
            # A photo carries no channel of its own -- if this sender has never picked a
            # channel (no prior digit message), there is nothing to capture for them yet.
            # Nudge them instead of silently archiving the photo with no reply at all.
            if self.user_team_tracker.get_team(touser) == UNASSIGNED:
                if not touser:
                    raise RuntimeError("touser missing: FromUserName is empty")
                send_info = self.image_sender.send_text(touser, CHANNEL_UNASSIGNED_PROMPT)
                result.update(
                    {
                        "ok": True,
                        "reply_text": CHANNEL_UNASSIGNED_PROMPT,
                        "send_response": send_info.get("send_response", {}),
                        "total_latency": round((time.perf_counter() - started) * 1000.0, 1),
                    }
                )
                return result

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

    def _handle_watermark_command(self, command):
        action = command.get("action")
        if action == "help" or "team_id" not in command:
            return WATERMARK_HELP_TEXT

        team_id = command["team_id"]
        if team_id not in self.browser.targets.targets:
            return f"未知频道编号: {team_id}\n\n{WATERMARK_HELP_TEXT}"

        if action == "status":
            status = self.browser.describe_watermark(team_id)
            lines = [f"频道{team_id}当前水印设置:"]
            for index, field in enumerate(status["fields"], start=1):
                lines.append(f"  {index}. {field['label']}{': ' if field['label'] else ''}{field['value']}")
            lines.append(f"背景不透明度: {status['background_opacity']}")
            lines.append("(已自定义)" if status["customized"] else "(使用默认设置)")
            return "\n".join(lines)

        if action == "reset":
            self.browser.reset_watermark(team_id)
            return f"频道{team_id}的水印设置已恢复默认。"

        if action == "opacity":
            value = command.get("value", "")
            if not value.isdigit():
                return f"透明度需为0-255之间的整数。\n\n{WATERMARK_HELP_TEXT}"
            try:
                self.browser.set_watermark_opacity(team_id, int(value))
            except ValueError as exc:
                return f"{exc}\n\n{WATERMARK_HELP_TEXT}"
            return f"频道{team_id}水印背景不透明度已设置为{value}。"

        if action == "set_field":
            index = command.get("index", "")
            if not index.isdigit():
                return f"序号需为数字。\n\n{WATERMARK_HELP_TEXT}"
            value = command.get("value", "")
            try:
                self.browser.set_watermark_field(team_id, int(index) - 1, value)
            except IndexError as exc:
                return str(exc)
            if not value.strip():
                return f"频道{team_id}水印第{index}行已清空。"
            return f"频道{team_id}水印第{index}行已更新为: {value}"

        return WATERMARK_HELP_TEXT

    def _store_incoming_image(self, message, touser, result):
        media_id = message.get("MediaId", "")
        if not media_id:
            return
        started = time.perf_counter()
        try:
            image_bytes = self.media_downloader.download(media_id)
            duration_ms = round((time.perf_counter() - started) * 1000.0)
            # A photo carries no channel of its own -- file it under whichever channel this
            # sender most recently joined with a text digit, so incoming photos land in the
            # same one-folder-per-channel layout as outgoing screenshots (see UserTeamTracker).
            channel_id = self.user_team_tracker.get_team(touser)
            store_key = f"channel_{channel_id}"
            record = self.incoming_image_store.save_screenshot(store_key, image_bytes, duration_ms)
            result["incoming_image_path"] = str(record.file_path)
            result["incoming_image_size"] = record.size_bytes
        except Exception as exc:
            # Best-effort: a failed download/save must not block the reply flow.
            result["incoming_image_error"] = str(exc)

    def _build_response_image(self, message, details):
        msg_type = message.get("MsgType", "")
        content = message.get("Content", "")
        touser = message.get("FromUserName", "")
        message_text = content if msg_type == "text" else f"<{msg_type}>"
        browser_team_id = self.browser.parse_team_id(message_text) if msg_type == "text" else None
        if msg_type == "text" and browser_team_id is not None:
            # Sending a channel digit both captures immediately (unchanged) and joins that
            # channel -- this is the only place channel membership is ever set.
            self.user_team_tracker.set_team(touser, browser_team_id)
        if msg_type == "image":
            # A photo has no channel of its own -- capture whichever channel this sender last
            # joined. handle() already returned early (before reaching here) if they've never
            # joined one, so this is always a real channel by this point.
            browser_team_id = self.user_team_tracker.get_team(touser)
        desktop_number = None
        if msg_type == "text" and browser_team_id is None and self.virtual_desktop.enabled:
            desktop_number = parse_desktop_number(message_text, self.virtual_desktop_config)

        details["browser_team_id"] = browser_team_id
        details["requested_desktop"] = desktop_number

        if msg_type in self.ignore_message_types and not should_capture_message(msg_type, desktop_number, browser_team_id, self.capture_message_types):
            return {"ignored": True, "reason": "message_type_disabled"}

        if browser_team_id is not None:
            name_prefix = f"channel{browser_team_id}"
        elif desktop_number is not None:
            name_prefix = f"desktop{desktop_number}"
        else:
            name_prefix = "wechat-official"
        image_name = f"{name_prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.png"
        image_path = self.screenshot_dir / image_name
        details["capture_started_at"] = utc_now_iso()

        if should_capture_message(msg_type, desktop_number, browser_team_id, self.capture_message_types):
            try:
                if browser_team_id is not None:
                    capture_info = self.browser.capture(
                        browser_team_id,
                        user_id=touser,
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
    incoming_image_dir = resolve_path(config_path, webhook.get("incoming_image_dir"), "storage/incoming")
    image_sender = WeChatImageSender(appid, appsecret)
    media_downloader = WeChatMediaDownloader(client=image_sender.client)
    incoming_image_store = ScreenshotStore(base_dir=incoming_image_dir)
    browser = BrowserScreenshotService(config_path)
    desktop = DesktopScreenshotService(
        config_path,
        webhook.get("screenshot_tool", "ScreenshotTool.exe"),
        webhook.get("screenshot_dir", "screenshots"),
    )
    virtual_desktop = VirtualDesktopSwitcher(get_section(config, "virtual_desktop"), base_dir=Path(config_path).resolve().parent)
    workflow = WeChatImageReplyWorkflow(
        config_path,
        image_sender,
        browser,
        desktop,
        virtual_desktop,
        screenshot_dir,
        media_downloader,
        incoming_image_store,
    )
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
