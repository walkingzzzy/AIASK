"""
数据源管理器
提供多数据源故障切换和负载均衡
"""
from typing import Dict, List, Optional, Callable
from enum import Enum
import logging
from datetime import datetime, timedelta
import threading
import time

logger = logging.getLogger(__name__)


# 重连配置
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY_SECONDS = 5


class ConnectionState(Enum):
    """连接状态"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class DataSourceType(Enum):
    """数据源类型"""
    SINA = "sina"
    TENCENT = "tencent"


class DataSourceStatus:
    """数据源状态"""
    def __init__(self, source_type: DataSourceType):
        self.source_type = source_type
        self.is_available = True
        self.last_check_time = datetime.now()
        self.failure_count = 0
        self.success_count = 0
        self.avg_response_time = 0.0
        self.connection_state = ConnectionState.DISCONNECTED
        self.reconnect_attempts = 0
        self.last_error: Optional[str] = None
        self.initialized = False


class DataSourceManager:
    """
    数据源管理器

    功能：
    1. 多数据源管理
    2. 自动故障切换
    3. 健康检查
    4. 负载均衡
    5. 断线自动重连
    """

    def __init__(self, check_interval: int = 60, auto_reconnect: bool = True):
        """
        初始化数据源管理器

        Args:
            check_interval: 健康检查间隔（秒）
            auto_reconnect: 是否自动重连
        """
        self.sources: Dict[DataSourceType, any] = {}
        self.status: Dict[DataSourceType, DataSourceStatus] = {}
        self.check_interval = check_interval
        self.primary_source = DataSourceType.SINA
        self.fallback_sources = [DataSourceType.TENCENT]
        self.auto_reconnect = auto_reconnect
        self._lock = threading.Lock()
        self._reconnect_thread: Optional[threading.Thread] = None
        self._stop_reconnect = False

        self._initialize_sources()

    def _initialize_sources(self):
        """初始化数据源"""
        self._initialize_source(DataSourceType.SINA)
        self._initialize_source(DataSourceType.TENCENT)

    def _initialize_source(self, source_type: DataSourceType) -> bool:
        """
        初始化单个数据源
        
        Args:
            source_type: 数据源类型
            
        Returns:
            是否初始化成功
        """
        with self._lock:
            # 创建状态对象（如果不存在）
            if source_type not in self.status:
                self.status[source_type] = DataSourceStatus(source_type)
            
            status = self.status[source_type]
            status.connection_state = ConnectionState.CONNECTING
            
            try:
                if source_type == DataSourceType.SINA:
                    from .sina_realtime import SinaRealtimeAdapter
                    self.sources[source_type] = SinaRealtimeAdapter()
                    logger.info("新浪数据源初始化成功")
                elif source_type == DataSourceType.TENCENT:
                    from .tencent_realtime import TencentRealtimeAdapter
                    self.sources[source_type] = TencentRealtimeAdapter()
                    logger.info("腾讯数据源初始化成功")
                
                status.connection_state = ConnectionState.CONNECTED
                status.initialized = True
                status.is_available = True
                status.failure_count = 0
                status.reconnect_attempts = 0
                status.last_error = None
                return True
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"{source_type.value} 数据源初始化失败: {error_msg}")
                status.connection_state = ConnectionState.FAILED
                status.last_error = error_msg
                status.is_available = False
                return False

    def reconnect(self, source_type: Optional[DataSourceType] = None) -> Dict[str, bool]:
        """
        重连数据源
        
        Args:
            source_type: 指定重连的数据源类型，None表示重连所有失败的数据源
            
        Returns:
            各数据源重连结果 {source_name: success}
        """
        results = {}
        
        sources_to_reconnect = [source_type] if source_type else list(DataSourceType)
        
        for src_type in sources_to_reconnect:
            status = self.status.get(src_type)
            
            # 只重连失败或不可用的数据源
            if status and (not status.is_available or status.connection_state == ConnectionState.FAILED):
                status.connection_state = ConnectionState.RECONNECTING
                status.reconnect_attempts += 1
                
                logger.info(f"正在重连 {src_type.value} 数据源 (第 {status.reconnect_attempts} 次尝试)")
                
                success = self._initialize_source(src_type)
                results[src_type.value] = success
                
                if success:
                    logger.info(f"{src_type.value} 数据源重连成功")
                else:
                    logger.warning(f"{src_type.value} 数据源重连失败")
        
        return results

    def _auto_reconnect_loop(self):
        """自动重连循环（在后台线程运行）"""
        while not self._stop_reconnect:
            time.sleep(RECONNECT_DELAY_SECONDS)
            
            for source_type, status in self.status.items():
                if self._stop_reconnect:
                    break
                    
                # 检查是否需要重连
                if not status.is_available and status.reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                    self.reconnect(source_type)
                elif status.reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
                    if status.connection_state != ConnectionState.FAILED:
                        status.connection_state = ConnectionState.FAILED
                        logger.error(f"{source_type.value} 数据源重连次数已达上限，停止重连")

    def start_auto_reconnect(self):
        """启动自动重连"""
        if self.auto_reconnect and self._reconnect_thread is None:
            self._stop_reconnect = False
            self._reconnect_thread = threading.Thread(target=self._auto_reconnect_loop, daemon=True)
            self._reconnect_thread.start()
            logger.info("自动重连服务已启动")

    def stop_auto_reconnect(self):
        """停止自动重连"""
        self._stop_reconnect = True
        if self._reconnect_thread:
            self._reconnect_thread.join(timeout=2)
            self._reconnect_thread = None
            logger.info("自动重连服务已停止")

    def get_status(self) -> Dict[str, Dict]:
        """
        获取各数据源连接状态
        
        Returns:
            各数据源的详细状态信息
        """
        result = {}
        for source_type, status in self.status.items():
            result[source_type.value] = {
                "connection_state": status.connection_state.value,
                "is_available": status.is_available,
                "initialized": status.initialized,
                "failure_count": status.failure_count,
                "success_count": status.success_count,
                "reconnect_attempts": status.reconnect_attempts,
                "last_error": status.last_error,
                "last_check_time": status.last_check_time.isoformat(),
                "avg_response_time_ms": round(status.avg_response_time * 1000, 2)
            }
        return result

    def get_overall_status(self) -> Dict[str, any]:
        """
        获取整体连接状态摘要
        
        Returns:
            整体状态信息
        """
        sources_status = self.get_status()
        available_count = sum(1 for s in self.status.values() if s.is_available)
        total_count = len(self.status)
        
        if available_count == total_count:
            overall_state = "healthy"
            message = "所有数据源正常"
        elif available_count > 0:
            overall_state = "degraded"
            message = f"{available_count}/{total_count} 数据源可用"
        else:
            overall_state = "unavailable"
            message = "所有数据源不可用"
        
        return {
            "overall_state": overall_state,
            "message": message,
            "available_sources": available_count,
            "total_sources": total_count,
            "primary_source": self.primary_source.value,
            "primary_available": self.status.get(self.primary_source, DataSourceStatus(self.primary_source)).is_available,
            "sources": sources_status,
            "auto_reconnect_enabled": self.auto_reconnect
        }

    def get_realtime_quote(self, stock_code: str) -> Optional[Dict]:
        """
        获取实时行情（自动故障切换）

        Args:
            stock_code: 股票代码

        Returns:
            行情数据
        """
        # 尝试主数据源
        result = self._try_get_quote(self.primary_source, stock_code)
        if result:
            return result

        # 尝试备用数据源
        for source_type in self.fallback_sources:
            result = self._try_get_quote(source_type, stock_code)
            if result:
                logger.warning(f"主数据源失败，使用备用数据源: {source_type.value}")
                return result

        logger.error(f"所有数据源均失败: {stock_code}")
        return None

    def get_batch_quotes(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """
        批量获取实时行情

        Args:
            stock_codes: 股票代码列表

        Returns:
            {code: quote_data}
        """
        # 尝试主数据源
        result = self._try_get_batch_quotes(self.primary_source, stock_codes)
        if result:
            return result

        # 尝试备用数据源
        for source_type in self.fallback_sources:
            result = self._try_get_batch_quotes(source_type, stock_codes)
            if result:
                logger.warning(f"主数据源失败，使用备用数据源: {source_type.value}")
                return result

        logger.error("所有数据源均失败")
        return {}

    def _try_get_quote(self, source_type: DataSourceType, stock_code: str) -> Optional[Dict]:
        """尝试从指定数据源获取行情"""
        if source_type not in self.sources:
            return None

        status = self.status.get(source_type)
        if status and not status.is_available:
            # 检查是否需要重试
            if datetime.now() - status.last_check_time < timedelta(seconds=self.check_interval):
                return None

        try:
            start_time = datetime.now()
            source = self.sources[source_type]
            result = source.get_realtime_quote(stock_code)

            if result:
                # 更新状态
                if status:
                    status.success_count += 1
                    status.is_available = True
                    status.last_check_time = datetime.now()
                    response_time = (datetime.now() - start_time).total_seconds()
                    status.avg_response_time = (
                        status.avg_response_time * 0.9 + response_time * 0.1
                    )
                return result
            else:
                self._mark_failure(source_type)
                return None

        except Exception as e:
            logger.error(f"数据源 {source_type.value} 请求失败: {e}")
            self._mark_failure(source_type)
            return None

    def _try_get_batch_quotes(
        self,
        source_type: DataSourceType,
        stock_codes: List[str]
    ) -> Optional[Dict[str, Dict]]:
        """尝试从指定数据源批量获取行情"""
        if source_type not in self.sources:
            return None

        status = self.status.get(source_type)
        if status and not status.is_available:
            if datetime.now() - status.last_check_time < timedelta(seconds=self.check_interval):
                return None

        try:
            source = self.sources[source_type]
            result = source.get_batch_quotes(stock_codes)

            if result:
                if status:
                    status.success_count += 1
                    status.is_available = True
                    status.last_check_time = datetime.now()
                return result
            else:
                self._mark_failure(source_type)
                return None

        except Exception as e:
            logger.error(f"数据源 {source_type.value} 批量请求失败: {e}")
            self._mark_failure(source_type)
            return None

    def _mark_failure(self, source_type: DataSourceType):
        """标记数据源失败"""
        status = self.status.get(source_type)
        if status:
            status.failure_count += 1
            status.last_check_time = datetime.now()

            # 连续失败3次则标记为不可用
            if status.failure_count >= 3:
                status.is_available = False
                logger.warning(f"数据源 {source_type.value} 已标记为不可用")

    def health_check(self):
        """健康检查"""
        logger.info("开始数据源健康检查...")

        for source_type, source in self.sources.items():
            try:
                is_available = source.is_available()
                status = self.status.get(source_type)

                if status:
                    if is_available:
                        status.is_available = True
                        status.failure_count = 0
                        logger.info(f"数据源 {source_type.value} 健康")
                    else:
                        status.is_available = False
                        logger.warning(f"数据源 {source_type.value} 不可用")

                    status.last_check_time = datetime.now()

            except Exception as e:
                logger.error(f"健康检查失败 {source_type.value}: {e}")

    def get_status_report(self) -> Dict:
        """获取状态报告"""
        report = {
            'primary_source': self.primary_source.value,
            'sources': {}
        }

        for source_type, status in self.status.items():
            report['sources'][source_type.value] = {
                'is_available': status.is_available,
                'success_count': status.success_count,
                'failure_count': status.failure_count,
                'avg_response_time': status.avg_response_time,
                'last_check_time': status.last_check_time.isoformat()
            }

        return report

    def switch_primary_source(self, source_type: DataSourceType):
        """切换主数据源"""
        if source_type in self.sources:
            self.primary_source = source_type
            logger.info(f"主数据源已切换为: {source_type.value}")
        else:
            logger.error(f"数据源不存在: {source_type.value}")
