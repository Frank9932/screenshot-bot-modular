from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def write_latency_image(path, details):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 720), (17, 28, 43))
    draw = ImageDraw.Draw(image)
    title_font = load_font(48)
    body_font = load_font(30)
    small_font = load_font(24)

    draw.rectangle((0, 0, 1280, 96), fill=(33, 79, 116))
    draw.text((48, 24), "Screenshot Bot WeChat Webhook Test", font=title_font, fill=(255, 255, 255))

    rows = [
        ("Received at", details.get("received_at", "")),
        ("Message create_time", str(details.get("create_time", ""))),
        ("Message type", details.get("msg_type", "")),
        ("From user", details.get("touser", "")),
        ("Message text", details.get("content", "")),
        ("Requested desktop", str(details.get("requested_desktop", ""))),
        ("Browser target", str(details.get("browser_team_id", ""))),
        ("Capture started", details.get("capture_started_at", "")),
    ]
    y = 140
    for label, value in rows:
        draw.text((64, y), f"{label}: ", font=body_font, fill=(120, 220, 180))
        draw.text((390, y), str(value)[:70], font=body_font, fill=(235, 238, 242))
        y += 54

    if details.get("capture_error"):
        draw.text((64, 594), "Capture error:", font=small_font, fill=(255, 180, 120))
        draw.text((240, 594), str(details.get("capture_error"))[:95], font=small_font, fill=(255, 220, 190))
    draw.text(
        (64, 650),
        "This image was generated locally after the WeChat webhook arrived, then uploaded through WeChat media API.",
        font=small_font,
        fill=(200, 210, 220),
    )
    image.save(path)


def load_font(size):
    for candidate in ["arial.ttf", "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/msyh.ttc"]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()
