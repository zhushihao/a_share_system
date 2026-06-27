# -*- coding: utf-8 -*-
"""
Stage 4-6 轻量验证脚本（不使用 TestClient，避免 lifespan 耗时）
"""
import sys, os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

print("=" * 60)
print("Stage 4-6 Light Verification")
print("=" * 60)

errors = []

# --- Stage 4: 回测引擎 ---
print("\n[TEST] Stage 4: Backtest Engine")

try:
    from backend.services.backtest_engine import get_strategy_templates
    print("  [OK] backtest_engine import success")
    
    # 测试策略模板
    templates = get_strategy_templates()
    assert len(templates) >= 5, "Expected >= 5 templates, got %d" % len(templates)
    print("  [OK] Strategy templates: %d" % len(templates))
except Exception as e:
    errors.append("backtest engine: %s" % e)
    print("  [FAIL] backtest engine: %s" % e)

try:
    from backend.api.backtest import router as backtest_router
    print("  [OK] backtest router import success")
except Exception as e:
    errors.append("backtest router: %s" % e)
    print("  [FAIL] backtest router: %s" % e)

try:
    from backend.api.data import router as data_router
    print("  [OK] data router import success")
except Exception as e:
    errors.append("data router: %s" % e)
    print("  [FAIL] data router: %s" % e)

try:
    from backend.api.settings import router as settings_router
    print("  [OK] settings router import success")
except Exception as e:
    errors.append("settings router: %s" % e)
    print("  [FAIL] settings router: %s" % e)

# --- Stage 5: AI ---
print("\n[TEST] Stage 5: AI Research")

try:
    from backend.api.ai import router as ai_router
    print("  [OK] ai router import success")
except Exception as e:
    errors.append("ai router: %s" % e)
    print("  [FAIL] ai router: %s" % e)

try:
    from backend.api.ai import _DEFAULT_TEMPLATES
    assert len(_DEFAULT_TEMPLATES) >= 9, "Expected >= 9 templates, got %d" % len(_DEFAULT_TEMPLATES)
    print("  [OK] AI templates: %d" % len(_DEFAULT_TEMPLATES))
except Exception as e:
    errors.append("ai templates: %s" % e)
    print("  [FAIL] ai templates: %s" % e)

# --- Stage 6: Onboarding ---
print("\n[TEST] Stage 6: Onboarding / Health")

try:
    from backend.services.onboarding import get_onboarding_service
    svc = get_onboarding_service()
    report = svc.generate_report()
    assert isinstance(report, dict)
    print("  [OK] Onboarding report: ready=%s" % report.get("ready", False))
except Exception as e:
    errors.append("onboarding: %s" % e)
    print("  [FAIL] onboarding: %s" % e)

# --- 前端文件检查 ---
print("\n[TEST] Frontend files")

frontend_files = [
    "frontend_react/src/pages/Backtest.tsx",
    "frontend_react/src/pages/StrategyEditor.tsx",
    "frontend_react/src/pages/DataManager.tsx",
    "frontend_react/src/pages/Settings.tsx",
    "frontend_react/src/pages/AIResearch.tsx",
]

for f in frontend_files:
    path = os.path.join(PROJECT_ROOT, f.replace('/', os.sep))
    path_alt = os.path.join(PROJECT_ROOT, f)
    if os.path.exists(path) or os.path.exists(path_alt):
        size = os.path.getsize(path) if os.path.exists(path) else os.path.getsize(path_alt)
        print("  [OK] %s (%d bytes)" % (f, size))
    else:
        errors.append("frontend missing: %s" % f)
        print("  [FAIL] %s missing" % f)

print("\n" + "=" * 60)
if errors:
    print("FAILED: %d errors" % len(errors))
    for e in errors:
        print("  - %s" % e)
    sys.exit(1)
else:
    print("ALL Stage 4-6 TESTS PASSED")
    sys.exit(0)
