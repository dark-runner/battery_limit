"""
Production API Server with Real Battery Information and Smart Device Control
"""

import sys
from pathlib import Path
import logging
from datetime import datetime
import json
import psutil
import threading
import time
from typing import Dict, Any, Optional

# Add src directory to path
SRC_DIR = Path(__file__).parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from flask import Flask, jsonify, render_template_string, request
from config import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class BatteryController:
    """Real battery and device controller"""
    
    def __init__(self, config: Config):
        self.config = config
        self.mihome_controller = None
        self.running = False
        self.lock = threading.Lock()
        self.last_error = None
        self.switch_state = None
        self.thresholds = {
            'high': config.get('thresholds.high', 80.0),
            'low': config.get('thresholds.low', 30.0)
        }
        self.auto_control_enabled = True
        self._init_mihome()
    
    def _init_mihome(self):
        """Initialize Xiaomi Home device connection"""
        try:
            ip = self.config.get('mihome.ip')
            token = self.config.get('mihome.token')
            
            if not ip or ip == '192.168.1.100' or not token or token == '0' * 32:
                logger.warning("Xiaomi Home device not configured. Please configure IP and Token.")
                self.last_error = "设备未配置"
                return
            
            from mihome_controller import MihomeController
            self.mihome_controller = MihomeController(ip=ip, token=token)
            logger.info(f"Xiaomi Home device connected: {ip}")
            self.last_error = None
        except Exception as e:
            logger.error(f"Failed to connect to Xiaomi Home device: {e}")
            self.last_error = str(e)
    
    def get_battery_info(self) -> Dict[str, Any]:
        """Get real battery information"""
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return {
                    'level': 0,
                    'percent': 0,
                    'plugged': False,
                    'time_left': 0,
                    'is_charging': False,
                    'error': 'No battery detected'
                }
            
            return {
                'level': battery.percent,
                'percent': battery.percent,
                'plugged': battery.power_plugged,
                'time_left': battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else -1,
                'is_charging': battery.power_plugged,
                'error': None
            }
        except Exception as e:
            logger.error(f"Error getting battery info: {e}")
            return {
                'level': 0,
                'percent': 0,
                'plugged': False,
                'time_left': 0,
                'is_charging': False,
                'error': str(e)
            }
    
    def get_switch_state(self) -> Optional[bool]:
        """Get current switch state from device"""
        if not self.mihome_controller:
            return None
        
        try:
            state = self.mihome_controller.is_on()
            with self.lock:
                self.switch_state = state
            return state
        except Exception as e:
            logger.error(f"Error getting switch state: {e}")
            return None
    
    def set_switch_on(self) -> bool:
        """Turn on the smart switch"""
        if not self.mihome_controller:
            return False
        
        try:
            result = self.mihome_controller.turn_on()
            with self.lock:
                self.switch_state = True
            logger.info("Smart switch turned ON")
            return True
        except Exception as e:
            logger.error(f"Error turning on switch: {e}")
            return False
    
    def set_switch_off(self) -> bool:
        """Turn off the smart switch"""
        if not self.mihome_controller:
            return False
        
        try:
            result = self.mihome_controller.turn_off()
            with self.lock:
                self.switch_state = False
            logger.info("Smart switch turned OFF")
            return True
        except Exception as e:
            logger.error(f"Error turning off switch: {e}")
            return False
    
    def update_thresholds(self, high: float, low: float):
        """Update battery thresholds"""
        with self.lock:
            self.thresholds['high'] = high
            self.thresholds['low'] = low
        logger.info(f"Thresholds updated: high={high}, low={low}")
    
    def update_config(self, ip: str, token: str):
        """Update device configuration"""
        try:
            self.config.set('mihome.ip', ip)
            self.config.set('mihome.token', token)
            self.config.save()
            self._init_mihome()
            logger.info(f"Device configuration updated: {ip}")
            return True
        except Exception as e:
            logger.error(f"Error updating configuration: {e}")
            return False
    
    def auto_control_loop(self):
        """Automatic battery control loop"""
        while self.running:
            try:
                battery = self.get_battery_info()
                if battery['error']:
                    time.sleep(self.config.get('check_interval', 60))
                    continue
                
                percent = battery['percent']
                
                if self.auto_control_enabled and self.mihome_controller:
                    with self.lock:
                        high_threshold = self.thresholds['high']
                        low_threshold = self.thresholds['low']
                    
                    if percent >= high_threshold and self.switch_state:
                        logger.info(f"Battery {percent}% >= {high_threshold}%, turning off switch")
                        self.set_switch_off()
                    elif percent <= low_threshold and not self.switch_state:
                        logger.info(f"Battery {percent}% <= {low_threshold}%, turning on switch")
                        self.set_switch_on()
                
                time.sleep(self.config.get('check_interval', 60))
            except Exception as e:
                logger.error(f"Error in auto control loop: {e}")
                time.sleep(10)
    
    def start(self):
        """Start controller"""
        self.running = True
        self.get_switch_state()  # Initial state
        thread = threading.Thread(target=self.auto_control_loop, daemon=True)
        thread.start()
        logger.info("Battery controller started")
    
    def stop(self):
        """Stop controller"""
        self.running = False
        logger.info("Battery controller stopped")

