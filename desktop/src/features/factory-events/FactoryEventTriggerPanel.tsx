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
  RefreshCw,
  Search,
  ShieldAlert,
  Target,
  Workflow
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { RawEvidencePanel, StatusBadge, shortText } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { ToolEnvelope } from "../../types";
import {
  HIGH_INTENSITY_THRESHOLD,
  OUTCOME_OPTIONS,
  SOURCE_OPTIONS,
  STATUS_OPTIONS,
  TYPE_OPTIONS,
  classifyEventStatus,
  eventListFromData,
  formatTime,
  intentIdFromEnvelope,
  latestRunId,
  lineageFromData,
  previewFromData,
  radarCandidatesFromData
} from "./FactoryEventTriggerData";
import type { FactoryEventRow, LineageRow, PreviewPayload, RadarCandidateRow, TabId } from "./FactoryEventTriggerData";
import { ActionLogPanel, CreateTab, LineageTab, MaintenancePanel, RadarTab } from "./FactoryEventTriggerPanels";
import type { ActionLogEntry } from "./FactoryEventTriggerPanels";

interface Props {
  endpoint: string;
  apiToken: string;
  controlToken: string;
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

  const [actionLog, setActionLog] = useState<ActionLogEntry[]>([]);
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
  const [radarStatus, setRadarStatus] = useState<Record<string, unknown> | null>(null);
  const [radarCandidates, setRadarCandidates] = useState<RadarCandidateRow[]>([]);
  const [radarDigest, setRadarDigest] = useState<Record<string, unknown> | null>(null);
  const [radarLoading, setRadarLoading] = useState(false);
  const [radarMessage, setRadarMessage] = useState("RADAR_NOT_LOADED");
  const [radarTierFilter, setRadarTierFilter] = useState("");

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

  const loadRadar = useCallback(async () => {
    setRadarLoading(true);
    try {
      const [statusEnvelope, candidatesEnvelope, digestEnvelope] = await Promise.all([
        client.stockRadarStatus({ limit: 20 }),
        client.stockRadarCandidates({ tier: radarTierFilter, limit: 100 }),
        client.stockRadarDigest({ limit: 20, channels: ["wecom", "telegram"] })
      ]);
      const nextMessage =
        statusEnvelope.error || candidatesEnvelope.error || digestEnvelope.error || "RADAR_DEGRADED";
      setRadarStatus(statusEnvelope.success ? statusEnvelope.data || {} : { status: "failed", degraded_flags: [nextMessage] });
      setRadarCandidates(candidatesEnvelope.success ? radarCandidatesFromData(candidatesEnvelope.data) : []);
      setRadarDigest(digestEnvelope.success ? digestEnvelope.data || {} : {});
      setRadarMessage(
        statusEnvelope.success && candidatesEnvelope.success && digestEnvelope.success
          ? "RADAR_LOADED"
          : nextMessage
      );
    } catch (error) {
      setRadarStatus(null);
      setRadarCandidates([]);
      setRadarDigest(null);
      setRadarMessage(formatApiError(error));
    } finally {
      setRadarLoading(false);
    }
  }, [client, radarTierFilter]);

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

