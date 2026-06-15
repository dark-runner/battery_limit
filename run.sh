#!/bin/bash
# Battery Limit - Linux/macOS 启动脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 Python 3，请先安装 Python 3.8+${NC}"
    exit 1
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}创建虚拟环境...${NC}"
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 检查依赖
if ! python3 -c "import psutil" 2>/dev/null; then
    echo -e "${YELLOW}安装依赖...${NC}"
    pip install -r requirements.txt
fi

# 显示菜单
show_menu() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Battery Limit - 电池限制管理工具${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "请选择运行模式:"
    echo ""
    echo "1. 命令行模式 (后台运行监控)"
    echo "2. Web API 模式 (启动 REST API 服务器)"
    echo "3. 查看日志"
    echo "4. 配置设置"
    echo "5. 运行测试"
    echo "6. 退出"
    echo ""
}

# 主循环
while true; do
    clear
    show_menu
    read -p "请选择 [1-6]: " choice
    
    case $choice in
        1)
            clear
            echo -e "${YELLOW}启动电池限制管理工具...${NC}"
            python src/main.py
            ;;
        2)
            clear
            echo -e "${YELLOW}启动 Web API 服务器...${NC}"
            echo -e "${GREEN}访问地址: http://localhost:5000${NC}"
            python src/api_server.py
            ;;
        3)
            clear
            if [ -f "battery_control.log" ]; then
                tail -f battery_control.log
            else
                echo -e "${RED}日志文件不存在${NC}"
                read -p "按 Enter 继续..."
            fi
            ;;
        4)
            clear
            if [ -f "config.json" ]; then
                ${EDITOR:-nano} config.json
            else
                echo -e "${RED}配置文件不存在${NC}"
                read -p "按 Enter 继续..."
            fi
            ;;
        5)
            clear
            echo -e "${YELLOW}运行单元测试...${NC}"
            python -m pytest tests/ -v
            read -p "按 Enter 继续..."
            ;;
        6)
            echo -e "${GREEN}再见!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}无效选择，请重新选择${NC}"
            read -p "按 Enter 继续..."
            ;;
    esac
done
