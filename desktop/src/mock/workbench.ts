import type {
  AgentArtifactRecord,
  AgentSourceRecord,
  DesktopRunSummary,
  DesktopWorkbenchSummary,
  HandoffQueuePayload,
  HandoffRecord,
  NormalizedRunEvent,
  RecentSessionSummary,
  SessionResumeContextPayload
} from "../types";

const mockRunEvents: NormalizedRunEvent[] = [
  {
    id: "evt_quote",
    event: "market.quote_snapshot",
    event_type: "market.quote_snapshot",
    run_id: "run_mock",
    created_at: "2026-05-22T09:00:00Z",
    kind: "tool",
    title: "market.quote_snapshot: 600519",
    severity: "info",
    status: "completed",
    tool_name: "agent_stock_live_quote",
    jump_target: "runs-events",
    data: {
      artifact_id: "art_mock_quote",
      code: "600519",
      price: 123.45,
      provider: "akshare/sina",
      data_timestamp: "2026-05-22T09:00:00+08:00"
    },
  },
  {
    id: "evt_source",
    event: "news.source_linked",
    event_type: "news.source_linked",
    run_id: "run_mock",
    created_at: "2026-05-22T09:00:00Z",
    kind: "tool",
    title: "news.source_linked: Mock 财经新闻",
    severity: "info",
    status: "completed",
    tool_name: "agent_stock_news_digest",
    jump_target: "runs-events",
    data: {
      source_id: "src_mock_news",
      title: "Mock 财经新闻",
      url: "https://example.com/aiask/mock-news",
      provider: "eastmoney",
      published_at: "2026-05-22T08:55:00+08:00"
    },
  },
  {
    id: "evt_tool",
    event: "tool.called",
    event_type: "tool.called",
    run_id: "run_mock",
    created_at: "2026-05-22T09:00:01Z",
    kind: "tool",
    title: "tool.called: agent_analyze_stock",
    severity: "info",
    status: "completed",
    tool_name: "agent_analyze_stock",
    jump_target: "tools-intents-approvals",
    data: { tool: "agent_analyze_stock", status: "completed" },
  },
  {
    id: "evt_approval",
    event: "approval.intent_created",
    event_type: "approval.intent_created",
    run_id: "run_mock",
    created_at: "2026-05-22T09:00:02Z",
    kind: "approval",
    title: "approval.intent_created",
    severity: "info",
    status: "pending",
    jump_target: "tools-intents-approvals",
    data: { intent_id: "intent_mock_pending", status: "pending" },
  },
];

const mockRunSummaries: DesktopRunSummary[] = [
  {
    run_id: "run_mock",
    session_id: "sess_mock",
    status: "completed",
    response_id: "resp_mock",
    created_at: "2026-05-22T09:00:00Z",
    updated_at: "2026-05-22T09:00:02Z",
    event_count: mockRunEvents.length,
    tool_call_count: 1,
    approval_count: 1,
    error_count: 0,
    last_event: mockRunEvents[mockRunEvents.length - 1],
    has_errors: false,
    has_pending_approval: true,
  },
];

function firstMockRunSummary() {
  return mockRunSummaries[0];
}

function latestMockRunEvent() {
  return mockRunEvents[mockRunEvents.length - 1];
}

