"""Example usage of Battery Auto Controller

This file demonstrates how to use the BatteryAutoController in different ways.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import Config
from battery_auto_controller import BatteryAutoController
import logging


def setup_logging(config: Config) -> None:
    """设置日志"""
    logging.basicConfig(
        level=getattr(logging, config.get("logging.level", "INFO")),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.get("logging.file", "battery_control.log")),
            logging.StreamHandler(sys.stdout)
        ]
    )


def example_1_basic_usage():
    """示例 1：基础使用"""
    print("\n" + "="*50)
    print("示例 1: 基础使用")
    print("="*50)
    
    config = Config()
    setup_logging(config)
    
    # 创建控制器
    controller = BatteryAutoController(
        mihome_ip=config.get("mihome.ip"),
        mihome_token=config.get("mihome.token"),
        high_threshold=config.get("thresholds.high", 80.0),
        low_threshold=config.get("thresholds.low", 30.0),
        check_interval=config.get("check_interval", 60)
    )
    
    # 获取当前状态
    print("\n当前状态:")
    status = controller.get_current_status()
    import json
    print(json.dumps(status, indent=2, default=str))
    
    # 启动监控
    print("\n启动监控...")
    controller.start()
    
    # 运行 30 秒后停止
    import time
    print("监控运行中... (30 秒)")
    time.sleep(30)
    
    controller.stop()
    print("监控已停止")


def example_2_manual_control():
    """示例 2：手动控制开关"""
    print("\n" + "="*50)
    print("示例 2: 手动控制开关")
    print("="*50)
    
    config = Config()
    setup_logging(config)
    
    from mihome_controller import MihomeController
    
    controller = MihomeController(
        ip=config.get("mihome.ip"),
        token=config.get("mihome.token")
    )
    
    print("\n获取开关状态...")
    status = controller.get_status()
    print(f"状态: {status}")
    
    is_on = controller.is_on()
    print(f"开关已{'' if is_on else '未'}打开")
    
    # 切换开关
    print("\n切换开关...")
    if is_on:
        print("关闭开关...")
        result = controller.turn_off()
    else:
        print("打开开关...")
        result = controller.turn_on()
    
    print(f"操作结果: {'成功' if result else '失败'}")


def example_3_api_server():
    """示例 3：启动 Web API 服务器"""
    print("\n" + "="*50)
    print("示例 3: Web API 服务器")
    print("="*50)
    
    config = Config()
    setup_logging(config)
    
    from battery_auto_controller import BatteryAutoController
    from api_server import BatteryControlAPI
    
    # 创建控制器
    controller = BatteryAutoController(
        mihome_ip=config.get("mihome.ip"),
        mihome_token=config.get("mihome.token"),
        high_threshold=config.get("thresholds.high", 80.0),
        low_threshold=config.get("thresholds.low", 30.0),
        check_interval=config.get("check_interval", 60)
    )
    
    # 启动自动控制
    print("\n启动自动控制...")
    controller.start()
    
    # 创建并启动 API
    api = BatteryControlAPI(
        controller=controller,
        host=config.get("api.host", "0.0.0.0"),
        port=config.get("api.port", 5000)
    )
    
    print(f"\n启动 API 服务器: {config.get('api.host', '0.0.0.0')}:{config.get('api.port', 5000)}")
    print("API 文档: 查看 README.md 中的 API 接口文档")
    print("按 Ctrl+C 停止服务器")
    
    try:
        api.run(debug=config.get("api.debug", False))
    except KeyboardInterrupt:
        print("\n正在关闭...")
        controller.stop()
        print("已关闭")


def example_4_custom_monitoring():
    """示例 4：自定义监控"""
    print("\n" + "="*50)
    print("示例 4: 自定义监控")
    print("="*50)
    
    config = Config()
    setup_logging(config)
    
    from battery_manager import BatteryManager
    import time
    
    battery = BatteryManager()
    
    print("\n开始实时监控电池（按 Ctrl+C 停止）...")
    try:
        while True:
            battery_info = battery.get_battery_status()
            percent = battery_info["percent"]
            is_charging = battery_info["power_plugged"]
            
            status = "充电中" if is_charging else "放电中"
            print(f"电池: {percent:6.1f}% | 状态: {status}")
            
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n监控已停止")


def example_5_threshold_adjustment():
    """示例 5: 动态调整阈值"""
    print("\n" + "="*50)
    print("示例 5: 动态调整阈值")
    print("="*50)
    
    config = Config()
    setup_logging(config)
    
    from battery_auto_controller import BatteryAutoController
    
    controller = BatteryAutoController(
        mihome_ip=config.get("mihome.ip"),
        mihome_token=config.get("mihome.token"),
        high_threshold=80.0,
        low_threshold=30.0
    )
    
    print(f"\n初始阈值设置:")
    print(f"  高阈值: {controller.high_threshold}%")
    print(f"  低阈值: {controller.low_threshold}%")
    
    # 调整阈值
    print(f"\n调整阈值...")
    controller.set_thresholds(high_threshold=85, low_threshold=25)
    
    print(f"\n更新后的阈值设置:")
    print(f"  高阈值: {controller.high_threshold}%")
    print(f"  低阈值: {controller.low_threshold}%")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Battery Limit 使用示例"
    )
    parser.add_argument(
        "example",
        type=int,
        choices=[1, 2, 3, 4, 5],
        help="要运行的示例号 (1-5)"
    )
    
    args = parser.parse_args()
    
    examples = {
        1: example_1_basic_usage,
        2: example_2_manual_control,
        3: example_3_api_server,
        4: example_4_custom_monitoring,
        5: example_5_threshold_adjustment,
    }
    
    try:
        examples[args.example]()
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
