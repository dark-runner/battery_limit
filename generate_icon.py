"""Convert icon.png -> app.ico (multi-res, manually packed)"""
from PIL import Image
import struct, os

SIZES = [16, 24, 32, 48, 64, 128, 256]
src = os.path.join(os.path.dirname(__file__), "icon.png")
dst = os.path.join(os.path.dirname(__file__), "app.ico")

img = Image.open(src).convert("RGBA")
w, h = img.size
side = min(w, h)
img = img.crop(((w - side) // 2, (h - side) // 2,
                (w + side) // 2, (h + side) // 2))

frames = {s: img.resize((s, s), Image.LANCZOS) for s in SIZES}

data = b""
offset = 6 + len(SIZES) * 16

for s in SIZES:
    f = frames[s]
    bmp = struct.pack("<I", 40)     # BITMAPINFOHEADER
    bmp += struct.pack("<i", s)     # width
    bmp += struct.pack("<i", s * 2) # height (x2 for ICO)
    bmp += struct.pack("<HH", 1, 32)  # planes, bpp
    bmp += struct.pack("<I", 0)     # compression
    bmp += struct.pack("<I", s * s * 4)
    bmp += struct.pack("<ii", 0, 0)  # resolution
    bmp += struct.pack("<II", 0, 0)  # colors, important

    pixels = list(f.getdata())
    for y in range(s - 1, -1, -1):
        for x in range(s):
            r, g, b, a = pixels[y * s + x]
            bmp += struct.pack("BBBB", b, g, r, a)

    # AND mask padding
    bmp += b"\x00" * (((s + 31) // 32) * 4 * s)

    ew = 0 if s == 256 else s
    eh = 0 if s == 256 else s
    data += struct.pack("<BBBBHHII", ew, eh, 0, 0, 1, 32, len(bmp), offset)
    data += bmp
    offset += len(bmp)

with open(dst, "wb") as f:
    f.write(struct.pack("<HHH", 0, 1, len(SIZES)))
    f.write(data)
print(f"✅ {dst} ({len(SIZES)} sizes)")
