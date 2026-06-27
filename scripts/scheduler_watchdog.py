#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quant Workbench 自检看门狗（Task Scheduler 不可用时的兜底方案）

每小时执行一次 selfcheck_loop.main()，异常时继续循环。
"""

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 标记当前为守护进程，避免无限递归启动新的看门狗
os.environ["_QW_DAEMON"] = "1"

from scripts.selfcheck_loop import main

INTERVAL_SECONDS = 3600


def run_forever():
    print(f"[WATCHDOG] Started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    while True:
        start = time.time()
        try:
            main()
        except Exception as e:
            print(f"[WATCHDOG] selfcheck loop failed: {e}")
        elapsed = time.time() - start
        sleep_time = max(0, INTERVAL_SECONDS - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)


if __name__ == "__main__":
    run_forever()
