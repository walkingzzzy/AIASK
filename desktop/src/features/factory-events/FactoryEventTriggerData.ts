import { compact } from "../../components/shared";

export interface FactoryEventRow {
  event_id: string;
  event_name: string;
  event_type: string;
  event_source: string;
  status: string;
  direction: string;
  intensity: number;
  confidence: number;
  primary_themes: string[];
  operator_id?: string;
  approver_id?: string | null;
  created_at?: string;
  valid_from?: string;
  valid_until?: string;
  [key: string]: unknown;
}

export interface PreviewImpact {
  theme_code: string;
  depth: number;
  magnitude: number;
  source_path?: string;
}

export interface PreviewPayload {
  event_id?: string;
  impacts?: PreviewImpact[];
  candidate_symbols?: string[];
  target_count?: number;
  warnings?: string[];
  preview_mode?: string;
}

export interface LineageRow {
  lineage_id?: number;
  dedupe_key?: string;
  event_id: string;
  event_name?: string;
  event_type?: string;
  event_status?: string;
  task_id: string;
  theme_code: string;
  impact_direction?: string;
  impact_magnitude?: number;
  target_symbols?: string[];
  target_count?: number;
  breadth_resolved?: string;
  generated_at?: string;
  gate_1_passed?: number | boolean | null;
  gate_2_passed?: number | boolean | null;
  gate_3_passed?: number | boolean | null;
  strategies_submitted?: number;
  [key: string]: unknown;
}

export interface RadarCandidateRow {
  candidate_id: string;
  run_id: string;
  symbol: string;
  stock_name?: string;
  tier: string;
  radar_score: number;
  event_id?: string;
  event_type: string;
  direction: string;
  summary?: string;
  source_doc_uids: string[];
  source_chain: unknown[];
  extraction: Record<string, unknown>;
  confirmations: Record<string, unknown>;
  risk_flags: string[];
  push_status?: string;
  [key: string]: unknown;
}

export interface IntentEnvelope {
  intent?: {
    intent_id?: string;
    status?: string;
    target_action?: string;
  };
  intent_id?: string;
  status?: string;
}

export type TabId = "events" | "radar" | "create" | "preview" | "lineage";

export const STATUS_OPTIONS = ["", "pending_review", "active", "paused", "expired"];
export const SOURCE_OPTIONS = ["", "manual", "news_llm", "macro_shock", "market_anomaly", "price_inference"];
export const TYPE_OPTIONS = ["", "policy_shock", "earnings", "guidance", "regulation", "macro_data", "other"];
export const DIRECTION_OPTIONS = ["bullish", "bearish", "neutral"];
export const OUTCOME_OPTIONS = ["positive", "negative", "mixed", "no_effect"] as const;
export const RADAR_TIER_OPTIONS = [
  { value: "", label: "全部级别" },
  { value: "alert", label: "警报" },
  { value: "watch", label: "观察" },
  { value: "observe", label: "跟踪" },
  { value: "reject", label: "排除" }
];

export const HIGH_INTENSITY_THRESHOLD = 0.8;

export function eventListFromData(data: unknown): FactoryEventRow[] {
  const record = data && typeof data === "object" && !Array.isArray(data) ? (data as Record<string, unknown>) : {};
  const rawEvents = Array.isArray(record.events) ? record.events : Array.isArray(data) ? data : [];
  return rawEvents.map((item, index) => {
    const event = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    const themes = Array.isArray(event.primary_themes)
      ? (event.primary_themes as unknown[]).map((value) => compact(value))
      : [];
    return {
      ...event,
      event_id: compact(event.event_id || event.id || `evt_${index}`),
      event_name: compact(event.event_name || event.name || event.event_id || "(unnamed)"),
      event_type: compact(event.event_type || event.type || "unknown"),
      event_source: compact(event.event_source || event.source || "unknown"),
      status: compact(event.status || "unknown"),
      direction: compact(event.direction || "neutral"),
      intensity: Number(event.intensity || 0),
      confidence: Number(event.confidence || 0),
      primary_themes: themes,
      operator_id: compact(event.operator_id || ""),
      approver_id: event.approver_id == null ? null : compact(event.approver_id),
      created_at: compact(event.created_at || ""),
      valid_from: compact(event.valid_from || ""),
      valid_until: compact(event.valid_until || "")
    } as FactoryEventRow;
  });
}

export function previewFromData(data: unknown): PreviewPayload {
  const record = data && typeof data === "object" && !Array.isArray(data) ? (data as Record<string, unknown>) : {};
  const impacts = Array.isArray(record.impacts)
    ? (record.impacts as unknown[]).map((item) => {
        const row = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
        return {
          theme_code: compact(row.theme_code || row.theme || "unknown"),
          depth: Number(row.depth || 0),
          magnitude: Number(row.magnitude || 0),
          source_path: compact(row.source_path || "")
        };
      })
    : [];
  const candidateSymbols = Array.isArray(record.candidate_symbols)
    ? (record.candidate_symbols as unknown[]).map((value) => compact(value))
    : [];
  const warnings = Array.isArray(record.warnings)
    ? (record.warnings as unknown[]).map((value) => compact(value))
    : [];
  return {
    event_id: compact(record.event_id || ""),
    impacts,
    candidate_symbols: candidateSymbols,
    target_count: Number(record.target_count || candidateSymbols.length),
    warnings,
    preview_mode: compact(record.preview_mode || "")
  };
}

