import time
import uuid
from pathlib import Path

from screenshot_bot.browser import BrowserScreenshotService
from screenshot_bot.config import get_section, load_json_config, resolve_path
from screenshot_bot.runtime.clock import utc_now_iso
from screenshot_bot.runtime.latency_image import write_latency_image
from screenshot_bot.screenshot_store import ScreenshotStore
from screenshot_bot.wechat.image_sender import WeChatImageSender
from screenshot_bot.wechat.media_downloader import WeChatMediaDownloader
from screenshot_bot.wechat.webhook_server import WeChatWebhookServer

from .equipment_catalog import load_categories, load_equipment
from .equipment_prompts import (
    EQUIPMENT_LIST_EMPTY_TEXT,
    build_capture_no_channel_text,
    build_capture_not_ready_text,
    build_cancelled_text,
    build_category_list_text,
    build_confirm_prompt_text,
    build_confirmed_text,
    build_equipment_list_text,
    build_invalid_selection_text,
)
from .equipment_selection_tracker import EquipmentSelectionTracker
from .help_text import (
    FIRST_JOIN_STORAGE_NOTICE,
    PRIVATE_CHANNEL_JOINED_TEXT,
    PRIVATE_CHANNEL_SAVED_TEXT,
    PRIVATE_CHANNEL_UNLOCKED_TEXT,
    build_channel_guidance,
    build_general_help_text,
)
from .menu import event_key_to_text
from .message_router import route_message
from .user_team_tracker import PRIVATE_CHANNEL_ID, UNASSIGNED, UserTeamTracker
from .watermark_commands import HELP_TEXT as WATERMARK_HELP_TEXT


