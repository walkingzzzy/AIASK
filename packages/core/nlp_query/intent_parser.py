"""
意图解析器
解析用户自然语言查询的意图
"""
import re
import os
import json
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class IntentType(Enum):
    """意图类型"""
    STOCK_SCREENING = "stock_screening"    # 股票筛选
    STOCK_ANALYSIS = "stock_analysis"      # 个股分析
    DATA_QUERY = "data_query"              # 数据查询
    UNKNOWN = "unknown"


@dataclass
class QueryIntent:
    """查询意图"""
    intent_type: IntentType
    confidence: float
    entities: Dict[str, Any]      # 提取的实体
    original_query: str
    normalized_query: str
    
    def to_dict(self) -> Dict:
        return {
            "intent_type": self.intent_type.value,
            "confidence": self.confidence,
            "entities": self.entities,
            "original_query": self.original_query,
            "normalized_query": self.normalized_query
        }


# 全局股票名称缓存
_stock_name_cache: Dict[str, str] = {}
_stock_name_cache_lock = threading.Lock()
_stock_name_cache_loaded = False


def _load_stock_name_cache() -> Dict[str, str]:
    """
    加载完整的股票名称到代码映射
    使用AKShare获取全部A股股票信息，带缓存机制
    """
    global _stock_name_cache, _stock_name_cache_loaded
    
    if _stock_name_cache_loaded:
        return _stock_name_cache
    
    with _stock_name_cache_lock:
        # 双重检查
        if _stock_name_cache_loaded:
            return _stock_name_cache
        
        # 常见股票的默认映射（作为基础数据）
        default_mapping = {
            '茅台': '600519',
            '贵州茅台': '600519',
            '平安': '601318',
            '中国平安': '601318',
            '招商银行': '600036',
            '招行': '600036',
            '宁德时代': '300750',
            '比亚迪': '002594',
            '五粮液': '000858',
            '格力': '000651',
            '格力电器': '000651',
            '美的': '000333',
            '美的集团': '000333',
            '恒瑞医药': '600276',
            '药明康德': '603259',
            '隆基': '601012',
            '隆基绿能': '601012',
        }
        
        _stock_name_cache.update(default_mapping)
        
        # 尝试从缓存文件加载
        cache_file = Path(__file__).parent.parent.parent.parent / "data" / "stock_name_cache.json"
        try:
            if cache_file.exists():
                import time
                # 检查缓存是否过期（7天）
                file_mtime = cache_file.stat().st_mtime
                if time.time() - file_mtime < 7 * 24 * 3600:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                        _stock_name_cache.update(cached_data)
                        logger.info(f"从缓存加载股票名称映射，共 {len(_stock_name_cache)} 条")
                        _stock_name_cache_loaded = True
                        return _stock_name_cache
        except Exception as e:
            logger.warning(f"加载股票名称缓存失败: {e}")
        
        # 尝试从AKShare获取完整股票列表
        try:
            import akshare as ak
            
            # 获取A股股票列表
            df = ak.stock_info_a_code_name()
            
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    code = str(row.get('code', '')).zfill(6)
                    name = str(row.get('name', ''))
                    if code and name:
                        # 添加完整名称映射
                        _stock_name_cache[name] = code
                        # 添加简称映射（去掉常见后缀）
                        for suffix in ['股份', 'A', 'B', '-U', '-W']:
                            if name.endswith(suffix):
                                short_name = name[:-len(suffix)]
                                if short_name and short_name not in _stock_name_cache:
                                    _stock_name_cache[short_name] = code
                
                logger.info(f"从AKShare加载股票名称映射，共 {len(_stock_name_cache)} 条")
                
                # 保存到缓存文件
                try:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(_stock_name_cache, f, ensure_ascii=False, indent=2)
                    logger.info("股票名称映射已保存到缓存")
                except Exception as e:
                    logger.warning(f"保存股票名称缓存失败: {e}")
                    
        except ImportError:
            logger.warning("AKShare未安装，使用默认股票名称映射")
        except Exception as e:
            logger.warning(f"从AKShare获取股票列表失败: {e}，使用默认映射")
        
        _stock_name_cache_loaded = True
        return _stock_name_cache


