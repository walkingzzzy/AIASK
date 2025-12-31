#!/bin/bash

# 股票分析系统 - 后端启动脚本

echo "========================================"
echo "股票分析系统 - 后端服务启动中..."
echo "========================================"
echo ""

# 项目配置 - 使用脚本所在目录作为项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONDA_ENV="stock-analyzer"
HOST="127.0.0.1"
PORT="8000"

# 切换到项目目录
cd "$PROJECT_DIR" || {
    echo "❌ 错误: 无法切换到项目目录: $PROJECT_DIR"
    exit 1
}
echo "📁 项目目录: $PROJECT_DIR"

# 初始化conda
if [ -f "/opt/miniconda3/etc/profile.d/conda.sh" ]; then
    source /opt/miniconda3/etc/profile.d/conda.sh
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
else
    echo "❌ 错误: 无法找到conda初始化脚本"
    exit 1
fi

# 激活conda环境
echo "🐍 激活conda环境: $CONDA_ENV"
conda activate "$CONDA_ENV" || {
    echo "❌ 错误: 无法激活conda环境: $CONDA_ENV"
    echo "   请确保环境已创建: conda create -n $CONDA_ENV python=3.11"
    exit 1
}

echo ""
echo "========================================"
echo "🚀 启动后端API服务"
echo "========================================"
echo ""
echo "📍 服务地址: http://$HOST:$PORT"
echo "📚 API文档: http://$HOST:$PORT/docs"
echo "📖 ReDoc文档: http://$HOST:$PORT/redoc"
echo ""
echo "💡 提示: 按 Ctrl+C 停止服务"
echo ""
echo "----------------------------------------"

# 启动后端服务
uvicorn packages.api.main:app --host "$HOST" --port "$PORT"