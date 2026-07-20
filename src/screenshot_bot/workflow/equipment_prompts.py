"""Trigger words and reply text for the select-equipment guided flow (category -> equipment ->
confirm -> capture). Mirrors help_text.py's role for the simpler channel flow -- written 傻瓜式
(plain-language) for the same reason: whoever is tapping/typing through this may have no
technical background beyond what the bot tells them directly."""

from .help_text import format_channel_list

EQUIPMENT_START_WORDS = {"设备", "equipment"}
EQUIPMENT_CAPTURE_WORDS = {"获取截图", "截图"}
EQUIPMENT_CONFIRM_WORDS = {"确认", "confirm"}
EQUIPMENT_CANCEL_WORDS = {"取消", "cancel"}

EQUIPMENT_LIST_EMPTY_TEXT = "设备列表暂不可用，请联系管理员检查设备清单文件"


def build_category_list_text(categories):
    lines = ["请选择设备类别（回复数字）：", ""]
    lines.extend(f"{index}. {category}" for index, category in enumerate(categories, start=1))
    return "\n".join(lines)


def build_equipment_list_text(category, items):
    lines = [f"类别「{category}」下的设备，请选择（回复数字）：", ""]
    lines.extend(f"{index}. {item['equipment']}" for index, item in enumerate(items, start=1))
    lines.append("")
    lines.append('发送"设备"可重新选择类别')
    return "\n".join(lines)


def build_confirm_prompt_text(category, equipment):
    return f'您选择了：{category} / {equipment}\n\n确认请回复"确认"，重选请回复"取消"'


def build_confirmed_text(category, equipment):
    return (
        f"已确认设备：{category} / {equipment}\n"
        "\n"
        '点击菜单"获取截图"（或发送"获取截图"）即可获取该设备的最新截图'
    )


def build_cancelled_text():
    return '已取消，发送"设备"重新选择'


def build_invalid_selection_text(list_text):
    return "输入的数字无效，请重新选择\n\n" + list_text


def build_capture_not_ready_text():
    return '尚未确认设备，请先发送"设备"选择要截图的设备'


def build_capture_no_channel_text(visible_channel_ids):
    channel_list = format_channel_list(visible_channel_ids)
    return f"请先发送数字 {channel_list} 中的一个选择频道，再获取设备截图"
