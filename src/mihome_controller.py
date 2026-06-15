"""Mihome Smart Switch Controller"""

import logging
import socket as _socket
import threading
import time
from typing import Optional, Dict, Any, List

try:
    from miio import Device, DeviceException
    MIIO_AVAILABLE = True
except ImportError:
    MIIO_AVAILABLE = False
    Device = None
    DeviceException = Exception

logger = logging.getLogger(__name__)
_DEVICE_TIMEOUT = 10

class MihomeController:
    """米家智能开关控制器"""

    def __init__(self, ip: str = "", token: str = "", model: str = None):
        self.ip = ip or ""
        self.token = token or ""
        self.model = model or "Unknown"
        self.device = None  # noqa: PGH003
        self._available = MIIO_AVAILABLE and bool(ip and token)
        self._is_connected = False  # 动态物理连接状态，与 _available 解耦
        self._lock = threading.Lock()
        self._device_info: Optional[Dict] = None
        self._model_prefix: str = ""
        self._unsupported_props: set = set()
        self._unsupported_cmds: set = set()

        # ── 智能连接自适应退避 ──
        self._last_connect_fail_time = 0.0
        self._connect_fail_count = 0
        self._base_cooldown = 60      # 基础冷却60秒
        self._max_cooldown = 1800     # 最大延迟30分钟熔断

        if not MIIO_AVAILABLE:
            logger.warning("python-miio 未安装")
            return
        if not ip or not token:
            logger.info("米家设备未配置")

    def configure(self, ip: str, token: str, model: str = ""):
        self.ip = ip
        self.token = token
        self.model = model or self.model
        self._available = MIIO_AVAILABLE and bool(ip and token)
        self.device = None
        self._device_info = None
        self._model_prefix = ""
        self._unsupported_cmds.clear()
        self._unsupported_props.clear()

    def reset_cooldown(self) -> None:
        """强制重置所有连接冷却计数（供 GUI 刷新按钮调用）"""
        with self._lock:
            self._last_connect_fail_time = 0.0
            self._connect_fail_count = 0
            logger.info("米家连接冷却状态机已清空")

    def _get_current_cooldown(self) -> float:
        """根据失败次数计算当前应退避的秒数（指数退避）"""
        if self._connect_fail_count == 0:
            return 0.0
        backoff = self._base_cooldown * (2 ** min(self._connect_fail_count - 1, 5))
        return float(min(backoff, self._max_cooldown))

    def _connect(self, force: bool = False) -> bool:
        """
        内核连接逻辑
        Args:
            force: True代表用户手动操作或看门狗硬重启，无视冷却限制
        """
        if not self._available:
            return False

        if self.device is not None:
            return True

        now = time.time()
        current_cooldown = self._get_current_cooldown()

        # 后台流量且在冷却期内则拦截；force=True 时无视冷却
        if not force and current_cooldown > 0 and (now - self._last_connect_fail_time < current_cooldown):
            remaining = int(current_cooldown - (now - self._last_connect_fail_time))
            logger.debug(f"连接冷却中（指数退避），剩余{remaining}秒，跳过本次重试")
            return False

        with self._lock:
            try:
                self.device = Device(ip=self.ip, token=self.token,
                                     timeout=_DEVICE_TIMEOUT,
                                     model=self.model or None)
                info = self.device.send("miIO.info", [])
                if isinstance(info, dict):
                    self._device_info = info
                    detected = info.get("model", "")
                    if detected:
                        parts = detected.split(".")
                        self._model_prefix = ".".join(parts[:2]) if len(parts) >= 2 else detected
                        self.model = detected
                        logger.info(f"检测到设备型号: {detected}")
                self._connect_fail_count = 0
                self._last_connect_fail_time = 0.0
                self._is_connected = True
                logger.info(f"已连接: {self.ip} [{self.model}]")
                return True
            except Exception as e:
                self.device = None
                self._is_connected = False
                self._last_connect_fail_time = time.time()
                self._connect_fail_count += 1
                logger.error(f"连接失败 {self.ip} (累计{self._connect_fail_count}次): {e}")
                return False

    def _call_with_timeout(self, method: str, params=None) -> Any:
        if not self._available:
            raise RuntimeError("设备不可用")
        if self.device is None:
            if not self._connect():
                raise RuntimeError("无法连接设备")

        try:
            return self.device.send(method, params or [])
        except DeviceException:
            logger.warning(f"设备不支持命令: {method}")
            raise
        except Exception as e:
            logger.warning(f"设备调用 {method} 失败: {e}")
            self.device = None
            raise

    def _try_get_prop(self, *props) -> Optional[list]:
        """查询设备状态"""
        if not self._available:
            return None
        dev = self.device
        if dev is None:
            if not self._connect():
                return None
            dev = self.device

        # cuco.plug.v3: 先试 get_properties（MIoT），再试 miIO.info
        if self._model_prefix == "cuco.plug":
            for method, params in [
                ("get_properties", [{"siid": 2, "piid": 1}]),
                ("miIO.info", []),
            ]:
                try:
                    raw = dev.send(method, params)
                    if method == "get_properties":
                        if isinstance(raw, list) and len(raw) > 0:
                            item = raw[0] if isinstance(raw[0], dict) else {}
                            val = item.get("value")
                            if val is not None:
                                return [val]
                    elif method == "miIO.info":
                        if isinstance(raw, dict):
                            pm = raw.get("power_mode")
                            if pm is not None:
                                return [pm]
                except Exception:
                    continue
            return None

        # 标准 get_prop 方式
        try:
            if len(props) > 1:
                raw = dev.send("get_prop", list(props))
                if isinstance(raw, list) and len(raw) > 0:
                    return raw
        except Exception:
            pass
        for prop in props:
            if prop in self._unsupported_props:
                continue
            try:
                raw = dev.send("get_prop", [prop])
                if isinstance(raw, list) and len(raw) > 0:
                    return raw
            except DeviceException:
                self._unsupported_props.add(prop)
                continue
            except Exception:
                continue
        return None

    def _try_send_cmd(self, method: str, params=None) -> bool:
        try:
            self._call_with_timeout(method, params)
            return True
        except Exception:
            return False

    def turn_on(self, force: bool = True) -> bool:
        if force:
            self.reset_cooldown()
        for cmd, params in [
            ("set_properties", [{"siid": 2, "piid": 1, "value": True}]),
            ("set_properties", [{"siid": 2, "piid": 2, "value": True}]),
            ("set_power", ["on"]),
            ("on", []),
            ("power_on", []),
        ]:
            if self._try_send_cmd(cmd, params):
                logger.info(f"开关已开启")
                return True
        logger.warning("开启失败")
        return False

    def turn_off(self, force: bool = True) -> bool:
        if force:
            self.reset_cooldown()
        for cmd, params in [
            ("set_properties", [{"siid": 2, "piid": 1, "value": False}]),
            ("set_properties", [{"siid": 2, "piid": 2, "value": False}]),
            ("set_power", ["off"]),
            ("off", []),
            ("power_off", []),
        ]:
            if self._try_send_cmd(cmd, params):
                logger.info(f"开关已关闭")
                return True
        logger.warning("关闭失败")
        return False

    def get_status(self) -> Optional[Dict[str, Any]]:
        if not self._available:
            return {"available": False, "message": "python-miio 未安装或设备不可达"}
        try:
            result = self._call_with_timeout("miIO.info", [])
            info = result if isinstance(result, dict) else {}
            power = self._try_get_prop("power", "on")
            return {
                "available": True,
                "model": info.get("model", self.model),
                "fw_ver": info.get("fw_ver", ""),
                "power": power[0] if power else None,
                "message": "在线",
            }
        except Exception as e:
            return {"available": False, "message": str(e)}

    def is_on(self, force: bool = False) -> Optional[bool]:
        """获取设备开关状态"""
        if not self._available:
            return None
        if force:
            self.reset_cooldown()
        if self.device is None:
            if not self._connect(force=force):
                return None

        raw = self._try_get_prop("power", "on")
        if raw is not None and len(raw) > 0:
            val = raw[0]
            if isinstance(val, (int, float)):
                return val > 0
            s = str(val).lower()
            if s in ("on", "true", "1", "yes"):
                return True
            if s in ("off", "false", "0", "no"):
                return False

        if hasattr(self.device, 'status'):
            try:
                st = self.device.status()
                if hasattr(st, 'is_on'):
                    return st.is_on
            except Exception:
                pass
        return None

    def disconnect(self) -> None:
        """断开连接并重置冷却，支持 GUI 刷新按钮快速恢复"""
        with self._lock:
            if self.device:
                try:
                    logger.warning(f"正在强制关闭米家设备底层 Socket 连接... (IP: {self.ip})")
                    if hasattr(self.device, '_protocol') and self.device._protocol:
                        proto = self.device._protocol
                        if hasattr(proto, 'transport') and proto.transport:
                            if hasattr(proto.transport, 'close'):
                                proto.transport.close()
                        if hasattr(proto, 'socket') and proto.socket:
                            try:
                                proto.socket.close()
                            except Exception:
                                pass
                    for attr_name in dir(self.device):
                        attr = getattr(self.device, attr_name, None)
                        if attr is None:
                            continue
                        if hasattr(attr, 'close') and ('sock' in attr_name.lower() or 'net' in attr_name.lower()):
                            try:
                                attr.close()
                            except Exception:
                                pass
                except Exception as e:
                    logger.error(f"暴力关闭底层 Socket 失败 (不影响后续重置): {e}")
                finally:
                    self.device = None
                    self._device_info = None

            # 断开时重置冷却，方便 GUI 刷新按钮立即重连
            self._last_connect_fail_time = 0.0
            self._connect_fail_count = 0
            self._is_connected = False
            # 绝对不修改 _available——那是静态准入状态
            logger.info("米家设备控制器已完全释放重置，冷却已归零。")

    @property
    def available(self) -> bool:
        """环境与配置是否可用（静态，不受断连影响）"""
        return self._available

    @property
    def is_connected(self) -> bool:
        """当前是否已建立物理连接"""
        return self._is_connected and self.device is not None

    @property
    def device_model(self) -> str:
        if self._device_info:
            return self._device_info.get("model", self.model)
        return self.model


