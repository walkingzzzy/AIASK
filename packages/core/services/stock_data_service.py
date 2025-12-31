"""
统一股票数据服务
整合数据层、缓存、指标计算和AI评分
"""
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import asdict
from functools import wraps
import logging
import threading
import concurrent.futures
import pandas as pd
import re

from ..data_layer.sources.source_aggregator import get_data_source, DataSourceAggregator
from ..data_layer.sources.base_adapter import StockQuote, DailyBar, FinancialData
from ..data_layer.cache.cache_manager import get_cache_manager, CacheManager
from ..data_layer.quality.validator import DataValidator
from ..indicators import MA, EMA, MACD, RSI, KDJ, BOLL, ATR, OBV
from ..scoring.ai_score.score_calculator import AIScoreCalculator, AIScoreResult
from ..scoring.explainer.score_explainer import ScoreExplainer, ExplanationResult
from ..exceptions import (
    InvalidStockCodeError, DataNotFoundError, CalculationError,
    DataSourceError, CacheError
)
from ..vector_store.retrieval.retriever import StockRetriever, get_retriever
from ..vector_store.indexer.stock_indexer import StockDataIndexer, get_stock_indexer

logger = logging.getLogger(__name__)

# 单例锁
_service_lock = threading.Lock()


def validate_stock_code_decorator(func: Callable) -> Callable:
    """股票代码验证装饰器"""
    @wraps(func)
    def wrapper(self, stock_code: str, *args, **kwargs):
        StockDataService.validate_stock_code(stock_code)
        return func(self, stock_code, *args, **kwargs)
    return wrapper


