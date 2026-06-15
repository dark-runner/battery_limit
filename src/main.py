"""Main Application Entry Point - 全生命周期句柄安全释放版"""

import logging
import sys
import os
import ctypes
import atexit
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 进程级全局句柄追踪 ──────────────────────────────────
_APPLICATION_MUTEX = None
MUTEX_NAME = "Global\\BatteryLimitManager-6A2B9F81-1D38-4E8A-9A3C-8F1E2D4B5C7A"


def _cleanup_system_handles():
    """进程退出时的物理句柄注销回调（由 atexit 强保障）"""
    global _APPLICATION_MUTEX
    if _APPLICATION_MUTEX is not None:
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.CloseHandle(_APPLICATION_MUTEX)
            logger.info("系统全局互斥体句柄已显式安全关闭。")
        except Exception as e:
            logger.error(f"释放互斥体句柄失败: {e}")
        finally:
            _APPLICATION_MUTEX = None


atexit.register(_cleanup_system_handles)


def _check_single_instance() -> bool:
    """检查是否已有实例运行，严格保障句柄无泄漏"""
    global _APPLICATION_MUTEX
    kernel32 = ctypes.windll.kernel32
    ERROR_ALREADY_EXISTS = 183

    try:
        _APPLICATION_MUTEX = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not _APPLICATION_MUTEX:
            logger.critical("无法创建系统互斥体内核对象。")
            return False

        if ctypes.GetLastError() == ERROR_ALREADY_EXISTS:
            logger.warning("检测到已有程序实例正在运行，开始执行前台激活唤醒序列...")
            kernel32.CloseHandle(_APPLICATION_MUTEX)
            _APPLICATION_MUTEX = None
            _activate_existing_window()
            return False

        return True
    except Exception as e:
        logger.error(f"单实例检测模块发生异常: {e}")
        return True


def _activate_existing_window():
    """精确、短生命周期安全地查找已有窗口并激活到前台"""
    user32 = ctypes.windll.user32
    titles = ["🔋 电池监控 · Battery Limit", "🔋 电池监控"]

    def enum_windows_callback(hwnd, lParam) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value in titles:
                logger.info(f"成功定位旧实例窗口句柄 (HWND: {hwnd})，正在强制还原并激活...")
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    callback_func = WNDENUMPROC(enum_windows_callback)

    try:
        user32.EnumWindows(callback_func, 0)
    except Exception as e:
        logger.error(f"枚举 Windows 顶级窗口失败: {e}")
    finally:
        del callback_func
        logger.debug("窗口枚举内存跳板已安全剥离销毁。")


# 路径处理：支持 PyInstaller 打包后的路径
if getattr(sys, 'frozen', False):
    SRC_DIR = Path(sys._MEIPASS) / "src"
else:
    SRC_DIR = Path(__file__).parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ── 日志轮转 ───────────────────────────────────────────
from logging.handlers import RotatingFileHandler


def _setup_logging():
    """配置日志（轮转，仅初始化一次）"""
    root = logging.getLogger()
    if root.handlers:
        return
    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    root.setLevel(logging.INFO)
    fh = RotatingFileHandler('battery_control.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8-sig')
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)


_setup_logging()

# ── 阻止系统睡眠 ─────────────────────────────────────────
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def _prevent_sleep(enable: bool = True):
    """阻止/恢复系统睡眠"""
    try:
        kernel32 = ctypes.windll.kernel32
        if enable:
            kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
        else:
            kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    except Exception:
        pass


class BatteryLimitApp:
    """电池限制管理应用 - 原生桌面GUI"""

    def __init__(
        self,
        mihome_ip: str,
        mihome_token: str,
        high_threshold: float = 80.0,
        low_threshold: float = 30.0,
        check_interval: int = 60
    ):
        from battery_auto_controller import BatteryAutoController
        from config import Config

        self.config = Config(config_file="config.json")
        self.controller = BatteryAutoController(
            mihome_ip=mihome_ip,
            mihome_token=mihome_token,
            high_threshold=high_threshold,
            low_threshold=low_threshold,
            check_interval=check_interval
        )

    def _set_process_priority(self):
        """提升进程优先级防止被降频"""
        try:
            kernel32 = ctypes.windll.kernel32
            pid = kernel32.GetCurrentProcess()
            kernel32.SetPriorityClass(pid, 0x00000080)
            logger.info("进程优先级已设置为高")
        except Exception:
            pass

    def run(self) -> None:
        """运行应用 - 监控与GUI生命周期彻底分离"""
        logger.info("启动电池限制管理桌面应用")
        try:
            self._set_process_priority()
            if not self.controller.is_running:
                # 监控启动时同步挂载防睡眠锁
                _prevent_sleep(True)
                self.controller.start()
            from gui import run_gui
            run_gui(self.controller, self.config)
        except Exception as e:
            logger.critical(f"应用核心生命周期发生严重崩溃: {e}")

        # GUI 窗口已关闭，但托盘和监控线程仍在运行
        logger.info("主 GUI 窗口已关闭，转入后台纯净守护模式...")

        # 阻塞等待控制器彻底退出（托盘点击"退出"时 is_running 变为 False）
        try:
            while self.controller.is_running:
                if self.controller.monitor_thread and self.controller.monitor_thread.is_alive():
                    self.controller.monitor_thread.join(timeout=2)
                else:
                    break
        except (KeyboardInterrupt, SystemExit):
            logger.info("接收到终止信号，停止控制器...")
            self.controller.stop()

        # 监控线程完全结束后才释放防睡眠锁
        _prevent_sleep(False)
        logger.info("应用全链路已安全平稳退出。")


if __name__ == "__main__":
    if not _check_single_instance():
        logger.info("当前进程属于重复实例，正在安全离场...")
        sys.exit(0)

    try:
        from config import Config
        cfg = Config(config_file="config.json")

        mihome_ip = cfg.get("mihome.ip", "") or ""
        mihome_token = cfg.get("mihome.token", "") or ""
        high_threshold = cfg.get("thresholds.high", 80.0)
        low_threshold = cfg.get("thresholds.low", 30.0)
        check_interval = cfg.get("check_interval", 60)

        app = BatteryLimitApp(
            mihome_ip=mihome_ip,
            mihome_token=mihome_token,
            high_threshold=high_threshold,
            low_threshold=low_threshold,
            check_interval=check_interval
        )
        app.run()
    except Exception as e:
        import traceback
        traceback.print_exc()
        if not isinstance(e, SystemExit):
            from tkinter import messagebox
            messagebox.showerror("启动失败", f"应用启动时发生异常: {e}")
        sys.exit(1)
