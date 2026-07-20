"""Builds the WeChat custom tap-menu and translates a button tap back into the same plain
text a sender would have typed -- so a menu tap and typing "1"/"帮助"/"水印" produce exactly
the same `route_message` decision, with zero duplicated routing logic. This is the one place
that owns the button->EventKey scheme, since `build_menu_payload` (what gets pushed to WeChat)
and `event_key_to_text` (what an incoming tap means) have to agree with each other.

WeChat menu limits this respects: max 3 top-level buttons, max 5 sub-buttons per submenu, and
name length (roughly 4 CJK chars top-level / 8 CJK chars sub-level)."""

MAX_TOP_LEVEL_BUTTONS = 3
MAX_SUBMENU_BUTTONS = 5

MENU_HELP_KEY = "MENU_HELP"
MENU_WATERMARK_HELP_KEY = "MENU_WATERMARK_HELP"
MENU_EQUIPMENT_START_KEY = "MENU_EQUIPMENT_START"
MENU_EQUIPMENT_CAPTURE_KEY = "MENU_EQUIPMENT_CAPTURE"
CHANNEL_KEY_PREFIX = "MENU_CHANNEL_"


def channel_event_key(channel_id):
    return CHANNEL_KEY_PREFIX + str(channel_id)


def event_key_to_text(event_key):
    """Returns the chat text this EventKey stands in for, or None if it's not one of ours
    (e.g. a stale key from a previously pushed menu)."""
    if event_key == MENU_HELP_KEY:
        return "帮助"
    if event_key == MENU_WATERMARK_HELP_KEY:
        return "水印"
    if event_key == MENU_EQUIPMENT_START_KEY:
        return "设备"
    if event_key == MENU_EQUIPMENT_CAPTURE_KEY:
        return "获取截图"
    if event_key and event_key.startswith(CHANNEL_KEY_PREFIX):
        return event_key[len(CHANNEL_KEY_PREFIX):]
    return None


def _build_channel_submenu(visible_channel_ids):
    """Only the first MAX_SUBMENU_BUTTONS channel ids (sorted numerically) get a button; a
    config with more visible channels than that still works fine by typing the digit, it just
    isn't tappable. Returns None if there are no visible channels at all (e.g. browser_targets
    disabled), so the caller can omit the button entirely instead of pushing an empty submenu."""
    def sort_key(value):
        return (0, int(value)) if str(value).isdigit() else (1, str(value))

    channel_ids = sorted({str(c) for c in visible_channel_ids}, key=sort_key)[:MAX_SUBMENU_BUTTONS]
    if not channel_ids:
        return None
    return {
        "name": "选择频道",
        "sub_button": [
            {"type": "click", "name": f"频道{channel_id}", "key": channel_event_key(channel_id)}
            for channel_id in channel_ids
        ],
    }


def build_menu_payload(visible_channel_ids, equipment_enabled=False):
    """`visible_channel_ids` is the same set help_text.build_general_help_text uses
    (browser.targets.visible_targets.keys()) -- backup channels and the passcode-gated private
    channel are deliberately never exposed as buttons.

    WeChat allows at most MAX_TOP_LEVEL_BUTTONS (3) top-level buttons, which is exactly enough
    for either layout below but not both at once:
    - equipment_enabled=False (default): 选择频道 (channel submenu) + 帮助 + 水印帮助.
    - equipment_enabled=True: 选择设备 (starts the category->equipment->confirm flow) + 选择频道
      + 获取截图 (captures the sender's confirmed equipment). 帮助/水印帮助 drop off the menu in
      this layout to stay within the 3-button limit -- typing 帮助/水印 directly still works,
      the menu was always a tap shortcut for typing, never the only way in."""
    channel_button = _build_channel_submenu(visible_channel_ids)

    if equipment_enabled:
        buttons = [{"type": "click", "name": "选择设备", "key": MENU_EQUIPMENT_START_KEY}]
        if channel_button:
            buttons.append(channel_button)
        buttons.append({"type": "click", "name": "获取截图", "key": MENU_EQUIPMENT_CAPTURE_KEY})
        return {"button": buttons}

    buttons = []
    if channel_button:
        buttons.append(channel_button)
    buttons.append({"type": "click", "name": "帮助", "key": MENU_HELP_KEY})
    buttons.append({"type": "click", "name": "水印帮助", "key": MENU_WATERMARK_HELP_KEY})
    return {"button": buttons}
