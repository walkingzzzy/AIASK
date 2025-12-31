"""
竞价时段实时监控器
提供竞价时段（9:15-9:25集合竞价，14:57-15:00尾盘竞价）的实时监控功能
"""
import logging
import threading
import time
from datetime import datetime, time as dt_time
from typing import Any, Callable, Dict, List, Optional, Set

from .auction_analyzer import CallAuctionAnalyzer, AuctionStock
from .alert_rules import (
    AlertRule,HighOpenRule,
    LowOpenRule,
    VolumeAnomalyRule,
    LimitUpExpectedRule,
    LimitDownExpectedRule,
    BigOrderRule,
    PriceVolatilityRule,
)
from .models import Alert

logger = logging.getLogger(__name__)


class AuctionMonitor:
    """
    竞价时段实时监控器
    支持功能：
    - 自选股监控或全市场监控
    - 实时竞价数据获取
    - 多种预警规则检测
    - 预警回调通知
    - 后台线程监控
    Attributes:
        watch_list: 监控股票代码集合
        alert_callback: 预警回调函数
        refresh_interval: 刷新间隔（秒）
        is_running: 监控是否运行中"""
    
    #竞价时段定义
    MORNING_AUCTION_START = dt_time(9, 15)
    MORNING_AUCTION_END = dt_time(9, 25)
    AFTERNOON_AUCTION_START = dt_time(14, 57)
    AFTERNOON_AUCTION_END = dt_time(15, 0)
    
    def __init__(
        self,
        watch_list: Optional[List[str]] = None,
        alert_callback: Optional[Callable[[Alert], None]] = None,
        refresh_interval: int = 3
    ):
        """
        初始化监控器
        
        Args:
            watch_list: 自选股代码列表，None则监控全市场
            alert_callback: 预警回调函数，接收Alert对象
            refresh_interval: 刷新间隔（秒），默认3秒
        """
        # 线程安全锁
        self._lock = threading.Lock()
        
        # 监控股票列表
        self._watch_list: Set[str] = set(watch_list) if watch_list else set()
        self._monitor_all = watch_list is None
        
        # 回调函数
        self._alert_callback = alert_callback
        
        # 刷新间隔
        self._refresh_interval = refresh_interval
        
        # 监控状态
        self._is_running = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        # 分析器
        self._analyzer = CallAuctionAnalyzer()
        
        # 预警规则列表
        self._alert_rules: List[AlertRule] = self._init_default_rules()
        
        # 当前数据缓存
        self._current_data: Dict[str, AuctionStock] = {}
        
        # 预警列表
        self._alerts: List[Alert] = []
        
        # 已触发预警的记录（避免重复预警）
        self._triggered_alerts: Dict[str, Set[str]] = {}
        logger.info(
            f"AuctionMonitor initialized: "
            f"watch_list={'全市场' if self._monitor_all else len(self._watch_list)}, "
            f"refresh_interval={refresh_interval}s"
        )
    
    def _init_default_rules(self) -> List[AlertRule]:
        """
        初始化默认预警规则
        
        Returns:
            预警规则列表
        """
        return [
            HighOpenRule(threshold=5.0, priority=2),
            LowOpenRule(threshold=-5.0, priority=2),
            VolumeAnomalyRule(multiplier=2.0, priority=3),
            LimitUpExpectedRule(threshold=9.0, priority=5),
            LimitDownExpectedRule(threshold=-9.0, priority=5),
            BigOrderRule(threshold=1000000, priority=4),
            PriceVolatilityRule(volatility_threshold=3.0, priority=3),
        ]
    
    def add_rule(self, rule: AlertRule) -> None:
        """
        添加自定义预警规则
        
        Args:
            rule: 预警规则对象
        """
        with self._lock:
            self._alert_rules.append(rule)
            logger.info(f"Added alert rule: {rule.name}")
    
    def remove_rule(self, rule_name: str) -> bool:
        """
        移除预警规则
        
        Args:
            rule_name: 规则名称
            
        Returns:
            是否成功移除
        """
        with self._lock:
            for i, rule in enumerate(self._alert_rules):
                if rule.name == rule_name:
                    self._alert_rules.pop(i)
                    logger.info(f"Removed alert rule: {rule_name}")
                    return True
            return False
    
    def start(self) -> None:
        """
        启动后台监控线程
        
        如果已经在运行，则不会重复启动
        """
        with self._lock:
            if self._is_running:
                logger.warning("Monitor is already running")
                return
            
            self._is_running = True
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="AuctionMonitorThread",
                daemon=True
            )
            self._monitor_thread.start()
            logger.info("Auction monitor started")
    
    def stop(self) -> None:
        """
        停止监控
        
        等待监控线程结束
        """
        with self._lock:
            if not self._is_running:
                logger.warning("Monitor is not running")
                return
            
            self._is_running = False
        # 等待线程结束（不在锁内等待）
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
            self._monitor_thread = None
        
        logger.info("Auction monitor stopped")
    
    def add_stock(self, stock_code: str) -> None:
        """
        添加监控股票
        
        Args:
            stock_code: 股票代码
        """
        with self._lock:
            self._watch_list.add(stock_code)
            self._monitor_all = False
            logger.info(f"Added stock to watch list: {stock_code}")
    
    def remove_stock(self, stock_code: str) -> None:
        """
        移除监控股票
        
        Args:
            stock_code: 股票代码
        """
        with self._lock:
            self._watch_list.discard(stock_code)
            # 同时清理相关缓存
            self._current_data.pop(stock_code, None)
            self._triggered_alerts.pop(stock_code, None)
            logger.info(f"Removed stock from watch list: {stock_code}")
    
    def set_watch_list(self, watch_list: Optional[List[str]]) -> None:
        """
        设置监控股票列表
        
        Args:
            watch_list: 股票代码列表，None则监控全市场
        """
        with self._lock:
            if watch_list is None:
                self._watch_list = set()
                self._monitor_all = True
            else:
                self._watch_list = set(watch_list)
                self._monitor_all = False
            logger.info(
                f"Watch list updated: "
                f"{'全市场' if self._monitor_all else len(self._watch_list)} stocks"
            )
    
    def get_realtime_data(self) -> Dict[str, Any]:
        """
        获取所有监控股票的实时竞价数据
        
        Returns:
            包含所有监控股票数据的字典，格式：
            {
                'timestamp': ISO格式时间戳,
                'is_auction_time': 是否在竞价时段,
                'stocks': {stock_code: stock_data, ...}
            }
        """
        with self._lock:
            stocks_data = {}
            for code, stock in self._current_data.items():
                stocks_data[code] = {
                    'stock_code': stock.stock_code,
                    'stock_name': stock.stock_name,
                    'auction_price': stock.auction_price,
                    'auction_change': stock.auction_change,
                    'auction_volume': stock.auction_volume,
                    'volume_ratio': stock.volume_ratio,
                    'buy_volume': stock.buy_volume,
                    'sell_volume': stock.sell_volume,
                    'net_inflow': stock.net_inflow,
                    'is_abnormal': stock.is_abnormal,
                    'abnormal_reason': stock.abnormal_reason,
                }
            return {
                'timestamp': datetime.now().isoformat(),
                'is_auction_time': self.is_auction_time(),
                'stocks': stocks_data,'total_count': len(stocks_data),
                'abnormal_count': sum(1 for s in self._current_data.values() if s.is_abnormal),
            }
    
    def get_alerts(self) -> List[Alert]:
        """
        获取当前所有预警
        
        Returns:
            预警列表，按优先级和时间排序
        """
        with self._lock:
            # 按优先级降序、时间降序排序
            sorted_alerts = sorted(
                self._alerts,
                key=lambda a: (a.priority, a.timestamp),
                reverse=True
            )
            return sorted_alerts.copy()
    
    def clear_alerts(self) -> None:
        """
        清空所有预警
        """
        with self._lock:
            self._alerts.clear()
            self._triggered_alerts.clear()
            logger.info("All alerts cleared")
    
    def is_auction_time(self) -> bool:
        """
        判断当前是否在竞价时段
        
        竞价时段包括：
        - 早盘集合竞价：9:15-9:25
        -尾盘集合竞价：14:57-15:00
        
        Returns:
            当前是否在竞价时段
        """
        now = datetime.now().time()
        
        # 早盘竞价时段
        if self.MORNING_AUCTION_START <= now <= self.MORNING_AUCTION_END:
            return True
        
        # 尾盘竞价时段
        if self.AFTERNOON_AUCTION_START <= now <= self.AFTERNOON_AUCTION_END:
            return True
        
        return False
    
    def get_auction_phase(self) -> str:
        """
        获取当前竞价阶段
        
        Returns:
            竞价阶段描述
        """
        now = datetime.now().time()
        
        if self.MORNING_AUCTION_START <= now <= self.MORNING_AUCTION_END:
            return "早盘集合竞价"
        elif self.AFTERNOON_AUCTION_START <= now <= self.AFTERNOON_AUCTION_END:
            return "尾盘集合竞价"
        elif now < self.MORNING_AUCTION_START:
            return "早盘竞价未开始"
        elif now > self.AFTERNOON_AUCTION_END:
            return "今日竞价已结束"
        else:
            return "非竞价时段"
    
    @property
    def is_running(self) -> bool:
        """
        获取监控运行状态
        
        Returns:
            是否正在运行
        """
        return self._is_running
    
    @property
    def watch_count(self) -> int:
        """
        获取监控股票数量
        
        Returns:
            监控股票数量，-1表示全市场
        """
        if self._monitor_all:
            return -1
        return len(self._watch_list)
    
    def _monitor_loop(self) -> None:
        """
        监控循环（在后台线程中运行）
        """
        logger.info("Monitor loop started")
        
        while self._is_running:
            try:
                # 获取并处理数据
                self._fetch_and_process()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
            
            # 等待下一次刷新
            time.sleep(self._refresh_interval)
        
        logger.info("Monitor loop ended")
    
    def _fetch_and_process(self) -> None:
        """
        获取数据并处理预警
        """
        try:
            # 获取竞价数据
            stocks = self._analyzer.get_auction_data()
            
            if not stocks:
                logger.debug("No auction data received")
                return
            
            # 过滤监控股票
            with self._lock:
                if not self._monitor_all:
                    stocks = [s for s in stocks if s.stock_code in self._watch_list]
                
                # 更新数据缓存
                for stock in stocks:
                    self._current_data[stock.stock_code] = stock
            
            # 检查预警
            self._check_alerts(stocks)
            
            logger.debug(f"Processed {len(stocks)} stocks")
            
        except Exception as e:
            logger.error(f"Error fetching auction data: {e}", exc_info=True)
    
    def _check_alerts(self, stocks: List[AuctionStock]) -> None:
        """
        检查所有预警规则
        
        Args:
            stocks: 股票数据列表
        """
        for stock in stocks:
            stock_code = stock.stock_code
            
            # 准备检查数据
            check_data = {
                'stock_code': stock.stock_code,
                'stock_name': stock.stock_name,
                'auction_price': stock.auction_price,
                'auction_change': stock.auction_change,
                'auction_volume': stock.auction_volume,
                'volume_ratio': stock.volume_ratio,
                'net_inflow': stock.net_inflow,
            }
            
            # 遍历所有规则
            for rule in self._alert_rules:
                if not rule.enabled:
                    continue
                
                try:
                    alert = rule.check(check_data)
                    if alert:
                        self._handle_alert(stock_code, rule.name, alert)
                except Exception as e:
                    logger.error(
                        f"Error checking rule {rule.name} for {stock_code}: {e}"
                    )
    
    def _handle_alert(self, stock_code: str, rule_name: str, alert: Alert) -> None:
        """
        处理预警
        
        Args:
            stock_code: 股票代码
            rule_name: 规则名称
            alert: 预警对象
        """
        with self._lock:
            # 检查是否已触发过
            if stock_code not in self._triggered_alerts:
                self._triggered_alerts[stock_code] = set()
            
            if rule_name in self._triggered_alerts[stock_code]:
                return  # 已触发过，跳过
            
            # 记录已触发
            self._triggered_alerts[stock_code].add(rule_name)
            
            # 添加到预警列表
            self._alerts.append(alert)
            
            logger.info(f"Alert triggered: {alert}")
        # 调用回调函数（在锁外调用，避免死锁）
        if self._alert_callback:
            try:
                self._alert_callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}", exc_info=True)
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取监控器状态
        
        Returns:
            状态信息字典
        """
        with self._lock:
            return {
                'is_running': self._is_running,
                'is_auction_time': self.is_auction_time(),
                'auction_phase': self.get_auction_phase(),
                'watch_count': self.watch_count,
                'monitor_all': self._monitor_all,
                'refresh_interval': self._refresh_interval,
                'rules_count': len(self._alert_rules),
                'enabled_rules': sum(1 for r in self._alert_rules if r.enabled),
                'current_data_count': len(self._current_data),
                'alerts_count': len(self._alerts),
            }
    
    def get_stock_data(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取指定股票的实时数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票数据字典，未找到返回None
        """
        with self._lock:
            stock = self._current_data.get(stock_code)
            if stock:
                return {
                    'stock_code': stock.stock_code,
                    'stock_name': stock.stock_name,
                    'auction_price': stock.auction_price,
                    'auction_change': stock.auction_change,
                    'auction_volume': stock.auction_volume,
                    'volume_ratio': stock.volume_ratio,
                    'buy_volume': stock.buy_volume,
                    'sell_volume': stock.sell_volume,
                    'net_inflow': stock.net_inflow,
                    'is_abnormal': stock.is_abnormal,
                    'abnormal_reason': stock.abnormal_reason,
                }
            return None
    
    def get_abnormal_stocks(self) -> List[Dict[str, Any]]:
        """
        获取所有异动股票
        
        Returns:
            异动股票列表
        """
        with self._lock:
            abnormal = []
            for stock in self._current_data.values():
                if stock.is_abnormal:
                    abnormal.append({
                        'stock_code': stock.stock_code,
                        'stock_name': stock.stock_name,
                        'auction_price': stock.auction_price,
                        'auction_change': stock.auction_change,
                        'volume_ratio': stock.volume_ratio,
                        'abnormal_reason': stock.abnormal_reason,
                    })
            # 按涨幅排序
            abnormal.sort(key=lambda x: x['auction_change'], reverse=True)
            return abnormal
    def manual_refresh(self) -> Dict[str, Any]:
        """
        手动刷新数据
        
        Returns:
            刷新后的数据
        """
        self._fetch_and_process()
        return self.get_realtime_data()