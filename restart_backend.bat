@echo off
chcp 65001 >nul

:: 关闭现有的 uvicorn 进程
for /f "tokens=2" %%a in ('tasklist ^| findstr python.exe') do (
    taskkill /PID %%a /F >nul 2>&1
    echo Killed python process PID: %%a
)

timeout /t 2 /nobreak >nul

:: 启动新的 uvicorn 进程
cd /d "C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system\backend"
start /B python -m uvicorn main:app --host 0.0.0.0 --port 5889 --reload --log-level info

echo Backend restarted on port 5889
