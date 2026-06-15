"""Configuration management for Battery Limit"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── 开机自启（注册表） ──────────────────────────────────
_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "BatteryLimitManager"


def _get_exe_path() -> str:
    """获取开机自启的命令行，所有路径统一加引号，兼容空格路径"""
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    else:
        script = os.path.join(os.path.dirname(__file__), "main.py")
        return f'"{sys.executable}" "{script}"'


def _autostart_path_valid() -> bool:
    """验证开机自启的路径是否有效"""
    if getattr(sys, 'frozen', False):
        return os.path.exists(sys.executable)
    else:
        script = os.path.join(os.path.dirname(__file__), "main.py")
        return os.path.exists(sys.executable) and os.path.exists(script)


def set_autostart(enable: bool) -> bool:
    """设置开机自启（HKCU 注册表 Run 项）"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                if not _autostart_path_valid():
                    logger.warning("开发模式下开机自启仅在当前环境有效，打包后自动适配")
                exe_cmd = _get_exe_path()
                winreg.SetValueEx(k, _AUTOSTART_NAME, 0, winreg.REG_SZ, exe_cmd)
            else:
                try:
                    winreg.DeleteValue(k, _AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        logger.error(f"设置开机自启失败: {e}")
        return False


def is_autostart_enabled() -> bool:
    """检查开机自启是否已开启"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, _AUTOSTART_NAME)
            return True
    except (FileNotFoundError, OSError):
        return False
    except Exception:
        return False


class Config:
    """配置管理类"""

    def __init__(self, config_file: str = "config.json"):
        """初始化配置
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config: Dict[str, Any] = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """从文件加载配置，如果文件不存在则返回默认配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载配置文件失败: {e}，使用默认配置")
                return self._get_default_config()
        return self._get_default_config()

    @staticmethod
    def _get_default_config() -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "mihome": {
                "ip": "",
                "token": "",
                "model": ""
            },
            "thresholds": {
                "high": 80.0,
                "low": 30.0
            },
            "check_interval": 60,
            "api": {
                "host": "0.0.0.0",
                "port": 5000,
                "debug": False
            },
            "autostart": False,
            "logging": {
                "level": "INFO",
                "file": "battery_control.log"
            }
        }

    def save(self) -> None:
        """原子写入配置（防崩溃损坏）"""
        tmp = self.config_file + ".tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            os.replace(tmp, self.config_file)
            print(f"配置已保存到 {self.config_file}")
        except Exception as e:
            print(f"保存配置失败: {e}")
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值
        
        Args:
            key: 配置键，支持点号分隔的嵌套键（如 'mihome.ip'）
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value

    def set(self, key: str, value: Any) -> None:
        """设置配置值
        
        Args:
            key: 配置键，支持点号分隔的嵌套键（如 'mihome.ip'）
            value: 新值
        """
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value

    def to_dict(self) -> Dict[str, Any]:
        """返回配置字典"""
        return self.config.copy()
