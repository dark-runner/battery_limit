"""
PySide6 版本 GUI - 真正 Windows 毛玻璃效果
调用 Win32 DWM API 实现 Mica/模糊背景
"""
import sys
import os
import ctypes
import threading
import logging
from typing import Optional

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

logger = logging.getLogger(__name__)

# ── Win32 DWM API ─────────────────────────────────────
DWMWA_SYSTEMBACKDROP_TYPE = 38

TK = {
    "bg": "rgba(18, 18, 31, 0.7)",
    "glass": "rgba(30, 30, 48, 0.6)",
    "glass_border": "rgba(58, 58, 92, 0.8)",
    "fg": "#e0e0ff",
    "accent": "#7289da",
    "accent_light": "#99aaff",
    "dim": "#7a7a9a",
    "success": "#43b581",
    "warning": "#faa61a",
    "danger": "#f87171",
}

FONT_FAMILY = "Microsoft YaHei UI"


def enable_mica_effect(hwnd):
    """启用 Windows 11 Mica 毛玻璃效果"""
    try:
        dwm = ctypes.windll.dwmapi
        val = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(
            hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(val), ctypes.sizeof(val)
        )
        return True
    except Exception:
        return False


class GlassCard(QFrame):
    """磨砂玻璃卡片，带阴影"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            GlassCard {{
                background-color: {TK['glass']};
                border: 1px solid {TK['glass_border']};
                border-radius: 16px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)


class CloudLoginDialog(QDialog):
    """小米云登录对话框 - 支持二维码/密码登录（线程安全版）"""
    # ── 线程安全信号 ──
    qr_ready = Signal(object, object)    # QPixmap, str (login_url)
    captcha_needed = Signal(object, object)  # img_bytes, QEventLoop
    twfa_needed = Signal(object)         # QEventLoop
    devices_ready = Signal(object)       # list of devices
    status_update = Signal(str, str)     # msg, color
    login_failed = Signal(str)           # error msg

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.config = getattr(parent, 'config', None)
        self._connector = None
        self._device_list = []
        self.setWindowTitle("小米云登录")
        self.setFixedSize(420, 600)
        self.setStyleSheet(f"background-color: {TK['bg']};")
        self.setup_ui()
        self._connector = self._make_connector()
        # 连接信号到主线程槽
        self.qr_ready.connect(self._on_qr_ready)
        self.captcha_needed.connect(self._on_captcha_needed)
        self.twfa_needed.connect(self._on_twfa_needed)
        self.devices_ready.connect(self._on_devices_ready)
        self.status_update.connect(self._on_status_update)
        self.login_failed.connect(self._on_login_failed)

    def _make_connector(self):
        from micloud_helper import XiaomiCloudConnector
        return XiaomiCloudConnector()

    def setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("☁️ 小米云登录")
        title.setStyleSheet(f"color: {TK['fg']}; font-family: {FONT_FAMILY}; font-size: 16px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        region_row = QHBoxLayout()
        region_lbl = QLabel("区域:")
        region_lbl.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 10px; background: transparent;")
        region_row.addWidget(region_lbl)
        self.region_combo = QComboBox()
        regions = ["🇨🇳 cn (中国)", "🇸🇬 sg (新加坡)", "🇺🇸 us (美国)", "🇩🇪 de (德国)", "🇷🇺 ru (俄罗斯)", "🇮🇳 in (印度)"]
        self.region_combo.addItems(regions)
        self.region_combo.setStyleSheet(f"""
            QComboBox {{ background: {TK['glass']}; color: {TK['fg']}; border: 1px solid {TK['glass_border']};
            border-radius: 6px; padding: 6px; font-family: {FONT_FAMILY}; font-size: 10px; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox::down-arrow {{ image: none; }}
        """)
        region_row.addWidget(self.region_combo)
        layout.addLayout(region_row)

        self.status_label = QLabel("选择区域后点击「获取二维码」或输入账号密码登录")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 9px; background: transparent;")
        layout.addWidget(self.status_label)

        qr_group = QGroupBox("📱 二维码登录")
        qr_group.setStyleSheet(f"""
            QGroupBox {{ color: {TK['fg']}; font-family: {FONT_FAMILY}; font-size: 10px;
            border: 1px solid {TK['glass_border']}; border-radius: 8px; margin-top: 8px; padding-top: 16px; }}
            QGroupBox::title {{ subcontrol-origin: margin; padding: 0 6px; }}
        """)
        qr_layout = QVBoxLayout(qr_group)
        qr_layout.setSpacing(8)
        self.qr_label = QLabel("点击下方按钮获取二维码")
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumHeight(140)
        self.qr_label.setStyleSheet(
            f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 10px; "
            f"background: {TK['glass']}; border: 1px solid {TK['glass_border']}; border-radius: 8px;"
        )
        qr_layout.addWidget(self.qr_label, stretch=1)
        self.qr_btn = QPushButton("📱 获取二维码")
        self.qr_btn.setStyleSheet(f"""
            QPushButton {{ background: {TK['accent']}; color: #fff; border: none;
            border-radius: 6px; padding: 8px; font-family: {FONT_FAMILY}; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {TK['accent_light']}; }}
            QPushButton:disabled {{ background: {TK['glass']}; color: {TK['dim']}; }}
        """)
        self.qr_btn.clicked.connect(self._start_qrcode)
        qr_layout.addWidget(self.qr_btn)
        layout.addWidget(qr_group)

        sep = QLabel("━━━━ 或 ━━━━")
        sep.setAlignment(Qt.AlignCenter)
        sep.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 9px; background: transparent;")
        layout.addWidget(sep)

        pw_group = QGroupBox("🔑 账号密码登录")
        pw_group.setStyleSheet(qr_group.styleSheet())
        pw_layout = QVBoxLayout(pw_group)
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("小米账号")
        self.user_edit.setStyleSheet(f"""
            QLineEdit {{ background: {TK['glass']}; color: {TK['fg']}; border: 1px solid {TK['glass_border']};
            border-radius: 6px; padding: 8px; font-family: {FONT_FAMILY}; font-size: 10px; }}
        """)
        pw_layout.addWidget(self.user_edit)
        self.pass_edit = QLineEdit()
        self.pass_edit.setPlaceholderText("密码")
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setStyleSheet(self.user_edit.styleSheet())
        pw_layout.addWidget(self.pass_edit)
        self.login_btn = QPushButton("🔑 登录并获取设备")
        self.login_btn.setStyleSheet(self.qr_btn.styleSheet())
        self.login_btn.clicked.connect(self._password_login)
        pw_layout.addWidget(self.login_btn)
        layout.addWidget(pw_group)
        layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background: {TK['glass']}; color: {TK['dim']}; border: none;
            border-radius: 6px; padding: 8px; font-family: {FONT_FAMILY}; font-size: 10px; }}
            QPushButton:hover {{ background: {TK['glass_border']}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        scroll.setWidget(content)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    # ── 信号槽：主线程安全更新 UI ──

    @Slot(object, object)
    def _on_qr_ready(self, pix, login_url):
        """主线程：更新二维码显示"""
        self.qr_label.setPixmap(pix)
        self.qr_label.setFixedHeight(pix.height() + 8)
        self.qr_label.setStyleSheet("background: transparent; border: none;")
        self.qr_label.setText("")
        self.qr_btn.setEnabled(True)
        self.qr_btn.setText("🔄 刷新二维码")
        self._set_status("请使用米家 APP 扫描二维码", TK["accent"])

    @Slot(object, object)
    def _on_captcha_needed(self, img_bytes, loop):
        """主线程：显示验证码输入对话框"""
        from PIL import Image, ImageQt
        import tempfile
        dlg = QDialog(self)
        dlg.setWindowTitle("验证码")
        dlg.setFixedSize(300, 220)
        dlg.setStyleSheet(f"background: {TK['bg']};")
        layout = QVBoxLayout(dlg)
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.write(img_bytes); tmp.close()
            img = Image.open(tmp.name)
            img.thumbnail((260, 100), Image.LANCZOS)
            qt_img = ImageQt.ImageQt(img)
            pix = QPixmap.fromImage(qt_img)
            lbl = QLabel()
            lbl.setPixmap(pix)
            layout.addWidget(lbl)
        except Exception:
            pass
        layout.addWidget(QLabel("请输入验证码（区分大小写）"))
        code_edit = QLineEdit()
        code_edit.setStyleSheet(f"background: {TK['glass']}; color: {TK['fg']}; border-radius: 4px; padding: 6px;")
        layout.addWidget(code_edit)
        result = [""]
        def _ok():
            result[0] = code_edit.text().strip()
            dlg.accept()
            loop.quit()
        btn = QPushButton("确认")
        btn.clicked.connect(_ok)
        layout.addWidget(btn)
        dlg.finished.connect(lambda: loop.quit() if loop.isRunning() else None)
        dlg.open()  # 非阻塞
        # loop 在后台线程中 exec，此处返回后线程继续
        # 结果通过 result 传递
        loop.exec()
        loop.result = result[0]

    @Slot(object)
    def _on_twfa_needed(self, loop):
        """主线程：显示2FA输入对话框"""
        dlg = QDialog(self)
        dlg.setWindowTitle("两步验证")
        dlg.setFixedSize(300, 160)
        dlg.setStyleSheet(f"background: {TK['bg']};")
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("📧 验证码已发送到邮箱"))
        layout.addWidget(QLabel("请输入邮件中的验证码"))
        code_edit = QLineEdit()
        code_edit.setStyleSheet(f"background: {TK['glass']}; color: {TK['fg']}; border-radius: 4px; padding: 6px; font-size: 14px;")
        layout.addWidget(code_edit)
        result = [""]
        def _ok():
            result[0] = code_edit.text().strip()
            dlg.accept()
            loop.quit()
        btn = QPushButton("确认")
        btn.clicked.connect(_ok)
        layout.addWidget(btn)
        dlg.finished.connect(lambda: loop.quit() if loop.isRunning() else None)
        dlg.open()
        loop.exec()
        loop.result = result[0]

    @Slot(object)
    def _on_devices_ready(self, devices):
        """主线程：显示设备列表"""
        if not devices:
            mb = QMessageBox(QMessageBox.Icon.Warning, "云端结果", "未找到设备",
                             QMessageBox.StandardButton.Ok, self)
            mb.setStyleSheet(f"color: {TK['fg']}; background: {TK['bg']};")
            mb.exec()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("选择设备")
        dlg.setFixedSize(400, 350)
        dlg.setStyleSheet(f"background: {TK['bg']};")
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        title = QLabel("✅ 登录成功！请选择要控制的设备：")
        title.setStyleSheet(f"color: {TK['fg']}; font-family: {FONT_FAMILY}; font-size: 11px;")
        layout.addWidget(title)
        list_widget = QListWidget()
        list_widget.setStyleSheet(f"""
            QListWidget {{ background: {TK['glass']}; color: {TK['fg']}; border: 1px solid {TK['glass_border']};
            border-radius: 8px; font-family: {FONT_FAMILY}; font-size: 10px; }}
            QListWidget::item {{ padding: 8px; }}
            QListWidget::item:hover {{ background: {TK['glass_border']}; }}
            QListWidget::item:selected {{ background: {TK['accent']}; color: #fff; }}
        """)
        for d in devices:
            item = QListWidgetItem(f"🔌 {d.get('name', '')} ({d.get('ip', '')})")
            item.setData(Qt.ItemDataRole.UserRole, d)
            list_widget.addItem(item)
        if list_widget.count() > 0:
            list_widget.setCurrentRow(0)
        layout.addWidget(list_widget)
        status_info = QLabel("")
        status_info.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 9px; background: transparent;")
        layout.addWidget(status_info)
        def _show_msg(parent, icon, title, text):
            mb = QMessageBox(icon, title, text, QMessageBox.StandardButton.Ok, parent)
            mb.setStyleSheet(f"color: {TK['fg']}; background: {TK['bg']};")
            return mb.exec()

        def _select():
            try:
                item = list_widget.currentItem()
                if not item:
                    status_info.setText("⚠️ 请先从列表中选择一个设备")
                    return
                d = item.data(Qt.ItemDataRole.UserRole)
                ip = d.get("ip", ""); token = d.get("token", "")
                if not ip or not token:
                    _show_msg(dlg, QMessageBox.Icon.Warning, "数据不完整",
                              f"该设备缺少IP或Token信息，无法配置。\nIP: {ip}\nToken: {token}")
                    return
                btn.setText("⏳ 正在配置...")
                btn.setEnabled(False)
                QApplication.processEvents()
                self.controller.mihome_controller.configure(ip, token, d.get("model", ""))
                if self.config:
                    self.config.set("mihome.ip", ip)
                    self.config.set("mihome.token", token)
                    self.config.set("mihome.model", d.get("model", ""))
                    self.config.save()
                status_info.setText(f"✅ 已配置设备: {d.get('name', '')}")
                QApplication.processEvents()
                QTimer.singleShot(300, dlg.accept)
                QTimer.singleShot(300, self.accept)
            except Exception as e:
                _show_msg(dlg, QMessageBox.Icon.Critical, "配置失败", f"保存设备配置时出错：\n{e}")
                btn.setText("选择此设备")
                btn.setEnabled(True)
        list_widget.itemDoubleClicked.connect(_select)
        btn = QPushButton("选择此设备")
        btn.setStyleSheet(f"""
            QPushButton {{ background: {TK['accent']}; color: #fff; border: none;
            border-radius: 6px; padding: 8px; font-family: {FONT_FAMILY}; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {TK['accent_light']}; }}
        """)
        btn.clicked.connect(_select)
        layout.addWidget(btn)
        dlg.exec()

    @Slot(str, str)
    def _on_status_update(self, msg, color):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {color}; font-family: {FONT_FAMILY}; font-size: 9px; background: transparent;")

    @Slot(str)
    def _on_login_failed(self, msg):
        self._set_status(msg, TK["danger"])
        self.qr_btn.setEnabled(True)
        self.qr_btn.setText("📱 获取二维码")

    def _set_status(self, msg, color=None):
        color = color or TK["dim"]
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {color}; font-family: {FONT_FAMILY}; font-size: 9px; background: transparent;")
        QApplication.processEvents()

    # ── 后台线程：网络 IO，不碰 UI ──

    def _start_qrcode(self):
        """主线程调用：启动后台二维码获取"""
        region = self.region_combo.currentText()
        region_code = region.split()[1] if " " in region else region
        self.qr_btn.setEnabled(False)
        self.qr_btn.setText("⏳ 获取中...")
        self._set_status("正在获取二维码...", TK["warning"])

        def _do():
            try:
                self._connector.login_qrcode(
                    qrcode_callback=self._on_qr_bytes,
                    status_callback=self._on_qr_status
                )
            except Exception as e:
                self.login_failed.emit(f"❌ 错误: {e}")
        threading.Thread(target=_do, daemon=True).start()

    def _on_qr_bytes(self, img_bytes, login_url):
        """后台线程：处理二维码图片，通过信号发送到主线程"""
        try:
            from PIL import Image, ImageQt
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            tmp.write(img_bytes); tmp.close()
            img = Image.open(tmp.name)
            img.thumbnail((200, 150), Image.LANCZOS)
            qt_img = ImageQt.ImageQt(img)
            pix = QPixmap.fromImage(qt_img)
            self.qr_ready.emit(pix, login_url)  # ✅ 信号发送到主线程
        except Exception as e:
            self.login_failed.emit(f"❌ 显示二维码失败: {e}")

    def _on_qr_status(self, msg):
        """后台线程：状态回调"""
        color = TK["success"] if "成功" in msg else TK["warning"]
        self.status_update.emit(msg, color)
        if "成功" in msg:
            region = self.region_combo.currentText()
            region_code = region.split()[1] if " " in region else region
            threading.Thread(target=lambda: self._connector.fetch_devices_by_region(
                region_code,
                status_cb=lambda m: self.status_update.emit(m, TK["success"] if "✅" in m else TK["warning"]),
                result_cb=lambda devices: self.devices_ready.emit(devices)  # ✅ 信号
            ), daemon=True).start()

    def _password_login(self):
        """主线程调用：启动后台密码登录"""
        username = self.user_edit.text().strip()
        password = self.pass_edit.text()
        if not username or not password:
            self._set_status("⚠ 请输入账号和密码", TK["danger"])
            return
        region = self.region_combo.currentText()
        region_code = region.split()[1] if " " in region else region
        self.login_btn.setEnabled(False)
        self._set_status("⏳ 正在登录...", TK["warning"])

        def _do():
            try:
                ok = self._connector.login(username, password,
                    captcha_callback=self._sync_captcha,
                    twfa_callback=self._sync_2fa,
                    status_callback=lambda m: self.status_update.emit(m,
                        TK["success"] if "✅" in m else TK["red"] if "❌" in m else TK["warning"])
                )
                if ok:
                    self._connector.fetch_devices_by_region(
                        region_code,
                        status_cb=lambda m: self.status_update.emit(m, TK["success"] if "✅" in m else TK["warning"]),
                        result_cb=lambda devices: self.devices_ready.emit(devices)
                    )
                else:
                    self.status_update.emit("❌ 登录失败", TK["danger"])
            except Exception as e:
                self.status_update.emit(f"❌ 错误: {e}", TK["danger"])
            finally:
                self.qr_btn.setEnabled(True)
        threading.Thread(target=_do, daemon=True).start()

    def _sync_captcha(self, img_bytes) -> str:
        """后台线程：通过信号在主线程显示验证码，阻塞等待结果"""
        loop = QEventLoop()
        self.captcha_needed.emit(img_bytes, loop)
        loop.exec()
        return getattr(loop, 'result', "")

    def _sync_2fa(self) -> str:
        """后台线程：通过信号在主线程显示2FA，阻塞等待结果"""
        loop = QEventLoop()
        self.twfa_needed.emit(loop)
        loop.exec()
        return getattr(loop, 'result', "")

    # ── CloudLoginDialog 结束 ──


class SettingsDialog(QDialog):
    """设置对话框"""
    def __init__(self, controller, config, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.config = config
        self.setWindowTitle("设置")
        self.setFixedSize(380, 580)
        self.setStyleSheet(f"background-color: {TK['bg']};")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("⚙ 设置")
        title.setStyleSheet(f"color: {TK['fg']}; font-family: {FONT_FAMILY}; font-size: 16px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        # 高阈值
        hi_lbl = QLabel("高阈值 (%)")
        hi_lbl.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 10px; background: transparent;")
        layout.addWidget(hi_lbl)
        self.hi_spin = QSpinBox()
        self.hi_spin.setRange(1, 100)
        self.hi_spin.setValue(int(self.controller.high_threshold))
        self.hi_spin.setStyleSheet(f"""
            QSpinBox {{ background: {TK['glass']}; color: {TK['fg']}; border: 1px solid {TK['glass_border']};
            border-radius: 6px; padding: 6px 10px; font-family: {FONT_FAMILY}; font-size: 11px; }}
        """)
        self.hi_spin.setFixedHeight(32)
        layout.addWidget(self.hi_spin)

        # 低阈值
        lo_lbl = QLabel("低阈值 (%)")
        lo_lbl.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 10px; background: transparent;")
        layout.addWidget(lo_lbl)
        self.lo_spin = QSpinBox()
        self.lo_spin.setRange(0, 99)
        self.lo_spin.setValue(int(self.controller.low_threshold))
        self.lo_spin.setStyleSheet(self.hi_spin.styleSheet())
        self.lo_spin.setFixedHeight(32)
        layout.addWidget(self.lo_spin)

        # 检查间隔
        int_lbl = QLabel("检查间隔 (秒)")
        int_lbl.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 10px; background: transparent;")
        layout.addWidget(int_lbl)
        self.int_spin = QSpinBox()
        self.int_spin.setRange(10, 600)
        self.int_spin.setValue(self.controller.check_interval)
        self.int_spin.setSingleStep(10)
        self.int_spin.setStyleSheet(self.hi_spin.styleSheet())
        self.int_spin.setFixedHeight(32)
        layout.addWidget(self.int_spin)

        # ── 米家设备 ──
        mi_title = QLabel("米家设备")
        mi_title.setStyleSheet(f"color: {TK['fg']}; font-family: {FONT_FAMILY}; font-size: 13px; font-weight: bold; background: transparent; margin-top: 8px;")
        layout.addWidget(mi_title)

        ip_lbl = QLabel("设备 IP")
        ip_lbl.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 10px; background: transparent;")
        layout.addWidget(ip_lbl)
        self.ip_edit = QLineEdit(self.controller.mihome_controller.ip)
        self.ip_edit.setStyleSheet(f"""
            QLineEdit {{ background: {TK['glass']}; color: {TK['fg']}; border: 1px solid {TK['glass_border']};
            border-radius: 6px; padding: 6px 10px; font-family: {FONT_FAMILY}; font-size: 11px; }}
        """)
        self.ip_edit.setFixedHeight(32)
        layout.addWidget(self.ip_edit)

        tk_lbl = QLabel("设备 Token")
        tk_lbl.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 10px; background: transparent;")
        layout.addWidget(tk_lbl)
        self.tk_edit = QLineEdit(self.controller.mihome_controller.token)
        self.tk_edit.setStyleSheet(self.ip_edit.styleSheet())
        self.tk_edit.setFixedHeight(32)
        layout.addWidget(self.tk_edit)

        # ── 小米云登录按钮 ──
        cloud_btn = QPushButton("☁️ 小米云登录获取 Token")
        cloud_btn.setStyleSheet(f"""
            QPushButton {{ background: {TK['accent']}; color: #fff; border: none;
            border-radius: 8px; padding: 10px; font-family: {FONT_FAMILY}; font-size: 10px; font-weight: bold; }}
            QPushButton:hover {{ background: {TK['accent_light']}; }}
        """)
        cloud_btn.clicked.connect(self._cloud_login)
        layout.addWidget(cloud_btn)

        # ── 开机自启 ──
        autostart_title = QLabel("🚀 开机自启")
        autostart_title.setStyleSheet(f"color: {TK['fg']}; font-family: {FONT_FAMILY}; font-size: 13px; font-weight: bold; background: transparent; margin-top: 8px;")
        layout.addWidget(autostart_title)

        self.autostart_cb = QCheckBox("系统启动时自动运行")
        self.autostart_cb.setChecked(self.config.get("autostart", False))
        self.autostart_cb.setStyleSheet(f"""
            QCheckBox {{ color: {TK['fg']}; font-family: {FONT_FAMILY}; font-size: 10px; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; }}
        """)
        layout.addWidget(self.autostart_cb)

        layout.addStretch()

        # 按钮
        btn_row = QHBoxLayout()
        btn_style = f"""
            QPushButton {{ background: {TK['glass']}; color: {TK['fg']}; border: none;
            border-radius: 8px; padding: 8px 20px; font-family: {FONT_FAMILY}; font-size: 10px; }}
            QPushButton:hover {{ background: {TK['glass_border']}; }}
        """
        save_btn = QPushButton("💾 保存")
        save_btn.setStyleSheet(btn_style)
        save_btn.setFixedHeight(34)
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(btn_style)
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _cloud_login(self):
        """小米云登录获取 Token（PySide6 对话框）"""
        dlg = CloudLoginDialog(self.controller, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.ip_edit.setText(self.controller.mihome_controller.ip)
            self.tk_edit.setText(self.controller.mihome_controller.token)
            mb = QMessageBox(QMessageBox.Icon.Information, "完成", "IP 和 Token 已自动填入", QMessageBox.StandardButton.Ok, self)
            mb.setStyleSheet(f"color: {TK['fg']}; background: {TK['bg']};")
            mb.exec()

    def _save(self):
        hi = self.hi_spin.value()
        lo = self.lo_spin.value()
        interval = self.int_spin.value()

        if lo >= hi:
            mb = QMessageBox(QMessageBox.Icon.Warning, "错误", "低阈值必须小于高阈值", QMessageBox.StandardButton.Ok, self)
            mb.setStyleSheet(f"color: {TK['fg']}; background: {TK['bg']};")
            mb.exec()
            return

        # 更新控制器
        self.controller.high_threshold = float(hi)
        self.controller.low_threshold = float(lo)
        self.controller.check_interval = interval

        # 更新配置
        self.config.set("thresholds.high", float(hi))
        self.config.set("thresholds.low", float(lo))
        self.config.set("check_interval", interval)

        # 更新米家设备配置
        ip = self.ip_edit.text().strip()
        token = self.tk_edit.text().strip()
        if ip and token:
            self.config.set("mihome.ip", ip)
            self.config.set("mihome.token", token)
            self.controller.mihome_controller.configure(ip, token)

        # 开机自启
        autostart = self.autostart_cb.isChecked()
        self.config.set("autostart", autostart)
        from config import set_autostart
        set_autostart(autostart)

        self.config.save()
        mb = QMessageBox(QMessageBox.Icon.Information, "完成", "设置已保存", QMessageBox.StandardButton.Ok, self)
        mb.setStyleSheet(f"color: {TK['fg']}; background: {TK['bg']};")
        mb.exec()
        self.accept()


class MainWindow(QMainWindow):
    switch_done = Signal(str, str)

    def __init__(self, controller, config):
        super().__init__()
        self.controller = controller
        self.config = config
        self._running = True
        self._tray = None
        self._timer = None

        self.switch_done.connect(self._on_switch_done)

        self.setWindowTitle("Battery Limit")
        self.setFixedSize(420, 520)
        self.setAttribute(Qt.WA_TranslucentBackground)

        hwnd = int(self.winId())
        if not enable_mica_effect(hwnd):
            logger.debug("Mica 不可用，使用半透明背景")

        self.setup_ui()
        self.setup_tray()
        self.start_refresh()

    def setup_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background-color: {TK['bg']}; border-radius: 16px;")
        self.setCentralWidget(central)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 8)
        central.setGraphicsEffect(shadow)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # ── 1. 标题行 ─────────────────
        title = QLabel("充电控制")
        title.setStyleSheet(f"color: {TK['fg']}; font-family: {FONT_FAMILY}; font-size: 18px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        # ── 2. 大电量 ───────────────
        self.pct_label = QLabel("--%")
        self.pct_label.setAlignment(Qt.AlignCenter)
        self.pct_label.setStyleSheet(f"color: {TK['accent']}; font-family: {FONT_FAMILY}; font-size: 64px; font-weight: 100; background: transparent;")
        layout.addWidget(self.pct_label)

        self.power_label = QLabel("⏳ 正在获取...")
        self.power_label.setAlignment(Qt.AlignCenter)
        self.power_label.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 12px; background: transparent;")
        layout.addWidget(self.power_label)

        # ── 3. 三个玻璃卡片 ─────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        card1 = GlassCard()
        c1l = QVBoxLayout(card1)
        c1l.setContentsMargins(16, 16, 16, 16)
        c1l.setSpacing(8)
        t1 = QLabel("🔌 米家开关")
        t1.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 9px; background: transparent;")
        c1l.addWidget(t1)
        self.switch_status = QLabel("--")
        self.switch_status.setStyleSheet(f"color: {TK['fg']}; font-family: {FONT_FAMILY}; font-size: 14px; font-weight: bold; background: transparent;")
        c1l.addWidget(self.switch_status)
        self.switch_detail = QLabel("")
        self.switch_detail.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 8px; background: transparent;")
        c1l.addWidget(self.switch_detail)
        cards_row.addWidget(card1)

        card2 = GlassCard()
        c2l = QVBoxLayout(card2)
        c2l.setContentsMargins(16, 16, 16, 16)
        c2l.setSpacing(8)
        t2 = QLabel("🎯 充电区间")
        t2.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 9px; background: transparent;")
        c2l.addWidget(t2)
        self.threshold_label = QLabel("-- ~ --")
        self.threshold_label.setStyleSheet(f"color: {TK['accent']}; font-family: {FONT_FAMILY}; font-size: 14px; font-weight: bold; background: transparent;")
        c2l.addWidget(self.threshold_label)
        c2l.addStretch()
        cards_row.addWidget(card2)

        card3 = GlassCard()
        c3l = QVBoxLayout(card3)
        c3l.setContentsMargins(16, 16, 16, 16)
        c3l.setSpacing(8)
        t3 = QLabel("⏱ 检查间隔")
        t3.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 9px; background: transparent;")
        c3l.addWidget(t3)
        self.interval_label = QLabel("--s")
        self.interval_label.setStyleSheet(f"color: {TK['fg']}; font-family: {FONT_FAMILY}; font-size: 14px; font-weight: bold; background: transparent;")
        c3l.addWidget(self.interval_label)
        c3l.addStretch()
        cards_row.addWidget(card3)

        layout.addLayout(cards_row)

        # ── 4. 操作按钮 ────────────────
        switch_btns = QHBoxLayout()
        switch_btns.setSpacing(12)

        btn_off = QPushButton("🔴 停止充电")
        btn_off.setStyleSheet(f"""
            QPushButton {{
                background-color: {TK['glass']};
                color: {TK['accent']};
                border: 1px solid {TK['glass_border']};
                border-radius: 8px;
                padding: 10px 20px;
                font-family: {FONT_FAMILY};
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {TK['glass_border']};
                border: 1px solid {TK['accent']};
            }}
        """)
        btn_off.clicked.connect(self._switch_off)

        btn_on = QPushButton("⚡ 开启充电")
        btn_on.setStyleSheet(f"""
            QPushButton {{
                background-color: {TK['accent']};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-family: {FONT_FAMILY};
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {TK['accent_light']};
            }}
        """)
        btn_on.clicked.connect(self._switch_on)

        switch_btns.addWidget(btn_off)
        switch_btns.addWidget(btn_on)
        layout.addLayout(switch_btns)

        # ── 5. 底部按钮 ────────────────
        bottom_btns = QHBoxLayout()
        btn_style = f"""
            QPushButton {{
                background-color: {TK['glass']};
                color: {TK['fg']};
                border: none;
                border-radius: 8px;
                padding: 8px 24px;
                font-family: {FONT_FAMILY};
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {TK['glass_border']};
            }}
        """

        btn_settings = QPushButton("⚙ 设置")
        btn_settings.setStyleSheet(btn_style)
        btn_settings.clicked.connect(self._open_settings)

        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.setStyleSheet(btn_style)
        btn_refresh.clicked.connect(self._refresh)

        bottom_btns.addWidget(btn_settings)
        bottom_btns.addStretch()
        bottom_btns.addWidget(btn_refresh)
        layout.addLayout(bottom_btns)

        # ── 6. 底部信息 ────────────────
        self.info_label = QLabel("阈值: ↑--% ↓--% | 间隔: --s")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet(f"color: {TK['dim']}; font-family: {FONT_FAMILY}; font-size: 9px; background: transparent;")
        layout.addWidget(self.info_label)

    def setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        icon = self._load_icon()
        self._tray.setIcon(icon)
        self._tray.setToolTip("Battery Limit")
        self._tray.setVisible(True)
        # 点击托盘图标恢复窗口
        self._tray.activated.connect(self._on_tray_activated)
        menu = QMenu()
        menu.addAction("显示窗口", self._show_window)
        menu.addSeparator()
        menu.addAction("退出", self._quit)
        self._tray.setContextMenu(menu)

    def _show_window(self):
        """恢复窗口并激活到前台"""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _on_tray_activated(self, reason):
        """托盘图标被点击时恢复窗口（仅左键单击/双击，右键弹出菜单不触发展开）"""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                       QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_window()

    def _load_icon(self) -> QIcon:
        for p in [
            os.path.join(os.path.dirname(__file__), "..", "app.ico"),
            os.path.join(os.path.dirname(__file__), "app.ico"),
            "app.ico",
            os.path.join(os.path.dirname(__file__), "..", "icon.png"),
            os.path.join(os.path.dirname(__file__), "icon.png"),
            "icon.png",
        ]:
            if os.path.exists(p):
                return QIcon(p)
        pix = QPixmap(32, 32)
        pix.fill(QColor(TK["accent"]))
        return QIcon(pix)

    def start_refresh(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self._bg_refresh)
        self._timer.start(2000)

    def _bg_refresh(self):
        try:
            ctrl = self.controller
            bm = ctrl.battery_manager
            mh = ctrl.mihome_controller
            st = bm.get_battery_status()
            pct = st.get("percent", 0)
            plugged = st.get("power_plugged")
            on = None
            if mh.available:
                try:
                    on = mh.is_on()
                except Exception:
                    pass
            has_battery = bm.has_battery
            if not has_battery:
                self.pct_label.setText("🖥️ 台式机")
                self.pct_label.setStyleSheet(f"color: {TK['dim']}; font-size: 24px; background: transparent;")
                self.power_label.setText("无物理电池")
            else:
                pct_int = int(round(pct))
                self.pct_label.setText(f"{pct_int}%")
                color = TK["accent"]
                if pct <= 20:
                    color = TK["danger"]
                elif pct <= 40:
                    color = TK["warning"]
                elif pct >= 80:
                    color = TK["accent_light"]
                self.pct_label.setStyleSheet(f"color: {color}; font-family: {FONT_FAMILY}; font-size: 64px; font-weight: 100; background: transparent;")
                self.power_label.setText("⚡ 充电中" if plugged is True else "🔋 电池供电" if plugged is False else "❓ 未知")
            if on is True:
                txt, fg = "已开启", TK["success"]
                detail = f"已连接 ({mh.ip})" if mh.ip else ""
            elif on is False:
                txt, fg = "已关闭", TK["danger"]
                detail = f"已连接 ({mh.ip})" if mh.ip else ""
            elif on is None and not mh.available:
                txt, fg = "未配置", TK["dim"]
                detail = "请设置设备"
            else:
                txt, fg = "离线", TK["warning"]
                detail = ""
            self.switch_status.setText(txt)
            self.switch_status.setStyleSheet(f"color: {fg}; font-family: {FONT_FAMILY}; font-size: 14px; font-weight: bold; background: transparent;")
            self.switch_detail.setText(detail)
            hi, lo = ctrl.high_threshold, ctrl.low_threshold
            self.threshold_label.setText(f"{lo:.0f}% ~ {hi:.0f}%")
            self.interval_label.setText(f"{ctrl.check_interval}s")
            self.info_label.setText(f"阈值: ↑{hi:.0f}% ↓{lo:.0f}% | 间隔: {ctrl.check_interval}s")
        except Exception as e:
            logger.error(f"刷新失败: {e}")

    def _switch_on(self):
        mh = self.controller.mihome_controller
        mh.reset_cooldown()
        self.switch_status.setText("⏳ 开启中...")
        def _do():
            if mh.turn_on(force=True):
                self.switch_done.emit("已开启", TK["success"])
        threading.Thread(target=_do, daemon=True).start()

    def _switch_off(self):
        mh = self.controller.mihome_controller
        mh.reset_cooldown()
        self.switch_status.setText("⏳ 关闭中...")
        def _do():
            if mh.turn_off(force=True):
                self.switch_done.emit("已关闭", TK["danger"])
        threading.Thread(target=_do, daemon=True).start()

    def _on_switch_done(self, text, color):
        self.switch_status.setText(text)
        self.switch_status.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold; background: transparent;")

    def _refresh(self):
        self._bg_refresh()

    def _open_settings(self):
        """打开设置对话框"""
        dlg = SettingsDialog(self.controller, self.config, self)
        dlg.exec()

    def _quit(self):
        logger.info("用户退出")
        self._running = False
        if self._timer:
            self._timer.stop()
        if self.controller and self.controller.is_running:
            self.controller.stop()
        if self._tray:
            self._tray.setVisible(False)
        QApplication.quit()

    def closeEvent(self, event):
        if self._tray and self._tray.isVisible():
            event.ignore()
            self.hide()
            self._tray.showMessage("Battery Limit", "已最小化到托盘", QSystemTrayIcon.Information, 2000)
        else:
            self._quit()


def run_gui(controller, config):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    icon = QIcon()
    for p in [
        os.path.join(os.path.dirname(__file__), "..", "app.ico"),
        os.path.join(os.path.dirname(__file__), "app.ico"),
    ]:
        if os.path.exists(p):
            icon = QIcon(p)
            break
    app.setWindowIcon(icon)
    window = MainWindow(controller, config)
    window.show()
    sys.exit(app.exec())
