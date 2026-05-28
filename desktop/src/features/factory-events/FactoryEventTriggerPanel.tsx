// PR-G (Phase 5, 2026-05-24): Desktop strategy-factory event trigger
// console. Replaces the implicit "use the read-only EventConsolePanel"
// gap from §1 of the upgrade plan with a real ops surface that drives
// the full ``factory_event_*`` action set through the Agent ActionIntent
// chain landed in PR-F.
//
// Boundary contract (matches plan §Phase 5 acceptance):
//   - Read paths use ``factory_event_list`` / ``factory_event_preview_tasks``
//     via the ``agent_strategy_manager`` MCP tool — these are
//     ``READ_ONLY_STRATEGY_ACTIONS`` so no ActionIntent is created.
//   - Write paths (create / approve / pause / record_outcome) **always**
//     create an ActionIntent first; the operator must explicitly confirm
//     before the manager handler runs. We never call the manager write
//     handler directly from Desktop — that would bypass the dual-person
//     review and self-approval guard enforced inside
//     ``handle_factory_event_approve``.
//   - When ``controlToken`` is missing, the API client throws on intent
//     create/confirm/deny — the UI surfaces this without crashing and
//     keeps reads working.

import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Compass,
  Filter,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  Target,
  Workflow
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact, shortText } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { ToolEnvelope } from "../../types";

