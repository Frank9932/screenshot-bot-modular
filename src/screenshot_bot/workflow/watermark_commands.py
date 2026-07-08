"""Parses the single-message chat commands that let a team customize its own watermark
(field text, background opacity) without touching config.json. Deliberately stateless --
each message is a complete command on its own, there is no multi-step/guided flow to track
per user."""

TRIGGER_WORDS = {"水印", "watermark"}
STATUS_WORDS = {"状态", "status"}
RESET_WORDS = {"重置", "reset"}
OPACITY_WORDS = {"透明度", "opacity"}
SET_WORDS = {"设置", "set"}
HELP_WORDS = {"帮助", "help"}

# One block per command, separated by a blank line -- a WeChat chat bubble is proportional-font
# and often narrow (mobile), so column-aligning descriptions with padding spaces (as in a
# terminal help screen) doesn't actually line up and just reads as ragged. A short heading line
# per command, its description right below, is what stays scannable at chat width.
HELP_TEXT = (
    "水印设置命令（频道编号 1-5）\n"
    "\n"
    "水印 <频道> 状态\n"
    "查看当前水印设置\n"
    "\n"
    "水印 <频道> 设置 <序号> <内容>\n"
    "修改水印第N行内容\n"
    "\n"
    "水印 <频道> 透明度 <0-255>\n"
    "设置背景不透明度（0=全透明，255=不透明）\n"
    "\n"
    "水印 <频道> 重置\n"
    "恢复默认水印设置\n"
    "\n"
    "示例：水印 1 设置 1 新的测试区域内容\n"
    "提示：设置 <序号> 后不加内容可清空该行"
)


def parse_watermark_command(text):
    """Returns None if this text isn't a watermark command at all (so the caller falls
    through to normal team-digit/screenshot handling); otherwise a dict describing the
    parsed action, always including "action" ("help" unless fully recognized)."""
    tokens = (text or "").strip().split()
    if not tokens or tokens[0].strip().lower() not in TRIGGER_WORDS:
        return None

    rest = tokens[1:]
    if not rest or rest[0] in HELP_WORDS:
        return {"action": "help"}

    team_id = rest[0]
    if not team_id.isdigit():
        return {"action": "help"}

    rest = rest[1:]
    if not rest:
        return {"action": "help", "team_id": team_id}

    sub = rest[0]
    if sub in STATUS_WORDS:
        return {"action": "status", "team_id": team_id}
    if sub in RESET_WORDS:
        return {"action": "reset", "team_id": team_id}
    if sub in OPACITY_WORDS and len(rest) >= 2:
        return {"action": "opacity", "team_id": team_id, "value": rest[1]}
    # len(rest) == 2 (just the index, no content after it) is valid on purpose: it means
    # "clear this field to empty", not a malformed command -- there is no way to type a
    # literal empty string as its own whitespace-split token, so omitting it entirely is the
    # only way a chat command can express "blank this out".
    if sub in SET_WORDS and len(rest) >= 2:
        return {"action": "set_field", "team_id": team_id, "index": rest[1], "value": " ".join(rest[2:])}
    return {"action": "help", "team_id": team_id}
