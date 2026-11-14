"""Draws media_manager/assets/icon.png and icon.ico (run once; needs Pillow)."""

from pathlib import Path

from PIL import Image, ImageDraw

out = Path(__file__).resolve().parents[1] / "media_manager" / "assets"
S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=52, fill=(59, 111, 196))
ink = (255, 255, 255)
d.rounded_rectangle([44, 64, 212, 192], radius=18, outline=ink, width=12)  # a screen / frame
d.polygon([(108, 98), (108, 158), (160, 128)], fill=ink)  # play
img.save(out / "icon.png")
img.save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
