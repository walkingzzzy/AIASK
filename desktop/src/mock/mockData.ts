import type { RunEvent, UnknownRecord, WorkbenchMessage } from "../types";

const now = new Date("2026-06-21T09:30:00+08:00").toISOString();

export const mockMessages: WorkbenchMessage[] = [
  {
    id: "msg_user_001",
    role: "user",
    content: "检查今天的数据状态，并给出可以继续研究的股票方向。",
    created_at: now,
    status: "sent"
  },
  {
    id: "msg_ai_001",
    role: "assistant",
    content: "数据源处于部分降级状态，雷达候选可先用于只读研究；需要刷新 TDX/Tushare 后再进入量化报告。",
    created_at: now,
    status: "completed",
    sources: [{ type: "data_status", freshness: "stale", source: "mock" }]
  }
];

export const mockRuns: UnknownRecord[] = [
  {
    id: "run_20260621_001",
    session_id: "sess_research_001",
    title: "金融研究预检",
    status: "completed",
    started_at: now,
    updated_at: now,
    toolset: "finance_safe",
    model: "gpt-4.1-compatible"
  },
  {
    id: "run_20260621_002",
    session_id: "sess_ops_001",
    title: "Gateway readiness scan",
    status: "requires_approval",
    started_at: now,
    updated_at: now,
    toolset: "ops_safe",
    model: "gpt-4.1-compatible"
  }
];

export const mockSessions: UnknownRecord[] = [
  {
    id: "sess_research_001",
    title: "金融研究工作台",
    status: "active",
    message_count: 12,
    updated_at: now
  },
  {
    id: "sess_ops_001",
    title: "集成与运维巡检",
    status: "active",
    message_count: 8,
    updated_at: now
  }
];

export const mockRunEvents: RunEvent[] = [
  {
    event_id: 1,
    type: "run.started",
    status: "completed",
    message: "Run created with finance_safe toolset",
    timestamp: now
  },
  {
    event_id: 2,
    type: "tool.completed",
    name: "agent_market_temperature_cache_readiness",
    status: "warning",
    message: "Cache is available but stale",
    timestamp: now,
    data: { quality_status: "stale", secrets_redacted: true }
  },
  {
    event_id: 3,
    type: "artifact.created",
    name: "data_preflight_report",
    status: "completed",
    message: "Preflight report attached",
    timestamp: now
  }
];

