import { RefreshCw, Save, Search, UserRound } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, RawEvidencePanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { LocalProfile, RecentSessionSummary } from "../../types";

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
      setMessage("LOCAL_PROFILE_SAVED");
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

          <details className="raw-details">
            <summary>原始本地画像数据</summary>
            <JsonPanel value={{ profile, sessions, messages, searchResults, memoryStatus, memoryResults }} />
          </details>
        </div>
      </div>
    </section>
  );
}
