"""Build Battery Limit Manager EXE"""
import os, sys, struct
from pathlib import Path

HERE = Path(__file__).parent

# ── 自动检测虚拟环境 ──
_VENV_PY = HERE / ".venv" / "Scripts" / "python.exe"
if _VENV_PY.exists() and sys.executable.lower() != str(_VENV_PY).lower():
    # 重启脚本使用虚拟环境的 Python
    os.execl(str(_VENV_PY), str(_VENV_PY), *sys.argv)
    # os.execl 成功后不会执行到这里

import shutil, subprocess
from PIL import Image


def gen_ico():
    src, dst = HERE / "icon.png", HERE / "app.ico"
    if not src.exists():
        return False
    img = Image.open(str(src)).convert("RGBA")
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2,
                    (w + side) // 2, (h + side) // 2))
    # 添加圆角
    from PIL import ImageDraw
    mask = Image.new("L", (side, side), 0)
    draw = ImageDraw.Draw(mask)
    radius = max(4, side // 10)
    draw.rounded_rectangle([0, 0, side - 1, side - 1], radius=radius, fill=255)
    img.putalpha(mask)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    entries, data, off = b"", b"", 6 + len(sizes) * 16
    for s in sizes:
        pix = list(img.resize((s, s), Image.LANCZOS).getdata())
        bmp = b""
        for y in range(s - 1, -1, -1):
            for x in range(s):
                r, g, b, a = pix[y * s + x]
                bmp += struct.pack("BBBB", b, g, r, a)
        bmp += b"\x00" * (((s + 31) // 32) * 4 * s)
        dib = struct.pack("<IiiHHIIiiII", 40, s, s * 2, 1, 32, 0, 0, 0, 0, 0, 0)
        fd = dib + bmp
        ew = 0 if s == 256 else s
        entries += struct.pack("<BBBBHHII", ew, ew, 0, 0, 1, 32, len(fd), off)
        data += fd
        off += len(fd)
    with open(str(dst), "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(sizes)))
        f.write(entries)
        f.write(data)
    print(f"app.ico ({len(sizes)} sizes)")
    return True


def build():
    gen_ico()

    dist_dir, build_dir = HERE / "dist", HERE / "build"
    for d in [dist_dir, build_dir]:
        if d.exists():
            try:
                shutil.rmtree(d)
            except PermissionError:
                # 可能是文件被占用，尝试删除内容
                for f in d.rglob("*"):
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass
                try:
                    shutil.rmtree(d)
                except Exception:
                    pass

    print("Building...")
    sep = os.pathsep
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "BatteryLimitManager",
        "--onefile",
        "--icon", str(HERE / "app.ico"),
        "--add-data", f"src{sep}src",
        "--add-data", f"config.json{sep}.",
        "--add-data", f"app.ico{sep}.",
        "--add-data", f"icon.png{sep}.",
        "--windowed",
        "--clean", "--noconfirm",
        "--hidden-import", "psutil",
        "--collect-all", "psutil",
        "--hidden-import", "miio",
        "--collect-all", "miio",
        "--hidden-import", "netifaces",
        "--hidden-import", "pystray",
        "--collect-all", "pystray",
        "--hidden-import", "PIL",
        "--collect-all", "PIL",
        "--hidden-import", "src.battery_auto_controller",
        "--hidden-import", "src.battery_manager",
        "--hidden-import", "src.mihome_controller",
        "--hidden-import", "src.config",
        "--hidden-import", "src.gui",
        "--hidden-import", "PySide6",
        "--hidden-import", "src.micloud_helper",
        "--hidden-import", "Crypto",
        "--hidden-import", "Cryptodome",
        "--collect-all", "Cryptodome",
        "src/main.py"
    ]

    result = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)

    if result.returncode != 0:
        print("Build failed!")
        print(result.stderr[-2000:] if result.stderr else "No stderr")
        print(result.stdout[-2000:] if result.stdout else "No stdout")
        return False

    exe = dist_dir / "BatteryLimitManager.exe"
    if not exe.exists():
        print("EXE not found")
        return False

    mb = exe.stat().st_size / (1024 * 1024)
    print(f"OK: {exe} ({mb:.1f} MB)")
    return True


if __name__ == "__main__":
    build()
