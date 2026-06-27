# -*- coding: utf-8 -*-
"""
Backtest API - 回测接口

功能：
1. 运行回测（单股 / 多股）
2. 获取回测结果列表
3. 获取回测结果详情
4. 删除回测结果
5. 策略模板列表
6. 自定义策略回测
"""

import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query

from backend.services.backtest_engine import (
    BacktestEngine,
    get_strategy_templates,
    get_custom_strategy_template,
    validate_custom_dsl,
)
from backend.models.database import (
    DATABASE_PATH,
    init_db,
    add_backtest_result,
    get_backtest_results,
    get_backtest_result_by_id,
    delete_backtest_result,
)

router = APIRouter()


# ───────────────────────────────────────────────
# Pydantic Models
# ───────────────────────────────────────────────

class BacktestRunRequest(BaseModel):
    """回测运行请求"""
    symbol: str = Field(..., description="股票代码，如 000001")
    strategy_name: str = Field(..., description="策略名称：dual_ma/macd/kd/cai_sen/bai_da/custom")
    start_date: str = Field(..., description="起始日期（YYYY-MM-DD）")
    end_date: str = Field(..., description="结束日期（YYYY-MM-DD）")
    initial_cash: float = Field(100000.0, description="初始资金")
    commission_rate: float = Field(0.0003, description="手续费率")
    slippage: float = Field(0.001, description="滑点率")
    params: Optional[Dict[str, Any]] = Field(None, description="策略参数字典")
    custom_code: Optional[str] = Field(None, description="自定义策略代码（strategy_name=custom时必需）")
    adjust: str = Field("qfq", description="复权方式：qfq/hfq/none")


class BacktestRunMultiRequest(BaseModel):
    """多股回测运行请求"""
    symbols: List[str] = Field(..., description="股票代码列表")
    strategy_name: str = Field(..., description="策略名称")
    start_date: str = Field(..., description="起始日期（YYYY-MM-DD）")
    end_date: str = Field(..., description="结束日期（YYYY-MM-DD）")
    initial_cash: float = Field(100000.0, description="初始资金")
    commission_rate: float = Field(0.0003, description="手续费率")
    slippage: float = Field(0.001, description="滑点率")
    params: Optional[Dict[str, Any]] = Field(None, description="策略参数字典")
    custom_code: Optional[str] = Field(None, description="自定义策略代码")
    adjust: str = Field("qfq", description="复权方式")


class BacktestResultResponse(BaseModel):
    """回测结果响应"""
    id: Optional[str] = None
    strategy_name: str
    symbols: List[str]
    start_date: str
    end_date: str
    initial_cash: float
    final_value: float
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    profit_loss_ratio: float
    total_trades: int
    win_trades: int
    loss_trades: int
    avg_holding_days: float
    equity_curve: List[Dict[str, Any]]
    trades: List[Dict[str, Any]]
    monthly_returns: Dict[str, float]
    params: Dict[str, Any]
    error: Optional[str] = None


# ───────────────────────────────────────────────
# Helper
# ───────────────────────────────────────────────

async def _get_db_conn():
    """获取数据库连接"""
    return await init_db(DATABASE_PATH)


def _result_to_dict(result, result_id: str = None) -> Dict[str, Any]:
    """将 BacktestResult 转换为 API 响应字典"""
    return {
        "id": result_id,
        "strategy_name": result.strategy_name,
        "symbols": result.symbols,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "initial_cash": result.initial_cash,
        "final_value": result.final_value,
        "total_return": result.total_return,
        "annual_return": result.annual_return,
        "max_drawdown": result.max_drawdown,
        "sharpe_ratio": result.sharpe_ratio,
        "win_rate": result.win_rate,
        "profit_loss_ratio": result.profit_loss_ratio,
        "total_trades": result.total_trades,
        "win_trades": result.win_trades,
        "loss_trades": result.loss_trades,
        "avg_holding_days": result.avg_holding_days,
        "equity_curve": [
            {
                "date": s.date,
                "cash": s.cash,
                "position": s.position,
                "close_price": s.close_price,
                "market_value": s.market_value,
                "total_value": s.total_value,
                "equity_return": s.equity_return,
            }
            for s in result.equity_curve
        ],
        "trades": [
            {
                "date": t.date,
                "action": t.action,
                "symbol": t.symbol,
                "price": t.price,
                "size": t.size,
                "amount": t.amount,
                "commission": t.commission,
                "reason": t.reason,
                "cash_after": t.cash_after,
                "position_after": t.position_after,
            }
            for t in result.trades
        ],
        "monthly_returns": result.monthly_returns,
        "params": result.params,
        "error": result.error,
    }


# ───────────────────────────────────────────────
# API Routes
# ───────────────────────────────────────────────

@router.get("/backtest/strategies")
async def list_strategies():
    """
    获取所有可用回测策略模板
    """
    templates = get_strategy_templates()
    return {
        "status": "ok",
        "count": len(templates),
        "strategies": templates,
    }


@router.get("/backtest/custom-template")
async def get_custom_template():
    """
    获取自定义策略代码模板
    """
    return {
        "status": "ok",
        "template": get_custom_strategy_template(),
    }


