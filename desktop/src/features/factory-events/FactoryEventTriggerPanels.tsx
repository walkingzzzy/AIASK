import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Compass,
  Plus,
  RefreshCw,
  ShieldAlert,
  Target,
  Workflow
} from "lucide-react";
import { RawEvidencePanel, StatusBadge, compact, shortText, statusLabel } from "../../components/shared";
import {
  DIRECTION_OPTIONS,
  HIGH_INTENSITY_THRESHOLD,
  RADAR_TIER_OPTIONS,
  SOURCE_OPTIONS,
  TYPE_OPTIONS,
  formatTime,
  latestRunId,
  numericStatus,
  outboxCount,
  radarTierLabel
} from "./FactoryEventTriggerData";
import type { LineageRow, RadarCandidateRow } from "./FactoryEventTriggerData";

export interface ActionLogEntry {
  stamp: string;
  text: string;
  ok: boolean;
}

export function ActionLogPanel({ actionLog }: { actionLog: ActionLogEntry[] }) {
  return (
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
            <span>尚未创建或确认任何意图。</span>
          </div>
        )}
      </div>
    </section>
  );
}

export function MaintenancePanel({
  bootstrapStatus,
  exposureStatus,
  handleBootstrap,
  handleExposureRefresh,
  handleOutboxDrain,
  handleRegressionRun,
  hasControlToken,
  loadMaintenanceStatus,
  maintenanceLoading,
  maintenanceMessage,
  outboxStatus
}: {
  bootstrapStatus: string;
  exposureStatus: Record<string, unknown> | null;
  handleBootstrap: () => void;
  handleExposureRefresh: () => void;
  handleOutboxDrain: () => void;
  handleRegressionRun: () => void;
  hasControlToken: boolean;
  loadMaintenanceStatus: () => void | Promise<void>;
  maintenanceLoading: boolean;
  maintenanceMessage: string;
  outboxStatus: Record<string, unknown> | null;
}) {
  return (
    <section className="capability-section">
      <div className="section-header">
        <div>
          <span>{statusLabel(maintenanceMessage)}</span>
          <h3>暴露与出站队列状态</h3>
        </div>
        <RefreshCw size={18} className={maintenanceLoading ? "spin" : ""} />
      </div>
      <div className="status-cluster">
        <StatusBadge status="info" label={`${numericStatus(exposureStatus, "row_count")} 行暴露`} />
        <StatusBadge status="info" label={`${numericStatus(exposureStatus, "theme_count")} 个主题`} />
        <StatusBadge status={outboxCount(outboxStatus, "failed") ? "warning" : "implemented"} label={`${outboxCount(outboxStatus, "failed")} 条出站失败`} />
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
          初始化引导
        </button>
        <button className="small-button" type="button" onClick={handleExposureRefresh} disabled={!hasControlToken || maintenanceLoading}>
          <Target size={13} />
          刷新暴露
        </button>
        <button className="small-button" type="button" onClick={handleOutboxDrain} disabled={!hasControlToken || maintenanceLoading}>
          <Workflow size={13} />
          排空出站队列
        </button>
        <button className="small-button" type="button" onClick={handleRegressionRun} disabled={!hasControlToken || maintenanceLoading}>
          <Compass size={13} />
          运行回归
        </button>
      </div>
      {!hasControlToken && (
        <div className="notice warn">
          <AlertTriangle size={15} />
          维护类写操作需要控制令牌；只读状态仍可查看。
        </div>
      )}
    </section>
  );
}