function createMockSessionSummary(userId: unknown): RecentSessionSummary {
  return {
    session_id: "sess_mock",
    title: "Mock 研究会话",
    user_id: String(userId || "local"),
    created_at: "2026-05-22T09:00:00Z",
    updated_at: "2026-05-22T09:00:02Z",
    last_message_at: "2026-05-22T09:00:02Z",
    last_run_id: "run_mock",
    last_run_summary: firstMockRunSummary(),
    last_event: latestMockRunEvent(),
    message_count: 2,
    has_errors: false,
    has_pending_approval: true,
    status: "completed",
    archived: false,
    archived_at: null,
    archived_reason: null,
    handoff_state: {
      status: "active",
      handoff_id: "handoff_mock",
      target: "risk_specialist",
      source_run_id: "run_source_mock",
      source_tool_call_id: "call_handoff_mock",
      context_snapshot_id: "ctxsnap_mock_source",
      active_run_id: "run_mock",
      summary: "Continue with risk review.",
      reason: "risk escalation",
      updated_at: "2026-05-22T09:00:02Z",
      activated_at: "2026-05-22T09:00:02Z",
      metadata: { handoff_kind: "ownership_transfer" },
    },
    handoff_status: "active",
    handoff_target: "risk_specialist",
    handoff_id: "handoff_mock",
    handoff_context_snapshot_id: "ctxsnap_mock_source",
    active_agent: "risk_specialist",
    active_context_snapshot_id: "ctxsnap_mock_source",
    metadata: {
      source: "desktop.mockApi",
      handoff_status: "active",
      handoff_target: "risk_specialist",
      active_agent: "risk_specialist",
      active_context_snapshot_id: "ctxsnap_mock_source",
    },
  };
}

const mockSessionSummaries: RecentSessionSummary[] = [createMockSessionSummary("local")];

const initialMockSessionMessages: Array<Record<string, unknown>> = [
  { id: 1, message_id: "msg_user", role: "user", content: "mock question", created_at: "2026-05-22T09:00:01Z" },
  { id: 2, message_id: "msg_assistant", role: "assistant", content: "mock answer", created_at: "2026-05-22T09:00:02Z" },
];

let mockSessionMessages: Array<Record<string, unknown>> = initialMockSessionMessages.map((item) => ({ ...item }));

export function resetMockWorkbenchState(userId: unknown): void {
  mockSessionSummaries.splice(0, mockSessionSummaries.length, createMockSessionSummary(userId));
  mockSessionMessages = initialMockSessionMessages.map((item) => ({ ...item }));
}

export function currentMockSessionSummaries(): RecentSessionSummary[] {
  return mockSessionSummaries.map((session) => {
    if (session.session_id !== "sess_mock") return session;
    const lastMessage = mockSessionMessages[mockSessionMessages.length - 1];
    return {
      ...session,
      message_count: mockSessionMessages.length,
      last_message_at: String(lastMessage?.created_at || session.last_message_at || ""),
    };
  });
}

export function mockSessionMessagesData() {
  return mockSessionMessages;
}

function mockHandoffRecord(session = currentMockSessionSummaries()[0], userId: unknown = "local"): HandoffRecord {
  const state = session.handoff_state || {};
  return {
    handoff_id: String(session.handoff_id || state.handoff_id || "handoff_mock"),
    session_id: session.session_id,
    user_id: session.user_id || String(userId || "local"),
    target: session.handoff_target || state.target || "risk_specialist",
    status: "requested",
    runtime_status: session.handoff_status || state.status || "active",
    reason: String(state.reason || "risk escalation"),
    summary: String(state.summary || "Continue with risk review."),
    metadata: { context_snapshot_id: session.handoff_context_snapshot_id || state.context_snapshot_id || "ctxsnap_mock_source" },
    created_at: session.created_at,
    updated_at: session.updated_at,
    session_title: session.title,
    handoff_state: state,
    active_agent: session.active_agent || state.target || "risk_specialist",
    active_context_snapshot_id: session.active_context_snapshot_id || state.context_snapshot_id || "ctxsnap_mock_source",
    resume_context_snapshot_id: session.active_context_snapshot_id || session.handoff_context_snapshot_id || state.context_snapshot_id || "ctxsnap_mock_source",
    resume_ready: true,
    secrets_redacted: true,
  };
}

