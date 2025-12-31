"""
研报管理器
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .models import ResearchReport, ReportSummary, ReportType, Rating

logger = logging.getLogger(__name__)


class ReportManager:
    """研报管理器"""

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            data_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "research_reports"
            data_dir.mkdir(parents=True, exist_ok=True)
            storage_path = str(data_dir)

        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.reports_file = self.storage_path / "reports.json"
        self.reports: List[ResearchReport] = []
        self._initialized = False
        self._load_reports()

    def _load_reports(self):
        """从文件加载研报，如果文件不存在则自动初始化"""
        try:
            if self.reports_file.exists():
                with open(self.reports_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.reports = []
                    for item in data:
                        report = ResearchReport(
                            report_id=item['report_id'],
                            title=item['title'],
                            institution=item['institution'],
                            analyst=item['analyst'],
                            publish_date=datetime.fromisoformat(item['publish_date']),
                            report_type=ReportType(item['report_type']),
                            stock_code=item.get('stock_code'),
                            stock_name=item.get('stock_name'),
                            rating=Rating(item['rating']) if item.get('rating') else None,
                            target_price=item.get('target_price'),
                            summary=item.get('summary', ''),
                            content=item.get('content', ''),
                            url=item.get('url'),
                            tags=item.get('tags', [])
                        )
                        self.reports.append(report)
                logger.info(f"加载研报数据成功，共{len(self.reports)}条")
                self._initialized = True
            else:
                # 文件不存在，尝试自动初始化
                logger.info("研报数据文件不存在，尝试自动初始化...")
                self._auto_initialize()
        except Exception as e:
            logger.error(f"加载研报数据失败: {e}")
            self.reports = []
            # 创建空文件以避免重复报错
            self._create_empty_file()
    
    def _auto_initialize(self):
        """自动初始化研报数据"""
        try:
            # 尝试从外部数据源获取初始数据
            count = self.fetch_and_update()
            if count > 0:
                logger.info(f"自动初始化成功，获取 {count} 条研报")
                self._initialized = True
            else:
                # 无法获取外部数据，创建空文件
                logger.warning("无法从外部数据源获取研报，创建空的初始文件")
                self._create_empty_file()
        except Exception as e:
            logger.warning(f"自动初始化失败: {e}，创建空的初始文件")
            self._create_empty_file()
    
    def _create_empty_file(self):
        """创建空的研报JSON文件"""
        try:
            with open(self.reports_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False)
            self.reports = []
            self._initialized = True
            logger.info("已创建空的研报数据文件")
        except Exception as e:
            logger.error(f"创建空研报文件失败: {e}")

    def _save_reports(self):
        """保存研报到文件"""
        try:
            data = []
            for report in self.reports:
                item = {
                    'report_id': report.report_id,
                    'title': report.title,
                    'institution': report.institution,
                    'analyst': report.analyst,
                    'publish_date': report.publish_date.isoformat(),
                    'report_type': report.report_type.value,
                    'stock_code': report.stock_code,
                    'stock_name': report.stock_name,
                    'rating': report.rating.value if report.rating else None,
                    'target_price': report.target_price,
                    'summary': report.summary,
                    'content': report.content,
                    'url': report.url,
                    'tags': report.tags
                }
                data.append(item)

            with open(self.reports_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("保存研报数据成功")
        except Exception as e:
            logger.error(f"保存研报数据失败: {e}")

    def add_report(self, report: ResearchReport) -> bool:
        """添加研报"""
        self.reports.append(report)
        self._save_reports()
        return True

    def add_reports_batch(self, reports: List[ResearchReport]) -> int:
        """批量添加研报"""
        count = 0
        for report in reports:
            # 检查是否已存在
            if not any(r.report_id == report.report_id for r in self.reports):
                self.reports.append(report)
                count += 1
        if count > 0:
            self._save_reports()
        return count

    def fetch_and_update(self, stock_code: Optional[str] = None) -> int:
        """
        从数据源获取并更新研报

        Args:
            stock_code: 股票代码，如果为None则获取行业研报

        Returns:
            新增研报数量
        """
        try:
            from .report_crawler import ReportCrawler

            crawler = ReportCrawler()
            if stock_code:
                new_reports = crawler.fetch_stock_reports(stock_code)
            else:
                new_reports = crawler.fetch_industry_reports()

            return self.add_reports_batch(new_reports)

        except Exception as e:
            logger.error(f"获取研报失败: {e}")
            return 0

    def get_report_by_id(self, report_id: str) -> Optional[ResearchReport]:
        """根据ID获取研报"""
        for report in self.reports:
            if report.report_id == report_id:
                return report
        return None

    def search_reports(
        self,
        keyword: Optional[str] = None,
        stock_code: Optional[str] = None,
        report_type: Optional[ReportType] = None,
        institution: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 20
    ) -> List[ResearchReport]:
        """
        搜索研报

        Args:
            keyword: 关键词
            stock_code: 股票代码
            report_type: 研报类型
            institution: 机构名称
            start_date: 开始日期
            end_date: 结束日期
            limit: 返回数量限制

        Returns:
            研报列表
        """
        results = self.reports.copy()

        # 按股票代码筛选
        if stock_code:
            results = [r for r in results if r.stock_code == stock_code]

        # 按类型筛选
        if report_type:
            results = [r for r in results if r.report_type == report_type]

        # 按机构筛选
        if institution:
            results = [r for r in results if institution.lower() in r.institution.lower()]

        # 按日期筛选
        if start_date:
            results = [r for r in results if r.publish_date >= start_date]
        if end_date:
            results = [r for r in results if r.publish_date <= end_date]

        # 按关键词筛选
        if keyword:
            keyword_lower = keyword.lower()
            results = [
                r for r in results
                if keyword_lower in r.title.lower() or keyword_lower in r.summary.lower()
            ]

        # 按日期排序（最新的在前）
        results.sort(key=lambda x: x.publish_date, reverse=True)

        return results[:limit]

    def get_recent_reports(self, days: int = 7, limit: int = 20) -> List[ResearchReport]:
        """获取最近的研报"""
        cutoff_date = datetime.now() - timedelta(days=days)
        return self.search_reports(start_date=cutoff_date, limit=limit)

    def get_stock_reports(self, stock_code: str, limit: int = 10) -> List[ResearchReport]:
        """获取个股研报"""
        return self.search_reports(stock_code=stock_code, limit=limit)

    def get_summary(self) -> ReportSummary:
        """获取研报摘要统计"""
        by_type = {}
        by_rating = {}

        for report in self.reports:
            # 按类型统计
            report_type = report.report_type.value
            by_type[report_type] = by_type.get(report_type, 0) + 1

            # 按评级统计
            if report.rating:
                rating = report.rating.value
                by_rating[rating] = by_rating.get(rating, 0) + 1

        # 获取最近研报
        recent_reports = self.get_recent_reports(days=7, limit=10)

        # 统计热门股票
        stock_counts = {}
        for report in self.reports:
            if report.stock_code:
                key = (report.stock_code, report.stock_name or report.stock_code)
                stock_counts[key] = stock_counts.get(key, 0) + 1

        hot_stocks = [
            {"stock_code": code, "stock_name": name, "report_count": count}
            for (code, name), count in sorted(stock_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        return ReportSummary(
            total_count=len(self.reports),
            by_type=by_type,
            by_rating=by_rating,
            recent_reports=recent_reports,
            hot_stocks=hot_stocks
        )