class StockDataService:
    """
    统一股票数据服务
    
    功能：
    1. 获取实时行情（带缓存）
    2. 获取历史数据（带缓存）
    3. 计算技术指标
    4. 计算AI评分
    5. 生成评分解释
    """
    
    # 缓存TTL配置 (memory_ttl, sqlite_ttl)
    CACHE_TTL = {
        'realtime': (30, 60),           # 实时行情: 内存30秒, SQLite1分钟
        'daily': (1800, 86400),         # 日线: 内存30分钟, SQLite1天
        'financial': (3600, 604800),    # 财务数据: 内存1小时, SQLite7天
        'indicators': (300, 3600),      # 指标: 内存5分钟, SQLite1小时
        'ai_score': (300, 1800)         # AI评分: 内存5分钟, SQLite30分钟
    }
    
    def __init__(self,
                 data_source: Optional[DataSourceAggregator] = None,
                 cache_manager: Optional[CacheManager] = None,
                 use_enhanced_scoring: bool = True):
        self.data_source = data_source or get_data_source()
        self.cache = cache_manager or get_cache_manager()
        self.validator = DataValidator()
        self.score_calculator = AIScoreCalculator(use_enhanced=use_enhanced_scoring)
        self.score_explainer = ScoreExplainer()
        
        # 新增: 知识库检索器和索引器
        self.retriever = get_retriever()
        self.indexer = get_stock_indexer()

    @staticmethod
    def validate_stock_code(stock_code: str) -> bool:
        """
        验证股票代码格式

        Args:
            stock_code: 股票代码

        Returns:
            是否有效

        Raises:
            InvalidStockCodeError: 股票代码格式无效
        """
        if not stock_code:
            raise InvalidStockCodeError("空代码")

        # A股代码格式：6位数字
        if not re.match(r'^\d{6}$', stock_code):
            raise InvalidStockCodeError(stock_code)
        
        # 验证股票代码前缀的合法性
        prefix = stock_code[:3]
        valid_prefixes = {
            # 上交所
            '600', '601', '603', '605',  # 主板
            '688',  # 科创板
            '900',  # B股
            # 深交所
            '000', '001', '002', '003',  # 主板、中小板
            '300', '301',  # 创业板
            '200',  # B股
            # 北交所
            '430', '830', '831', '832', '833', '834', '835', '836', '837', '838', '839',
            '870', '871', '872', '873',
        }
        
        # 检查前3位是否在有效前缀中
        if prefix not in valid_prefixes:
            # 检查前2位（某些代码如002xxx）
            prefix2 = stock_code[:2]
            valid_prefix2 = {'00', '30', '60', '68', '83', '87'}
            if prefix2 not in valid_prefix2:
                raise InvalidStockCodeError(f"{stock_code} (无效的股票代码前缀)")

        return True
    
    # ==================== 行情数据 ====================
    
    def get_realtime_quote(self, stock_code: str,
                           use_cache: bool = True) -> Optional[Dict]:
        """
        获取实时行情

        Args:
            stock_code: 股票代码
            use_cache: 是否使用缓存

        Returns:
            行情数据字典

        Raises:
            InvalidStockCodeError: 股票代码格式无效
            DataSourceError: 数据源错误
        """
        try:
            self.validate_stock_code(stock_code)
        except InvalidStockCodeError as e:
            logger.warning(f"股票代码验证失败: {e}")
            raise

        cache_key = f"quote:{stock_code}"

        if use_cache:
            try:
                cached = self.cache.get(cache_key)
                if cached:
                    return cached
            except Exception as e:
                logger.warning(f"缓存读取失败: {e}")

        try:
            quote = self.data_source.get_realtime_quote(stock_code)
            if quote:
                result = asdict(quote)
                memory_ttl, sqlite_ttl = self.CACHE_TTL['realtime']
                try:
                    self.cache.set(cache_key, result, memory_ttl=memory_ttl, sqlite_ttl=sqlite_ttl)
                except Exception as e:
                    logger.warning(f"缓存写入失败: {e}")
                return result
            else:
                logger.info(f"未找到股票 {stock_code} 的行情数据")
                return None
        except Exception as e:
            logger.error(f"获取实时行情失败 {stock_code}: {e}")
            raise DataSourceError(f"获取实时行情失败", str(e))
    
    def get_daily_bars(self, stock_code: str, 
                       days: int = 120,
                       use_cache: bool = True) -> Optional[pd.DataFrame]:
        """
        获取日线数据
        
        Args:
            stock_code: 股票代码
            days: 获取天数
            use_cache: 是否使用缓存
            
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        cache_key = f"daily:{stock_code}:{days}"
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return pd.DataFrame(cached)
        
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days*2)).strftime("%Y%m%d")
        
        bars = self.data_source.get_daily_bars(stock_code, start_date, end_date)
        if bars:
            df = pd.DataFrame([asdict(b) for b in bars])
            df = df.tail(days)  # 取最近N天

            memory_ttl, sqlite_ttl = self.CACHE_TTL['daily']
            self.cache.set(cache_key, df.to_dict('records'),
                          memory_ttl=memory_ttl, sqlite_ttl=sqlite_ttl)
            return df
        
        return None
    
    def get_financial_data(self, stock_code: str,
                           use_cache: bool = True) -> Optional[Dict]:
        """
        获取财务数据
        
        Args:
            stock_code: 股票代码
            use_cache: 是否使用缓存
            
        Returns:
            财务数据字典
        """
        cache_key = f"financial:{stock_code}"
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
        
        financial = self.data_source.get_financial_data(stock_code)
        if financial:
            result = asdict(financial)
            memory_ttl, sqlite_ttl = self.CACHE_TTL['financial']
            self.cache.set(cache_key, result, memory_ttl=memory_ttl, sqlite_ttl=sqlite_ttl)
            return result
        
        return None
    
    # ==================== 技术指标 ====================
    
    def calculate_indicators(self, stock_code: str,
                             use_cache: bool = True) -> Optional[Dict]:
        """
        计算技术指标

        Args:
            stock_code: 股票代码
            use_cache: 是否使用缓存

        Returns:
            技术指标字典

        Raises:
            InvalidStockCodeError: 股票代码格式无效
            CalculationError: 指标计算错误
        """
        try:
            self.validate_stock_code(stock_code)
        except InvalidStockCodeError as e:
            logger.warning(f"股票代码验证失败: {e}")
            raise

        cache_key = f"indicators:{stock_code}"

        if use_cache:
            try:
                cached = self.cache.get(cache_key)
                if cached:
                    return cached
            except Exception as e:
                logger.warning(f"缓存读取失败: {e}")

        # 获取日线数据
        try:
            df = self.get_daily_bars(stock_code, days=120)
        except Exception as e:
            logger.error(f"获取日线数据失败 {stock_code}: {e}")
            raise CalculationError("无法获取历史数据", str(e))

        if df is None or df.empty:
            logger.warning(f"股票 {stock_code} 没有足够的历史数据")
            return None

        try:
            indicators = {}
            
            # 均线 - MA类在构造时设置periods，calculate不接受period参数
            ma = MA(periods=[5, 10, 20, 60])
            ma_result = ma.calculate(df)
            if not ma_result.empty:
                for period in [5, 10, 20, 60]:
                    col_name = f'MA{period}'
                    if col_name in ma_result.columns:
                        val = ma_result[col_name].iloc[-1]
                        if pd.notna(val):
                            indicators[f'ma{period}'] = float(val)
            
            # MACD
            macd = MACD()
            macd_result = macd.calculate(df)
            if not macd_result.empty:
                if 'DIF' in macd_result.columns:
                    indicators['macd_dif'] = float(macd_result['DIF'].iloc[-1])
                if 'DEA' in macd_result.columns:
                    indicators['macd_dea'] = float(macd_result['DEA'].iloc[-1])
                if 'MACD' in macd_result.columns:
                    indicators['macd_hist'] = float(macd_result['MACD'].iloc[-1])
            
            # RSI - RSI类在构造时设置periods列表
            rsi = RSI(periods=[14])
            rsi_result = rsi.calculate(df)
            if not rsi_result.empty and 'RSI14' in rsi_result.columns:
                indicators['rsi'] = float(rsi_result['RSI14'].iloc[-1])
            
            # KDJ
            kdj = KDJ()
            kdj_result = kdj.calculate(df)
            if not kdj_result.empty:
                if 'K' in kdj_result.columns:
                    indicators['kdj_k'] = float(kdj_result['K'].iloc[-1])
                if 'D' in kdj_result.columns:
                    indicators['kdj_d'] = float(kdj_result['D'].iloc[-1])
                if 'J' in kdj_result.columns:
                    indicators['kdj_j'] = float(kdj_result['J'].iloc[-1])
            
            # BOLL
            boll = BOLL()
            boll_result = boll.calculate(df)
            if not boll_result.empty:
                if 'upper' in boll_result.columns:
                    indicators['boll_upper'] = float(boll_result['upper'].iloc[-1])
                if 'middle' in boll_result.columns:
                    indicators['boll_middle'] = float(boll_result['middle'].iloc[-1])
                if 'lower' in boll_result.columns:
                    indicators['boll_lower'] = float(boll_result['lower'].iloc[-1])
            
            # ATR
            atr = ATR()
            atr_result = atr.calculate(df)
            if not atr_result.empty and 'ATR' in atr_result.columns:
                indicators['atr'] = float(atr_result['ATR'].iloc[-1])
            
            # 当前价格和涨跌
            indicators['close'] = float(df['close'].iloc[-1])
            if len(df) > 1:
                prev_close = float(df['close'].iloc[-2])
                indicators['price_change'] = (indicators['close'] - prev_close) / prev_close
            
            # 成交量比
            if 'volume' in df.columns and len(df) >= 5:
                avg_vol = df['volume'].tail(5).mean()
                indicators['volume_ratio'] = float(df['volume'].iloc[-1] / avg_vol) if avg_vol > 0 else 1.0
            
            memory_ttl, sqlite_ttl = self.CACHE_TTL['indicators']
            try:
                self.cache.set(cache_key, indicators, memory_ttl=memory_ttl, sqlite_ttl=sqlite_ttl)
            except Exception as e:
                logger.warning(f"缓存写入失败: {e}")
            return indicators

        except Exception as e:
            logger.error(f"计算指标失败 {stock_code}: {e}")
            raise CalculationError(f"技术指标计算失败", str(e))
    
    # ==================== AI评分 ====================
    
    def get_ai_score(self, stock_code: str, stock_name: str = "",
                     use_cache: bool = True) -> Optional[AIScoreResult]:
        """
        获取AI评分
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            use_cache: 是否使用缓存
            
        Returns:
            AIScoreResult
        """
        cache_key = f"ai_score:{stock_code}"
        
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                # 从缓存重建对象
                return AIScoreResult(**cached)
        
        # 收集评分所需数据
        data = self._collect_score_data(stock_code)
        if not data:
            return None
        
        try:
            result = self.score_calculator.calculate(stock_code, stock_name, data)
            memory_ttl, sqlite_ttl = self.CACHE_TTL['ai_score']
            self.cache.set(cache_key, result.to_dict(), memory_ttl=memory_ttl, sqlite_ttl=sqlite_ttl)
            return result
        except Exception as e:
            logger.error(f"计算AI评分失败 {stock_code}: {e}")
            return None
    
    def get_score_explanation(self, stock_code: str, 
                               stock_name: str = "") -> Optional[ExplanationResult]:
        """
        获取评分解释
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            ExplanationResult
        """
        score_result = self.get_ai_score(stock_code, stock_name)
        if not score_result:
            return None
        
        return self.score_explainer.explain(score_result.to_dict())
    
    def _collect_score_data(self, stock_code: str) -> Optional[Dict]:
        """
        收集评分所需的所有数据
        
        返回数据包含 data_completeness 字段，标识数据完整性信息
        """
        data = {}
        
        # 数据完整性跟踪
        data_completeness = {
            'total_fields': 0,
            'available_fields': 0,
            'missing_fields': [],
            'default_value_fields': [],
            'completeness_percent': 0.0,
            'data_sources': {
                'realtime_quote': False,
                'technical_indicators': False,
                'financial_data': False
            }
        }
        
        # 必需的财务指标字段
        required_financial_fields = [
            'pe', 'pb', 'roe', 'gross_margin',
            'revenue_growth', 'profit_growth', 'pe_percentile'
        ]
        
        # 必需的其他字段
        required_other_fields = [
            'pe_percentile', 'market_breadth', 'volatility', 'beta', 'max_drawdown'
        ]
        
        # 实时行情
        quote = self.get_realtime_quote(stock_code)
        if quote:
            data['close'] = quote.get('price', 0)
            data['volume_ratio'] = quote.get('volume_ratio', 1.0)
            data_completeness['data_sources']['realtime_quote'] = True
        else:
            data_completeness['missing_fields'].append('realtime_quote')
        
        # 技术指标
        indicators = self.calculate_indicators(stock_code)
        if indicators:
            data.update(indicators)
            data_completeness['data_sources']['technical_indicators'] = True
        else:
            data_completeness['missing_fields'].append('technical_indicators')
        
        # 财务数据
        financial = self.get_financial_data(stock_code)
        if financial:
            data_completeness['data_sources']['financial_data'] = True
            for field in required_financial_fields:
                value = financial.get(field)
                if value is not None:
                    data[field] = value
                    data_completeness['available_fields'] += 1
                else:
                    # 使用默认值
                    default_values = {
                        'pe': 20, 'pb': 2, 'roe': 10, 'gross_margin': 30,
                        'revenue_growth': 0, 'profit_growth': 0, 'pe_percentile': 50
                    }
                    data[field] = default_values.get(field, 0)
                    data_completeness['default_value_fields'].append(field)
                data_completeness['total_fields'] += 1
        else:
            # 财务数据完全缺失，全部使用默认值
            data_completeness['missing_fields'].append('financial_data')
            default_financial = {
                'pe': 20, 'pb': 2, 'roe': 10, 'gross_margin': 30,
                'revenue_growth': 0, 'profit_growth': 0, 'pe_percentile': 50
            }
            for field, default_value in default_financial.items():
                data[field] = default_value
                data_completeness['default_value_fields'].append(field)
                data_completeness['total_fields'] += 1
        
        # 默认值填充（其他必需字段）
        other_defaults = {
            'pe_percentile': 50,
            'market_breadth': 0.5,
            'volatility': 0.02,
            'beta': 1.0,
            'max_drawdown': 0.15
        }
        
        for field, default_value in other_defaults.items():
            data_completeness['total_fields'] += 1
            if field not in data or data[field] is None:
                data[field] = default_value
                if field not in data_completeness['default_value_fields']:
                    data_completeness['default_value_fields'].append(field)
            else:
                data_completeness['available_fields'] += 1
        
        # 计算完整度百分比
        total = data_completeness['total_fields']
        available = data_completeness['available_fields']
        if total > 0:
            data_completeness['completeness_percent'] = round((available / total) * 100, 1)
        
        # 生成完整性消息
        if data_completeness['completeness_percent'] >= 80:
            data_completeness['status'] = 'complete'
            data_completeness['message'] = '数据完整，评分可靠'
        elif data_completeness['completeness_percent'] >= 50:
            data_completeness['status'] = 'partial'
            data_completeness['message'] = f"部分数据缺失（{len(data_completeness['default_value_fields'])}项使用默认值），评分供参考"
        else:
            data_completeness['status'] = 'incomplete'
            data_completeness['message'] = f"数据不完整（{len(data_completeness['default_value_fields'])}项使用默认值），评分仅供参考"
        
        # 将完整性信息添加到数据中
        data['_data_completeness'] = data_completeness
        
        return data if data else None
    
    # ==================== 批量操作 ====================
    
    def batch_get_ai_scores(self, stock_codes: List[str],
                            stock_names: Optional[Dict[str, str]] = None,
                            max_workers: int = 5) -> List[AIScoreResult]:
        """
        批量获取AI评分（并发控制）
        
        Args:
            stock_codes: 股票代码列表
            stock_names: 股票名称映射 {code: name}
            max_workers: 最大并发数
            
        Returns:
            AIScoreResult列表
        """
        results = []
        stock_names = stock_names or {}
        
        def get_score(code: str) -> Optional[AIScoreResult]:
            name = stock_names.get(code, code)
            return self.get_ai_score(code, name)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_code = {executor.submit(get_score, code): code for code in stock_codes}
            for future in concurrent.futures.as_completed(future_to_code):
                try:
                    score = future.result()
                    if score:
                        results.append(score)
                except Exception as e:
                    code = future_to_code[future]
                    logger.warning(f"获取AI评分失败 {code}: {e}")
        
        return results
    
    def get_top_stocks(self, stock_codes: List[str],
                       top_n: int = 10,
                       stock_names: Optional[Dict[str, str]] = None) -> List[AIScoreResult]:
        """
        获取评分最高的股票
        
        Args:
            stock_codes: 候选股票代码列表
            top_n: 返回数量
            stock_names: 股票名称映射
            
        Returns:
            按评分排序的AIScoreResult列表
        """
        scores = self.batch_get_ai_scores(stock_codes, stock_names)
        scores.sort(key=lambda x: x.ai_score, reverse=True)
        return scores[:top_n]
    
    # ==================== 缓存优化 ====================

    def warm_cache(self, stock_codes: List[str]):
        """
        预热缓存 - 批量预加载常用股票数据

        Args:
            stock_codes: 需要预热的股票代码列表
        """
        logger.info(f"开始预热缓存，共{len(stock_codes)}只股票")

        for code in stock_codes:
            try:
                # 预加载实时行情
                self.get_realtime_quote(code, use_cache=False)
                # 预加载日线数据
                self.get_daily_bars(code, days=120, use_cache=False)
                # 预加载技术指标
                self.calculate_indicators(code, use_cache=False)
            except Exception as e:
                logger.warning(f"预热缓存失败 {code}: {e}")

        logger.info("缓存预热完成")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            缓存统计数据
        """
        return self.cache.stats()

    def clear_cache(self, pattern: Optional[str] = None):
        """
        清理缓存

        Args:
            pattern: 缓存key模式，如 "quote:*" 只清理行情缓存
        """
        if pattern is None:
            self.cache.clear_all()
            logger.info("已清空所有缓存")
        else:
            # 基于 pattern 的缓存清理
            if hasattr(self.cache, 'clear_pattern'):
                count = self.cache.clear_pattern(pattern)
                logger.info(f"已清理匹配 '{pattern}' 的缓存 {count} 条")
            elif hasattr(self.cache, 'keys'):
                # 手动匹配清理
                import fnmatch
                keys_to_delete = []
                for key in self.cache.keys():
                    if fnmatch.fnmatch(key, pattern):
                        keys_to_delete.append(key)
                for key in keys_to_delete:
                    self.cache.delete(key)
                logger.info(f"已清理匹配 '{pattern}' 的缓存 {len(keys_to_delete)} 条")
            else:
                logger.warning(f"缓存不支持模式清理，清空所有缓存")
                self.cache.clear_all()

    def cleanup_expired_cache(self) -> int:
        """
        清理过期缓存

        Returns:
            清理的条目数
        """
        count = self.cache.cleanup()
        logger.info(f"清理了{count}条过期缓存")
        return count

    # ==================== 健康检查 ====================

    def health_check(self) -> Dict[str, Any]:
        """服务健康检查"""
        return {
            "data_source": self.data_source.health_check_all(),
            "cache": self.cache.stats(),
            "status": "healthy"
        }
    
    # ==================== 知识库检索 ====================
    
    def get_context_for_analysis(self, stock_code: str, 
                                  query: str = "",
                                  max_tokens: int = 2000) -> str:
        """
        获取RAG上下文用于AI分析
        
        Args:
            stock_code: 股票代码
            query: 查询文本（可选）
            max_tokens: 最大token数
            
        Returns:
            构建的上下文文本
        """
        if not query:
            query = f"{stock_code} 投资分析"
        
        return self.retriever.build_context(query, stock_code, max_tokens)
    
    def search_knowledge_base(self, query: str,
                               stock_code: Optional[str] = None,
                               top_k: int = 5) -> List[Dict]:
        """
        搜索知识库
        
        Args:
            query: 搜索查询
            stock_code: 限定股票代码（可选）
            top_k: 返回数量
            
        Returns:
            检索结果列表
        """
        if stock_code:
            result = self.retriever.retrieve_for_stock(stock_code, query, top_k)
        else:
            result = self.retriever.retrieve(query, top_k)
        
        return result.results
    
    def find_similar_stocks(self, stock_code: str, top_k: int = 5) -> List[Dict]:
        """
        查找相似股票
        
        基于向量相似度查找特征相似的股票
        """
        return self.retriever.retrieve_similar_stocks(stock_code, top_k)
    
    # ==================== 数据索引 ====================
    
    def index_stock_data(self, stock_code: str, stock_name: str = "") -> bool:
        """
        索引单只股票的数据到知识库
        
        在获取数据后自动调用，保持知识库更新
        """
        try:
            quote = self.get_realtime_quote(stock_code)
            indicators = self.calculate_indicators(stock_code)
            financial = self.get_financial_data(stock_code)
            
            success = True
            
            if quote and indicators:
                success &= self.indexer.index_stock_summary(
                    stock_code, stock_name or stock_code, quote, indicators
                )
            
            if financial:
                success &= self.indexer.index_financial_report(
                    stock_code, stock_name or stock_code, financial
                )
            
            return success
            
        except Exception as e:
            logger.error(f"索引股票数据失败 {stock_code}: {e}")
            return False
    
    # ==================== 回测数据支持 ====================
    
    def get_score_data(self, stock_codes: List[str],
                       start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        获取回测所需的评分数据
        
        Args:
            stock_codes: 股票代码列表
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
        
        Returns:
            DataFrame with columns: date, stock_code, score, signal
        """
        try:
            from datetime import datetime as dt_class
            
            # 解析日期
            if start_date:
                start_dt = dt_class.strptime(start_date, "%Y-%m-%d")
            else:
                start_dt = datetime.now() - timedelta(days=365)
            
            if end_date:
                end_dt = dt_class.strptime(end_date, "%Y-%m-%d")
            else:
                end_dt = datetime.now()
            
            all_records = []
            
            for stock_code in stock_codes:
                try:
                    # 获取日线数据
                    days = (end_dt - start_dt).days + 60  # 额外获取一些数据用于计算指标
                    df = self.get_daily_bars(stock_code, days=days)
                    
                    if df is None or df.empty:
                        continue
                    
                    # 确保日期格式正确
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
                    
                    # 对每个交易日计算评分
                    for _, row in df.iterrows():
                        try:
                            # 简化的评分计算（基于价格变化和成交量）
                            data = {
                                'close': row.get('close', 0),
                                'volume': row.get('volume', 0),
                                'open': row.get('open', 0),
                                'high': row.get('high', 0),
                                'low': row.get('low', 0)
                            }
                            
                            # 计算简单评分 (0-10)
                            price_change = (data['close'] - data['open']) / data['open'] if data['open'] > 0 else 0
                            score = 5.0 + price_change * 50  # 基础分5分，涨跌幅影响
                            score = max(0, min(10, score))  # 限制在0-10之间
                            
                            # 信号判断
                            if score >= 7:
                                signal = 'buy'
                            elif score <= 4:
                                signal = 'sell'
                            else:
                                signal = 'hold'
                            
                            all_records.append({
                                'date': row.get('date'),
                                'stock_code': stock_code,
                                'score': round(score, 2),
                                'signal': signal
                            })
                        except Exception:
                            continue
                            
                except Exception as e:
                    logger.warning(f"获取股票 {stock_code} 评分数据失败: {e}")
                    continue
            
            if not all_records:
                return None
            
            result_df = pd.DataFrame(all_records)
            return result_df
            
        except Exception as e:
            logger.error(f"获取评分数据失败: {e}")
            return None
    
    def get_price_data(self, stock_codes: List[str],
                       start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        获取回测所需的价格数据
        
        Args:
            stock_codes: 股票代码列表
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
        
        Returns:
            DataFrame with columns: date, stock_code, open, high, low, close, volume
        """
        try:
            from datetime import datetime as dt_class
            
            # 解析日期
            if start_date:
                start_dt = dt_class.strptime(start_date, "%Y-%m-%d")
            else:
                start_dt = datetime.now() - timedelta(days=365)
            
            if end_date:
                end_dt = dt_class.strptime(end_date, "%Y-%m-%d")
            else:
                end_dt = datetime.now()
            
            all_records = []
            
            for stock_code in stock_codes:
                try:
                    # 获取日线数据
                    days = (end_dt - start_dt).days + 30
                    df = self.get_daily_bars(stock_code, days=days)
                    
                    if df is None or df.empty:
                        continue
                    
                    # 确保日期格式正确
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
                    
                    # 添加股票代码
                    df = df.copy()
                    df['stock_code'] = stock_code
                    
                    # 选择需要的列
                    required_cols = ['date', 'stock_code', 'open', 'high', 'low', 'close', 'volume']
                    available_cols = [col for col in required_cols if col in df.columns]
                    df = df[available_cols]
                    
                    all_records.append(df)
                    
                except Exception as e:
                    logger.warning(f"获取股票 {stock_code} 价格数据失败: {e}")
                    continue
            
            if not all_records:
                return None
            
            result_df = pd.concat(all_records, ignore_index=True)
            return result_df
            
        except Exception as e:
            logger.error(f"获取价格数据失败: {e}")
            return None
    
    # ==================== 数据索引 ====================
    
    def sync_knowledge_base(self, stock_codes: List[str],
                            stock_names: Optional[Dict[str, str]] = None) -> Dict:
        """
        同步知识库
        
        批量更新多只股票的知识库数据
        """
        stock_names = stock_names or {}
        stock_list = [
            {"code": code, "name": stock_names.get(code, code)}
            for code in stock_codes
        ]
        
        stats = self.indexer.index_batch_stocks(stock_list, self)
        
        return {
            "total": stats.total_docs,
            "success": stats.new_docs,
            "failed": stats.failed_docs,
            "time_ms": stats.execution_time_ms
        }


# 全局单例
_service_instance: Optional[StockDataService] = None


def get_stock_service() -> StockDataService:
    """获取股票数据服务单例（线程安全）"""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            # 双重检查锁定
            if _service_instance is None:
                _service_instance = StockDataService()
    return _service_instance
