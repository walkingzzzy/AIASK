#!/bin/bash
# AIASK Desktop 启动脚本
# 同时启动 Desktop API 和前端开发服务器

echo "======================================"
echo "  AIASK Desktop V1 启动中..."
echo "======================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Python
echo -e "${YELLOW}[1/3]${NC} 检查 Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python 已就绪"

# 检查 Node.js
echo -e "${YELLOW}[2/3]${NC} 检查 Node.js..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js 未安装"
    exit 1
fi
echo -e "${GREEN}✓${NC} Node.js 已就绪"

# 检查依赖
echo -e "${YELLOW}[3/3]${NC} 检查依赖..."
cd packages/desktop-api
if [ ! -d ".venv" ]; then
    echo "  → 创建 Python 虚拟环境..."
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -e . 2>/dev/null
echo -e "${GREEN}✓${NC} Desktop API 依赖已安装"

cd ../../desktop
if [ ! -d "node_modules" ]; then
    echo "  → 安装前端依赖..."
    npm install --silent
fi
echo -e "${GREEN}✓${NC} 前端依赖已安装"

cd ..

# 启动服务
echo ""
echo "======================================"
echo "  启动服务..."
echo "======================================"

# 启动 Desktop API
echo -e "${GREEN}→${NC} Desktop API (http://127.0.0.1:8001)"
cd packages/desktop-api
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8001 > ../../logs/desktop-api.log 2>&1 &
DESKTOP_API_PID=$!
cd ../..

# 等待 Desktop API 启动
sleep 3

# 检查 Desktop API 健康状态
if curl -s http://127.0.0.1:8001/health > /dev/null; then
    echo -e "${GREEN}✓${NC} Desktop API 启动成功 (PID: $DESKTOP_API_PID)"
else
    echo -e "❌ Desktop API 启动失败"
    kill $DESKTOP_API_PID 2>/dev/null
    exit 1
fi

# 启动前端
echo -e "${GREEN}→${NC} Frontend (http://localhost:5173)"
cd desktop
npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo ""
echo "======================================"
echo -e "  ${GREEN}✓${NC} 所有服务已启动"
echo "======================================"
echo ""
echo "服务地址:"
echo "  • Desktop API: http://127.0.0.1:8001"
echo "  • Frontend:    http://localhost:5173"
echo "  • Health:      http://127.0.0.1:8001/health"
echo ""
echo "进程ID:"
echo "  • Desktop API: $DESKTOP_API_PID"
echo "  • Frontend:    $FRONTEND_PID"
echo ""
echo "日志文件:"
echo "  • Desktop API: logs/desktop-api.log"
echo "  • Frontend:    logs/frontend.log"
echo ""
echo "停止服务: kill $DESKTOP_API_PID $FRONTEND_PID"
echo ""
echo "======================================"

# 等待用户中断
trap "echo ''; echo '正在停止服务...'; kill $DESKTOP_API_PID $FRONTEND_PID 2>/dev/null; echo '已停止'; exit 0" INT TERM

# 保持脚本运行
wait
