# -*- coding: utf-8 -*-
"""
Onboarding Service - 首次启动引导与离线模式检测

职责：
1. 检测通达信目录是否存在
2. 检测数据库是否已初始化
3. 自动创建默认设置
4. 检测网络连通性（离线模式）
5. 输出引导报告
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)
for _path in (PARENT_ROOT, PROJECT_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from config import settings
except ImportError:
    from backend.config import settings


class OnboardingService:
    """首次启动引导服务"""

    def __init__(self):
        self.tdx_dir = Path(settings.TDX_DIR)
        self.db_path = Path(settings.DATABASE_URL.replace("sqlite:///", ""))
        self._offline_mode: Optional[bool] = None

    def check_tdx_dir(self) -> Dict[str, Any]:
        """检测通达信目录"""
        exists = self.tdx_dir.exists()
        has_vipdoc = (self.tdx_dir / "vipdoc").exists() if exists else False
        has_sh = (self.tdx_dir / "vipdoc" / "sh" / "lday").exists() if has_vipdoc else False
        has_sz = (self.tdx_dir / "vipdoc" / "sz" / "lday").exists() if has_vipdoc else False

        return {
            "exists": exists,
            "path": str(self.tdx_dir),
            "has_vipdoc": has_vipdoc,
            "has_sh_data": has_sh,
            "has_sz_data": has_sz,
            "ready": exists and has_vipdoc and (has_sh or has_sz),
        }

    def check_database(self) -> Dict[str, Any]:
        """检测数据库是否已初始化"""
        exists = self.db_path.exists()
        if not exists:
            return {"exists": False, "initialized": False, "tables": []}

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
            return {
                "exists": True,
                "initialized": len(tables) > 0,
                "tables": tables,
            }
        except Exception as e:
            return {"exists": True, "initialized": False, "tables": [], "error": str(e)}

    def check_network(self) -> Dict[str, Any]:
        """检测网络连通性（离线模式）"""
        import urllib.request
        import socket

        # 设置短超时
        socket.setdefaulttimeout(3)

        test_urls = [
            ("Moonshot API", "https://api.moonshot.cn"),
            ("Baidu", "https://www.baidu.com"),
        ]

        results = {}
        any_online = False

        for name, url in test_urls:
            try:
                req = urllib.request.Request(url, method="HEAD")
                req.add_header("User-Agent", "QuantWorkbench/1.0")
                urllib.request.urlopen(req, timeout=3)
                results[name] = "online"
                any_online = True
            except Exception as e:
                results[name] = f"offline ({type(e).__name__})"

        return {
            "online": any_online,
            "offline_mode": not any_online,
            "details": results,
        }

    def is_ready(self) -> bool:
        """系统是否已就绪"""
        return self.generate_report()["ready"]

    def is_first_run(self) -> bool:
        """是否为首次运行"""
        return self.generate_report()["first_run"]

    def is_offline_mode(self) -> bool:
        """缓存的离线模式检测"""
        if self._offline_mode is None:
            self._offline_mode = self.check_network()["offline_mode"]
        return self._offline_mode

    def generate_report(self) -> Dict[str, Any]:
        """生成完整的引导报告"""
        tdx = self.check_tdx_dir()
        db = self.check_database()
        network = self.check_network()

        issues = []
        if not tdx["ready"]:
            issues.append(f"通达信目录未就绪: {tdx['path']}")
        if not db["initialized"]:
            issues.append("数据库未初始化")
        if network["offline_mode"]:
            issues.append("离线模式：实时数据和 AI 功能不可用")

        return {
            "first_run": not db["initialized"],
            "ready": len(issues) == 0,
            "issues": issues,
            "tdx": tdx,
            "database": db,
            "network": network,
            "recommendations": self._generate_recommendations(tdx, db, network),
        }

    def _generate_recommendations(
        self, tdx: Dict, db: Dict, network: Dict
    ) -> list:
        """生成改进建议"""
        recs = []
        if not tdx["exists"]:
            recs.append("请安装通达信金融终端，并确保数据目录存在（默认 D:/TDX）")
            recs.append("或在「系统设置」中修改 TDX_DIR 指向正确的数据目录")
        elif not tdx["has_vipdoc"]:
            recs.append("通达信目录存在但缺少 vipdoc 数据子目录，请执行盘后数据下载")

        if not db["initialized"]:
            recs.append("首次启动将自动初始化数据库（自选股、信号、设置等表）")

        if network["offline_mode"]:
            recs.append("当前处于离线模式，AI 投研和实时行情不可用，离线数据功能正常")
        else:
            recs.append("网络已连接，建议配置 Kimi API Key 以启用 AI 投研功能")

        return recs


# 全局单例
_onboarding_instance: Optional[OnboardingService] = None


def get_onboarding_service() -> OnboardingService:
    """获取全局 OnboardingService 实例"""
    global _onboarding_instance
    if _onboarding_instance is None:
        _onboarding_instance = OnboardingService()
    return _onboarding_instance


if __name__ == "__main__":
    svc = get_onboarding_service()
    report = svc.generate_report()
    print("=" * 50)
    print("Quant Workbench 启动引导报告")
    print("=" * 50)
    print(f"首次运行: {report['first_run']}")
    print(f"系统就绪: {report['ready']}")
    print()
    print("--- 通达信检测 ---")
    for k, v in report["tdx"].items():
        print(f"  {k}: {v}")
    print()
    print("--- 数据库检测 ---")
    for k, v in report["database"].items():
        print(f"  {k}: {v}")
    print()
    print("--- 网络检测 ---")
    for k, v in report["network"].items():
        print(f"  {k}: {v}")
    print()
    print("--- 建议 ---")
    for rec in report["recommendations"]:
        print(f"  • {rec}")
    print()
    print("=" * 50)