export function lineageFromData(data: unknown): LineageRow[] {
  const record = data && typeof data === "object" && !Array.isArray(data) ? (data as Record<string, unknown>) : {};
  const rawRows = Array.isArray(record.lineage)
    ? record.lineage
    : Array.isArray(record.items)
      ? record.items
      : Array.isArray(data)
        ? data
        : [];
  return rawRows.map((item, index) => {
    const row = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    const rawSymbols = Array.isArray(row.target_symbols) ? row.target_symbols : [];
    return {
      ...row,
      lineage_id: Number(row.lineage_id || index + 1),
      dedupe_key: compact(row.dedupe_key || ""),
      event_id: compact(row.event_id || ""),
      event_name: compact(row.event_name || ""),
      event_type: compact(row.event_type || ""),
      event_status: compact(row.event_status || ""),
      task_id: compact(row.task_id || ""),
      theme_code: compact(row.theme_code || ""),
      impact_direction: compact(row.impact_direction || ""),
      impact_magnitude: Number(row.impact_magnitude || 0),
      target_symbols: rawSymbols.map((value) => compact(value)).filter(Boolean),
      target_count: Number(row.target_count || rawSymbols.length || 0),
      breadth_resolved: compact(row.breadth_resolved || ""),
      generated_at: compact(row.generated_at || ""),
      strategies_submitted: Number(row.strategies_submitted || 0)
    } as LineageRow;
  });
}

export function radarCandidatesFromData(data: unknown): RadarCandidateRow[] {
  const record = data && typeof data === "object" && !Array.isArray(data) ? (data as Record<string, unknown>) : {};
  const rawRows = Array.isArray(record.candidates)
    ? record.candidates
    : Array.isArray(data)
      ? data
      : [];
  return rawRows.map((item, index) => {
    const row = (item && typeof item === "object" ? item : {}) as Record<string, unknown>;
    return {
      ...row,
      candidate_id: compact(row.candidate_id || `radar_candidate_${index}`),
      run_id: compact(row.run_id || ""),
      symbol: compact(row.symbol || row.stock_code || ""),
      stock_name: compact(row.stock_name || row.name || ""),
      tier: compact(row.tier || "observe"),
      radar_score: Number(row.radar_score || 0),
      event_id: compact(row.event_id || ""),
      event_type: compact(row.event_type || "unknown"),
      direction: compact(row.direction || "neutral"),
      summary: compact(row.summary || ""),
      source_doc_uids: Array.isArray(row.source_doc_uids) ? row.source_doc_uids.map((value) => compact(value)).filter(Boolean) : [],
      source_chain: Array.isArray(row.source_chain) ? row.source_chain : [],
      extraction: row.extraction && typeof row.extraction === "object" && !Array.isArray(row.extraction) ? row.extraction as Record<string, unknown> : {},
      confirmations: row.confirmations && typeof row.confirmations === "object" && !Array.isArray(row.confirmations) ? row.confirmations as Record<string, unknown> : {},
      risk_flags: Array.isArray(row.risk_flags) ? row.risk_flags.map((value) => compact(value)).filter(Boolean) : [],
      push_status: compact(row.push_status || "")
    } as RadarCandidateRow;
  });
}

export function numericStatus(value: Record<string, unknown> | null, key: string): number {
  if (!value) return 0;
  const raw = value[key];
  const parsed = Number(raw || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function latestRunId(value: Record<string, unknown> | null): string {
  const latest = value && typeof value.latest_run === "object" && value.latest_run !== null
    ? value.latest_run as Record<string, unknown>
    : {};
  return compact(latest.run_id || "");
}

export function radarTierLabel(value: string) {
  return RADAR_TIER_OPTIONS.find((option) => option.value === value)?.label || value || "全部级别";
}

export function outboxCount(value: Record<string, unknown> | null, status: string): number {
  const counts = value && typeof value.counts === "object" && value.counts !== null
    ? (value.counts as Record<string, unknown>)
    : {};
  const parsed = Number(counts[status] || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function intentIdFromEnvelope(data: unknown): string {
  const record = data && typeof data === "object" && !Array.isArray(data) ? (data as IntentEnvelope) : {};
  if (typeof record.intent_id === "string" && record.intent_id) return record.intent_id;
  if (record.intent && typeof record.intent.intent_id === "string") return record.intent.intent_id;
  return "";
}

export function formatTime(value?: string): string {
  if (!value || value === "-") return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function classifyEventStatus(event: FactoryEventRow): string {
  switch (event.status) {
    case "active":
      return "implemented";
    case "pending_review":
      return "warning";
    case "paused":
      return "not_loaded";
    case "expired":
      return "deprecated";
    default:
      return "info";
  }
}