def _get_subnet_broadcast_addresses() -> List[str]:
    """动态获取本机所有活动网卡的定向广播地址"""
    broadcast_list = []
    try:
        import psutil as _psutil
        interfaces = _psutil.net_if_addrs()
        for _intf_name, intf_addresses in interfaces.items():
            for addr in intf_addresses:
                if addr.family == _socket.AF_INET and addr.address != "127.0.0.1":
                    if addr.broadcast:
                        broadcast_list.append(addr.broadcast)
                    elif addr.netmask and addr.address:
                        ip_parts = list(map(int, addr.address.split('.')))
                        mask_parts = list(map(int, addr.netmask.split('.')))
                        bcast_parts = [
                            (ip_parts[i] | (255 ^ mask_parts[i])) for i in range(4)
                        ]
                        broadcast_list.append(".".join(map(str, bcast_parts)))
    except Exception as e:
        logger.debug(f"通过 psutil 获取子网广播地址失败: {e}")
        try:
            hostname = _socket.gethostname()
            local_ip = _socket.gethostbyname(hostname)
            if local_ip and local_ip != "127.0.0.1":
                ip_prefix = ".".join(local_ip.split(".")[:3])
                broadcast_list.append(f"{ip_prefix}.255")
        except Exception:
            pass

    valid_broadcasts = list(set(b for b in broadcast_list if not b.startswith("127.")))
    logger.debug(f"探测到当前系统可用的子网定向广播目标: {valid_broadcasts}")
    return valid_broadcasts