@router.post("/backtest/run")
async def run_backtest(request: BacktestRunRequest):
    """
    运行单股回测
    
    对指定股票运行回测策略，返回完整回测结果。
    """
    # 自定义策略 DSL 入口校验：拒绝非 JSON / 非法结构，并阻止旧的 Python 代码字符串
    if request.strategy_name == "custom" or request.custom_code:
        if not request.custom_code:
            raise HTTPException(status_code=400, detail="自定义策略需要提供 DSL JSON")
        try:
            dsl = json.loads(request.custom_code)
            validate_custom_dsl(dsl)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"自定义策略 DSL 不是合法 JSON: {e}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"自定义策略 DSL 校验失败: {e}")
    
    engine = BacktestEngine()
    
    result = engine.run(
        symbol=request.symbol,
        strategy_name=request.strategy_name,
        start_date=request.start_date,
        end_date=request.end_date,
        initial_cash=request.initial_cash,
        commission_rate=request.commission_rate,
        slippage=request.slippage,
        params=request.params or {},
        custom_code=request.custom_code,
        adjust=request.adjust,
    )
    
    # 保存到数据库
    conn = await _get_db_conn()
    try:
        result_id = await add_backtest_result(
            conn,
            strategy_name=result.strategy_name,
            symbols=result.symbols,
            start_date=result.start_date,
            end_date=result.end_date,
            config={
                "initial_cash": result.initial_cash,
                "commission_rate": request.commission_rate,
                "slippage": request.slippage,
                "params": result.params,
                "adjust": request.adjust,
            },
            result=_result_to_dict(result),
        )
    except Exception as e:
        result_id = None
    finally:
        await conn.close()
    
    return {
        "status": "ok",
        "result_id": result_id,
        "result": _result_to_dict(result, result_id),
    }


@router.post("/backtest/run-multi")
async def run_multi_backtest(request: BacktestRunMultiRequest):
    """
    运行多股回测
    
    对每只股票独立运行回测，返回汇总结果。
    """
    # 自定义策略 DSL 入口校验
    if request.strategy_name == "custom" or request.custom_code:
        if not request.custom_code:
            raise HTTPException(status_code=400, detail="自定义策略需要提供 DSL JSON")
        try:
            dsl = json.loads(request.custom_code)
            validate_custom_dsl(dsl)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"自定义策略 DSL 不是合法 JSON: {e}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"自定义策略 DSL 校验失败: {e}")
    
    engine = BacktestEngine()
    results = []
    
    for symbol in request.symbols:
        result = engine.run(
            symbol=symbol,
            strategy_name=request.strategy_name,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_cash=request.initial_cash,
            commission_rate=request.commission_rate,
            slippage=request.slippage,
            params=request.params or {},
            custom_code=request.custom_code,
            adjust=request.adjust,
        )
        results.append(_result_to_dict(result))
    
    # 汇总统计
    valid_results = [r for r in results if not r.get("error")]
    if valid_results:
        avg_return = sum(r["total_return"] for r in valid_results) / len(valid_results)
        avg_sharpe = sum(r.get("sharpe_ratio", 0) for r in valid_results) / len(valid_results)
    else:
        avg_return = 0.0
        avg_sharpe = 0.0
    
    return {
        "status": "ok",
        "symbols": request.symbols,
        "count": len(results),
        "valid_count": len(valid_results),
        "avg_return": round(avg_return, 4),
        "avg_sharpe": round(avg_sharpe, 4),
        "results": results,
    }


@router.get("/backtest/results")
async def list_backtest_results(
    strategy_name: Optional[str] = Query(None, description="按策略筛选"),
    limit: int = Query(50, ge=1, le=100),
):
    """
    获取回测历史记录列表
    """
    conn = await _get_db_conn()
    try:
        items = await get_backtest_results(conn, strategy_name=strategy_name, limit=limit)
        return {
            "status": "ok",
            "count": len(items),
            "results": items,
        }
    finally:
        await conn.close()


@router.get("/backtest/results/{result_id}")
async def get_backtest_detail(result_id: str):
    """
    获取回测结果详情
    """
    conn = await _get_db_conn()
    try:
        item = await get_backtest_result_by_id(conn, result_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"Backtest result not found: {result_id}")
        
        # 解析 JSON 字段
        import json
        try:
            item["config_json"] = json.loads(item["config_json"]) if item.get("config_json") else {}
        except json.JSONDecodeError:
            pass
        try:
            item["result_json"] = json.loads(item["result_json"]) if item.get("result_json") else {}
        except json.JSONDecodeError:
            pass
        try:
            item["symbols"] = json.loads(item["symbols"]) if item.get("symbols") else []
        except json.JSONDecodeError:
            pass
        
        return {
            "status": "ok",
            "result": item,
        }
    finally:
        await conn.close()


@router.delete("/backtest/results/{result_id}")
async def remove_backtest_result(result_id: str):
    """
    删除回测记录
    """
    conn = await _get_db_conn()
    try:
        ok = await delete_backtest_result(conn, result_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Backtest result not found: {result_id}")
        return {"status": "ok", "result_id": result_id}
    finally:
        await conn.close()
