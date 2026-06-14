import { Archive, ArchiveRestore, Filter, LockKeyhole, MessagesSquare, RefreshCw, Search, Send, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact, localizeBlockedReason } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { HandoffRecord, RecentSessionSummary, SessionResumeContextPayload } from "../../types";
import "./SessionsPage.css";

type FilterType = "all" | "recent_active" | "recent_created" | "has_pending_approval" | "has_errors";
type SortBy = "last_activity" | "created_at" | "message_count";
type HandoffView = {
  status?: string;
  target?: string;
  handoffId?: string;
  contextSnapshotId?: string;
  activeAgent?: string;
  activeContextSnapshotId?: string;
  summary?: string;
  reason?: string;
  updatedAt?: string;
};

function activityAt(session: RecentSessionSummary): string {
  return session.last_message_at || session.updated_at || session.created_at || "";
}

function lastRunStatus(session?: RecentSessionSummary): string {
  return session?.last_run_summary?.status || session?.status || "unknown";
}

function eventLabel(event: RecentSessionSummary["last_event"]): string {
  if (!event || typeof event !== "object") return "unknown";
  const record = event as Record<string, unknown>;
  return String(record.title || record.event_type || record.event || record.kind || "event");
}

function cleanString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function shortReference(value?: string): string {
  const text = cleanString(value);
  if (!text) return "";
  return text.length > 24 ? `${text.slice(0, 12)}...${text.slice(-7)}` : text;
}

function handoffView(session?: RecentSessionSummary | null): HandoffView | null {
  if (!session) return null;
  const metadata = asRecord(session.metadata);
  const state = asRecord(session.handoff_state || metadata.handoff_state);
  const status = cleanString(session.handoff_status || metadata.handoff_status || state.status);
  const target = cleanString(session.handoff_target || metadata.handoff_target || state.target || session.active_agent || metadata.active_agent);
  const handoffId = cleanString(session.handoff_id || metadata.handoff_id || metadata.last_handoff_id || state.handoff_id);
  const contextSnapshotId = cleanString(session.handoff_context_snapshot_id || metadata.handoff_context_snapshot_id || state.context_snapshot_id);
  const activeAgent = cleanString(session.active_agent || metadata.active_agent);
  const activeContextSnapshotId = cleanString(session.active_context_snapshot_id || metadata.active_context_snapshot_id);
  const summary = cleanString(state.summary);
  const reason = cleanString(state.reason);
  const updatedAt = cleanString(state.activated_at || state.updated_at);
  if (!status && !target && !handoffId && !contextSnapshotId && !activeAgent && !activeContextSnapshotId) return null;
  return { status, target, handoffId, contextSnapshotId, activeAgent, activeContextSnapshotId, summary, reason, updatedAt };
}

function isRecent(value: string | undefined, windowMs: number): boolean {
  if (!value) return false;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) && parsed > Date.now() - windowMs;
}

