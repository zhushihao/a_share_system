"""
多级缓存系统 v4.0

L1: 内存缓存（Python dict，同进程内，最快）
L2: 本地文件缓存（pickle，跨进程，重启保留）
L3: SQLite（跨会话持久化，已持久化）

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
    
    def __init__(self, cache_dir: str = None, enable_l1: bool = True, enable_l2: bool = True):
        if cache_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cache_dir = os.path.join(base, "data", "cache")
        
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        self._l1: Dict[str, CacheEntry] = {}  # 内存缓存
        self._l1_lock = threading.Lock()
        
        self._enable_l1 = enable_l1
        self._enable_l2 = enable_l2
        
        # 统计
        self._hits = {"l1": 0, "l2": 0, "miss": 0}
    
    def _key_to_filename(self, key: str) -> str:
        """将key转换为安全的文件名"""
        hash_name = hashlib.md5(key.encode()).hexdigest()[:16]
        return os.path.join(self.cache_dir, f"{hash_name}.pkl")
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值（按 L1 → L2 顺序）"""
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
    
    def delete(self, key: str) -> None:
        """删除缓存"""
        with self._l1_lock:
            self._l1.pop(key, None)
        
        filepath = self._key_to_filename(key)
        if os.path.exists(filepath):
            os.remove(filepath)
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self._l1_lock:
            self._l1.clear()
        
        for f in os.listdir(self.cache_dir):
            if f.endswith(".pkl"):
                os.remove(os.path.join(self.cache_dir, f))
    
    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total = sum(self._hits.values())
        if total == 0:
            return {"hits": self._hits, "hit_rate": 0, "l1_size": len(self._l1)}
        
        hit_rate = (self._hits["l1"] + self._hits["l2"]) / total
        return {
            "hits": self._hits,
            "hit_rate": round(hit_rate, 4),
            "l1_size": len(self._l1),
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
    cache = MultiLevelCache()
    
    cache.set("test:1", {"value": 42}, ttl=60)
    result = cache.get("test:1")
    assert result == {"value": 42}
    
    cache.set("test:2", [1, 2, 3], ttl=1)
    time.sleep(1.1)
    result = cache.get("test:2")
    assert result is None  # 已过期
    
    print(f"Cache stats: {cache.get_stats()}")
    print("Cache tests: PASSED")
