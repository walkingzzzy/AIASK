# AIASK Desktop 启动脚本 (Windows)
# 同时启动 Desktop API 和前端开发服务器

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  AIASK Desktop V1 启动中..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
Write-Host "[1/3] 检查 Python..." -ForegroundColor Yellow
$pythonPath = "F:\Python311\python.exe"
if (-not (Test-Path $pythonPath)) {
    Write-Host "❌ Python 未找到: $pythonPath" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Python 已就绪" -ForegroundColor Green

# 检查 Node.js
Write-Host "[2/3] 检查 Node.js..." -ForegroundColor Yellow
try {
    $null = Get-Command node -ErrorAction Stop
    Write-Host "✓ Node.js 已就绪" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js 未安装" -ForegroundColor Red
    exit 1
}

# 检查依赖
Write-Host "[3/3] 检查依赖..." -ForegroundColor Yellow

# Desktop API 依赖
Push-Location packages\desktop-api
if (-not (Test-Path ".venv")) {
    Write-Host "  → 创建 Python 虚拟环境..." -ForegroundColor Gray
    & $pythonPath -m venv .venv
}
Write-Host "✓ Desktop API 依赖已安装" -ForegroundColor Green
Pop-Location

# 前端依赖
Push-Location desktop
if (-not (Test-Path "node_modules")) {
    Write-Host "  → 安装前端依赖..." -ForegroundColor Gray
    npm install --silent
}
Write-Host "✓ 前端依赖已安装" -ForegroundColor Green
Pop-Location

# 创建日志目录
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

# 启动服务
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  启动服务..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# 启动 Desktop API
Write-Host "→ Desktop API (http://127.0.0.1:8001)" -ForegroundColor Green
Push-Location packages\desktop-api
$desktopApiJob = Start-Process -NoNewWindow -FilePath $pythonPath `
    -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8001" `
    -PassThru `
    -RedirectStandardOutput "..\..\logs\desktop-api.log" `
    -RedirectStandardError "..\..\logs\desktop-api-error.log"
$desktopApiPid = $desktopApiJob.Id
Pop-Location

# 等待 Desktop API 启动
Start-Sleep -Seconds 3

# 检查 Desktop API 健康状态
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health" -TimeoutSec 5
    if ($health.status -eq "healthy") {
        Write-Host "✓ Desktop API 启动成功 (PID: $desktopApiPid)" -ForegroundColor Green
    } else {
        throw "Health check failed"
    }
} catch {
    Write-Host "❌ Desktop API 启动失败" -ForegroundColor Red
    Stop-Process -Id $desktopApiPid -Force -ErrorAction SilentlyContinue
    exit 1
}

# 启动前端
Write-Host "→ Frontend (http://localhost:5173)" -ForegroundColor Green
Push-Location desktop
$frontendJob = Start-Process -NoNewWindow -FilePath "npm" `
    -ArgumentList "run", "dev" `
    -PassThru `
    -RedirectStandardOutput "..\logs\frontend.log" `
    -RedirectStandardError "..\logs\frontend-error.log"
$frontendPid = $frontendJob.Id
Pop-Location

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  ✓ 所有服务已启动" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "服务地址:" -ForegroundColor Cyan
Write-Host "  • Desktop API: http://127.0.0.1:8001"
Write-Host "  • Frontend:    http://localhost:5173"
Write-Host "  • Health:      http://127.0.0.1:8001/health"
Write-Host ""
Write-Host "进程ID:" -ForegroundColor Cyan
Write-Host "  • Desktop API: $desktopApiPid"
Write-Host "  • Frontend:    $frontendPid"
Write-Host ""
Write-Host "日志文件:" -ForegroundColor Cyan
Write-Host "  • Desktop API: logs\desktop-api.log"
Write-Host "  • Frontend:    logs\frontend.log"
Write-Host ""
Write-Host "停止服务:" -ForegroundColor Yellow
Write-Host "  Stop-Process -Id $desktopApiPid, $frontendPid -Force"
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "按 Ctrl+C 停止所有服务..." -ForegroundColor Gray

# 等待用户中断
try {
    while ($true) {
        Start-Sleep -Seconds 1

        # 检查进程是否还在运行
        if (-not (Get-Process -Id $desktopApiPid -ErrorAction SilentlyContinue)) {
            Write-Host ""
            Write-Host "❌ Desktop API 进程已停止" -ForegroundColor Red
            break
        }
        if (-not (Get-Process -Id $frontendPid -ErrorAction SilentlyContinue)) {
            Write-Host ""
            Write-Host "❌ Frontend 进程已停止" -ForegroundColor Red
            break
        }
    }
} finally {
    Write-Host ""
    Write-Host "正在停止服务..." -ForegroundColor Yellow
    Stop-Process -Id $desktopApiPid -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $frontendPid -Force -ErrorAction SilentlyContinue
    Write-Host "✓ 已停止" -ForegroundColor Green
}
