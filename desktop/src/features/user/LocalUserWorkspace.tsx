import { RefreshCw, Save, Search, UserRound } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { LocalProfile } from "../../types";

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
  const [draftProfileName, setDraftProfileName] = useState(profileName || "Local Operator");
  const [sessions, setSessions] = useState<Array<Record<string, unknown>>>([]);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [messages, setMessages] = useState<Array<Record<string, unknown>>>([]);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<Record<string, unknown>>>([]);
  const [memoryResults, setMemoryResults] = useState<unknown>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const loadedProfile = await api.localProfileGet();
      setProfile(loadedProfile);
      setDraftUserId(loadedProfile.user_id || "local");
      setDraftProfileName(loadedProfile.profile_name || "Local Operator");
      onProfileChange(loadedProfile);
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

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>Local User</span>
          <h1>Profile and local data scope</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : profile?.status || "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>{draftUserId}</span>
              <h2>{draftProfileName}</h2>
              <p>Local profile is a desktop and Agent state scope. It is not a remote account, and secrets are not stored in the profile.</p>
            </div>
            <UserRound size={24} />
          </div>

          <section className="capability-grid two">
            <form className="capability-section" onSubmit={saveProfile}>
              <div className="section-header">
                <div>
                  <span>Profile</span>
                  <h3>Local identity</h3>
                </div>
                <StatusBadge status={profile?.status || "ready"} />
              </div>
              <label className="field-row">
                <span>User ID</span>
                <input value={draftUserId} onChange={(event) => setDraftUserId(event.target.value)} />
              </label>
              <label className="field-row">
                <span>Profile name</span>
                <input value={draftProfileName} onChange={(event) => setDraftProfileName(event.target.value)} />
              </label>
              <button className="primary-button" disabled={busy || !draftUserId.trim() || !draftProfileName.trim()} type="submit">
                <Save size={15} />
                Save profile
              </button>
              <div className="kv-grid">
                <span>Storage</span>
                <strong>{compact(profile?.storage)}</strong>
                <span>Path</span>
                <strong>{compact(profile?.path)}</strong>
                <span>Updated</span>
                <strong>{compact(profile?.updated_at)}</strong>
              </div>
            </form>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>{sessions.length} sessions</span>
                  <h3>Recent sessions</h3>
                </div>
                <StatusBadge status={sessions.length ? "ready" : "not_loaded"} />
              </div>
              <div className="mini-list">
                {sessions.slice(0, 8).map((session) => (
                  <article key={String(session.session_id)}>
                    <strong>{String(session.title || session.session_id)}</strong>
                    <span>{String(session.updated_at || session.created_at || "-")}</span>
                    <button className="small-button" disabled={busy || !session.session_id} onClick={() => loadSessionMessages(String(session.session_id))} type="button">
                      Load messages
                    </button>
                  </article>
                ))}
                {!sessions.length && <p className="muted">Sessions load when control access is available, or after this user starts Agent threads.</p>}
              </div>
            </section>
          </section>

          <section className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>{messages.length} messages</span>
                  <h3>Session messages</h3>
                </div>
                <StatusBadge status={messages.length ? "ready" : "not_loaded"} />
              </div>
              <div className="inline-form">
                <input value={selectedSessionId} onChange={(event) => setSelectedSessionId(event.target.value)} placeholder="session id" />
                <button disabled={busy || !selectedSessionId.trim()} onClick={() => loadSessionMessages()} type="button">
                  Load messages
                </button>
              </div>
              <div className="mini-list">
                {messages.slice(0, 12).map((item, index) => (
                  <article key={`${item.message_id || item.id || "message"}:${index}`}>
                    <strong>{String(item.role || item.kind || item.object || "message")}</strong>
                    <span>{String(item.created_at || item.updated_at || item.session_id || "-")}</span>
                    <p>{String(item.content || item.output_text || item.payload || "").slice(0, 220)}</p>
                  </article>
                ))}
                {!messages.length && <p className="muted">Select a recent session or paste a session id to inspect stored messages.</p>}
              </div>
            </section>

            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>Search</span>
                  <h3>Responses, sessions, and memory</h3>
                </div>
                <StatusBadge status={searchResults.length || memoryResults ? "ready" : "not_loaded"} />
              </div>
              <form className="inline-form" onSubmit={runSearch}>
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search local sessions, responses, and memory" />
                <button disabled={busy || !query.trim()} type="submit">
                  <Search size={14} />
                  Search
                </button>
              </form>
              <div className="mini-list">
                {searchResults.map((item, index) => (
                  <article key={`${item.object_id || item.session_id || "result"}:${index}`}>
                    <strong>{String(item.kind || item.object_id || "result")}</strong>
                    <span>{String(item.session_id || item.user_id || "-")}</span>
                    <p>{String(item.content || item.payload || "").slice(0, 220)}</p>
                  </article>
                ))}
                {!searchResults.length && <p className="muted">Search results will appear here.</p>}
              </div>
              <details className="raw-details">
                <summary>Memory search result</summary>
                <JsonPanel value={memoryResults || { status: "not_searched" }} />
              </details>
            </section>
          </section>

          <details className="raw-details">
            <summary>Raw local profile data</summary>
            <JsonPanel value={{ profile, sessions, messages, searchResults, memoryResults }} />
          </details>
        </div>
      </div>
    </section>
  );
}
