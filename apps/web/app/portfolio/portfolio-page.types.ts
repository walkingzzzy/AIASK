export type OptData = {
  optimization?: {
    expectedReturn?: number;
    expectedRisk?: number;
    sharpe?: number;
    weights?: Record<string, number> | Array<{ code: string; weight: number }>;
  };
};

export type RiskData = {
  riskMetrics?: {
    var95?: number;
    var99?: number;
    cvar?: number;
    beta?: number;
    volatility?: number;
    riskContribution?: Record<string, number>;
  };
};

export type StressScenario = { name?: string; impact?: number; description?: string };

export type StressData = { stressResult?: { scenarios?: StressScenario[] } };

export type PortfolioDetailRecord = Record<string, unknown> & {
  strategyAllocations?: Array<Record<string, unknown>>;
};

export type PendingPortfolioAction =
  | {
      type: 'create';
      summary: string;
      payload: { name: string; description: string; initialCapital: string };
    }
  | {
      type: 'addHolding';
      summary: string;
      payload: { portfolioId: string; code: string; shares: string; costPrice?: string };
    };
