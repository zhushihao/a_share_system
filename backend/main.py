# -*- coding: utf-8 -*-
"""
Quant Workbench Backend - FastAPI Entry (独立版本)

v1.0 - 全新后端，不依赖旧系统
"""

import os
import sys
from datetime import datetime
from contextlib import asynccontextmanager

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PARENT_ROOT = os.path.dirname(PROJECT_ROOT)

# 确保 backend/ 和项目根目录在 sys.path 中，兼容多种启动方式
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if PARENT_ROOT not in sys.path:
    sys.path.insert(0, PARENT_ROOT)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import json


class UTF8JSONResponse(JSONResponse):
    """自定义 JSONResponse：确保中文正确编码（ensure_ascii=False）"""
    media_type = "application/json; charset=utf-8"
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")

# 配置
try:
    from config import settings
except ImportError:
    from backend.config import settings

# API 路由（先注册空路由，后续逐步填充）
try:
    from api import (
        quote, watchlist, market, signals, data, backtest, ai,
        settings as settings_router, data_platform
    )
except ImportError:
    from backend.api import (
        quote, watchlist, market, signals, data, backtest, ai,
        settings as settings_router, data_platform
    )

# 启动引导
try:
    from services.onboarding import get_onboarding_service
except ImportError:
    from backend.services.onboarding import get_onboarding_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    from backend.config import logger, settings

    print(f"[INFO] Quant Workbench Backend starting on port {settings.PORT}")
    
    # 启动引导检查
    try:
        onboarding = get_onboarding_service()
        report = onboarding.generate_report()
        
        if report["first_run"]:
            logger.info("首次启动检测到，正在初始化系统...")
        
        if not report["ready"]:
            logger.warning("系统尚未完全就绪：")
            for issue in report["issues"]:
                logger.warning(f"  - {issue}")
            for rec in report["recommendations"]:
                logger.info(f"  💡 {rec}")
        else:
            logger.info("系统检查通过，全部就绪")
            
        if report["network"]["offline_mode"]:
            logger.info("离线模式已启用，AI 和实时数据功能不可用")
        else:
            logger.info("网络已连接")
            
    except Exception as e:
        logger.warning(f"启动引导检查失败: {e}")
    
    yield
    logger.info("Quant Workbench Backend shutting down")


app = FastAPI(
    title="Quant Workbench API",
    description="本地金融分析工作台",
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=UTF8JSONResponse,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
app.include_router(quote.router, prefix="/api/v1", tags=["quote"])
app.include_router(watchlist.router, prefix="/api/v1", tags=["watchlist"])
app.include_router(market.router, prefix="/api/v1", tags=["market"])
app.include_router(data_platform.router, prefix="/api/v1", tags=["data-platform"])
app.include_router(signals.router, prefix="/api/v1", tags=["signals"])
app.include_router(data.router, prefix="/api/v1", tags=["data"])
app.include_router(backtest.router, prefix="/api/v1", tags=["backtest"])
app.include_router(ai.router, prefix="/api/v1", tags=["ai"])
app.include_router(settings_router.router, prefix="/api/v1", tags=["settings"])


@app.get("/api/health")
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
    }


@app.get("/")
async def root():
    """根路径：返回前端构建产物，如果不存在则返回 API 信息"""
    index_path = os.path.join(PARENT_ROOT, "frontend_react", "dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Quant Workbench API", "docs": "/docs", "redoc": "/redoc"}


@app.get("/assets/{file:path}")
async def static_assets(file: str):
    """静态文件服务（前端 JS/CSS）"""
    asset_path = os.path.join(PARENT_ROOT, "frontend_react", "dist", "assets", file)
    if os.path.exists(asset_path):
        return FileResponse(asset_path)
    raise HTTPException(status_code=404, detail="Asset not found")


# Catch-all 路由：支持前端 History 路由模式
# 当用户访问 /quote/000001 等前端路由时，返回 index.html 让前端路由处理
@app.get("/{path:path}")
async def catch_all(path: str):
    """返回前端 index.html，支持前端路由刷新"""
    # 排除 API 路径和 assets 路径（虽然这些路由已注册在前面，但这里做双重保护）
    if path.startswith("api/") or path.startswith("assets/") or path in ("docs", "redoc", "openapi.json"):
        raise HTTPException(status_code=404, detail="Not found")
    index_path = os.path.join(PARENT_ROOT, "frontend_react", "dist", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Quant Workbench API", "docs": "/docs", "redoc": "/redoc"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level="info",
    )
