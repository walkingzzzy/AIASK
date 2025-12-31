"""
股票数据索引器
负责将股票数据向量化并存入知识库
"""
import logging
from typing import List, Dict, Optional, TYPE_CHECKING
from datetime import datetime, timedelta
from dataclasses import dataclass

from ..storage.sqlite_vector_store import SQLiteVectorStore, StockDocument, get_vector_store
from ..embeddings.embedding_models import BaseEmbedding, get_embedding_model

if TYPE_CHECKING:
    from ...services.stock_data_service import StockDataService

logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    """索引统计"""
    total_docs: int = 0
    new_docs: int = 0
    updated_docs: int = 0
    failed_docs: int = 0
    execution_time_ms: float = 0


class StockDataIndexer:
    """
    股票数据索引器
    
    功能：
    1. 将股票行情摘要向量化入库
    2. 将财报数据向量化入库
    3. 将新闻资讯向量化入库
    4. 支持增量更新
    """
    
    def __init__(self,
                 vector_store: Optional[SQLiteVectorStore] = None,
                 embedding_model: Optional[BaseEmbedding] = None):
        self.store = vector_store or get_vector_store()
        self.embedding = embedding_model or get_embedding_model()

    def index_stock_summary(self, stock_code: str, stock_name: str,
                            quote_data: Dict, indicators: Dict) -> bool:
        """
        索引股票行情摘要
        
        将实时行情和技术指标转换为自然语言描述后向量化存储
        """
        try:
            content = self._build_quote_summary(stock_code, stock_name, quote_data, indicators)
            
            doc = StockDocument(
                stock_code=stock_code,
                doc_type="quote_summary",
                content=content,
                date=datetime.now().strftime("%Y-%m-%d"),
                period="daily",
                source="system",
                importance=0.7,
                metadata={"stock_name": stock_name}
            )
            
            embedding = self.embedding.embed(content)
            self.store.add_document(doc, embedding)
            
            logger.info(f"索引股票摘要成功: {stock_code}")
            return True
            
        except Exception as e:
            logger.error(f"索引股票摘要失败 {stock_code}: {e}")
            return False
    
    def index_financial_report(self, stock_code: str, stock_name: str,
                                financial_data: Dict, period: str = "quarterly") -> bool:
        """
        索引财报数据
        
        将财务数据转换为结构化描述后向量化存储
        """
        try:
            content = self._build_financial_summary(stock_code, stock_name, financial_data)
            
            doc = StockDocument(
                stock_code=stock_code,
                doc_type="financial_report",
                content=content,
                date=datetime.now().strftime("%Y-%m-%d"),
                period=period,
                source="financial",
                importance=0.8,
                metadata={"stock_name": stock_name, "report_type": period}
            )
            
            embedding = self.embedding.embed(content)
            self.store.add_document(doc, embedding)
            
            logger.info(f"索引财报数据成功: {stock_code}")
            return True
            
        except Exception as e:
            logger.error(f"索引财报数据失败 {stock_code}: {e}")
            return False

    def index_news(self, stock_code: str, stock_name: str,
                   news_list: List[Dict]) -> IndexStats:
        """批量索引新闻资讯"""
        stats = IndexStats()
        start_time = datetime.now()
        
        docs_with_embeddings = []
        
        for news in news_list:
            try:
                content = f"【{news.get('title', '')}】\n{news.get('content', '')}"
                
                doc = StockDocument(
                    stock_code=stock_code,
                    doc_type="news",
                    content=content,
                    date=news.get('date', datetime.now().strftime("%Y-%m-%d")),
                    period="daily",
                    source=news.get('source', 'news'),
                    importance=news.get('importance', 0.5),
                    metadata={"stock_name": stock_name, "title": news.get('title', '')}
                )
                
                embedding = self.embedding.embed(content)
                docs_with_embeddings.append((doc, embedding))
                stats.new_docs += 1
                
            except Exception as e:
                logger.error(f"处理新闻失败: {e}")
                stats.failed_docs += 1
        
        if docs_with_embeddings:
            self.store.add_documents_batch(docs_with_embeddings)
        
        stats.total_docs = len(news_list)
        stats.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        return stats
    
    def index_batch_stocks(self, stock_list: List[Dict],
                           data_service: "StockDataService") -> IndexStats:
        """
        批量索引多只股票
        
        Args:
            stock_list: [{"code": "600519", "name": "贵州茅台"}, ...]
            data_service: StockDataService实例
        """
        stats = IndexStats()
        start_time = datetime.now()
        
        for stock in stock_list:
            code = stock.get("code")
            name = stock.get("name", code)
            
            try:
                quote = data_service.get_realtime_quote(code)
                indicators = data_service.calculate_indicators(code)
                
                if quote and indicators:
                    if self.index_stock_summary(code, name, quote, indicators):
                        stats.new_docs += 1
                    else:
                        stats.failed_docs += 1
                
                financial = data_service.get_financial_data(code)
                if financial:
                    if self.index_financial_report(code, name, financial):
                        stats.new_docs += 1
                    else:
                        stats.failed_docs += 1
                        
            except Exception as e:
                logger.error(f"索引股票 {code} 失败: {e}")
                stats.failed_docs += 1
            
            stats.total_docs += 1
        
        stats.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"批量索引完成: 成功{stats.new_docs}, 失败{stats.failed_docs}")
        
        return stats

    def cleanup_old_documents(self, days: int = 30) -> int:
        """清理过期文档"""
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        deleted = self.store.delete_documents({
            "doc_type": "quote_summary",
            "date_before": cutoff_date
        })
        
        logger.info(f"清理了 {deleted} 条过期文档")
        return deleted
    
    def _build_quote_summary(self, stock_code: str, stock_name: str,
                              quote: Dict, indicators: Dict) -> str:
        """构建行情摘要文本"""
        parts = [f"{stock_name}({stock_code})行情摘要"]
        
        if quote:
            price = quote.get('price', quote.get('close', 'N/A'))
            change = quote.get('change_pct', quote.get('pct_change', 0))
            if isinstance(change, (int, float)):
                change_str = f"+{change:.2f}%" if change > 0 else f"{change:.2f}%"
            else:
                change_str = str(change)
            parts.append(f"当前价格: {price}元, 涨跌幅: {change_str}")
            
            if quote.get('pe'):
                parts.append(f"市盈率PE: {quote['pe']:.2f}")
            if quote.get('pb'):
                parts.append(f"市净率PB: {quote['pb']:.2f}")
        
        if indicators:
            if indicators.get('rsi'):
                rsi = indicators['rsi']
                rsi_status = "超买" if rsi > 70 else "超卖" if rsi < 30 else "中性"
                parts.append(f"RSI指标: {rsi:.1f} ({rsi_status})")
            
            if indicators.get('macd_hist'):
                macd = indicators['macd_hist']
                macd_status = "多头" if macd > 0 else "空头"
                parts.append(f"MACD: {macd_status}")
            
            ma5 = indicators.get('ma5', 0)
            ma20 = indicators.get('ma20', 0)
            if ma5 and ma20:
                trend = "短期强势" if ma5 > ma20 else "短期弱势"
                parts.append(f"均线趋势: {trend}")
        
        return "\n".join(parts)
    
    def _build_financial_summary(self, stock_code: str, stock_name: str,
                                  financial: Dict) -> str:
        """构建财务摘要文本"""
        parts = [f"{stock_name}({stock_code})财务摘要"]
        
        if financial.get('roe'):
            parts.append(f"净资产收益率ROE: {financial['roe']:.2f}%")
        if financial.get('gross_margin'):
            parts.append(f"毛利率: {financial['gross_margin']:.2f}%")
        if financial.get('revenue_growth'):
            parts.append(f"营收增速: {financial['revenue_growth']:.2f}%")
        if financial.get('profit_growth'):
            parts.append(f"利润增速: {financial['profit_growth']:.2f}%")
        if financial.get('pe'):
            parts.append(f"市盈率PE: {financial['pe']:.2f}")
        if financial.get('pb'):
            parts.append(f"市净率PB: {financial['pb']:.2f}")
        
        return "\n".join(parts)


_indexer_instance: Optional[StockDataIndexer] = None


def get_stock_indexer() -> StockDataIndexer:
    """获取索引器单例"""
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = StockDataIndexer()
    return _indexer_instance
