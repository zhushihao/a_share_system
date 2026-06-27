"""
多级缓存系统 v5.0 — 完整实现 L1/L2/L3

L1: 内存缓存（Python dict，同进程内，最快）
L2: 本地文件缓存（pickle，跨进程，重启保留）
L3: SQLite 持久化缓存（跨会话持久化，结构化查询，容量更大）

TTL策略：
- 个股K线：1天
- 板块数据：1天
- 型态识别：1天
- 实时价格：5分钟
"""

import os
import pickle
import time
import hashlib
import threading
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple


class CacheEntry:
    """缓存条目"""
    def __init__(self, value: Any, ttl_seconds: int = 3600):
        self.value = value
        self.created_at = time.time()
        self.ttl_seconds = ttl_seconds
        self.access_count = 0
        self.last_access = self.created_at
    
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds
    
    def touch(self):
        self.access_count += 1
        self.last_access = time.time()


class MultiLevelCache:
    """
    多级缓存系统
    
    使用方式：
    cache = MultiLevelCache()
    cache.set("stock:000001", df, ttl=86400)
    df = cache.get("stock:000001")
    """
    
    def __init__(
        self,
        cache_dir: str = None,
        enable_l1: bool = True,
        enable_l2: bool = True,
        enable_l3: bool = True,
    ):
        if cache_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cache_dir = os.path.join(base, "data", "cache")
        
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        self._l1: Dict[str, CacheEntry] = {}  # 内存缓存
        self._l1_lock = threading.Lock()
        
        self._enable_l1 = enable_l1
        self._enable_l2 = enable_l2
        self._enable_l3 = enable_l3
        
        # L3: SQLite 持久化缓存
        self._l3_db_path = os.path.join(cache_dir, "cache_l3.db")
        self._l3_conn: Optional[sqlite3.Connection] = None
        self._l3_lock = threading.Lock()
        if self._enable_l3:
            self._init_l3_db()
        
        # 统计
        self._hits = {"l1": 0, "l2": 0, "l3": 0, "miss": 0}
    
    # ───────────────────────────────────────────────
    # L3: SQLite 初始化
    # ───────────────────────────────────────────────
    
    def _init_l3_db(self) -> None:
        """初始化 L3 SQLite 数据库"""
        conn = sqlite3.connect(self._l3_db_path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL,
                created_at REAL NOT NULL,
                ttl_seconds INTEGER NOT NULL,
                access_count INTEGER DEFAULT 0,
                last_access REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_created ON cache_entries(created_at)
        """)
        conn.commit()
        conn.close()
    
    def _get_l3_conn(self) -> sqlite3.Connection:
        """获取 L3 数据库连接（每个线程独立连接）"""
        # 使用线程本地存储，避免多线程冲突
        if not hasattr(self, '_thread_local'):
            self._thread_local = threading.local()
        if not hasattr(self._thread_local, 'conn') or self._thread_local.conn is None:
            self._thread_local.conn = sqlite3.connect(self._l3_db_path, check_same_thread=False)
        return self._thread_local.conn
    
    def _close_l3_conn(self) -> None:
        """关闭当前线程的 L3 连接"""
        if hasattr(self, '_thread_local') and hasattr(self._thread_local, 'conn'):
            if self._thread_local.conn is not None:
                self._thread_local.conn.close()
                self._thread_local.conn = None
    
    # ───────────────────────────────────────────────
    # L2: 文件缓存辅助
    # ───────────────────────────────────────────────
    
    def _key_to_filename(self, key: str) -> str:
        """将key转换为安全的文件名"""
        hash_name = hashlib.md5(key.encode()).hexdigest()[:16]
        return os.path.join(self.cache_dir, f"{hash_name}.pkl")
    
    # ───────────────────────────────────────────────
    # 核心操作
    # ───────────────────────────────────────────────
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值（按 L1 → L2 → L3 顺序）"""
        # L1: 内存缓存
        if self._enable_l1:
            with self._l1_lock:
                entry = self._l1.get(key)
                if entry and not entry.is_expired():
                    entry.touch()
                    self._hits["l1"] += 1
                    return entry.value
        
        # L2: 文件缓存
        if self._enable_l2:
            filepath = self._key_to_filename(key)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "rb") as f:
                        entry = pickle.load(f)
                    if isinstance(entry, CacheEntry) and not entry.is_expired():
                        entry.touch()
                        self._hits["l2"] += 1
                        # 回填 L1
                        if self._enable_l1:
                            with self._l1_lock:
                                self._l1[key] = entry
                        return entry.value
                    else:
                        # 过期，删除
                        os.remove(filepath)
                except Exception:
                    pass
        
        # L3: SQLite 持久化缓存
        if self._enable_l3:
            try:
                with self._l3_lock:
                    conn = self._get_l3_conn()
                    cursor = conn.execute(
                        "SELECT value, created_at, ttl_seconds, access_count FROM cache_entries WHERE key = ?",
                        (key,),
                    )
                    row = cursor.fetchone()
                    if row:
                        value_blob, created_at, ttl_seconds, access_count = row
                        if time.time() - created_at <= ttl_seconds:
                            # 未过期，反序列化
                            value = pickle.loads(value_blob)
                            # 更新访问统计
                            conn.execute(
                                "UPDATE cache_entries SET access_count = ?, last_access = ? WHERE key = ?",
                                (access_count + 1, time.time(), key),
                            )
                            conn.commit()
                            self._hits["l3"] += 1
                            # 回填 L1 和 L2
                            entry = CacheEntry(value, ttl_seconds)
                            entry.access_count = access_count + 1
                            entry.last_access = time.time()
                            if self._enable_l1:
                                with self._l1_lock:
                                    self._l1[key] = entry
                            if self._enable_l2:
                                filepath = self._key_to_filename(key)
                                try:
                                    with open(filepath, "wb") as f:
                                        pickle.dump(entry, f)
                                except Exception:
                                    pass
                            return value
                        else:
                            # 过期，删除
                            conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                            conn.commit()
            except Exception:
                pass
        
        self._hits["miss"] += 1
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """设置缓存值"""
        entry = CacheEntry(value, ttl_seconds)
        
        # L1
        if self._enable_l1:
            with self._l1_lock:
                self._l1[key] = entry
        
        # L2
        if self._enable_l2:
            filepath = self._key_to_filename(key)
            try:
                with open(filepath, "wb") as f:
                    pickle.dump(entry, f)
            except Exception:
                pass
        
        # L3: SQLite
        if self._enable_l3:
            try:
                with self._l3_lock:
                    conn = self._get_l3_conn()
                    value_blob = pickle.dumps(value)
                    conn.execute(
                        """
                        INSERT INTO cache_entries (key, value, created_at, ttl_seconds, access_count, last_access)
                        VALUES (?, ?, ?, ?, 0, ?)
                        ON CONFLICT(key) DO UPDATE SET
                            value=excluded.value,
                            created_at=excluded.created_at,
                            ttl_seconds=excluded.ttl_seconds,
                            access_count=0,
                            last_access=excluded.last_access
                        """,
                        (key, value_blob, entry.created_at, ttl_seconds, entry.created_at),
                    )
                    conn.commit()
            except Exception:
                pass
    
    def delete(self, key: str) -> None:
        """删除缓存"""
        # L1
        with self._l1_lock:
            self._l1.pop(key, None)
        
        # L2
        filepath = self._key_to_filename(key)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        # L3
        if self._enable_l3:
            try:
                with self._l3_lock:
                    conn = self._get_l3_conn()
                    conn.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                    conn.commit()
            except Exception:
                pass
    
    def clear(self) -> None:
        """清空所有缓存"""
        # L1
        with self._l1_lock:
            self._l1.clear()
        
        # L2
        for f in os.listdir(self.cache_dir):
            if f.endswith(".pkl"):
                os.remove(os.path.join(self.cache_dir, f))
        
        # L3
        if self._enable_l3:
            try:
                with self._l3_lock:
                    conn = self._get_l3_conn()
                    conn.execute("DELETE FROM cache_entries")
                    conn.commit()
            except Exception:
                pass
    
    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total = sum(self._hits.values())
        if total == 0:
            return {"hits": self._hits, "hit_rate": 0, "l1_size": len(self._l1), "l3_count": 0}
        
        hit_rate = (self._hits["l1"] + self._hits["l2"] + self._hits["l3"]) / total
        
        l3_count = 0
        if self._enable_l3:
            try:
                with self._l3_lock:
                    conn = self._get_l3_conn()
                    cursor = conn.execute("SELECT COUNT(*) FROM cache_entries")
                    row = cursor.fetchone()
                    l3_count = row[0] if row else 0
            except Exception:
                pass
        
        return {
            "hits": self._hits,
            "hit_rate": round(hit_rate, 4),
            "l1_size": len(self._l1),
            "l3_count": l3_count,
            "total_requests": total,
        }
    
    def clean_expired(self) -> int:
        """清理过期缓存，返回清理数量"""
        cleaned = 0
        
        # L1
        with self._l1_lock:
            expired = [k for k, e in self._l1.items() if e.is_expired()]
            for k in expired:
                del self._l1[k]
                cleaned += 1
        
        # L2
        for f in os.listdir(self.cache_dir):
            if f.endswith(".pkl"):
                filepath = os.path.join(self.cache_dir, f)
                try:
                    with open(filepath, "rb") as fh:
                        entry = pickle.load(fh)
                    if entry.is_expired():
                        os.remove(filepath)
                        cleaned += 1
                except Exception:
                    pass
        
        # L3
        if self._enable_l3:
            try:
                with self._l3_lock:
                    conn = self._get_l3_conn()
                    now = time.time()
                    cursor = conn.execute(
                        "DELETE FROM cache_entries WHERE ? - created_at > ttl_seconds",
                        (now,),
                    )
                    conn.commit()
                    cleaned += cursor.rowcount
            except Exception:
                pass
        
        return cleaned


