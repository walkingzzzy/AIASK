"""
股票数据库
提供全A股股票代码和名称映射
"""
import logging
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

logger = logging.getLogger(__name__)


class StockDatabase:
    """
    股票数据库

    提供股票代码和名称的双向映射
    支持模糊匹配和简称匹配
    """

    def __init__(self):
        """初始化股票数据库"""
        self._code_to_name: Dict[str, str] = {}
        self._name_to_code: Dict[str, str] = {}
        self._loaded = False

    def load_from_akshare(self) -> bool:
        """
        从AKShare加载全A股股票列表

        Returns:
            bool: 是否加载成功
        """
        try:
            import akshare as ak

            # 获取A股列表
            logger.info("正在从AKShare加载A股列表...")

            # 获取沪深A股列表
            stock_list = []

            try:
                # 沪市A股
                sh_stocks = ak.stock_info_a_code_name()
                if sh_stocks is not None and not sh_stocks.empty:
                    stock_list.append(sh_stocks)
                    logger.info(f"加载沪深A股: {len(sh_stocks)}只")
            except Exception as e:
                logger.warning(f"加载沪深A股失败: {e}")

            if not stock_list:
                logger.warning("无法从AKShare加载股票列表，使用内置数据")
                return self._load_builtin_stocks()

            # 合并数据
            import pandas as pd
            all_stocks = pd.concat(stock_list, ignore_index=True)

            # 构建映射
            for _, row in all_stocks.iterrows():
                code = str(row['code'])
                name = str(row['name'])

                self._code_to_name[code] = name
                self._name_to_code[name] = code

                # 添加简称映射（去除"股份"、"集团"等后缀）
                short_name = self._get_short_name(name)
                if short_name != name and short_name not in self._name_to_code:
                    self._name_to_code[short_name] = code

            self._loaded = True
            logger.info(f"成功加载{len(self._code_to_name)}只A股")
            return True

        except ImportError:
            logger.error("AKShare未安装，无法加载股票列表")
            return self._load_builtin_stocks()
        except Exception as e:
            logger.error(f"从AKShare加载股票列表失败: {e}")
            return self._load_builtin_stocks()

    def _load_builtin_stocks(self) -> bool:
        """
        加载内置股票列表（常见股票）

        Returns:
            bool: 是否加载成功
        """
        builtin_stocks = {
            '600519': '贵州茅台',
            '000858': '五粮液',
            '601318': '中国平安',
            '600036': '招商银行',
            '300750': '宁德时代',
            '002594': '比亚迪',
            '000651': '格力电器',
            '000333': '美的集团',
            '600276': '恒瑞医药',
            '603259': '药明康德',
            '601012': '隆基绿能',
            '600887': '伊利股份',
            '000568': '泸州老窖',
            '600809': '山西汾酒',
            '002475': '立讯精密',
            '002415': '海康威视',
            '000002': '万科A',
            '600030': '中信证券',
            '601166': '兴业银行',
            '601288': '农业银行',
        }

        for code, name in builtin_stocks.items():
            self._code_to_name[code] = name
            self._name_to_code[name] = code

            # 添加简称
            short_name = self._get_short_name(name)
            if short_name != name and short_name not in self._name_to_code:
                self._name_to_code[short_name] = code

        self._loaded = True
        logger.info(f"加载内置股票列表: {len(self._code_to_name)}只")
        return True

    def _get_short_name(self, name: str) -> str:
        """
        获取股票简称

        Args:
            name: 股票全称

        Returns:
            str: 简称
        """
        # 移除常见后缀
        suffixes = ['股份有限公司', '有限公司', '股份', '集团', 'A', 'B']
        short = name
        for suffix in suffixes:
            short = short.replace(suffix, '')
        return short.strip()

    @lru_cache(maxsize=1000)
    def get_name_by_code(self, code: str) -> Optional[str]:
        """
        根据股票代码获取名称

        Args:
            code: 股票代码

        Returns:
            Optional[str]: 股票名称，未找到返回None
        """
        if not self._loaded:
            self.load_from_akshare()

        return self._code_to_name.get(code)

    @lru_cache(maxsize=1000)
    def get_code_by_name(self, name: str) -> Optional[str]:
        """
        根据股票名称获取代码

        Args:
            name: 股票名称

        Returns:
            Optional[str]: 股票代码，未找到返回None
        """
        if not self._loaded:
            self.load_from_akshare()

        # 精确匹配
        if name in self._name_to_code:
            return self._name_to_code[name]

        # 模糊匹配
        return self._fuzzy_match_name(name)

    def _fuzzy_match_name(self, name: str) -> Optional[str]:
        """
        模糊匹配股票名称

        Args:
            name: 股票名称

        Returns:
            Optional[str]: 股票代码，未找到返回None
        """
        name_lower = name.lower()

        # 尝试包含匹配
        for stock_name, code in self._name_to_code.items():
            if name_lower in stock_name.lower() or stock_name.lower() in name_lower:
                return code

        return None

    def search_stocks(self, keyword: str, limit: int = 10) -> List[Tuple[str, str]]:
        """
        搜索股票

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            List[Tuple[str, str]]: [(代码, 名称), ...]
        """
        if not self._loaded:
            self.load_from_akshare()

        keyword_lower = keyword.lower()
        results = []

        for code, name in self._code_to_name.items():
            # 代码匹配
            if keyword in code:
                results.append((code, name))
                continue

            # 名称匹配
            if keyword_lower in name.lower():
                results.append((code, name))

            if len(results) >= limit:
                break

        return results

    def get_all_stocks(self) -> Dict[str, str]:
        """
        获取所有股票

        Returns:
            Dict[str, str]: {代码: 名称}
        """
        if not self._loaded:
            self.load_from_akshare()

        return self._code_to_name.copy()

    def is_valid_code(self, code: str) -> bool:
        """
        检查是否为有效的股票代码

        Args:
            code: 股票代码

        Returns:
            bool: 是否有效
        """
        if not self._loaded:
            self.load_from_akshare()

        return code in self._code_to_name


# 全局单例
_stock_db_instance: Optional[StockDatabase] = None


def get_stock_database() -> StockDatabase:
    """
    获取股票数据库单例

    Returns:
        StockDatabase: 股票数据库实例
    """
    global _stock_db_instance
    if _stock_db_instance is None:
        _stock_db_instance = StockDatabase()
        _stock_db_instance.load_from_akshare()
    return _stock_db_instance
