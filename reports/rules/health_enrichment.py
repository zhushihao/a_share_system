# -*- coding: utf-8 -*-
"""
健康检查增强规则

将 /api/health 从静态字符串升级为探测数据库、TDX 目录和数据源状态。
"""

import json
import urllib.request
from typing import Tuple

from reports.rules import PROJECT_ROOT, Rule


class HealthEnrichmentRule(Rule):
    name = "health_enrichment"
    description = "增强 /api/health，探测 DB、TDX 和数据源状态"
    keywords = ["健康检查", "health", "只返回静态字符串", "探测 DB"]
    risk = "low"
    requires_restart = True

    def detect(self) -> Tuple[bool, str]:
        main_file = PROJECT_ROOT / "backend" / "main.py"
        text = main_file.read_text(encoding="utf-8")

        fn_start = text.find('@app.get("/api/health")')
        if fn_start == -1:
            return False, "未找到 /api/health 端点"
        # 截取到下一个 @app 装饰器或函数定义之前
        fn_end = text.find("\n@app", fn_start + 1)
        if fn_end == -1:
            fn_end = len(text)
        fn_text = text[fn_start:fn_end]

        if "checks" in fn_text or "tdx_dir" in fn_text or "database" in fn_text.lower():
            return False, "健康检查已包含 DB/TDX 探测"
        return True, "健康检查仍为静态返回"

    def apply(self) -> Tuple[bool, str]:
        main_file = PROJECT_ROOT / "backend" / "main.py"
        self.backup("backend/main.py")
        text = main_file.read_text(encoding="utf-8")

        old_fn = '''@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
    }'''

        new_fn = '''@app.get("/api/health")
async def health_check():
    import os
    from backend.config import settings
    from backend.models.database import DATABASE_PATH

    checks = {
        "tdx_dir": os.path.exists(settings.TDX_DIR),
        "database": os.path.exists(str(DATABASE_PATH)),
    }

    # 数据源健康
    try:
        from backend.services.data_provider import DataProviderService
        provider = DataProviderService(tdxdir=settings.TDX_DIR)
        checks["data_sources"] = provider.health_check()
    except Exception as e:
        checks["data_sources"] = {"error": str(e)}

    all_ok = checks["tdx_dir"] and checks["database"]
    if isinstance(checks.get("data_sources"), dict):
        all_ok = all_ok and (
            checks["data_sources"].get("offline_available") or
            checks["data_sources"].get("realtime_available")
        )

    return {
        "status": "ok" if all_ok else "degraded",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
    }'''

        if old_fn not in text:
            return False, "未找到旧的 /api/health 实现，可能源码已变化"

        text = text.replace(old_fn, new_fn)
        main_file.write_text(text, encoding="utf-8")
        return True, "已增强 /api/health 探测 DB、TDX 和数据源"

    def verify(self) -> Tuple[bool, str]:
        main_file = PROJECT_ROOT / "backend" / "main.py"
        text = main_file.read_text(encoding="utf-8")
        fn_start = text.find('@app.get("/api/health")')
        fn_end = text.find("\n@app", fn_start + 1)
        if fn_end == -1:
            fn_end = len(text)
        fn_text = text[fn_start:fn_end]
        if "checks" not in fn_text:
            return False, "main.py 中 /api/health 未包含 checks"
        try:
            with urllib.request.urlopen("http://127.0.0.1:5889/api/health", timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "checks" not in data:
                    return False, "运行时 /api/health 未返回 checks"
                return True, "运行时 /api/health 已返回 enriched checks"
        except Exception as e:
            return False, f"调用 /api/health 失败: {e}"