  useEffect(() => {
    loadRadar().catch(() => undefined);
  }, [loadRadar]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return events.filter((event) => {
      if (statusFilter && event.status !== statusFilter) return false;
      if (sourceFilter && event.event_source !== sourceFilter) return false;
      if (typeFilter && event.event_type !== typeFilter) return false;
      return !needle || JSON.stringify(event).toLowerCase().includes(needle);
    });
  }, [events, query, sourceFilter, statusFilter, typeFilter]);

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
      appendLog("缺少控制令牌，写操作需要确认。", false);
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
          if (label === "初始化引导" || label.includes("Bootstrap")) {
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
    createAndConfirmMaintenanceIntent("初始化引导", () =>
      client.factoryEventBootstrapIntent({ batch_size: 1000, refresh_exposure: true })
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const handleExposureRefresh = useCallback(() => {
    createAndConfirmMaintenanceIntent("刷新暴露", () =>
      client.factoryThemeExposureRefreshIntent({ batch_size: 1000 })
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const handleOutboxDrain = useCallback(() => {
    createAndConfirmMaintenanceIntent("排空出站队列", () =>
      client.factoryEventOutboxDrainIntent({ limit: 20 })
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const handleRegressionRun = useCallback(() => {
    createAndConfirmMaintenanceIntent("主题回归", () =>
      client.factoryThemeRegressionRunIntent({})
    );
  }, [client, createAndConfirmMaintenanceIntent]);

  const handleRadarRun = useCallback(() => {
    createAndConfirmMaintenanceIntent("股票雷达运行", () =>
      client.stockRadarRunIntent({
        mode: "run_once",
        days: 3,
        limit: 80,
        allow_network: false,
        allow_llm: false,
        ingest_market_text: true,
        parse_pdf: true
      })
    ).then(() => loadRadar());
  }, [client, createAndConfirmMaintenanceIntent, loadRadar]);

  const handleRadarPushPreview = useCallback(() => {
    createAndConfirmMaintenanceIntent("股票雷达推送预览", () =>
      client.stockRadarPushDigestIntent({
        run_id: latestRunId(radarStatus),
        channels: ["wecom", "telegram"],
        dry_run: true
      })
    ).then(() => loadRadar());
  }, [client, createAndConfirmMaintenanceIntent, loadRadar, radarStatus]);

  const handleRadarSchedulePreview = useCallback(() => {
    createAndConfirmMaintenanceIntent("股票雷达调度预览", () =>
      client.stockRadarScheduleUpdateIntent({
        interval_seconds: 86400,
        enabled: true,
        days: 3,
        limit: 80,
        allow_network: false,
        allow_llm: false,
        ingest_market_text: true,
        parse_pdf: true
      })
    ).then(() => loadRadar());
  }, [client, createAndConfirmMaintenanceIntent, loadRadar]);

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
              <RawEvidencePanel title="证据载荷" value={event} />
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

      <ActionLogPanel actionLog={actionLog} />
    </>
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
          <RawEvidencePanel title={`主题影响 (${preview.impacts?.length || 0})`} value={preview.impacts || []} />
          <RawEvidencePanel title={`候选标的 (${preview.candidate_symbols?.length || 0})`} value={preview.candidate_symbols || []} />
          {preview.warnings && preview.warnings.length > 0 && (
            <RawEvidencePanel title="警告" value={preview.warnings} />
          )}
        </>
      )}
    </section>
  );

  // ── Render ───────────────────────────────────────────────────────────

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "radar", label: "雷达" },
    { id: "events", label: "事件" },
    { id: "create", label: "创建" },
    { id: "preview", label: "预览" },
    { id: "lineage", label: "血缘" }
  ];
  const activeTabLabel = tabs.find((entry) => entry.id === tab)?.label || tab;

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
              <StatusBadge status="info" label={`当前页：${activeTabLabel}`} />
            </div>
          </section>

          <MaintenancePanel
            bootstrapStatus={bootstrapStatus}
            exposureStatus={exposureStatus}
            handleBootstrap={handleBootstrap}
            handleExposureRefresh={handleExposureRefresh}
            handleOutboxDrain={handleOutboxDrain}
            handleRegressionRun={handleRegressionRun}
            hasControlToken={hasControlToken}
            loadMaintenanceStatus={loadMaintenanceStatus}
            maintenanceLoading={maintenanceLoading}
            maintenanceMessage={maintenanceMessage}
            outboxStatus={outboxStatus}
          />

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
          {tab === "radar" && (
            <RadarTab
              actionLog={actionLog}
              handleRadarPushPreview={handleRadarPushPreview}
              handleRadarRun={handleRadarRun}
              handleRadarSchedulePreview={handleRadarSchedulePreview}
              hasControlToken={hasControlToken}
              loadRadar={loadRadar}
              radarCandidates={radarCandidates}
              radarDigest={radarDigest}
              radarLoading={radarLoading}
              radarMessage={radarMessage}
              radarStatus={radarStatus}
              radarTierFilter={radarTierFilter}
              setRadarTierFilter={setRadarTierFilter}
            />
          )}
          {tab === "create" && (
            <CreateTab
              formConfidence={formConfidence}
              formDirection={formDirection}
              formEvidenceSummary={formEvidenceSummary}
              formEvidenceUrl={formEvidenceUrl}
              formIntensity={formIntensity}
              formName={formName}
              formOperator={formOperator}
              formSource={formSource}
              formThemes={formThemes}
              formType={formType}
              formValidUntil={formValidUntil}
              handleCreate={handleCreate}
              handleCreateAndConfirm={handleCreateAndConfirm}
              hasControlToken={hasControlToken}
              setFormConfidence={setFormConfidence}
              setFormDirection={setFormDirection}
              setFormEvidenceSummary={setFormEvidenceSummary}
              setFormEvidenceUrl={setFormEvidenceUrl}
              setFormIntensity={setFormIntensity}
              setFormName={setFormName}
              setFormOperator={setFormOperator}
              setFormSource={setFormSource}
              setFormThemes={setFormThemes}
              setFormType={setFormType}
              setFormValidUntil={setFormValidUntil}
            />
          )}
          {tab === "preview" && renderPreviewTab()}
          {tab === "lineage" && (
            <LineageTab
              actionLog={actionLog}
              lineage={lineage}
              lineageLoading={lineageLoading}
              lineageMessage={lineageMessage}
              loadLineage={loadLineage}
              selectedEventId={selectedEventId}
              setSelectedEventId={setSelectedEventId}
            />
          )}
        </div>
      </div>
    </section>
  );
}
