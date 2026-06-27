# -*- coding: utf-8 -*-
"""
后端自动重启规则

当 /api/health 不可达时，结束占用 5889 的后端进程并重新启动。
"""

import re
import subprocess
import time
from pathlib import Path
from typing import Tuple

from reports.rules import PROJECT_ROOT, Rule, api_health


class BackendRestartRule(Rule):
    name = "backend_restart"
    description = "后端不可达时自动重启服务"
    keywords = ["后端未运行", "连接失败", "端口 5889", "后端宕机", "health 失败"]
    risk = "medium"

    PORT = 5889

    def detect(self) -> Tuple[bool, str]:
        ok, msg = api_health(timeout=5)
        if ok:
            return False, "后端健康检查通过"
        # 重试一次，避免瞬时抖动
        time.sleep(2)
        ok2, msg2 = api_health(timeout=5)
        if ok2:
            return False, "后端健康检查第二次通过"
        return True, f"后端健康检查失败: {msg} / {msg2}"

    def _get_backend_pid(self) -> int:
        """通过 netstat 查找监听 5889 的进程 PID"""
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.splitlines():
                if f":{self.PORT}" in line and "LISTENING" in line:
                    m = re.search(r"LISTENING\s+(\d+)", line)
                    if m:
                        return int(m.group(1))
        except Exception:
            pass
        return 0

    def apply(self) -> Tuple[bool, str]:
        pid = self._get_backend_pid()
        kill_msg = ""
        if pid:
            try:
                subprocess.run(
                    ["taskkill", "//PID", str(pid), "//F"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                kill_msg = f"已结束 PID {pid}"
            except Exception as e:
                kill_msg = f"结束 PID {pid} 失败: {e}"

        # 等待端口释放
        for _ in range(10):
            if self._get_backend_pid() == 0:
                break
            time.sleep(0.5)

        log_path = PROJECT_ROOT / "backend.log"
        try:
            proc = subprocess.Popen(
                ["pythonw", "-m", "backend.main"],
                cwd=PROJECT_ROOT,
                stdout=open(log_path, "a", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            start_msg = f"已启动后端 (pid={proc.pid})"
        except Exception as e:
            return False, f"启动后端失败: {e}; {kill_msg}"

        return True, f"{kill_msg}; {start_msg}"

    def verify(self) -> Tuple[bool, str]:
        for i in range(20):
            ok, msg = api_health(timeout=5)
            if ok:
                return True, f"后端重启后健康检查通过 (尝试 {i+1})"
            time.sleep(2)
        return False, f"后端重启后健康检查仍失败: {msg}"

    def rollback(self) -> Tuple[bool, str]:
        # 重启操作无法回滚
        return False, "重启操作无法回滚"
