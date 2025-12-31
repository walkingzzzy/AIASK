"""
缓存管理器
实现内存缓存 + SQLite持久化缓存
"""
from typing import Optional, Any, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
import sqlite3
import hashlib
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    created_at: datetime
    expires_at: datetime
    hit_count: int = 0


class MemoryCache:
    """内存缓存"""
    
    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            
            # 检查是否过期
            if datetime.now() > entry.expires_at:
                del self._cache[key]
                return None
            
            entry.hit_count += 1
            return entry.value
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """设置缓存"""
        with self._lock:
            # 如果超过最大容量，清理过期和最少使用的
            if len(self._cache) >= self._max_size:
                self._evict()
            
            now = datetime.now()
            self._cache[key] = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds)
            )
    
    def delete(self, key: str):
        """删除缓存"""
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    def _evict(self):
        """清理缓存"""
        now = datetime.now()
        # 先清理过期的
        expired_keys = [
            k for k, v in self._cache.items() 
            if now > v.expires_at
        ]
        for key in expired_keys:
            del self._cache[key]
        
        # 如果还是超过容量，清理最少使用的
        if len(self._cache) >= self._max_size:
            sorted_entries = sorted(
                self._cache.items(),
                key=lambda x: x[1].hit_count
            )
            # 删除前20%
            to_delete = len(sorted_entries) // 5
            for key, _ in sorted_entries[:to_delete]:
                del self._cache[key]
    
    def stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "total_hits": sum(e.hit_count for e in self._cache.values())
            }


class SQLiteCache:
    """SQLite持久化缓存"""
    
    def __init__(self, db_path: str = "data/cache.db"):
        self._db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                created_at TEXT,
                expires_at TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at ON cache(expires_at)
        """)
        conn.commit()
        conn.close()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return None
        
        value, expires_at = row
        if datetime.fromisoformat(expires_at) < datetime.now():
            self.delete(key)
            return None
        
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600):
        """设置缓存"""
        now = datetime.now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        
        if isinstance(value, (dict, list)):
            value_str = json.dumps(value, ensure_ascii=False, default=str)
        else:
            value_str = json.dumps(value, default=str)
        
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO cache (key, value, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (key, value_str, now.isoformat(), expires_at.isoformat()))
        conn.commit()
        conn.close()
    
    def delete(self, key: str):
        """删除缓存"""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cache WHERE key = ?", (key,))
        conn.commit()
        conn.close()
    
    def clear(self):
        """清空缓存"""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cache")
        conn.commit()
        conn.close()
    
    def cleanup_expired(self):
        """清理过期缓存"""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM cache WHERE expires_at < ?",
            (datetime.now().isoformat(),)
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted


class CacheManager:
    """
    缓存管理器
    
    两级缓存架构：
    1. L1: 内存缓存 - 快速访问，短TTL
    2. L2: SQLite缓存 - 持久化，长TTL
    """
    
    # 缓存TTL配置（秒）
    TTL_REALTIME = 30        # 实时行情 30秒
    TTL_DAILY = 3600         # 日线数据 1小时
    TTL_FINANCIAL = 86400    # 财务数据 24小时
    TTL_STOCK_LIST = 86400   # 股票列表 24小时
    
    def __init__(self, db_path: str = "data/cache.db"):
        self._memory_cache = MemoryCache(max_size=1000)
        self._sqlite_cache = SQLiteCache(db_path)
    
    @staticmethod
    def _make_key(prefix: str, *args) -> str:
        """生成缓存key"""
        key_str = f"{prefix}:" + ":".join(str(a) for a in args)
        return hashlib.md5(key_str.encode()).hexdigest()[:16] + f"_{prefix}"
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存（先L1后L2）
        """
        # 先查内存缓存
        value = self._memory_cache.get(key)
        if value is not None:
            return value
        
        # 再查SQLite缓存
        value = self._sqlite_cache.get(key)
        if value is not None:
            # 回填到内存缓存
            self._memory_cache.set(key, value, ttl_seconds=300)
            return value
        
        return None
    
    def set(self, key: str, value: Any, 
            memory_ttl: int = 300, sqlite_ttl: int = 3600):
        """
        设置缓存（同时写入L1和L2）
        """
        self._memory_cache.set(key, value, ttl_seconds=memory_ttl)
        self._sqlite_cache.set(key, value, ttl_seconds=sqlite_ttl)
    
    def delete(self, key: str):
        """删除缓存"""
        self._memory_cache.delete(key)
        self._sqlite_cache.delete(key)
    
    def clear_all(self):
        """清空所有缓存"""
        self._memory_cache.clear()
        self._sqlite_cache.clear()
    
    def cleanup(self):
        """清理过期缓存"""
        return self._sqlite_cache.cleanup_expired()
    
    def stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "memory": self._memory_cache.stats(),
            "sqlite": {
                "db_path": self._sqlite_cache._db_path
            }
        }
    
    # 便捷方法
    def cache_realtime_quote(self, stock_code: str, data: Any):
        """缓存实时行情"""
        key = self._make_key("quote", stock_code)
        self.set(key, data, memory_ttl=self.TTL_REALTIME, sqlite_ttl=60)
    
    def get_realtime_quote(self, stock_code: str) -> Optional[Any]:
        """获取缓存的实时行情"""
        key = self._make_key("quote", stock_code)
        return self.get(key)
    
    def cache_daily_bars(self, stock_code: str, start: str, end: str, data: Any):
        """缓存日线数据"""
        key = self._make_key("daily", stock_code, start, end)
        self.set(key, data, memory_ttl=self.TTL_DAILY, sqlite_ttl=self.TTL_DAILY * 24)
    
    def get_daily_bars(self, stock_code: str, start: str, end: str) -> Optional[Any]:
        """获取缓存的日线数据"""
        key = self._make_key("daily", stock_code, start, end)
        return self.get(key)
    
    def cache_financial(self, stock_code: str, data: Any):
        """缓存财务数据"""
        key = self._make_key("financial", stock_code)
        self.set(key, data, memory_ttl=self.TTL_FINANCIAL, sqlite_ttl=self.TTL_FINANCIAL * 7)
    
    def get_financial(self, stock_code: str) -> Optional[Any]:
        """获取缓存的财务数据"""
        key = self._make_key("financial", stock_code)
        return self.get(key)


# 全局单例
_cache_instance: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    """获取缓存管理器单例"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheManager()
    return _cache_instance


# 别名，保持向后兼容
def get_cache_manager() -> CacheManager:
    """获取缓存管理器单例（get_cache的别名）"""
    return get_cache()
