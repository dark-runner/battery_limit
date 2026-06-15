"""Battery Manager Module - 支持台式机降级运行版"""

import logging
import time
from typing import Optional, Dict, Any
import psutil

logger = logging.getLogger(__name__)


class BatteryManager:
    """管理系统电池相关操作"""

    def __init__(self):
        """初始化电池管理器"""
        self.max_charge_limit = 100

        # 探测电池，不抛出异常——无电池时降级为纯手动控制
        battery = psutil.sensors_battery()
        if battery is None:
            self.has_battery = False
            logger.warning("未检测到物理电池，应用切入【纯手动米家开关控制】降级模式")
        else:
            self.has_battery = True
            logger.info("物理电池探测成功")

    def get_battery_percentage(self) -> float:
        """获取当前电池电量百分比（无电池返回 -1.0）"""
        if not self.has_battery:
            return -1.0
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return -1.0
            return float(battery.percent)
        except Exception as e:
            logger.error(f"获取电池电量异常: {e}")
            return -1.0

    def get_battery_status(self) -> Dict[str, Any]:
        """获取详细电池状态"""
        if not self.has_battery:
            return {"percent": -1.0, "secsleft": -1, "power_plugged": True, "has_battery": False}
        battery = psutil.sensors_battery()
        if battery is None:
            return {"percent": -1.0, "secsleft": -1, "power_plugged": True, "has_battery": False}
        return {
            "percent": battery.percent,
            "secsleft": battery.secsleft,
            "power_plugged": battery.power_plugged,
            "timestamp": time.time(),
            "has_battery": True
        }

    def get_status(self) -> dict:
        """获取电池状态"""
        try:
            battery_info = self.get_battery_status()
            return {
                "max_charge_limit": self.max_charge_limit,
                "status": "ok",
                "has_battery": self.has_battery,
                "battery": battery_info
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "has_battery": self.has_battery
            }

    def set_charge_limit(self, limit: int) -> bool:
        """设置最大充电限制
        
        Args:
            limit: 充电限制百分比 (0-100)
            
        Returns:
            bool: 操作是否成功
        """
        if 0 <= limit <= 100:
            self.max_charge_limit = limit
            return True
        return False

    def is_charging(self) -> bool:
        """检查是否正在充电（无电池返回True）"""
        battery = psutil.sensors_battery()
        if battery is None:
            return True
        return battery.power_plugged
