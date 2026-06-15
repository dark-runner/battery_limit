"""Native Desktop GUI - High DPI Glassmorphism Design + System Tray"""

import logging
import os
import sys
import time
import ctypes
import threading
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED
from typing import Optional
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

try:
    import pystray
    from PIL import Image as PILImage
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── 高DPI 感知 ──────────────────────────────────────────
def _enable_dpi_aware():
    """启用 Windows 高DPI 支持"""
    try:
        # Windows 10 (1703+) Per-Monitor v2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # Windows 8.1
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                # Windows Vista/7
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def _get_dpi_scale(root) -> float:
    """获取当前 DPI 缩放比例"""
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(root.winfo_id())
        return dpi / 96.0
    except Exception:
        return 1.0


# ── 调色板 ──────────────────────────────────────────────
TK = {
    "bg": "#1a1a2e",
    "card": "#222244",
    "card_light": "#2a2a50",
    "fg": "#e8e8f0",
    "dim": "#8888aa",
    "green": "#7ddfa0",
    "orange": "#f5b87a",
    "red": "#f07a7a",
    "blue": "#7ecfff",
    "pink": "#ffb6c1",
    "border": "#3a3a5c",
}

FONT_FAMILY = "Microsoft YaHei UI"


def _style(scale: float = 1.0):
    s = ttk.Style()
    for t in ("vista", "clam"):
        try:
            s.theme_use(t)
            break
        except tk.TclError:
            continue

    fs = lambda pt: max(int(pt * scale), pt)  # noqa: E731
    s.configure(".", font=(FONT_FAMILY, fs(9)), foreground=TK["fg"],
                background=TK["bg"])
    s.configure("TFrame", background=TK["bg"])
    s.configure("TLabelframe", background=TK["bg"], foreground=TK["fg"],
                font=(FONT_FAMILY, fs(9), "bold"),
                relief=tk.FLAT)
    s.configure("TLabelframe.Label", background=TK["bg"], foreground=TK["blue"])
    s.configure("TLabel", background=TK["bg"], foreground=TK["fg"])
    s.configure("TButton", padding=(fs(8), fs(3)))
    s.configure("Horizontal.TProgressbar",
                troughcolor=TK["card"],
                background=TK["green"],
                thickness=fs(14))


def _glass_frame(parent, **kw):
    f = tk.Frame(parent, bg=TK["card"], highlightbackground=TK["border"],
                 highlightthickness=1, **kw)
    return f


def _icon_path() -> str:
    for p in [
        os.path.join(os.path.dirname(__file__), "..", "app.ico"),
        os.path.join(os.path.dirname(__file__), "app.ico"),
        "app.ico",
    ]:
        if os.path.exists(p):
            return p
    return ""


def _make_rounded(img, radius=None):
    """为 PIL Image 添加圆角（自适应尺寸）"""
    from PIL import ImageDraw
    if radius is None:
        radius = max(4, min(img.width, img.height) // 6)
    mask = PILImage.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, img.width - 1, img.height - 1],
                           radius=radius, fill=255)
    rounded = PILImage.new("RGBA", img.size, (0, 0, 0, 0))
    rounded.paste(img, (0, 0), mask)
    return rounded


def _load_tray_image():
    """加载系统托盘图标（圆角处理）"""
    for p in [
        os.path.join(os.path.dirname(__file__), "..", "icon.png"),
        os.path.join(os.path.dirname(__file__), "icon.png"),
        "icon.png",
    ]:
        if os.path.exists(p):
            img = PILImage.open(p).convert("RGBA")
            return _make_rounded(img)
    ico = _icon_path()
    if ico:
        img = PILImage.open(ico).convert("RGBA")
        return _make_rounded(img)
    # 最后后备：创建一个简单的圆角图标
    img = PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 60, 60], radius=12, fill=(120, 180, 255, 255))
    return img


