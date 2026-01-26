/**
 * 持仓可视化面板
 */

import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface PortfolioPanelProps {
    title?: string;
    data: unknown;
}

type Position = {
    code: string;
    name?: string;
    quantity?: number;
    costPrice?: number;
    currentPrice?: number;
    marketValue?: number;
    profit?: number;
    profitPercent?: string;
};

type PortfolioData = {
    positions?: Position[];
    totalMarketValue?: number;
    totalProfit?: number;
};

const PortfolioPanel: React.FC<PortfolioPanelProps> = ({ title, data }) => {
    const pieRef = useRef<HTMLDivElement>(null);
    const barRef = useRef<HTMLDivElement>(null);

    const payload = (data && typeof data === 'object' ? data : {}) as PortfolioData;
    const positions = payload.positions || [];

    useEffect(() => {
        if (!pieRef.current || !barRef.current) return;

        const pieChart = echarts.init(pieRef.current);
        const barChart = echarts.init(barRef.current);

        if (positions.length === 0) {
            pieChart.setOption({ title: { text: '暂无持仓', left: 'center', top: 'center' } });
            barChart.setOption({ title: { text: '' } });
            return () => {
                pieChart.dispose();
                barChart.dispose();
            };
        }

        const pieData = positions.map(pos => ({
            name: `${pos.name || pos.code}`,
            value: pos.marketValue || 0,
        }));

        pieChart.setOption({
            title: { text: '' },
            tooltip: { trigger: 'item' },
            legend: { bottom: 0, textStyle: { fontSize: 11 } },
            series: [
                {
                    type: 'pie',
                    radius: ['30%', '70%'],
                    center: ['50%', '45%'],
                    data: pieData,
                    label: { formatter: '{b}: {d}%' },
                },
            ],
        });

        const categories = positions.map(pos => pos.name || pos.code);
        const profits = positions.map(pos => pos.profit || 0);

        barChart.setOption({
            title: { text: '' },
            grid: { left: 20, right: 20, top: 20, bottom: 30 },
            xAxis: { type: 'category', data: categories },
            yAxis: { type: 'value' },
            series: [
                {
                    type: 'bar',
                    data: profits,
                    itemStyle: {
                        color: (params: { value: number }) => (params.value >= 0 ? '#ef5350' : '#26a69a'),
                    },
                },
            ],
        });

        const resizeObserver = new ResizeObserver(() => {
            pieChart.resize();
            barChart.resize();
        });
        resizeObserver.observe(pieRef.current);
        resizeObserver.observe(barRef.current);

        return () => {
            resizeObserver.disconnect();
            pieChart.dispose();
            barChart.dispose();
        };
    }, [positions]);

    return (
        <div className="visualization portfolio-panel">
            {title && <div className="visualization-title">{title}</div>}
            <div className="portfolio-summary">
                <div>
                    <span>总市值</span>
                    <strong>{payload.totalMarketValue ?? 0}</strong>
                </div>
                <div>
                    <span>总盈亏</span>
                    <strong>{payload.totalProfit ?? 0}</strong>
                </div>
            </div>
            <div className="portfolio-charts">
                <div className="portfolio-chart" ref={pieRef} />
                <div className="portfolio-chart" ref={barRef} />
            </div>
        </div>
    );
};

export default PortfolioPanel;
