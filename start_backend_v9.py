import subprocess
import sys

# Start backend in background
subprocess.Popen(
    [
        r"C:\Users\江厉害\AppData\Roaming\kimi-desktop\daimon-share\daimon\runtime\python\.venv\Scripts\python.exe",
        r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system\backend\main.py"
    ],
    stdout=open(r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system\backend_v9.log", "w"),
    stderr=subprocess.STDOUT,
    cwd=r"C:\Users\江厉害\Documents\Kimi\Workspaces\投资研究\a_share_system",
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
)
print("Backend started")
