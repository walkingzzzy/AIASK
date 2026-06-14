import { RefreshCw, Save, Search, UserRound } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, RawEvidencePanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type {
  LocalProfile,
  RecentSessionSummary,
  RetentionSweepResult,
  UserAnalyticsSummary,
  UserActivityPayload,
  UserDataDeleteResult,
  UserDataExport,
  UserDataPolicy,
  UserLearningDataset,
  WorkflowRecommendationPayload
} from "../../types";

export function LocalUserWorkspace({
  endpoint,
  apiToken,
  controlToken,
  userId,
  profileName,
  onProfileChange
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  userId: string;
  profileName: string;
  onProfileChange: (profile: LocalProfile) => void;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [profile, setProfile] = useState<LocalProfile | null>(null);
  const [draftUserId, setDraftUserId] = useState(userId || "local");
  const [draftProfileName, setDraftProfileName] = useState(profileName || "本地操作者");
  const [sessions, setSessions] = useState<RecentSessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [messages, setMessages] = useState<Array<Record<string, unknown>>>([]);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<Record<string, unknown>>>([]);
  const [activity, setActivity] = useState<UserActivityPayload | null>(null);
  const [policy, setPolicy] = useState<UserDataPolicy | null>(null);
  const [analytics, setAnalytics] = useState<UserAnalyticsSummary | null>(null);
  const [exportData, setExportData] = useState<UserDataExport | null>(null);
  const [deletePreview, setDeletePreview] = useState<UserDataDeleteResult | null>(null);
  const [retentionPreview, setRetentionPreview] = useState<RetentionSweepResult | null>(null);
  const [learningDataset, setLearningDataset] = useState<UserLearningDataset | null>(null);
  const [recommendations, setRecommendations] = useState<WorkflowRecommendationPayload | null>(null);
  const [aggregateAnalytics, setAggregateAnalytics] = useState<UserAnalyticsSummary | null>(null);
  const [globalRetentionPreview, setGlobalRetentionPreview] = useState<RetentionSweepResult | null>(null);
  const [memoryStatus, setMemoryStatus] = useState<unknown>(null);
  const [memoryResults, setMemoryResults] = useState<unknown>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const loadedProfile = await api.localProfileGet();
      setProfile(loadedProfile);
      setDraftUserId(loadedProfile.user_id || "local");
      setDraftProfileName(loadedProfile.profile_name || "本地操作者");
      onProfileChange(loadedProfile);
      try {
        setMemoryStatus(await api.memoryStatus());
      } catch (error) {
        setMemoryStatus({ status: "degraded", error: formatApiError(error) });
      }
      try {
        const sessionPayload = await api.sessionsList(loadedProfile.user_id, 50);
        setSessions(sessionPayload.data || []);
      } catch {
        setSessions([]);
      }
      try {
        const [activityPayload, policyPayload, analyticsPayload, learningPayload, recommendationPayload] = await Promise.all([
          api.userActivity(loadedProfile.user_id, 30),
          api.userDataPolicyGet(loadedProfile.user_id),
          api.userAnalyticsSummary(loadedProfile.user_id, 20),
          api.userLearningDataset(loadedProfile.user_id, 50),
          api.userRecommendations(loadedProfile.user_id, 5)
        ]);
        setActivity(activityPayload);
        setPolicy(policyPayload.data);
        setAnalytics(analyticsPayload);
        setLearningDataset(learningPayload);
        setRecommendations(recommendationPayload);
      } catch {
        setActivity(null);
        setPolicy(null);
        setAnalytics(null);
        setLearningDataset(null);
        setRecommendations(null);
      }
      setMessage("LOCAL_PROFILE_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const saved = await api.localProfileSave({ user_id: draftUserId, profile_name: draftProfileName });
      setProfile(saved);
      onProfileChange(saved);
      try {
        const [activityPayload, policyPayload, analyticsPayload, learningPayload, recommendationPayload] = await Promise.all([
          api.userActivity(saved.user_id, 30),
          api.userDataPolicyGet(saved.user_id),
          api.userAnalyticsSummary(saved.user_id, 20),
          api.userLearningDataset(saved.user_id, 50),
          api.userRecommendations(saved.user_id, 5)
        ]);
        setActivity(activityPayload);
        setPolicy(policyPayload.data);
        setAnalytics(analyticsPayload);
        setLearningDataset(learningPayload);
        setRecommendations(recommendationPayload);
      } catch {
        setActivity(null);
        setPolicy(null);
        setAnalytics(null);
        setLearningDataset(null);
        setRecommendations(null);
      }
      setMessage("LOCAL_PROFILE_SAVED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function savePolicyPatch(patch: Partial<UserDataPolicy>) {
    const targetUserId = policy?.user_id || draftUserId || "local";
    setBusy(true);
    try {
      const payload = await api.userDataPolicySave(targetUserId, patch);
      setPolicy(payload.data);
      setActivity((current) => (current ? { ...current, policy: payload.data } : current));
      setLearningDataset(await api.userLearningDataset(targetUserId, 50));
      setMessage("USER_DATA_POLICY_SAVED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function runSearch(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    try {
      const [payload, memoryPayload] = await Promise.all([
        api.search(query, { user_id: draftUserId, limit: 30 }),
        api.memorySearch({ query, user_id: draftUserId, limit: 30 })
      ]);
      setSearchResults(payload.data || []);
      setMemoryResults(memoryPayload);
      setMessage("USER_DATA_SEARCHED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function previewExport() {
    const targetUserId = policy?.user_id || draftUserId || "local";
    setBusy(true);
    try {
      const [exportPayload, deletePayload, retentionPayload] = await Promise.all([
        api.userDataExport(targetUserId, 500),
        api.userDataDelete(targetUserId, { dry_run: true, reason: "desktop_preview" }),
        api.retentionSweep({ user_id: targetUserId, dry_run: true })
      ]);
      setExportData(exportPayload);
      setDeletePreview(deletePayload);
      setRetentionPreview(retentionPayload);
      setMessage("USER_DATA_EXPORT_PREVIEWED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function previewGovernance() {
    setBusy(true);
    try {
      const [aggregatePayload, retentionPayload] = await Promise.all([
        api.userAnalyticsSummary(undefined, 20),
        api.retentionSweep({ dry_run: true })
      ]);
      setAggregateAnalytics(aggregatePayload);
      setGlobalRetentionPreview(retentionPayload);
      setMessage("AGGREGATE_GOVERNANCE_PREVIEWED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function loadSessionMessages(sessionIdValue = selectedSessionId) {
    const id = sessionIdValue.trim();
    if (!id) return;
    setBusy(true);
    try {
      const payload = await api.sessionMessages(id, 80);
      setMessages(payload.data || []);
      setSelectedSessionId(id);
      setMessage("SESSION_MESSAGES_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  const memoryStatusRecord = memoryStatus && typeof memoryStatus === "object" ? (memoryStatus as Record<string, unknown>) : {};
  const activityEvents = activity?.events || [];
  const toolInvocations = activity?.tool_invocations || [];
  const feedbackEvents = activity?.feedback || [];

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>本地用户</span>
          <h1>画像与本地数据范围</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : profile?.status || "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>{draftUserId}</span>
              <h2>{draftProfileName}</h2>
              <p>本地画像用于限定 Desktop 与 Agent 的状态范围。它不是远程账号，也不会在画像里保存密钥。</p>
            </div>
            <UserRound size={24} />
          </div>

          <section className="capability-grid two">
            <form className="capability-section" onSubmit={saveProfile}>
              <div className="section-header">
                <div>
                  <span>画像</span>
                  <h3>本地身份</h3>
                </div>
                <StatusBadge status={profile?.status || "ready"} />
              </div>
              <label className="field-row">
                <span>用户 ID</span>
                <input value={draftUserId} onChange={(event) => setDraftUserId(event.target.value)} />
              </label>
              <label className="field-row">
                <span>画像名称</span>
                <input value={draftProfileName} onChange={(event) => setDraftProfileName(event.target.value)} />
              </label>
              <button className="primary-button" disabled={busy || !draftUserId.trim() || !draftProfileName.trim()} type="submit">
                <Save size={15} />
                保存画像
              </button>
              <div className="kv-grid">
                <span>存储</span>
                <strong>{compact(profile?.storage)}</strong>
                <span>路径</span>
                <strong>{compact(profile?.path)}</strong>
                <span>更新时间</span>
                <strong>{compact(profile?.updated_at)}</strong>
              </div>
            </form>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>{sessions.length} 个会话</span>
                  <h3>最近会话</h3>
                </div>
                <StatusBadge status={sessions.length ? "ready" : "not_loaded"} />
              </div>
              <div className="mini-list">
                {sessions.slice(0, 8).map((session) => (
                  <article key={String(session.session_id)}>
                    <strong>{String(session.title || session.session_id)}</strong>
                    <span>{String(session.last_message_at || "-")}</span>
                    <button className="small-button" disabled={busy || !session.session_id} onClick={() => loadSessionMessages(String(session.session_id))} type="button">
                      加载消息
                    </button>
                  </article>
                ))}
                {!sessions.length && <p className="muted">获得控制权限后会加载会话；该用户开始 Agent 线程后也会出现记录。</p>}
              </div>
            </section>
          </section>

          <section className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>{messages.length} 条消息</span>
                  <h3>会话消息</h3>
                </div>
                <StatusBadge status={messages.length ? "ready" : "not_loaded"} />
              </div>
              <div className="inline-form">
                <input value={selectedSessionId} onChange={(event) => setSelectedSessionId(event.target.value)} placeholder="session id" />
                <button disabled={busy || !selectedSessionId.trim()} onClick={() => loadSessionMessages()} type="button">
                  加载消息
                </button>
              </div>
              <div className="mini-list">
                {messages.slice(0, 12).map((item, index) => (
                  <article key={`${item.message_id || item.id || "message"}:${index}`}>
                    <strong>{String(item.role || item.kind || item.object || "消息")}</strong>
                    <span>{String(item.created_at || item.updated_at || item.session_id || "-")}</span>
                    <p>{String(item.content || item.output_text || item.payload || "").slice(0, 220)}</p>
                  </article>
                ))}
                {!messages.length && <p className="muted">选择最近会话或粘贴 session id，即可查看已保存的消息。</p>}
              </div>
            </section>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>搜索</span>
                  <h3>回复、会话与记忆</h3>
                </div>
                <StatusBadge status={searchResults.length || memoryResults ? "ready" : "not_loaded"} />
              </div>
              <form className="inline-form" onSubmit={runSearch}>
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索本地会话、回复和记忆" />
                <button disabled={busy || !query.trim()} type="submit">
                  <Search size={14} />
                  搜索
                </button>
              </form>
              <div className="mini-list">
                {searchResults.map((item, index) => (
                  <article key={`${item.object_id || item.session_id || "result"}:${index}`}>
                    <strong>{String(item.kind || item.object_id || "结果")}</strong>
                    <span>{String(item.session_id || item.user_id || "-")}</span>
                    <p>{String(item.content || item.payload || "").slice(0, 220)}</p>
                  </article>
                ))}
                {!searchResults.length && <p className="muted">搜索结果会显示在这里。</p>}
              </div>
              <details className="raw-details">
                <summary>记忆搜索结果</summary>
                <JsonPanel value={memoryResults || { status: "not_searched" }} />
              </details>
            </section>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>Agent 记忆</span>
                <h3>记忆状态</h3>
              </div>
              <StatusBadge status={String(memoryStatusRecord.status || (memoryStatus ? "ready" : "not_loaded"))} />
            </div>
            <div className="kv-grid">
              <span>提供方</span>
              <strong>{compact(memoryStatusRecord.provider || memoryStatusRecord.default_provider)}</strong>
              <span>路径</span>
              <strong>{compact(memoryStatusRecord.path || memoryStatusRecord.database_path)}</strong>
              <span>状态</span>
              <strong>{compact(memoryStatusRecord.status || "-")}</strong>
              <span>错误</span>
              <strong>{compact(memoryStatusRecord.error || "-")}</strong>
            </div>
            <RawEvidencePanel title="记忆状态 JSON" value={memoryStatus || { status: "not_loaded" }} />
          </section>

          <section className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>{activityEvents.length} events</span>
                  <h3>Activity Audit</h3>
                </div>
                <StatusBadge status={activity ? "ready" : "not_loaded"} />
              </div>
              <div className="mini-list">
                {activityEvents.slice(0, 10).map((item, index) => (
                  <article key={`${item.id || item.event_type || "event"}:${index}`}>
                    <strong>{String(item.event_type || "event")}</strong>
                    <span>{String(item.page_key || item.route || item.target_type || "-")}</span>
                    <p>{String(item.created_at || item.source || "-")}</p>
                  </article>
                ))}
                {!activityEvents.length && <p className="muted">No page or interaction events have been stored for this user yet.</p>}
              </div>
            </section>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>{toolInvocations.length} calls</span>
                  <h3>Tool Audit</h3>
                </div>
                <StatusBadge status={toolInvocations.length ? "ready" : "not_loaded"} />
              </div>
              <div className="mini-list">
                {toolInvocations.slice(0, 10).map((item, index) => (
                  <article key={`${item.invocation_id || item.tool_name || "tool"}:${index}`}>
                    <strong>{String(item.tool_name || "tool")}</strong>
                    <span>{String(item.status || "-")}</span>
                    <p>{String(item.created_at || item.trace_id || item.run_id || "-")}</p>
                  </article>
                ))}
                {!toolInvocations.length && <p className="muted">Tool calls will appear here with secret fields redacted.</p>}
              </div>
            </section>
          </section>

          <section className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>Retention</span>
                  <h3>Data Policy</h3>
                </div>
                <StatusBadge status={policy ? "ready" : "not_loaded"} />
              </div>
              <div className="kv-grid">
                <span>Event TTL</span>
                <strong>{policy ? `${policy.event_ttl_days} days` : "-"}</strong>
                <span>Audit TTL</span>
                <strong>{policy ? `${policy.audit_ttl_days} days` : "-"}</strong>
                <span>Run/Event TTL</span>
                <strong>{policy ? `${policy.run_event_ttl_days} days` : "-"}</strong>
                <span>Tool Payload TTL</span>
                <strong>{policy ? `${policy.tool_payload_ttl_days} days` : "-"}</strong>
                <span>Conversation</span>
                <strong>{compact(policy?.conversation_retention)}</strong>
              </div>
              <label className="field-row">
                <span>Product analytics</span>
                <input
                  checked={Boolean(policy?.allow_product_analytics)}
                  disabled={busy || !policy}
                  onChange={(event) => savePolicyPatch({ allow_product_analytics: event.target.checked })}
                  type="checkbox"
                />
              </label>
              <label className="field-row">
                <span>Learning use</span>
                <input
                  checked={Boolean(policy?.allow_learning)}
                  disabled={busy || !policy}
                  onChange={(event) => savePolicyPatch({ allow_learning: event.target.checked })}
                  type="checkbox"
                />
              </label>
            </section>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>{feedbackEvents.length} items</span>
                  <h3>Feedback</h3>
                </div>
                <StatusBadge status={feedbackEvents.length ? "ready" : "not_loaded"} />
              </div>
              <div className="mini-list">
                {feedbackEvents.slice(0, 10).map((item, index) => (
                  <article key={`${item.feedback_id || item.target_id || "feedback"}:${index}`}>
                    <strong>{String(item.feedback_type || "feedback")}</strong>
                    <span>{String(item.target_type || item.target_id || "-")}</span>
                    <p>{String(item.comment || item.created_at || "-").slice(0, 220)}</p>
                  </article>
                ))}
                {!feedbackEvents.length && <p className="muted">Explicit user feedback will be stored here for review and learning gates.</p>}
              </div>
              <RawEvidencePanel title="User Activity JSON" value={activity || { status: "not_loaded" }} />
            </section>
          </section>

          <section className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>Optimization</span>
                  <h3>Analytics Summary</h3>
                </div>
                <StatusBadge status={analytics ? "ready" : "not_loaded"} />
              </div>
              <div className="kv-grid">
                <span>Events</span>
                <strong>{compact(analytics?.totals?.events)}</strong>
                <span>Tools</span>
                <strong>{compact(analytics?.totals?.tool_invocations)}</strong>
                <span>Feedback</span>
                <strong>{compact(analytics?.totals?.feedback)}</strong>
              </div>
              <div className="mini-list">
                {(analytics?.tools || []).slice(0, 6).map((item, index) => (
                  <article key={`${item.tool_name || "tool"}:${index}`}>
                    <strong>{String(item.tool_name || "tool")}</strong>
                    <span>{String(item.count || 0)} calls</span>
                    <p>{`failure_rate=${String(item.failure_rate ?? 0)}, avg_ms=${String(item.avg_duration_ms ?? 0)}`}</p>
                  </article>
                ))}
                {!(analytics?.tools || []).length && <p className="muted">Tool reliability metrics will appear after audited tool calls.</p>}
              </div>
            </section>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>{recommendations?.count || 0} items</span>
                  <h3>Recommendations</h3>
                </div>
                <StatusBadge status={recommendations ? "ready" : "not_loaded"} />
              </div>
              <div className="mini-list">
                {(recommendations?.data || []).map((item, index) => (
                  <article key={`${item.id || item.kind || "recommendation"}:${index}`}>
                    <strong>{String(item.title || item.kind || "Recommendation")}</strong>
                    <span>{String(item.priority || "-")}</span>
                    <p>{String(item.reason || "-").slice(0, 220)}</p>
                  </article>
                ))}
                {!(recommendations?.data || []).length && <p className="muted">Workflow recommendations will appear after enough activity, failures, or feedback.</p>}
              </div>
            </section>
          </section>

          <section className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>Portability</span>
                  <h3>Export And Delete</h3>
                </div>
                <StatusBadge status={exportData || deletePreview ? "ready" : "not_loaded"} />
              </div>
              <button className="small-button" disabled={busy || !draftUserId.trim()} onClick={previewExport} type="button">
                Preview Export/Delete
              </button>
              <div className="kv-grid">
                <span>Export sessions</span>
                <strong>{compact(exportData?.sessions?.length)}</strong>
                <span>Export messages</span>
                <strong>{compact(exportData?.messages?.length)}</strong>
                <span>Delete dry-run</span>
                <strong>{compact(deletePreview?.dry_run)}</strong>
                <span>Delete messages</span>
                <strong>{compact(deletePreview?.counts?.messages)}</strong>
              </div>
              <RawEvidencePanel title="Export/Delete JSON" value={{ exportData, deletePreview }} />
            </section>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>Governance</span>
                  <h3>Retention And Learning</h3>
                </div>
                <StatusBadge status={retentionPreview || learningDataset ? "ready" : "not_loaded"} />
              </div>
              <div className="kv-grid">
                <span>Retention dry-run</span>
                <strong>{compact(retentionPreview?.dry_run)}</strong>
                <span>Market data affected</span>
                <strong>{compact(retentionPreview?.market_data_affected)}</strong>
                <span>Learning allowed</span>
                <strong>{compact(learningDataset?.allowed)}</strong>
                <span>Learning items</span>
                <strong>{compact(learningDataset?.count || learningDataset?.items?.length)}</strong>
              </div>
              <RawEvidencePanel title="Retention/Learning JSON" value={{ retentionPreview, learningDataset }} />
            </section>
          </section>

          <section className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>Admin</span>
                  <h3>Privacy Aggregates</h3>
                </div>
                <StatusBadge status={aggregateAnalytics ? "ready" : "control_token_required"} />
              </div>
              <button className="small-button" disabled={busy || !controlToken.trim()} onClick={previewGovernance} type="button">
                Preview Aggregate Governance
              </button>
              <div className="kv-grid">
                <span>Scope</span>
                <strong>{compact(aggregateAnalytics?.scope)}</strong>
                <span>Events</span>
                <strong>{compact(aggregateAnalytics?.totals?.events)}</strong>
                <span>Tools</span>
                <strong>{compact(aggregateAnalytics?.totals?.tool_invocations)}</strong>
                <span>Feedback</span>
                <strong>{compact(aggregateAnalytics?.totals?.feedback)}</strong>
              </div>
              <div className="mini-list">
                {(aggregateAnalytics?.pages || []).slice(0, 5).map((item, index) => (
                  <article key={`${item.page_key || "page"}:${index}`}>
                    <strong>{String(item.page_key || "unknown")}</strong>
                    <span>{String(item.count || 0)} events</span>
                    <p>Aggregated page usage only; per-user records stay in the user activity panel.</p>
                  </article>
                ))}
                {!(aggregateAnalytics?.pages || []).length && <p className="muted">Aggregate page usage appears here after a control-gated preview.</p>}
              </div>
            </section>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>Reliability</span>
                  <h3>Audit Posture</h3>
                </div>
                <StatusBadge status={globalRetentionPreview ? "ready" : "not_loaded"} />
              </div>
              <div className="kv-grid">
                <span>Retention dry-run</span>
                <strong>{compact(globalRetentionPreview?.dry_run)}</strong>
                <span>Market data affected</span>
                <strong>{compact(globalRetentionPreview?.market_data_affected)}</strong>
                <span>Tables</span>
                <strong>{compact(globalRetentionPreview?.tables?.length)}</strong>
                <span>Tool rows</span>
                <strong>{compact(globalRetentionPreview?.counts?.tool_invocations_payloads)}</strong>
              </div>
              <div className="mini-list">
                {(aggregateAnalytics?.tools || []).slice(0, 5).map((item, index) => (
                  <article key={`${item.tool_name || "tool"}:${index}`}>
                    <strong>{String(item.tool_name || "tool")}</strong>
                    <span>{String(item.count || 0)} calls</span>
                    <p>{`failed=${String(item.failed ?? 0)}, failure_rate=${String(item.failure_rate ?? 0)}`}</p>
                  </article>
                ))}
                {!(aggregateAnalytics?.tools || []).length && <p className="muted">Aggregate tool reliability appears here without raw input or output payloads.</p>}
              </div>
              <RawEvidencePanel title="Aggregate Governance JSON" value={{ aggregateAnalytics, globalRetentionPreview }} />
            </section>
          </section>

          <details className="raw-details">
            <summary>原始本地画像数据</summary>
            <JsonPanel value={{ profile, sessions, messages, searchResults, activity, policy, analytics, exportData, deletePreview, retentionPreview, learningDataset, recommendations, aggregateAnalytics, globalRetentionPreview, memoryStatus, memoryResults }} />
          </details>
        </div>
      </div>
    </section>
  );
}