# ════════════════════════════════════════════════════════
#  设置窗口
# ════════════════════════════════════════════════════════
class SettingsWindow:
    """设置窗口（二级页面）"""

    def __init__(self, parent, config, controller, on_save=None, scale=1.0):
        self.parent = parent
        self.config = config
        self.controller = controller
        self.on_save = on_save
        self.scale = scale
        self.window: Optional[tk.Toplevel] = None
        self._create()

    def _create(self):
        sc = self.scale
        fs = lambda pt: max(int(pt * sc), pt)

        # 先算好位置再创建窗口，避免跳动
        self.parent.update_idletasks()
        pw, ph = self.parent.winfo_width(), self.parent.winfo_height()
        px, py = self.parent.winfo_x(), self.parent.winfo_y()
        W, H = int(520 * sc), int(620 * sc)
        cx = px + max(0, (pw - W) // 2)
        cy = max(0, py - 60)  # 偏上，窗口顶部上移60px

        w = tk.Toplevel(self.parent)
        w.title("⚙ 设置")
        w.resizable(False, False)
        w.transient(self.parent)
        w.geometry(f"{W}x{H}+{cx}+{cy}")
        w.configure(bg=TK["bg"])
        w.grab_set()
        icon = _icon_path()
        if icon:
            try:
                w.iconbitmap(default=icon)
            except Exception:
                pass
        self.window = w

        pad = int(18 * sc)

        # ── 可滚动容器 ──
        canvas = tk.Canvas(w, bg=TK["bg"], highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(w, orient=tk.VERTICAL, command=canvas.yview,
                                 bg=TK["card"], troughcolor=TK["bg"])
        scrollable = tk.Frame(canvas, bg=TK["bg"])
        scrollable.bind("<Configure>",
                        lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮支持（绑定到画布及其所有子组件）
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_wheel(widget):
            widget.bind("<MouseWheel>", _on_mousewheel, add="+")
            for child in widget.winfo_children():
                _bind_wheel(child)

        canvas.bind("<MouseWheel>", _on_mousewheel)
        w.bind("<MouseWheel>", _on_mousewheel)
        # 窗口关闭时清理滚轮绑定
        w.protocol("WM_DELETE_WINDOW", lambda: (
            w.unbind_all("<MouseWheel>"), w.destroy()
        ))

        mf = tk.Frame(scrollable, bg=TK["bg"])
        mf.pack(fill=tk.BOTH, expand=True, padx=pad, pady=int(16 * sc))

        # 延迟绑定滚轮到所有子组件
        w.after(100, lambda: _bind_wheel(scrollable))

        # 标题
        tk.Label(mf, text="⚙ 设置",
                 font=(FONT_FAMILY, fs(16), "bold"),
                 fg=TK["fg"], bg=TK["bg"]).pack(pady=(0, int(4 * sc)))
        tk.Label(mf, text="Battery Limit Manager",
                 font=(FONT_FAMILY, fs(8)),
                 fg=TK["dim"], bg=TK["bg"]).pack(pady=(0, int(16 * sc)))

        # ── 卡片 ──
        self._card(mf, "🎯 阈值设置", [
            ("高阈值 (%)", "high", self.controller.high_threshold, 1, 100, 1.0),
            ("低阈值 (%)", "low", self.controller.low_threshold, 0, 99, 1.0),
        ], sc)
        self._card(mf, "⏱ 检查设置", [
            ("检查间隔 (秒)", "interval", self.config.get("check_interval", 60),
             10, 600, 10),
        ], sc)
        self._autostart_card(mf, sc)
        self._mi_card(mf, sc)

        # 按钮
        br = tk.Frame(mf, bg=TK["bg"])
        br.pack(pady=(int(14 * sc), 0))
        for txt, cmd, bold in [("💾 保存", self._save, True),
                                ("取消", w.destroy, False)]:
            tk.Button(br, text=txt,
                      font=(FONT_FAMILY, fs(10), "bold" if bold else "normal"),
                      bg=TK["card"], fg=TK["fg"],
                      activebackground=TK["card_light"],
                      relief=tk.FLAT, bd=0, padx=int(18 * sc), pady=int(4 * sc),
                      cursor="hand2", command=cmd
                      ).pack(side=tk.LEFT, padx=int(5 * sc))

        w.bind("<Return>", lambda e: self._save())
        w.bind("<Escape>", lambda e: w.destroy())

    def _card(self, parent, title, fields, sc):
        fs = lambda pt: max(int(pt * sc), pt)
        card = _glass_frame(parent, padx=int(14 * sc), pady=int(10 * sc))
        card.pack(fill=tk.X, pady=(0, int(10 * sc)))

        tk.Label(card, text=title, font=(FONT_FAMILY, fs(10), "bold"),
                 fg=TK["blue"], bg=TK["card"]).pack(anchor=tk.W, pady=(0, int(6 * sc)))

        for label, key, default, lo, hi, inc in fields:
            row = tk.Frame(card, bg=TK["card"])
            row.pack(fill=tk.X, pady=int(2 * sc))
            tk.Label(row, text=label, width=int(14 * sc), anchor=tk.W,
                     fg=TK["fg"], bg=TK["card"],
                     font=(FONT_FAMILY, fs(9))).pack(side=tk.LEFT)

            if key == "high":
                self.high_var = tk.DoubleVar(value=default)
                self._spin(row, self.high_var, lo, hi, inc, sc)
                tk.Label(row, text="≥ 此值关闭开关",
                         fg=TK["dim"], bg=TK["card"],
                         font=(FONT_FAMILY, fs(8))).pack(side=tk.LEFT, padx=(int(6 * sc), 0))
            elif key == "low":
                self.low_var = tk.DoubleVar(value=default)
                self._spin(row, self.low_var, lo, hi, inc, sc)
                tk.Label(row, text="≤ 此值开启开关",
                         fg=TK["dim"], bg=TK["card"],
                         font=(FONT_FAMILY, fs(8))).pack(side=tk.LEFT, padx=(int(6 * sc), 0))
            elif key == "interval":
                self.interval_var = tk.IntVar(value=default)
                self._spin(row, self.interval_var, lo, hi, inc, sc)

    def _spin(self, parent, var, lo, hi, inc, sc):
        fs = lambda pt: max(int(pt * sc), pt)
        tk.Spinbox(parent, from_=lo, to=hi, increment=inc,
                   textvariable=var, width=int(8 * sc),
                   font=(FONT_FAMILY, fs(9)),
                   bg=TK["card_light"], fg=TK["fg"],
                   relief=tk.FLAT, bd=0,
                   buttonbackground=TK["border"]).pack(side=tk.LEFT)

    def _autostart_card(self, parent, sc):
        """开机自启设置卡片"""
        fs = lambda pt: max(int(pt * sc), pt)
        card = _glass_frame(parent, padx=int(14 * sc), pady=int(10 * sc))
        card.pack(fill=tk.X, pady=(0, int(10 * sc)))

        tk.Label(card, text="🚀 开机自启",
                 font=(FONT_FAMILY, fs(10), "bold"),
                 fg=TK["blue"], bg=TK["card"]).pack(anchor=tk.W, pady=(0, int(6 * sc)))

        row = tk.Frame(card, bg=TK["card"])
        row.pack(fill=tk.X)
        self._autostart_var = tk.BooleanVar(value=self.config.get("autostart", False))
        cb = tk.Checkbutton(row, text="开机后自动启动", variable=self._autostart_var,
                            font=(FONT_FAMILY, fs(9)),
                            fg=TK["fg"], bg=TK["card"],
                            selectcolor=TK["card"],
                            activebackground=TK["card"],
                            activeforeground=TK["fg"],
                            relief=tk.FLAT, bd=0,
                            cursor="hand2")
        cb.pack(side=tk.LEFT)
        # 提示文字
        tk.Label(row, text="（注册表 Run 项）",
                 font=(FONT_FAMILY, fs(7)), fg=TK["dim"], bg=TK["card"]
                 ).pack(side=tk.LEFT, padx=(int(4 * sc), 0))

    def _mi_card(self, parent, sc):
        fs = lambda pt: max(int(pt * sc), pt)
        card = _glass_frame(parent, padx=int(14 * sc), pady=int(10 * sc))
        card.pack(fill=tk.X, pady=(0, int(10 * sc)))

        tk.Label(card, text="🌐 米家设备设置",
                 font=(FONT_FAMILY, fs(10), "bold"),
                 fg=TK["blue"], bg=TK["card"]).pack(anchor=tk.W, pady=(0, int(6 * sc)))

        # ── 方式A：手动输入 ──
        tk.Label(card, text="方式一：手动输入（IP + Token）",
                 font=(FONT_FAMILY, fs(8)), fg=TK["dim"], bg=TK["card"]
                 ).pack(anchor=tk.W)

        ipr = tk.Frame(card, bg=TK["card"])
        ipr.pack(fill=tk.X, pady=int(1 * sc))
        tk.Label(ipr, text="设备 IP", width=int(10 * sc), anchor=tk.W,
                 fg=TK["fg"], bg=TK["card"]).pack(side=tk.LEFT)
        self.ip_var = tk.StringVar(value=self.config.get("mihome.ip", ""))
        tk.Entry(ipr, textvariable=self.ip_var, width=int(24 * sc),
                 font=(FONT_FAMILY, fs(9)),
                 bg=TK["card_light"], fg=TK["fg"],
                 relief=tk.FLAT, bd=0).pack(side=tk.LEFT)

        tkr = tk.Frame(card, bg=TK["card"])
        tkr.pack(fill=tk.X, pady=int(1 * sc))
        tk.Label(tkr, text="Token", width=int(10 * sc), anchor=tk.W,
                 fg=TK["fg"], bg=TK["card"]).pack(side=tk.LEFT)
        self._show_token = False
        self.token_var = tk.StringVar(value=self.config.get("mihome.token", ""))
        self.token_ent = tk.Entry(tkr, textvariable=self.token_var,
                                  width=int(18 * sc),
                                  show="*", font=(FONT_FAMILY, fs(9)),
                                  bg=TK["card_light"], fg=TK["fg"],
                                  relief=tk.FLAT, bd=0)
        self.token_ent.pack(side=tk.LEFT, padx=(0, int(4 * sc)))
        tk.Button(tkr, text="显示", font=(FONT_FAMILY, fs(8)),
                  bg=TK["card"], fg=TK["blue"],
                  activebackground=TK["card_light"],
                  relief=tk.FLAT, bd=0, cursor="hand2",
                  command=self._tog_token).pack(side=tk.LEFT, padx=(0, 2))
        # 测试连接按钮
        tk.Button(tkr, text="🔌 测试连接", font=(FONT_FAMILY, fs(8)),
                  bg=TK["card"], fg=TK["green"],
                  activebackground=TK["card_light"],
                  relief=tk.FLAT, bd=0, cursor="hand2",
                  command=self._test_connection_manual
                  ).pack(side=tk.LEFT)

        # 云端获取 Token 按钮
        cloud_frame = tk.Frame(card, bg=TK["card"])
        cloud_frame.pack(fill=tk.X, pady=(int(4 * sc), 0))
        tk.Button(cloud_frame, text="☁️ 云端获取 Token",
                  font=(FONT_FAMILY, fs(9)),
                  bg=TK["card_light"], fg=TK["blue"],
                  activebackground=TK["border"],
                  relief=tk.FLAT, bd=0, cursor="hand2", padx=10, pady=3,
                  command=self._cloud_login_dialog
                  ).pack(side=tk.LEFT)

        # 扫描结果区域
        self._discover_frame = tk.Frame(card, bg=TK["card"])

        self._device_list_label = tk.Label(card, text="",
                                           font=(FONT_FAMILY, fs(8)),
                                           fg=TK["dim"], bg=TK["card"])
        self._device_list_label.pack(anchor=tk.W, pady=(int(2 * sc), 0))

    def _tog_token(self):
        self._show_token = not self._show_token
        self.token_ent.config(show="" if self._show_token else "*")

    def _test_connection_manual(self):
        """测试当前输入的 IP 和 Token 是否能连接设备"""
        ip = self.ip_var.get().strip()
        token = self.token_var.get().strip()
        if not ip or not token:
            messagebox.showwarning("测试连接", "请先输入 IP 和 Token", parent=self.window)
            return

        import re
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
            messagebox.showerror("参数错误", "IP 地址格式不正确", parent=self.window)
            return
        if not re.match(r'^[0-9a-fA-F]{32}$', token):
            messagebox.showerror("参数错误", "Token 必须是32位十六进制字符", parent=self.window)
            return

        # 后台测试
        import threading

        def _do_test():
            try:
                from miio import Device
                test_dev = Device(ip=ip, token=token, timeout=5)
                info = test_dev.send("miIO.info", [])
                model = info.get("model", "未知") if isinstance(info, dict) else "未知"
                fw = info.get("fw_ver", "") if isinstance(info, dict) else ""
                extra = f"  固件: {fw}" if fw else ""
                self.window.after(0, lambda: messagebox.showinfo(
                    "✅ 连接成功",
                    f"设备连接成功！\nIP: {ip}\n型号: {model}{extra}\n\nToken 有效，保存后即可使用。",
                    parent=self.window))
            except Exception as e:
                self.window.after(0, lambda e=e: messagebox.showerror(
                    "❌ 连接失败",
                    f"无法连接到设备 {ip}\n\n"
                    f"错误: {e}\n\n"
                    f"常见原因：\n"
                    f"1. Token 不正确 — 请用「☁️ 云端获取 Token」获取\n"
                    f"2. IP 地址不正确\n"
                    f"3. 设备不在线或网络不通\n"
                    f"4. 防火墙阻止了 UDP 通信(54321端口)",
                    parent=self.window))

        threading.Thread(target=_do_test, daemon=True).start()

    def _cloud_login_dialog(self):
        """显示小米云登录对话框 - 支持二维码和密码两种登录方式"""
        # 先算好位置再创建
        if self.window and self.window.winfo_exists():
            self.window.update_idletasks()
            dw, dh = 620, 680
            cx = self.window.winfo_x() + max(0, (self.window.winfo_width() - dw) // 2)
            cy = max(0, self.window.winfo_y() - 60)
        else:
            dw, dh, cx, cy = 620, 680, 100, 100

        dlg = tk.Toplevel(self.window)
        dlg.title("☁️ 登录小米云")
        dlg.geometry(f"{dw}x{dh}+{cx}+{cy}")
        dlg.resizable(False, False)
        dlg.transient(self.window)
        dlg.configure(bg=TK["bg"])
        dlg.grab_set()
        sc = getattr(self, 'scale', 1.0)
        f9 = lambda: max(int(10 * sc), 10)
        f11 = lambda: max(int(12 * sc), 12)

        # ── 区域选择 ──
        region_frame = tk.Frame(dlg, bg=TK["bg"])
        region_frame.pack(fill=tk.X, padx=20, pady=(18, 0))
        tk.Label(region_frame, text="服务器区域：", font=(FONT_FAMILY, f9()),
                 fg=TK["fg"], bg=TK["bg"]).pack(side=tk.LEFT)
        region_var = tk.StringVar(value="cn")
        regions = [("🇨🇳 cn (中国)", "cn"), ("🇩🇪 de (德国)", "de"),
                   ("🇺🇸 us (美国)", "us"), ("🇷🇺 ru (俄罗斯)", "ru"),
                   ("🇸🇬 sg (新加坡)", "sg"), ("🇹🇼 tw (台湾)", "tw"),
                   ("🇮🇳 in (印度)", "in"), ("🇯🇵 i2 (日本)", "i2")]
        region_menu = ttk.Combobox(region_frame, textvariable=region_var,
                                   values=[r[0] for r in regions],
                                   width=22, state="readonly",
                                   font=(FONT_FAMILY, 9))
        region_menu.pack(side=tk.LEFT, padx=(4, 0))

        # ── 状态标签 ──
        status_var = tk.StringVar(value="请选择登录方式")
        status_lbl = tk.Label(dlg, textvariable=status_var,
                              font=(FONT_FAMILY, 8), fg=TK["dim"], bg=TK["bg"])
        status_lbl.pack(pady=(6, 0))

        # ══════════════════════════════════════════════
        #  验证码 / 2FA 回调
        # ══════════════════════════════════════════════
        def _show_captcha(img_bytes: bytes) -> str:
            result = [""]
            ev = threading.Event()
            captcha_win = None
            def _cleanup_and_release(code_value: str):
                nonlocal captcha_win
                result[0] = code_value
                ev.set()
                if captcha_win is not None:
                    try:
                        captcha_win.destroy()
                    except Exception:
                        pass
            def _show():
                nonlocal captcha_win
                captcha_win = tk.Toplevel(dlg)
                captcha_win.title("验证码"); captcha_win.geometry("320x280")
                captcha_win.resizable(False, False); captcha_win.transient(dlg); captcha_win.grab_set()
                captcha_win.configure(bg=TK["bg"])
                import tempfile; from PIL import Image, ImageTk
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                tmp.write(img_bytes); tmp.close()
                img = Image.open(tmp.name); img.thumbnail((280, 120), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(captcha_win, image=photo, bg=TK["bg"]); lbl.image = photo; lbl.pack(pady=10)
                tk.Label(captcha_win, text="请输入验证码（区分大小写）", font=(FONT_FAMILY, 9),
                         fg=TK["fg"], bg=TK["bg"]).pack()
                cv = tk.StringVar()
                tk.Entry(captcha_win, textvariable=cv, width=20, font=(FONT_FAMILY, 10),
                         bg=TK["card_light"], fg=TK["fg"], relief=tk.FLAT, bd=0).pack(pady=8)
                def _cf():
                    _cleanup_and_release(cv.get().strip())
                tk.Button(captcha_win, text="确认", font=(FONT_FAMILY, 9, "bold"),
                          bg=TK["card"], fg=TK["green"],
                          activebackground=TK["card_light"],
                          relief=tk.FLAT, bd=0, cursor="hand2",
                          padx=14, pady=2, command=_cf).pack()
                captcha_win.bind("<Return>", lambda e: _cf())
                captcha_win.protocol("WM_DELETE_WINDOW", lambda: _cleanup_and_release(""))
            dlg.after(0, _show)
            if not ev.wait(timeout=300):
                logger.warning("验证码输入超时（5分钟），自动熔断")
                dlg.after(0, lambda: _cleanup_and_release(""))
            return result[0]

        def _ask_2fa() -> str:
            result = [""]; ev = threading.Event()
            twofa_win = None
            def _cleanup_and_release(code_value: str):
                nonlocal twofa_win
                result[0] = code_value
                ev.set()
                if twofa_win is not None:
                    try:
                        twofa_win.destroy()
                    except Exception:
                        pass
            def _ask():
                nonlocal twofa_win
                twofa_win = tk.Toplevel(dlg)
                twofa_win.title("两步验证"); twofa_win.geometry("320x150")
                twofa_win.resizable(False, False); twofa_win.transient(dlg); twofa_win.grab_set()
                twofa_win.configure(bg=TK["bg"])
                tk.Label(twofa_win, text="📧 验证码已发送到邮箱", font=(FONT_FAMILY, 10, "bold"),
                         fg=TK["blue"], bg=TK["bg"]).pack(pady=(12, 2))
                tk.Label(twofa_win, text="请输入邮件中的验证码", font=(FONT_FAMILY, 9),
                         fg=TK["fg"], bg=TK["bg"]).pack(pady=(0, 8))
                cv = tk.StringVar()
                tk.Entry(twofa_win, textvariable=cv, width=16, font=(FONT_FAMILY, 14),
                         bg=TK["card_light"], fg=TK["fg"],
                         relief=tk.FLAT, bd=0, justify=tk.CENTER).pack()
                def _cf():
                    _cleanup_and_release(cv.get().strip())
                tk.Button(twofa_win, text="确认", font=(FONT_FAMILY, 9, "bold"),
                          bg=TK["card"], fg=TK["green"],
                          activebackground=TK["card_light"],
                          relief=tk.FLAT, bd=0, cursor="hand2",
                          padx=14, pady=2, command=_cf).pack(pady=10)
                twofa_win.bind("<Return>", lambda e: _cf())
                twofa_win.protocol("WM_DELETE_WINDOW", lambda: _cleanup_and_release(""))
            dlg.after(0, _ask)
            if not ev.wait(timeout=300):
                logger.warning("2FA 输入超时（5分钟），自动熔断")
                dlg.after(0, lambda: _cleanup_and_release(""))
            return result[0]

        def _set_status(msg, color=None):
            dlg.after(0, lambda: status_var.set(msg))
            if color:
                dlg.after(0, lambda: status_lbl.config(fg=color))

        # ══════════════════════════════════════════════
        #  方式一：二维码登录
        # ══════════════════════════════════════════════
        qr_frame = tk.Frame(dlg, bg=TK["bg"])
        qr_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(8, 4))

        tk.Label(qr_frame, text="📱 方式一：扫描二维码登录（推荐）",
                 font=(FONT_FAMILY, f11(), "bold"), fg=TK["green"], bg=TK["bg"]
                 ).pack(anchor=tk.W)

        # 二维码显示区域
        qr_image_label = tk.Label(qr_frame, text="点击下方按钮获取二维码",
                                  font=(FONT_FAMILY, f9()), fg=TK["dim"], bg=TK["card"],
                                  relief=tk.SUNKEN, bd=0, height=6)
        qr_image_label.pack(fill=tk.X, pady=(3, 3))

        def _start_qrcode():
            region = region_var.get()
            # 从 "🇨🇳 cn (中国)" 提取 "cn"
            region_code = region.split()[1] if " " in region else region

            from micloud_helper import XiaomiCloudConnector
            connector = XiaomiCloudConnector()

            def _show_qr(img_bytes: bytes, login_url: str):
                try:
                    from PIL import Image, ImageTk
                    import tempfile
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                    tmp.write(img_bytes); tmp.close()
                    img = Image.open(tmp.name)
                    img.thumbnail((200, 200), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    # ✅ 通过 after(0) 切回主线程更新 UI
                    def _update_ui(p=photo):
                        qr_image_label.config(image=p, text="", height=200,
                                              relief=tk.FLAT, bg=TK["bg"])
                        qr_image_label.image = p
                        qr_btn.config(state=tk.NORMAL, text="🔄 刷新二维码")
                    dlg.after(0, _update_ui)
                except Exception as e:
                    _set_status(f"❌ 显示二维码失败: {e}", TK["red"])

            def _status(msg):
                _set_status(msg, TK["orange"])
                if "成功" in msg:
                    _set_status(msg, TK["green"])
                    # 获取设备
                    connector.fetch_devices_by_region(
                        region_code,
                        status_cb=lambda m: _set_status(
                            m, TK["green"] if "✅" in m else TK["orange"]),
                        result_cb=lambda devices: dlg.after(
                            0, lambda: self._show_cloud_results(devices, dlg))
                    )

            def _do_qr():
                # ✅ 通过 after(0) 切回主线程更新按钮状态
                dlg.after(0, lambda: qr_btn.config(state=tk.DISABLED, text="⏳ 获取中..."))
                connector.login_qrcode(
                    qrcode_callback=_show_qr,
                    status_callback=_status
                )

            import threading
            threading.Thread(target=_do_qr, daemon=True).start()

        qr_btn = tk.Button(qr_frame, text="📱 获取二维码", font=(FONT_FAMILY, f9()),
                           bg=TK["card_light"], fg=TK["green"],
                           activebackground=TK["border"],
                           relief=tk.FLAT, bd=0, cursor="hand2",
                           padx=14, pady=5, command=_start_qrcode)
        qr_btn.pack()

        # ── 分隔 ──
        tk.Label(dlg, text="━━━━ 或 ━━━━",
                 font=(FONT_FAMILY, f9()), fg=TK["dim"], bg=TK["bg"]
                 ).pack(pady=(6, 4))

        # ══════════════════════════════════════════════
        #  方式二：密码登录
        # ══════════════════════════════════════════════
        pw_frame = tk.Frame(dlg, bg=TK["bg"])
        pw_frame.pack(fill=tk.X, padx=20)

        tk.Label(pw_frame, text="🔑 方式二：账号密码登录",
                 font=(FONT_FAMILY, f11(), "bold"), fg=TK["blue"], bg=TK["bg"]
                 ).pack(anchor=tk.W)

        # 用户名
        uf = tk.Frame(pw_frame, bg=TK["bg"])
        uf.pack(fill=tk.X, pady=(6, 3))
        tk.Label(uf, text="账号", width=10, anchor=tk.W,
                 font=(FONT_FAMILY, f9()),
                 fg=TK["fg"], bg=TK["bg"]).pack(side=tk.LEFT)
        user_var = tk.StringVar()
        tk.Entry(uf, textvariable=user_var, width=30,
                 font=(FONT_FAMILY, f9()),
                 bg=TK["card_light"], fg=TK["fg"],
                 relief=tk.FLAT, bd=0).pack(side=tk.LEFT)

        # 密码
        pf = tk.Frame(pw_frame, bg=TK["bg"])
        pf.pack(fill=tk.X, pady=3)
        tk.Label(pf, text="密码", width=10, anchor=tk.W,
                 font=(FONT_FAMILY, f9()),
                 fg=TK["fg"], bg=TK["bg"]).pack(side=tk.LEFT)
        pass_var = tk.StringVar()
        tk.Entry(pf, textvariable=pass_var, width=30, show="*",
                 font=(FONT_FAMILY, f9()),
                 bg=TK["card_light"], fg=TK["fg"],
                 relief=tk.FLAT, bd=0).pack(side=tk.LEFT)

        def _do_password_login():
            username = user_var.get().strip()
            password = pass_var.get()
            if not username or not password:
                status_var.set("⚠ 请输入账号和密码"); status_lbl.config(fg=TK["red"])
                return

            region = region_var.get()
            region_code = region.split()[1] if " " in region else region

            status_var.set("⏳ 正在登录..."); status_lbl.config(fg=TK["orange"])
            pw_btn.config(state=tk.DISABLED)

            def _fetch():
                try:
                    from micloud_helper import XiaomiCloudConnector
                    connector = XiaomiCloudConnector()
                    ok = connector.login(username, password, _show_captcha, _ask_2fa,
                                         lambda m: dlg.after(0, lambda: (
                                             status_var.set(m),
                                             status_lbl.config(
                                                 fg=TK["green"] if "✅" in m else
                                                 TK["red"] if "❌" in m else
                                                 TK["orange"]))))
                    if ok:
                        connector.fetch_devices_by_region(
                            region_code,
                            status_cb=lambda m: dlg.after(0, lambda: (
                                status_var.set(m), status_lbl.config(
                                    fg=TK["green"] if "✅" in m else TK["orange"]))),
                            result_cb=lambda devices: dlg.after(
                                0, lambda: self._show_cloud_results(devices, dlg))
                        )
                    else:
                        dlg.after(0, lambda: pw_btn.config(state=tk.NORMAL))
                except Exception as e:
                    dlg.after(0, lambda: status_var.set(f"❌ 错误: {e}"))
                    dlg.after(0, lambda: status_lbl.config(fg=TK["red"]))
                    dlg.after(0, lambda: pw_btn.config(state=tk.NORMAL))

            import threading
            threading.Thread(target=_fetch, daemon=True).start()

        pw_btn = tk.Button(pw_frame, text="🔑 登录并获取", font=(FONT_FAMILY, f11(), "bold"),
                           bg=TK["card"], fg=TK["blue"],
                           activebackground=TK["card_light"],
                           relief=tk.FLAT, bd=0, cursor="hand2",
                           padx=18, pady=4, command=_do_password_login)
        pw_btn.pack(pady=(6, 0))

        # 取消按钮
        tk.Button(dlg, text="取消", font=(FONT_FAMILY, f9()),
                  bg=TK["card"], fg=TK["dim"],
                  activebackground=TK["card_light"],
                  relief=tk.FLAT, bd=0, cursor="hand2",
                  padx=18, pady=4, command=dlg.destroy
                  ).pack(pady=(8, 0))

        dlg.bind("<Escape>", lambda e: dlg.destroy())

    def _show_cloud_results(self, cloud_devices, login_dlg):
        """显示云端获取到的设备列表"""
        login_dlg.destroy()

        if not cloud_devices:
            messagebox.showwarning("云端结果",
                                   "云端未找到设备（带IP和Token）。\n\n"
                                   "请确认：\n"
                                   "1. 小米账号已绑定米家设备\n"
                                   "2. 设备已在线\n"
                                   "3. 使用正确的区域（中国大陆用户选cn）",
                                   parent=self.window)
            return

        # 显示结果到扫描结果区域
        self._device_list_label.config(
            text=f"☁️ 云端获取到 {len(cloud_devices)} 个设备，点击自动填入：",
            fg=TK["blue"])

        self._discover_frame.pack(fill=tk.X, pady=(4, 0))
        for w in self._discover_frame.winfo_children():
            w.destroy()

        sc = self.scale
        fs2 = lambda pt: max(int(pt * sc), pt)

        for dev in cloud_devices:
            ip = dev.get("ip", "?")
            name = dev.get("name", dev.get("model", "未知"))
            model = dev.get("model", "")
            label = f"  ☁️ {name}  ({ip})"
            if model and model != name:
                label += f"  [{model}]"

            dev_btn = tk.Button(
                self._discover_frame,
                text=label,
                font=(FONT_FAMILY, fs2(9)),
                bg=TK["card_light"], fg=TK["blue"],
                activebackground=TK["border"],
                relief=tk.FLAT, bd=0, cursor="hand2",
                anchor=tk.W,
                command=lambda d=dev: self._pick_device(d, None, sc),
            )
            dev_btn.pack(fill=tk.X, pady=int(1 * sc))



    def _pick_device(self, dev, card, sc):
        """选择发现的设备，填入IP和Token"""
        ip = dev.get("ip", "")
        token = dev.get("token", "")
        name = dev.get("name", "") or dev.get("model", "设备")

        # 检查 token 是否有效（新版设备UDP返回全ff，不可用）
        token_invalid = token in ("", "f" * 32, "0" * 32)

        if ip:
            self.ip_var.set(ip)

        if token and not token_invalid:
            self.token_var.set(token)
            self._device_list_label.config(
                text=f"✅ 已选择 {name}，IP和Token已自动填入，点击保存",
                fg=TK["green"])
            messagebox.showinfo(
                "选择成功",
                f"已选择: {name}\nIP: {ip}\nToken: {'已自动获取' if token else '未获取'}\n\n"
                f"{'点击下方「保存」即可使用。' if token else '请手动输入Token后再保存。'}"
            )
        elif token_invalid and token:
            # UDP扫描拿到的是无效token（全ff）
            self.token_var.set("")
            self._device_list_label.config(
                text=f"⚠ {name} 的 Token 不可用（UDP返回占位符），请用☁️云端获取",
                fg=TK["red"])
            messagebox.showwarning(
                "Token 不可用",
                f"设备 {name}({ip}) 的 Token 为无效占位符。\n\n"
                f"新版米家设备不支持通过局域网扫描获取 Token。\n\n"
                f"请使用「☁️ 云端获取 Token」按钮，\n"
                f"用小米账号登录后自动获取真实 Token。",
                parent=self.window)
        else:
            self._device_list_label.config(
                text=f"✅ 已选择 {ip}，Token未获取到，请手动输入或使用☁️云端获取",
                fg=TK["orange"])
        self.token_ent.config(show="" if self._show_token else "*")

    def _save(self):
        """保存设置并应用到控制器"""
        try:
            high = self.high_var.get()
            low = self.low_var.get()
            interval = self.interval_var.get()
            ip = self.ip_var.get().strip()
            token = self.token_var.get().strip()

            # 阈值验证
            if low >= high:
                messagebox.showerror("参数错误",
                                     "低阈值必须小于高阈值\n请调整后重试",
                                     parent=self.window)
                return
            if not (0 <= low < high <= 100):
                messagebox.showerror("参数错误",
                                     "阈值必须在 0-100 范围内",
                                     parent=self.window)
                return

            # IP 格式验证（如果填写了IP）
            if ip and token:
                import re
                if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                    messagebox.showerror("参数错误",
                                         "IP 地址格式不正确",
                                         parent=self.window)
                    return
                if not re.match(r'^[0-9a-fA-F]{32}$', token):
                    messagebox.showerror("参数错误",
                                         "Token 必须是32位十六进制字符",
                                         parent=self.window)
                    return

            # 热更新控制器参数
            self.controller.set_thresholds(high_threshold=high,
                                           low_threshold=low)
            with self.controller._lock:
                self.controller.check_interval = interval
            if ip and token:
                self.controller.mihome_controller.configure(ip, token)

            # 开机自启
            autostart = self._autostart_var.get() if hasattr(self, '_autostart_var') else False
            if autostart != self.config.get("autostart", False):
                try:
                    from config import set_autostart
                    set_autostart(autostart)
                except Exception:
                    pass

            # 保存到配置
            self.config.set("thresholds.high", high)
            self.config.set("thresholds.low", low)
            self.config.set("check_interval", interval)
            self.config.set("mihome.ip", ip)
            self.config.set("mihome.token", token)
            self.config.set("autostart", autostart)
            self.config.save()

            logger.info(f"设置已保存: 高={high}%, 低={low}%, 间隔={interval}s")

            # 触发回调
            if self.on_save:
                self.on_save()

            # 如果配置了设备，关闭窗口后测试连接（通过主窗口回调）
            if ip and token and hasattr(self.parent, 'after'):
                self.window.destroy()
                self._test_connection_and_notify()
                return

            self.window.destroy()
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            messagebox.showerror("保存失败", f"保存设置时出错:\n{e}",
                                 parent=self.window)

    def _test_connection_and_notify(self):
        """后台测试设备连接，通过主窗口显示结果"""
        mh = self.controller.mihome_controller
        parent = self.parent

        def _do_test():
            try:
                from miio import Device
                test_dev = Device(ip=mh.ip, token=mh.token, timeout=5)
                info = test_dev.send("miIO.info", [])
                model = info.get("model", "未知") if isinstance(info, dict) else "未知"
                parent.after(0, lambda: messagebox.showinfo(
                    "✅ 连接成功",
                    f"设备连接成功！\nIP: {mh.ip}\n型号: {model}\n\n监控将自动开始。",
                ))
            except Exception as e:
                parent.after(0, lambda e=e: messagebox.showwarning(
                    "⚠ 连接测试",
                    f"保存成功，但连接测试未通过:\n{e}\n\n"
                    f"可能原因：\n"
                    f"1. Token 不正确（UDP 获取的 Token 可能被加密）\n"
                    f"2. 设备不在线或网络不通\n"
                    f"3. 防火墙阻止了通信\n\n"
                    f"建议：尝试使用「提取 Token 帮助」获取正确 Token。\n"
                    f"监控仍会在后台自动尝试连接。",
                ))

        import threading
        threading.Thread(target=_do_test, daemon=True).start()


class BatteryMonitorGUI:
    """电池监控主窗口 - 高DPI玻璃质感设计"""

    def __init__(self, controller, config):
        if not TKINTER_AVAILABLE:
            raise RuntimeError("tkinter 不可用")
        _enable_dpi_aware()

        self.controller = controller
        self.config = config
        self.settings_window: Optional[SettingsWindow] = None
        self._running = True
        self._timer: Optional[str] = None
        self._tray_icon: Optional[pystray.Icon] = None
        self._tray_thread: Optional[threading.Thread] = None
        # 全局单线程池，整个程序生命周期只创建1个线程
        self._refresh_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="status_refresh")
        # 用于追踪当前正在执行的后台异步任务句柄
        self._current_refresh_future: Optional[any] = None
        # GUI 内部生命周期状态闸
        self._is_exiting = False
        self._exit_lock = threading.Lock()
        self._build()
        self._setup_tray()

    def _build(self):
        # ── 创建根窗口 ──
        root = tk.Tk()
        root.title("🔋 电池监控 · Battery Limit")
        root.resizable(False, False)
        root.configure(bg=TK["bg"])

        # 设置图标
        icon = _icon_path()
        if icon:
            try:
                root.iconbitmap(default=icon)
            except Exception:
                pass

        # 半透明
        try:
            root.attributes("-alpha", 0.93)
        except Exception:
            pass

        # ── DPI缩放 ──
        scale = _get_dpi_scale(root)
        root.tk.call("tk", "scaling", scale)
        _style(scale)
        self._scale = scale

        # ── 窗口尺寸并居中到屏幕 ──
        W, H = int(520 * scale), int(480 * scale)
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = max(0, (sw - W) // 2)
        y = max(0, (sh - H) // 2)
        root.geometry(f"{W}x{H}+{x}+{y}")
        root.protocol("WM_DELETE_WINDOW", self._close)
        self.root = root

        # 注入UI错误回调
        def _ui_error(message):
            def _show():
                messagebox.showerror("致命错误", message)
                root.quit()
            root.after(0, _show)
        self.controller.ui_error_callback = _ui_error

        # ── 布局 ──
        sc = scale
        self._sc = sc
        fs = lambda pt: max(int(pt * sc), pt)
        pd = lambda n: int(n * sc)

        mf = tk.Frame(root, bg=TK["bg"])
        mf.pack(fill=tk.BOTH, expand=True, padx=pd(16), pady=pd(14))

        # ══ 标题行：标题 + 运行状态 ══
        tr = tk.Frame(mf, bg=TK["bg"])
        tr.pack(fill=tk.X)

        tk.Label(tr, text="🔋 电池限制管理",
                 font=(FONT_FAMILY, fs(15), "bold"),
                 fg=TK["fg"], bg=TK["bg"]).pack(side=tk.LEFT)

        # 状态指示灯 + 运行时长
        df = tk.Frame(tr, bg=TK["bg"])
        df.pack(side=tk.RIGHT)
        dot_s = pd(16)
        st_frame = tk.Frame(df, bg=TK["bg"])
        st_frame.pack(side=tk.RIGHT)
        self._glow = tk.Canvas(st_frame, width=dot_s + pd(4), height=dot_s + pd(4),
                               highlightthickness=0, bd=0, bg=TK["bg"])
        self._glow.pack(side=tk.LEFT)
        gl = pd(2)
        self._glow.create_oval(gl, gl, dot_s + gl, dot_s + gl, fill="", outline="")
        self._dot_id = self._glow.create_oval(pd(4), pd(4), dot_s - pd(4), dot_s - pd(4),
                                               fill=TK["green"], outline="")
        self._uptime_lbl = tk.Label(st_frame, text="运行中",
                                     font=(FONT_FAMILY, fs(8)), fg=TK["dim"], bg=TK["bg"])
        self._uptime_lbl.pack(side=tk.LEFT, padx=(pd(3), 0))
        self._start_time = time.time()

        # ══ 电池状态卡片（主卡片） ══
        card = _glass_frame(mf, padx=pd(16), pady=pd(12))
        card.pack(fill=tk.X, pady=(pd(10), pd(6)))

        self.pct = tk.Label(card, text="--%",
                            font=(FONT_FAMILY, fs(36), "bold"),
                            fg=TK["green"], bg=TK["card"])
        self.pct.pack(pady=(pd(4), pd(2)))

        self.bar = ttk.Progressbar(card, length=int(420 * sc), mode="determinate")
        self.bar.pack(pady=(pd(6), pd(6)))

        self.chg = tk.Label(card, text="⏳ 正在获取...",
                            font=(FONT_FAMILY, fs(10)),
                            fg=TK["dim"], bg=TK["card"])
        self.chg.pack(pady=(0, pd(2)))

        # ══ 阈值区间可视化进度条 ══
        self._threshold_cv = tk.Canvas(mf, height=pd(28), bg=TK["bg"],
                                       highlightthickness=0, bd=0)
        self._threshold_cv.pack(fill=tk.X, pady=(pd(2), pd(4)))

        # ══ 状态卡片行（三列） ══
        cards_row = tk.Frame(mf, bg=TK["bg"])
        cards_row.pack(fill=tk.X, pady=(pd(2), pd(4)))

        # 开关状态卡片
        sw_card = _glass_frame(cards_row, padx=pd(8), pady=pd(6))
        sw_card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, pd(4)))
        tk.Label(sw_card, text="🔌 米家开关", font=(FONT_FAMILY, fs(8)),
                 fg=TK["dim"], bg=TK["card"]).pack()
        self.sw = tk.Label(sw_card, text="❓ 未知",
                           font=(FONT_FAMILY, fs(11), "bold"),
                           fg=TK["dim"], bg=TK["card"])
        self.sw.pack(pady=(pd(2), 0))
        self._sw_detail = tk.Label(sw_card, text="", font=(FONT_FAMILY, fs(7)),
                                   fg=TK["dim"], bg=TK["card"])
        self._sw_detail.pack()

        # 检查间隔卡片
        int_card = _glass_frame(cards_row, padx=pd(8), pady=pd(6))
        int_card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(pd(4), 0))
        tk.Label(int_card, text="⏱ 检查间隔", font=(FONT_FAMILY, fs(8)),
                 fg=TK["dim"], bg=TK["card"]).pack()
        self._int_lbl = tk.Label(int_card, text="--s",
                                 font=(FONT_FAMILY, fs(11), "bold"),
                                 fg=TK["fg"], bg=TK["card"])
        self._int_lbl.pack(pady=(pd(2), 0))
        tk.Label(int_card, text=" ", font=(FONT_FAMILY, fs(7)),
                 fg=TK["dim"], bg=TK["card"]).pack()

        # ══ 快捷操作按钮行 ══
        action_row = tk.Frame(mf, bg=TK["bg"])
        action_row.pack(fill=tk.X, pady=(pd(6), pd(4)))

        self._on_btn = tk.Button(action_row, text="⚡ 开启充电",
                                 font=(FONT_FAMILY, fs(9), "bold"),
                                 bg="#2d6a4f", fg=TK["fg"],
                                 activebackground="#40916c",
                                 relief=tk.FLAT, bd=0, cursor="hand2",
                                 padx=pd(10), pady=pd(5),
                                 command=self._switch_on)
        self._on_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, pd(3)))

        self._off_btn = tk.Button(action_row, text="⏹ 停止充电",
                                  font=(FONT_FAMILY, fs(9), "bold"),
                                  bg="#6b2d2d", fg=TK["fg"],
                                  activebackground="#8f3e3e",
                                  relief=tk.FLAT, bd=0, cursor="hand2",
                                  padx=pd(10), pady=pd(5),
                                  command=self._switch_off)
        self._off_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(pd(3), 0))

        # ══ 提示条（异常/状态信息，默认隐藏） ══
        self._notice_bar = tk.Frame(mf, bg=TK["card"], height=pd(26))
        self._notice_lbl = tk.Label(self._notice_bar, text="", font=(FONT_FAMILY, fs(8)),
                                    fg=TK["orange"], bg=TK["card"], anchor=tk.W)
        self._notice_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=pd(8))
        self._notice_btn = tk.Button(self._notice_bar, text="", font=(FONT_FAMILY, fs(7)),
                                     bg=TK["card"], fg=TK["blue"],
                                     relief=tk.FLAT, bd=0, cursor="hand2",
                                     padx=pd(4), pady=pd(1))
        self._notice_btn.pack(side=tk.RIGHT, padx=pd(4))
        # 默认隐藏（由 _show_notice / _hide_notice 控制）

        # ══ 底部按钮行 ══
        br = tk.Frame(mf, bg=TK["bg"])
        br.pack(fill=tk.X, pady=(pd(6), 0))

        tk.Button(br, text="⚙ 设置", font=(FONT_FAMILY, fs(9)),
                  bg=TK["card"], fg=TK["fg"],
                  activebackground=TK["card_light"],
                  relief=tk.FLAT, bd=0,
                  padx=pd(14), pady=pd(4), cursor="hand2",
                  command=self._settings).pack(side=tk.LEFT, padx=pd(4))

        tk.Button(br, text="🔄 刷新", font=(FONT_FAMILY, fs(9)),
                  bg=TK["card"], fg=TK["fg"],
                  activebackground=TK["card_light"],
                  relief=tk.FLAT, bd=0,
                  padx=pd(14), pady=pd(4), cursor="hand2",
                  command=self._refresh).pack(side=tk.RIGHT)

        # ══ 底部统计 ══
        self.foot = tk.Label(mf,
                             text="阈值: ↑--% ↓--%  间隔: --s",
                             font=(FONT_FAMILY, fs(8)),
                             fg=TK["dim"], bg=TK["bg"], anchor=tk.W)
        self.foot.pack(fill=tk.X, pady=(pd(6), 0))

        root.after(800, self._first_update)

    # ──────── 更新 ────────

    def _first_update(self):
        self._trigger_async_refresh()
        self._tick()

    def _tick(self):
        if self._running:
            self._trigger_async_refresh()
            self._timer = self.root.after(2000, self._tick)

    def _trigger_async_refresh(self):
        """线程安全的异步数据刷新触发器"""
        with self._exit_lock:
            if self._is_exiting:
                return

        if self._current_refresh_future and not self._current_refresh_future.done():
            return

        self._current_refresh_future = self._refresh_executor.submit(self._bg_refresh_task)

    def _bg_refresh_task(self):
        """在 ThreadPoolExecutor 中运行的后台耗时任务"""
        with self._exit_lock:
            if self._is_exiting:
                return

        try:
            bm = self.controller.battery_manager
            mh = self.controller.mihome_controller

            st = bm.get_battery_status()
            pct = st.get("percent", 0)
            plugged = st.get("power_plugged")

            on = None
            if mh.available:
                try:
                    on = mh.is_on()
                except Exception:
                    pass

            with self._exit_lock:
                if self._is_exiting:
                    return

            self.root.after(0, lambda: self._apply_status(pct, plugged, on))
        except Exception as e:
            logger.error(f"刷新状态失败: {e}")

    def _apply_status(self, pct: float, plugged: Optional[bool], on: Optional[bool]):
        """（主线程执行）安全地将快照更新到 Tkinter 变量中"""
        with self._exit_lock:
            if self._is_exiting:
                return

        # 更新运行时长
        elapsed = int(time.time() - self._start_time)
        hours, rem = divmod(elapsed, 3600)
        mins = rem // 60
        if hours > 0:
            self._uptime_lbl.config(text=f"运行 {hours}h{mins}m")
        else:
            self._uptime_lbl.config(text=f"运行 {mins}m")

        has_battery = self.controller.battery_manager.has_battery

        # 无电池时显示台式机降级模式
        if not has_battery:
            self.pct.config(text="🖥️ 台式机模式", fg=TK["dim"])
            self.bar["value"] = 0
            try:
                s = ttk.Style()
                s.configure("Horizontal.TProgressbar",
                            background=TK["dim"], thickness=int(14 * self._scale))
            except Exception:
                pass
            self.chg.config(text="无物理电池，自动阈值已禁用", fg=TK["dim"])
        else:
            # 电池百分比（取整显示）
            pct_int = int(round(pct))
            self.pct.config(text=f"{pct_int}%")
            self.bar["value"] = pct

            color = TK["green"]
            if pct <= 20:
                color = TK["red"]
            elif pct <= 40:
                color = TK["orange"]
            elif pct >= 80:
                color = TK["blue"]
            self.pct.config(fg=color)
            try:
                s = ttk.Style()
                s.configure("Horizontal.TProgressbar",
                            background=color, thickness=int(14 * self._scale))
            except Exception:
                pass

            self.chg.config(
                text="⚡ 充电中" if plugged is True
                else "🔋 电池供电" if plugged is False
                else "❓ 未知",
                fg=TK["green"] if plugged is True
                else TK["orange"] if plugged is False
                else TK["dim"]
            )

        # 米家开关状态
        mh = self.controller.mihome_controller
        if on is True:
            text, fg = "✅ 已开启", TK["green"]
            detail = f"已连接 ({mh.ip})" if mh.ip else ""
        elif on is False:
            text, fg = "⛔ 已关闭", TK["red"]
            detail = f"已连接 ({mh.ip})" if mh.ip else ""
        elif on is None and not mh.available:
            text, fg = "⚠ 未配置", TK["dim"]
            detail = "请进入设置配置设备"
        elif on is None and not mh.is_connected:
            text, fg = "⚠ 连接中...", TK["orange"]
            detail = ""
        else:
            text, fg = "⚠ 离线", TK["orange"]
            detail = ""
        self.sw.config(text=text, fg=fg)
        self._sw_detail.config(text=detail)

        # 检查间隔
        interval = self.controller.check_interval
        self._int_lbl.config(text=f"{interval}s")

        # 阈值区间进度条
        self._draw_threshold_bar()

        # 运行状态指示灯
        if has_battery and self.controller.is_running:
            self._glow.itemconfig(self._dot_id, fill=TK["green"])
        elif not mh.available:
            self._glow.itemconfig(self._dot_id, fill=TK["red"])
        else:
            self._glow.itemconfig(self._dot_id, fill=TK["orange"])

        # 提示条：连接异常时显示
        if not mh.available:
            self._show_notice("⚠ 米家设备未配置，请在设置中配置设备IP和Token", "⚙ 设置", self._settings)
        elif on is None and mh.ip:
            cooldown_active = hasattr(mh, '_get_current_cooldown') and mh._get_current_cooldown() > 0
            if cooldown_active:
                self._show_notice("⚠ 连接冷却中，将在冷却后自动重试", "🔄 立即重试", self._refresh, TK["orange"])
            else:
                self._show_notice("⚠ 正在连接设备...", "", fg=TK["orange"])
        else:
            self._hide_notice()

        # 底部统计
        hi = self.controller.high_threshold
        lo = self.controller.low_threshold
        self.foot.config(
            text=f"阈值: ↑{hi:.0f}% ↓{lo:.0f}%  |  间隔: {interval}s"
        )

    def _draw_threshold_bar(self):
        """绘制阈值区间可视化进度条"""
        hi = self.controller.high_threshold
        lo = self.controller.low_threshold
        sc = self._scale
        w = int(480 * sc)
        h = pd = int(26 * sc)
        cv = self._threshold_cv
        cv.delete("all")
        cv.config(width=w, height=h)

        y_mid = h // 2
        bar_h = max(4, int(6 * sc))

        # 背景条
        cv.create_rectangle(pd//2, y_mid - bar_h//2, w - pd//2, y_mid + bar_h//2,
                            fill=TK["card"], width=0)

        # 低阈值标记（橙色圆点 + 标签）
        x1 = pd//2 + (w - pd) * lo / 100.0
        r = max(5, int(6 * sc))
        cv.create_oval(x1 - r, y_mid - r, x1 + r, y_mid + r,
                       fill=TK["orange"], width=0)
        cv.create_text(x1, h - 2, text=f"{lo:.0f}% 开始充电",
                       fill=TK["orange"], font=(FONT_FAMILY, max(7, int(8 * sc))), anchor=tk.S)

        # 高阈值标记（绿色圆点 + 标签）
        x2 = pd//2 + (w - pd) * hi / 100.0
        cv.create_oval(x2 - r, y_mid - r, x2 + r, y_mid + r,
                       fill=TK["green"], width=0)
        cv.create_text(x2, 2, text=f"停止充电 {hi:.0f}%",
                       fill=TK["green"], font=(FONT_FAMILY, max(7, int(8 * sc))), anchor=tk.N)

    def _show_notice(self, text: str, btn_text: str = "", btn_cmd=None, fg: str = ""):
        """显示底部提示条"""
        fg = fg or TK["orange"]
        sc = self._sc
        pd = lambda n: int(n * sc)
        self._notice_lbl.config(text=text, fg=fg)
        if btn_text and btn_cmd:
            self._notice_btn.config(text=btn_text, command=btn_cmd)
            self._notice_btn.pack(side=tk.RIGHT, padx=pd(4))
        else:
            self._notice_btn.pack_forget()
        self._notice_bar.pack(fill=tk.X, pady=(pd(4), 0))

    def _hide_notice(self):
        """隐藏底部提示条"""
        self._notice_bar.pack_forget()

    def _notify(self, title: str, msg: str):
        try:
            if self._tray_icon:
                self._tray_icon.notify(title, msg)
        except Exception:
            pass

    def _switch_on(self):
        def _do():
            mh = self.controller.mihome_controller
            mh.reset_cooldown()
            self.sw.config(text="⏳ 正在开启...", fg=TK["green"])
            if mh.turn_on(force=True):
                self.root.after(0, lambda: self.sw.config(
                    text="✅ 已开启", fg=TK["green"]))
            else:
                self.root.after(0, lambda: self.sw.config(
                    text="❌ 开启失败", fg=TK["red"]))
                self.root.after(0, lambda: self._notify("控制失败", "无法开启设备"))
        threading.Thread(target=_do, daemon=True).start()

    def _switch_off(self):
        def _do():
            mh = self.controller.mihome_controller
            mh.reset_cooldown()
            self.sw.config(text="⏳ 正在关闭...", fg=TK["red"])
            if mh.turn_off(force=True):
                self.root.after(0, lambda: self.sw.config(
                    text="⛔ 已关闭", fg=TK["red"]))
            else:
                self.root.after(0, lambda: self.sw.config(
                    text="❌ 关闭失败", fg=TK["orange"]))
                self.root.after(0, lambda: self._notify("控制失败", "无法关闭设备"))
        threading.Thread(target=_do, daemon=True).start()

    # ──────── 操作 ────────

    def _refresh(self):
        self.controller.mihome_controller.reset_cooldown()
        self._trigger_async_refresh()

    def _settings(self):
        if (self.settings_window and self.settings_window.window
                and self.settings_window.window.winfo_exists()):
            self.settings_window.window.lift()
            return
        self.settings_window = SettingsWindow(
            parent=self.root, config=self.config, controller=self.controller,
            on_save=self._refresh, scale=self._scale,
        )

    def _hide_window(self):
        """最小化到系统托盘"""
        if self._tray_icon is None:
            self.root.iconify()
            return
        try:
            self.root.withdraw()
            self._tray_icon.visible = True
        except Exception as e:
            logger.error(f"隐藏到托盘失败: {e}")
            self.root.iconify()

    def _show_window(self, icon=None, item=None):
        """从托盘恢复窗口"""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception as e:
            logger.error(f"恢复窗口失败: {e}")

    def _close(self):
        """关闭窗口 -> 最小化到托盘"""
        if self._tray_icon is not None:
            self._hide_window()
        else:
            self._really_quit()

    def _really_quit(self, icon=None, item=None):
        """最高安全级别的优雅关机序列"""
        logger.info("开始执行 GUI 进程销毁序列...")

        # 1. 立即锁定状态闸，全面切断后续任何异步任务的提交与回调路由
        with self._exit_lock:
            if self._is_exiting:
                return
            self._is_exiting = True

        self._running = False
        if self._timer:
            self.root.after_cancel(self._timer)

        # 2. 停止托盘图标（防止 Windows 任务栏残留死图标）
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception as e:
                logger.error(f"停止系统托盘出错: {e}")
            self._tray_icon = None

        # 3. 下毒与回收后台线程池
        if self._current_refresh_future:
            cancelled = self._current_refresh_future.cancel()
            logger.info(f"尝试取消运行中的刷新 Future 任务，结果: {cancelled}")

        self._refresh_executor.shutdown(wait=False)

        if self._current_refresh_future and not self._current_refresh_future.done():
            logger.warning("检测到后台仍有活跃网络任务，正在等待其强制离场（限时2秒）...")
            done, not_done = wait([self._current_refresh_future], timeout=2.0, return_when=ALL_COMPLETED)
            if not_done:
                logger.critical("警告：后台刷新任务遭遇严重网络阻塞，未能在2秒内退出！")
            else:
                logger.info("后台刷新任务已安全离场，未残留任何资源。")

        # 4. 停止主控制器背后的常驻监控线程与看门狗
        try:
            if self.controller and self.controller.is_running:
                self.controller.stop()
        except Exception as e:
            logger.error(f"关停底层电池控制器出错: {e}")

        # 恢复系统默认睡眠策略
        try:
            from main import _prevent_sleep
            _prevent_sleep(False)
        except Exception:
            pass

        # 5. 最后销毁 Tkinter 主上下文
        try:
            logger.info("正在清理 Tkinter 核心组件...")
            self.root.destroy()
        except Exception as e:
            logger.error(f"销毁 Tkinter 实例时发生微小异常 (可忽略): {e}")

        logger.info("GUI 进程全生命周期回收完成，程序安全退出。")

    def _setup_tray(self):
        """设置系统托盘图标"""
        if not TRAY_AVAILABLE:
            return

        try:
            img = _load_tray_image()
            menu = pystray.Menu(
                pystray.MenuItem("显示窗口", self._show_window, default=True),
                pystray.MenuItem("退出", self._really_quit),
            )

            self._tray_icon = pystray.Icon(
                "BatteryLimit",
                img,
                "🔋 电池监控 - 运行中",
                menu,
            )

            self._tray_thread = threading.Thread(
                target=self._tray_icon.run,
                daemon=True,
            )
            self._tray_thread.start()
            logger.info("系统托盘已启动")
        except Exception as e:
            logger.error(f"托盘初始化失败: {e}")

    def run(self):
        if not TKINTER_AVAILABLE:
            return
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.mainloop()
        # 主循环结束后，确保托盘也停止
        if self._tray_icon:
            self._tray_icon.stop()


def run_gui(controller, config):
    if not TKINTER_AVAILABLE:
        logger.error("tkinter 不可用")
        return
    BatteryMonitorGUI(controller, config).run()
