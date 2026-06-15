# 🔋 Battery Limit Manager

**智能笔记本电池充电控制系统** — 原生桌面 GUI 应用

监控笔记本电池电量，通过米家智能开关自动控制充电，防止电池过充。  
**无电池的台式机也可作为米家开关桌面挂件使用（自动阈值禁用，手动控制正常）。**

## ✨ 功能

| 功能 | 说明 |
|------|------|
| 🔋 实时监控 | 持续监测电池电量，每 2 秒自动刷新 |
| 🎯 智能控制 | 电量 ≥ 高阈值自动断电，≤ 低阈值自动充电（内敛迟滞状态机，绝不越界） |
| 🏠 降级模式 | 无电池台式机自动切入纯手动模式，开关控制正常可用 |
| 🪟 原生桌面 | 玻璃质感深色主题，高 DPI 适配 |
| 🗔 系统托盘 | 关闭窗口 → 右下角继续运行（阻止系统睡眠，7×24 守护） |
| ⚙️ 设置页面 | 二级窗口配置所有参数 |
| ☁️ 小米云登录 | 支持二维码/密码登录 + 验证码/2FA，自动提取设备 Token |
| 🔍 局域网发现 | 有限广播 + 子网定向广播双轨探测，兼容 Mesh/AP 隔离路由器 |
| 🔄 开机自启 | 注册表 `HKCU\Run` 自启，开发/打包模式自动适配 |
| 🛡️ 崩溃自愈 | 看门狗 + 心跳检测，5 分钟无响应自动重启，指数退避防频繁重试 |

## 📦 快速开始

### 前置条件

- Python 3.8+
- Windows 10/11（依赖 Windows API 阻止睡眠）

### 安装与运行

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # 开发/打包依赖
python src/main.py
```

### 打包 EXE

```bash
python build_exe.py
```

输出：`dist\BatteryLimitManager.exe`（免 Python 环境运行，约 35 MB）

## ⚙️ 配置

通过 GUI「设置」页面或编辑 `config.json`：

```json
{
  "mihome": {
    "ip": "192.168.31.100",
    "token": "32位十六进制Token",
    "model": "cuco.plug.v3"
  },
  "thresholds": {
    "high": 80.0,
    "low": 30.0
  },
  "check_interval": 60,
  "autostart": false
}
```

### 获取设备 Token

1. 打开应用 → 设置 → 米家设备 →「小米云登录」
2. 选择账号区域（如 `cn`），点击「获取二维码」
3. 使用米家 App 扫描二维码授权
4. 自动获取设备列表，选择你的智能插座

## 📁 项目结构

```
src/
├── main.py                     # 入口（单实例 Mutex + atexit 句柄清理）
├── gui.py                      # 桌面界面（tkinter + pystray + ThreadPoolExecutor）
├── battery_manager.py          # 电池信息（支持无电池降级）
├── mihome_controller.py        # 米家控制（MIoT 协议 + 指数退避 + 硬关闭 Socket）
├── battery_auto_controller.py  # 自动逻辑（Event 令牌生命周期 + 内敛迟滞状态机 + 看门狗）
├── config.py                   # 配置管理（原子写入 + 开机自启）
├── micloud_helper.py           # 小米云 V2 API（RC4 加密 + 二维码/密码登录）
tests/
├── test_battery_manager.py     # 单元测试
build_exe.py                    # PyInstaller 打包脚本
icon.png / app.ico              # 应用图标
```

## 🔧 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| GUI | tkinter + pystray（系统托盘） |
| 电池 | psutil |
| 米家协议 | python-miio 0.5.12（MIoT `get_properties`/`set_properties`） |
| 云登录 | MiCloud V2 API（pycryptodome RC4） |
| 打包 | PyInstaller |
| 防崩溃 | 心跳检测 + 看门狗 + 局部 Event 令牌 + 指数退避 |

## 🏗️ 架构设计

### 线程模型

```
┌─ Main Process ─────────────────────────────────────────────┐
│                                                             │
│  ┌─ Main Thread (GUI) ────┐  ┌─ Monitor Thread ──────────┐ │
│  │  tkinter mainloop       │  │  _start_monitor_safe       │ │
│  │  ThreadPoolExecutor     │  │  └─ _monitor_loop         │ │
│  │  (max_workers=1)        │  │  (每60秒巡检 + 心跳更新)   │ │
│  └─────────────────────────┘  └────────────────────────────┘ │
│                                ┌─ Watchdog Thread ─────────┐ │
│                                │  _watchdog_loop            │ │
│                                │  (每30秒检查心跳，假死重启) │ │
│                                └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 关键机制

- **生命周期令牌**：每代线程持有独立 `threading.Event`，看门狗下毒旧线程、创建新 Event 传入新线程，零竞态
- **两段式物理断开**：看门狗先 `Event.set()` 通知退出，再反射关闭底层 Socket 击穿 IO 阻塞，最后 `join(timeout=5)` 等待句柄释放
- **内敛迟滞状态机**：`_last_command` 记录开关状态，充电到 `hi` 才停、放电到 `lo` 才开，`lo~hi` 整个区间为死区，绝不越界
- **连接冷却**：后台自动探测使用 `min(60 × 2^count, 1800)` 指数退避；用户手动操作 `force=True` 无视冷却

## 📄 许可

MIT
