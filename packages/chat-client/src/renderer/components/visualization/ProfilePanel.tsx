/**
 * 行为画像面板
 */

import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface ProfilePanelProps {
    title?: string;
    data: unknown;
}

type BehaviorSummary = {
    periodDays?: number;
    totalEvents?: number;
    topTools?: Array<{ name: string; count: number }>;
    topStocks?: Array<{ code: string; count: number }>;
    activeHours?: number[];
};

const ProfilePanel: React.FC<ProfilePanelProps> = ({ title, data }) => {
    const chartRef = useRef<HTMLDivElement>(null);
    const summary = (data && typeof data === 'object' ? data : {}) as BehaviorSummary;
    const topTools = summary.topTools || [];
    const topStocks = summary.topStocks || [];
    const activeHours = summary.activeHours || [];

    useEffect(() => {
        if (!chartRef.current) return;
        const chart = echarts.init(chartRef.current);

        const hours = Array.from({ length: 24 }).map((_, i) => String(i));
        const values = hours.map((_, idx) => activeHours[idx] || 0);

        chart.setOption({
            title: { text: '' },
            grid: { left: 20, right: 20, top: 10, bottom: 20 },
            xAxis: { type: 'category', data: hours },
            yAxis: { type: 'value' },
            series: [
                {
                    type: 'bar',
                    data: values,
                    itemStyle: { color: '#1890ff' },
                },
            ],
        });

        const resizeObserver = new ResizeObserver(() => chart.resize());
        resizeObserver.observe(chartRef.current);

        return () => {
            resizeObserver.disconnect();
            chart.dispose();
        };
    }, [activeHours]);

    return (
        <div className="visualization profile-panel">
            {title && <div className="visualization-title">{title}</div>}
            <div className="profile-summary">
                <div className="profile-item">
                    <span>近{summary.periodDays || 30}天事件</span>
                    <strong>{summary.totalEvents ?? 0}</strong>
                </div>
                <div className="profile-item">
                    <span>常用工具</span>
                    <strong>{topTools.length}</strong>
                </div>
                <div className="profile-item">
                    <span>关注股票</span>
                    <strong>{topStocks.length}</strong>
                </div>
            </div>

            <div className="profile-section">
                <h4>常用工具</h4>
                {topTools.length === 0 ? (
                    <div className="profile-empty">暂无记录</div>
                ) : (
                    <div className="profile-tags">
                        {topTools.map(tool => (
                            <span key={tool.name}>
                                {tool.name} ({tool.count})
                            </span>
                        ))}
                    </div>
                )}
            </div>

            <div className="profile-section">
                <h4>关注股票</h4>
                {topStocks.length === 0 ? (
                    <div className="profile-empty">暂无记录</div>
                ) : (
                    <div className="profile-tags">
                        {topStocks.map(stock => (
                            <span key={stock.code}>
                                {stock.code} ({stock.count})
                            </span>
                        ))}
                    </div>
                )}
            </div>

            <div className="profile-section">
                <h4>活跃时段</h4>
                <div ref={chartRef} className="profile-chart" />
            </div>
        </div>
    );
};

export default ProfilePanel;
