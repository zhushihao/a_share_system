# -*- coding: utf-8 -*-
"""
Dashboard Routes - Flask API路由

提供看板所需的REST API和页面渲染。

路由列表：
- /                    -> 主看板页面
- /api/market/overview -> 市场概览JSON
- /api/sectors/top     -> 板块热点JSON
- /api/health          -> 系统健康JSON
- /api/events/status   -> 事件引擎状态JSON
"""

from flask import Blueprint, jsonify, render_template, request
from datetime import datetime

from dashboard.data_service import DashboardDataService
from core.observability import get_obs

# 创建蓝图
routes_bp = Blueprint('dashboard', __name__, template_folder='templates', static_folder='static')

# 数据服务实例（延迟初始化）
_data_service = None

# 全局事件引擎实例（用于UI控制）
_scheduler = None

def get_data_service():
    """获取数据服务实例（延迟初始化）"""
    global _data_service
    if _data_service is None:
        _data_service = DashboardDataService(tdxdir="D:/TDX")
    return _data_service


# ════════════════════════════════════════════════════════════
# 系统控制 API（UI 直接操作）
# ════════════════════════════════════════════════════════════

@routes_bp.route('/api/system/start', methods=['POST'])
def api_system_start():
    """启动事件引擎"""
    global _scheduler
    try:
        from events.scheduler import EventScheduler
        if _scheduler is None:
            _scheduler = EventScheduler()
        if not _scheduler._running:
            _scheduler.start()
            return jsonify({"success": True, "message": "事件引擎已启动"})
        return jsonify({"success": True, "message": "事件引擎已在运行中"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@routes_bp.route('/api/system/stop', methods=['POST'])
def api_system_stop():
    """停止事件引擎"""
    global _scheduler
    try:
        if _scheduler is not None and _scheduler._running:
            _scheduler.stop()
            return jsonify({"success": True, "message": "事件引擎已停止"})
        return jsonify({"success": True, "message": "事件引擎未运行"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@routes_bp.route('/api/system/status')
def api_system_control_status():
    """获取系统控制状态"""
    global _scheduler
    try:
        if _scheduler is not None and _scheduler._running:
            return jsonify({"running": True, "triggers": len(_scheduler._triggers)})
        return jsonify({"running": False, "triggers": 0})
    except Exception as e:
        return jsonify({"running": False, "error": str(e)})


# ════════════════════════════════════════════════════════════
# 页面路由
# ════════════════════════════════════════════════════════════

@routes_bp.route('/')
def index():
    """主看板页面"""
    service = get_data_service()
    
    # 获取数据
    overview = service.get_market_overview()
    sectors = service.get_top_sectors(limit=10)
    health = service.get_system_health()
    
    # 获取关注股（默认示例）
    watchlist = service.get_watchlist_status(["000001", "600519", "300750"])
    
    # 获取今日事件（从事件引擎）
    try:
        from events.scheduler import EventScheduler
        scheduler = EventScheduler()
        next_events = scheduler.get_next_events()
    except Exception:
        next_events = []
    
    # 市场状态
    market_status_map = {
        "pre_open": "开盘前",
        "auction": "集合竞价",
        "trading_am": "早盘交易中",
        "noon_break": "午间休市",
        "trading_pm": "午盘交易中",
        "closed": "已收盘",
    }
    market_status = market_status_map.get(overview.get("market_status", "closed"), "未知")
    
    return render_template(
        'index.html',
        indices=overview.get("indices", []),
        sectors=sectors,
        health=health,
        watchlist=watchlist,
        signals=[],
        next_events=next_events,
        market_status=market_status,
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ════════════════════════════════════════════════════════════
# API 路由
# ════════════════════════════════════════════════════════════

@routes_bp.route('/api/market/overview')
def api_market_overview():
    """市场概览API"""
    service = get_data_service()
    return jsonify(service.get_market_overview())


@routes_bp.route('/api/sectors/top')
def api_sectors_top():
    """板块热点API"""
    service = get_data_service()
    limit = __import__('flask').request.args.get('limit', 10, type=int)
    return jsonify({"sectors": service.get_top_sectors(limit=limit)})


@routes_bp.route('/api/health')
def api_health():
    """系统健康API"""
    service = get_data_service()
    return jsonify(service.get_system_health())


@routes_bp.route('/api/events/status')
def api_events_status():
    """事件引擎状态API"""
    try:
        from events.scheduler import EventScheduler
        scheduler = EventScheduler()
        return jsonify(scheduler.get_status())
    except Exception as e:
        return jsonify({"error": str(e)})


@routes_bp.route('/api/stocks/watchlist')
def api_watchlist():
    """关注股状态API"""
    service = get_data_service()
    codes = __import__('flask').request.args.get('codes', '000001,600519,300750')
    code_list = [c.strip() for c in codes.split(',')]
    return jsonify({"stocks": service.get_watchlist_status(code_list)})


@routes_bp.route('/api/stocks/quote/<code>')
def api_stock_quote(code):
    """单股实时行情API"""
    service = get_data_service()
    return jsonify(service.get_stock_quote(code))



# ════════════════════════════════════════════════════════════
# 新增页面路由（Phase 3）
# ════════════════════════════════════════════════════════════

@routes_bp.route('/sectors')
def sectors():
    """板块详情页"""
    service = get_data_service()
    return render_template(
        'sectors.html',
        sectors=service.get_all_sectors(),
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@routes_bp.route('/signals')
def signals():
    """信号列表页"""
    service = get_data_service()
    return render_template(
        'signals.html',
        signals=service.get_signals_history(),
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@routes_bp.route('/stock/<code>')
def stock(code):
    """单股详情页"""
    service = get_data_service()
    return render_template(
        'stock.html',
        stock=service.get_stock_quote(code),
        kline=service.get_stock_kline(code),
        analysis=service.get_stock_analysis(code),
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
