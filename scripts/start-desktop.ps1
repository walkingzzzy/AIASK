# AIASK Desktop 启动脚本 (Windows)
# Live 主路径：Agent :8765 + Frontend
# Optional：Desktop API :8001（薄 CRUD，不是主 live 后端）

param(
    [switch]$WithDesktopApi,
    [switch]$SkipAgent
)

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  AIASK Desktop V1 启动中..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

$pythonPath = "F:\Python311\python.exe"
if (-not (Test-Path $pythonPath)) {
    Write-Host "❌ Python 未找到: $pythonPath" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Python 已就绪" -ForegroundColor Green

try {
    $null = Get-Command node -ErrorAction Stop
    Write-Host "✓ Node.js 已就绪" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js 未安装" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

$agentPid = $null
$desktopApiPid = $null
$frontendPid = $null

function Stop-Tracked {
    param([int[]]$ProcessIds)
    foreach ($procId in $ProcessIds) {
        if ($procId) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    if (-not $SkipAgent) {
        Write-Host "→ Agent Live API (http://127.0.0.1:8765)" -ForegroundColor Green
        Push-Location packages\agent
        $agentArgs = @("run", "aiask-agent")
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            $agentJob = Start-Process -NoNewWindow -FilePath "uv" `
                -ArgumentList $agentArgs `
                -PassThru `
                -RedirectStandardOutput "..\..\logs\agent.log" `
                -RedirectStandardError "..\..\logs\agent-error.log"
        } else {
            $agentJob = Start-Process -NoNewWindow -FilePath $pythonPath `
                -ArgumentList "-m", "aiask_agent" `
                -PassThru `
                -RedirectStandardOutput "..\..\logs\agent.log" `
                -RedirectStandardError "..\..\logs\agent-error.log"
        }
        $agentPid = $agentJob.Id
        Pop-Location
        Start-Sleep -Seconds 3
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -TimeoutSec 5
            Write-Host "✓ Agent 启动成功 (PID: $agentPid) status=$($health.status)" -ForegroundColor Green
        } catch {
            Write-Host "⚠ Agent health 暂不可达，请检查 logs\agent-error.log（进程 PID=$agentPid）" -ForegroundColor Yellow
        }
    }

    if ($WithDesktopApi) {
        Write-Host "→ Desktop API optional (http://127.0.0.1:8001)" -ForegroundColor Green
        Push-Location packages\desktop-api
        $desktopApiJob = Start-Process -NoNewWindow -FilePath $pythonPath `
            -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8001" `
            -PassThru `
            -RedirectStandardOutput "..\..\logs\desktop-api.log" `
            -RedirectStandardError "..\..\logs\desktop-api-error.log"
        $desktopApiPid = $desktopApiJob.Id
        Pop-Location
    }

    Write-Host "→ Frontend (http://localhost:1420 或 package 配置端口)" -ForegroundColor Green
    Push-Location desktop
    if (-not (Test-Path "node_modules")) {
        npm install --silent
    }
    $frontendJob = Start-Process -NoNewWindow -FilePath "npm" `
        -ArgumentList "run", "dev" `
        -PassThru `
        -RedirectStandardOutput "..\logs\frontend.log" `
        -RedirectStandardError "..\logs\frontend-error.log"
    $frontendPid = $frontendJob.Id
    Pop-Location

    Write-Host ""
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host "  服务地址" -ForegroundColor Cyan
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host "  • Live Agent API: http://127.0.0.1:8765   ← Desktop live 模式默认"
    Write-Host "  • Readiness:      http://127.0.0.1:8765/v1/financial-system/readiness"
    if ($WithDesktopApi) {
        Write-Host "  • Desktop API:    http://127.0.0.1:8001   (optional CRUD)"
    }
    Write-Host "  • Frontend:       desktop npm run dev"
    Write-Host ""
    Write-Host "说明: Desktop live 只应连接 Agent :8765，不要把 :8001 当生产控制面。" -ForegroundColor Yellow
    Write-Host "证据链共启见 scripts/factories/COSTART_EVIDENCE_LOOP.md" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "按 Ctrl+C 停止..." -ForegroundColor Gray

    while ($true) {
        Start-Sleep -Seconds 1
        if ($agentPid -and -not (Get-Process -Id $agentPid -ErrorAction SilentlyContinue)) {
            Write-Host "❌ Agent 进程已停止" -ForegroundColor Red
            break
        }
        if ($frontendPid -and -not (Get-Process -Id $frontendPid -ErrorAction SilentlyContinue)) {
            Write-Host "❌ Frontend 进程已停止" -ForegroundColor Red
            break
        }
    }
}
finally {
    Write-Host "正在停止服务..." -ForegroundColor Yellow
    Stop-Tracked -ProcessIds @($agentPid, $desktopApiPid, $frontendPid)
    Write-Host "✓ 已停止" -ForegroundColor Green
}
