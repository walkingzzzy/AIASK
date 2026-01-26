/**
 * 可视化渲染入口
 */

import React from 'react';
import { Visualization } from '../../../shared/types';
import StockCard from './StockCard';
import KlineChart from './KlineChart';
import DataTable from './DataTable';
import ChartPanel from './ChartPanel';
import ProfilePanel from './ProfilePanel';
import PortfolioPanel from './PortfolioPanel';
import DecisionPanel from './DecisionPanel';
import BacktestPanel from './BacktestPanel';

interface VisualizationRendererProps {
    visualization: Visualization;
}

const VisualizationRenderer: React.FC<VisualizationRendererProps> = ({ visualization }) => {
    switch (visualization.type) {
        case 'stock':
            return <StockCard title={visualization.title} data={visualization.data} />;
        case 'kline':
            return <KlineChart title={visualization.title} data={visualization.data} />;
        case 'table':
            return <DataTable title={visualization.title} data={visualization.data} />;
        case 'chart':
            return <ChartPanel title={visualization.title} data={visualization.data} />;
        case 'profile':
            return <ProfilePanel title={visualization.title} data={visualization.data} />;
        case 'portfolio':
            return <PortfolioPanel title={visualization.title} data={visualization.data} />;
        case 'decision':
            return <DecisionPanel title={visualization.title} data={visualization.data} />;
        case 'backtest':
            return <BacktestPanel title={visualization.title} data={visualization.data} />;
        default:
            return null;
    }
};

export default VisualizationRenderer;
