"""
涨停分析器
提供涨停数据获取、原因分析、连板预测等功能
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import re

try:
    import akshare as ak
    import pandas as pd
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None
    pd = None

logger = logging.getLogger(__name__)


class LimitUpType(Enum):
    """涨停类型"""
    FIRST_LIMIT = "首板"
    SECOND_LIMIT = "二连板"
    THIRD_LIMIT = "三连板"
    MULTI_LIMIT = "多连板"
    T_BOARD = "T字板"
    ONE_WORD = "一字板"
    BROKEN = "炸板"


class LimitUpReasonType(Enum):
    """涨停原因类型"""
    CONCEPT = "概念题材"
    EARNINGS = "业绩驱动"
    POLICY = "政策利好"
    MERGER = "并购重组"
    INSTITUTION = "机构买入"
    NORTH_FUND = "北向资金"
    TECHNICAL = "技术突破"
    OVERSOLD = "超跌反弹"
    FOLLOW = "跟风上涨"
    UNKNOWN = "未知"


@dataclass
class LimitUpStock:
    """涨停股票信息"""
    stock_code: str
    stock_name: str
    limit_up_time: str = ""          # 涨停时间
    limit_up_type: str = "首板"       # 涨停类型
    continuous_days: int = 1          # 连板天数
    turnover_rate: float = 0.0        # 换手率
    amount: float = 0.0               # 成交额（亿）
    circulating_value: float = 0.0    # 流通市值（亿）
    limit_up_reason: str = ""         # 涨停原因
    concept: str = ""                 # 所属概念
    open_count: int = 0               # 开板次数
    last_limit_time: str = ""         # 最后封板时间
    seal_amount: float = 0.0          # 封单金额（亿）
    seal_ratio: float = 0.0           # 封单比例
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class LimitUpReason:
    """涨停原因分析"""
    stock_code: str
    stock_name: str
    primary_reason: str = ""          # 主要原因
    reason_type: str = ""             # 原因类型
    related_concepts: List[str] = field(default_factory=list)  # 相关概念
    related_news: List[str] = field(default_factory=list)      # 相关新闻
    confidence: float = 0.5           # 置信度
    analysis: str = ""                # 分析说明
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ContinuationPrediction:
    """连板预测"""
    stock_code: str
    stock_name: str
    current_continuous: int = 1       # 当前连板数
    continuation_prob: float = 0.0    # 连板概率
    prediction: str = ""              # 预测结论
    factors: List[Dict] = field(default_factory=list)  # 影响因子
    risk_level: str = "中"            # 风险等级
    suggestion: str = ""              # 操作建议
    
    def to_dict(self) -> Dict:
        return asdict(self)


class LimitUpAnalyzer:
    """
    涨停分析器
    
    功能：
    1. 获取每日涨停股票列表
    2. 分析涨停原因
    3. 统计连板情况
    4. 预测连板概率
    """
    
    # 热门概念关键词
    HOT_CONCEPTS = [
        '人工智能', 'AI', 'ChatGPT', '大模型', '算力',
        '芯片', '半导体', '光刻机', '存储',
        '新能源', '锂电池', '储能', '光伏', '风电',
        '汽车', '智能驾驶', '无人驾驶',
        '医药', '创新药', '中药', '医疗器械',
        '消费', '白酒', '食品', '旅游',
        '军工', '航天', '国防',
        '数字经济', '数据要素', '信创',
        '华为', '苹果', '特斯拉',
    ]
    
    # 连板概率基准（历史统计）
    CONTINUATION_BASE_PROB = {
        1: 0.25,   # 首板连板概率
        2: 0.35,   # 二板连板概率
        3: 0.30,   # 三板连板概率
        4: 0.25,   # 四板连板概率
        5: 0.20,   # 五板及以上
    }
    
    def __init__(self):
        self._cache = {}
    
    def get_daily_limit_up(self, date: str = None) -> List[LimitUpStock]:
        """
        获取每日涨停股票列表
        
        Args:
            date: 日期，格式YYYYMMDD，默认今天
            
        Returns:
            涨停股票列表
        """
        if not HAS_AKSHARE:
            logger.error("akshare未安装，无法获取涨停数据")
            return []
        
        try:
            # 获取涨停数据
            df = ak.stock_zt_pool_em(date=date)
            
            if df is None or df.empty:
                logger.warning(f"未获取到 {date} 的涨停数据")
                return []
            
            stocks = []
            for _, row in df.iterrows():
                # 判断涨停类型
                continuous = int(row.get('连板数', 1))
                if continuous == 1:
                    limit_type = LimitUpType.FIRST_LIMIT.value
                elif continuous == 2:
                    limit_type = LimitUpType.SECOND_LIMIT.value
                elif continuous == 3:
                    limit_type = LimitUpType.THIRD_LIMIT.value
                else:
                    limit_type = LimitUpType.MULTI_LIMIT.value
                
                stocks.append(LimitUpStock(
                    stock_code=str(row.get('代码', '')),
                    stock_name=str(row.get('名称', '')),
                    limit_up_time=str(row.get('首次封板时间', '')),
                    limit_up_type=limit_type,
                    continuous_days=continuous,
                    turnover_rate=self._safe_float(row.get('换手率')),
                    amount=self._safe_float(row.get('成交额')) / 100000000,
                    circulating_value=self._safe_float(row.get('流通市值')) / 100000000,
                    limit_up_reason=str(row.get('涨停原因', '')),
                    concept=str(row.get('所属行业', '')),
                    open_count=int(row.get('开板次数', 0)),
                    last_limit_time=str(row.get('最后封板时间', '')),
                    seal_amount=self._safe_float(row.get('封单金额')) / 100000000,
                ))
            
            return stocks
            
        except Exception as e:
            logger.error(f"获取涨停数据失败: {e}")
            return []
    
    def get_continuous_limit_up(self, min_days: int = 2) -> List[LimitUpStock]:
        """
        获取连板股票
        
        Args:
            min_days: 最小连板天数
            
        Returns:
            连板股票列表
        """
        all_stocks = self.get_daily_limit_up()
        return [s for s in all_stocks if s.continuous_days >= min_days]
    
    def analyze_limit_up_reason(self, stock_code: str, 
                                 stock_name: str = "") -> LimitUpReason:
        """
        分析涨停原因
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            涨停原因分析
        """
        # 获取涨停信息
        limit_up_stocks = self.get_daily_limit_up()
        target_stock = None
        
        for stock in limit_up_stocks:
            if stock.stock_code == stock_code or stock.stock_code == stock_code.split('.')[0]:
                target_stock = stock
                break
        
        if not target_stock:
            return LimitUpReason(
                stock_code=stock_code,
                stock_name=stock_name,
                primary_reason="未找到涨停信息",
                reason_type=LimitUpReasonType.UNKNOWN.value,
                confidence=0.3
            )
        
        # 分析原因
        reason_type, confidence = self._classify_reason(target_stock)
        related_concepts = self._extract_concepts(target_stock)
        
        analysis = self._generate_analysis(target_stock, reason_type)
        
        return LimitUpReason(
            stock_code=stock_code,
            stock_name=target_stock.stock_name,
            primary_reason=target_stock.limit_up_reason or reason_type,
            reason_type=reason_type,
            related_concepts=related_concepts,
            confidence=confidence,
            analysis=analysis
        )
    
    def predict_continuation(self, stock_code: str,
                              stock_name: str = "") -> ContinuationPrediction:
        """
        预测连板概率
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            连板预测
        """
        # 获取当前涨停信息
        limit_up_stocks = self.get_daily_limit_up()
        target_stock = None
        
        for stock in limit_up_stocks:
            if stock.stock_code == stock_code or stock.stock_code == stock_code.split('.')[0]:
                target_stock = stock
                break
        
        if not target_stock:
            return ContinuationPrediction(
                stock_code=stock_code,
                stock_name=stock_name,
                prediction="未找到涨停信息",
                risk_level="高",
                suggestion="无法预测"
            )
        
        # 计算连板概率
        base_prob = self.CONTINUATION_BASE_PROB.get(
            min(target_stock.continuous_days, 5), 0.20
        )
        
        # 调整因子
        factors = []
        adjusted_prob = base_prob
        
        # 1. 封单比例因子
        if target_stock.seal_amount > 0:
            seal_factor = min(target_stock.seal_amount / 5, 0.15)  # 封单5亿以上加分
            adjusted_prob += seal_factor
            factors.append({
                'name': '封单金额',
                'value': f'{target_stock.seal_amount:.1f}亿',
                'impact': f'+{seal_factor:.1%}'
            })
        
        # 2. 换手率因子
        if target_stock.turnover_rate < 5:
            turnover_factor = 0.05  # 低换手加分
            adjusted_prob += turnover_factor
            factors.append({
                'name': '换手率',
                'value': f'{target_stock.turnover_rate:.1f}%',
                'impact': '+5%（低换手利于连板）'
            })
        elif target_stock.turnover_rate > 15:
            turnover_factor = -0.05  # 高换手减分
            adjusted_prob += turnover_factor
            factors.append({
                'name': '换手率',
                'value': f'{target_stock.turnover_rate:.1f}%',
                'impact': '-5%（高换手风险大）'
            })
        
        # 3. 开板次数因子
        if target_stock.open_count == 0:
            factors.append({
                'name': '开板次数',
                'value': '0次',
                'impact': '+5%（一字板强势）'
            })
            adjusted_prob += 0.05
        elif target_stock.open_count > 2:
            factors.append({
                'name': '开板次数',
                'value': f'{target_stock.open_count}次',
                'impact': '-10%（多次开板弱势）'
            })
            adjusted_prob -= 0.10
        
        # 4. 市值因子
        if target_stock.circulating_value < 50:
            factors.append({
                'name': '流通市值',
                'value': f'{target_stock.circulating_value:.1f}亿',
                'impact': '+5%（小盘股弹性大）'
            })
            adjusted_prob += 0.05
        elif target_stock.circulating_value > 200:
            factors.append({
                'name': '流通市值',
                'value': f'{target_stock.circulating_value:.1f}亿',
                'impact': '-5%（大盘股连板难）'
            })
            adjusted_prob -= 0.05
        
        # 5. 概念热度因子
        if any(concept in target_stock.concept or concept in target_stock.limit_up_reason 
               for concept in self.HOT_CONCEPTS[:10]):
            factors.append({
                'name': '概念热度',
                'value': '热门概念',
                'impact': '+10%（热门题材加持）'
            })
            adjusted_prob += 0.10
        
        # 归一化概率
        adjusted_prob = max(0.05, min(0.80, adjusted_prob))
        
        # 生成预测结论
        if adjusted_prob >= 0.50:
            prediction = "连板概率较高"
            risk_level = "中"
            suggestion = "可关注，但需注意高位风险，建议轻仓参与"
        elif adjusted_prob >= 0.30:
            prediction = "连板概率中等"
            risk_level = "中高"
            suggestion = "谨慎参与，设置好止损位"
        else:
            prediction = "连板概率较低"
            risk_level = "高"
            suggestion = "不建议追高，风险较大"
        
        return ContinuationPrediction(
            stock_code=stock_code,
            stock_name=target_stock.stock_name,
            current_continuous=target_stock.continuous_days,
            continuation_prob=round(adjusted_prob, 2),
            prediction=prediction,
            factors=factors,
            risk_level=risk_level,
            suggestion=suggestion
        )
    
    def get_limit_up_statistics(self, date: str = None) -> Dict:
        """
        获取涨停统计
        
        Args:
            date: 日期
            
        Returns:
            统计数据
        """
        stocks = self.get_daily_limit_up(date)
        
        if not stocks:
            return {
                'total': 0,
                'first_limit': 0,
                'continuous': 0,
                'broken': 0,
                'avg_turnover': 0,
                'hot_concepts': []
            }
        
        first_limit = sum(1 for s in stocks if s.continuous_days == 1)
        continuous = sum(1 for s in stocks if s.continuous_days >= 2)
        broken = sum(1 for s in stocks if s.open_count > 2)
        
        avg_turnover = sum(s.turnover_rate for s in stocks) / len(stocks)
        
        # 统计热门概念
        concept_count = {}
        for s in stocks:
            if s.concept:
                concept_count[s.concept] = concept_count.get(s.concept, 0) + 1
        
        hot_concepts = sorted(concept_count.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'total': len(stocks),
            'first_limit': first_limit,
            'continuous': continuous,
            'broken': broken,
            'avg_turnover': round(avg_turnover, 2),
            'hot_concepts': [{'name': c[0], 'count': c[1]} for c in hot_concepts],
            'max_continuous': max(s.continuous_days for s in stocks) if stocks else 0
        }
    
    def _classify_reason(self, stock: LimitUpStock) -> Tuple[str, float]:
        """分类涨停原因"""
        reason_text = stock.limit_up_reason + stock.concept
        
        # 概念题材
        if any(c in reason_text for c in self.HOT_CONCEPTS):
            return LimitUpReasonType.CONCEPT.value, 0.8
        
        # 业绩驱动
        if any(kw in reason_text for kw in ['业绩', '预增', '盈利', '营收']):
            return LimitUpReasonType.EARNINGS.value, 0.85
        
        # 并购重组
        if any(kw in reason_text for kw in ['并购', '重组', '收购', '借壳']):
            return LimitUpReasonType.MERGER.value, 0.85
        
        # 政策利好
        if any(kw in reason_text for kw in ['政策', '利好', '补贴', '扶持']):
            return LimitUpReasonType.POLICY.value, 0.75
        
        # 机构买入
        if any(kw in reason_text for kw in ['机构', '基金', '龙虎榜']):
            return LimitUpReasonType.INSTITUTION.value, 0.7
        
        return LimitUpReasonType.CONCEPT.value, 0.5
    
    def _extract_concepts(self, stock: LimitUpStock) -> List[str]:
        """提取相关概念"""
        concepts = []
        text = stock.limit_up_reason + stock.concept
        
        for concept in self.HOT_CONCEPTS:
            if concept in text:
                concepts.append(concept)
        
        return concepts[:5]
    
    def _generate_analysis(self, stock: LimitUpStock, reason_type: str) -> str:
        """生成分析说明"""
        analysis = f"{stock.stock_name}今日涨停，"
        
        if stock.continuous_days > 1:
            analysis += f"实现{stock.continuous_days}连板，"
        
        if stock.limit_up_reason:
            analysis += f"涨停原因为{stock.limit_up_reason}。"
        else:
            analysis += f"主要受{reason_type}驱动。"
        
        if stock.open_count == 0:
            analysis += "全天一字板封死，市场情绪强烈。"
        elif stock.open_count > 2:
            analysis += f"盘中开板{stock.open_count}次，封板不牢固。"
        
        if stock.seal_amount > 3:
            analysis += f"封单金额{stock.seal_amount:.1f}亿，封单较强。"
        
        return analysis
    
    @staticmethod
    def _safe_float(value) -> float:
        """安全转换为float"""
        try:
            if pd is not None and pd.isna(value):
                return 0.0
            return float(value) if value else 0.0
        except (ValueError, TypeError):
            return 0.0


# 便捷函数
def get_limit_up_analyzer() -> LimitUpAnalyzer:
    """获取涨停分析器实例"""
    return LimitUpAnalyzer()
