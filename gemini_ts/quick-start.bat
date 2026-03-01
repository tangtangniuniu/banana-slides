@echo off
REM Vertex AI 工具类快速启动脚本 (Windows)

echo =================================================
echo Vertex AI 工具类 (TypeScript) 快速启动
echo =================================================

REM 检查是否安装了 pnpm
where pnpm >nul 2>nul
if %errorlevel% neq 0 (
    echo 错误: 未检测到 pnpm
    echo 请先安装 pnpm: npm install -g pnpm
    pause
    exit /b 1
)

REM 检查 .env 文件
if not exist ".env" (
    echo 警告: 未找到 .env 文件
    echo 正在从 .env.example 创建 .env 文件...
    copy .env.example .env
    echo 请编辑 .env 文件并配置你的 Vertex AI 凭据
    echo.
    echo 需要配置以下变量:
    echo   - VERTEX_PROJECT_ID
    echo   - VERTEX_LOCATION
    echo   - GOOGLE_APPLICATION_CREDENTIALS
    echo.
    pause
)

REM 检查代理设置
if defined HTTP_PROXY (
    echo.
    echo 检测到代理设置:
    echo   HTTP_PROXY=%HTTP_PROXY%
)
if defined HTTPS_PROXY (
    if not defined HTTP_PROXY echo.
    echo   HTTPS_PROXY=%HTTPS_PROXY%
)
if defined HTTP_PROXY or defined HTTPS_PROXY echo.

REM 安装依赖（如果需要）
if not exist "node_modules" (
    echo 正在安装依赖...
    call pnpm install
)

REM 运行测试
echo 启动 Vertex AI 工具类测试...
call pnpm dev

pause
