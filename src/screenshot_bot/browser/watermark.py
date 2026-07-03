from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class WatermarkRenderer:
    def __init__(self, watermark_config):
        self.config = watermark_config or {}

    def apply(self, input_path, output_path, dynamic_fields=None):
        dynamic = dynamic_fields or {}
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        if not bool(self.config.get("enabled", True)):
            Image.open(input_path).convert("RGB").save(output, "PNG")
            return {"watermark_applied": False, "watermarked_path": str(output)}

        image = Image.open(input_path).convert("RGBA")
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = self._load_font()
        rows = self._rows(dynamic)
        if not rows:
            image.convert("RGB").save(output, "PNG")
            return {"watermark_applied": False, "watermarked_path": str(output)}

        padding = int(self.config.get("padding", 18))
        margin_left = int(self.config.get("margin_left", 70))
        margin_bottom = int(self.config.get("margin_bottom", 70))
        line_spacing = int(self.config.get("line_spacing", 8))
        text_color = (*_parse_hex_color(self.config.get("text_color"), (255, 255, 255)), 255)
        bg_rgb = _parse_hex_color(self.config.get("background_color"), (0, 0, 0))
        bg_alpha = int(self.config.get("background_opacity", 190))

        boxes = [draw.textbbox((0, 0), row, font=font) for row in rows]
        line_heights = [box[3] - box[1] for box in boxes]
        width = max(box[2] - box[0] for box in boxes) + padding * 2
        height = sum(line_heights) + line_spacing * (len(rows) - 1) + padding * 2
        x = margin_left
        y = max(0, image.height - margin_bottom - height)
        draw.rectangle((x, y, x + width, y + height), fill=(*bg_rgb, bg_alpha))
        text_y = y + padding
        for row, line_height in zip(rows, line_heights):
            draw.text((x + padding, text_y), row, font=font, fill=text_color)
            text_y += line_height + line_spacing

        Image.alpha_composite(image, overlay).convert("RGB").save(output, "PNG")
        return {"watermark_applied": True, "watermarked_path": str(output)}

    def _rows(self, dynamic):
        label_separator = str(self.config.get("label_separator", ": "))
        rows = []
        for item in self.config.get("fields", []) or []:
            if not isinstance(item, dict):
                continue
            label = _render_value(item.get("label", ""), dynamic)
            value = _render_value(item.get("value", ""), dynamic)
            rows.append(f"{label}{label_separator}{value}" if label else value)
        for line in self.config.get("lines", []) or []:
            rows.append(_render_value(line, dynamic))
        if bool(self.config.get("include_timestamp", True)):
            timestamp = dynamic.get("timestamp") or datetime.now().astimezone().strftime(_timestamp_format(self.config.get("timestamp_format")))
            label = str(self.config.get("timestamp_label", "") or "")
            prefix = str(self.config.get("timestamp_prefix", "") or "")
            rows.append(f"{label}{label_separator}{timestamp}" if label else f"{prefix}{timestamp}")
        rows.extend(str(row) for row in dynamic.get("_extra_watermark_rows", []) if str(row).strip())
        return [row for row in rows if str(row).strip()]

    def _load_font(self):
        size = int(self.config.get("font_size", 36))
        family = str(self.config.get("font_family", "")).lower()
        candidates = []
        if "yahei" in family:
            candidates.append("C:/Windows/Fonts/msyh.ttc")
        candidates.extend(["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/msyh.ttc", "arial.ttf"])
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        return ImageFont.load_default()


def _parse_hex_color(value, default):
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        return default
    try:
        return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return default


def _timestamp_format(fmt):
    return (
        str(fmt or "yyyy.MM.dd HH:mm")
        .replace("yyyy", "%Y")
        .replace("MM", "%m")
        .replace("dd", "%d")
        .replace("HH", "%H")
        .replace("mm", "%M")
        .replace("ss", "%S")
    )


def _render_value(value, dynamic_fields):
    text = str(value)
    for key, replacement in dynamic_fields.items():
        text = text.replace("{" + key + "}", str(replacement))
    return text
