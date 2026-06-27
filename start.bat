@echo off
set "PYTHON=C:\Users\江厉害\AppData\Local\Programs\Python\Python312\python.exe"
set "BACKEND=%~dp0backend\main.py"
set "LOG=%~dp0backend.log"

if not exist "%PYTHON%" (
    echo ERROR: Python not found at %PYTHON%
    pause
    exit /b 1
)

if not exist "%BACKEND%" (
    echo ERROR: Backend not found at %BACKEND%
    pause
    exit /b 1
)

echo Starting Quant Workbench Backend...
start /b "" "%PYTHON%" "%BACKEND%" > "%LOG%" 2>&1

echo Waiting for server...
timeout /t 3 /nobreak >nul

echo Opening browser...
start "" "http://127.0.0.1:5889/"

echo.
echo Backend running at http://127.0.0.1:5889/
echo Press any key to stop...
pause >nul

taskkill /F /IM python.exe >nul 2>&1
echo Stopped.
