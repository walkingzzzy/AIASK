"""
竞价监控报告生成器
提供文字摘要、HTML报告、Excel导出等功能
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MonitorReporter:
    """
    监控报告生成器
    提供多种格式的报告生成功能：
    - 文字摘要
    - HTML报告
    - Excel导出
    """
    
    def __init__(self):
        """初始化报告生成器"""
        self._report_title = "竞价监控报告"
    def generate_summary(self, monitor_data: Dict[str, Any]) -> str:
        """
        生成文字摘要
        
        Args:
            monitor_data: 监控数据，包含stocks、alerts等信息
            
        Returns:
            文字摘要字符串
        """
        try:
            timestamp = monitor_data.get('timestamp', datetime.now().isoformat())
            is_auction_time = monitor_data.get('is_auction_time', False)
            stocks = monitor_data.get('stocks', {})
            total_count = monitor_data.get('total_count', len(stocks))
            abnormal_count = monitor_data.get('abnormal_count', 0)
            
            # 构建摘要
            lines = []
            lines.append("=" * 50)
            lines.append(f"【{self._report_title}】")
            lines.append(f"生成时间: {timestamp}")
            lines.append(f"竞价时段: {'是' if is_auction_time else '否'}")
            lines.append("=" * 50)
            lines.append("")
            
            # 基本统计
            lines.append("【基本统计】")
            lines.append(f"  监控股票数: {total_count}")
            lines.append(f"  异动股票数: {abnormal_count}")
            lines.append("")
            
            #涨跌分布
            if stocks:
                up_count = sum(1 for s in stocks.values() if s.get('auction_change', 0) > 0)
                down_count = sum(1 for s in stocks.values() if s.get('auction_change', 0) < 0)
                flat_count = total_count - up_count - down_count
                
                lines.append("【涨跌分布】")
                lines.append(f"  上涨: {up_count} 只({up_count/total_count*100:.1f}%)")
                lines.append(f"  下跌: {down_count} 只 ({down_count/total_count*100:.1f}%)")
                lines.append(f"  平盘: {flat_count} 只 ({flat_count/total_count*100:.1f}%)")
                lines.append("")
            
            # 涨幅榜
            if stocks:
                sorted_stocks = sorted(
                    stocks.values(),
                    key=lambda x: x.get('auction_change', 0),
                    reverse=True
                )
                
                lines.append("【竞价涨幅榜 TOP10】")
                for i, stock in enumerate(sorted_stocks[:10], 1):
                    code = stock.get('stock_code', '')
                    name = stock.get('stock_name', '')
                    change = stock.get('auction_change', 0)
                    lines.append(f"  {i:2}. {code} {name:8s} {change:+.2f}%")
                lines.append("")
                lines.append("【竞价跌幅榜 TOP10】")
                for i, stock in enumerate(reversed(sorted_stocks[-10:]), 1):
                    code = stock.get('stock_code', '')
                    name = stock.get('stock_name', '')
                    change = stock.get('auction_change', 0)
                    lines.append(f"  {i:2}. {code} {name:8s} {change:+.2f}%")
                lines.append("")
            
            # 异动股票
            abnormal_stocks = [s for s in stocks.values() if s.get('is_abnormal', False)]
            if abnormal_stocks:
                lines.append("【异动股票】")
                for stock in abnormal_stocks[:20]:
                    code = stock.get('stock_code', '')
                    name = stock.get('stock_name', '')
                    change = stock.get('auction_change', 0)
                    reasons = stock.get('abnormal_reason', [])
                    reason_str = ', '.join(reasons) if reasons else '未知'
                    lines.append(f"  {code} {name}: {change:+.2f}% - {reason_str}")
                lines.append("")
            
            # 预警信息
            alerts = monitor_data.get('alerts', [])
            if alerts:
                lines.append("【预警信息】")
                for alert in alerts[:20]:
                    if isinstance(alert, dict):
                        alert_type = alert.get('alert_type', '')
                        stock_code = alert.get('stock_code', '')
                        stock_name = alert.get('stock_name', '')
                        message = alert.get('message', '')
                        priority = alert.get('priority', 1)
                    else:
                        alert_type = getattr(alert, 'alert_type', '')
                        stock_code = getattr(alert, 'stock_code', '')
                        stock_name = getattr(alert, 'stock_name', '')
                        message = getattr(alert, 'message', '')
                        priority = getattr(alert, 'priority', 1)
                    priority_mark = "!" * priority
                    lines.append(f"  [{alert_type}]{priority_mark} {stock_code} {stock_name}: {message}")
                lines.append("")
            
            lines.append("=" * 50)
            lines.append("报告结束")
            lines.append("=" * 50)
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}", exc_info=True)
            return f"生成摘要失败: {e}"
    
    def generate_html_report(self, monitor_data: Dict[str, Any]) -> str:
        """
        生成HTML报告
        
        Args:
            monitor_data: 监控数据
            
        Returns:
            HTML字符串
        """
        try:
            timestamp = monitor_data.get('timestamp', datetime.now().isoformat())
            is_auction_time = monitor_data.get('is_auction_time', False)
            stocks = monitor_data.get('stocks', {})
            total_count = monitor_data.get('total_count', len(stocks))
            abnormal_count = monitor_data.get('abnormal_count', 0)
            alerts = monitor_data.get('alerts', [])
            
            # 涨跌统计
            up_count = sum(1 for s in stocks.values() if s.get('auction_change', 0) > 0)
            down_count = sum(1 for s in stocks.values() if s.get('auction_change', 0) < 0)
            
            # 排序股票
            sorted_stocks = sorted(
                stocks.values(),
                key=lambda x: x.get('auction_change', 0),
                reverse=True
            )
            
            html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self._report_title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Microsoft YaHei','PingFang SC', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 2px solid #4a4a6a;
            margin-bottom: 30px;
        }}
        .header h1 {{
            font-size: 2.5em;
            color: #ffd700;
            margin-bottom: 10px;
        }}
        .header .timestamp {{
            color: #888;
            font-size: 0.9em;
        }}
        .header .status {{
            margin-top: 10px;
            padding: 5px 15px;
            border-radius: 20px;
            display: inline-block;
            font-weight: bold;
        }}
        .status.active {{
            background: #27ae60;
            color: white;
        }}
        .status.inactive {{
            background: #7f8c8d;
            color: white;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .stat-card .value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #ffd700;
        }}
        .stat-card .label {{
            color: #888;
            margin-top: 5px;
        }}
        .stat-card.up .value {{ color: #e74c3c; }}
        .stat-card.down .value {{ color: #27ae60; }}
        .section {{
            background: rgba(255,255,255,0.03);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;border: 1px solid rgba(255,255,255,0.1);
        }}
        .section h2 {{
            color: #ffd700;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        th {{
            background: rgba(255,215,0,0.1);
            color: #ffd700;
            font-weight: bold;
        }}
        tr:hover {{
            background: rgba(255,255,255,0.05);
        }}
        .change-up {{ color: #e74c3c; font-weight: bold; }}
        .change-down {{ color: #27ae60; font-weight: bold; }}
        .change-flat {{ color: #888; }}
        .alert-item {{
            padding: 10px 15px;
            margin: 5px 0;
            border-radius: 5px;
            border-left: 4px solid;
        }}
        .alert-priority-5 {{ border-color: #e74c3c; background: rgba(231,76,60,0.1); }}
        .alert-priority-4 {{ border-color: #e67e22; background: rgba(230,126,34,0.1); }}
        .alert-priority-3 {{ border-color: #f1c40f; background: rgba(241,196,15,0.1); }}
        .alert-priority-2 {{ border-color: #3498db; background: rgba(52,152,219,0.1); }}
        .alert-priority-1 {{ border-color: #95a5a6; background: rgba(149,165,166,0.1); }}
        .alert-type {{
            font-weight: bold;
            margin-right: 10px;
        }}
        .abnormal-tag {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.8em;
            background: #e74c3c;
            color: white;
            margin-left: 5px;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 {self._report_title}</h1>
            <div class="timestamp">生成时间: {timestamp}</div>
            <div class="status {'active' if is_auction_time else 'inactive'}">
                {'🟢 竞价时段' if is_auction_time else '⚪ 非竞价时段'}
            </div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value">{total_count}</div>
                <div class="label">监控股票数</div>
            </div>
            <div class="stat-card">
                <div class="value">{abnormal_count}</div>
                <div class="label">异动股票数</div>
            </div>
            <div class="stat-card up">
                <div class="value">{up_count}</div>
                <div class="label">上涨股票</div>
            </div>
            <div class="stat-card down">
                <div class="value">{down_count}</div>
                <div class="label">下跌股票</div>
            </div></div>
"""
            
            # 预警信息
            if alerts:
                html += """<div class="section">
            <h2>⚠️ 预警信息</h2>
"""
                for alert in alerts[:20]:
                    if isinstance(alert, dict):
                        alert_type = alert.get('alert_type', '')
                        stock_code = alert.get('stock_code', '')
                        stock_name = alert.get('stock_name', '')
                        message = alert.get('message', '')
                        priority = alert.get('priority', 1)
                    else:
                        alert_type = getattr(alert, 'alert_type', '')
                        stock_code = getattr(alert, 'stock_code', '')
                        stock_name = getattr(alert, 'stock_name', '')
                        message = getattr(alert, 'message', '')
                        priority = getattr(alert, 'priority', 1)
                    html += f"""
            <div class="alert-item alert-priority-{priority}">
                <span class="alert-type">[{alert_type}]</span>
                <strong>{stock_code}</strong> {stock_name}: {message}
            </div>
"""
                html += """</div>
"""
            
            # 涨幅榜
            html += """
        <div class="section">
            <h2>🔥 竞价涨幅榜 TOP20</h2>
            <table>
                <thead>
                    <tr>
                        <th>排名</th>
                        <th>代码</th>
                        <th>名称</th>
                        <th>竞价涨幅</th>
                        <th>量比</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody>
"""
            for i, stock in enumerate(sorted_stocks[:20], 1):
                code = stock.get('stock_code', '')
                name = stock.get('stock_name', '')
                change = stock.get('auction_change', 0)
                volume_ratio = stock.get('volume_ratio', 1.0)
                is_abnormal = stock.get('is_abnormal', False)
                
                change_class = 'change-up' if change > 0 else ('change-down' if change < 0 else 'change-flat')
                abnormal_tag = '<span class="abnormal-tag">异动</span>' if is_abnormal else ''
                
                html += f"""
                    <tr>
                        <td>{i}</td>
                        <td>{code}</td>
                        <td>{name}{abnormal_tag}</td>
                        <td class="{change_class}">{change:+.2f}%</td>
                        <td>{volume_ratio:.2f}</td>
                        <td>{'异动' if is_abnormal else '正常'}</td>
                    </tr>
"""
            html += """
                </tbody>
            </table>
        </div>
"""
            
            # 跌幅榜
            html += """
        <div class="section">
            <h2>📉 竞价跌幅榜 TOP20</h2>
            <table>
                <thead>
                    <tr>
                        <th>排名</th>
                        <th>代码</th>
                        <th>名称</th>
                        <th>竞价跌幅</th>
                        <th>量比</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody>
"""
            for i, stock in enumerate(reversed(sorted_stocks[-20:]), 1):
                code = stock.get('stock_code', '')
                name = stock.get('stock_name', '')
                change = stock.get('auction_change', 0)
                volume_ratio = stock.get('volume_ratio', 1.0)
                is_abnormal = stock.get('is_abnormal', False)
                
                change_class = 'change-up' if change > 0 else ('change-down' if change < 0 else 'change-flat')
                abnormal_tag = '<span class="abnormal-tag">异动</span>' if is_abnormal else ''
                
                html += f"""
                    <tr>
                        <td>{i}</td>
                        <td>{code}</td>
                        <td>{name}{abnormal_tag}</td>
                        <td class="{change_class}">{change:+.2f}%</td>
                        <td>{volume_ratio:.2f}</td>
                        <td>{'异动' if is_abnormal else '正常'}</td>
                    </tr>
"""
            
            html += """
                </tbody>
            </table>
        </div>
        <div class="footer">
            <p>© 竞价监控系统 - 数据仅供参考，不构成投资建议</p>
        </div>
    </div>
</body>
</html>
"""
            return html
        except Exception as e:
            logger.error(f"Error generating HTML report: {e}", exc_info=True)
            return f"<html><body>生成报告失败: {e}</body></html>"
    
    def export_to_excel(self, monitor_data: Dict[str, Any], filepath: str) -> None:
        """
        导出Excel报告
        
        Args:
            monitor_data: 监控数据
            filepath: 导出文件路径
            Raises:
            ImportError: 如果未安装pandas或openpyxl
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required for Excel export. Install with: pip install pandas openpyxl")
        
        try:
            stocks = monitor_data.get('stocks', {})
            alerts = monitor_data.get('alerts', [])
            
            # 准备股票数据
            stocks_data = []
            for stock in stocks.values():
                stocks_data.append({
                    '股票代码': stock.get('stock_code', ''),
                    '股票名称': stock.get('stock_name', ''),
                    '竞价价格': stock.get('auction_price', 0),
                    '竞价涨幅(%)': stock.get('auction_change', 0),
                    '竞价成交量': stock.get('auction_volume', 0),
                    '量比': stock.get('volume_ratio', 1.0),
                    '买入量': stock.get('buy_volume', 0),
                    '卖出量': stock.get('sell_volume', 0),
                    '净流入': stock.get('net_inflow', 0),
                    '是否异动': '是' if stock.get('is_abnormal', False) else '否',
                    '异动原因': ', '.join(stock.get('abnormal_reason', [])),
                })
            
            # 创建股票DataFrame
            df_stocks = pd.DataFrame(stocks_data)
            if not df_stocks.empty:
                df_stocks = df_stocks.sort_values('竞价涨幅(%)', ascending=False)
            # 准备预警数据
            alerts_data = []
            for alert in alerts:
                if isinstance(alert, dict):
                    alerts_data.append({
                        '预警类型': alert.get('alert_type', ''),
                        '股票代码': alert.get('stock_code', ''),
                        '股票名称': alert.get('stock_name', ''),
                        '预警信息': alert.get('message', ''),
                        '优先级': alert.get('priority', 1),
                        '时间': alert.get('timestamp', ''),
                    })
                else:
                    alerts_data.append({
                        '预警类型': getattr(alert, 'alert_type', ''),
                        '股票代码': getattr(alert, 'stock_code', ''),
                        '股票名称': getattr(alert, 'stock_name', ''),
                        '预警信息': getattr(alert, 'message', ''),
                        '优先级': getattr(alert, 'priority', 1),
                        '时间': getattr(alert, 'timestamp', datetime.now()).isoformat() if hasattr(alert, 'timestamp') else '',
                    })
            
            df_alerts = pd.DataFrame(alerts_data)
            
            # 准备摘要数据
            timestamp = monitor_data.get('timestamp', datetime.now().isoformat())
            is_auction_time = monitor_data.get('is_auction_time', False)
            total_count = monitor_data.get('total_count', len(stocks))
            abnormal_count = monitor_data.get('abnormal_count', 0)
            
            summary_data = {
                '指标': ['报告时间', '竞价时段', '监控股票数', '异动股票数', '预警数量'],
                '值': [timestamp, '是' if is_auction_time else '否', total_count, abnormal_count, len(alerts)]
            }
            df_summary = pd.DataFrame(summary_data)
            
            # 写入Excel
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                df_summary.to_excel(writer, sheet_name='摘要', index=False)
                df_stocks.to_excel(writer, sheet_name='股票数据', index=False)
                if not df_alerts.empty:
                    df_alerts.to_excel(writer, sheet_name='预警信息', index=False)
            
            logger.info(f"Excel report exported to: {filepath}")
            
        except Exception as e:
            logger.error(f"Error exporting to Excel: {e}", exc_info=True)
            raise
    
    def generate_alert_summary(self, alerts: List[Any]) -> str:
        """
        生成预警摘要
        
        Args:
            alerts: 预警列表
            
        Returns:
            预警摘要字符串
        """
        if not alerts:
            return "暂无预警信息"
        
        lines = []
        lines.append(f"共有 {len(alerts)} 条预警：")
        lines.append("")
        
        # 按优先级分组
        priority_groups: Dict[int, List[Any]] = {}
        for alert in alerts:
            if isinstance(alert, dict):
                priority = alert.get('priority', 1)
            else:
                priority = getattr(alert, 'priority', 1)
            
            if priority not in priority_groups:
                priority_groups[priority] = []
            priority_groups[priority].append(alert)
        
        priority_names = {5: '紧急', 4: '重要', 3: '一般', 2: '提示', 1: '信息'}
        
        for priority in sorted(priority_groups.keys(), reverse=True):
            alerts_in_group = priority_groups[priority]
            lines.append(f"【{priority_names.get(priority, '其他')}级别】({len(alerts_in_group)}条)")
            for alert in alerts_in_group[:10]:
                if isinstance(alert, dict):
                    alert_type = alert.get('alert_type', '')
                    stock_code = alert.get('stock_code', '')
                    stock_name = alert.get('stock_name', '')
                    message = alert.get('message', '')
                else:
                    alert_type = getattr(alert, 'alert_type', '')
                    stock_code = getattr(alert, 'stock_code', '')
                    stock_name = getattr(alert, 'stock_name', '')
                    message = getattr(alert, 'message', '')
                
                lines.append(f"  - [{alert_type}] {stock_code} {stock_name}: {message}")
            
            if len(alerts_in_group) > 10:
                lines.append(f"  ... 及其他 {len(alerts_in_group) - 10} 条")
            lines.append("")
        
        return "\n".join(lines)
    
    def generate_quick_stats(self, monitor_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成快速统计数据
        
        Args:
            monitor_data: 监控数据
            
        Returns:
            统计数据字典
        """
        stocks = monitor_data.get('stocks', {})
        alerts = monitor_data.get('alerts', [])
        
        if not stocks:
            return {
                'total_count': 0,
                'up_count': 0,
                'down_count': 0,
                'flat_count': 0,
                'abnormal_count': 0,
                'alerts_count': len(alerts),
                'avg_change': 0,
                'max_change': 0,
                'min_change': 0,}
        
        changes = [s.get('auction_change', 0) for s in stocks.values()]
        
        return {
            'total_count': len(stocks),
            'up_count': sum(1 for c in changes if c > 0),
            'down_count': sum(1 for c in changes if c < 0),
            'flat_count': sum(1 for c in changes if c == 0),
            'abnormal_count': sum(1 for s in stocks.values() if s.get('is_abnormal', False)),
            'alerts_count': len(alerts),
            'avg_change': sum(changes) / len(changes) if changes else 0,
            'max_change': max(changes) if changes else 0,
            'min_change': min(changes) if changes else 0,
        }