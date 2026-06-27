# -*- coding: utf-8 -*-
"""
Diagnose.py - Run this to check why you can't open http://127.0.0.1:5888/

Usage:
    python diagnose.py
    
Or double-click diagnose.bat
"""

import sys
import os
import socket
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check(label, result, detail=""):
    status = "PASS" if result else "FAIL"
    print(f"  [{status}] {label}")
    if detail:
        print(f"         {detail}")

def main():
    print("=" * 50)
    print("  A-Share Momentum System v5.0 - Diagnose")
    print("=" * 50)
    
    # 1. Python
    print("\n[1] Python environment")
    check(f"Python executable: {sys.executable}", True)
    check(f"Python version: {sys.version.split()[0]}", True)
    
    # 2. Flask
    print("\n[2] Flask installation")
    try:
        import flask
        check(f"Flask version: {flask.__version__}", True)
    except ImportError:
        check("Flask NOT installed", False, "Run: pip install flask flask-cors")
    
    # 3. mootdx
    print("\n[3] mootdx installation")
    try:
        import mootdx
        check(f"mootdx: OK", True)
    except ImportError:
        check("mootdx NOT installed", False, "Run: pip install mootdx")
    
    # 4. Port
    print("\n[4] Port 5888")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('127.0.0.1', 5888))
        check("Port 5888 is FREE", True)
    except OSError:
        check("Port 5888 is IN USE", False, "Another program is using port 5888")
    finally:
        sock.close()
    
    # 5. Key files
    print("\n[5] Key files")
    files = [
        "launch.py",
        "launch.bat",
        "api_server.py",
        "frontend/index.html",
        "frontend/app.js",
        "frontend/style.css",
    ]
    for f in files:
        exists = os.path.exists(f)
        check(f"{f}: {'exists' if exists else 'MISSING'}", exists)
    
    # 6. Try to start server
    print("\n[6] Server test (starting for 3 seconds...)")
    try:
        from api_server import create_app
        app = create_app()
        app.config['TESTING'] = True
        client = app.test_client()
        
        r = client.get('/')
        check(f"GET / returns {r.status_code}", r.status_code == 200)
        
        r = client.get('/api/health')
        check(f"GET /api/health returns {r.status_code}", r.status_code == 200)
    except Exception as e:
        check(f"Server test FAILED: {e}", False)
    
    print("\n" + "=" * 50)
    print("  Diagnose complete.")
    print("=" * 50)
    print("\nIf all checks PASS, run:")
    print("  python launch.py")
    print("  or double-click launch.bat")
    print("\nThen open browser:")
    print("  http://127.0.0.1:5888/")
    print("=" * 50)
    
    input("\nPress Enter to exit...")

if __name__ == '__main__':
    main()
