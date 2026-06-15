"""
Demo API Server with Mock Data - For visualization without physical Xiaomi devices
"""

import sys
from pathlib import Path
import logging
from datetime import datetime
import json

# Add src directory to path
SRC_DIR = Path(__file__).parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from flask import Flask, jsonify, render_template_string
import threading
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Mock data storage
class MockController:
    def __init__(self):
        self.battery_level = 65.0
        self.switch_state = True
        self.is_charging = True
        self.running = True
        self.lock = threading.Lock()
        
    def update_battery(self):
        """Simulate battery level changes"""
        while self.running:
            time.sleep(5)
            with self.lock:
                if self.is_charging:
                    self.battery_level = min(100.0, self.battery_level + 0.5)
                    if self.battery_level >= 80:
                        self.switch_state = False
                else:
                    self.battery_level = max(0.0, self.battery_level - 0.3)
                    if self.battery_level <= 30:
                        self.switch_state = True
    
    def start(self):
        """Start battery simulation"""
        thread = threading.Thread(target=self.update_battery, daemon=True)
        thread.start()
    
    def stop(self):
        """Stop battery simulation"""
        self.running = False
    
    def get_status(self):
        with self.lock:
            return {
                "battery_level": round(self.battery_level, 1),
                "switch_state": self.switch_state,
                "is_charging": self.is_charging,
                "timestamp": datetime.now().isoformat()
            }

app = Flask(__name__)
controller = MockController()

