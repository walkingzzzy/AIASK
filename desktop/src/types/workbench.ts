import type { MainView, ToolEnvelope } from "../types";

export interface AgentToolCall {
  id?: string;
  name?: string;
  arguments?: Record<string, unknown>;
  result?: ToolEnvelope | unknown;
}

export interface AgentResponse {
  id: string;
  object: string;
  status: string;
  output_text: string;
  metadata?: {
    session_id?: string;
    run_id?: string;
    mode?: string;
    tool_calls?: AgentToolCall[];
    audit_events?: Record<string, unknown>[];
  };
}

export interface ResponseRecord extends AgentResponse {
  model?: string;
  usage?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface RunRecord {
  run_id?: string;
  id?: string;
  object?: string;
  status?: string;
  response_id?: string;
  session_id?: string;
  created_at?: string;
  updated_at?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

export type TaskArtifactKind =
  | "report"
  | "strategy"
  | "factor"
  | "data"
  | "screenshot"
  | "json"
  | "run"
  | "approval"
  | "note"
  | "file"
  | "code"
  | "script"
  | "terminal_output"
  | "quote_snapshot"
  | "news_digest"
  | "chart"
  | "table"
  | "patch";

export interface TaskArtifact {
  id: string;
  kind: TaskArtifactKind;
  title: string;
  description?: string;
  status?: string;
  source?: string;
  sourceView?: MainView;
  createdAt?: string;
  path?: string;
  targetPath?: string;
  href?: string;
  severity?: "info" | "warning" | "critical";
  thumbnailPath?: string;
  value?: unknown;
}

export interface AgentArtifactRecord {
  artifact_id: string;
  user_id?: string;
  session_id?: string;
  run_id?: string;
  trace_id?: string;
  tool_call_id?: string;
  tool_name?: string;
  kind: TaskArtifactKind | string;
  title: string;
  path?: string;
  uri?: string;
  mime_type?: string;
  size_bytes?: number;
  sha256?: string;
  preview_text?: string;
  preview_json?: unknown;
  source_id?: string;
  status?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface AgentSourceRecord {
  source_id: string;
  user_id?: string;
  session_id?: string;
  run_id?: string;
  trace_id?: string;
  tool_call_id?: string;
  tool_name?: string;
  provider?: string;
  source_type: string;
  title?: string;
  url?: string;
  published_at?: string;
  fetched_at?: string;
  data_timestamp?: string;
  excerpt?: string;
  source_tier?: string;
  credibility_score?: number;
  metadata?: Record<string, unknown>;
  created_at?: string;
  [key: string]: unknown;
}

export interface TaskReviewComment {
  id: string;
  targetId: string;
  targetType: "artifact" | "run" | "page" | "screenshot" | "thread";
  body: string;
  status?: "open" | "resolved";
  createdAt?: string;
  targetPath?: string;
  severity?: "info" | "warning" | "critical";
}

export interface TaskContextSummary {
  projectLabel: string;
  threadLabel: string;
  runLabel: string;
  mode: "finance_safe" | "hermes_full";
  backendMode: "mock" | "live";
  endpoint: string;
  healthStatus: string;
  pendingApprovals: number;
  pendingIntents: number;
  artifactCount: number;
}

export interface TaskThread {
  id: string;
  title: string;
  prompt: string;
  createdAt: string;
  status: string;
  sessionId?: string;
  runId?: string;
  lastMessageAt?: string;
  response?: AgentResponse;
}

export type TimelineEventKind = "user" | "assistant" | "tool" | "approval" | "gateway" | "mcp" | "error" | "system" | "event";

export interface SessionHandoffState {
  status?: string;
  handoff_id?: string | null;
  target?: string | null;
  source_run_id?: string | null;
  source_tool_call_id?: string | null;
  context_snapshot_id?: string | null;
  active_run_id?: string | null;
  active_trace_id?: string | null;
  summary?: string | null;
  reason?: string | null;
  updated_at?: string;
  activated_at?: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RecentSessionSummary {
  session_id: string;
  title: string;
  user_id?: string;
  created_at?: string;
  updated_at?: string;
  last_message_at?: string;
  last_run_id?: string;
  last_event?: NormalizedRunEvent | Record<string, unknown> | null;
  last_run_summary?: DesktopRunSummary | null;
  message_count?: number;
  has_errors?: boolean;
  has_pending_approval?: boolean;
  status?: string;
  archived?: boolean;
  archived_at?: string | null;
  archived_reason?: string | null;
  handoff_state?: SessionHandoffState | null;
  handoff_status?: string | null;
  handoff_target?: string | null;
  handoff_id?: string | null;
  handoff_context_snapshot_id?: string | null;
  active_agent?: string | null;
  active_context_snapshot_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface HandoffRecord {
  handoff_id: string;
  session_id?: string;
  user_id?: string;
  target?: string | null;
  status?: string;
  runtime_status?: string;
  reason?: string | null;
  summary?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  session_title?: string | null;
  handoff_state?: SessionHandoffState | null;
  active_agent?: string | null;
  active_context_snapshot_id?: string | null;
  resume_context_snapshot_id?: string | null;
  resume_ready?: boolean;
  secrets_redacted?: boolean;
  [key: string]: unknown;
}

export interface HandoffQueuePayload {
  object: "aiask.handoff_queue" | string;
  implementation?: string;
  data: HandoffRecord[];
  count?: number;
  summary?: Record<string, number>;
  filters?: Record<string, unknown>;
  secrets_redacted?: boolean;
}

export interface SessionResumeContextPayload {
  object: "aiask.session_resume_context" | string;
  implementation?: string;
  session_id: string;
  session?: RecentSessionSummary;
  handoff?: HandoffRecord | null;
  handoff_state?: SessionHandoffState | null;
  context_snapshot?: Record<string, unknown> | null;
  resume_context?: {
    session_id?: string;
    handoff_id?: string | null;
    target?: string | null;
    status?: string | null;
    context_snapshot_id?: string | null;
    context_summary_id?: string | null;
    risk_flags?: string[];
    source_message_ids?: string[];
    source_ids?: string[];
    artifact_ids?: string[];
    summary?: string | null;
    reason?: string | null;
    resume_prompt?: string;
    [key: string]: unknown;
  };
  secrets_redacted?: boolean;
}

export interface SessionUndoPayload {
  object: "aiask.session_undo";
  implementation?: string;
  session_id: string;
  turns_requested: number;
  turns_undone: number;
  message_ids: Array<number | string>;
  message_count: number;
  deleted_at?: string;
  deleted_reason?: string;
  deleted_by?: string;
  soft_deleted?: boolean;
  side_effects_rolled_back: boolean;
  external_side_effects: string;
}

export interface SessionArchivePayload {
  object: "aiask.session_archive";
  implementation?: string;
  session_id: string;
  archived: boolean;
  archived_at?: string | null;
  archived_reason?: string | null;
  session?: RecentSessionSummary & { metadata?: Record<string, unknown> };
}

export interface DesktopRunSummary {
  run_id: string;
  session_id?: string;
  status: string;
  response_id?: string;
  created_at?: string;
  updated_at?: string;
  event_count?: number;
  tool_call_count?: number;
  approval_count?: number;
  error_count?: number;
  last_event?: NormalizedRunEvent | null;
  has_errors?: boolean;
  has_pending_approval?: boolean;
}

export interface DesktopWorkbenchSummary {
  recent_sessions: RecentSessionSummary[];
  recent_runs?: DesktopRunSummary[];
  queues: {
    pending_intents: number;
    pending_approvals: number;
    gateway_failed: number;
    mcp_degraded: number;
  };
  access: {
    full_mode_active: boolean;
    control_token_configured?: boolean;
    sessions_admin_available: boolean;
  };
}

export interface NormalizedRunEvent {
  id?: string;
  event?: string;
  event_type?: string;
  run_id?: string;
  created_at?: string;
  status?: string;
  kind?: string;
  title?: string;
  severity?: string;
  tool_name?: string | null;
  error_message?: string | null;
  jump_target?: MainView | string;
  data?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RunTraceEvalCheck {
  id: string;
  label?: string;
  status: "pass" | "warn" | "fail" | string;
  detail?: string;
  evidence?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RunTraceEvalPayload {
  object: "aiask.run_trace_eval" | string;
  implementation?: string;
  run_id: string;
  session_id?: string | null;
  status: "healthy" | "degraded" | "failed" | string;
  score?: number;
  checks: RunTraceEvalCheck[];
  summary: {
    event_count?: number;
    tool_invocation_count?: number;
    failed_tool_invocation_count?: number;
    context_snapshot_count?: number;
    source_count?: number;
    artifact_count?: number;
    handoff_event_count?: number;
    guardrail_event_count?: number;
    error_event_count?: number;
    [key: string]: unknown;
  };
  latest_context_snapshot?: Record<string, unknown> | null;
  risk_flags?: string[];
  secrets_redacted?: boolean;
  [key: string]: unknown;
}

export interface TimelineEvent {
  id: string;
  kind: TimelineEventKind;
  title: string;
  subtitle?: string;
  body?: string;
  status?: string;
  severity?: string;
  jumpTarget?: MainView | string;
  payload?: unknown;
}

export interface DiagnosticsSummary {
  status: string;
  coverage?: number;
  complete?: number;
  implementedFeatures?: number;
  featureCount?: number;
  liveStatus?: string;
}
