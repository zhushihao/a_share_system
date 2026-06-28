# -*- coding: utf-8 -*-
"""
自主迭代规则库

每条规则必须继承 Rule 基类，并实现 detect/apply/verify/rollback 四个方法。
"""

import os
import shutil
import subprocess
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKUP_DIR = PROJECT_ROOT / "reports" / ".backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


class Rule(ABC):
    """规则基类"""

    name: str = ""
    description: str = ""
    keywords: List[str] = []
    risk: str = "low"  # low / medium / high
    priority: int = 99  # 越小越优先执行；P0=0, P1=1, P2=2

    def __init__(self):
        self._backups: List[Tuple[str, Path]] = []

    def matches(self, issue_text: str) -> bool:
        """基于关键词匹配问题描述"""
        text = issue_text.lower()
        return any(kw.lower() in text for kw in self.keywords)

    @abstractmethod
    def detect(self) -> Tuple[bool, str]:
        """返回 (问题是否存在, 描述)"""
        pass

    def apply(self) -> Tuple[bool, str]:
        """返回 (是否成功, 描述)"""
        return False, "未实现"

    def verify(self) -> Tuple[bool, str]:
        """返回 (是否通过, 描述)"""
        return True, "未配置验证"

    def rollback(self) -> Tuple[bool, str]:
        """回滚所有已备份文件"""
        ok = True
        msgs = []
        for rel_path, backup_path in self._backups:
            target = PROJECT_ROOT / rel_path
            try:
                shutil.copy2(backup_path, target)
                msgs.append(f"已回滚 {rel_path}")
            except Exception as e:
                ok = False
                msgs.append(f"回滚 {rel_path} 失败: {e}")
        return ok, "; ".join(msgs) if msgs else "无备份可回滚"

    def backup(self, rel_path: str) -> Optional[Path]:
        """备份相对项目根目录的文件"""
        target = PROJECT_ROOT / rel_path
        if not target.exists():
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = rel_path.replace("/", "__").replace("\\", "__").replace(":", "_")
        backup_path = BACKUP_DIR / f"{safe_name}.{ts}.bak"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)
        self._backups.append((rel_path, backup_path))
        return backup_path


def api_health(timeout: int = 10) -> Tuple[bool, str]:
    """检查后端健康接口"""
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:5889/api/health", timeout=timeout
        ) as resp:
            body = resp.read().decode("utf-8")
            return resp.status == 200, body
    except Exception as e:
        return False, str(e)


def api_quote_health(timeout: int = 10) -> Tuple[bool, str]:
    """检查行情数据源健康"""
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:5889/api/v1/quote/health", timeout=timeout
        ) as resp:
            body = resp.read().decode("utf-8")
            return resp.status == 200, body
    except Exception as e:
        return False, str(e)


def run_pytest(test_path: str = "tests/unit/", timeout: int = 180) -> Tuple[bool, str]:
    """运行 pytest 测试"""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", test_path, "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout + "\n" + result.stderr
    except Exception as e:
        return False, str(e)


def api_smoke_tests() -> Tuple[bool, str]:
    """核心 API 冒烟测试"""
    endpoints = [
        "/api/health",
        "/api/v1/quote/health",
        "/api/v1/data/stock-list",
        "/api/v1/quote/000001/signal",
    ]
    msgs = []
    for ep in endpoints:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:5889{ep}", timeout=10
            ) as resp:
                if resp.status != 200:
                    return False, f"{ep} 返回 {resp.status}"
                msgs.append(f"{ep} OK")
        except Exception as e:
            return False, f"{ep} 失败: {e}"
    return True, "; ".join(msgs)
