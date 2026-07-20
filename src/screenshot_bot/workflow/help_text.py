"""General (non-watermark) assistant prompts. Written 傻瓜式 (foolproof/plain-language) on
purpose: whoever is messaging this bot may have no technical background at all, so every prompt
spells out exactly what to type next instead of assuming any prior context."""

from .user_team_tracker import PRIVATE_CHANNEL_ID, UNASSIGNED

GENERAL_HELP_WORDS = {"帮助", "help"}

# Hidden on purpose: not shown in any help/guidance text, and "私密"/"private" itself does
# nothing until a sender has first sent this exact passcode (see PRIVATE_CHANNEL_PASSCODE
# handling in wechat_image_reply.py). This keeps the private channel undiscoverable by anyone
# who doesn't already know the passcode.
PRIVATE_CHANNEL_WORDS = {"私密", "private"}
PRIVATE_CHANNEL_PASSCODE = "11223344"

PRIVATE_CHANNEL_UNLOCKED_TEXT = "已解锁私密频道"

PRIVATE_CHANNEL_JOINED_TEXT = (
    "已进入私密频道\n"
    "\n"
    "现在发给机器人的图片只会被保存，不会自动回发截图\n"
    "\n"
    "想退出私密频道，发送频道数字即可换回普通频道"
)

FIRST_JOIN_STORAGE_NOTICE = (
    "提示：您发送和接收的图片都会按您的用户ID单独保存，不会和其他人混在一起"
)

PRIVATE_CHANNEL_SAVED_TEXT = "图片已保存"


def format_channel_list(channel_ids):
    """Formats channel ids as a natural-language Chinese list, e.g. ["1","2","3"] ->
    "1、2 或 3". Sorted numerically where possible so channels read in a sensible order even
    though they're stored as dict/string keys."""
    def sort_key(value):
        return (0, int(value)) if str(value).isdigit() else (1, str(value))

    ids = sorted({str(c) for c in channel_ids}, key=sort_key)
    if not ids:
        return ""
    if len(ids) == 1:
        return ids[0]
    return "、".join(ids[:-1]) + " 或 " + ids[-1]


def build_general_help_text(visible_channel_ids):
    channel_list = format_channel_list(visible_channel_ids)
    return (
        "您好，这是截图机器人，使用说明如下\n"
        "\n"
        "第一步：选择频道\n"
        f"发送数字 {channel_list} 中的一个，机器人会马上把那个频道的截图发给您\n"
        "\n"
        "第二步：以后怎么再拿截图\n"
        "选好频道后，随时发一张图片给机器人，就能再收到这个频道的最新截图，不用再发数字\n"
        "\n"
        "想换频道\n"
        f"直接再发一次数字（{channel_list}）就能换到别的频道\n"
        "\n"
        "想改截图上的文字\n"
        "发送\"水印\"，查看怎么修改\n"
        "\n"
        "遇到问题\n"
        "随时发送\"帮助\"，可以再看一次这份说明"
    )


def build_channel_guidance(channel_id, visible_channel_ids):
    """The default reply when nothing else matches: an unrecognized text message, or a photo
    from a sender with no channel yet. Always states the sender's current channel (or that they
    have none) up front, then the two things they can actually do next -- this is the message
    that stands in for a human clicking around a confusing app for the first time, so it needs
    to say what a "channel" even is and what typing a photo/digit does, in plain terms."""
    channel_list = format_channel_list(visible_channel_ids)
    if not channel_id or channel_id == UNASSIGNED:
        return (
            "您好，这是截图机器人\n"
            "\n"
            "您还没有选择频道\n"
            "\n"
            "怎么用：\n"
            f"1. 发送数字 {channel_list} 中的一个，选择一个频道，机器人会马上发给您那个频道的截图\n"
            "2. 选好频道后，以后发一张图片给机器人，也能再收到这个频道的最新截图\n"
            "\n"
            "遇到问题？发送\"帮助\"查看完整说明"
        )
    if channel_id == PRIVATE_CHANNEL_ID:
        return (
            "您好，您现在在私密频道\n"
            "\n"
            "怎么用：\n"
            "1. 发送图片给机器人，图片只会被保存，不会自动回发\n"
            f"2. 发送数字 {channel_list} 中的一个，可以换回普通频道\n"
            "\n"
            "遇到问题？发送\"帮助\"查看完整说明"
        )
    return (
        f"您好，您现在在频道{channel_id}\n"
        "\n"
        "怎么用：\n"
        f"1. 发送图片给机器人，会收到频道{channel_id}的最新截图\n"
        f"2. 发送数字 {channel_list} 中的一个，可以换到别的频道\n"
        "\n"
        "遇到问题？发送\"帮助\"查看完整说明"
    )
