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
  const [outcomeText, setOutcomeText] = useState("");

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
        event_source: sourceFilter,
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
      appendLog("Control token missing — write actions require confirmation.", false);
      return false;
    }
    return true;
  }, [appendLog, hasControlToken]);

  const handleCreate = useCallback(async () => {
    if (!requireControlToken()) return;
    if (!formName.trim()) {
      appendLog("Event name is required.", false);
      return;
    }
    const themes = formThemes
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    if (themes.length === 0) {
      appendLog("At least one primary theme is required.", false);
      return;
    }
    const payload: Record<string, unknown> = {
      event_name: formName.trim(),
      event_type: formType,
      event_source: formSource,
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
      ? `High-intensity event (${formIntensity.toFixed(2)}) — pending dual-person review.`
      : `Operator-initiated factory event create from Desktop.`;

    try {
      const envelope = await client.factoryEventCreateIntent(payload, rationale);
      const intentId = intentIdFromEnvelope(envelope.data);
      if (intentId) {
        appendLog(`Intent ${intentId} created (awaiting confirmation).`, true);
      } else {
        appendLog("Intent created (no intent_id in envelope).", envelope.success);
      }
    } catch (error) {
      appendLog(`Create failed: ${formatApiError(error)}`, false);
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
          appendLog(`Intent ${intentId} confirmed.`, true);
          await loadEvents();
        } else {
          appendLog(`Confirm failed: ${envelope.error || "unknown"}`, false);
        }
      } catch (error) {
        appendLog(`Confirm failed: ${formatApiError(error)}`, false);
      }
    },
    [appendLog, client, loadEvents]
  );

  const handleCreateAndConfirm = useCallback(async () => {
    if (!requireControlToken()) return;
    if (!formName.trim()) {
      appendLog("Event name is required.", false);
      return;
    }
    const themes = formThemes
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    if (themes.length === 0) {
      appendLog("At least one primary theme is required.", false);
      return;
    }
    const payload: Record<string, unknown> = {
      event_name: formName.trim(),
      event_type: formType,
      event_source: formSource,
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
        appendLog("Create failed: missing intent_id.", false);
        return;
      }
      await confirmIntentNow(intentId);
    } catch (error) {
      appendLog(`Create+confirm failed: ${formatApiError(error)}`, false);
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
        appendLog("Approver id is required.", false);
        return;
      }
      try {
        const envelope = await client.factoryEventApproveIntent(eventId, approverId.trim(), "Desktop approve.");
        const intentId = intentIdFromEnvelope(envelope.data);
        if (intentId) {
          await confirmIntentNow(intentId);
        } else {
          appendLog("Approve intent created without intent_id.", envelope.success);
        }
      } catch (error) {
        appendLog(`Approve failed: ${formatApiError(error)}`, false);
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
          appendLog("Pause intent created without intent_id.", envelope.success);
        }
      } catch (error) {
        appendLog(`Pause failed: ${formatApiError(error)}`, false);
      }
    },
    [appendLog, client, confirmIntentNow, requireControlToken]
  );

  const handleRecordOutcome = useCallback(
    async (eventId: string) => {
      if (!requireControlToken()) return;
      if (!outcomeText.trim()) {
        appendLog("Outcome description is required.", false);
        return;
      }
      try {
        const envelope = await client.factoryEventRecordOutcomeIntent(
          eventId,
          { outcome_description: outcomeText.trim() },
          "Desktop record outcome."
        );
        const intentId = intentIdFromEnvelope(envelope.data);
        if (intentId) {
          await confirmIntentNow(intentId);
        } else {
          appendLog("Outcome intent created without intent_id.", envelope.success);
        }
      } catch (error) {
        appendLog(`Outcome failed: ${formatApiError(error)}`, false);
      }
    },
    [appendLog, client, confirmIntentNow, outcomeText, requireControlToken]
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
          appendLog(`${label} intent missing intent_id.`, false);
          return;
        }
        const confirmed = await client.confirmIntent(intentId);
        if (confirmed.success) {
          appendLog(`${label} intent ${intentId} confirmed.`, true);
          await Promise.all([loadMaintenanceStatus(), loadLineage()]);
        } else {
          appendLog(`${label} confirm failed: ${confirmed.error || "unknown"}`, false);
        }
      } catch (error) {
        appendLog(`${label} failed: ${formatApiError(error)}`, false);
      } finally {
        setMaintenanceLoading(false);
      }
    },
    [appendLog, client, loadLineage, loadMaintenanceStatus, requireControlToken]
  );

  const handleExposureRefresh = useCallback(() => {
    createAndConfirmMaintenanceIntent("Exposure refresh", () =>
      client.factoryThemeExposureRefreshIntent({ batch_size: 1000 })
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const handleOutboxDrain = useCallback(() => {
    createAndConfirmMaintenanceIntent("Outbox drain", () =>
      client.factoryEventOutboxDrainIntent({ limit: 20 })
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const handleRegressionRun = useCallback(() => {
    createAndConfirmMaintenanceIntent("Theme regression", () =>
      client.factoryThemeRegressionRunIntent({})
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const renderMaintenancePanel = () => (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>{maintenanceMessage}</span>
          <h3>Exposure and outbox status</h3>
        </div>
        <RefreshCw size={18} className={maintenanceLoading ? "spin" : ""} />
      </div>
      <div className="status-cluster">
        <StatusBadge status="info" label={`${numericStatus(exposureStatus, "row_count")} exposure rows`} />
        <StatusBadge status="info" label={`${numericStatus(exposureStatus, "theme_count")} themes`} />
        <StatusBadge status={outboxCount(outboxStatus, "failed") ? "warning" : "implemented"} label={`${outboxCount(outboxStatus, "failed")} failed outbox`} />
        <StatusBadge status="info" label={`${outboxCount(outboxStatus, "processed")} processed`} />
      </div>
      <div className="header-actions">
        <button className="small-button" type="button" onClick={loadMaintenanceStatus} disabled={maintenanceLoading}>
          <RefreshCw size={13} className={maintenanceLoading ? "spin" : ""} />
          Refresh status
        </button>
        <button className="small-button" type="button" onClick={handleExposureRefresh} disabled={!hasControlToken || maintenanceLoading}>
          <Target size={13} />
          Refresh exposure
        </button>
        <button className="small-button" type="button" onClick={handleOutboxDrain} disabled={!hasControlToken || maintenanceLoading}>
          <Workflow size={13} />
          Drain outbox
        </button>
        <button className="small-button" type="button" onClick={handleRegressionRun} disabled={!hasControlToken || maintenanceLoading}>
          <Compass size={13} />
          Run regression
        </button>
      </div>
      {!hasControlToken && (
        <div className="notice warn">
          <AlertTriangle size={15} />
          Maintenance writes require a control token; read-only status remains available.
        </div>
      )}
    </section>
  );

  const renderEventsTab = () => (
    <>
      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>Filters</span>
            <h3>Find an event to inspect or trigger</h3>
          </div>
          <Filter size={18} />
        </div>
        <div className="event-filter-grid">
          <label>
            <span>Status</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              {STATUS_OPTIONS.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "all statuses"}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Source</span>
            <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
              {SOURCE_OPTIONS.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "all sources"}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Type</span>
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              {TYPE_OPTIONS.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "all types"}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Search</span>
            <div className="search-field">
              <Search size={14} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="theme / id / name" />
            </div>
          </label>
        </div>
      </section>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>{filtered.length} matching events</span>
            <h3>Active injections</h3>
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
                    {shortText(event.primary_themes.join(", ") || "(no themes)", 200)} / intensity{" "}
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
                  Preview
                </button>
                {event.status === "pending_review" && (
                  <button
                    className="small-button"
                    type="button"
                    onClick={() => handleApprove(event.event_id)}
                    disabled={!hasControlToken}
                  >
                    <CheckCircle2 size={13} />
                    Approve
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
                    Pause
                  </button>
                )}
              </div>
              <details className="raw-details">
                <summary>Evidence payload</summary>
                <JsonPanel value={event} />
              </details>
            </article>
          ))}
          {!filtered.length && (
            <div className="empty-mini">
              <ClipboardCheck size={24} />
              <span>No events match the current filters. Adjust filters or refresh.</span>
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
          <span>Create event</span>
          <h3>All writes go through ActionIntent</h3>
        </div>
        <Plus size={18} />
      </div>
      {!hasControlToken && (
        <div className="notice warn">
          <AlertTriangle size={15} />
          Control token is missing. Reads still work, but ``Create`` / ``Approve`` / ``Pause`` cannot dispatch intents.
        </div>
      )}
      <div className="event-filter-grid">
        <label>
          <span>Event name</span>
          <input value={formName} onChange={(event) => setFormName(event.target.value)} placeholder="e.g. 稀土出口管制" />
        </label>
        <label>
          <span>Type</span>
          <select value={formType} onChange={(event) => setFormType(event.target.value)}>
            {TYPE_OPTIONS.filter(Boolean).map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Source</span>
          <select value={formSource} onChange={(event) => setFormSource(event.target.value)}>
            {SOURCE_OPTIONS.filter(Boolean).map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Direction</span>
          <select value={formDirection} onChange={(event) => setFormDirection(event.target.value as "bullish" | "bearish" | "neutral")}>
            {DIRECTION_OPTIONS.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Intensity (0–1)</span>
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
          <span>Confidence (0–1)</span>
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
          <span>Primary themes (comma-separated)</span>
          <input value={formThemes} onChange={(event) => setFormThemes(event.target.value)} placeholder="critical_minerals, rare_earth" />
        </label>
        <label>
          <span>Valid until (ISO)</span>
          <input value={formValidUntil} onChange={(event) => setFormValidUntil(event.target.value)} placeholder="2026-06-24T08:00:00Z" />
        </label>
        <label>
          <span>Evidence URL</span>
          <input value={formEvidenceUrl} onChange={(event) => setFormEvidenceUrl(event.target.value)} placeholder="https://..." />
        </label>
        <label>
          <span>Evidence summary</span>
          <input value={formEvidenceSummary} onChange={(event) => setFormEvidenceSummary(event.target.value)} placeholder="brief context" />
        </label>
        <label>
          <span>Operator id</span>
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
          Create intent only
        </button>
        <button
          className="small-button"
          type="button"
          onClick={handleCreateAndConfirm}
          disabled={!hasControlToken || formIntensity >= HIGH_INTENSITY_THRESHOLD}
          title={
            formIntensity >= HIGH_INTENSITY_THRESHOLD
              ? "High-intensity events must go through dual-person review (intent only)."
              : undefined
          }
        >
          <CheckCircle2 size={13} />
          Create + confirm
        </button>
      </div>
      {formIntensity >= HIGH_INTENSITY_THRESHOLD && (
        <div className="notice warn">
          <ShieldAlert size={15} />
          Intensity ≥ {HIGH_INTENSITY_THRESHOLD.toFixed(2)} forces ``pending_review`` — only ``Create intent only`` is enabled.
        </div>
      )}
    </section>
  );

  const renderPreviewTab = () => (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>Preview</span>
          <h3>BFS propagation + candidate basket</h3>
        </div>
        <Target size={18} />
      </div>
      <div className="event-filter-grid">
        <label>
          <span>Event id</span>
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
            Run preview
          </button>
        </label>
        <label>
          <span>Approver id (for approve)</span>
          <input value={approverId} onChange={(event) => setApproverId(event.target.value)} placeholder="approver_..." />
        </label>
        <label>
          <span>Outcome description</span>
          <input value={outcomeText} onChange={(event) => setOutcomeText(event.target.value)} placeholder="actual market response..." />
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
            Approve {selectedEvent.event_id}
          </button>
          <button
            className="small-button"
            type="button"
            onClick={() => handlePause(selectedEvent.event_id)}
            disabled={!hasControlToken || selectedEvent.status !== "active"}
          >
            <ShieldAlert size={13} />
            Pause
          </button>
          <button
            className="small-button"
            type="button"
            onClick={() => handleRecordOutcome(selectedEvent.event_id)}
            disabled={!hasControlToken || !outcomeText.trim()}
          >
            <ClipboardCheck size={13} />
            Record outcome
          </button>
        </div>
      )}
      {preview && (
        <>
          <div className="status-cluster">
            <StatusBadge status="implemented" label={`${preview.candidate_symbols?.length || 0} candidate symbols`} />
            <StatusBadge status={preview.warnings?.length ? "warning" : "implemented"} label={`${preview.warnings?.length || 0} warnings`} />
            <StatusBadge status="info" label={preview.preview_mode || "real_bfs"} />
          </div>
          <details className="raw-details" open>
            <summary>Theme impacts ({preview.impacts?.length || 0})</summary>
            <JsonPanel value={preview.impacts || []} />
          </details>
          <details className="raw-details">
            <summary>Candidate symbols ({preview.candidate_symbols?.length || 0})</summary>
            <JsonPanel value={preview.candidate_symbols || []} />
          </details>
          {preview.warnings && preview.warnings.length > 0 && (
            <details className="raw-details" open>
              <summary>Warnings</summary>
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
            <h3>Persisted event lineage</h3>
          </div>
          <Workflow size={18} />
        </div>
        <div className="header-actions">
          <label>
            <span>Event id filter</span>
            <input
              value={selectedEventId}
              onChange={(event) => setSelectedEventId(event.target.value)}
              placeholder="all events"
            />
          </label>
          <button className="small-button" type="button" onClick={loadLineage} disabled={lineageLoading}>
            <RefreshCw size={13} className={lineageLoading ? "spin" : ""} />
            Refresh lineage
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
                    {" "}/ {row.target_count || 0} targets / {row.breadth_resolved || "unknown"}
                  </p>
                </div>
              </div>
              <div className="event-card-meta">
                <StatusBadge
                  status={row.gate_3_passed ? "implemented" : row.gate_1_passed ? "info" : "warning"}
                  label={`submitted ${row.strategies_submitted || 0}`}
                />
                <small>{formatTime(row.generated_at)}</small>
              </div>
              <details className="raw-details">
                <summary>Lineage payload</summary>
                <JsonPanel value={row} />
              </details>
            </article>
          ))}
          {!lineage.length && (
            <div className="empty-mini">
              <ClipboardCheck size={24} />
              <span>No persisted lineage rows match the current filter.</span>
            </div>
          )}
        </div>
      </section>

      <section className="capability-section">
      <div className="section-header">
        <div>
          <span>Action log</span>
          <h3>Recent intent dispatches</h3>
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
              <StatusBadge status={entry.ok ? "implemented" : "warning"} label={entry.ok ? "ok" : "blocked"} />
            </div>
          </article>
        ))}
        {!actionLog.length && (
          <div className="empty-mini">
            <ClipboardCheck size={24} />
            <span>No dispatches yet. Create or approve an event to see lineage entries.</span>
          </div>
        )}
      </div>
      <div className="notice">
        <Workflow size={15} />
        Persisted lineage (event -&gt; task -&gt; gate -&gt; strategy/outcome) is read from
        ``strategy_factory_event_task_lineage`` through ``factory_event_lineage``.
      </div>
      </section>
    </>
  );

  // ── Render ───────────────────────────────────────────────────────────

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "events", label: "Events" },
    { id: "create", label: "Create" },
    { id: "preview", label: "Preview" },
    { id: "lineage", label: "Lineage" }
  ];

  return (
    <section className="capabilities-workspace" data-testid="factory-event-trigger-panel">
      <header className="capabilities-header">
        <div>
          <span>Factory Event Trigger</span>
          <h1>Inject, approve, and inspect event-driven research</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : "implemented"} label={message} />
          <button className="small-button" type="button" disabled={loading} onClick={loadEvents}>
            <RefreshCw size={14} className={loading ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <section className="capability-banner">
            <div>
              <span>Agent-gated event console</span>
              <h2>{filtered.length} events / {events.filter((e) => e.status === "pending_review").length} pending review</h2>
              <p>
                All write actions (create / approve / pause / record outcome) flow through the ``ActionIntent`` chain
                wired in PR-F. This panel never calls the manager handler directly — that would bypass the
                dual-person review and self-approval guard inside ``handle_factory_event_approve``.
              </p>
            </div>
            <div className="status-cluster">
              <StatusBadge status={hasControlToken ? "implemented" : "warning"} label={hasControlToken ? "Control token ready" : "Read-only (no control token)"} />
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
              {message}. Reads will recover once the Agent API is reachable.
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
