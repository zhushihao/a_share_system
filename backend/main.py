# -*- coding: utf-8 -*-
"""
Quant Workbench Backend - FastAPI Entry (独立版本)

v1.0 - 全新后端，不依赖旧系统
"""

import os
import sys
import asyncio
from datetime import datetime, timedelta
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


def _next_half_hour_tick():
    """计算下一个整点或半点（本地时间）"""
    now = datetime.now()
    minutes = (now.minute // 30 + 1) * 30
    next_tick = now.replace(minute=0, second=5, microsecond=0) + timedelta(minutes=minutes)
    return next_tick


async def _delayed_full_scan(scan_func):
    """启动后延迟 60 秒执行一次全市场扫描，避免与启动流程竞争资源。"""
    await asyncio.sleep(60)
    await scan_func()


async def _scheduled_signal_scan_loop():
    """定时扫描信号任务

    - 启动后立即扫描一次自选股，避免服务重启后等待过久
    - 每 30 分钟扫描一次自选股
    - 每日 09:35、15:05 执行全市场扫描，补齐非自选股的最新信号
    """
    from backend.api.signals import scan_signals, SignalScanRequest
    from backend.models.database import init_db, DATABASE_PATH, get_watchlist
    from backend.config import logger
    from backend.services.data_provider import get_data_provider_service

    async def _scan_watchlist():
        conn = await init_db(DATABASE_PATH)
        try:
            items = await get_watchlist(conn)
            symbols = [getattr(item, "symbol", item.get("symbol")) for item in items]
            symbols = [s for s in symbols if s]
            if symbols:
                logger.info(f"[scheduler] 开始扫描 {len(symbols)} 只自选股信号")
                await scan_signals(SignalScanRequest(symbols=symbols))
                logger.info("[scheduler] 自选股信号扫描完成")
            return symbols
        finally:
            await conn.close()

    async def _scan_all_stocks(chunk_size: int = 500):
        try:
            provider = get_data_provider_service()
            stock_list = provider.fetch_stock_list()
            if stock_list is None or len(stock_list) == 0:
                logger.warning("[scheduler] 全市场扫描：无法获取股票列表")
                return
            code_col = "code" if "code" in stock_list.columns else stock_list.columns[0]
            symbols = stock_list[code_col].astype(str).str.strip().str.zfill(6).tolist()
            # 排除指数/基金等过长的代码，仅保留 6 位 A 股
            symbols = [s for s in symbols if s.isdigit() and len(s) == 6]
            total = len(symbols)
            logger.info(f"[scheduler] 开始全市场扫描，共 {total} 只股票，分 {chunk_size} 只/批")
            for i in range(0, total, chunk_size):
                chunk = symbols[i:i + chunk_size]
                try:
                    await scan_signals(SignalScanRequest(symbols=chunk))
                    logger.info(f"[scheduler] 全市场扫描进度 {min(i + chunk_size, total)}/{total}")
                except Exception as e:
                    logger.warning(f"[scheduler] 全市场扫描批次失败 ({i}-{i+chunk_size}): {e}")
                # 每批之间让出事件循环，避免长时间阻塞
                await asyncio.sleep(0.5)
            logger.info("[scheduler] 全市场信号扫描完成")
        except Exception as e:
            logger.warning(f"[scheduler] 全市场扫描失败: {e}")

    # 启动后立即扫描一次自选股
    try:
        await _scan_watchlist()
    except Exception as e:
        logger.warning(f"[scheduler] 启动时扫描失败: {e}")

    # 启动后 60 秒再执行一次全市场扫描，补齐非自选股最新信号
    asyncio.create_task(_delayed_full_scan(_scan_all_stocks))

    while True:
        next_tick = _next_half_hour_tick()
        sleep_seconds = (next_tick - datetime.now()).total_seconds()
        await asyncio.sleep(max(sleep_seconds, 0))

        now = datetime.now()
        try:
            # 每日 09:35 和 15:05 执行全市场扫描
            if (now.hour == 9 and now.minute == 35) or (now.hour == 15 and now.minute == 5):
                await _scan_all_stocks()
            else:
                await _scan_watchlist()
        except Exception as e:
            logger.warning(f"[scheduler] 定时信号扫描失败: {e}")


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

    # 启动定时信号扫描任务
    scheduler_task = asyncio.create_task(_scheduled_signal_scan_loop())

    yield

    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
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
@app.get("/health")
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
        from backend.services.data_provider import get_data_provider_service
        provider = get_data_provider_service()
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
