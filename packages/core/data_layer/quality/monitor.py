"""
数据质量监控
实时监控数据质量指标，生成质量报告
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """质量指标"""
    completeness: float = 0.0      # 完整性 (非空比例)
    accuracy: float = 0.0          # 准确性 (通过验证比例)
    timeliness: float = 0.0        # 时效性 (数据新鲜度)
    consistency: float = 0.0       # 一致性 (数据一致性)
    overall_score: float = 0.0     # 综合评分


@dataclass
class QualityAlert:
    """质量告警"""
    level: str              # 'warning' / 'error' / 'critical'
    source: str             # 数据源
    metric: str             # 指标名称
    message: str            # 告警信息
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            'level': self.level,
            'source': self.source,
            'metric': self.metric,
            'message': self.message,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class QualityReport:
    """质量报告"""
    report_time: datetime
    period_start: datetime
    period_end: datetime
    metrics: QualityMetrics
    alerts: List[QualityAlert]
    source_stats: Dict[str, Dict]
    recommendations: List[str]
    
    def to_dict(self) -> Dict:
        return {
            'report_time': self.report_time.isoformat(),
            'period': f"{self.period_start.isoformat()} ~ {self.period_end.isoformat()}",
            'metrics': {
                'completeness': f"{self.metrics.completeness:.1%}",
                'accuracy': f"{self.metrics.accuracy:.1%}",
                'timeliness': f"{self.metrics.timeliness:.1%}",
                'consistency': f"{self.metrics.consistency:.1%}",
                'overall_score': f"{self.metrics.overall_score:.1f}/100"
            },
            'alerts_count': len(self.alerts),
            'alerts': [a.to_dict() for a in self.alerts[:10]],  # 最多10条
            'source_stats': self.source_stats,
            'recommendations': self.recommendations
        }
    
    def summary(self) -> str:
        """生成摘要"""
        return f"""
========== 数据质量报告 ==========
报告时间: {self.report_time.strftime('%Y-%m-%d %H:%M:%S')}
统计周期: {self.period_start.strftime('%Y-%m-%d')} ~ {self.period_end.strftime('%Y-%m-%d')}

【质量指标】
完整性: {self.metrics.completeness:.1%}
准确性: {self.metrics.accuracy:.1%}
时效性: {self.metrics.timeliness:.1%}
一致性: {self.metrics.consistency:.1%}
综合评分: {self.metrics.overall_score:.1f}/100

【告警统计】
告警数量: {len(self.alerts)}
- 严重: {sum(1 for a in self.alerts if a.level == 'critical')}
- 错误: {sum(1 for a in self.alerts if a.level == 'error')}
- 警告: {sum(1 for a in self.alerts if a.level == 'warning')}