# HTML Dashboard
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
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            width: 100%;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 40px;
        }
        
        .header h1 {
            font-size: 3em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .header p {
            font-size: 1.1em;
            opacity: 0.9;
        }
        
        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 30px;
            margin-bottom: 30px;
        }
        
        .card {
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 50px rgba(0,0,0,0.3);
        }
        
        .card h2 {
            color: #333;
            margin-bottom: 20px;
            font-size: 1.3em;
        }
        
        .battery-circle {
            width: 180px;
            height: 180px;
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
            margin: 0 auto 20px;
            position: relative;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .battery-inner {
            width: 170px;
            height: 170px;
            border-radius: 50%;
            background: white;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
        }
        
        .battery-level {
            font-size: 3em;
            font-weight: bold;
            color: #333;
        }
        
        .battery-label {
            font-size: 0.9em;
            color: #999;
            margin-top: 5px;
        }
        
        .status-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 0;
            border-bottom: 1px solid #eee;
        }
        
        .status-item:last-child {
            border-bottom: none;
        }
        
        .status-label {
            color: #666;
            font-weight: 500;
        }
        
        .status-value {
            color: #333;
            font-weight: bold;
        }
        
        .switch-toggle {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 0;
        }
        
        .toggle-btn {
            width: 60px;
            height: 34px;
            background-color: #ccc;
            border-radius: 34px;
            position: relative;
            cursor: pointer;
            border: none;
            transition: 0.3s;
        }
        
        .toggle-btn.active {
            background-color: #4CAF50;
        }
        
        .toggle-btn::after {
            content: '';
            position: absolute;
            width: 26px;
            height: 26px;
            background-color: white;
            border-radius: 50%;
            top: 4px;
            left: 4px;
            transition: 0.3s;
        }
        
        .toggle-btn.active::after {
            left: 30px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        
        .stat-box {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            margin: 10px 0;
        }
        
        .stat-label {
            font-size: 0.9em;
            opacity: 0.9;
        }
        
        .charging-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            background-color: #FF9800;
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .footer {
            text-align: center;
            color: white;
            margin-top: 40px;
            opacity: 0.8;
        }
        
        .refresh-info {
            text-align: center;
            color: white;
            margin-top: 20px;
            font-size: 0.9em;
            opacity: 0.8;
        }
        
        @media (max-width: 768px) {
            .header h1 {
                font-size: 2em;
            }
            
            .dashboard {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔋 电池限制管理</h1>
            <p>Battery Limit Manager - 智能电池充电控制系统</p>
        </div>
        
        <div class="dashboard">
            <!-- Battery Status Card -->
            <div class="card">
                <h2>🔋 电池状态</h2>
                <div class="battery-circle" style="--percentage: var(--battery-level)">
                    <div class="battery-inner">
                        <div class="battery-level" id="batteryLevel">65%</div>
                        <div class="battery-label">当前电量</div>
                    </div>
                </div>
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-label">充电状态</div>
                        <div class="stat-value" id="chargingStatus">🔌</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">开关状态</div>
                        <div class="stat-value" id="switchStatus">✓</div>
                    </div>
                </div>
            </div>
            
            <!-- Control Card -->
            <div class="card">
                <h2>⚙️ 控制面板</h2>
                <div class="switch-toggle">
                    <span class="status-label">智能开关</span>
                    <button class="toggle-btn active" id="switchBtn" onclick="toggleSwitch()"></button>
                </div>
                
                <div class="status-item">
                    <span class="status-label">设备连接</span>
                    <span class="status-value" id="deviceStatus">
                        <span class="charging-indicator"></span> 正常
                    </span>
                </div>
                
                <div class="status-item">
                    <span class="status-label">自动控制</span>
                    <span class="status-value">已启用</span>
                </div>
                
                <div class="status-item">
                    <span class="status-label">更新时间</span>
                    <span class="status-value" id="updateTime">刚刚</span>
                </div>
            </div>
            
            <!-- Thresholds Card -->
            <div class="card">
                <h2>⚠️ 阈值配置</h2>
                <div class="status-item">
                    <span class="status-label">高电量阈值</span>
                    <span class="status-value">80%</span>
                </div>
                <div class="status-item">
                    <span class="status-label">低电量阈值</span>
                    <span class="status-value">30%</span>
                </div>
                <div class="status-item">
                    <span class="status-label">检查间隔</span>
                    <span class="status-value">60秒</span>
                </div>
                <div class="status-item">
                    <span class="status-label">运行状态</span>
                    <span class="status-value" style="color: #4CAF50;">● 运行中</span>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>💡 Demo Mode - 演示模式</p>
            <p>演示数据每5秒自动更新</p>
        </div>
        
        <div class="refresh-info">
            🔄 实时更新中...
        </div>
    </div>
    
    <script>
        const status = {
            battery: 65,
            switchState: true,
            isCharging: true
        };
        
        function updateUI() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('batteryLevel').textContent = data.battery_level + '%';
                    document.documentElement.style.setProperty('--battery-level', data.battery_level);
                    
                    const switchBtn = document.getElementById('switchBtn');
                    if (data.switch_state) {
                        switchBtn.classList.add('active');
                        document.getElementById('switchStatus').textContent = '✓';
                    } else {
                        switchBtn.classList.remove('active');
                        document.getElementById('switchStatus').textContent = '✗';
                    }
                    
                    document.getElementById('chargingStatus').textContent = 
                        data.is_charging ? '🔌 充电中' : '🔋 放电中';
                    
                    // Update time
                    const time = new Date(data.timestamp);
                    const now = new Date();
                    const diff = Math.floor((now - time) / 1000);
                    if (diff < 60) {
                        document.getElementById('updateTime').textContent = '刚刚';
                    } else {
                        document.getElementById('updateTime').textContent = 
                            Math.floor(diff / 60) + ' 分钟前';
                    }
                })
                .catch(error => console.error('Error:', error));
        }
        
        function toggleSwitch() {
            fetch('/api/switch/toggle', { method: 'POST' })
                .then(() => updateUI())
                .catch(error => console.error('Error:', error));
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
    return jsonify(controller.get_status())

@app.route('/api/switch/toggle', methods=['POST'])
def toggle_switch():
    """Toggle switch state"""
    with controller.lock:
        controller.switch_state = not controller.switch_state
    return jsonify({"success": True, "switch_state": controller.switch_state})

@app.route('/api/health')
def health():
    """Health check"""
    return jsonify({"status": "ok"})

def main():
    """Main entry point"""
    try:
        logger.info("Starting Mock Battery Control API Server...")
        logger.info("=" * 60)
        logger.info("🚀 API Server is running!")
        logger.info("=" * 60)
        logger.info("📊 Open your browser and go to:")
        logger.info("   👉 http://localhost:5000")
        logger.info("=" * 60)
        logger.info("This is DEMO MODE - using simulated data")
        logger.info("Battery level will change automatically")
        logger.info("=" * 60)
        
        controller.start()
        app.run(host='0.0.0.0', port=5000, debug=False)
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        controller.stop()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
