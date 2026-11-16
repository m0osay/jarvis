"""Generate the home-screen icons (run once; needs Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw

out = Path(__file__).resolve().parent.parent / "app" / "static"
for size in (192, 512):
    img = Image.new("RGB", (size, size), "#0e1116")
    d = ImageDraw.Draw(img)
    c, r = size / 2, size * 0.30
    d.ellipse([c - r, c - r, c + r, c + r], outline="#f0b429", width=max(4, size // 24))
    r2 = size * 0.10
    d.ellipse([c - r2, c - r2, c + r2, c + r2], fill="#f0b429")
    img.save(out / f"icon-{size}.png")
print("icons written to", out)
