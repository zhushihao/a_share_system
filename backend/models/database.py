# -*- coding: utf-8 -*-
"""
Database Layer - SQLite Async (aiosqlite)

表结构：
  - watchlist: 自选股
  - signals: 信号历史
  - settings: 系统设置
  - backtest_results: 回测记录
"""

import os
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict

import aiosqlite


# ───────────────────────────────────────────────
# 配置
# ───────────────────────────────────────────────

# 使用 backend/config.py 中的 DATA_DIR，但保持独立引用避免循环导入
_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "backend")
os.makedirs(_DB_DIR, exist_ok=True)
DATABASE_PATH = os.path.join(_DB_DIR, "quant_workbench.db")


# ───────────────────────────────────────────────
# 初始化
# ───────────────────────────────────────────────

async def init_db(db_path: str = DATABASE_PATH) -> aiosqlite.Connection:
    """
    初始化数据库连接并创建表（如果不存在）。
    
    Returns:
        aiosqlite.Connection 连接对象
    """
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    # 启用 WAL 模式，提高并发性能（FastAPI 多 worker 场景）
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await _create_tables(conn)
    return conn


async def _create_tables(conn: aiosqlite.Connection) -> None:
    """创建所有表结构"""
    
    # 自选股表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL UNIQUE,
            name TEXT,
            group_name TEXT DEFAULT '默认',
            added_at TEXT NOT NULL,
            notes TEXT,
            tags TEXT,            -- JSON 数组
            alert_price_high REAL,
            alert_price_low REAL
        )
    """)
    
    # 信号历史表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT,
            timestamp TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            strategy TEXT,
            description TEXT,
            confidence INTEGER DEFAULT 50,
            price REAL,
            target_price REAL,
            stop_loss REAL,
            triggered INTEGER DEFAULT 1,
            acknowledged INTEGER DEFAULT 0,
            status TEXT DEFAULT 'open',
            exit_price REAL,
            exit_date TEXT,
            pnl_pct REAL,
            max_pnl_pct REAL,
            min_pnl_pct REAL
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status)
    """)
    
    # 迁移：为旧表添加新列（如果缺失）
    await _migrate_signals_table(conn)
    
    # 系统设置表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    
    # 回测记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id TEXT PRIMARY KEY,
            strategy_name TEXT,
            symbols TEXT,          -- JSON 数组
            start_date TEXT,
            end_date TEXT,
            config_json TEXT,      -- JSON 对象
            result_json TEXT,      -- JSON 对象
            created_at TEXT NOT NULL
        )
    """)
    
    await conn.commit()


async def _migrate_signals_table(conn: aiosqlite.Connection) -> None:
    """迁移信号表：为旧表添加新列（如果缺失）"""
    # 获取当前表的列信息
    cursor = await conn.execute("PRAGMA table_info(signals)")
    columns = await cursor.fetchall()
    column_names = {c["name"] for c in columns}
    
    # 需要添加的新列
    new_columns = [
        ("status", "TEXT DEFAULT 'open'"),
        ("exit_price", "REAL"),
        ("exit_date", "TEXT"),
        ("pnl_pct", "REAL"),
        ("max_pnl_pct", "REAL"),
        ("min_pnl_pct", "REAL"),
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in column_names:
            await conn.execute(f"ALTER TABLE signals ADD COLUMN {col_name} {col_type}")
            await conn.commit()


# ───────────────────────────────────────────────
# 连接管理（单例）
# ───────────────────────────────────────────────

_db_instance: Optional[aiosqlite.Connection] = None

async def get_db(db_path: str = DATABASE_PATH) -> aiosqlite.Connection:
    """获取全局数据库连接（单例，自动初始化）"""
    global _db_instance
    if _db_instance is None or _db_instance.closed:
        _db_instance = await init_db(db_path)
    return _db_instance


async def close_db() -> None:
    """关闭全局数据库连接"""
    global _db_instance
    if _db_instance is not None and not _db_instance.closed:
        await _db_instance.close()
        _db_instance = None


# ───────────────────────────────────────────────
# Watchlist CRUD
# ───────────────────────────────────────────────

@dataclass
class WatchlistRecord:
    """自选股记录"""
    id: str
    symbol: str
    name: str
    group: str = "默认"
    added_at: str = ""
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    alert_price_high: Optional[float] = None
    alert_price_low: Optional[float] = None
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.added_at:
            self.added_at = datetime.now().isoformat()


async def add_watchlist(
    conn: aiosqlite.Connection,
    symbol: str,
    name: str,
    group: str = "默认",
    notes: str = "",
    tags: List[str] = None,
    alert_price_high: Optional[float] = None,
    alert_price_low: Optional[float] = None,
) -> WatchlistRecord:
    """添加自选股"""
    record = WatchlistRecord(
        id=str(uuid.uuid4())[:8],
        symbol=symbol,
        name=name,
        group=group,
        added_at=datetime.now().isoformat(),
        notes=notes,
        tags=tags or [],
        alert_price_high=alert_price_high,
        alert_price_low=alert_price_low,
    )
    
    await conn.execute(
        """
        INSERT INTO watchlist (id, symbol, name, group_name, added_at, notes, tags, alert_price_high, alert_price_low)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            name=excluded.name,
            group_name=excluded.group_name,
            notes=excluded.notes,
            tags=excluded.tags,
            alert_price_high=excluded.alert_price_high,
            alert_price_low=excluded.alert_price_low
        """,
        (
            record.id, record.symbol, record.name, record.group, record.added_at,
            record.notes, json.dumps(record.tags), record.alert_price_high, record.alert_price_low,
        ),
    )
    await conn.commit()
    return record


async def get_watchlist(
    conn: aiosqlite.Connection,
    group: Optional[str] = None,
) -> List[WatchlistRecord]:
    """获取自选股列表"""
    if group:
        cursor = await conn.execute(
            "SELECT * FROM watchlist WHERE group_name = ? ORDER BY added_at DESC",
            (group,),
        )
    else:
        cursor = await conn.execute(
            "SELECT * FROM watchlist ORDER BY added_at DESC"
        )
    
    rows = await cursor.fetchall()
    return [_row_to_watchlist(r) for r in rows]


async def get_watchlist_by_symbol(conn: aiosqlite.Connection, symbol: str) -> Optional[WatchlistRecord]:
    """根据代码获取自选股"""
    cursor = await conn.execute(
        "SELECT * FROM watchlist WHERE symbol = ?",
        (symbol,),
    )
    row = await cursor.fetchone()
    if row:
        return _row_to_watchlist(row)
    return None


async def delete_watchlist(conn: aiosqlite.Connection, symbol: str) -> bool:
    """删除自选股"""
    cursor = await conn.execute(
        "DELETE FROM watchlist WHERE symbol = ?",
        (symbol,),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def update_watchlist_group(
    conn: aiosqlite.Connection,
    symbol: str,
    group: str,
) -> bool:
    """修改自选股分组"""
    cursor = await conn.execute(
        "UPDATE watchlist SET group_name = ? WHERE symbol = ?",
        (group, symbol),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def update_watchlist_group_batch(
    conn: aiosqlite.Connection,
    symbols: List[str],
    group: str,
) -> int:
    """批量修改自选股分组"""
    if not symbols:
        return 0
    placeholders = ','.join('?' * len(symbols))
    cursor = await conn.execute(
        f"UPDATE watchlist SET group_name = ? WHERE symbol IN ({placeholders})",
        (group, *symbols),
    )
    await conn.commit()
    return cursor.rowcount


async def add_watchlist_batch(
    conn: aiosqlite.Connection,
    items: List[Dict[str, Any]],
) -> int:
    """批量添加/更新自选股

    items 格式: [{"symbol": "...", "name": "...", "group": "..."}, ...]
    """
    if not items:
        return 0
    now = datetime.now().isoformat()
    params = []
    for item in items:
        symbol = (item.get("symbol") or "").strip()
        name = (item.get("name") or "").strip()
        if not symbol or not name:
            continue
        group = (item.get("group") or "默认").strip() or "默认"
        notes = item.get("notes") or ""
        tags = json.dumps(item.get("tags") or [])
        alert_high = item.get("alert_price_high")
        alert_low = item.get("alert_price_low")
        params.append((str(uuid.uuid4())[:8], symbol, name, group, now, notes, tags, alert_high, alert_low))
    if not params:
        return 0
    await conn.executemany(
        """
        INSERT INTO watchlist (id, symbol, name, group_name, added_at, notes, tags, alert_price_high, alert_price_low)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            name=excluded.name,
            group_name=excluded.group_name,
            notes=excluded.notes,
            tags=excluded.tags,
            alert_price_high=excluded.alert_price_high,
            alert_price_low=excluded.alert_price_low
        """,
        params,
    )
    await conn.commit()
    return len(params)


async def get_watchlist_groups(conn: aiosqlite.Connection) -> List[str]:
    """获取所有分组名称"""
    cursor = await conn.execute(
        "SELECT DISTINCT group_name FROM watchlist ORDER BY group_name"
    )
    rows = await cursor.fetchall()
    return [r[0] for r in rows if r[0]]


def _row_to_watchlist(row: aiosqlite.Row) -> WatchlistRecord:
    """将数据库行转换为 WatchlistRecord"""
    return WatchlistRecord(
        id=row["id"],
        symbol=row["symbol"],
        name=row["name"],
        group=row["group_name"],
        added_at=row["added_at"],
        notes=row["notes"] or "",
        tags=json.loads(row["tags"]) if row["tags"] else [],
        alert_price_high=row["alert_price_high"],
        alert_price_low=row["alert_price_low"],
    )


# ───────────────────────────────────────────────
# Settings CRUD
# ───────────────────────────────────────────────

async def set_setting(conn: aiosqlite.Connection, key: str, value: Any) -> None:
    """设置系统配置"""
    await conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        (key, json.dumps(value), datetime.now().isoformat()),
    )
    await conn.commit()


async def get_setting(conn: aiosqlite.Connection, key: str, default: Any = None) -> Any:
    """获取系统配置"""
    cursor = await conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,),
    )
    row = await cursor.fetchone()
    if row:
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]
    return default


async def get_all_settings(conn: aiosqlite.Connection) -> Dict[str, Any]:
    """获取所有系统配置"""
    cursor = await conn.execute("SELECT key, value FROM settings")
    rows = await cursor.fetchall()
    result = {}
    for row in rows:
        try:
            result[row["key"]] = json.loads(row["value"])
        except json.JSONDecodeError:
            result[row["key"]] = row["value"]
    return result


async def delete_setting(conn: aiosqlite.Connection, key: str) -> bool:
    """删除配置"""
    cursor = await conn.execute(
        "DELETE FROM settings WHERE key = ?",
        (key,),
    )
    await conn.commit()
    return cursor.rowcount > 0


# ───────────────────────────────────────────────
# Signals CRUD
# ───────────────────────────────────────────────

async def add_signal(
    conn: aiosqlite.Connection,
    symbol: str,
    name: str,
    signal_type: str,
    strategy: str,
    description: str,
    confidence: int = 50,
    price: Optional[float] = None,
    target_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    timestamp: Optional[str] = None,
    status: str = "open",
) -> Optional[str]:
    """添加信号，返回信号ID；若同一天已存在相同 symbol+type+strategy 的信号则跳过去重"""
    ts = timestamp or datetime.now().isoformat()
    date_part = ts[:10]  # YYYY-MM-DD

    # 去重检查：同一天同一股票同一策略同方向信号已存在则跳过
    cursor = await conn.execute(
        """
        SELECT id FROM signals
        WHERE symbol = ? AND signal_type = ? AND strategy = ? AND date(timestamp) = date(?)
        LIMIT 1
        """,
        (symbol, signal_type, strategy, ts),
    )
    row = await cursor.fetchone()
    if row:
        return None  # 重复信号，跳过

    sid = str(uuid.uuid4())[:8]
    await conn.execute(
        """
        INSERT INTO signals (id, symbol, name, timestamp, signal_type, strategy, description, confidence, price, target_price, stop_loss, status, pnl_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sid, symbol, name, ts, signal_type, strategy, description, confidence, price, target_price, stop_loss, status, None),
    )
    await conn.commit()
    return sid


