@echo off
set "PYTHON=C:\Users\江厉害\AppData\Local\Programs\Python\Python312\python.exe"
set "SCRIPT=C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system\scripts\selfcheck_loop.py"
set "TASK_NAME=QuantWorkbench-SelfCheckLoop"

schtasks /Create /SC HOURLY /TN "%TASK_NAME%" /TR "\"%PYTHON%\" \"%SCRIPT%\"" /ST 00:00 /F
exit /b %errorlevel%