app = Flask(__name__)
config = Config()
controller = BatteryController(config)

# Enhanced HTML Dashboard
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>电池限制管理 - Battery Limit Manager</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .header p {
            font-size: 1em;
            opacity: 0.9;
        }
        
        .main-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 25px;
            margin-bottom: 30px;
        }
        
        .card {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            transition: transform 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-3px);
        }
        
        .card h2 {
            color: #333;
            margin-bottom: 20px;
            font-size: 1.3em;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        
        .battery-display {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        }
        
        .battery-circle {
            width: 150px;
            height: 150px;
            border-radius: 50%;
            background: conic-gradient(
                #4CAF50 0deg,
                #4CAF50 calc(var(--percentage) * 3.6deg),
                #e0e0e0 calc(var(--percentage) * 3.6deg),
                #e0e0e0 360deg
            );
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .battery-inner {
            width: 140px;
            height: 140px;
            border-radius: 50%;
            background: white;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
        }
        
        .battery-level {
            font-size: 2.5em;
            font-weight: bold;
            color: #333;
        }
        
        .battery-info {
            flex: 1;
            margin-left: 30px;
        }
        
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }
        
        .info-row:last-child {
            border-bottom: none;
        }
        
        .info-label {
            color: #666;
            font-weight: 500;
        }
        
        .info-value {
            color: #333;
            font-weight: bold;
        }
        
        .status-online {
            color: #4CAF50;
        }
        
        .status-offline {
            color: #f44336;
        }
        
        .button-group {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }
        
        button {
            flex: 1;
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            font-size: 1em;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .btn-on {
            background: #4CAF50;
            color: white;
        }
        
        .btn-on:hover {
            background: #45a049;
            transform: scale(1.02);
        }
        
        .btn-off {
            background: #f44336;
            color: white;
        }
        
        .btn-off:hover {
            background: #da190b;
            transform: scale(1.02);
        }
        
        .settings-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .input-group {
            display: flex;
            flex-direction: column;
        }
        
        .input-group label {
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
            font-size: 0.9em;
        }
        
        input[type="text"],
        input[type="number"] {
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 0.95em;
            transition: border-color 0.3s ease;
        }
        
        input[type="text"]:focus,
        input[type="number"]:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 5px rgba(102, 126, 234, 0.3);
        }
        
        .btn-save {
            background: #667eea;
            color: white;
            margin-top: 15px;
        }
        
        .btn-save:hover {
            background: #5568d3;
        }
        
        .status-message {
            padding: 12px;
            margin-top: 10px;
            border-radius: 6px;
            font-size: 0.9em;
        }
        
        .status-success {
            background: #c8e6c9;
            color: #2e7d32;
            border: 1px solid #2e7d32;
        }
        
        .status-error {
            background: #ffcdd2;
            color: #c62828;
            border: 1px solid #c62828;
        }
        
        .full-width {
            grid-column: 1 / -1;
        }
        
        .threshold-display {
            background: #f5f5f5;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
        }
        
        .threshold-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
        }
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.4);
        }
        
        .modal.show {
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .modal-content {
            background-color: white;
            padding: 30px;
            border-radius: 15px;
            max-width: 500px;
            width: 90%;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        
        .modal-header {
            font-size: 1.3em;
            font-weight: bold;
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        
        .close-btn {
            position: absolute;
            top: 20px;
            right: 20px;
            font-size: 2em;
            cursor: pointer;
            color: #999;
        }
        
        .close-btn:hover {
            color: #333;
        }
        
        .footer {
            text-align: center;
            color: white;
            margin-top: 30px;
            opacity: 0.8;
            font-size: 0.9em;
        }
        
        @media (max-width: 1024px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔋 电池限制管理系统</h1>
            <p>Battery Limit Manager - 智能电池充电控制</p>
        </div>
        
        <div class="main-grid">
            <!-- Battery Status Card -->
            <div class="card">
                <h2>🔋 电池状态</h2>
                <div class="battery-display">
                    <div class="battery-circle" style="--percentage: var(--battery-level)">
                        <div class="battery-inner">
                            <div class="battery-level" id="batteryLevel">--</div>
                        </div>
                    </div>
                    <div class="battery-info">
                        <div class="info-row">
                            <span class="info-label">当前电量</span>
                            <span class="info-value" id="batteryPercent">-- %</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">充电状态</span>
                            <span class="info-value" id="chargeStatus">检测中...</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">剩余时间</span>
                            <span class="info-value" id="timeRemaining">-- </span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">更新时间</span>
                            <span class="info-value" id="updateTime">刚刚</span>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Device Control Card -->
            <div class="card">
                <h2>⚙️ 智能开关</h2>
                <div style="text-align: center; margin: 30px 0;">
                    <div style="font-size: 4em; margin-bottom: 15px;" id="deviceIcon">❓</div>
                    <div style="font-size: 1.1em; color: #666; margin-bottom: 20px;" id="deviceStatus">
                        连接中...
                    </div>
                </div>
                <div class="button-group">
                    <button class="btn-on" onclick="turnOn()">✓ 打开</button>
                    <button class="btn-off" onclick="turnOff()">✗ 关闭</button>
                </div>
                <div id="deviceMessage"></div>
            </div>
            
            <!-- Settings Card -->
            <div class="card full-width">
                <h2>⚙️ 系统设置</h2>
                <div class="settings-grid">
                    <div class="input-group">
                        <label>米家设备 IP</label>
                        <input type="text" id="deviceIP" placeholder="192.168.1.100">
                    </div>
                    <div class="input-group">
                        <label>设备 Token (32位)</label>
                        <input type="text" id="deviceToken" placeholder="输入32位十六进制token">
                    </div>
                    <div class="input-group">
                        <label>高电量阈值 (%)</label>
                        <input type="number" id="highThreshold" min="0" max="100" step="1" value="80">
                    </div>
                    <div class="input-group">
                        <label>低电量阈值 (%)</label>
                        <input type="number" id="lowThreshold" min="0" max="100" step="1" value="30">
                    </div>
                </div>
                
                <div class="threshold-display">
                    <div class="threshold-item">
                        <span>自动控制模式</span>
                        <span id="autoControlStatus">启用</span>
                    </div>
                    <div class="threshold-item">
                        <span>当前规则</span>
                        <span>电量 ≥ <span id="displayHigh">80</span>% 时关闭 | 电量 ≤ <span id="displayLow">30</span>% 时打开</span>
                    </div>
                </div>
                
                <button class="btn-save" onclick="saveSettings()">💾 保存设置</button>
                <div id="settingsMessage"></div>
            </div>
        </div>
        
        <div class="footer">
            <p>© 2026 Battery Limit Manager | 智能电池充电控制系统</p>
            <p>Version 1.0 | Running on Windows</p>
        </div>
    </div>
    
    <script>
        function formatTime(seconds) {
            if (seconds < 0) return '未知';
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            if (hours > 0) {
                return `${hours}小时${minutes}分钟`;
            }
            return `${minutes}分钟`;
        }
        
        function updateUI() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    // Update battery info
                    const percent = data.battery.percent;
                    document.getElementById('batteryLevel').textContent = Math.round(percent) + '%';
                    document.getElementById('batteryPercent').textContent = percent.toFixed(1) + ' %';
                    document.documentElement.style.setProperty('--battery-level', percent);
                    
                    // Update charge status
                    if (data.battery.is_charging) {
                        document.getElementById('chargeStatus').textContent = '🔌 充电中';
                        document.getElementById('chargeStatus').style.color = '#4CAF50';
                    } else {
                        document.getElementById('chargeStatus').textContent = '🔋 放电中';
                        document.getElementById('chargeStatus').style.color = '#ff9800';
                    }
                    
                    // Update time remaining
                    if (data.battery.time_left > 0) {
                        document.getElementById('timeRemaining').textContent = formatTime(data.battery.time_left);
                    } else {
                        document.getElementById('timeRemaining').textContent = '计算中...';
                    }
                    
                    // Update device status
                    if (data.device_connected) {
                        document.getElementById('deviceIcon').textContent = data.switch_state ? '✓' : '✗';
                        const statusText = data.switch_state ? '智能开关已打开' : '智能开关已关闭';
                        document.getElementById('deviceStatus').textContent = statusText;
                        document.getElementById('deviceStatus').style.color = data.switch_state ? '#4CAF50' : '#f44336';
                    } else {
                        document.getElementById('deviceIcon').textContent = '❌';
                        document.getElementById('deviceStatus').textContent = data.device_error || '设备未连接';
                        document.getElementById('deviceStatus').style.color = '#f44336';
                    }
                    
                    // Update time
                    const now = new Date();
                    const time = new Date(data.timestamp);
                    const diff = Math.floor((now - time) / 1000);
                    if (diff < 60) {
                        document.getElementById('updateTime').textContent = '刚刚';
                    } else {
                        document.getElementById('updateTime').textContent = Math.floor(diff / 60) + '分钟前';
                    }
                    
                    // Load settings
                    document.getElementById('deviceIP').value = data.config.ip || '';
                    document.getElementById('deviceToken').value = data.config.token || '';
                    document.getElementById('highThreshold').value = data.thresholds.high;
                    document.getElementById('lowThreshold').value = data.thresholds.low;
                    document.getElementById('displayHigh').textContent = data.thresholds.high;
                    document.getElementById('displayLow').textContent = data.thresholds.low;
                })
                .catch(error => {
                    console.error('Error:', error);
                    document.getElementById('deviceStatus').textContent = '连接错误';
                });
        }
        
        function turnOn() {
            fetch('/api/switch/on', { method: 'POST' })
                .then(() => {
                    showMessage('deviceMessage', '✓ 已发送打开命令', 'success');
                    setTimeout(updateUI, 1000);
                })
                .catch(error => {
                    showMessage('deviceMessage', '✗ 发送失败: ' + error, 'error');
                });
        }
        
        function turnOff() {
            fetch('/api/switch/off', { method: 'POST' })
                .then(() => {
                    showMessage('deviceMessage', '✓ 已发送关闭命令', 'success');
                    setTimeout(updateUI, 1000);
                })
                .catch(error => {
                    showMessage('deviceMessage', '✗ 发送失败: ' + error, 'error');
                });
        }
        
        function saveSettings() {
            const data = {
                ip: document.getElementById('deviceIP').value,
                token: document.getElementById('deviceToken').value,
                high_threshold: parseFloat(document.getElementById('highThreshold').value),
                low_threshold: parseFloat(document.getElementById('lowThreshold').value)
            };
            
            fetch('/api/config/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    showMessage('settingsMessage', '✓ 设置已保存', 'success');
                    setTimeout(updateUI, 1000);
                } else {
                    showMessage('settingsMessage', '✗ 保存失败: ' + result.message, 'error');
                }
            })
            .catch(error => {
                showMessage('settingsMessage', '✗ 保存失败: ' + error, 'error');
            });
        }
        
        function showMessage(elementId, message, type) {
            const el = document.getElementById(elementId);
            el.textContent = message;
            el.className = 'status-message status-' + type;
            if (type === 'success') {
                setTimeout(() => {
                    el.textContent = '';
                    el.className = '';
                }, 3000);
            }
        }
        
        // Initial update
        updateUI();
        
        // Update every 2 seconds
        setInterval(updateUI, 2000);
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    """Main dashboard"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
def get_status():
    """Get current status"""
    battery = controller.get_battery_info()
    switch_state = controller.switch_state
    
    return jsonify({
        'battery': {
            'percent': battery['percent'],
            'is_charging': battery['is_charging'],
            'time_left': battery['time_left'],
            'level': battery['level']
        },
        'device_connected': controller.mihome_controller is not None and controller.last_error is None,
        'device_error': controller.last_error,
        'switch_state': switch_state if switch_state is not None else False,
        'thresholds': controller.thresholds,
        'config': {
            'ip': config.get('mihome.ip', ''),
            'token': config.get('mihome.token', '')
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/switch/on', methods=['POST'])
def switch_on():
    """Turn on switch"""
    success = controller.set_switch_on()
    return jsonify({'success': success})

@app.route('/api/switch/off', methods=['POST'])
def switch_off():
    """Turn off switch"""
    success = controller.set_switch_off()
    return jsonify({'success': success})

@app.route('/api/config/update', methods=['POST'])
def update_config():
    """Update configuration"""
    try:
        data = request.json
        controller.update_config(data['ip'], data['token'])
        controller.update_thresholds(data['high_threshold'], data['low_threshold'])
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/health')
def health():
    """Health check"""
    return jsonify({'status': 'ok'})

def main():
    """Main entry point"""
    try:
        logger.info("=" * 70)
        logger.info("🚀 Battery Limit Manager - Production Server Starting")
        logger.info("=" * 70)
        logger.info("📊 Dashboard: http://localhost:5000")
        logger.info("🔋 Using Real Battery Information")
        logger.info("=" * 70)
        
        controller.start()
        app.run(host='127.0.0.1', port=5000, debug=False)
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        controller.stop()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