export const mockApiPayloads: Record<string, unknown> = {
  "/health": { status: "ok", service: "aiask-agent", mock: true },
  "/health/detailed": {
    status: "ok",
    service: "aiask-agent",
    runtime: { model: "gpt-4.1-compatible", toolset: "finance_safe" },
    tools: { count: 36, names: ["agent_market_temperature_snapshot", "agent_stock_radar_status"] },
    control: { loopback_only: true, token_configured: false }
  },
  "/v1/ai/status": {
    object: "aiask.ai_status",
    configured: true,
    provider: "openai-compatible",
    model: "gpt-4.1-compatible",
    base_url_configured: true,
    api_key_configured: true,
    source_mode: "mock",
    errors: []
  },
  "/v1/ai/config": {
    object: "aiask.ai_config",
    data: {
      provider: "openai-compatible",
      model: "gpt-4.1-compatible",
      base_url: "https://api.example.invalid/v1",
      api_key_configured: true,
      secrets_redacted: true
    }
  },
  "/v1/ai/models": {
    object: "list",
    data: [
      { id: "gpt-4.1-compatible", provider: "openai-compatible", status: "available" },
      { id: "gpt-4o-compatible", provider: "openai-compatible", status: "available" }
    ]
  },
  "/v1/desktop/workbench/summary": {
    object: "aiask.desktop.workbench_summary",
    data: {
      sessions: mockSessions,
      runs: mockRuns,
      messages: mockMessages,
      stats: { active_sessions: 2, runs_today: 5, pending_approvals: 1, data_gates: 2 }
    }
  },
  "/v1/hermes/sessions": { object: "list", data: mockSessions },
  "/v1/desktop/runs": { object: "list", data: mockRuns },
  "/v1/tools": {
    object: "list",
    data: [
      {
        name: "agent_market_temperature_snapshot",
        category: "finance",
        side_effect: "read_only",
        description: "Read market breadth and industry temperature."
      },
      {
        name: "agent_stock_radar_candidates",
        category: "finance",
        side_effect: "read_only",
        description: "Read stock radar candidate list."
      },
      {
        name: "agent_gateway_send_intent",
        category: "gateway",
        side_effect: "approval_required",
        description: "Create an intent for external delivery."
      }
    ]
  },
  "/intents": {
    object: "list",
    data: [
      {
        id: "intent_gateway_001",
        title: "Send digest preview",
        status: "pending",
        side_effect: "external_platform",
        created_at: now
      }
    ]
  },
  "/v1/approvals": {
    object: "list",
    data: [
      {
        id: "approval_001",
        title: "Gateway outbound message",
        status: "pending",
        risk: "external_delivery",
        created_at: now
      }
    ]
  },
  "/v1/mcp/servers": {
    object: "list",
    data: [
      { name: "akshare", status: "connected", transport: "stdio", tools: 128 },
      { name: "openai-docs", status: "available", transport: "http", tools: 8 }
    ]
  },
  "/v1/mcp/tools": { object: "list", data: [{ name: "stock_zh_a_spot", server: "akshare", status: "ready" }] },
  "/v1/mcp/resources": { object: "list", data: [{ uri: "akshare://market/a-share", server: "akshare", status: "ready" }] },
  "/v1/mcp/prompts": { object: "list", data: [{ name: "stock_deep_analysis", server: "akshare", status: "ready" }] },
  "/v1/mcp/oauth_status": { object: "list", data: [{ server: "openai-docs", configured: false, status: "not_required" }] },
  "/v1/connectors": {
    object: "list",
    data: [
      { id: "gateway:feishu", type: "gateway", name: "feishu", category: "delivery", configured: false, connected: false, status: "missing_env" },
      { id: "finance:tushare", type: "finance", name: "tushare", category: "data", configured: true, connected: true, status: "ready" }
    ]
  },
  "/v1/connectors/summary": {
    object: "connector.summary",
    data: { total: 2, ready: 1, missing: 1, gated: 1 }
  },
  "/v1/skills": { object: "list", data: { installed: ["aiask-repo-orientation", "aiask-desktop-workbench"], stale: [] } },
  "/v1/plugins": { object: "list", data: [{ name: "gateway-helper", enabled: true, tools: 2, commands: 1 }] },
  "/v1/gateway/status": { object: "gateway.status", data: { enabled: true, mode: "dry-run", platforms_ready: 1, blocked: 2 } },
  "/v1/gateway/daemon/status": { object: "gateway.daemon", data: { running: false, last_error: "not started in mock mode" } },
  "/v1/gateway/platforms": { object: "list", data: [{ platform: "local", configured: true, status: "ready" }, { platform: "feishu", configured: false, status: "missing_env" }] },
  "/v1/gateway/messages": { object: "list", data: [{ id: "msg_gateway_001", platform: "local", status: "draft", direction: "outbound", created_at: now }] },
  "/v1/gateway/directory": { object: "list", data: [{ id: "dir_local_001", platform: "local", kind: "channel", name: "Research Desk" }] },
  "/v1/webhooks": { object: "list", data: [{ id: "webhook_local_001", platform: "local", status: "disabled", verified: false }] },
  "/v1/desktop/settings/status": {
    object: "aiask.desktop.settings_status",
    data: { api_token_configured: false, control_token_configured: false, control_authorized: false, source_mode: "mock" }
  },
  "/v1/desktop/data/status": {
    object: "aiask.desktop.data_status",
    data: {
      database: { status: "ready", path_redacted: true },
      freshness: { status: "stale", max_stale_days: 5, stale_count: 3 },
      missing: ["market_temperature_snapshot_cache"],
      stale: ["daily_kline", "stock_basic"],
      source_chain: ["desktop_data", "akshare_mcp"]
    }
  },
  "/v1/desktop/stock-data-sources": {
    object: "list",
    data: [
      { name: "akshare", configured: true, status: "ready", secrets_redacted: true },
      { name: "tushare", configured: true, status: "ready", secrets_redacted: true },
      { name: "tdx", configured: false, status: "missing_path", secrets_redacted: true }
    ]
  },
  "/v1/desktop/stock-radar/status": {
    object: "tool_result",
    success: true,
    data: { latest_run_id: "radar_20260621", status: "ready", candidate_count: 18, last_updated: now }
  },
  "/v1/desktop/stock-radar/candidates": {
    object: "tool_result",
    success: true,
    data: {
      candidates: [
        { symbol: "600519", name: "贵州茅台", tier: "A", score: 87, reason: "趋势稳定，数据完整", risk: "估值敏感" },
        { symbol: "300750", name: "宁德时代", tier: "B", score: 79, reason: "行业温度回升", risk: "波动较高" },
        { symbol: "000858", name: "五粮液", tier: "B", score: 74, reason: "资金面修复", risk: "消费弱复苏" }
      ]
    }
  },
  "/v1/desktop/stock-radar/digest": {
    object: "tool_result",
    success: true,
    data: {
      digest: "今日雷达候选以消费和新能源龙头为主，建议先做数据刷新和只读复核。",
      channels: ["local", "preview"],
      delivery_intent_required: true
    }
  },
  "/v1/desktop/quant/presets": {
    object: "list",
    data: [
      { id: "momentum_research", name: "动量研究", risk: "read_only", default_universe: "A-share liquid" },
      { id: "breadth_rotation", name: "市场广度轮动", risk: "read_only", default_universe: "industry" }
    ]
  },
  "/v1/desktop/financial-manager/catalog": {
    object: "list",
    data: [
      { id: "portfolio_review", name: "组合复核", side_effect: "read_only" },
      { id: "broker_snapshot", name: "券商快照", side_effect: "read_only" }
    ]
  },
  "/v1/desktop/financial-manager/status": {
    object: "aiask.financial_manager.status",
    data: { ready: true, broker_read_only: true, live_trading_enabled: false, warnings: ["control token missing"] }
  },
  "/v1/desktop/broker-readiness": {
    object: "aiask.broker.readiness",
    data: { read_only: true, live_trading_enabled: false, accounts_ready: false, blockers: ["broker token not configured"] }
  },
  "/v1/desktop/broker/accounts": { object: "list", data: [{ provider: "qmt", account_id: "demo-redacted", status: "mock", read_only: true }] },
  "/v1/desktop/broker/positions": { object: "list", data: [{ symbol: "600519", quantity: 100, market_value: 168000, read_only: true }] },
  "/v1/desktop/broker/orders": { object: "list", data: [{ id: "order_demo_001", symbol: "600519", status: "historical", read_only: true }] },
  "/v1/jobs": {
    object: "list",
    data: [
      { id: "job_data_preflight", name: "数据预检", enabled: true, schedule: "weekday 08:45", toolset: "finance_safe" },
      { id: "job_gateway_digest", name: "投递摘要预览", enabled: false, schedule: "manual", toolset: "ops_safe" }
    ]
  },
  "/v1/desktop/users/local-profile": {
    object: "aiask.local_profile",
    data: { user_id: "local-user", display_name: "AIASK User", preferences: { language: "zh-CN" }, secrets_redacted: true }
  },
  "/v1/learning/status": { object: "learning.status", data: { enabled: true, proposals_pending: 2, last_review_at: now } },
  "/v1/learning/review": { object: "list", data: [{ id: "proposal_001", title: "优化数据预检提示", status: "pending", risk: "low" }] },
  "/v1/rl/environments": { object: "list", data: [{ id: "market_research_mock", status: "available", side_effect: "sandbox" }] },
  "/v1/rl/runs": { object: "list", data: [{ id: "rl_run_001", environment: "market_research_mock", status: "completed", score: 0.72 }] },
  "/v1/processes": { object: "list", data: [{ pid: 1234, name: "aiask-agent", status: "mock" }] },
  "/v1/terminal/backends": { object: "list", data: [{ name: "powershell", available: true, gated: true }] },
  "/v1/terminal/sessions": { object: "list", data: [] },
  "/v1/browser/sessions": { object: "list", data: [] },
  "/v1/hermes/readiness": { object: "hermes.readiness", data: { ready: true, full_mode_enabled: false, blockers: [] } },
  "/v1/financial-system/readiness": {
    object: "financial.readiness",
    data: {
      production_ready: false,
      required_gates: [{ name: "data_freshness", status: "warning" }],
      optional_gates: [{ name: "broker_read_only", status: "blocked" }],
      next_actions: ["配置 control token", "刷新市场温度缓存"]
    }
  },
  "/v1/desktop/capabilities": {
    object: "desktop.capabilities",
    data: { native: "gated", mcp: "ready", gateway: "degraded", finance: "ready" }
  },
  "/v1/capabilities/parity": {
    object: "capabilities.parity",
    data: { parity_ratio: 0.86, missing: ["voice_live"], warnings: ["full mode disabled"] }
  }
};

export function mockToolResponse(toolName: string, body: unknown): unknown {
  if (toolName === "agent_market_temperature_snapshot") {
    return {
      object: "tool_result",
      success: true,
      data: {
        market: { temperature: 62.4, state: "warm", sample_count: 4180 },
        hot_industries: [
          { industry: "白酒", temperature: 76.2, breadth: 0.68 },
          { industry: "新能源", temperature: 69.5, breadth: 0.57 }
        ],
        cold_industries: [{ industry: "地产", temperature: 28.4, breadth: 0.21 }],
        source_chain: ["mock", "agent_market_temperature_snapshot"]
      }
    };
  }
  if (toolName === "agent_market_temperature_cache_readiness") {
    return {
      object: "tool_result",
      success: true,
      data: { ready: false, status: "stale", blockers: ["cache_stale"], warnings: ["refresh recommended"] }
    };
  }
  return { object: "tool_result", success: true, data: { echoed_tool: toolName, body, mock: true } };
}
