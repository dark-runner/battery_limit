"""Battery Monitor and Auto Controller - 局部生命周期令牌（Event）防竞态条件版"""

import logging
import time
import threading
import sys
from pathlib import Path
from typing import Optional, Callable

# 添加当前程序所在目录到路径（支持 PyInstaller 打包）
if getattr(sys, 'frozen', False):
    SRC_DIR = Path(sys._MEIPASS) / "src"
else:
    SRC_DIR = Path(__file__).parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import psutil
from battery_manager import BatteryManager
from mihome_controller import MihomeController

logger = logging.getLogger(__name__)


class BatteryAutoController:
    """电池自动控制器 - 根据电池电量自动控制米家开关"""

    def __init__(
        self,
        mihome_ip: str,
        mihome_token: str,
        high_threshold: float = 80.0,
        low_threshold: float = 30.0,
        check_interval: int = 60
    ):
        self.battery_manager = BatteryManager()
        self.mihome_controller = MihomeController(ip=mihome_ip, token=mihome_token)

        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.check_interval = check_interval
        self._hysteresis = 2.0  # 死区克制震荡频率

        self.is_running = False
        self._lock = threading.Lock()

        # 全局大闸：用户手动点击"停止"或程序整体退出时使用
        self._global_stop_event = threading.Event()

        # 核心：当前活跃的工作线程专属局部生命周期令牌
        self._current_worker_stop_event: Optional[threading.Event] = None

        # 线程句柄
        self.monitor_thread: Optional[threading.Thread] = None
        self.watchdog_thread: Optional[threading.Thread] = None

        # 心跳与防御变量
        self._last_heartbeat = 0.0
        self._last_wall_time = 0.0
        self._heartbeat_timeout = 300.0  # 5分钟防死锁
        self._max_time_jump = 600.0     # 10分钟系统休眠判定

        # 状态缓存
        self._last_command: Optional[bool] = None
        self._battery_ok = psutil.sensors_battery() is not None

        # 异常熔断计数
        self._restart_count = 0
        self._restart_window_start = 0.0

        # 注册UI回调，由主线程注入（工作线程通过此回调安全通知UI）
        self.ui_error_callback: Optional[Callable[[str], None]] = None

        # 检测电池是否存在——无电池时仍可手动控制开关，自动阈值功能禁用
        if not self._battery_ok:
            logger.warning("未检测到系统电池，自动阈值功能已禁用，仍可手动控制米家开关")

        logger.info(
            f"已初始化电池自动控制器: "
            f"高阈值={high_threshold}%, "
            f"低阈值={low_threshold}%, "
            f"检查间隔={check_interval}秒"
        )

    def start(self) -> None:
        """启动监控+看门狗"""
        with self._lock:
            if self.is_running:
                logger.warning("监控已在运行中")
                return
            self.is_running = True
            self._global_stop_event.clear()

            # 为即将诞生的新一代工作线程创建专属生命周期令牌
            self._current_worker_stop_event = threading.Event()
            worker_stop_ref = self._current_worker_stop_event

            now = time.time()
            self._last_heartbeat = now
            self._last_wall_time = now
            self._restart_window_start = now
            self._restart_count = 0

        # 启动时主动获取开关真实状态，初始化死区基线
        try:
            current_switch_state = self.mihome_controller.is_on()
            if current_switch_state is not None:
                with self._lock:
                    self._last_command = current_switch_state
                logger.info(f"已同步米家开关真实状态: {'开启' if current_switch_state else '关闭'}")
        except Exception as e:
            logger.warning(f"获取开关初始状态失败: {e}，将在首次阈值触发时初始化")

        # 启动防假死看门狗
        self.watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True
        )
        self.watchdog_thread.start()

        # 启动工作流安全外壳，将属于它的 Event 引用以参数形式强绑定传下去
        self.monitor_thread = threading.Thread(
            target=self._start_monitor_safe,
            args=(worker_stop_ref,),
            daemon=True
        )
        self.monitor_thread.start()

        logger.info("电池自动控制+看门狗已启动，生命周期令牌已绑定")

    def stop(self) -> None:
        """停止监控（强制唤醒所有等待）"""
        logger.info("正在停止电池自动控制...")
        self._global_stop_event.set()

        with self._lock:
            self.is_running = False
            # 顺着引用把当前的后台线程一并下毒退出
            if self._current_worker_stop_event:
                self._current_worker_stop_event.set()
                self._current_worker_stop_event = None

        self.mihome_controller.disconnect()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        if self.watchdog_thread and self.watchdog_thread.is_alive():
            self.watchdog_thread.join(timeout=2)
        logger.info("电池自动控制已停止")

    def _start_monitor_safe(self, my_stop_event: threading.Event):
        """外壳包装：异常崩溃自动恢复（持有局部停止令牌）"""
        while not self._global_stop_event.is_set() and not my_stop_event.is_set():
            try:
                t = threading.Thread(target=self._monitor_loop, args=(my_stop_event,), daemon=True)
                t.start()
                while t.is_alive() and not self._global_stop_event.is_set() and not my_stop_event.is_set():
                    t.join(timeout=1)
            except Exception as e:
                logger.error(f"核心工作流抛出未捕获异常: {e}，将在10秒后重试...")
                time.sleep(10)
            time.sleep(0.5)

    def _monitor_loop(self, my_stop_event: threading.Event):
        """核心监控循环（完全摆脱全局整数代数竞争）"""
        logger.debug("工作监控核心已就绪")

        # 首次启动：主动同步一次开关状态，实现平滑死区过渡
        self._sync_initial_switch_status()

        # 无电池时：挂起监控循环，不执行任何自动控制，保持线程存活
        if not self._battery_ok:
            logger.warning("无电池环境，监控线程进入挂起模式（仍可手动控制开关）")
            while not self._global_stop_event.is_set() and not my_stop_event.is_set():
                with self._lock:
                    if not self.is_running:
                        break
                for _ in range(30):
                    if self._global_stop_event.is_set() or my_stop_event.is_set():
                        return
                    time.sleep(1)
                    with self._lock:
                        self._last_heartbeat = time.time()
            return

        while not self._global_stop_event.is_set() and not my_stop_event.is_set():
            with self._lock:
                if not self.is_running:
                    break
                self._last_heartbeat = time.time()
                hi = self.high_threshold
                lo = self.low_threshold
                interval = self.check_interval

            try:
                self._check_and_control_with_hysteresis(hi, lo)
            except Exception as e:
                logger.error(f"监控循环异常: {e}")

            for _ in range(int(interval)):
                if self._global_stop_event.is_set() or my_stop_event.is_set():
                    return
                time.sleep(1)

    def _sync_initial_switch_status(self):
        """首次运行时同步开关真实状态，初始化死区基线"""
        try:
            status = self.mihome_controller.is_on()
            if status is not None:
                with self._lock:
                    self._last_command = status
                logger.info(f"成功同步初始智能插座硬件状态: {'开启' if status else '关闭'}")
        except Exception as e:
            logger.debug(f"初始硬件状态同步未成功(不影响运行): {e}")

    def _check_and_control_with_hysteresis(self, hi: float, lo: float) -> None:
        """内敛型迟滞状态机：绝对不越界，死区内保持当前状态"""
        if not self._battery_ok:
            return
        try:
            pct = self.battery_manager.get_battery_percentage()
        except Exception as e:
            logger.error(f"无法读取系统电量: {e}")
            return

        if pct < 0:
            return

        with self._lock:
            last_cmd = self._last_command

        logger.debug(f"电量巡检: {pct}%, 状态: {last_cmd}")

        # ── 场景 1：冷启动（状态未知） ──
        if last_cmd is None:
            if pct >= hi:
                logger.info(f"冷启动触顶 ({pct}% >= {hi}%)，关闭充电")
                self._execute_switch_control(False)
            elif pct <= lo:
                logger.info(f"冷启动触底 ({pct}% <= {lo}%)，开启充电")
                self._execute_switch_control(True)
            else:
                # 中间态：按偏向初始化状态，等待触发边界
                mid = (hi + lo) / 2
                if pct > mid:
                    with self._lock:
                        self._last_command = True
                    logger.debug(f"冷启动中间态({pct}%)靠拢高水位，标记为充电中")
                else:
                    with self._lock:
                        self._last_command = False
                    logger.debug(f"冷启动中间态({pct}%)靠拢低水位，标记为放电中")
            return

        # ── 场景 2：正常运行状态机 ──
        if last_cmd is True:
            # 充电中：达到 hi 才关闭，绝不超限
            if pct >= hi:
                logger.info(f"📈 到达上限 ({pct}% >= {hi}%)，关闭充电")
                self._execute_switch_control(False)
            else:
                logger.debug(f"充电中 ({pct}% < {hi}%)，保持")
        else:
            # 放电中：跌到 lo 才开启，绝不超限
            if pct <= lo:
                logger.info(f"📉 到达下限 ({pct}% <= {lo}%)，开启充电")
                self._execute_switch_control(True)
            else:
                logger.debug(f"放电中 ({pct}% > {lo}%)，保持")

    def _execute_switch_control(self, turn_on: bool) -> None:
        """物理执行开关控制并更新缓存状态"""
        ok = self.mihome_controller.turn_on() if turn_on else self.mihome_controller.turn_off()
        if ok:
            with self._lock:
                self._last_command = turn_on
            logger.info(f"米家插座 -> {'开启充电' if turn_on else '关闭充电'}")
        else:
            logger.error(f"控制失败，将在下个周期重试（不更新状态缓存）")

    def _watchdog_loop(self):
        """看门狗：精准下毒 + 物理断开连接 + 阻塞等待旧线程离场"""
        logger.info("看门狗线程已启动，假死检测阈值5分钟，休眠跳变阈值10分钟")
        while not self._global_stop_event.is_set():
            for _ in range(30):
                if self._global_stop_event.is_set():
                    break
                time.sleep(1)

            with self._lock:
                if not self.is_running:
                    break
                now = time.time()

                # 防御系统休眠唤醒
                if now - self._last_wall_time > self._max_time_jump:
                    logger.info(f"检测到系统休眠唤醒，时间跳变{int(now - self._last_wall_time)}秒，重置心跳")
                    self._last_heartbeat = now
                    self._last_wall_time = now
                    continue
                self._last_wall_time = now
                dead_duration = now - self._last_heartbeat

            if dead_duration > self._heartbeat_timeout:
                logger.critical(f"检测到核心监控线程假死！已持续{int(dead_duration)}秒无心跳")

                old_monitor_thread = None

                with self._lock:
                    # 频率限制防护（熔断机制）
                    now = time.time()
                    if now - self._restart_window_start > 3600:
                        self._restart_count = 0
                        self._restart_window_start = now

                    self._restart_count += 1
                    if self._restart_count > 5:
                        logger.critical("触发熔断：1小时内连续假死重启超过5次，终止后台控制。")
                        self.is_running = False
                        callback = getattr(self, 'ui_error_callback', None)
                        if callback:
                            callback("监控线程假死次数过多，程序已停止")
                        break

                    # 1. 精准对旧工作线程的生命周期令牌下毒
                    if self._current_worker_stop_event:
                        logger.warning("看门狗已向当前活跃线程的专属 Event 下毒...")
                        self._current_worker_stop_event.set()

                    # 暂存旧线程句柄用于安全 join
                    old_monitor_thread = self.monitor_thread

                    # 2. 强行切断底层网络 Socket（物理关闭，旧线程会收到 OSError）
                    self.mihome_controller.disconnect()

                    # 3. 为下一代准备全新的干净 Event 令牌
                    self._current_worker_stop_event = threading.Event()
                    next_worker_stop_ref = self._current_worker_stop_event
                    self._last_heartbeat = now

                # 4. 在锁外等待旧线程完全退出，严防 Socket 句柄并发冲突与泄露
                if old_monitor_thread and old_monitor_thread.is_alive():
                    logger.warning("正在等待旧工作线程释放句柄资源并优雅离场...")
                    old_monitor_thread.join(timeout=5.0)
                    if old_monitor_thread.is_alive():
                        logger.error("警告：旧工作线程在物理切断 Socket 后 5 秒内仍未退出！")
                    else:
                        logger.info("旧工作线程已安全离场，资源已完全回收。")

                # 5. 此时旧线程已死，无任何残留句柄。安全拉起全新一代工作外壳
                self.monitor_thread = threading.Thread(
                    target=self._start_monitor_safe,
                    args=(next_worker_stop_ref,),
                    daemon=True
                )
                self.monitor_thread.start()
                logger.warning("新一代监控主线程已安全无泄露拉起。")

        logger.info("看门狗线程已正常退出")

    def get_current_status(self) -> dict:
        """获取当前状态

        Returns:
            dict: 包含电池和开关状态的字典
        """
        try:
            with self._lock:
                is_run = self.is_running
                hi = self.high_threshold
                lo = self.low_threshold
                last_cmd = self._last_command

            battery_status = self.battery_manager.get_battery_status()
            switch_status = self.mihome_controller.get_status()

            return {
                "status": "running" if is_run else "stopped",
                "battery": battery_status,
                "switch": switch_status,
                "running": is_run,
                "high_threshold": hi,
                "low_threshold": lo,
                "last_command": last_cmd
            }
        except Exception as e:
            logger.error(f"获取状态出错: {e}")
            return {"error": str(e)}

    def set_thresholds(
        self,
        high_threshold: Optional[float] = None,
        low_threshold: Optional[float] = None
    ) -> bool:
        """动态线程安全阈值调整"""
        with self._lock:
            new_high = self.high_threshold if high_threshold is None else high_threshold
            new_low = self.low_threshold if low_threshold is None else low_threshold

            if high_threshold is not None and not (0 <= high_threshold <= 100):
                logger.error("高阈值必须在0-100之间")
                return False
            if low_threshold is not None and not (0 <= low_threshold <= 100):
                logger.error("低阈值必须在0-100之间")
                return False
            if new_low >= new_high:
                logger.error(f"低阈值({new_low})必须小于高阈值({new_high})")
                return False

            if high_threshold is not None:
                self.high_threshold = high_threshold
            if low_threshold is not None:
                self.low_threshold = low_threshold

            logger.info(f"阈值已更新: 高={self.high_threshold}%, 低={self.low_threshold}%")
            return True
