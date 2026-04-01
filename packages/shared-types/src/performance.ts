export type PerformanceAttributionComponent = {
    return?: number | null;
    contribution?: number | null;
    description?: string | null;
    status?: string | null;
    basis?: string | null;
    alignedDays?: number | null;
    assetsUsed?: number | null;
    staticTotalReturn?: number | null;
    realizedTotalReturn?: number | null;
};

export type PerformanceAttributionStockItem = {
    code?: string;
    sector?: string;
    weight?: number | null;
    weightPct?: number | null;
    stockReturn?: number | null;
    stockReturnPct?: number | null;
    lifetimeReturn?: number | null;
    lifetimeReturnPct?: number | null;
    contribution?: number | null;
    contributionPct?: number | null;
};

export type PerformanceSectorPerformanceItem = {
    sector: string;
    weight?: number | null;
    weightPct?: number | null;
    return?: number | null;
    returnPct?: number | null;
};

export type PerformanceBenchmarkAlignment = {
    benchmark: string;
    benchmarkReturn?: number | null;
    benchmarkReturnPct?: number | null;
    excessReturn?: number | null;
    excessReturnPct?: number | null;
    aligned?: boolean;
    alignmentMethod?: string | null;
};

export type PerformanceAttributionResponse = {
    message?: string | null;
    portfolioId: number | null;
    portfolioName: string | null;
    autoSelectedPortfolio: boolean;
    benchmark: string;
    lookbackDays: number;
    totalReturn?: number | null;
    totalReturnPct?: number | null;
    attribution?: {
        stockSelection?: PerformanceAttributionComponent | null;
        sectorAllocation?: PerformanceAttributionComponent | null;
        timing?: PerformanceAttributionComponent | null;
    };
    attributionByStock: PerformanceAttributionStockItem[];
    sectorPerformance: PerformanceSectorPerformanceItem[];
    benchmarkAlignment?: PerformanceBenchmarkAlignment | null;
    method?: string | null;
    windowAudit?: Record<string, unknown> | null;
    fees?: Record<string, unknown> | null;
    sourceTool?: string;
    argsMatched?: Record<string, unknown>;
    result?: unknown;
};

export type PerformanceBenchmarkComparisonResponse = {
    message?: string | null;
    portfolioId: number | null;
    portfolioName: string | null;
    autoSelectedPortfolio: boolean;
    benchmark: string;
    lookbackDays: number;
    alignedDays?: number | null;
    portfolioReturn?: number | null;
    portfolioReturnPct?: number | null;
    benchmarkReturn?: number | null;
    benchmarkReturnPct?: number | null;
    excessReturn?: number | null;
    excessReturnPct?: number | null;
    trackingError?: number | null;
    trackingErrorPct?: number | null;
    annualizedExcessReturn?: number | null;
    annualizedExcessReturnPct?: number | null;
    informationRatio?: number | null;
    outperformance?: boolean;
    portfolioTotalReturnAccount?: number | null;
    portfolioTotalReturnSeries?: number | null;
    windowAudit?: Record<string, unknown> | null;
    fees?: Record<string, unknown> | null;
    sourceTool?: string;
    argsMatched?: Record<string, unknown>;
    result?: unknown;
};