export function SessionsPage({
  endpoint,
  apiToken,
  controlToken,
  userId,
  fullModeActive,
  sessionsAdminAvailable,
  selectedSessionId: initialSelectedSessionId = "",
  onResumeSession,
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  userId?: string;
  fullModeActive: boolean;
  sessionsAdminAvailable: boolean;
  selectedSessionId?: string;
  onResumeSession?: (sessionId: string, resumeContext?: SessionResumeContextPayload) => void;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [endpoint, apiToken, controlToken]);
  const [sessions, setSessions] = useState<RecentSessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState(initialSelectedSessionId);
  const [messages, setMessages] = useState<Array<Record<string, unknown>>>([]);
  const [handoffQueue, setHandoffQueue] = useState<HandoffRecord[]>([]);
  const [resumeContext, setResumeContext] = useState<SessionResumeContextPayload | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState<FilterType>("all");
  const [sortBy, setSortBy] = useState<SortBy>("last_activity");
  const [showArchived, setShowArchived] = useState(false);

  const accessAllowed = fullModeActive && sessionsAdminAvailable && !!controlToken.trim();
  const selectedSession = useMemo(
    () => sessions.find((session) => session.session_id === selectedSessionId) || null,
    [sessions, selectedSessionId]
  );
  const selectedHandoff = useMemo(() => handoffView(selectedSession), [selectedSession]);

  async function loadSessions() {
    if (!accessAllowed) return;
    setBusy(true);
    try {
      const [payload, handoffs] = await Promise.all([
        api.sessionsList(userId, 80, showArchived),
        api.handoffsList({ userId, limit: 80 }),
      ]);
      const nextSessions = payload.data || [];
      setSessions(nextSessions);
      setHandoffQueue(handoffs.data || []);
      const nextSelected = initialSelectedSessionId || selectedSessionId || nextSessions[0]?.session_id || "";
      if (nextSelected) setSelectedSessionId(nextSelected);
      setMessage("SESSIONS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function loadMessages(sessionId: string) {
    if (!sessionId || !accessAllowed) return;
    setBusy(true);
    try {
      const payload = await api.sessionMessages(sessionId, 200);
      setMessages(payload.data || []);
      setSelectedSessionId(sessionId);
      setResumeContext(null);
      setMessage("SESSION_MESSAGES_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function undoLastTurn() {
    if (!selectedSessionId || !accessAllowed) return;
    setBusy(true);
    try {
      const undo = await api.sessionUndo(selectedSessionId, 1, "desktop sessions page");
      const [messagePayload, sessionsPayload] = await Promise.all([
        api.sessionMessages(selectedSessionId, 200),
        api.sessionsList(userId, 80, showArchived),
      ]);
      setMessages(messagePayload.data || []);
      setSessions(sessionsPayload.data || []);
      setMessage(`UNDO_${undo.turns_undone}_TURNS`);
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function toggleArchiveSession() {
    if (!selectedSessionId || !accessAllowed) return;
    const nextArchived = !Boolean(selectedSession?.archived);
    setBusy(true);
    try {
      const result = await api.sessionArchive(
        selectedSessionId,
        nextArchived,
        nextArchived ? "desktop sessions page archive" : "desktop sessions page restore"
      );
      const sessionsPayload = await api.sessionsList(userId, 80, showArchived);
      const nextSessions = sessionsPayload.data || [];
      setSessions(nextSessions);
      if (result.archived && !showArchived) {
        setMessages([]);
        setSelectedSessionId(nextSessions[0]?.session_id || "");
      }
      setMessage(result.archived ? "SESSION_ARCHIVED" : "SESSION_RESTORED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function resumeSelectedSession() {
    if (!selectedSessionId) return;
    setBusy(true);
    try {
      const payload = await api.sessionResumeContext(selectedSessionId);
      setResumeContext(payload);
      setMessage("RESUME_CONTEXT_LOADED");
      onResumeSession?.(selectedSessionId, payload);
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  const filteredAndSortedSessions = useMemo(() => {
    let filtered = [...sessions];
    const query = searchQuery.trim().toLowerCase();

    if (query) {
      filtered = filtered.filter(
        (session) => {
          const handoff = handoffView(session);
          return (
            session.session_id.toLowerCase().includes(query) ||
            (session.title || "").toLowerCase().includes(query) ||
            (session.user_id || "").toLowerCase().includes(query) ||
            (handoff?.target || "").toLowerCase().includes(query) ||
            (handoff?.activeAgent || "").toLowerCase().includes(query) ||
            (handoff?.handoffId || "").toLowerCase().includes(query) ||
            (handoff?.contextSnapshotId || "").toLowerCase().includes(query)
          );
        }
      );
    }

    switch (filterType) {
      case "recent_active":
        filtered = filtered.filter((session) => isRecent(activityAt(session), 7 * 24 * 60 * 60 * 1000));
        break;
      case "recent_created":
        filtered = filtered.filter((session) => isRecent(session.created_at, 24 * 60 * 60 * 1000));
        break;
      case "has_pending_approval":
        filtered = filtered.filter((session) => Boolean(session.has_pending_approval));
        break;
      case "has_errors":
        filtered = filtered.filter((session) => session.status === "error" || Boolean(session.has_errors));
        break;
      default:
        break;
    }

    filtered.sort((a, b) => {
      switch (sortBy) {
        case "created_at":
          return (b.created_at || "").localeCompare(a.created_at || "");
        case "message_count":
          return (b.message_count || 0) - (a.message_count || 0);
        case "last_activity":
        default:
          return activityAt(b).localeCompare(activityAt(a));
      }
    });

    return filtered;
  }, [sessions, searchQuery, filterType, sortBy]);

  useEffect(() => {
    if (!accessAllowed) return;
    loadSessions().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessAllowed, endpoint, userId, initialSelectedSessionId, showArchived]);

  useEffect(() => {
    if (initialSelectedSessionId) setSelectedSessionId(initialSelectedSessionId);
  }, [initialSelectedSessionId]);

  useEffect(() => {
    if (!accessAllowed || !selectedSessionId) return;
    loadMessages(selectedSessionId).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessAllowed, selectedSessionId]);

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>Agent 会话</span>
          <h1>会话</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={accessAllowed ? "implemented" : "gated"} label={accessAllowed ? "完整模式已开启" : "已锁定"} />
          <button className="small-button" disabled={busy || !accessAllowed} onClick={() => loadSessions()} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        {!accessAllowed ? (
          <div className="capability-stack">
            <div className="capability-banner">
              <div>
                <span>会话管理</span>
                <h2>需要完整模式和控制令牌</h2>
                <p>{localizeBlockedReason("Hermes full mode and control token required")}</p>
              </div>
              <LockKeyhole size={22} />
            </div>
            <div className="notice warn">
              <LockKeyhole size={14} />
              <span>当前页面始终可见，但在未激活完整模式、未配置控制令牌或无管理员访问权时不会发起请求。</span>
            </div>
          </div>
        ) : (
          <div className="page-split">
            <section className="capability-section session-list-panel">
              <div className="section-header">
                <div>
                  <span>{filteredAndSortedSessions.length} / {sessions.length} 个会话 · 交接队列 {handoffQueue.length}</span>
                  <h3>会话列表</h3>
                </div>
                <MessagesSquare size={18} />
              </div>

              <div className="filter-toolbar">
                <div className="search-box">
                  <Search size={14} />
                  <input
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder="搜索会话 ID、标题、用户..."
                    type="text"
                    value={searchQuery}
                  />
                </div>

                <div className="filter-row">
                  <Filter size={14} />
                  <select value={filterType} onChange={(event) => setFilterType(event.target.value as FilterType)}>
                    <option value="all">所有会话</option>
                    <option value="recent_active">最近活跃（7天）</option>
                    <option value="recent_created">最近创建（24小时）</option>
                    <option value="has_pending_approval">有审批</option>
                    <option value="has_errors">有错误</option>
                  </select>

                  <span>排序：</span>
                  <select value={sortBy} onChange={(event) => setSortBy(event.target.value as SortBy)}>
                    <option value="last_activity">最近活跃</option>
                    <option value="created_at">创建时间</option>
                    <option value="message_count">消息数量</option>
                  </select>

                  <label className="inline-toggle">
                    <input checked={showArchived} onChange={(event) => setShowArchived(event.target.checked)} type="checkbox" />
                    <span>显示归档</span>
                  </label>
                </div>
              </div>

              <div className="mini-list">
                {filteredAndSortedSessions.map((session) => {
                  const handoff = handoffView(session);
                  return (
                    <button
                      className={selectedSessionId === session.session_id ? "active" : ""}
                      key={session.session_id}
                      onClick={() => loadMessages(session.session_id)}
                      type="button"
                    >
                      <strong>{session.title || session.session_id}</strong>
                      <span>{session.session_id}</span>
                      <span>
                        {activityAt(session) || "-"}
                        {session.message_count ? ` • ${session.message_count} 条消息` : ""}
                      </span>
                      <span className="session-flags">
                        {session.archived ? <StatusBadge status="gated" label="已归档" /> : null}
                        {session.has_pending_approval ? <StatusBadge status="queued" label="有审批" /> : null}
                        {session.has_errors ? <StatusBadge status="error" label="有错误" /> : null}
                        {handoff ? (
                          <StatusBadge
                            status={handoff.status || "queued"}
                            label={`${handoff.status === "active" ? "接管" : "交接"}: ${handoff.activeAgent || handoff.target || "unknown"}`}
                          />
                        ) : null}
                      </span>
                    </button>
                  );
                })}
                {!filteredAndSortedSessions.length && sessions.length > 0 ? <p className="muted">没有符合筛选条件的会话。</p> : null}
                {!sessions.length ? <p className="muted">暂无最近会话。</p> : null}
              </div>
            </section>

            <section className="capability-section session-detail-panel">
              <div className="section-header">
                <div>
                  <span>{selectedSessionId || "未选择"}</span>
                  <h3>会话详情</h3>
                </div>
                <div className="header-actions">
                  <StatusBadge status={message} label={message} />
                  <button
                    className="small-button"
                    disabled={!selectedSessionId || busy || !messages.length}
                    onClick={() => undoLastTurn()}
                    type="button"
                  >
                    <Undo2 size={13} />
                    Undo last turn
                  </button>
                  <button
                    className="small-button"
                    disabled={!selectedSessionId || busy}
                    onClick={() => toggleArchiveSession()}
                    type="button"
                  >
                    {selectedSession?.archived ? <ArchiveRestore size={13} /> : <Archive size={13} />}
                    {selectedSession?.archived ? "Restore" : "Archive"}
                  </button>
                  <button
                    className="small-button"
                    disabled={!selectedSessionId || busy}
                    onClick={() => resumeSelectedSession()}
                    type="button"
                  >
                    <Send size={13} />
                    继续会话
                  </button>
                </div>
              </div>

              {selectedSession ? (
                <div className="session-summary-card">
                  {selectedHandoff ? (
                    <div className="session-handoff-strip" aria-label="会话交接状态">
                      <div>
                        <span>任务接管</span>
                        <strong>{selectedHandoff.activeAgent || selectedHandoff.target || "unknown"}</strong>
                      </div>
                      <div>
                        <span>交接状态</span>
                        <strong>{selectedHandoff.status || "unknown"}</strong>
                      </div>
                      <div>
                        <span>上下文快照</span>
                        <strong title={selectedHandoff.activeContextSnapshotId || selectedHandoff.contextSnapshotId || ""}>
                          {shortReference(selectedHandoff.activeContextSnapshotId || selectedHandoff.contextSnapshotId) || "none"}
                        </strong>
                      </div>
                    </div>
                  ) : null}
                  {resumeContext?.resume_context ? (
                    <div className="session-handoff-strip" aria-label="会话恢复上下文">
                      <div>
                        <span>恢复快照</span>
                        <strong title={resumeContext.resume_context.context_snapshot_id || ""}>
                          {shortReference(resumeContext.resume_context.context_snapshot_id || "") || "none"}
                        </strong>
                      </div>
                      <div>
                        <span>恢复目标</span>
                        <strong>{resumeContext.resume_context.target || "unknown"}</strong>
                      </div>
                      <div>
                        <span>风险标记</span>
                        <strong>{(resumeContext.resume_context.risk_flags || []).join(", ") || "none"}</strong>
                      </div>
                    </div>
                  ) : null}
                  <div className="kv-grid">
                    <span>创建时间</span>
                    <strong>{selectedSession.created_at || "unknown"}</strong>
                    <span>更新时间</span>
                    <strong>{selectedSession.updated_at || selectedSession.last_message_at || "unknown"}</strong>
                    <span>消息数</span>
                    <strong>{selectedSession.message_count ?? "not_loaded"}</strong>
                    <span>最近运行</span>
                    <strong>{selectedSession.last_run_id || selectedSession.last_run_summary?.run_id || "unknown"}</strong>
                    <span>运行状态</span>
                    <strong>{lastRunStatus(selectedSession)}</strong>
                    <span>最近事件</span>
                    <strong>{eventLabel(selectedSession.last_event)}</strong>
                    <span>归档状态</span>
                    <strong>{selectedSession.archived ? selectedSession.archived_at || "archived" : "active"}</strong>
                    <span>交接目标</span>
                    <strong>{selectedHandoff?.target || "none"}</strong>
                    <span>交接 ID</span>
                    <strong title={selectedHandoff?.handoffId || ""}>{shortReference(selectedHandoff?.handoffId) || "none"}</strong>
                    <span>交接原因</span>
                    <strong>{selectedHandoff?.reason || "none"}</strong>
                    <span>交接摘要</span>
                    <strong>{selectedHandoff?.summary || "none"}</strong>
                    <span>交接更新时间</span>
                    <strong>{selectedHandoff?.updatedAt || "none"}</strong>
                  </div>
                </div>
              ) : null}

              <div className="mini-list">
                {messages.map((item, index) => (
                  <article key={`${item.message_id || item.id || "message"}:${index}`}>
                    <strong>{String(item.role || "message")}</strong>
                    <span>{String(item.created_at || item.updated_at || "-")}</span>
                    <p>{String(item.content || item.output_text || item.payload || "").slice(0, 400)}</p>
                  </article>
                ))}
                {!messages.length ? <p className="muted">选择左侧会话后，这里会显示最近消息。</p> : null}
              </div>
              <details className="raw-details">
                <summary>原始会话数据</summary>
                <JsonPanel value={{ selectedSession, messages, handoffQueue, resumeContext, selectedSessionId, message: compact(message) }} />
              </details>
            </section>
          </div>
        )}
      </div>
    </section>
  );
}
