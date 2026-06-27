# -*- coding: utf-8 -*-
"""
Dashboard Module - 实时看板

提供 Flask Web 服务和数据组装。

Usage:
    from dashboard import create_app
    app = create_app()
    app.run(host='127.0.0.1', port=5888)
"""

from .app import create_app
from .data_service import DashboardDataService

__all__ = ["create_app", "DashboardDataService"]
