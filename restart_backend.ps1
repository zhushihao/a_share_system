#!/usr/bin/env pwsh
# 后端服务重启脚本（PowerShell）

$ErrorActionPreference = "SilentlyContinue"

Write-Host "=== Quant Workbench 后端重启 ===" -ForegroundColor Cyan

# 1. 关闭所有 python 进程（uvicorn）
Write-Host "正在关闭现有后端进程..." -ForegroundColor Yellow
$pythonProcs = Get-Process python -ErrorAction SilentlyContinue
foreach ($proc in $pythonProcs) {
    $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
    if ($cmdLine -match "uvicorn" -or $cmdLine -match "main:app") {
        Stop-Process -Id $proc.Id -Force
        Write-Host "  已关闭 uvicorn 进程 PID: $($proc.Id)" -ForegroundColor Green
    }
}

Start-Sleep -Seconds 2

# 2. 启动新的 uvicorn
Write-Host "正在启动新后端..." -ForegroundColor Yellow
$backendDir = "C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system\backend"
$env:PYTHONPATH = "C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system"

Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5889", "--reload", "--log-level", "info" -WorkingDirectory $backendDir -WindowStyle Hidden

Start-Sleep -Seconds 3

# 3. 验证
Write-Host "验证后端服务..." -ForegroundColor Yellow
try {
    $resp = Invoke-RestMethod -Uri "http://localhost:5889/api/health" -TimeoutSec 5
    Write-Host "  后端已启动: $($resp.status) v$($resp.version)" -ForegroundColor Green
} catch {
    Write-Host "  后端启动失败，请手动检查" -ForegroundColor Red
}

Write-Host "=== 重启完成 ===" -ForegroundColor Cyan
