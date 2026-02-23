/**
 * Query Key 工厂 — 按模块组织，支持 invalidateQueries 批量失效。
 * 模块名必须与 API 路径的第一段一致（如 /portfolio/list → 'portfolio'），
 * 因为 useApiQuery 的 key 结构为 ['api', module, path, ...extra]。
 */
export const apiKeys = {
  all: ['api'] as const,
  market:         (...a: unknown[]) => ['api', 'market',          ...a] as const,
  fundFlow:       (...a: unknown[]) => ['api', 'fund-flow',       ...a] as const,
  portfolio:      (...a: unknown[]) => ['api', 'portfolio',       ...a] as const,
  backtest:       (...a: unknown[]) => ['api', 'backtest',        ...a] as const,
  alerts:         (...a: unknown[]) => ['api', 'alerts',          ...a] as const,
  strategy:       (...a: unknown[]) => ['api', 'strategy-market', ...a] as const,
  paper:          (...a: unknown[]) => ['api', 'paper-trading',   ...a] as const,
  risk:           (...a: unknown[]) => ['api', 'risk',            ...a] as const,
  research:       (...a: unknown[]) => ['api', 'research',        ...a] as const,
  factor:         (...a: unknown[]) => ['api', 'factor',          ...a] as const,
  tdx:            (...a: unknown[]) => ['api', 'tdx',             ...a] as const,
  auth:           (...a: unknown[]) => ['api', 'auth',            ...a] as const,
  sentiment:      (...a: unknown[]) => ['api', 'sentiment',       ...a] as const,
  technical:      (...a: unknown[]) => ['api', 'technical',       ...a] as const,
  fundamental:    (...a: unknown[]) => ['api', 'fundamental',     ...a] as const,
  health:         (...a: unknown[]) => ['api', 'health',          ...a] as const,
  assistant:      (...a: unknown[]) => ['api', 'assistant',       ...a] as const,
  data:           (...a: unknown[]) => ['api', 'data',            ...a] as const,
  search:         (...a: unknown[]) => ['api', 'search',          ...a] as const,
  custom:         (p: string, ...a: unknown[]) => ['api', p,      ...a] as const,
} as const;
