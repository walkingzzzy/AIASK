"""
研报分析器
"""
from typing import List, Dict, Any, Optional
from collections import Counter
from .models import ResearchReport, Rating


class ReportAnalyzer:
    """研报分析器"""

    def analyze_stock_consensus(self, reports: List[ResearchReport]) -> Dict[str, Any]:
        """
        分析个股研报一致性

        Args:
            reports: 研报列表

        Returns:
            一致性分析结果
        """
        if not reports:
            return {
                "consensus_rating": "无数据",
                "rating_distribution": {},
                "avg_target_price": None,
                "report_count": 0
            }

        # 评级分布
        ratings = [r.rating for r in reports if r.rating]
        rating_counts = Counter([r.value for r in ratings])

        # 目标价统计
        target_prices = [r.target_price for r in reports if r.target_price]
        avg_target_price = sum(target_prices) / len(target_prices) if target_prices else None

        # 一致性评级（众数）
        consensus_rating = "无评级"
        if rating_counts:
            consensus_rating = rating_counts.most_common(1)[0][0]

        return {
            "consensus_rating": consensus_rating,
            "rating_distribution": dict(rating_counts),
            "avg_target_price": avg_target_price,
            "target_price_range": {
                "min": min(target_prices) if target_prices else None,
                "max": max(target_prices) if target_prices else None
            },
            "report_count": len(reports)
        }

    def extract_key_points(self, report: ResearchReport) -> List[str]:
        """
        提取研报要点

        Args:
            report: 研报

        Returns:
            要点列表
        """
        # TODO: 实现NLP提取关键信息
        key_points = []

        if report.rating:
            key_points.append(f"评级: {report.rating.value}")

        if report.target_price:
            key_points.append(f"目标价: {report.target_price}元")

        if report.summary:
            # 简单提取摘要前200字
            summary_preview = report.summary[:200]
            key_points.append(f"摘要: {summary_preview}...")

        return key_points

    def compare_institutions(self, reports: List[ResearchReport]) -> Dict[str, Any]:
        """
        对比不同机构观点

        Args:
            reports: 研报列表

        Returns:
            机构对比结果
        """
        institution_views = {}

        for report in reports:
            inst = report.institution
            if inst not in institution_views:
                institution_views[inst] = {
                    "institution": inst,
                    "report_count": 0,
                    "ratings": [],
                    "latest_report": None
                }

            institution_views[inst]["report_count"] += 1
            if report.rating:
                institution_views[inst]["ratings"].append(report.rating.value)

            # 更新最新研报
            if (institution_views[inst]["latest_report"] is None or
                report.publish_date > institution_views[inst]["latest_report"].publish_date):
                institution_views[inst]["latest_report"] = report

        # 转换为列表
        result = []
        for inst_data in institution_views.values():
            latest = inst_data["latest_report"]
            result.append({
                "institution": inst_data["institution"],
                "report_count": inst_data["report_count"],
                "latest_rating": latest.rating.value if latest and latest.rating else None,
                "latest_date": latest.publish_date.isoformat() if latest else None,
                "latest_title": latest.title if latest else None
            })

        return {
            "institution_count": len(result),
            "institutions": result
        }