def discover_devices(timeout: int = 5) -> List[Dict[str, str]]:
    """自愈式米家设备发现 - 有限广播 + 子网定向广播双轨探测"""
    results: List[Dict[str, str]] = []
    seen_ips: set = set()

    hello_packet = bytes.fromhex(
        '21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff'
    )
    port = 54321

    try:
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)

        # 第一轮：全局有限广播
        logger.info("发送第一轮全局有限广播 (255.255.255.255)...")
        sock.sendto(hello_packet, ('255.255.255.255', port))

        start_time = time.time()
        deadline = start_time + timeout
        subnet_bcast_sent = False

        while time.time() < deadline:
            try:
                _, addr = sock.recvfrom(1024)
                if addr[0] not in seen_ips:
                    seen_ips.add(addr[0])
                    results.append({"ip": addr[0], "token": "", "model": "", "name": ""})
                    logger.info(f"发现设备: {addr[0]}")
            except _socket.timeout:
                pass

            # 如果时间已过 40% 且结果不足，触发子网定向广播
            elapsed = time.time() - start_time
            if not subnet_bcast_sent and elapsed > timeout * 0.4:
                subnet_broadcasts = _get_subnet_broadcast_addresses()
                if subnet_broadcasts:
                    logger.warning(f"全局广播响应不足，启动子网定向广播: {subnet_broadcasts}")
                    for bcast_ip in subnet_broadcasts:
                        try:
                            sock.sendto(hello_packet, (bcast_ip, port))
                        except Exception as ex:
                            logger.debug(f"向 {bcast_ip} 发包失败: {ex}")
                else:
                    logger.debug("未获取到有效子网广播，尝试盲推默认网段")
                    try:
                        sock.sendto(hello_packet, ('192.168.1.255', port))
                        sock.sendto(hello_packet, ('192.168.31.255', port))
                    except Exception:
                        pass
                subnet_bcast_sent = True

        sock.close()

        # 查询设备详细信息
        for r in results:
            try:
                dev = Device(ip=r["ip"], token="", timeout=3)
                info = dev.send("miIO.info", [])
                if isinstance(info, dict):
                    r["model"] = info.get("model", "")
                    r["name"] = info.get("model", "")
            except Exception:
                pass
    except Exception as e:
        logger.error(f"局域网扫描发生错误: {e}")

    logger.info(f"设备发现完成，共找到 {len(results)} 台设备")
    return results
