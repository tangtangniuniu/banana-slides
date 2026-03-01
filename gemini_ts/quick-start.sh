#!/bin/bash

# Vertex AI 工具类快速启动脚本

echo "================================================"
echo "Vertex AI 工具类 (TypeScript) 快速启动"
echo "================================================"

# 检查是否安装了 pnpm
if ! command -v pnpm &> /dev/null; then
    echo "错误: 未检测到 pnpm"
    echo "请先安装 pnpm: npm install -g pnpm"
    exit 1
fi

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "警告: 未找到 .env 文件"
    echo "正在从 .env.example 创建 .env 文件..."
    cp .env.example .env
    echo "请编辑 .env 文件并配置你的 Vertex AI 凭据"
    echo ""
    echo "需要配置以下变量:"
    echo "  - VERTEX_PROJECT_ID"
    echo "  - VERTEX_LOCATION"
    echo "  - GOOGLE_APPLICATION_CREDENTIALS"
    echo ""
    read -p "按 Enter 继续，或按 Ctrl+C 退出..."
fi

# 检查代理设置
if [ -n "$HTTP_PROXY" ] || [ -n "$HTTPS_PROXY" ]; then
    echo ""
    echo "检测到代理设置:"
    [ -n "$HTTP_PROXY" ] && echo "  HTTP_PROXY=$HTTP_PROXY"
    [ -n "$HTTPS_PROXY" ] && echo "  HTTPS_PROXY=$HTTPS_PROXY"
    echo ""
fi

# 安装依赖（如果需要）
if [ ! -d "node_modules" ]; then
    echo "正在安装依赖..."
    pnpm install
fi

# 运行测试
echo "启动 Vertex AI 工具类测试..."
pnpm dev
