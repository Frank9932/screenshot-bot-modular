import xml.etree.ElementTree as ET


def parse_xml_message(body):
    root = ET.fromstring(body)
    result = {}
    for child in root:
        result[child.tag] = child.text or ""
    return result


def message_dedupe_key(message):
    msg_id = str(message.get("MsgId", "") or "").strip()
    if msg_id:
        return "msgid:" + msg_id
    parts = [
        str(message.get("FromUserName", "") or ""),
        str(message.get("CreateTime", "") or ""),
        str(message.get("MsgType", "") or ""),
        str(message.get("Content", "") or ""),
    ]
    return "fallback:" + "|".join(parts)