# 预设的TTL配置
TTL_PRESETS = {
    "stock_kline": 86400,      # 1天
    "sector_data": 86400,      # 1天
    "pattern": 86400,          # 1天
    "realtime_price": 300,     # 5分钟
    "stock_info": 604800,      # 7天
    "index_kline": 86400,      # 1天
}


if __name__ == "__main__":
    # 快速测试
    import tempfile
    import shutil
    
    test_dir = tempfile.mkdtemp(prefix="quant_cache_test_")
    print(f"=== MultiLevelCache Test (dir={test_dir}) ===")
    
    try:
        cache = MultiLevelCache(cache_dir=test_dir, enable_l1=True, enable_l2=True, enable_l3=True)
        
        # 1. Happy path: set/get
        print("\n[1] Basic set/get")
        cache.set("test:1", {"value": 42}, ttl_seconds=60)
        result = cache.get("test:1")
        assert result == {"value": 42}, f"Expected {{'value': 42}}, got {result}"
        print("  [PASS] L1 cache hit")
        
        # 2. L3 persistence: 清除 L1/L2，从 L3 恢复
        print("\n[2] L3 persistence")
        cache._l1.clear()  # 清空 L1
        # 删除 L2 文件
        for f in os.listdir(test_dir):
            if f.endswith(".pkl"):
                os.remove(os.path.join(test_dir, f))
        result = cache.get("test:1")
        assert result == {"value": 42}, f"Expected {{'value': 42}}, got {result}"
        print("  [PASS] L3 recovery after L1/L2 cleared")
        
        # 3. TTL expiration
        print("\n[3] TTL expiration")
        cache.set("test:2", [1, 2, 3], ttl_seconds=1)
        time.sleep(1.1)
        result = cache.get("test:2")
        assert result is None, f"Expected None, got {result}"
        print("  [PASS] Expired entry returns None")
        
        # 4. Edge case: empty key
        print("\n[4] Edge cases")
        cache.set("", "empty_key_value", ttl_seconds=60)
        result = cache.get("")
        assert result == "empty_key_value"
        print("  [PASS] Empty key handled")
        
        # 5. Large value
        print("\n[5] Large value")
        large_data = {"items": list(range(10000))}
        cache.set("large", large_data, ttl_seconds=60)
        result = cache.get("large")
        assert result == large_data
        print("  [PASS] Large value round-trip")
        
        # 6. Stats
        print("\n[6] Stats")
        stats = cache.get_stats()
        assert "hits" in stats
        assert "hit_rate" in stats
        assert "l1_size" in stats
        assert "l3_count" in stats
        print(f"  [PASS] Stats: {stats}")
        
        # 7. Clean expired
        print("\n[7] Clean expired")
        cache.set("expired_a", "a", ttl_seconds=1)
        cache.set("expired_b", "b", ttl_seconds=1)
        time.sleep(1.1)
        cache.set("fresh", "c", ttl_seconds=60)
        cleaned = cache.clean_expired()
        assert cleaned >= 2, f"Expected >= 2 cleaned, got {cleaned}"
        assert cache.get("fresh") == "c"
        print(f"  [PASS] Cleaned {cleaned} expired entries, fresh entry preserved")
        
        # 8. Delete
        print("\n[8] Delete")
        cache.set("to_delete", "x", ttl_seconds=60)
        assert cache.get("to_delete") == "x"
        cache.delete("to_delete")
        assert cache.get("to_delete") is None
        print("  [PASS] Delete removes from all layers")
        
        # 9. Clear all
        print("\n[9] Clear all")
        cache.set("clear_a", "a", ttl_seconds=60)
        cache.set("clear_b", "b", ttl_seconds=60)
        cache.clear()
        assert cache.get("clear_a") is None
        assert cache.get("clear_b") is None
        assert cache.get_stats()["l1_size"] == 0
        print("  [PASS] Clear removes all entries")
        
        print("\n=== All Cache Tests PASSED ===")
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
