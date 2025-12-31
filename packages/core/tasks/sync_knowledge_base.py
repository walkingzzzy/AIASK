"""
知识库同步任务
定时将股票数据同步到向量知识库
"""
import logging
import time
from typing import List, Optional, Dict
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


class KnowledgeBaseSyncTask:
    """
    知识库同步任务
    
    功能：
    1. 定时同步热门股票数据
    2. 增量更新变化的数据
    3. 清理过期文档
    """
    
    HOT_STOCKS = [
        "600519", "000858", "601318", "600036", "300750",
        "002594", "000651", "000333", "600276", "603259",
        "601012", "600887", "000568", "600809", "002475",
        "002415", "000002", "600030", "601166", "601288",
    ]
    
    def __init__(self):
        self._service = None
        self._stock_db = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    @property
    def service(self):
        if self._service is None:
            from ..services.stock_data_service import get_stock_service
            self._service = get_stock_service()
        return self._service
    
    @property
    def stock_db(self):
        if self._stock_db is None:
            from ..nlp_query.stock_database import get_stock_database
            self._stock_db = get_stock_database()
        return self._stock_db

    def sync_hot_stocks(self) -> Dict:
        """同步热门股票"""
        logger.info("开始同步热门股票到知识库...")
        
        stock_names = {}
        for code in self.HOT_STOCKS:
            name = self.stock_db.get_name_by_code(code)
            if name:
                stock_names[code] = name
        
        result = self.service.sync_knowledge_base(self.HOT_STOCKS, stock_names)
        
        logger.info(f"热门股票同步完成: {result}")
        return result
    
    def sync_all_stocks(self, batch_size: int = 100) -> Dict:
        """同步全部A股（分批处理）"""
        logger.info("开始同步全部A股到知识库...")
        
        all_stocks = self.stock_db.get_all_stocks()
        stock_codes = list(all_stocks.keys())
        
        total_success = 0
        total_failed = 0
        
        for i in range(0, len(stock_codes), batch_size):
            batch = stock_codes[i:i+batch_size]
            batch_names = {code: all_stocks[code] for code in batch}
            
            result = self.service.sync_knowledge_base(batch, batch_names)
            total_success += result.get("success", 0)
            total_failed += result.get("failed", 0)
            
            logger.info(f"已处理 {i + len(batch)}/{len(stock_codes)} 只股票")
            time.sleep(1)
        
        return {
            "total": len(stock_codes),
            "success": total_success,
            "failed": total_failed
        }
    
    def cleanup_expired(self, days: int = 30) -> int:
        """清理过期文档"""
        logger.info(f"清理{days}天前的过期文档...")
        deleted = self.service.indexer.cleanup_old_documents(days)
        logger.info(f"清理完成，删除{deleted}条文档")
        return deleted
    
    def start_scheduler(self, interval_minutes: int = 30):
        """启动定时任务"""
        if self._running:
            logger.warning("同步任务已在运行")
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._run_scheduler, 
            args=(interval_minutes,),
            daemon=True
        )
        self._thread.start()
        logger.info(f"知识库同步任务已启动，间隔{interval_minutes}分钟")
    
    def stop_scheduler(self):
        """停止定时任务"""
        self._running = False
        logger.info("知识库同步任务已停止")
    
    def _run_scheduler(self, interval_minutes: int):
        """运行调度器"""
        interval_seconds = interval_minutes * 60
        last_sync = 0
        
        while self._running:
            current_time = time.time()
            if current_time - last_sync >= interval_seconds:
                try:
                    self.sync_hot_stocks()
                    last_sync = current_time
                except Exception as e:
                    logger.error(f"同步任务执行失败: {e}")
            time.sleep(60)


_sync_task: Optional[KnowledgeBaseSyncTask] = None


def get_sync_task() -> KnowledgeBaseSyncTask:
    """获取同步任务单例"""
    global _sync_task
    if _sync_task is None:
        _sync_task = KnowledgeBaseSyncTask()
    return _sync_task


def start_knowledge_sync(interval_minutes: int = 30):
    """启动知识库同步"""
    task = get_sync_task()
    task.start_scheduler(interval_minutes)


def sync_now() -> Dict:
    """立即执行一次同步"""
    task = get_sync_task()
    return task.sync_hot_stocks()
