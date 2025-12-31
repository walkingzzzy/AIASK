#!/bin/bash

# 股票分析系统 - 前端启动脚本

echo "========================================"
echo "股票分析系统 - 前端服务启动中..."
echo "========================================"
echo ""

# 项目配置 - 使用脚本所在目录作为项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$PROJECT_DIR/packages/frontend"

# 检查前端目录是否存在
if [ ! -d "$FRONTEND_DIR" ]; then
    echo "❌ 错误: 前端目录不存在: $FRONTEND_DIR"
    exit 1
fi

# 切换到前端目录
cd "$FRONTEND_DIR" || {
    echo "❌ 错误: 无法切换到前端目录: $FRONTEND_DIR"
    exit 1
}
echo "📁 前端目录: $FRONTEND_DIR"
echo ""

# 检查 node_modules 是否存在
if [ ! -d "node_modules" ]; then
    echo "📦 首次运行，正在安装依赖..."
    echo "----------------------------------------"
    npm install || {
        echo "❌ 错误: 依赖安装失败"
        exit 1
    }
    echo ""
fi

echo "========================================"
echo "🚀 启动前端开发服务器"
echo "========================================"
echo ""
echo "💡 提示: 按 Ctrl+C 停止服务"
echo ""
echo "----------------------------------------"

# 启动前端开发服务器
npm run dev