interface FactoryEventRow {
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

interface PreviewImpact {
  theme_code: string;
  depth: number;
  magnitude: number;
  source_path?: string;
}

interface PreviewPayload {
  event_id?: string;
  impacts?: PreviewImpact[];
  candidate_symbols?: string[];
  target_count?: number;
  warnings?: string[];
  preview_mode?: string;
}

interface LineageRow {
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

interface IntentEnvelope {
  intent?: {
    intent_id?: string;
    status?: string;
    target_action?: string;
  };
  intent_id?: string;
  status?: string;
}

interface Props {
  endpoint: string;
  apiToken: string;
  controlToken: string;
}

type TabId = "events" | "create" | "preview" | "lineage";

const STATUS_OPTIONS = ["", "pending_review", "active", "paused", "expired"];
const SOURCE_OPTIONS = ["", "manual", "news_llm", "macro_shock", "market_anomaly", "price_inference"];
const TYPE_OPTIONS = ["", "policy_shock", "earnings", "guidance", "regulation", "macro_data", "other"];
const DIRECTION_OPTIONS = ["bullish", "bearish", "neutral"];
const OUTCOME_OPTIONS = ["positive", "negative", "mixed", "no_effect"] as const;

const HIGH_INTENSITY_THRESHOLD = 0.8;

function eventListFromData(data: unknown): FactoryEventRow[] {
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

function previewFromData(data: unknown): PreviewPayload {
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

function lineageFromData(data: unknown): LineageRow[] {
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

function numericStatus(value: Record<string, unknown> | null, key: string): number {
  if (!value) return 0;
  const raw = value[key];
  const parsed = Number(raw || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function outboxCount(value: Record<string, unknown> | null, status: string): number {
  const counts = value && typeof value.counts === "object" && value.counts !== null
    ? (value.counts as Record<string, unknown>)
    : {};
  const parsed = Number(counts[status] || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function intentIdFromEnvelope(data: unknown): string {
  const record = data && typeof data === "object" && !Array.isArray(data) ? (data as IntentEnvelope) : {};
  if (typeof record.intent_id === "string" && record.intent_id) return record.intent_id;
  if (record.intent && typeof record.intent.intent_id === "string") return record.intent.intent_id;
  return "";
}

function formatTime(value?: string): string {
  if (!value || value === "-") return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function classifyEventStatus(event: FactoryEventRow): string {
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

export function FactoryEventTriggerPanel({ endpoint, apiToken, controlToken }: Props) {
  const client = useMemo(
    () => new AiaskApi({ endpoint, apiToken, controlToken }),
    [apiToken, controlToken, endpoint]
  );
  const hasControlToken = Boolean(controlToken && controlToken.trim());

  const [tab, setTab] = useState<TabId>("events");
  const [events, setEvents] = useState<FactoryEventRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("NOT_LOADED");

  const [statusFilter, setStatusFilter] = useState<string>("active");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [query, setQuery] = useState<string>("");

  const [selectedEventId, setSelectedEventId] = useState<string>("");
  const [preview, setPreview] = useState<PreviewPayload | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewMessage, setPreviewMessage] = useState<string>("");

  const [actionLog, setActionLog] = useState<Array<{ stamp: string; text: string; ok: boolean }>>([]);
  const appendLog = useCallback((text: string, ok: boolean) => {
    setActionLog((prev) => [
      { stamp: new Date().toLocaleTimeString(), text, ok },
      ...prev
    ].slice(0, 20));
  }, []);

  const [lineage, setLineage] = useState<LineageRow[]>([]);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageMessage, setLineageMessage] = useState("LINEAGE_NOT_LOADED");
  const [exposureStatus, setExposureStatus] = useState<Record<string, unknown> | null>(null);
  const [outboxStatus, setOutboxStatus] = useState<Record<string, unknown> | null>(null);
  const [bootstrapStatus, setBootstrapStatus] = useState("BOOTSTRAP_NOT_RUN");
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [maintenanceMessage, setMaintenanceMessage] = useState("MAINTENANCE_NOT_LOADED");

  // ── Create form state ────────────────────────────────────────────────
  const [formName, setFormName] = useState("");
  const [formType, setFormType] = useState("policy_shock");
  const [formSource, setFormSource] = useState("manual");
  const [formDirection, setFormDirection] = useState<"bullish" | "bearish" | "neutral">("bullish");
  const [formIntensity, setFormIntensity] = useState(0.6);
  const [formConfidence, setFormConfidence] = useState(0.6);
  const [formThemes, setFormThemes] = useState("");
  const [formValidUntil, setFormValidUntil] = useState("");
  const [formEvidenceUrl, setFormEvidenceUrl] = useState("");
  const [formEvidenceSummary, setFormEvidenceSummary] = useState("");
  const [formOperator, setFormOperator] = useState("operator_local");

  // ── Approve / pause / outcome state ──────────────────────────────────
  const [approverId, setApproverId] = useState("approver_local");
  const [outcomeValue, setOutcomeValue] = useState<(typeof OUTCOME_OPTIONS)[number]>("mixed");
  const [outcomeNotes, setOutcomeNotes] = useState("");

  const loadMaintenanceStatus = useCallback(async () => {
    setMaintenanceLoading(true);
    try {
      const [exposureEnvelope, outboxEnvelope] = await Promise.all([
        client.factoryThemeExposureStatus({}),
        client.factoryEventOutboxStatus({ limit: 20 })
      ]);
      setExposureStatus(exposureEnvelope.data || {});
      setOutboxStatus(outboxEnvelope.data || {});
      setMaintenanceMessage(
        exposureEnvelope.success && outboxEnvelope.success
          ? "MAINTENANCE_STATUS_LOADED"
          : exposureEnvelope.error || outboxEnvelope.error || "MAINTENANCE_STATUS_DEGRADED"
      );
    } catch (error) {
      setMaintenanceMessage(formatApiError(error));
    } finally {
      setMaintenanceLoading(false);
    }
  }, [client]);

  const loadLineage = useCallback(async () => {
    setLineageLoading(true);
    try {
      const envelope = await client.factoryEventLineage({
        event_id: selectedEventId,
        limit: 100
      });
      setLineage(lineageFromData(envelope.data));
      setLineageMessage(envelope.success ? "LINEAGE_LOADED" : envelope.error || "LINEAGE_DEGRADED");
    } catch (error) {
      setLineageMessage(formatApiError(error));
    } finally {
      setLineageLoading(false);
    }
  }, [client, selectedEventId]);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const envelope = await client.factoryEventList({
        status: statusFilter,
        source: sourceFilter,
        event_type: typeFilter,
        limit: 100
      });
      setEvents(eventListFromData(envelope.data));
      setMessage(envelope.success ? "EVENTS_LOADED" : envelope.error || "EVENTS_DEGRADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }, [client, sourceFilter, statusFilter, typeFilter]);

  useEffect(() => {
    loadEvents().catch(() => undefined);
  }, [loadEvents]);

  useEffect(() => {
    loadMaintenanceStatus().catch(() => undefined);
  }, [loadMaintenanceStatus]);

  useEffect(() => {
    loadLineage().catch(() => undefined);
  }, [loadLineage]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return events;
    return events.filter((event) => JSON.stringify(event).toLowerCase().includes(needle));
  }, [events, query]);

  const selectedEvent = useMemo(
    () => filtered.find((event) => event.event_id === selectedEventId) || null,
    [filtered, selectedEventId]
  );

  const runPreview = useCallback(
    async (eventId: string) => {
      if (!eventId) return;
      setPreviewLoading(true);
      setPreviewMessage("");
      try {
        const envelope = await client.factoryEventPreviewTasks(eventId);
        setPreview(previewFromData(envelope.data));
        if (!envelope.success) {
          setPreviewMessage(envelope.error || "PREVIEW_DEGRADED");
        }
      } catch (error) {
        setPreviewMessage(formatApiError(error));
      } finally {
        setPreviewLoading(false);
      }
    },
    [client]
  );

  const handleSelectEvent = useCallback(
    async (eventId: string) => {
      setSelectedEventId(eventId);
      setTab("preview");
      await runPreview(eventId);
    },
    [runPreview]
  );

  const requireControlToken = useCallback(() => {
    if (!hasControlToken) {
      appendLog("缺少控制令牌 Control token，写操作需要确认。", false);
      return false;
    }
    return true;
  }, [appendLog, hasControlToken]);

  const handleCreate = useCallback(async () => {
    if (!requireControlToken()) return;
    if (!formName.trim()) {
      appendLog("请填写事件名称。", false);
      return;
    }
    const themes = formThemes
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    if (themes.length === 0) {
      appendLog("至少需要填写一个 primary theme。", false);
      return;
    }
    const payload: Record<string, unknown> = {
      event_name: formName.trim(),
      event_type: formType,
      source: formSource,
      direction: formDirection,
      intensity: formIntensity,
      confidence: formConfidence,
      primary_themes: themes,
      operator_id: formOperator.trim() || "operator_local"
    };
    if (formValidUntil) payload.valid_until = formValidUntil;
    if (formEvidenceUrl) payload.evidence_url = formEvidenceUrl;
    if (formEvidenceSummary) payload.evidence_summary = formEvidenceSummary;

    const rationale = formIntensity >= HIGH_INTENSITY_THRESHOLD
      ? `高强度事件 (${formIntensity.toFixed(2)})，进入 pending dual-person review。`
      : "操作者从 Desktop 创建 factory event。";

    try {
      const envelope = await client.factoryEventCreateIntent(payload, rationale);
      const intentId = intentIdFromEnvelope(envelope.data);
      if (intentId) {
        appendLog(`意图 ${intentId} 已创建，等待确认。`, true);
      } else {
        appendLog("意图已创建，但 envelope 中没有 intent_id。", envelope.success);
      }
    } catch (error) {
      appendLog(`创建失败：${formatApiError(error)}`, false);
    }
  }, [
    appendLog,
    client,
    formConfidence,
    formDirection,
    formEvidenceSummary,
    formEvidenceUrl,
    formIntensity,
    formName,
    formOperator,
    formSource,
    formThemes,
    formType,
    formValidUntil,
    requireControlToken
  ]);

  const confirmIntentNow = useCallback(
    async (intentId: string) => {
      try {
        const envelope = await client.confirmIntent(intentId);
        if (envelope.success) {
          appendLog(`意图 ${intentId} 已确认。`, true);
          await loadEvents();
        } else {
          appendLog(`确认失败：${envelope.error || "unknown"}`, false);
        }
      } catch (error) {
        appendLog(`确认失败：${formatApiError(error)}`, false);
      }
    },
    [appendLog, client, loadEvents]
  );

  const handleCreateAndConfirm = useCallback(async () => {
    if (!requireControlToken()) return;
    if (!formName.trim()) {
      appendLog("请填写事件名称。", false);
      return;
    }
    const themes = formThemes
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    if (themes.length === 0) {
      appendLog("至少需要填写一个 primary theme。", false);
      return;
    }
    const payload: Record<string, unknown> = {
      event_name: formName.trim(),
      event_type: formType,
      source: formSource,
      direction: formDirection,
      intensity: formIntensity,
      confidence: formConfidence,
      primary_themes: themes,
      operator_id: formOperator.trim() || "operator_local"
    };
    if (formValidUntil) payload.valid_until = formValidUntil;
    try {
      const envelope = await client.factoryEventCreateIntent(payload, "Desktop create + confirm.");
      const intentId = intentIdFromEnvelope(envelope.data);
      if (!intentId) {
        appendLog("创建失败：缺少 intent_id。", false);
        return;
      }
      await confirmIntentNow(intentId);
    } catch (error) {
      appendLog(`创建并确认失败：${formatApiError(error)}`, false);
    }
  }, [
    appendLog,
    client,
    confirmIntentNow,
    formConfidence,
    formDirection,
    formIntensity,
    formName,
    formOperator,
    formSource,
    formThemes,
    formType,
    formValidUntil,
    requireControlToken
  ]);

  const handleApprove = useCallback(
    async (eventId: string) => {
      if (!requireControlToken()) return;
      if (!approverId.trim()) {
        appendLog("请填写 approver id。", false);
        return;
      }
      try {
        const envelope = await client.factoryEventApproveIntent(eventId, approverId.trim(), "Desktop approve.");
        const intentId = intentIdFromEnvelope(envelope.data);
        if (intentId) {
          await confirmIntentNow(intentId);
        } else {
          appendLog("批准意图已创建，但缺少 intent_id。", envelope.success);
        }
      } catch (error) {
        appendLog(`批准失败：${formatApiError(error)}`, false);
      }
    },
    [appendLog, approverId, client, confirmIntentNow, requireControlToken]
  );

  const handlePause = useCallback(
    async (eventId: string) => {
      if (!requireControlToken()) return;
      try {
        const envelope = await client.factoryEventUpdateIntent(
          eventId,
          { status: "paused" },
          "Desktop pause event."
        );
        const intentId = intentIdFromEnvelope(envelope.data);
        if (intentId) {
          await confirmIntentNow(intentId);
        } else {
          appendLog("暂停意图已创建，但缺少 intent_id。", envelope.success);
        }
      } catch (error) {
        appendLog(`暂停失败：${formatApiError(error)}`, false);
      }
    },
    [appendLog, client, confirmIntentNow, requireControlToken]
  );

  const handleRecordOutcome = useCallback(
    async (eventId: string) => {
      if (!requireControlToken()) return;
      if (!outcomeValue) {
        appendLog("请填写 outcome 枚举。", false);
        return;
      }
      try {
        const envelope = await client.factoryEventRecordOutcomeIntent(
          eventId,
          { actual_outcome: outcomeValue, outcome_notes: outcomeNotes.trim() },
          "Desktop record outcome."
        );
        const intentId = intentIdFromEnvelope(envelope.data);
        if (intentId) {
          await confirmIntentNow(intentId);
        } else {
          appendLog("结果意图已创建，但缺少 intent_id。", envelope.success);
        }
      } catch (error) {
        appendLog(`记录结果失败：${formatApiError(error)}`, false);
      }
    },
    [appendLog, client, confirmIntentNow, outcomeNotes, outcomeValue, requireControlToken]
  );

  // ── Tab content renderers ────────────────────────────────────────────

  const createAndConfirmMaintenanceIntent = useCallback(
    async (
      label: string,
      createIntent: () => Promise<ToolEnvelope & { data: Record<string, unknown> }>
    ) => {
      if (!requireControlToken()) return;
      setMaintenanceLoading(true);
      try {
        const envelope = await createIntent();
        const intentId = intentIdFromEnvelope(envelope.data);
        if (!intentId) {
          appendLog(`${label} 意图缺少 intent_id。`, false);
          return;
        }
        const confirmed = await client.confirmIntent(intentId);
        if (confirmed.success) {
          appendLog(`${label} 意图 ${intentId} 已确认。`, true);
          if (label.includes("Bootstrap")) {
            setBootstrapStatus("BOOTSTRAP_CONFIRMED");
          }
          await Promise.all([loadMaintenanceStatus(), loadLineage()]);
        } else {
          appendLog(`${label} 确认失败：${confirmed.error || "unknown"}`, false);
        }
      } catch (error) {
        appendLog(`${label} 失败：${formatApiError(error)}`, false);
      } finally {
        setMaintenanceLoading(false);
      }
    },
    [appendLog, client, loadLineage, loadMaintenanceStatus, requireControlToken]
  );

  const handleBootstrap = useCallback(() => {
    setBootstrapStatus("BOOTSTRAP_PENDING");
    createAndConfirmMaintenanceIntent("初始化 Bootstrap", () =>
      client.factoryEventBootstrapIntent({ batch_size: 1000, refresh_exposure: true })
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const handleExposureRefresh = useCallback(() => {
    createAndConfirmMaintenanceIntent("刷新暴露", () =>
      client.factoryThemeExposureRefreshIntent({ batch_size: 1000 })
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const handleOutboxDrain = useCallback(() => {
    createAndConfirmMaintenanceIntent("排空 outbox", () =>
      client.factoryEventOutboxDrainIntent({ limit: 20 })
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const handleRegressionRun = useCallback(() => {
    createAndConfirmMaintenanceIntent("主题回归", () =>
      client.factoryThemeRegressionRunIntent({})
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const renderMaintenancePanel = () => (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>{maintenanceMessage}</span>
          <h3>暴露与 outbox 状态</h3>
        </div>
        <RefreshCw size={18} className={maintenanceLoading ? "spin" : ""} />
      </div>
      <div className="status-cluster">
        <StatusBadge status="info" label={`${numericStatus(exposureStatus, "row_count")} 行暴露`} />
        <StatusBadge status="info" label={`${numericStatus(exposureStatus, "theme_count")} 个主题`} />
        <StatusBadge status={outboxCount(outboxStatus, "failed") ? "warning" : "implemented"} label={`${outboxCount(outboxStatus, "failed")} 条 outbox 失败`} />
        <StatusBadge status="info" label={`${outboxCount(outboxStatus, "processed")} 条已处理`} />
        <StatusBadge status={bootstrapStatus === "BOOTSTRAP_CONFIRMED" ? "implemented" : "info"} label={bootstrapStatus} />
      </div>
      <div className="header-actions">
        <button className="small-button" type="button" onClick={loadMaintenanceStatus} disabled={maintenanceLoading}>
          <RefreshCw size={13} className={maintenanceLoading ? "spin" : ""} />
          刷新状态
        </button>
        <button className="small-button" type="button" onClick={handleBootstrap} disabled={!hasControlToken || maintenanceLoading}>
          <Compass size={13} />
          初始化 Bootstrap
        </button>
        <button className="small-button" type="button" onClick={handleExposureRefresh} disabled={!hasControlToken || maintenanceLoading}>
          <Target size={13} />
          刷新暴露
        </button>
        <button className="small-button" type="button" onClick={handleOutboxDrain} disabled={!hasControlToken || maintenanceLoading}>
          <Workflow size={13} />
          排空 outbox
        </button>
        <button className="small-button" type="button" onClick={handleRegressionRun} disabled={!hasControlToken || maintenanceLoading}>
          <Compass size={13} />
          运行回归
        </button>
      </div>
      {!hasControlToken && (
        <div className="notice warn">
          <AlertTriangle size={15} />
          维护类写操作需要控制令牌 Control token；只读状态仍可查看。
        </div>
      )}
    </section>
  );

  const renderEventsTab = () => (
    <>
      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>筛选</span>
            <h3>查找要查看或触发的事件</h3>
          </div>
          <Filter size={18} />
        </div>
        <div className="event-filter-grid">
          <label>
            <span>状态</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              {STATUS_OPTIONS.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "全部状态"}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>来源</span>
            <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
              {SOURCE_OPTIONS.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "全部来源"}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>类型</span>
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              {TYPE_OPTIONS.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "全部类型"}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>搜索</span>
            <div className="search-field">
              <Search size={14} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="主题 / id / 名称" />
            </div>
          </label>
        </div>
      </section>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>{filtered.length} 个匹配事件</span>
            <h3>当前生效的事件注入</h3>
          </div>
          <Workflow size={18} />
        </div>
        <div className="event-list">
          {filtered.map((event) => (
            <article className="event-card" key={event.event_id}>
              <div className="event-card-main">
                <div className="event-card-icon">
                  <Compass size={15} />
                </div>
                <div>
                  <span>
                    {event.event_type} / {event.event_source}
                  </span>
                  <strong>{event.event_name}</strong>
                  <p>
                    {shortText(event.primary_themes.join(", ") || "(无主题)", 200)} / 强度{" "}
                    {event.intensity.toFixed(2)} / {event.direction}
                  </p>
                </div>
              </div>
              <div className="event-card-meta">
                <StatusBadge status={classifyEventStatus(event)} label={event.status} />
                <small>{formatTime(event.created_at)}</small>
              </div>
              <div className="event-card-actions">
                <button className="small-button" type="button" onClick={() => handleSelectEvent(event.event_id)}>
                  <Target size={13} />
                  预览
                </button>
                {event.status === "pending_review" && (
                  <button
                    className="small-button"
                    type="button"
                    onClick={() => handleApprove(event.event_id)}
                    disabled={!hasControlToken}
                  >
                    <CheckCircle2 size={13} />
                    批准
                  </button>
                )}
                {event.status === "active" && (
                  <button
                    className="small-button"
                    type="button"
                    onClick={() => handlePause(event.event_id)}
                    disabled={!hasControlToken}
                  >
                    <ShieldAlert size={13} />
                    暂停
                  </button>
                )}
              </div>
              <details className="raw-details">
                <summary>证据 payload</summary>
                <JsonPanel value={event} />
              </details>
            </article>
          ))}
          {!filtered.length && (
            <div className="empty-mini">
              <ClipboardCheck size={24} />
              <span>没有匹配当前筛选条件的事件。请调整筛选或刷新。</span>
            </div>
          )}
        </div>
      </section>
    </>
  );

  const renderCreateTab = () => (
    <section className="capability-section">
        <div className="section-header">
          <div>
          <span>创建事件</span>
          <h3>所有写操作都通过 ActionIntent</h3>
        </div>
        <Plus size={18} />
      </div>
      {!hasControlToken && (
        <div className="notice warn">
          <AlertTriangle size={15} />
          缺少控制令牌 Control token。读取仍可使用，但“创建”/“批准”/“暂停”无法派发意图。
        </div>
      )}
      <div className="event-filter-grid">
        <label>
          <span>事件名称</span>
          <input value={formName} onChange={(event) => setFormName(event.target.value)} placeholder="e.g. 稀土出口管制" />
        </label>
        <label>
          <span>类型</span>
          <select value={formType} onChange={(event) => setFormType(event.target.value)}>
            {TYPE_OPTIONS.filter(Boolean).map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          <span>来源</span>
          <select value={formSource} onChange={(event) => setFormSource(event.target.value)}>
            {SOURCE_OPTIONS.filter(Boolean).map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          <span>方向</span>
          <select value={formDirection} onChange={(event) => setFormDirection(event.target.value as "bullish" | "bearish" | "neutral")}>
            {DIRECTION_OPTIONS.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          <span>强度 Intensity (0-1)</span>
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={formIntensity}
            onChange={(event) => setFormIntensity(Math.max(0, Math.min(1, Number(event.target.value) || 0)))}
          />
        </label>
        <label>
          <span>置信度 Confidence (0-1)</span>
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={formConfidence}
            onChange={(event) => setFormConfidence(Math.max(0, Math.min(1, Number(event.target.value) || 0)))}
          />
        </label>
        <label>
          <span>Primary themes（逗号分隔）</span>
          <input value={formThemes} onChange={(event) => setFormThemes(event.target.value)} placeholder="critical_minerals, rare_earth" />
        </label>
        <label>
          <span>有效期至 (ISO)</span>
          <input value={formValidUntil} onChange={(event) => setFormValidUntil(event.target.value)} placeholder="2026-06-24T08:00:00Z" />
        </label>
        <label>
          <span>证据 URL</span>
          <input value={formEvidenceUrl} onChange={(event) => setFormEvidenceUrl(event.target.value)} placeholder="https://..." />
        </label>
        <label>
          <span>证据摘要</span>
          <input value={formEvidenceSummary} onChange={(event) => setFormEvidenceSummary(event.target.value)} placeholder="简要背景" />
        </label>
        <label>
          <span>操作者 id</span>
          <input value={formOperator} onChange={(event) => setFormOperator(event.target.value)} />
        </label>
      </div>
      <div className="header-actions">
        <button
          className="small-button"
          type="button"
          onClick={handleCreate}
          disabled={!hasControlToken}
        >
          <Plus size={13} />
          仅创建意图
        </button>
        <button
          className="small-button"
          type="button"
          onClick={handleCreateAndConfirm}
          disabled={!hasControlToken || formIntensity >= HIGH_INTENSITY_THRESHOLD}
          title={
            formIntensity >= HIGH_INTENSITY_THRESHOLD
              ? "高强度事件必须经过双人复核，只能先创建意图。"
              : undefined
          }
        >
          <CheckCircle2 size={13} />
          创建并确认
        </button>
      </div>
      {formIntensity >= HIGH_INTENSITY_THRESHOLD && (
        <div className="notice warn">
          <ShieldAlert size={15} />
          强度 {">="} {HIGH_INTENSITY_THRESHOLD.toFixed(2)} 会强制进入 `pending_review`，只能使用“仅创建意图”。
        </div>
      )}
    </section>
  );

  const renderPreviewTab = () => (
    <section className="capability-section">
        <div className="section-header">
          <div>
          <span>预览</span>
          <h3>BFS 传播与候选篮子</h3>
        </div>
        <Target size={18} />
      </div>
      <div className="event-filter-grid">
        <label>
          <span>事件 id</span>
          <input
            value={selectedEventId}
            onChange={(event) => setSelectedEventId(event.target.value)}
            placeholder="evt_..."
          />
        </label>
        <label>
          <span>&nbsp;</span>
          <button
            className="small-button"
            type="button"
            onClick={() => runPreview(selectedEventId)}
            disabled={!selectedEventId || previewLoading}
          >
            <RefreshCw size={13} className={previewLoading ? "spin" : ""} />
            运行预览
          </button>
        </label>
        <label>
          <span>批准人 id（用于批准）</span>
          <input value={approverId} onChange={(event) => setApproverId(event.target.value)} placeholder="approver_..." />
        </label>
        <label>
          <span>实际结果</span>
          <select value={outcomeValue} onChange={(event) => setOutcomeValue(event.target.value as (typeof OUTCOME_OPTIONS)[number])}>
            {OUTCOME_OPTIONS.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          <span>结果备注</span>
          <input value={outcomeNotes} onChange={(event) => setOutcomeNotes(event.target.value)} placeholder="实际市场反应..." />
        </label>
      </div>
      {previewMessage && (
        <div className="notice warn">
          <AlertTriangle size={15} />
          {previewMessage}
        </div>
      )}
      {selectedEvent && (
        <div className="header-actions">
          <button
            className="small-button"
            type="button"
            onClick={() => handleApprove(selectedEvent.event_id)}
            disabled={!hasControlToken || selectedEvent.status !== "pending_review"}
          >
            <CheckCircle2 size={13} />
            批准 {selectedEvent.event_id}
          </button>
          <button
            className="small-button"
            type="button"
            onClick={() => handlePause(selectedEvent.event_id)}
            disabled={!hasControlToken || selectedEvent.status !== "active"}
          >
            <ShieldAlert size={13} />
            暂停
          </button>
          <button
            className="small-button"
            type="button"
            onClick={() => handleRecordOutcome(selectedEvent.event_id)}
            disabled={!hasControlToken || !outcomeValue}
          >
            <ClipboardCheck size={13} />
            记录结果
          </button>
        </div>
      )}
      {preview && (
        <>
          <div className="status-cluster">
            <StatusBadge status="implemented" label={`${preview.candidate_symbols?.length || 0} 个候选标的`} />
            <StatusBadge status={preview.warnings?.length ? "warning" : "implemented"} label={`${preview.warnings?.length || 0} 条警告`} />
            <StatusBadge status="info" label={preview.preview_mode || "real_bfs"} />
          </div>
          <details className="raw-details" open>
            <summary>主题影响 ({preview.impacts?.length || 0})</summary>
            <JsonPanel value={preview.impacts || []} />
          </details>
          <details className="raw-details">
            <summary>候选标的 ({preview.candidate_symbols?.length || 0})</summary>
            <JsonPanel value={preview.candidate_symbols || []} />
          </details>
          {preview.warnings && preview.warnings.length > 0 && (
            <details className="raw-details" open>
              <summary>警告</summary>
              <JsonPanel value={preview.warnings} />
            </details>
          )}
        </>
      )}
    </section>
  );

  const renderLineageTab = () => (
    <>
      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>{lineageMessage}</span>
            <h3>已持久化的事件血缘</h3>
          </div>
          <Workflow size={18} />
        </div>
        <div className="header-actions">
          <label>
            <span>事件 id 筛选</span>
            <input
              value={selectedEventId}
              onChange={(event) => setSelectedEventId(event.target.value)}
              placeholder="全部事件"
            />
          </label>
          <button className="small-button" type="button" onClick={loadLineage} disabled={lineageLoading}>
            <RefreshCw size={13} className={lineageLoading ? "spin" : ""} />
            刷新血缘
          </button>
        </div>
        <div className="event-list">
          {lineage.map((row) => (
            <article className="event-card" key={`${row.lineage_id}_${row.task_id}`}>
              <div className="event-card-main">
                <div className="event-card-icon">
                  <Workflow size={15} />
                </div>
                <div>
                  <span>
                    {row.event_id} / {row.event_status || "event"} / {row.theme_code}
                  </span>
                  <strong>{row.task_id}</strong>
                  <p>
                    {row.impact_direction || "neutral"} {Number(row.impact_magnitude || 0).toFixed(2)}
                    {" "}/ {row.target_count || 0} 个目标 / {row.breadth_resolved || "unknown"}
                  </p>
                </div>
              </div>
              <div className="event-card-meta">
                <StatusBadge
                  status={row.gate_3_passed ? "implemented" : row.gate_1_passed ? "info" : "warning"}
                  label={`已提交 ${row.strategies_submitted || 0}`}
                />
                <small>{formatTime(row.generated_at)}</small>
              </div>
              <details className="raw-details">
                <summary>血缘 payload</summary>
                <JsonPanel value={row} />
              </details>
            </article>
          ))}
          {!lineage.length && (
            <div className="empty-mini">
              <ClipboardCheck size={24} />
              <span>没有符合当前筛选条件的持久化血缘记录。</span>
            </div>
          )}
        </div>
      </section>

      <section className="capability-section">
      <div className="section-header">
        <div>
          <span>操作日志</span>
          <h3>最近意图派发</h3>
        </div>
        <Workflow size={18} />
      </div>
      <div className="event-list">
        {actionLog.map((entry, index) => (
          <article className="event-card" key={`${entry.stamp}_${index}`}>
            <div className="event-card-main">
              <div className="event-card-icon">
                {entry.ok ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
              </div>
              <div>
                <span>{entry.stamp}</span>
                <strong>{entry.text}</strong>
              </div>
            </div>
            <div className="event-card-meta">
              <StatusBadge status={entry.ok ? "implemented" : "warning"} label={entry.ok ? "成功" : "已阻塞"} />
            </div>
          </article>
        ))}
        {!actionLog.length && (
          <div className="empty-mini">
            <ClipboardCheck size={24} />
            <span>暂无派发记录。创建或批准事件后可在这里查看血缘记录。</span>
          </div>
        )}
      </div>
      <div className="notice">
        <Workflow size={15} />
        持久化血缘（event -&gt; task -&gt; gate -&gt; strategy/outcome）通过 `factory_event_lineage`
        读取 `strategy_factory_event_task_lineage`。
      </div>
      </section>
    </>
  );

  // ── Render ───────────────────────────────────────────────────────────

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "events", label: "事件" },
    { id: "create", label: "创建" },
    { id: "preview", label: "预览" },
    { id: "lineage", label: "血缘" }
  ];

  return (
    <section className="capabilities-workspace" data-testid="factory-event-trigger-panel">
      <header className="capabilities-header">
        <div>
          <span>工厂事件触发器</span>
          <h1>注入、批准并检查事件驱动研究</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : "implemented"} label={message} />
          <button className="small-button" type="button" disabled={loading} onClick={loadEvents}>
            <RefreshCw size={14} className={loading ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <section className="capability-banner">
            <div>
              <span>Agent 受控事件控制台</span>
              <h2>{filtered.length} 个事件 / {events.filter((e) => e.status === "pending_review").length} 个待复核</h2>
              <p>
                所有写操作（创建 / 批准 / 暂停 / 记录结果）都会走 PR-F 接入的 `ActionIntent` 链路。本面板不会直接调用 manager
                handler，以免绕过 `handle_factory_event_approve` 中的双人复核与自审批保护。
              </p>
            </div>
            <div className="status-cluster">
              <StatusBadge status={hasControlToken ? "implemented" : "warning"} label={hasControlToken ? "控制令牌已就绪" : "只读模式（无控制令牌）"} />
              <StatusBadge status="info" label={`Tab: ${tab}`} />
            </div>
          </section>

          {renderMaintenancePanel()}

          <div className="header-actions" role="tablist">
            {tabs.map((entry) => (
              <button
                key={entry.id}
                role="tab"
                aria-selected={tab === entry.id}
                className="small-button"
                type="button"
                onClick={() => setTab(entry.id)}
              >
                {entry.label}
              </button>
            ))}
          </div>

          {message.startsWith("AIASK_") && (
            <div className="notice warn">
              <AlertTriangle size={15} />
              {message}. Agent API 可达后读取会自动恢复。
            </div>
          )}

          {tab === "events" && renderEventsTab()}
          {tab === "create" && renderCreateTab()}
          {tab === "preview" && renderPreviewTab()}
          {tab === "lineage" && renderLineageTab()}
        </div>
      </div>
    </section>
  );
}
