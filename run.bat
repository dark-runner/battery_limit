@echo off
REM Battery Limit - Windows 启动脚本

setlocal enabledelayedexpansion

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

REM 检查虚拟环境
if not exist "venv" (
    echo 创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 检查依赖
pip show psutil >nul 2>&1
if errorlevel 1 (
    echo 安装依赖...
    pip install -r requirements.txt
)

REM 显示菜单
:menu
cls
echo =====================================================
echo   Battery Limit - 电池限制管理工具
echo =====================================================
echo.
echo 请选择运行模式:
echo.
echo 1. 桌面GUI模式 (原生小窗监控界面) ⭐推荐
echo 2. Web API 模式 (启动 REST API 服务器)
echo 3. 查看日志
echo 4. 配置设置
echo 5. 运行测试
echo 6. 退出
echo.
set /p choice="请选择 [1-6]: "

if "%choice%"=="1" (
    cls
    echo 启动桌面GUI模式...
    python src/main.py
) else if "%choice%"=="2" (
    cls
    echo 启动 Web API 服务器...
    echo 访问地址: http://localhost:5000
    python src/api_server.py
) else if "%choice%"=="3" (
    cls
    if exist "battery_control.log" (
        type battery_control.log
    ) else (
        echo 日志文件不存在
    )
    pause
    goto menu
) else if "%choice%"=="4" (
    cls
    if exist "config.json" (
        notepad config.json
    ) else (
        echo 配置文件不存在
    )
    pause
    goto menu
) else if "%choice%"=="5" (
    cls
    echo 运行单元测试...
    python -m pytest tests/ -v
    pause
    goto menu
) else if "%choice%"=="6" (
    exit /b 0
) else (
    echo 无效选择，请重新选择
    pause
    goto menu
)

pause
goto menu