export function mockHandoffQueue(
  filters: { userId?: string | null; sessionId?: string | null; status?: string | null; includeCompleted?: boolean; limit?: number } = {},
  userId: unknown = "local"
): HandoffQueuePayload {
  const status = String(filters.status || "").toLowerCase();
  const rows = currentMockSessionSummaries()
    .filter((session) => !filters.userId || session.user_id === filters.userId)
    .filter((session) => !filters.sessionId || session.session_id === filters.sessionId)
    .filter((session) => session.handoff_state || session.handoff_status || session.active_agent)
    .map((session) => mockHandoffRecord(session, userId))
    .filter((item) => !status || status === "all" || item.runtime_status === status)
    .filter((item) => filters.includeCompleted || !["completed", "failed", "cancelled", "canceled"].includes(String(item.runtime_status || item.status || "")));
  const limited = rows.slice(0, Math.max(1, Math.min(filters.limit || 100, 500)));
  const summary = limited.reduce<Record<string, number>>((acc, item) => {
    const key = String(item.runtime_status || item.status || "unknown");
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, { total: limited.length });
  return {
    object: "aiask.handoff_queue",
    implementation: "aiask_native",
    data: limited,
    count: limited.length,
    summary,
    filters,
    secrets_redacted: true,
  };
}

export function mockSessionResumeContext(sessionId: string, userId: unknown = "local"): SessionResumeContextPayload {
  const session = currentMockSessionSummaries().find((item) => item.session_id === sessionId) || currentMockSessionSummaries()[0];
  const handoff = mockHandoffRecord(session, userId);
  const snapshotId = String(handoff.resume_context_snapshot_id || "ctxsnap_mock_source");
  return {
    object: "aiask.session_resume_context",
    implementation: "aiask_native",
    session_id: sessionId,
    session,
    handoff,
    handoff_state: session.handoff_state || null,
    context_snapshot: {
      snapshot_id: snapshotId,
      session_id: session.session_id,
      context_summary_id: "ctxsum_mock_source",
      risk_flags: ["mock_resume"],
      source_message_ids: ["msg_user", "msg_assistant"],
      source_ids: ["src_mock_news"],
      artifact_ids: ["art_mock_quote"],
      summary: "Mock resume snapshot",
      secrets_redacted: true,
    },
    resume_context: {
      session_id: session.session_id,
      handoff_id: handoff.handoff_id,
      target: handoff.target,
      status: handoff.runtime_status,
      context_snapshot_id: snapshotId,
      context_summary_id: "ctxsum_mock_source",
      risk_flags: ["mock_resume"],
      source_message_ids: ["msg_user", "msg_assistant"],
      source_ids: ["src_mock_news"],
      artifact_ids: ["art_mock_quote"],
      summary: String(session.handoff_state?.summary || "Continue with risk review."),
      reason: String(session.handoff_state?.reason || "risk escalation"),
      resume_prompt: `继续会话 ${session.session_id}。当前任务接管目标为 ${handoff.target || "risk_specialist"}；请基于上下文快照 ${snapshotId} 继续推进。`,
    },
    secrets_redacted: true,
  };
}

export function mockSessionUndo(sessionId: string, body: Record<string, unknown>) {
  const turnsValue = Number(body.turns || 1);
  const turns = Math.max(1, Math.min(Math.floor(Number.isFinite(turnsValue) ? turnsValue : 1), 100));
  const userIndexes = mockSessionMessages
    .map((item, index) => ({ role: String(item.role || ""), index }))
    .filter((item) => item.role === "user")
    .map((item) => item.index)
    .reverse()
    .slice(0, turns);
  const cutoff = userIndexes.length ? Math.min(...userIndexes) : -1;
  const deleted = cutoff >= 0 ? mockSessionMessages.slice(cutoff) : [];
  if (cutoff >= 0) mockSessionMessages = mockSessionMessages.slice(0, cutoff);
  return {
    object: "aiask.session_undo",
    implementation: "aiask_native",
    session_id: sessionId,
    turns_requested: turns,
    turns_undone: userIndexes.length,
    message_ids: deleted.map((item) => item.id || item.message_id),
    message_count: deleted.length,
    deleted_at: "2026-05-22T09:00:03Z",
    deleted_reason: String(body.reason || "desktop session undo"),
    deleted_by: "mock-control-token",
    soft_deleted: true,
    side_effects_rolled_back: false,
    external_side_effects: "not_rolled_back",
  };
}

export function mockSessionArchive(sessionId: string, body: Record<string, unknown>) {
  const archived = body.archived !== false;
  const target = mockSessionSummaries.find((session) => session.session_id === sessionId);
  if (target) {
    target.archived = archived;
    target.archived_at = archived ? "2026-05-22T09:00:04Z" : null;
    target.archived_reason = archived ? String(body.reason || "desktop session archive") : null;
    target.metadata = {
      ...(target.metadata || {}),
      archived,
      archived_at: target.archived_at,
      archived_reason: target.archived_reason,
    };
  }
  return {
    object: "aiask.session_archive",
    implementation: "aiask_native",
    session_id: sessionId,
    archived,
    archived_at: target?.archived_at || null,
    archived_reason: target?.archived_reason || null,
    session: target,
  };
}

export function mockWorkbenchSummary(): DesktopWorkbenchSummary {
  return {
    recent_sessions: currentMockSessionSummaries(),
    recent_runs: mockRunSummaries,
    queues: {
      pending_intents: 1,
      pending_approvals: 1,
      gateway_failed: 1,
      mcp_degraded: 1,
    },
    access: {
      full_mode_active: true,
      control_token_configured: true,
      sessions_admin_available: true,
    },
  };
}

const mockAgentArtifacts: AgentArtifactRecord[] = [
  {
    artifact_id: "art_mock_quote",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_quote",
    tool_name: "agent_stock_live_quote",
    kind: "quote_snapshot",
    title: "600519 实时行情快照",
    preview_text: "价格 123.45，来源 akshare/sina，时间 2026-05-22T09:00:00+08:00",
    preview_json: {
      code: "600519",
      price: 123.45,
      change_pct: 1.23,
      provider: "akshare/sina",
      data_timestamp: "2026-05-22T09:00:00+08:00"
    },
    status: "ready",
    metadata: { source_chain: ["desktop.mockApi", "akshare", "sina"] },
    created_at: "2026-05-22T09:00:00Z",
    updated_at: "2026-05-22T09:00:00Z"
  },
  {
    artifact_id: "art_mock_news",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_news",
    tool_name: "agent_stock_news_digest",
    kind: "news_digest",
    title: "600519 新闻摘要",
    preview_text: "1 条带链接的新闻来源已保存。",
    preview_json: {
      items: [
        {
          title: "Mock 财经新闻",
          url: "https://example.com/aiask/mock-news",
          provider: "eastmoney",
          published_at: "2026-05-22T08:55:00+08:00"
        }
      ]
    },
    status: "ready",
    metadata: { source_chain: ["desktop.mockApi", "eastmoney"] },
    created_at: "2026-05-22T09:00:00Z",
    updated_at: "2026-05-22T09:00:00Z"
  },
  {
    artifact_id: "art_mock_script",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_script",
    tool_name: "agent_execute_python",
    kind: "script",
    title: "call_mock_script_snippet.py",
    path: "mock://aiask/artifacts/sess_mock/run_mock/call_mock_script_snippet.py",
    mime_type: "text/x-python",
    size_bytes: 54,
    sha256: "mock-sha256",
    preview_text: "print('AIASK mock script artifact')",
    status: "ready",
    metadata: { language: "python", persisted_from: "agent_execute_python" },
    created_at: "2026-05-22T09:00:01Z",
    updated_at: "2026-05-22T09:00:01Z"
  },
  {
    artifact_id: "art_mock_terminal",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_terminal",
    tool_name: "agent_terminal",
    kind: "terminal_output",
    title: "agent_terminal output",
    mime_type: "text/plain",
    preview_text: "PS> npm test -- --runInBand\nPASS workbench evidence smoke",
    preview_json: {
      command: "npm test -- --runInBand",
      exit_code: 0,
      stdout: "PASS workbench evidence smoke",
      stderr: ""
    },
    status: "ready",
    metadata: { persisted_from: "agent_terminal" },
    created_at: "2026-05-22T09:00:02Z",
    updated_at: "2026-05-22T09:00:02Z"
  }
];

const mockAgentSources: AgentSourceRecord[] = [
  {
    source_id: "src_mock_quote_provider",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_quote",
    tool_name: "agent_stock_live_quote",
    provider: "sina",
    source_type: "market_quote",
    title: "sina data source",
    fetched_at: "2026-05-22T09:00:00Z",
    data_timestamp: "2026-05-22T09:00:00+08:00",
    metadata: { source_chain: ["desktop.mockApi", "akshare", "sina"] },
    created_at: "2026-05-22T09:00:00Z"
  },
  {
    source_id: "src_mock_news",
    user_id: "local",
    session_id: "sess_mock",
    run_id: "run_mock",
    trace_id: "trace_mock",
    tool_call_id: "call_mock_news",
    tool_name: "agent_stock_news_digest",
    provider: "eastmoney",
    source_type: "news",
    title: "Mock 财经新闻",
    url: "https://example.com/aiask/mock-news",
    published_at: "2026-05-22T08:55:00+08:00",
    fetched_at: "2026-05-22T09:00:00Z",
    excerpt: "Mock 新闻来源链接，用于验证 Desktop 证据展示。",
    metadata: { source_chain: ["desktop.mockApi", "eastmoney"] },
    created_at: "2026-05-22T09:00:00Z"
  }
];

export function mockRunEventsData() {
  return mockRunEvents;
}

export function mockRunSummariesData() {
  return mockRunSummaries;
}

export function mockAgentArtifactsData() {
  return mockAgentArtifacts;
}

export function mockAgentSourcesData() {
  return mockAgentSources;
}

export function filterMockArtifacts({
  runId,
  sessionId,
  kind,
  limit = 100
}: {
  runId?: string;
  sessionId?: string;
  kind?: string | null;
  limit?: number;
}): AgentArtifactRecord[] {
  return mockAgentArtifacts
    .filter((item) => !runId || item.run_id === runId)
    .filter((item) => !sessionId || item.session_id === sessionId)
    .filter((item) => !kind || item.kind === kind)
    .slice(0, Math.max(1, Math.min(limit || 100, 1000)));
}

export function filterMockSources({
  runId,
  sessionId,
  sourceType,
  limit = 100
}: {
  runId?: string;
  sessionId?: string;
  sourceType?: string | null;
  limit?: number;
}): AgentSourceRecord[] {
  return mockAgentSources
    .filter((item) => !runId || item.run_id === runId)
    .filter((item) => !sessionId || item.session_id === sessionId)
    .filter((item) => !sourceType || item.source_type === sourceType)
    .slice(0, Math.max(1, Math.min(limit || 100, 1000)));
}

export function mockArtifactContent(artifactId: string) {
  const artifact = mockAgentArtifacts.find((item) => item.artifact_id === artifactId);
  if (!artifact) return null;
  return {
    object: "artifact.content",
    artifact_id: artifactId,
    encoding: "text",
    mime_type: artifact.mime_type || "text/plain",
    bytes: String(artifact.preview_text || "").length,
    truncated: false,
    content: artifact.preview_text || JSON.stringify(artifact.preview_json || artifact, null, 2)
  };
}

export function mockArtifactRecord(artifactId: string) {
  return mockAgentArtifacts.find((item) => item.artifact_id === artifactId) || { artifact_id: artifactId, status: "missing" };
}

export function mockSourceRecord(sourceId: string) {
  return mockAgentSources.find((item) => item.source_id === sourceId) || { source_id: sourceId, source_type: "missing" };
}
