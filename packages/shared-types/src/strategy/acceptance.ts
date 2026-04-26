export type StrategyCoreChainStepKey =
  | 'view_strategy'
  | 'personal_strategy'
  | 'paper_session'
  | 'ai_read'
  | 'ai_submit';

export type StrategyCoreChainStepStatus = 'passed' | 'ready' | 'blocked' | 'degraded';

export type StrategyCoreChainAction = {
  label: string;
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  path: string;
  href?: string | null;
  body?: Record<string, unknown> | null;
};

export type StrategyCoreChainStep = {
  key: StrategyCoreChainStepKey;
  title: string;
  status: StrategyCoreChainStepStatus;
  completed: boolean;
  can_complete: boolean;
  success_condition: string;
  failure_reason: string | null;
  dependency_gaps: string[];
  last_success_at: string | null;
  next_action: string;
  action: StrategyCoreChainAction;
  evidence: string[];
  sources: string[];
  detail?: Record<string, unknown>;
};

export type StrategyCoreChainAcceptanceResponse = {
  dto_version: 'strategy_market.core_chain_acceptance.v1';
  generated_at: string;
  actor: {
    user_id: string | null;
    role: string;
  };
  environment: {
    authenticated: boolean;
    mcp_reachable: boolean;
    mcp_source?: string | null;
    degraded: boolean;
    errors: Record<string, string | null>;
  };
  target: {
    requested_strategy_id: string | null;
    market_strategy_id: string | null;
    personal_strategy_id: string | null;
    source_strategy_id: string | null;
    strategy_name: string | null;
    personal_strategy_name: string | null;
  };
  summary: {
    overall_status: StrategyCoreChainStepStatus;
    runnable: boolean;
    fully_completed: boolean;
    completed_steps: number;
    ready_steps: number;
    blocked_steps: string[];
    degraded_steps: string[];
    broken_steps: string[];
  };
  steps: StrategyCoreChainStep[];
  raw?: Record<string, unknown>;
};