export function RadarTab({
  actionLog,
  handleRadarPushPreview,
  handleRadarRun,
  handleRadarSchedulePreview,
  hasControlToken,
  loadRadar,
  radarCandidates,
  radarDigest,
  radarLoading,
  radarMessage,
  radarStatus,
  radarTierFilter,
  setRadarTierFilter
}: {
  actionLog: ActionLogEntry[];
  handleRadarPushPreview: () => void;
  handleRadarRun: () => void;
  handleRadarSchedulePreview: () => void;
  hasControlToken: boolean;
  loadRadar: () => void | Promise<void>;
  radarCandidates: RadarCandidateRow[];
  radarDigest: Record<string, unknown> | null;
  radarLoading: boolean;
  radarMessage: string;
  radarStatus: Record<string, unknown> | null;
  radarTierFilter: string;
  setRadarTierFilter: (value: string) => void;
}) {
  const degradedFlags = Array.isArray(radarStatus?.degraded_flags)
    ? radarStatus.degraded_flags.map((value) => compact(value)).filter(Boolean)
    : [];
  const digestPreview = compact(radarDigest?.digest_preview || radarStatus?.digest_preview || "");
  const counts = radarStatus?.counts && typeof radarStatus.counts === "object"
    ? radarStatus.counts as Record<string, unknown>
    : {};
  return (
    <>
      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>状态：{statusLabel(radarMessage)}</span>
            <h3>股票雷达观察池</h3>
          </div>
          <Target size={18} />
        </div>
        <div className="status-cluster">
          <StatusBadge status={radarMessage.startsWith("AIASK_") ? "warning" : "implemented"} label={`状态 ${String(radarStatus?.status || "unknown")}`} />
          <StatusBadge status="info" label={`警报 ${Number(counts.alert || 0)}`} />
          <StatusBadge status="info" label={`观察 ${Number(counts.watch || 0)}`} />
          <StatusBadge status={degradedFlags.length ? "warning" : "implemented"} label={`降级 ${degradedFlags.length}`} />
          <StatusBadge status="info" label={`运行 ${latestRunId(radarStatus) || "-"}`} />
        </div>
        <div className="event-filter-grid">
          <label>
            <span>级别</span>
            <select value={radarTierFilter} onChange={(event) => setRadarTierFilter(event.target.value)}>
              {RADAR_TIER_OPTIONS.map((option) => (
                <option key={option.value || "all"} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <div className="field-row action-field">
            <span>&nbsp;</span>
            <button aria-label="刷新雷达" className="small-button" type="button" onClick={loadRadar} disabled={radarLoading}>
              <RefreshCw size={13} className={radarLoading ? "spin" : ""} />
              刷新雷达
            </button>
          </div>
          <div className="field-row action-field">
            <span>&nbsp;</span>
            <button aria-label="创建雷达运行意图" className="small-button" type="button" onClick={handleRadarRun} disabled={!hasControlToken || radarLoading}>
              <Compass size={13} />
              创建雷达运行意图
            </button>
          </div>
          <div className="field-row action-field">
            <span>&nbsp;</span>
            <button aria-label="创建推送预览意图" className="small-button" type="button" onClick={handleRadarPushPreview} disabled={!hasControlToken || radarLoading}>
              <ClipboardCheck size={13} />
              创建推送预览意图
            </button>
          </div>
          <div className="field-row action-field">
            <span>&nbsp;</span>
            <button aria-label="创建调度意图" className="small-button" type="button" onClick={handleRadarSchedulePreview} disabled={!hasControlToken || radarLoading}>
              <Workflow size={13} />
              创建调度意图
            </button>
          </div>
        </div>
        {degradedFlags.length > 0 && (
          <div className="notice warn">
            <AlertTriangle size={15} />
            {degradedFlags.slice(0, 8).join(", ")}
          </div>
        )}
        {!hasControlToken && (
          <div className="notice warn">
            <AlertTriangle size={15} />
            雷达运行、推送预览和调度更新需要控制令牌；状态、候选和推送预览仍可只读查看。
          </div>
        )}
      </section>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>{radarCandidates.length} 个候选</span>
            <h3>证据排序候选</h3>
          </div>
          <Workflow size={18} />
        </div>
        <div className="event-list">
          {radarCandidates.map((candidate) => (
            <article className="event-card" key={candidate.candidate_id}>
              <div className="event-card-main">
                <div className="event-card-icon">
                  <Target size={15} />
                </div>
                <div>
                  <span>
                    {candidate.symbol} / {candidate.event_type} / {candidate.direction}
                  </span>
                  <strong>{candidate.stock_name || candidate.symbol}</strong>
                  <p>{shortText(candidate.summary || "", 220)}</p>
                </div>
              </div>
              <div className="event-card-meta">
                <StatusBadge status={candidate.tier === "alert" ? "implemented" : candidate.tier === "watch" ? "info" : "warning"} label={`${radarTierLabel(candidate.tier)} ${candidate.radar_score.toFixed(1)}`} />
                <small>{candidate.source_doc_uids.length} 条来源</small>
              </div>
              <RawEvidencePanel
                title="证据、确认与风险标记"
                value={{ source_chain: candidate.source_chain, extraction: candidate.extraction, confirmations: candidate.confirmations, risk_flags: candidate.risk_flags }}
              />
            </article>
          ))}
          {!radarCandidates.length && (
            <div className="empty-mini">
              <ClipboardCheck size={24} />
              <span>当前筛选条件下没有雷达候选。</span>
            </div>
          )}
        </div>
      </section>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>推送预览</span>
            <h3>企微 / Telegram 载荷预览</h3>
          </div>
          <ClipboardCheck size={18} />
        </div>
        <pre className="json-panel">{digestPreview || "暂无推送预览。"}</pre>
        <div className="notice">
          <ShieldAlert size={15} />
          仅用于观察池和消息预览，文案不包含买入或卖出指令。
        </div>
      </section>

      <ActionLogPanel actionLog={actionLog} />
    </>
  );
}

export function CreateTab({
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
  handleCreate,
  handleCreateAndConfirm,
  hasControlToken,
  setFormConfidence,
  setFormDirection,
  setFormEvidenceSummary,
  setFormEvidenceUrl,
  setFormIntensity,
  setFormName,
  setFormOperator,
  setFormSource,
  setFormThemes,
  setFormType,
  setFormValidUntil
}: {
  formConfidence: number;
  formDirection: "bullish" | "bearish" | "neutral";
  formEvidenceSummary: string;
  formEvidenceUrl: string;
  formIntensity: number;
  formName: string;
  formOperator: string;
  formSource: string;
  formThemes: string;
  formType: string;
  formValidUntil: string;
  handleCreate: () => void;
  handleCreateAndConfirm: () => void;
  hasControlToken: boolean;
  setFormConfidence: (value: number) => void;
  setFormDirection: (value: "bullish" | "bearish" | "neutral") => void;
  setFormEvidenceSummary: (value: string) => void;
  setFormEvidenceUrl: (value: string) => void;
  setFormIntensity: (value: number) => void;
  setFormName: (value: string) => void;
  setFormOperator: (value: string) => void;
  setFormSource: (value: string) => void;
  setFormThemes: (value: string) => void;
  setFormType: (value: string) => void;
  setFormValidUntil: (value: string) => void;
}) {
  return (
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
          缺少控制令牌。读取仍可使用，但“创建”/“批准”/“暂停”无法派发意图。
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
}

export function LineageTab({
  actionLog,
  lineage,
  lineageLoading,
  lineageMessage,
  loadLineage,
  selectedEventId,
  setSelectedEventId
}: {
  actionLog: ActionLogEntry[];
  lineage: LineageRow[];
  lineageLoading: boolean;
  lineageMessage: string;
  loadLineage: () => void | Promise<void>;
  selectedEventId: string;
  setSelectedEventId: (value: string) => void;
}) {
  return (
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
              <RawEvidencePanel title="血缘载荷" value={row} />
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

      <ActionLogPanel actionLog={actionLog} />
      <div className="notice">
        <Workflow size={15} />
        持久化血缘（event -&gt; task -&gt; gate -&gt; strategy/outcome）通过 `factory_event_lineage`
        读取 `strategy_factory_event_task_lineage`。
      </div>
    </>
  );
}
