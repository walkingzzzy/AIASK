"""
研报爬取器
从公开数据源获取研报信息
"""
import uuid
import logging
from typing import List, Optional
from datetime import datetime
from .models import ResearchReport, ReportType, Rating

logger = logging.getLogger(__name__)


class ReportCrawler:
    """研报爬取器"""

    def __init__(self):
        self.has_akshare = False
        try:
            import akshare as ak
            self.ak = ak
            self.has_akshare = True
        except ImportError:
            logger.warning("akshare未安装，研报爬取功能不可用")

    def fetch_stock_reports(self, stock_code: str, limit: int = 20) -> List[ResearchReport]:
        """
        获取个股研报

        Args:
            stock_code: 股票代码
            limit: 数量限制

        Returns:
            研报列表
        """
        if not self.has_akshare:
            return []

        reports = []
        try:
            # 使用 akshare 获取个股研报
            # 注意：akshare 的研报接口可能需要调整
            df = self.ak.stock_research_report_em(symbol=stock_code)

            if df is not None and not df.empty:
                for idx, row in df.head(limit).iterrows():
                    report = ResearchReport(
                        report_id=str(uuid.uuid4()),
                        title=row.get('标题', ''),
                        institution=row.get('机构名称', '未知机构'),
                        analyst=row.get('研究员', ''),
                        publish_date=self._parse_date(row.get('发布日期')),
                        report_type=self._parse_report_type(row.get('研报类型', '')),
                        stock_code=stock_code,
                        stock_name=row.get('股票名称', ''),
                        rating=self._parse_rating(row.get('投资评级', '')),
                        summary=row.get('摘要', ''),
                        url=row.get('研报链接', '')
                    )
                    reports.append(report)

            logger.info(f"获取{stock_code}研报{len(reports)}条")

        except Exception as e:
            logger.error(f"获取研报失败: {e}")

        return reports

    def fetch_industry_reports(self, limit: int = 20) -> List[ResearchReport]:
        """
        获取行业研报

        Args:
            limit: 数量限制

        Returns:
            研报列表
        """
        # 预留接口，可以后续实现
        return []

    def _parse_date(self, date_str) -> datetime:
        """解析日期"""
        if isinstance(date_str, datetime):
            return date_str

        try:
            return datetime.strptime(str(date_str), '%Y-%m-%d')
        except ValueError as e:
            logger.warning(f"日期解析失败 '{date_str}': {e}，使用当前时间")
            return datetime.now()

    def _parse_report_type(self, type_str: str) -> ReportType:
        """解析研报类型"""
        type_str = str(type_str).lower()
        if '公司' in type_str or '个股' in type_str:
            return ReportType.COMPANY
        elif '行业' in type_str:
            return ReportType.INDUSTRY
        elif '策略' in type_str:
            return ReportType.STRATEGY
        else:
            return ReportType.COMPANY

    def _parse_rating(self, rating_str: str) -> Optional[Rating]:
        """解析评级"""
        rating_str = str(rating_str).lower()
        if '买入' in rating_str or '增持' in rating_str:
            return Rating.BUY
        elif '持有' in rating_str or '中性' in rating_str:
            return Rating.HOLD
        elif '卖出' in rating_str or '减持' in rating_str:
            return Rating.SELL
        return None