class IntentParser:
    """
    意图解析器
    
    支持的意图类型：
    1. stock_screening - 股票筛选
       例：找出PE低于20的股票、筛选ROE大于15%的股票
       
    2. stock_analysis - 个股分析
       例：分析贵州茅台、600519怎么样
       
    3. data_query - 数据查询
       例：茅台的PE是多少、平安银行今天涨了多少
    """
    
    # 股票代码正则
    STOCK_CODE_PATTERN = r'[036]\d{5}'
    
    # 筛选关键词
    SCREENING_KEYWORDS = [
        '筛选', '找出', '选出', '哪些股票', '推荐', '有哪些',
        '低于', '高于', '大于', '小于', '超过', '不超过',
        '排名', '前十', '前20', 'top', '最高', '最低'
    ]
    
    # 分析关键词
    ANALYSIS_KEYWORDS = [
        '分析', '怎么样', '如何', '评价', '看法', '建议',
        '能买吗', '可以买吗', '值得买吗', '还能涨吗'
    ]
    
    # 查询关键词
    QUERY_KEYWORDS = [
        '是多少', '多少钱', '价格', '涨跌', '涨幅', '跌幅',
        '市值', 'PE', 'PB', 'ROE', '营收', '利润', '股价'
    ]
    
    # 指标映射
    METRIC_MAPPING = {
        'pe': ['pe', 'pe值', '市盈率', 'p/e'],
        'pb': ['pb', 'pb值', '市净率', 'p/b'],
        'roe': ['roe', '净资产收益率'],
        'revenue_growth': ['营收增速', '营收增长', '收入增速'],
        'profit_growth': ['利润增速', '利润增长', '净利润增速'],
        'market_cap': ['市值', '总市值'],
        'price': ['股价', '价格', '现价'],
        'change_pct': ['涨跌幅', '涨幅', '跌幅', '涨了', '跌了'],
        'volume': ['成交量', '成交额'],
        'ai_score': ['ai评分', '评分', '得分']
    }
    
    def __init__(self):
        """初始化意图解析器，加载股票名称映射"""
        # 动态加载完整股票名称映射
        self._stock_name_mapping = _load_stock_name_cache()
    
    @property
    def STOCK_NAME_MAPPING(self) -> Dict[str, str]:
        """获取股票名称映射（兼容旧代码）"""
        return self._stock_name_mapping
    
    # 比较运算符映射
    OPERATOR_MAPPING = {
        '大于': '>',
        '高于': '>',
        '超过': '>',
        '>': '>',
        '>=': '>=',
        '不低于': '>=',
        '小于': '<',
        '低于': '<',
        '不超过': '<=',
        '<': '<',
        '<=': '<=',
        '等于': '==',
        '=': '=='
    }
    
    def parse(self, query: str) -> QueryIntent:
        """
        解析用户查询
        
        Args:
            query: 用户输入的自然语言查询
            
        Returns:
            QueryIntent
        """
        # 预处理
        normalized = self._normalize_query(query)
        
        # 提取实体
        entities = self._extract_entities(normalized)
        
        # 判断意图
        intent_type, confidence = self._classify_intent(normalized, entities)
        
        # 根据意图类型补充实体
        if intent_type == IntentType.STOCK_SCREENING:
            entities = self._extract_screening_conditions(normalized, entities)
        elif intent_type == IntentType.STOCK_ANALYSIS:
            entities = self._extract_analysis_params(normalized, entities)
        elif intent_type == IntentType.DATA_QUERY:
            entities = self._extract_query_params(normalized, entities)
        
        return QueryIntent(
            intent_type=intent_type,
            confidence=confidence,
            entities=entities,
            original_query=query,
            normalized_query=normalized
        )
    
    def _normalize_query(self, query: str) -> str:
        """标准化查询"""
        # 转小写
        normalized = query.lower()
        # 全角转半角
        normalized = self._full_to_half(normalized)
        # 去除多余空格
        normalized = ' '.join(normalized.split())
        return normalized
    
    def _full_to_half(self, text: str) -> str:
        """全角转半角"""
        result = []
        for char in text:
            code = ord(char)
            if code == 0x3000:  # 全角空格
                code = 0x0020
            elif 0xFF01 <= code <= 0xFF5E:  # 全角字符
                code -= 0xFEE0
            result.append(chr(code))
        return ''.join(result)
    
    def _extract_entities(self, query: str) -> Dict[str, Any]:
        """提取实体"""
        entities = {}
        
        # 提取股票代码
        codes = re.findall(self.STOCK_CODE_PATTERN, query)
        if codes:
            entities['stock_codes'] = codes
        
        # 提取股票名称
        for name, code in self.STOCK_NAME_MAPPING.items():
            if name in query:
                if 'stock_codes' not in entities:
                    entities['stock_codes'] = []
                if code not in entities['stock_codes']:
                    entities['stock_codes'].append(code)
                entities['stock_name'] = name
        
        # 提取数值
        numbers = re.findall(r'(\d+(?:\.\d+)?)\s*[%％]?', query)
        if numbers:
            entities['numbers'] = [float(n) for n in numbers]
        
        # 提取指标
        for metric, keywords in self.METRIC_MAPPING.items():
            for kw in keywords:
                if kw in query:
                    entities['metric'] = metric
                    break
        
        return entities
    
    def _classify_intent(self, query: str, 
                         entities: Dict) -> Tuple[IntentType, float]:
        """分类意图"""
        scores = {
            IntentType.STOCK_SCREENING: 0.0,
            IntentType.STOCK_ANALYSIS: 0.0,
            IntentType.DATA_QUERY: 0.0
        }
        
        # 基于关键词评分
        for kw in self.SCREENING_KEYWORDS:
            if kw in query:
                scores[IntentType.STOCK_SCREENING] += 1.0
        
        for kw in self.ANALYSIS_KEYWORDS:
            if kw in query:
                scores[IntentType.STOCK_ANALYSIS] += 1.0
        
        for kw in self.QUERY_KEYWORDS:
            if kw in query:
                scores[IntentType.DATA_QUERY] += 1.0
        
        # 基于实体调整
        if entities.get('stock_codes'):
            # 有具体股票代码，更可能是分析或查询
            scores[IntentType.STOCK_ANALYSIS] += 0.5
            scores[IntentType.DATA_QUERY] += 0.5
        
        if entities.get('numbers') and any(op in query for op in self.OPERATOR_MAPPING):
            # 有数值和比较运算符，更可能是筛选
            scores[IntentType.STOCK_SCREENING] += 1.0
        
        # 选择最高分
        max_intent = max(scores, key=scores.get)
        max_score = scores[max_intent]
        
        if max_score == 0:
            return IntentType.UNKNOWN, 0.0
        
        # 计算置信度
        total = sum(scores.values())
        confidence = max_score / total if total > 0 else 0.0
        
        return max_intent, min(confidence, 1.0)
    
    def _extract_screening_conditions(self, query: str, 
                                       entities: Dict) -> Dict:
        """提取筛选条件"""
        conditions = []
        
        # 解析条件表达式
        for metric, keywords in self.METRIC_MAPPING.items():
            for kw in keywords:
                if kw not in query:
                    continue
                
                # 查找运算符和数值
                for op_text, op_symbol in self.OPERATOR_MAPPING.items():
                    pattern = f'{kw}\\s*{re.escape(op_text)}\\s*(\\d+(?:\\.\\d+)?)'
                    match = re.search(pattern, query)
                    if match:
                        conditions.append({
                            'metric': metric,
                            'operator': op_symbol,
                            'value': float(match.group(1))
                        })
                        break
        
        # 处理排名类查询
        if '前' in query or 'top' in query:
            match = re.search(r'前\s*(\d+)|top\s*(\d+)', query)
            if match:
                limit = int(match.group(1) or match.group(2))
                entities['limit'] = limit
                entities['sort_order'] = 'desc'
        
        entities['conditions'] = conditions
        return entities
    
    def _extract_analysis_params(self, query: str, entities: Dict) -> Dict:
        """提取分析参数"""
        # 分析类型
        if '技术' in query:
            entities['analysis_type'] = 'technical'
        elif '基本面' in query or '财务' in query:
            entities['analysis_type'] = 'fundamental'
        elif '资金' in query:
            entities['analysis_type'] = 'fund_flow'
        else:
            entities['analysis_type'] = 'comprehensive'
        
        # 时间范围
        if '短期' in query or '近期' in query:
            entities['time_range'] = 'short'
        elif '中期' in query:
            entities['time_range'] = 'medium'
        elif '长期' in query:
            entities['time_range'] = 'long'
        
        return entities
    
    def _extract_query_params(self, query: str, entities: Dict) -> Dict:
        """提取查询参数"""
        # 时间相关
        if '今天' in query or '今日' in query:
            entities['time'] = 'today'
        elif '昨天' in query or '昨日' in query:
            entities['time'] = 'yesterday'
        elif '本周' in query:
            entities['time'] = 'this_week'
        elif '本月' in query:
            entities['time'] = 'this_month'
        
        return entities


def parse_query(query: str) -> QueryIntent:
    """便捷函数：解析查询"""
    parser = IntentParser()
    return parser.parse(query)
