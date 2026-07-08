"""General (non-watermark) assistant prompts: onboarding help and the nudge sent when a photo
arrives from a user who hasn't joined a channel yet."""

GENERAL_HELP_WORDS = {"帮助", "help"}

GENERAL_HELP_TEXT = (
    "欢迎使用截图机器人\n"
    "\n"
    "加入频道\n"
    "发送数字（1-5）加入对应频道，并立即收到该频道的截图\n"
    "\n"
    "再次获取截图\n"
    "加入频道后，发送任意图片即可再次收到该频道的截图\n"
    "\n"
    "自定义水印\n"
    "发送\"水印\"查看频道水印自定义命令"
)

CHANNEL_UNASSIGNED_PROMPT = (
    "您还没有加入任何频道\n"
    "请先发送数字（1-5）加入一个频道，之后发送图片即可获取该频道截图"
)
