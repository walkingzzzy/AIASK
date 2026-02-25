@echo off
chcp 65001 >nul
cd /d %~dp0

echo [AIASK] 一键启动 Web + BFF
start "AIASK-WEB" cmd /k "npm run dev:web"
start "AIASK-BFF" cmd /k "npm run dev:bff"

echo 已启动两个窗口：
echo  - Web: http://localhost:3000
echo  - BFF: http://127.0.0.1:3001/api
echo.
echo 关闭对应窗口即可停止服务。
pause

