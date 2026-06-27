import sys
import os

# Add project root to path
sys.path.insert(0, r'/c/Users/江厉害/Documents/Kimi/Workspaces/投资研究/a_share_system')

from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

endpoints = [
    '/api/health',
    '/api/v1/quote/health',
    '/api/v1/watchlist/',
    '/api/v1/market/indices',
    '/api/v1/signals/',
    '/api/v1/signals/strategies',
    '/api/v1/backtest/strategies',
    '/api/v1/data/overview',
    '/api/v1/settings',
    '/api/v1/ai/status',
    '/api/v1/ai/templates',
]

results = {}
for ep in endpoints:
    try:
        r = client.get(ep, timeout=5)
        results[ep] = r.status_code
    except Exception as e:
        results[ep] = f'ERROR: {type(e).__name__}'

print("=== Endpoint Verification ===")
for ep, status in results.items():
    print(f"  {ep}: {status}")

all_200 = all(v == 200 for v in results.values())
print(f"\nAll 200 OK: {all_200}")

# Check imports
import importlib
modules = [
    'backend.services.data_provider',
    'backend.models.database',
    'backend.services.indicators',
    'backend.api.quote',
    'backend.api.watchlist',
    'backend.api.market',
    'backend.api.signals',
    'backend.services.signal_engine',
    'backend.services.backtest_engine',
    'backend.api.backtest',
    'backend.api.data',
    'backend.api.settings',
    'backend.api.ai',
    'backend.services.onboarding',
]

print("\n=== Import Verification ===")
for mod in modules:
    try:
        importlib.import_module(mod)
        print(f"  {mod}: OK")
    except Exception as e:
        print(f"  {mod}: FAIL - {e}")
