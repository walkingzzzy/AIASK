import { ToolDefinition, ToolHandler, ToolRegistryItem } from '../types/tools.js';
import * as Handlers from './handlers/index.js';

const definitions: ToolDefinition[] = [
    Handlers.alertsManagerTool,
    Handlers.dataSyncManagerTool,
    Handlers.optionsManagerTool,
    Handlers.technicalAnalysisManagerTool,
    Handlers.fundamentalAnalysisManagerTool,
    Handlers.sentimentManagerTool,
    Handlers.marketInsightManagerTool,
    Handlers.industryChainManagerTool,
    Handlers.limitUpManagerTool,
    Handlers.tradingDataManagerTool,
    Handlers.sectorManagerTool,
    Handlers.portfolioManagerTool,
    Handlers.performanceManagerTool,
    Handlers.liveTradingManagerTool,
    Handlers.paperTradingManagerTool,
    Handlers.executionManagerTool,
    Handlers.complianceManagerTool,
    Handlers.backtestManagerTool,
    Handlers.quantManagerTool,
    Handlers.screenerManagerTool,
    Handlers.riskManagerTool,
    Handlers.insightManagerTool,
    Handlers.eventManagerTool,
    Handlers.decisionManagerTool,
    Handlers.userManagerTool,
    Handlers.vectorSearchManagerTool,
    Handlers.comprehensiveManagerTool,
    Handlers.watchlistManagerTool,
    Handlers.macroManagerTool,
    Handlers.researchManagerTool
];

const handlers: Record<string, ToolHandler> = {
    alerts_manager: Handlers.alertsManagerHandler,
    data_sync_manager: Handlers.dataSyncManagerHandler,
    options_manager: Handlers.optionsManagerHandler,
    technical_analysis_manager: Handlers.technicalAnalysisManagerHandler,
    fundamental_analysis_manager: Handlers.fundamentalAnalysisManagerHandler,
    sentiment_manager: Handlers.sentimentManagerHandler,
    market_insight_manager: Handlers.marketInsightManagerHandler,
    industry_chain_manager: Handlers.industryChainManagerHandler,
    limit_up_manager: Handlers.limitUpManagerHandler,
    trading_data_manager: Handlers.tradingDataManagerHandler,
    sector_manager: Handlers.sectorManagerHandler,
    portfolio_manager: Handlers.portfolioManagerHandler,
    performance_manager: Handlers.performanceManagerHandler,
    live_trading_manager: Handlers.liveTradingManagerHandler,
    paper_trading_manager: Handlers.paperTradingManagerHandler,
    execution_manager: Handlers.executionManagerHandler,
    compliance_manager: Handlers.complianceManagerHandler,
    backtest_manager: Handlers.backtestManagerHandler,
    quant_manager: Handlers.quantManagerHandler,
    screener_manager: Handlers.screenerManagerHandler,
    risk_manager: Handlers.riskManagerHandler,
    insight_manager: Handlers.insightManagerHandler,
    event_manager: Handlers.eventManagerHandler,
    decision_manager: Handlers.decisionManagerHandler,
    user_manager: Handlers.userManagerHandler,
    vector_search_manager: Handlers.vectorSearchManagerHandler,
    comprehensive_manager: Handlers.comprehensiveManagerHandler,
    watchlist_manager: Handlers.watchlistManagerHandler,
    macro_manager: Handlers.macroManagerHandler,
    research_manager: Handlers.researchManagerHandler
};

export const managerTools: ToolRegistryItem[] = definitions.map(def => ({
    definition: def,
    handler: handlers[def.name]
}));

export { managerSchema } from './parameters.js';
