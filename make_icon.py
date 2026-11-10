"""
tools/make_icon.py - ساخت آیکون‌های اپ از لوگوی نهایی (tools/logo.png).
اگر tools/logo.png نبود، لوگوی ساده‌ی رسم‌شده با کد استفاده می‌شود.
خروجی: android/assets/icon.png و android/res/mipmap-*/ic_launcher.png   (نیازمند: pip install pillow)
"""
import os
from PIL import Image, ImageDraw

NAVY, TEAL, GREEN, WHITE, GREY = "#153A5B", "#008975", "#2FBF8F", "#FFFFFF", "#DCE6EE"
S = 1024
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOGO_FILE = os.path.join(HERE, "logo.png")


def draw_logo(size=S):
    img = Image.new("RGB", (S, S), NAVY)
    d = ImageDraw.Draw(img)
    d.ellipse((130, 130, S - 130, S - 130), outline=TEAL, width=64)
    # کپسول سفید (مایل)
    cap = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    c = ImageDraw.Draw(cap)
    c.rounded_rectangle((250, 400, 700, 600), radius=100, fill=WHITE)
    c.rounded_rectangle((475, 400, 700, 600), radius=100, fill=GREY)
    c.rectangle((475, 400, 600, 600), fill=GREY)
    cap = cap.rotate(40, resample=Image.BICUBIC, center=(S // 2, S // 2))
    img.paste(cap, (0, 0), cap)
    # زنگوله‌ی سبز (بالا-راست)
    bx, by = 650, 250
    d = ImageDraw.Draw(img)
    d.ellipse((bx - 95, by - 100, bx + 95, by + 90), fill=GREEN)
    d.polygon([(bx - 95, by), (bx + 95, by), (bx + 130, by + 120), (bx - 130, by + 120)], fill=GREEN)
    d.rounded_rectangle((bx - 135, by + 105, bx + 135, by + 140), radius=17, fill=GREEN)
    d.ellipse((bx - 28, by + 128, bx + 28, by + 184), fill=GREEN)
    d.ellipse((bx - 16, by - 130, bx + 16, by - 98), fill=GREEN)
    return img


def load_logo():
    if os.path.exists(LOGO_FILE):
        return Image.open(LOGO_FILE).convert("RGB")
    return draw_logo()


def make_round(img):
    """برش دایره‌ای با گوشه‌های شفاف (آیکون گرد)"""
    img = img.convert("RGBA")
    big = 4
    mask = Image.new("L", (img.width * big, img.height * big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, img.width * big - 1, img.height * big - 1), fill=255)
    mask = mask.resize(img.size, Image.LANCZOS)
    img.putalpha(mask)
    return img


def main():
    logo = make_round(load_logo())
    os.makedirs(os.path.join(ROOT, "android", "assets"), exist_ok=True)
    logo.resize((512, 512), Image.LANCZOS).save(os.path.join(ROOT, "android", "assets", "icon.png"))
    for folder, px in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
        out = os.path.join(ROOT, "android", "res", f"mipmap-{folder}")
        os.makedirs(out, exist_ok=True)
        logo.resize((px, px), Image.LANCZOS).save(os.path.join(out, "ic_launcher.png"))
    print("آیکون‌ها ساخته شد.")


if __name__ == "__main__":
    main()