class WeChatImageReplyWorkflow:
    def __init__(
        self,
        config_path,
        image_sender,
        browser,
        screenshot_dir,
        media_downloader,
        incoming_image_store,
        private_image_store=None,
    ):
        self.config_path = config_path
        self.config = load_json_config(config_path)
        self.webhook_config = get_section(self.config, "wechat_official_webhook")
        self.screenshot_dir = Path(screenshot_dir)
        self.image_sender = image_sender
        self.browser = browser
        self.media_downloader = media_downloader
        self.incoming_image_store = incoming_image_store
        self.private_image_store = private_image_store or incoming_image_store
        self.user_team_tracker = UserTeamTracker(
            resolve_path(config_path, self.webhook_config.get("user_team_tracker_path"), "runtime/user-team-tracker.json")
        )
        self.ignore_message_types = _parse_type_set(self.webhook_config.get("ignore_message_types", "image"), keep_disabled_words=True)
        self.capture_timeout_seconds = int(self.webhook_config.get("capture_timeout_seconds", 15))

        equipment_config = get_section(self.config, "equipment_catalog")
        self.equipment_catalog_enabled = bool(equipment_config.get("enabled", False))
        self.equipment_csv_path = resolve_path(
            config_path, equipment_config.get("csv_path"), "runtime/cdp-explore-out/hvac_equipment.csv"
        )
        self.equipment_pane_height = equipment_config.get("pane_height", "12%")
        self.equipment_settle_seconds = float(equipment_config.get("settle_seconds", 3.0))
        self.equipment_selection_tracker = EquipmentSelectionTracker(
            resolve_path(config_path, equipment_config.get("selection_tracker_path"), "runtime/equipment-selection-tracker.json")
        )

    def ready_payload(self):
        return {
            "browser_targets_enabled": bool(self.browser.targets.enabled),
            "browser_target_ids": sorted(self.browser.targets.targets.keys()),
            "ignore_message_types": sorted(self.ignore_message_types),
            "equipment_catalog_enabled": self.equipment_catalog_enabled,
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

        # A tap on the custom menu (see menu.py) arrives as an "event"/"CLICK" message with the
        # button's EventKey as its only payload -- translate it back into the same plain text
        # typing the equivalent command would have sent, so everything below never needs to know
        # menu taps exist at all. An unrecognized/stale key (e.g. from a previously pushed menu)
        # falls through unchanged and ends up as ordinary guidance, same as any other menu/event
        # push we don't otherwise handle (e.g. "subscribe").
        routed_msg_type, routed_content = msg_type, content
        if msg_type == "event" and message.get("Event", "") == "CLICK":
            menu_text = event_key_to_text(message.get("EventKey", ""))
            if menu_text is not None:
                routed_msg_type, routed_content = "text", menu_text
                result["menu_event_key"] = message.get("EventKey", "")

        if routed_msg_type == "image":
            self._store_incoming_image(message, touser, result)

        # All the "what should happen" decision-making lives in message_router.route_message --
        # a pure function with no I/O, so it can be tested/debugged in complete isolation (see
        # that module's docstring). Everything below this point is just executing its decision:
        # sending replies, capturing screenshots, persisting channel/unlock state.
        channel_id = self.user_team_tracker.get_team(touser)
        private_unlocked = self.user_team_tracker.has_unlocked_private(touser)
        all_channel_ids = set(self.browser.targets.targets.keys()) if self.browser.targets.enabled else set()

        # route_message stays a pure function (see message_router.py's docstring), so any CSV
        # data it needs to resolve a category/equipment digit has to be loaded ahead of time,
        # here, same as all_channel_ids above. equipment_items is only ever consulted when the
        # stage is actually "awaiting_equipment", so it's the only one worth conditioning on
        # that -- categories are cheap and used by both "equipment_start" and validating an
        # "awaiting_category" digit.
        equipment_stage, equipment_categories, equipment_items = {}, [], []
        if self.equipment_catalog_enabled:
            equipment_stage = self.equipment_selection_tracker.get(touser)
            equipment_categories = self._load_equipment_categories()
            if equipment_stage.get("stage") == "awaiting_equipment":
                equipment_items = self._load_equipment_items(equipment_stage.get("category", ""))

        action = route_message(
            routed_msg_type, routed_content, channel_id, private_unlocked, all_channel_ids, self.ignore_message_types,
            equipment_catalog_enabled=self.equipment_catalog_enabled,
            equipment_stage=equipment_stage, equipment_categories=equipment_categories, equipment_items=equipment_items,
        )

        if action["kind"] == "ignored":
            result.update({"ok": True, "ignored": True, "reason": action["reason"]})
            return result

        if not touser:
            raise RuntimeError("touser missing: FromUserName is empty")

        if action["kind"] == "general_help":
            reply_text = build_general_help_text(self.browser.targets.visible_targets.keys())
            return self._reply_text(result, started, touser, reply_text)

        if action["kind"] == "unlock_private":
            self.user_team_tracker.unlock_private(touser)
            return self._reply_text(result, started, touser, PRIVATE_CHANNEL_UNLOCKED_TEXT)

        if action["kind"] == "join_private":
            self.user_team_tracker.set_team(touser, PRIVATE_CHANNEL_ID)
            return self._reply_text(result, started, touser, PRIVATE_CHANNEL_JOINED_TEXT)

        if action["kind"] == "watermark_command":
            reply_text = self._handle_watermark_command(action["command"])
            result["watermark_command"] = action["command"]
            return self._reply_text(result, started, touser, reply_text)

        if action["kind"] == "private_photo":
            return self._reply_text(result, started, touser, PRIVATE_CHANNEL_SAVED_TEXT)

        if action["kind"] == "unassigned_photo_prompt":
            reply_text = build_channel_guidance(UNASSIGNED, self.browser.targets.visible_targets.keys())
            return self._reply_text(result, started, touser, reply_text)

        if action["kind"] == "guidance":
            reply_text = build_channel_guidance(channel_id, self.browser.targets.visible_targets.keys())
            result["trigger_kind"] = "guidance"
            return self._reply_text(result, started, touser, reply_text)

        if action["kind"] == "equipment_start":
            self.equipment_selection_tracker.start(touser)
            reply_text = build_category_list_text(equipment_categories) if equipment_categories else EQUIPMENT_LIST_EMPTY_TEXT
            return self._reply_text(result, started, touser, reply_text)

        if action["kind"] == "equipment_category_selected":
            category = action["category"]
            self.equipment_selection_tracker.set_category(touser, category)
            items = self._load_equipment_items(category)
            reply_text = build_equipment_list_text(category, items) if items else EQUIPMENT_LIST_EMPTY_TEXT
            return self._reply_text(result, started, touser, reply_text)

        if action["kind"] == "equipment_selected":
            category = action["category"]
            self.equipment_selection_tracker.set_pending_equipment(touser, category, action["equipment"], action["path"])
            reply_text = build_confirm_prompt_text(category, action["equipment"])
            return self._reply_text(result, started, touser, reply_text)

        if action["kind"] == "equipment_invalid_selection":
            if action["stage"] == "awaiting_category":
                list_text = build_category_list_text(equipment_categories)
            else:
                list_text = build_equipment_list_text(equipment_stage.get("category", ""), equipment_items)
            return self._reply_text(result, started, touser, build_invalid_selection_text(list_text))

        if action["kind"] == "equipment_confirmed":
            self.equipment_selection_tracker.confirm(touser)
            reply_text = build_confirmed_text(equipment_stage.get("category", ""), equipment_stage.get("equipment", ""))
            return self._reply_text(result, started, touser, reply_text)

        if action["kind"] == "equipment_cancelled":
            self.equipment_selection_tracker.cancel(touser)
            return self._reply_text(result, started, touser, build_cancelled_text())

        if action["kind"] == "equipment_capture_not_ready":
            return self._reply_text(result, started, touser, build_capture_not_ready_text())

        if action["kind"] == "equipment_capture_no_channel":
            reply_text = build_capture_no_channel_text(self.browser.targets.visible_targets.keys())
            return self._reply_text(result, started, touser, reply_text)

        if action["kind"] == "equipment_capture":
            return self._capture_equipment_and_reply(result, started, touser, action)

        # Remaining kinds -- "join_channel" (text digit) and "recapture" (photo from a sender
        # with an assigned channel) -- both trigger an actual browser capture.
        target_channel_id = action["channel_id"]
        if action["kind"] == "join_channel":
            self.user_team_tracker.set_team(touser, target_channel_id)
        return self._capture_and_reply(result, started, touser, target_channel_id, action.get("is_first_join", False))

    def _reply_text(self, result, started, touser, reply_text):
        send_info = self.image_sender.send_text(touser, reply_text)
        result.update(
            {
                "ok": True,
                "reply_text": reply_text,
                "send_response": send_info.get("send_response", {}),
                "token_ms": send_info.get("token_ms", 0.0),
                "send_ms": send_info.get("send_ms", 0.0),
                "total_latency": round((time.perf_counter() - started) * 1000.0, 1),
            }
        )
        return result

    def _capture_and_reply(self, result, started, touser, channel_id, first_join_notice):
        image_name = f"channel{channel_id}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.png"
        result = self._run_capture(result, started, touser, channel_id, image_name)
        if result["ok"] and result.get("trigger_kind") != "capture_error" and first_join_notice:
            notice_send_info = self.image_sender.send_text(touser, FIRST_JOIN_STORAGE_NOTICE)
            result["first_join_notice_send_response"] = notice_send_info.get("send_response", {})
        return result

    def _capture_equipment_and_reply(self, result, started, touser, action):
        channel_id = action["channel_id"]
        equipment_name = action["equipment"]
        result["equipment_category"] = action["category"]
        result["equipment_name"] = equipment_name
        image_name = f"channel{channel_id}-equipment-{_safe_filename(equipment_name)}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.png"
        return self._run_capture(
            result, started, touser, channel_id, image_name,
            equipment_path=action["path"],
            equipment_pane_height=self.equipment_pane_height,
            equipment_settle_seconds=self.equipment_settle_seconds,
        )

    def _run_capture(self, result, started, touser, channel_id, image_name, **extra_capture_kwargs):
        image_path = self.screenshot_dir / image_name
        result["browser_team_id"] = channel_id
        result["capture_started_at"] = utc_now_iso()

        try:
            capture_info = self.browser.capture(
                channel_id,
                user_id=touser,
                output_dir=self.screenshot_dir,
                image_name=image_name,
                timeout_seconds=self.capture_timeout_seconds,
                **extra_capture_kwargs,
            )
        except Exception as exc:
            result["capture_error"] = str(exc)
            write_latency_image(image_path, result)
            result.update(
                {
                    "trigger_kind": "capture_error",
                    "response_image_kind": "capture_error",
                    "screenshot_path": str(image_path),
                    "capture_ms": 0.0,
                }
            )
            # The placeholder image must actually reach the user, not just land on disk --
            # without this send, a browser/CDP failure produced `ok=True` but silently left the
            # sender with no reply at all (bug: send_image_file was never called on this path).
            return self._send_capture_reply(result, started, touser, str(image_path))

        result.update(
            {
                "screenshot_done": utc_now_iso(),
                "screenshot_path": capture_info["published_path"],
                "capture_ms": round(float(capture_info.get("capture_ms", 0.0)), 1),
                "trigger_kind": "browser_target",
                "response_image_kind": "browser_screenshot",
                "capture_info": capture_info,
            }
        )
        return self._send_capture_reply(result, started, touser, capture_info["published_path"])

    def _send_capture_reply(self, result, started, touser, image_path):
        """Send the just-captured (or capture-error placeholder) image and fold the outcome
        into `result` -- without ever letting a sender exception escape. By this point capture
        and/or local storage may have already genuinely succeeded (`result` already carries
        their stage fields), so a WeChat upload/send failure must be reported as its own
        truthful ok=False stage rather than either masquerading as success or losing that
        already-gathered context to an uncaught exception bubbling out of .handle()."""
        try:
            send_info = self.image_sender.send_image_file(touser, image_path)
        except Exception as exc:
            result.update(
                {
                    "ok": False,
                    "send_error": str(exc),
                    "total_latency": round((time.perf_counter() - started) * 1000.0, 1),
                }
            )
            return result

        result.update(
            {
                "media_upload_done": utc_now_iso(),
                "media_id": send_info.get("media_id", ""),
                "upload_response": send_info.get("upload_response", {}),
            }
        )
        result.update(
            {
                "message_send_done": utc_now_iso(),
                "send_response": send_info.get("send_response", {}),
                "token_ms": send_info.get("token_ms", 0.0),
                "upload_ms": send_info.get("upload_ms", 0.0),
                "send_ms": send_info.get("send_ms", 0.0),
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

    def _load_equipment_categories(self):
        try:
            return load_categories(self.equipment_csv_path)
        except OSError:
            # Missing/unreadable CSV is treated the same as an empty catalog -- callers already
            # fall back to EQUIPMENT_LIST_EMPTY_TEXT for an empty list, no separate error path.
            return []

    def _load_equipment_items(self, category):
        try:
            return load_equipment(self.equipment_csv_path, category)
        except OSError:
            return []

    def _store_incoming_image(self, message, touser, result):
        media_id = message.get("MediaId", "")
        if not media_id:
            return
        started = time.perf_counter()
        try:
            image_bytes = self.media_downloader.download(media_id)
            duration_ms = round((time.perf_counter() - started) * 1000.0)
            channel_id = self.user_team_tracker.get_team(touser)
            if channel_id == PRIVATE_CHANNEL_ID:
                # Private channel: still one folder per sender, just not under a channel_N parent.
                record = self.private_image_store.save_screenshot(touser, image_bytes, duration_ms)
            else:
                # A photo carries no channel of its own -- file it under whichever channel this
                # sender most recently joined with a text digit, under that sender's own
                # top-level subfolder, matching the same {user_id}/channel_{id} layout outgoing
                # screenshots use (see UserTeamTracker and BrowserScreenshotService.capture).
                store_key = f"{touser}/channel_{channel_id}"
                record = self.incoming_image_store.save_screenshot(store_key, image_bytes, duration_ms)
            result["incoming_image_path"] = str(record.file_path)
            result["incoming_image_size"] = record.size_bytes
        except Exception as exc:
            # Best-effort: a failed download/save must not block the reply flow.
            result["incoming_image_error"] = str(exc)


def _safe_filename(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


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
    private_channel_config = get_section(webhook, "private_channel")
    private_image_dir = resolve_path(config_path, private_channel_config.get("save_dir"), "storage/private")
    image_sender = WeChatImageSender(appid, appsecret)
    media_downloader = WeChatMediaDownloader(client=image_sender.client)
    incoming_image_store = ScreenshotStore(base_dir=incoming_image_dir)
    private_image_store = ScreenshotStore(base_dir=private_image_dir)
    browser = BrowserScreenshotService(config_path)
    workflow = WeChatImageReplyWorkflow(
        config_path,
        image_sender,
        browser,
        screenshot_dir,
        media_downloader,
        incoming_image_store,
        private_image_store,
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
