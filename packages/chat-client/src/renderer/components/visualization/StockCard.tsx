/**
 * 股票卡片
 */

import React from 'react';

interface StockCardProps {
    title?: string;
    data: unknown;
}

const StockCard: React.FC<StockCardProps> = ({ title, data }) => {
    if (!data || typeof data !== 'object') {
        return null;
    }

    const quote = data as {
        code?: string;
        name?: string;
        price?: number;
        change?: number;
        changePercent?: number;
        open?: number;
        high?: number;
        low?: number;
        volume?: number;
        amount?: number;
        sector?: string;
        industry?: string;
        source?: string;
        warning?: string;
    };

    const changeValue = Number(quote.change ?? 0);
    const changePercent = Number(quote.changePercent ?? 0);
    const hasChange = Number.isFinite(changeValue) && Number.isFinite(changePercent);
    const isUp = hasChange ? changeValue >= 0 : true;
    const changeText = hasChange ? `${isUp ? '+' : ''}${changeValue.toFixed(2)}` : '--';
    const percentText = hasChange ? `${isUp ? '+' : ''}${changePercent.toFixed(2)}%` : '--';

    return (
        <div className="visualization stock-card">
            {title && <div className="visualization-title">{title}</div>}
            <div className="stock-card-header">
                <div className="stock-name">
                    <strong>{quote.name || '--'}</strong>
                    <span className="stock-code">{quote.code || '--'}</span>
                </div>
                {quote.sector && (
                    <span className="stock-sector">{quote.sector}</span>
                )}
            </div>
            <div className="stock-card-body">
                <div className="stock-price">
                    <span className="price">{quote.price ?? '--'}</span>
                    <span className={`change ${isUp ? 'up' : 'down'}`}>
                        {changeText} ({percentText})
                    </span>
                </div>
                <div className="stock-metrics">
                    <div>
                        <span>开盘</span>
                        <strong>{quote.open ?? '--'}</strong>
                    </div>
                    <div>
                        <span>最高</span>
                        <strong>{quote.high ?? '--'}</strong>
                    </div>
                    <div>
                        <span>最低</span>
                        <strong>{quote.low ?? '--'}</strong>
                    </div>
                </div>
                {quote.warning && (
                    <div className="stock-warning">{quote.warning}</div>
                )}
                {quote.source && (
                    <div className="stock-source">数据来源: {quote.source}</div>
                )}
            </div>
        </div>
    );
};

export default StockCard;