async def get_signals(
    conn: aiosqlite.Connection,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """获取信号列表"""
    params = []
    query = "SELECT * FROM signals"
    conditions = []
    
    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol)
    if strategy:
        conditions.append("strategy = ?")
        params.append(strategy)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def acknowledge_signal(conn: aiosqlite.Connection, signal_id: str) -> bool:
    """标记信号为已确认"""
    cursor = await conn.execute(
        "UPDATE signals SET acknowledged = 1 WHERE id = ?",
        (signal_id,),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def delete_signal(conn: aiosqlite.Connection, signal_id: str) -> bool:
    """删除信号"""
    cursor = await conn.execute(
        "DELETE FROM signals WHERE id = ?",
        (signal_id,),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def update_signal_status(
    conn: aiosqlite.Connection,
    signal_id: str,
    status: str,
    exit_price: Optional[float] = None,
    pnl_pct: Optional[float] = None,
) -> bool:
    """更新信号状态（平仓/触发/过期）"""
    exit_date = datetime.now().isoformat() if status != "open" else None
    
    cursor = await conn.execute(
        """
        UPDATE signals SET status = ?, exit_price = ?, exit_date = ?, pnl_pct = ?
        WHERE id = ?
        """,
        (status, exit_price, exit_date, pnl_pct, signal_id),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def track_signal_performance(
    conn: aiosqlite.Connection,
    signal_id: str,
    current_price: float,
) -> Dict[str, Any]:
    """追踪信号绩效：根据当前价格更新浮动盈亏"""
    cursor = await conn.execute(
        "SELECT * FROM signals WHERE id = ? AND status = 'open'",
        (signal_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return {}
    
    signal = dict(row)
    entry_price = signal.get("price") or current_price
    signal_type = signal.get("signal_type", "BUY")
    target_price = signal.get("target_price")
    stop_loss = signal.get("stop_loss")
    
    # 计算盈亏百分比
    if signal_type == "BUY":
        pnl_pct = (current_price - entry_price) / entry_price * 100
    else:
        pnl_pct = (entry_price - current_price) / entry_price * 100
    
    # 更新最大/最小盈亏
    max_pnl = signal.get("max_pnl_pct")
    min_pnl = signal.get("min_pnl_pct")
    
    if max_pnl is None or pnl_pct > max_pnl:
        max_pnl = pnl_pct
    if min_pnl is None or pnl_pct < min_pnl:
        min_pnl = pnl_pct
    
    # 检查是否触发目标/止损
    status = "open"
    exit_price = None
    
    if signal_type == "BUY":
        if target_price and current_price >= target_price:
            status = "hit_target"
            exit_price = current_price
        elif stop_loss and current_price <= stop_loss:
            status = "hit_stop"
            exit_price = current_price
    else:
        if target_price and current_price <= target_price:
            status = "hit_target"
            exit_price = current_price
        elif stop_loss and current_price >= stop_loss:
            status = "hit_stop"
            exit_price = current_price
    
    # 更新数据库
    await conn.execute(
        """
        UPDATE signals SET pnl_pct = ?, max_pnl_pct = ?, min_pnl_pct = ?, status = ?, exit_price = ?, exit_date = ?
        WHERE id = ?
        """,
        (pnl_pct, max_pnl, min_pnl, status, exit_price, datetime.now().isoformat() if status != "open" else None, signal_id),
    )
    await conn.commit()
    
    return {
        "signal_id": signal_id,
        "status": status,
        "entry_price": entry_price,
        "current_price": current_price,
        "pnl_pct": pnl_pct,
        "max_pnl_pct": max_pnl,
        "min_pnl_pct": min_pnl,
        "target_price": target_price,
        "stop_loss": stop_loss,
    }


async def expire_old_signals(
    conn: aiosqlite.Connection,
    days: int = 7,
) -> int:
    """将超过 N 天未触发的信号标记为过期"""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    cursor = await conn.execute(
        """
        UPDATE signals SET status = 'expired', exit_date = ?
        WHERE status = 'open' AND timestamp < ?
        """,
        (datetime.now().isoformat(), cutoff),
    )
    await conn.commit()
    return cursor.rowcount


async def get_signal_performance_stats(
    conn: aiosqlite.Connection,
    strategy: Optional[str] = None,
    days: int = 30,
) -> Dict[str, Any]:
    """获取信号绩效统计：胜率、平均盈亏、最大盈利/亏损等"""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    # 基础查询条件
    conditions = ["timestamp >= ?"]
    params = [cutoff]
    if strategy:
        conditions.append("strategy = ?")
        params.append(strategy)
    
    where_clause = " AND ".join(conditions)
    
    # 总信号数
    cursor = await conn.execute(
        f"SELECT COUNT(*) as total FROM signals WHERE {where_clause}",
        params,
    )
    row = await cursor.fetchone()
    total = row["total"] if row else 0
    
    # 已平仓信号统计
    cursor = await conn.execute(
        f"""
        SELECT 
            COUNT(*) as closed_count,
            AVG(pnl_pct) as avg_pnl,
            MAX(pnl_pct) as max_pnl,
            MIN(pnl_pct) as min_pnl,
            SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as win_count,
            SUM(CASE WHEN pnl_pct < 0 THEN 1 ELSE 0 END) as loss_count
        FROM signals
        WHERE {where_clause} AND status IN ('hit_target', 'hit_stop', 'expired', 'manual')
        """,
        params,
    )
    row = await cursor.fetchone()
    closed_count = row["closed_count"] or 0
    win_count = row["win_count"] or 0
    loss_count = row["loss_count"] or 0
    avg_pnl = row["avg_pnl"] or 0
    max_pnl = row["max_pnl"] or 0
    min_pnl = row["min_pnl"] or 0
    
    win_rate = (win_count / closed_count * 100) if closed_count > 0 else 0
    
    return {
        "total_signals": total,
        "closed_signals": closed_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 2),
        "avg_pnl_pct": round(avg_pnl, 2),
        "max_pnl_pct": round(max_pnl, 2),
        "min_pnl_pct": round(min_pnl, 2),
        "strategy": strategy,
        "days": days,
    }


# ───────────────────────────────────────────────
# Backtest Results CRUD
# ───────────────────────────────────────────────

async def add_backtest_result(
    conn: aiosqlite.Connection,
    strategy_name: str,
    symbols: List[str],
    start_date: str,
    end_date: str,
    config: Dict[str, Any],
    result: Dict[str, Any],
) -> str:
    """添加回测记录，返回ID"""
    rid = str(uuid.uuid4())[:8]
    
    await conn.execute(
        """
        INSERT INTO backtest_results (id, strategy_name, symbols, start_date, end_date, config_json, result_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rid, strategy_name, json.dumps(symbols), start_date, end_date,
            json.dumps(config), json.dumps(result), datetime.now().isoformat(),
        ),
    )
    await conn.commit()
    return rid


async def get_backtest_results(
    conn: aiosqlite.Connection,
    strategy_name: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """获取回测记录列表"""
    if strategy_name:
        cursor = await conn.execute(
            "SELECT * FROM backtest_results WHERE strategy_name = ? ORDER BY created_at DESC LIMIT ?",
            (strategy_name, limit),
        )
    else:
        cursor = await conn.execute(
            "SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_backtest_result_by_id(conn: aiosqlite.Connection, result_id: str) -> Optional[Dict[str, Any]]:
    """根据ID获取回测记录"""
    cursor = await conn.execute(
        "SELECT * FROM backtest_results WHERE id = ?",
        (result_id,),
    )
    row = await cursor.fetchone()
    if row:
        return dict(row)
    return None


async def delete_backtest_result(conn: aiosqlite.Connection, result_id: str) -> bool:
    """删除回测记录"""
    cursor = await conn.execute(
        "DELETE FROM backtest_results WHERE id = ?",
        (result_id,),
    )
    await conn.commit()
    return cursor.rowcount > 0


# ───────────────────────────────────────────────
# 便捷：同步包装（用于非异步上下文）
# ───────────────────────────────────────────────

import asyncio


def _run_sync(coro):
    """在同步上下文中运行异步协程"""
    try:
        loop = asyncio.get_running_loop()
        # 已有事件循环，使用 nest_asyncio 或返回 future
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.get_event_loop().run_until_complete(coro)
    except RuntimeError:
        # 无事件循环，直接创建
        return asyncio.run(coro)


def sync_add_watchlist(**kwargs) -> WatchlistRecord:
    """同步添加自选股"""
    async def _do():
        conn = await get_db()
        return await add_watchlist(conn, **kwargs)
    return _run_sync(_do())


def sync_get_watchlist(group: Optional[str] = None) -> List[WatchlistRecord]:
    """同步获取自选股"""
    async def _do():
        conn = await get_db()
        return await get_watchlist(conn, group)
    return _run_sync(_do())


# ───────────────────────────────────────────────
# 测试
# ───────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    
    async def _test():
        print("=== Database Layer Test ===")
        
        # 使用测试数据库
        test_db = os.path.join(_DB_DIR, "test_quant_workbench.db")
        if os.path.exists(test_db):
            os.remove(test_db)
        
        conn = await init_db(test_db)
        
        # 1. Watchlist CRUD
        print("\n[1] Watchlist CRUD")
        
        # 添加
        r1 = await add_watchlist(conn, "600519", "贵州茅台", group="白酒", tags=["蓝筹", "白酒"])
        r2 = await add_watchlist(conn, "000001", "平安银行", group="银行", notes="测试")
        print(f"  Added: {r1.symbol} ({r1.name}), id={r1.id}")
        print(f"  Added: {r2.symbol} ({r2.name}), id={r2.id}")
        
        # 重复添加（应更新）
        r1_dup = await add_watchlist(conn, "600519", "贵州茅台", group="白酒龙头")
        print(f"  Update same symbol: {r1_dup.group}")
        
        # 获取列表
        all_items = await get_watchlist(conn)
        print(f"  Total items: {len(all_items)}")
        assert len(all_items) == 2
        
        # 按分组获取
        baijiu = await get_watchlist(conn, group="白酒龙头")
        print(f"  白酒龙头 group: {len(baijiu)} items")
        assert len(baijiu) == 1
        
        # 按 symbol 获取
        item = await get_watchlist_by_symbol(conn, "600519")
        assert item is not None
        assert item.name == "贵州茅台"
        assert item.group == "白酒龙头"
        print(f"  By symbol OK: {item.name}")
        
        # 修改分组
        ok = await update_watchlist_group(conn, "000001", "金融")
        assert ok
        item = await get_watchlist_by_symbol(conn, "000001")
        assert item.group == "金融"
        print(f"  Update group OK: {item.group}")
        
        # 获取分组列表
        groups = await get_watchlist_groups(conn)
        print(f"  Groups: {groups}")
        assert "白酒龙头" in groups
        assert "金融" in groups
        
        # 删除
        ok = await delete_watchlist(conn, "000001")
        assert ok
        all_items = await get_watchlist(conn)
        assert len(all_items) == 1
        print(f"  Delete OK: remaining {len(all_items)}")
        
        # Edge case: 删除不存在的
        ok = await delete_watchlist(conn, "999999")
        assert not ok
        print(f"  Delete non-existent: handled correctly")
        
        # 2. Settings CRUD
        print("\n[2] Settings CRUD")
        await set_setting(conn, "theme", "dark")
        await set_setting(conn, "tdx_dir", "D:/TDX")
        
        theme = await get_setting(conn, "theme")
        assert theme == "dark"
        print(f"  Get setting: theme={theme}")
        
        tdx_dir = await get_setting(conn, "tdx_dir")
        assert tdx_dir == "D:/TDX"
        print(f"  Get setting: tdx_dir={tdx_dir}")
        
        missing = await get_setting(conn, "not_exist", default="default_val")
        assert missing == "default_val"
        print(f"  Default value: {missing}")
        
        all_settings = await get_all_settings(conn)
        print(f"  All settings: {all_settings}")
        assert len(all_settings) == 2
        
        # 3. Signals CRUD
        print("\n[3] Signals CRUD")
        sid = await add_signal(
            conn, "600519", "贵州茅台", "BUY", "双均线",
            "MA5 上穿 MA20", confidence=85, price=1500.0, target_price=1600.0, stop_loss=1400.0,
        )
        if sid is None:
            # 同一天已存在，先删除再重新添加
            signals = await get_signals(conn, symbol="600519")
            for s in signals:
                await delete_signal(conn, s["id"])
            sid = await add_signal(
                conn, "600519", "贵州茅台", "BUY", "双均线",
                "MA5 上穿 MA20", confidence=85, price=1500.0, target_price=1600.0, stop_loss=1400.0,
            )
        print(f"  Added signal: {sid}")
        assert sid is not None
        
        signals = await get_signals(conn, symbol="600519")
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "BUY"
        print(f"  Get signals: {len(signals)} items")
        
        ok = await acknowledge_signal(conn, sid)
        assert ok
        signals = await get_signals(conn, symbol="600519")
        assert signals[0]["acknowledged"] == 1
        print(f"  Acknowledge OK")
        
        ok = await delete_signal(conn, sid)
        assert ok
        signals = await get_signals(conn, symbol="600519")
        assert len(signals) == 0
        print(f"  Delete signal OK")
        
        # 4. Backtest Results CRUD
        print("\n[4] Backtest Results CRUD")
        rid = await add_backtest_result(
            conn, "双均线", ["600519", "000001"], "2024-01-01", "2024-12-31",
            config={"short_ma": 5, "long_ma": 20},
            result={"total_return": 0.15, "sharpe": 1.2},
        )
        print(f"  Added backtest: {rid}")
        
        results = await get_backtest_results(conn)
        assert len(results) == 1
        print(f"  Get results: {len(results)} items")
        
        result = await get_backtest_result_by_id(conn, rid)
        assert result is not None
        assert result["strategy_name"] == "双均线"
        print(f"  By ID OK: {result['strategy_name']}")
        
        ok = await delete_backtest_result(conn, rid)
        assert ok
        results = await get_backtest_results(conn)
        assert len(results) == 0
        print(f"  Delete result OK")
        
        # Edge case: get non-existent
        result = await get_backtest_result_by_id(conn, "nonexistent")
        assert result is None
        print(f"  Get non-existent: handled correctly")
        
        await conn.close()
        print("\n=== All Database Tests PASSED ===")
    
    asyncio.run(_test())