【改进建议】
{chr(10).join(f'- {r}' for r in self.recommendations[:5])}
================================
"""


class DataQualityMonitor:
    """数据质量监控器"""
    
    def __init__(self):
        self.stats = defaultdict(lambda: {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'validation_passed': 0,
            'validation_failed': 0,
            'null_values': 0,
            'total_values': 0,
            'last_update': None,
            'response_times': []
        })
        self.alerts: List[QualityAlert] = []
        self.alert_thresholds = {
            'error_rate': 0.1,        # 错误率超过10%告警
            'null_rate': 0.2,         # 空值率超过20%告警
            'staleness_hours': 24,    # 数据超过24小时未更新告警
            'response_time_ms': 5000  # 响应时间超过5秒告警
        }
    
    def record_request(self, source: str, success: bool, 
                       response_time_ms: Optional[float] = None):
        """
        记录数据请求
        
        Args:
            source: 数据源名称
            success: 是否成功
            response_time_ms: 响应时间（毫秒）
        """
        stats = self.stats[source]
        stats['total_requests'] += 1
        
        if success:
            stats['successful_requests'] += 1
            stats['last_update'] = datetime.now()
        else:
            stats['failed_requests'] += 1
        
        if response_time_ms:
            stats['response_times'].append(response_time_ms)
            # 只保留最近100次
            if len(stats['response_times']) > 100:
                stats['response_times'] = stats['response_times'][-100:]
            
            # 检查响应时间
            if response_time_ms > self.alert_thresholds['response_time_ms']:
                self._add_alert('warning', source, 'response_time',
                               f"响应时间过长: {response_time_ms:.0f}ms")
        
        # 检查错误率
        error_rate = stats['failed_requests'] / stats['total_requests']
        if error_rate > self.alert_thresholds['error_rate']:
            self._add_alert('error', source, 'error_rate',
                           f"错误率过高: {error_rate:.1%}")
    
    def record_validation(self, source: str, passed: bool, 
                          null_count: int = 0, total_count: int = 0):
        """
        记录数据验证结果
        
        Args:
            source: 数据源名称
            passed: 是否通过验证
            null_count: 空值数量
            total_count: 总值数量
        """
        stats = self.stats[source]
        
        if passed:
            stats['validation_passed'] += 1
        else:
            stats['validation_failed'] += 1
        
        stats['null_values'] += null_count
        stats['total_values'] += total_count
        
        # 检查空值率
        if total_count > 0:
            null_rate = null_count / total_count
            if null_rate > self.alert_thresholds['null_rate']:
                self._add_alert('warning', source, 'null_rate',
                               f"空值率过高: {null_rate:.1%}")
    
    def _add_alert(self, level: str, source: str, metric: str, message: str):
        """添加告警"""
        alert = QualityAlert(
            level=level,
            source=source,
            metric=metric,
            message=message
        )
        self.alerts.append(alert)
        
        # 只保留最近1000条告警
        if len(self.alerts) > 1000:
            self.alerts = self.alerts[-1000:]
        
        # 记录日志
        if level == 'critical':
            logger.error(f"[{source}] {message}")
        elif level == 'error':
            logger.warning(f"[{source}] {message}")
        else:
            logger.info(f"[{source}] {message}")
    
    def calculate_metrics(self, source: Optional[str] = None) -> QualityMetrics:
        """
        计算质量指标
        
        Args:
            source: 数据源名称，None表示全部
            
        Returns:
            质量指标
        """
        if source:
            sources = [source] if source in self.stats else []
        else:
            sources = list(self.stats.keys())
        
        if not sources:
            return QualityMetrics()
        
        total_requests = 0
        successful_requests = 0
        validation_passed = 0
        validation_total = 0
        null_values = 0
        total_values = 0
        stale_sources = 0
        
        now = datetime.now()
        
        for src in sources:
            s = self.stats[src]
            total_requests += s['total_requests']
            successful_requests += s['successful_requests']
            validation_passed += s['validation_passed']
            validation_total += s['validation_passed'] + s['validation_failed']
            null_values += s['null_values']
            total_values += s['total_values']
            
            # 检查数据新鲜度
            if s['last_update']:
                hours_since_update = (now - s['last_update']).total_seconds() / 3600
                if hours_since_update > self.alert_thresholds['staleness_hours']:
                    stale_sources += 1
        
        # 计算各项指标
        completeness = 1 - (null_values / total_values) if total_values > 0 else 1.0
        accuracy = validation_passed / validation_total if validation_total > 0 else 1.0
        timeliness = 1 - (stale_sources / len(sources)) if sources else 1.0
        consistency = successful_requests / total_requests if total_requests > 0 else 1.0
        
        # 综合评分 (加权平均)
        overall = (
            completeness * 25 +
            accuracy * 30 +
            timeliness * 25 +
            consistency * 20
        )
        
        return QualityMetrics(
            completeness=completeness,
            accuracy=accuracy,
            timeliness=timeliness,
            consistency=consistency,
            overall_score=overall
        )
    
    def generate_report(self, hours: int = 24) -> QualityReport:
        """
        生成质量报告
        
        Args:
            hours: 统计时间范围（小时）
            
        Returns:
            质量报告
        """
        now = datetime.now()
        period_start = now - timedelta(hours=hours)
        
        # 计算指标
        metrics = self.calculate_metrics()
        
        # 筛选时间范围内的告警
        recent_alerts = [
            a for a in self.alerts 
            if a.timestamp >= period_start
        ]
        
        # 数据源统计
        source_stats = {}
        for source, stats in self.stats.items():
            total = stats['total_requests']
            if total > 0:
                source_stats[source] = {
                    'total_requests': total,
                    'success_rate': f"{stats['successful_requests']/total:.1%}",
                    'validation_rate': f"{stats['validation_passed']/(stats['validation_passed']+stats['validation_failed']):.1%}" if (stats['validation_passed']+stats['validation_failed']) > 0 else 'N/A',
                    'avg_response_time': f"{sum(stats['response_times'])/len(stats['response_times']):.0f}ms" if stats['response_times'] else 'N/A',
                    'last_update': stats['last_update'].isoformat() if stats['last_update'] else 'Never'
                }
        
        # 生成建议
        recommendations = self._generate_recommendations(metrics, recent_alerts)
        
        return QualityReport(
            report_time=now,
            period_start=period_start,
            period_end=now,
            metrics=metrics,
            alerts=recent_alerts,
            source_stats=source_stats,
            recommendations=recommendations
        )
    
    def _generate_recommendations(self, metrics: QualityMetrics, 
                                   alerts: List[QualityAlert]) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        if metrics.completeness < 0.9:
            recommendations.append("数据完整性不足，建议检查数据源配置和网络连接")
        
        if metrics.accuracy < 0.95:
            recommendations.append("数据准确性需要提升，建议加强数据验证规则")
        
        if metrics.timeliness < 0.9:
            recommendations.append("部分数据源更新不及时，建议检查数据同步任务")
        
        if metrics.consistency < 0.95:
            recommendations.append("数据一致性有问题，建议检查多数据源的数据对齐")
        
        # 根据告警生成建议
        error_sources = set(a.source for a in alerts if a.level in ['error', 'critical'])
        if error_sources:
            recommendations.append(f"以下数据源需要重点关注: {', '.join(error_sources)}")
        
        if not recommendations:
            recommendations.append("数据质量良好，继续保持")
        
        return recommendations
    
    def get_alerts(self, level: Optional[str] = None, 
                   source: Optional[str] = None,
                   limit: int = 100) -> List[QualityAlert]:
        """
        获取告警列表
        
        Args:
            level: 告警级别过滤
            source: 数据源过滤
            limit: 返回数量限制
            
        Returns:
            告警列表
        """
        alerts = self.alerts
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        if source:
            alerts = [a for a in alerts if a.source == source]
        
        return alerts[-limit:]
    
    def clear_alerts(self):
        """清除所有告警"""
        self.alerts = []
    
    def reset_stats(self):
        """重置统计数据"""
        self.stats.clear()
        self.alerts = []


# 全局单例
_monitor_instance: Optional[DataQualityMonitor] = None


def get_monitor() -> DataQualityMonitor:
    """获取监控器单例"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = DataQualityMonitor()
    return _monitor_instance
