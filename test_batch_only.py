# -*- coding: utf-8 -*-
"""单独测试 batch 接口"""
import sys, os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

print("Testing batch endpoint...")

try:
    r = client.get("/api/v1/quotes/batch")
    print("No params -> status=%d, body=%s" % (r.status_code, r.text[:200]))
except Exception as e:
    print("No params EXCEPTION: type=%s, msg=%s" % (type(e).__name__, str(e)))

try:
    r = client.get("/api/v1/quotes/batch?symbols=000001,600519")
    print("Normal -> status=%d, body=%s" % (r.status_code, r.text[:500]))
except Exception as e:
    print("Normal EXCEPTION: type=%s, msg=%s" % (type(e).__name__, str(e)))
