"""
板块轮动分析工具
追踪行业板块轮动、资金流向和相对强弱
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

try:
    import akshare as ak
    import pandas as pd
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None
    pd = None


class SectorRotationAnalyzer:
    """板块轮动分析器"""
    
    def __init__(self):
        if not HAS_AKSHARE:
            raise ImportError("akshare is required for SectorRotationAnalyzer")
    
    def get_sector_list(self) -> List[Dict[str, Any]]:
        """获取行业板块列表"""
        try:
            df = ak.stock_board_industry_name_em()
            sectors = []
            for _, row in df.head(50).iterrows():
                sectors.append({
                    'name': row.get('板块名称', ''),
                    'code': row.get('板块代码', ''),
                    'stock_count': row.get('上涨家数', 0) + row.get('下跌家数', 0),
                })
            return sectors
        except Exception as e:
            return [{'error': str(e)}]
    
    def get_sector_realtime(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """获取板块实时行情"""
        try:
            df = ak.stock_board_industry_name_em()
            results = []
            for _, row in df.head(top_n).iterrows():
                results.append({
                    'name': row.get('板块名称', ''),
                    'change_pct': row.get('涨跌幅', 0),
                    'turnover': row.get('换手率', 0),
                    'amount': row.get('成交额', 0),
                    'leading_stock': row.get('领涨股票', ''),
                    'leading_change': row.get('领涨股票-涨跌幅', 0),
                    'up_count': row.get('上涨家数', 0),
                    'down_count': row.get('下跌家数', 0),
                })
            return results
        except Exception as e:
            return [{'error': str(e)}]
    
    def get_sector_fund_flow(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """获取板块资金流向"""
        try:
            df = ak.stock_sector_fund_flow_rank(indicator="今日")
            results = []
            for _, row in df.head(top_n).iterrows():
                results.append({
                    'name': row.get('名称', ''),
                    'change_pct': row.get('今日涨跌幅', 0),
                    'main_net_inflow': row.get('主力净流入-净额', 0),
                    'main_net_pct': row.get('主力净流入-净占比', 0),
                    'super_large_net': row.get('超大单净流入-净额', 0),
                    'large_net': row.get('大单净流入-净额', 0),
                    'medium_net': row.get('中单净流入-净额', 0),
                    'small_net': row.get('小单净流入-净额', 0),
                })
            return results
        except Exception as e:
            return [{'error': str(e)}]
    
    def get_sector_history(self, sector_name: str, days: int = 30) -> List[Dict[str, Any]]:
        """获取板块历史行情"""
        try:
            df = ak.stock_board_industry_hist_em(
                symbol=sector_name,
                period="日k",
                adjust="qfq"
            )
            if df is None or df.empty:
                return [{'error': f'未找到板块 {sector_name} 的历史数据'}]
            
            df = df.tail(days)
            results = []
            for _, row in df.iterrows():
                results.append({
                    'date': str(row.get('日期', '')),
                    'open': row.get('开盘', 0),
                    'high': row.get('最高', 0),
                    'low': row.get('最低', 0),
                    'close': row.get('收盘', 0),
                    'volume': row.get('成交量', 0),
                    'amount': row.get('成交额', 0),
                    'change_pct': row.get('涨跌幅', 0),
                })
            return results
        except Exception as e:
            return [{'error': str(e)}]
    
    def get_sector_stocks(self, sector_name: str, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取板块成分股"""
        try:
            df = ak.stock_board_industry_cons_em(symbol=sector_name)
            if df is None or df.empty:
                return [{'error': f'未找到板块 {sector_name} 的成分股'}]
            
            results = []
            for _, row in df.head(top_n).iterrows():
                results.append({
                    'code': row.get('代码', ''),
                    'name': row.get('名称', ''),
                    'price': row.get('最新价', 0),
                    'change_pct': row.get('涨跌幅', 0),
                    'turnover': row.get('换手率', 0),
                    'pe': row.get('市盈率-动态', 0),
                    'amount': row.get('成交额', 0),
                })
            return results
        except Exception as e:
            return [{'error': str(e)}]
    
    def analyze_rotation(self, days: int = 5) -> Dict[str, Any]:
        """分析板块轮动趋势"""
        try:
            # 获取今日板块行情
            today_df = ak.stock_board_industry_name_em()
            if today_df is None or today_df.empty:
                return {'error': '无法获取板块数据'}
            
            # 按涨跌幅排序
            today_df = today_df.sort_values('涨跌幅', ascending=False)
            
            # 领涨板块
            top_sectors = []
            for _, row in today_df.head(5).iterrows():
                top_sectors.append({
                    'name': row.get('板块名称', ''),
                    'change_pct': row.get('涨跌幅', 0),
                    'leading_stock': row.get('领涨股票', ''),
                })
            
            # 领跌板块
            bottom_sectors = []
            for _, row in today_df.tail(5).iterrows():
                bottom_sectors.append({
                    'name': row.get('板块名称', ''),
                    'change_pct': row.get('涨跌幅', 0),
                })
            
            # 资金流向分析
            fund_flow = self.get_sector_fund_flow(10)
            
            # 计算市场广度
            up_count = today_df[today_df['涨跌幅'] > 0].shape[0]
            down_count = today_df[today_df['涨跌幅'] < 0].shape[0]
            total = today_df.shape[0]
            
            return {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'top_sectors': top_sectors,
                'bottom_sectors': bottom_sectors,
                'fund_flow_top': fund_flow[:5] if fund_flow else [],
                'market_breadth': {
                    'up_sectors': up_count,
                    'down_sectors': down_count,
                    'total_sectors': total,
                    'up_ratio': round(up_count / total * 100, 2) if total > 0 else 0,
                },
                'rotation_signal': self._calc_rotation_signal(top_sectors, fund_flow),
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _calc_rotation_signal(self, top_sectors: List[Dict], fund_flow: List[Dict]) -> str:
        """计算轮动信号"""
        if not top_sectors:
            return '数据不足'
        
        # 简单判断：领涨板块涨幅和资金流入情况
        avg_change = sum(s.get('change_pct', 0) for s in top_sectors) / len(top_sectors)
        
        if avg_change > 3:
            return '强势轮动，市场活跃'
        elif avg_change > 1:
            return '温和轮动，结构性行情'
        elif avg_change > 0:
            return '弱势轮动，观望为主'
        else:
            return '板块普跌，防御为主'
    
    def get_stock_sector(self, stock_code: str) -> Dict[str, Any]:
        """获取个股所属板块"""
        try:
            # 尝试获取个股所属行业
            df = ak.stock_individual_info_em(symbol=stock_code)
            if df is None or df.empty:
                return {'error': f'未找到股票 {stock_code} 的信息'}
            
            info = {}
            for _, row in df.iterrows():
                item = row.get('item', '')
                value = row.get('value', '')
                if '行业' in item:
                    info['industry'] = value
                elif '板块' in item:
                    info['sector'] = value
            
            return {
                'stock_code': stock_code,
                'industry': info.get('industry', '未知'),
                'sector': info.get('sector', '未知'),
            }
        except Exception as e:
            return {'error': str(e)}


# ===== CrewAI Tools =====

class SectorRealtimeInput(BaseModel):
    top_n: int = Field(default=20, description="返回板块数量")


class SectorRealtimeTool(BaseTool):
    name: str = "sector_realtime"
    description: str = "获取行业板块实时行情，包括涨跌幅、换手率、领涨股等"
    args_schema: type[BaseModel] = SectorRealtimeInput
    
    def _run(self, top_n: int = 20) -> str:
        if not HAS_AKSHARE:
            return "错误：akshare未安装"
        
        analyzer = SectorRotationAnalyzer()
        data = analyzer.get_sector_realtime(top_n)
        
        if data and 'error' in data[0]:
            return f"获取失败：{data[0]['error']}"
        
        lines = ["=== 行业板块实时行情 ===\n"]
        for i, s in enumerate(data, 1):
            lines.append(f"{i}. {s['name']}")
            lines.append(f"   涨跌幅: {s['change_pct']:.2f}%  换手率: {s['turnover']:.2f}%")
            lines.append(f"   领涨股: {s['leading_stock']} ({s['leading_change']:.2f}%)")
            lines.append(f"   涨/跌: {s['up_count']}/{s['down_count']}\n")
        
        return '\n'.join(lines)


class SectorFundFlowInput(BaseModel):
    top_n: int = Field(default=20, description="返回板块数量")


class SectorFundFlowTool(BaseTool):
    name: str = "sector_fund_flow"
    description: str = "获取行业板块资金流向，包括主力净流入、大单净流入等"
    args_schema: type[BaseModel] = SectorFundFlowInput
    
    def _run(self, top_n: int = 20) -> str:
        if not HAS_AKSHARE:
            return "错误：akshare未安装"
        
        analyzer = SectorRotationAnalyzer()
        data = analyzer.get_sector_fund_flow(top_n)
        
        if data and 'error' in data[0]:
            return f"获取失败：{data[0]['error']}"
        
        lines = ["=== 板块资金流向 ===\n"]
        for i, s in enumerate(data, 1):
            main_net = s['main_net_inflow']
            main_net_str = f"{main_net/1e8:.2f}亿" if abs(main_net) >= 1e8 else f"{main_net/1e4:.0f}万"
            lines.append(f"{i}. {s['name']}")
            lines.append(f"   涨跌幅: {s['change_pct']:.2f}%")
            lines.append(f"   主力净流入: {main_net_str} ({s['main_net_pct']:.2f}%)\n")
        
        return '\n'.join(lines)


class SectorRotationInput(BaseModel):
    days: int = Field(default=5, description="分析天数")


class SectorRotationTool(BaseTool):
    name: str = "sector_rotation"
    description: str = "分析板块轮动趋势，包括领涨/领跌板块、资金流向、轮动信号"
    args_schema: type[BaseModel] = SectorRotationInput
    
    def _run(self, days: int = 5) -> str:
        if not HAS_AKSHARE:
            return "错误：akshare未安装"
        
        analyzer = SectorRotationAnalyzer()
        data = analyzer.analyze_rotation(days)
        
        if 'error' in data:
            return f"分析失败：{data['error']}"
        
        lines = [f"=== 板块轮动分析 ({data['date']}) ===\n"]
        
        lines.append("【领涨板块】")
        for s in data['top_sectors']:
            lines.append(f"  • {s['name']}: {s['change_pct']:.2f}% (领涨: {s['leading_stock']})")
        
        lines.append("\n【领跌板块】")
        for s in data['bottom_sectors']:
            lines.append(f"  • {s['name']}: {s['change_pct']:.2f}%")
        
        lines.append("\n【资金流入TOP5】")
        for s in data['fund_flow_top']:
            if 'error' not in s:
                lines.append(f"  • {s.get('name', 'N/A')}")
        
        mb = data['market_breadth']
        lines.append(f"\n【市场广度】")
        lines.append(f"  上涨板块: {mb['up_sectors']} / 下跌板块: {mb['down_sectors']}")
        lines.append(f"  上涨比例: {mb['up_ratio']}%")
        
        lines.append(f"\n【轮动信号】{data['rotation_signal']}")
        
        return '\n'.join(lines)


class SectorStocksInput(BaseModel):
    sector_name: str = Field(description="板块名称")
    top_n: int = Field(default=10, description="返回股票数量")


class SectorStocksTool(BaseTool):
    name: str = "sector_stocks"
    description: str = "获取指定板块的成分股列表"
    args_schema: type[BaseModel] = SectorStocksInput
    
    def _run(self, sector_name: str, top_n: int = 10) -> str:
        if not HAS_AKSHARE:
            return "错误：akshare未安装"
        
        analyzer = SectorRotationAnalyzer()
        data = analyzer.get_sector_stocks(sector_name, top_n)
        
        if data and 'error' in data[0]:
            return f"获取失败：{data[0]['error']}"
        
        lines = [f"=== {sector_name} 成分股 ===\n"]
        for i, s in enumerate(data, 1):
            lines.append(f"{i}. {s['name']}({s['code']})")
            lines.append(f"   价格: {s['price']}  涨跌幅: {s['change_pct']:.2f}%")
            lines.append(f"   换手率: {s['turnover']:.2f}%  PE: {s['pe']}\n")
        
        return '\n'.join(lines)
