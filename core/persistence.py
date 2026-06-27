"""
数据持久化层 - SQLite 持久化引擎

表结构：
- stock_klines: 个股K线历史数据
- patterns: 型态识别结果
- sector_rankings: 板块排名历史
- traffic_signals: 交通灯信号历史
- pipeline_runs: 流水线执行记录
- harness_metrics: Harness 执行指标
"""

import sqlite3
import pandas as pd
import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field


class PersistenceEngine:
    """
    SQLite 持久化引擎
    
    使用方式：
    1. 初始化时自动创建表结构
    2. 提供 insert/query/update 接口
    3. 支持 DataFrame 直接读写
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base, "data", "system.db")
        
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_tables()
    
    def _connect(self):
        return sqlite3.connect(self.db_path)
    
    def _init_tables(self) -> None:
        """初始化表结构"""
        with self._connect() as conn:
            # 个股K线
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_klines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL, high REAL, low REAL, close REAL,
                    volume INTEGER, amount REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(code, date)
                )
            """)
            
            # 型态识别结果
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    pattern_type TEXT NOT NULL,
                    confidence REAL,
                    status TEXT,
                    start_date TEXT, end_date TEXT,
                    data_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 板块排名
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sector_rankings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    sector_code TEXT NOT NULL,
                    sector_name TEXT,
                    score REAL,
                    rank INTEGER,
                    lifecycle TEXT,
                    style TEXT,
                    return_20d REAL,
                    volume_change REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(date, sector_code)
                )
            """)
            
            # 交通灯信号
            conn.execute("""
                CREATE TABLE IF NOT EXISTS traffic_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    code TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    category TEXT,
                    reasons TEXT,
                    entry_price REAL, stop_loss REAL, target_1 REAL,
                    position_size REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 流水线执行记录
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT UNIQUE,
                    date TEXT,
                    mode TEXT,
                    pipeline_name TEXT,
                    success INTEGER,
                    completed_steps INTEGER,
                    total_steps INTEGER,
                    duration_ms REAL,
                    context_keys TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Harness 指标
            conn.execute("""
                CREATE TABLE IF NOT EXISTS harness_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    name TEXT,
                    success INTEGER,
                    duration_ms REAL,
                    inputs TEXT,
                    outputs TEXT,
                    error TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
    
    # ==================== 个股K线 ====================
    
    def save_stock_klines(self, code: str, df: pd.DataFrame) -> None:
        """保存个股K线（UPSERT：先删除已有日期，再插入）"""
        if len(df) == 0:
            return
        df = df.copy()
        df["code"] = code
        if "date" not in df.columns and "time" in df.columns:
            df = df.rename(columns={"time": "date"})
        
        cols = ["code", "date", "open", "high", "low", "close", "volume", "amount"]
        available = [c for c in cols if c in df.columns]
        df_to_save = df[available]
        
        # 将 date 列转换为字符串格式（SQLite 参数绑定不支持 Timestamp）
        if "date" in df_to_save.columns:
            df_to_save["date"] = pd.to_datetime(df_to_save["date"]).dt.strftime("%Y-%m-%d")
        
        with self._connect() as conn:
            # 先删除已有的日期（避免 UNIQUE 约束冲突）
            dates = df_to_save["date"].tolist()
            placeholders = ",".join(["?"] * len(dates))
            conn.execute(f"DELETE FROM stock_klines WHERE code = ? AND date IN ({placeholders})", [code] + dates)
            
            df_to_save.to_sql("stock_klines", conn, if_exists="append", index=False)
            conn.commit()
    
    def get_stock_klines(self, code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """查询个股K线"""
        query = "SELECT * FROM stock_klines WHERE code = ?"
        params = [code]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date"
        
        with self._connect() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        return df
    
    # ==================== 型态 ====================
    
    def save_patterns(self, patterns: List[Dict]) -> None:
        """保存型态"""
        if not patterns:
            return
        with self._connect() as conn:
            for p in patterns:
                conn.execute("""
                    INSERT INTO patterns (code, pattern_type, confidence, status, start_date, end_date, data_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    p.get("code", ""),
                    p.get("pattern_type", ""),
                    p.get("confidence", 0),
                    p.get("status", ""),
                    p.get("pattern_start_date", ""),
                    p.get("pattern_end_date", ""),
                    json.dumps(p, ensure_ascii=False),
                ))
            conn.commit()
    
    def get_patterns(self, code: str = None, date: str = None) -> List[Dict]:
        """查询型态"""
        query = "SELECT * FROM patterns WHERE 1=1"
        params = []
        if code:
            query += " AND code = ?"
            params.append(code)
        if date:
            query += " AND date(created_at) = date(?)"
            params.append(date)
        query += " ORDER BY confidence DESC"
        
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [json.loads(r[7]) for r in rows if r[7]]
    
    # ==================== 板块排名 ====================
    
    def save_sector_rankings(self, date: str, rankings: List) -> None:
        """保存板块排名"""
        if not rankings:
            return
        with self._connect() as conn:
            for r in rankings:
                d = r.to_dict() if hasattr(r, "to_dict") else r
                conn.execute("""
                    INSERT OR REPLACE INTO sector_rankings 
                    (date, sector_code, sector_name, score, rank, lifecycle, style, return_20d, volume_change)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    d.get("sector_code", ""),
                    d.get("sector_name", ""),
                    d.get("score", 0),
                    d.get("rank", 0),
                    d.get("lifecycle", ""),
                    d.get("style", ""),
                    d.get("return_20d", 0),
                    d.get("volume_change", 0),
                ))
            conn.commit()
    
    def get_sector_rankings(self, date: str) -> pd.DataFrame:
        """查询板块排名"""
        with self._connect() as conn:
            df = pd.read_sql_query(
                "SELECT * FROM sector_rankings WHERE date = ? ORDER BY rank",
                conn, params=[date]
            )
        return df
    
    # ==================== 交通灯信号 ====================
    
    def save_traffic_signals(self, date: str, signals: List[Dict]) -> None:
        """保存交通灯信号"""
        if not signals:
            return
        with self._connect() as conn:
            for s in signals:
                d = s.to_dict() if hasattr(s, "to_dict") else s
                conn.execute("""
                    INSERT INTO traffic_signals
                    (date, code, signal, category, reasons, entry_price, stop_loss, target_1, position_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    d.get("code", ""),
                    d.get("signal", ""),
                    d.get("category", ""),
                    ",".join(d.get("reasons", [])),
                    d.get("entry_price", None),
                    d.get("stop_loss", None),
                    d.get("target_1", None),
                    d.get("position_size", 0),
                ))
            conn.commit()
    
    # ==================== 流水线记录 ====================
    
    def save_pipeline_run(self, run_id: str, date: str, mode: str, pipeline_name: str,
                          success: bool, completed: int, total: int, duration_ms: float,
                          context_keys: List[str]) -> None:
        """保存流水线执行记录（UPSERT）"""
        with self._connect() as conn:
            conn.execute("DELETE FROM pipeline_runs WHERE run_id = ?", (run_id,))
            conn.execute("""
                INSERT INTO pipeline_runs (run_id, date, mode, pipeline_name, success, completed_steps, total_steps, duration_ms, context_keys)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, date, mode, pipeline_name, int(success), completed, total, duration_ms, ",".join(context_keys)))
            conn.commit()
    
    def save_harness_metric(self, run_id: str, name: str, success: bool, 
                            duration_ms: float, inputs: Dict, outputs: Dict, error: str = None) -> None:
        """保存 Harness 指标（UPSERT）"""
        with self._connect() as conn:
            conn.execute("DELETE FROM harness_metrics WHERE run_id = ? AND name = ?", (run_id, name))
            conn.execute("""
                INSERT INTO harness_metrics (run_id, name, success, duration_ms, inputs, outputs, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (run_id, name, int(success), duration_ms, json.dumps(inputs), json.dumps(outputs), error or ""))
            conn.commit()
    
    def get_pipeline_history(self, limit: int = 50) -> pd.DataFrame:
        """查询流水线历史"""
        with self._connect() as conn:
            df = pd.read_sql_query(
                "SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT ?",
                conn, params=[limit]
            )
        return df


if __name__ == "__main__":
    # 快速测试
    engine = PersistenceEngine()
    
    # 测试保存/查询
    test_df = pd.DataFrame({
        "date": ["2025-06-01", "2025-06-02"],
        "open": [10.0, 11.0],
        "high": [11.0, 12.0],
        "low": [9.0, 10.0],
        "close": [10.5, 11.5],
        "volume": [1000000, 2000000],
    })
    engine.save_stock_klines("000001", test_df)
    
    result = engine.get_stock_klines("000001")
    print(f"Saved and retrieved {len(result)} klines for 000001")
    print(result)
