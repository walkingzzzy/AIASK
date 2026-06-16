import { ArrowRight, BarChart3, Code2, ExternalLink, FileJson, FileText, Filter, PackageOpen, RefreshCw, Terminal } from "lucide-react";
import type { MouseEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { PageShell, PageShellGrid, PageShellList } from "../../components/PageShell";
import { MetricCard, RawEvidencePanel, StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { AgentArtifactRecord, DesktopRunSummary, MainView } from "../../types";

const ALL_KINDS = "all";

function artifactTimeValue(artifact: AgentArtifactRecord) {
  const value = artifact.created_at || artifact.updated_at || "";
  const time = value ? new Date(value).getTime() : 0;
  return Number.isFinite(time) ? time : 0;
}

function artifactMatchesQuery(artifact: AgentArtifactRecord, query: string) {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [
    artifact.artifact_id,
    artifact.title,
    artifact.kind,
    artifact.path,
    artifact.uri,
    artifact.preview_text,
    artifact.run_id,
    artifact.session_id,
    artifact.tool_name
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(needle));
}

function uniqueArtifacts(records: AgentArtifactRecord[]) {
  const byId = new Map<string, AgentArtifactRecord>();
  for (const record of records) {
    if (!record.artifact_id) continue;
    const current = byId.get(record.artifact_id);
    if (!current || artifactTimeValue(record) >= artifactTimeValue(current)) {
      byId.set(record.artifact_id, record);
    }
  }
  return [...byId.values()].sort((a, b) => artifactTimeValue(b) - artifactTimeValue(a));
}

function apiHref(endpoint: string | undefined, path: string) {
  const base = String(endpoint || "").replace(/\/+$/, "");
  return base ? `${base}${path}` : path;
}

function artifactHref(artifact: AgentArtifactRecord, endpoint?: string) {
  const uri = String(artifact.uri || "");
  if (/^https?:\/\//i.test(uri)) return uri;
  return apiHref(endpoint, `/v1/artifacts/${encodeURIComponent(artifact.artifact_id)}/content?max_bytes=1048576`);
}

function artifactDescription(artifact: AgentArtifactRecord) {
  if (artifact.preview_text) return artifact.preview_text;
  if (artifact.mime_type || artifact.size_bytes) {
    return [artifact.mime_type, artifact.size_bytes ? `${artifact.size_bytes} bytes` : ""].filter(Boolean).join(" / ");
  }
  return artifact.tool_name || artifact.kind || "Durable Agent artifact";
}

function artifactSeverity(status?: string) {
  const normalized = String(status || "").toLowerCase();
  if (["failed", "error"].includes(normalized)) return "critical";
  if (["missing", "blocked"].includes(normalized)) return "warning";
  return "info";
}

function artifactIcon(kind?: string) {
  switch (String(kind || "file")) {
    case "json":
      return FileJson;
    case "quote_snapshot":
    case "strategy":
    case "factor":
    case "chart":
    case "table":
      return BarChart3;
    case "script":
    case "code":
    case "patch":
      return Code2;
    case "terminal_output":
      return Terminal;
    default:
      return FileText;
  }
}

async function openAgentEvidence(event: MouseEvent<HTMLAnchorElement>, href: string, token?: string) {
  if (!token?.trim() || !/\/v1\/artifacts\//.test(href)) return;
  event.preventDefault();
  try {
    const response = await fetch(href, { headers: { Authorization: `Bearer ${token.trim()}` } });
    if (!response.ok) throw new Error(`AIASK_HTTP_${response.status}`);
    const contentType = response.headers.get("content-type") || "application/octet-stream";
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob.type ? blob : new Blob([blob], { type: contentType }));
    window.open(objectUrl, "_blank", "noopener,noreferrer");
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch {
    window.open(href, "_blank", "noopener,noreferrer");
  }
}

function AgentArtifactCard({
  apiToken,
  artifact,
  endpoint
}: {
  apiToken?: string;
  artifact: AgentArtifactRecord;
  endpoint: string;
}) {
  const Icon = artifactIcon(artifact.kind);
  const href = artifactHref(artifact, endpoint);
  const status = artifact.status || "ready";
  const kind = artifact.kind || "file";
  const path = artifact.path || artifact.uri;
  const meta = [
    kind,
    artifact.run_id,
    artifact.session_id,
    artifact.tool_call_id,
    artifact.tool_name,
    path,
  ].filter(Boolean);

  return (
    <article className={`artifact-card ${artifactSeverity(status)}`}>
      <div className="artifact-icon">
        <Icon size={16} />
      </div>
      <div>
        <div className="artifact-card-head">
          <strong>{artifact.title || artifact.artifact_id}</strong>
          <StatusBadge status={status} technicalLabel={status || kind} />
        </div>
        <p>{artifactDescription(artifact)}</p>
        <div className="artifact-meta">
          {meta.map((value) => (
            <span key={String(value)}>{String(value)}</span>
          ))}
        </div>
        <a
          className="artifact-evidence-link"
          href={href}
          onClick={(event) => openAgentEvidence(event, href, apiToken)}
          rel="noreferrer"
          target="_blank"
        >
          <ExternalLink size={13} />
          Open evidence
        </a>
        <RawEvidencePanel title="Raw evidence" value={artifact} />
      </div>
    </article>
  );
}

export function ArtifactsPage({
  apiToken,
  controlToken,
  endpoint,
  onOpenView
}: {
  apiToken: string;
  controlToken: string;
  endpoint: string;
  onOpenView: (view: MainView) => void;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [runs, setRuns] = useState<DesktopRunSummary[]>([]);
  const [artifacts, setArtifacts] = useState<AgentArtifactRecord[]>([]);
  const [query, setQuery] = useState("");
  const [kindFilter, setKindFilter] = useState(ALL_KINDS);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function loadArtifacts() {
    setBusy(true);
    try {
      const runsPayload = await api.runsList({ limit: 40 });
      const nextRuns = runsPayload.data || [];
      setRuns(nextRuns);

      const settled = await Promise.allSettled(
        nextRuns.map((run) => api.runArtifacts(run.run_id, { limit: 100 }))
      );
      const nextArtifacts = uniqueArtifacts(
        settled.flatMap((result) => (result.status === "fulfilled" ? result.value.data || [] : []))
      );
      setArtifacts(nextArtifacts);
      const failedCount = settled.filter((result) => result.status === "rejected").length;
      setMessage(failedCount ? "ARTIFACTS_PARTIAL" : "ARTIFACTS_LOADED");
    } catch (error) {
      setRuns([]);
      setArtifacts([]);
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    loadArtifacts().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  const kindOptions = useMemo(() => {
    const kinds = Array.from(new Set(artifacts.map((artifact) => String(artifact.kind || "file")).filter(Boolean))).sort();
    return [ALL_KINDS, ...kinds];
  }, [artifacts]);

  const visibleArtifacts = useMemo(
    () =>
      artifacts.filter((artifact) => {
        if (kindFilter !== ALL_KINDS && String(artifact.kind || "file") !== kindFilter) return false;
        return artifactMatchesQuery(artifact, query);
      }),
    [artifacts, kindFilter, query]
  );

  const runCount = new Set(artifacts.map((artifact) => artifact.run_id).filter(Boolean)).size;
  const sessionCount = new Set(artifacts.map((artifact) => artifact.session_id).filter(Boolean)).size;

  return (
    <PageShell
      actions={
        <>
          <StatusBadge status={message} label={message} />
          <button className="small-button" disabled={busy} onClick={() => loadArtifacts()} type="button">
            <RefreshCw className={busy ? "spin" : ""} size={14} />
            刷新
          </button>
        </>
      }
      description="聚合最近运行沉淀的 durable artifacts，包括行情快照、脚本、终端输出、报告、表格和文件证据。"
      empty={!busy && artifacts.length === 0}
      emptyAction={
        <button className="small-button" onClick={() => onOpenView("runs-events")} type="button">
          <ArrowRight size={13} />
          打开运行 / 事件
        </button>
      }
      emptyDescription="运行产生的可持久化证据会出现在这里；AIASK 从 Agent artifacts API 读取，不从聊天文本里猜测。"
      emptyTitle="暂无产物"
      eyebrow="Agent 产物"
      filters={
        <label className="artifact-filter-control">
          <Filter size={14} />
          <select aria-label="产物类型" onChange={(event) => setKindFilter(event.target.value)} value={kindFilter}>
            {kindOptions.map((kind) => (
              <option key={kind} value={kind}>
                {kind === ALL_KINDS ? "全部类型" : kind}
              </option>
            ))}
          </select>
        </label>
      }
      loading={busy && artifacts.length === 0}
      loadingText="正在索引最近运行产物..."
      onSearchChange={setQuery}
      searchPlaceholder="搜索产物、路径、运行或工具..."
      searchValue={query}
      title="产物"
    >
      <div className="settings-section-stack">
        <PageShellGrid min={170}>
          <MetricCard label="产物" value={artifacts.length} />
          <MetricCard label="可见" value={visibleArtifacts.length} />
          <MetricCard label="运行" value={runCount || runs.length} />
          <MetricCard label="会话" value={sessionCount} />
        </PageShellGrid>

        <section className="task-panel">
          <div className="section-header">
            <div>
              <span>{visibleArtifacts.length} 个产物</span>
              <h3>产物索引</h3>
            </div>
            <PackageOpen size={18} />
          </div>
          {visibleArtifacts.length ? (
            <PageShellList>
              {visibleArtifacts.map((artifact) => (
                <AgentArtifactCard
                  apiToken={controlToken.trim() || apiToken}
                  artifact={artifact}
                  endpoint={endpoint}
                  key={artifact.artifact_id}
                />
              ))}
            </PageShellList>
          ) : (
            <div className="sidebar-empty">
              <strong>没有匹配产物</strong>
              <span>换一个关键词或类型筛选，或打开运行 / 事件查看最近运行。</span>
            </div>
          )}
        </section>
      </div>
    </PageShell>
  );
}
