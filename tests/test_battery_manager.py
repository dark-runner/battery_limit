"""Test Battery Manager"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from battery_manager import BatteryManager


def test_battery_manager_initialization():
    """Test BatteryManager initialization"""
    manager = BatteryManager()
    assert manager.max_charge_limit == 100


def test_get_status():
    """Test get_status method"""
    manager = BatteryManager()
    status = manager.get_status()
    # 可能的状态键
    assert "status" in status


def test_set_charge_limit_valid():
    """Test set_charge_limit with valid input"""
    manager = BatteryManager()
    result = manager.set_charge_limit(80)
    assert result is True
    assert manager.max_charge_limit == 80


def test_set_charge_limit_invalid():
    """Test set_charge_limit with invalid input"""
    manager = BatteryManager()
    result = manager.set_charge_limit(150)
    assert result is False
    assert manager.max_charge_limit == 100


def test_battery_percentage():
    """Test get_battery_percentage method"""
    manager = BatteryManager()
    try:
        percentage = manager.get_battery_percentage()
        assert 0 <= percentage <= 100
    except RuntimeError:
        # 如果没有电池，这是预期的行为
        pass


def test_is_charging():
    """Test is_charging method"""
    manager = BatteryManager()
    result = manager.is_charging()
    assert isinstance(result, bool)
