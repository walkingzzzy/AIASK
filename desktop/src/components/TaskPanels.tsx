import { BarChart3, ClipboardCheck, ExternalLink, FileJson, FileText, Image, Link2, MessageSquare, ShieldCheck, Sparkles } from "lucide-react";
import type { MouseEvent } from "react";
import { EmptyState, RawEvidencePanel, StatusBadge } from "./shared";
import type { AgentArtifactRecord, AgentSourceRecord, AgentResponse, DesktopRunSummary, TaskArtifact, TaskArtifactKind, TaskReviewComment, TaskThread, TimelineEvent } from "../types";

function artifactIcon(kind: TaskArtifact["kind"]) {
  switch (kind) {
    case "screenshot":
      return Image;
    case "json":
      return FileJson;
    case "quote_snapshot":
      return BarChart3;
    case "news_digest":
    case "file":
    case "code":
    case "script":
    case "terminal_output":
    case "table":
    case "patch":
      return FileText;
    case "strategy":
    case "factor":
      return BarChart3;
    case "approval":
      return ShieldCheck;
    case "run":
      return Sparkles;
    default:
      return FileText;
  }
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

function sourceHref(source: AgentSourceRecord, endpoint?: string) {
  if (source.url) return source.url;
  return apiHref(endpoint, `/v1/sources/${encodeURIComponent(source.source_id)}`);
}

async function openAgentEvidence(event: MouseEvent<HTMLAnchorElement>, href: string, token?: string) {
  if (!token?.trim() || !/\/v1\/(?:artifacts|sources)\//.test(href)) return;
  event.preventDefault();
  try {
    const response = await fetch(href, { headers: { Authorization: `Bearer ${token.trim()}` } });
    if (!response.ok) throw new Error(`AIASK_HTTP_${response.status}`);
    const contentType = response.headers.get("content-type") || "application/json";
    const text = await response.text();
    const blob = new Blob([text], { type: contentType.includes("json") ? "application/json" : "text/plain" });
    const objectUrl = URL.createObjectURL(blob);
    window.open(objectUrl, "_blank", "noopener,noreferrer");
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch {
    window.open(href, "_blank", "noopener,noreferrer");
  }
}

function artifactDescription(artifact: AgentArtifactRecord) {
  if (artifact.preview_text) return artifact.preview_text;
  if (artifact.mime_type || artifact.size_bytes) {
    return [artifact.mime_type, artifact.size_bytes ? `${artifact.size_bytes} bytes` : ""].filter(Boolean).join(" / ");
  }
  return artifact.tool_name || artifact.kind || "Durable Agent artifact";
}

export function buildTaskArtifacts({
  durableArtifacts,
  endpoint
}: {
  selectedThread: TaskThread | null;
  selectedResponse?: AgentResponse | null;
  recentRuns?: DesktopRunSummary[];
  timelineEvents?: TimelineEvent[];
  durableArtifacts?: AgentArtifactRecord[];
  durableSources?: AgentSourceRecord[];
  endpoint?: string;
}): TaskArtifact[] {
  return (durableArtifacts || []).map((artifact) => {
    const href = artifactHref(artifact, endpoint);
    const status = artifact.status || "ready";
    const severity =
      ["failed", "error"].includes(status.toLowerCase())
        ? "critical"
        : ["missing", "blocked"].includes(status.toLowerCase())
          ? "warning"
          : "info";
    return {
      id: `artifact:${artifact.artifact_id}`,
      kind: normalizeArtifactKind(artifact.kind),
      title: artifact.title || artifact.artifact_id,
      description: artifactDescription(artifact),
      status,
      source: artifact.tool_call_id || artifact.run_id || artifact.session_id,
      createdAt: artifact.created_at,
      sourceView: "runs-events",
      targetPath: href,
      href,
      path: artifact.path || artifact.uri,
      severity,
      value: artifact
    };
  });
}

function normalizeArtifactKind(kind: string | undefined): TaskArtifactKind {
  const normalized = String(kind || "file") as TaskArtifactKind;
  const allowed: TaskArtifactKind[] = [
    "report",
    "strategy",
    "factor",
    "data",
    "screenshot",
    "json",
    "run",
    "approval",
    "note",
    "file",
    "code",
    "script",
    "terminal_output",
    "quote_snapshot",
    "news_digest",
    "chart",
    "table",
    "patch",
  ];
  return allowed.includes(normalized) ? normalized : "file";
}

function readableTimestamp(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function buildTaskReviewComments(artifacts: TaskArtifact[]): TaskReviewComment[] {
  return artifacts
    .filter((artifact) => artifact.status && ["queued", "approval_required", "failed", "blocked", "error"].includes(artifact.status.toLowerCase()))
    .map((artifact, index) => ({
      id: `review:${artifact.id}:${index}`,
      targetId: artifact.id,
      targetType: artifact.kind === "screenshot" ? "screenshot" : artifact.kind === "run" ? "run" : "artifact",
      body: `复核 ${artifact.title}：${artifact.description || "线程完成前需要处理。"}`,
      status: "open",
      targetPath: artifact.targetPath,
      severity: artifact.severity === "critical" ? "critical" : "warning"
    }));
}

export function SourcesPanel({
  sources,
  compact = false,
  endpoint,
  apiToken
}: {
  sources?: AgentSourceRecord[];
  compact?: boolean;
  endpoint?: string;
  apiToken?: string;
}) {
  const items = sources || [];
  return (
    <section className={`task-panel ${compact ? "compact" : ""}`}>
      <div className="section-header">
        <div>
          <span>{items.length} 个来源</span>
          <h3>来源证据</h3>
        </div>
        <Link2 size={18} />
      </div>
      {items.length ? (
        <div className="source-evidence-list">
          {items.map((source) => (
            <article className="source-evidence-card" key={source.source_id}>
              <div>
                <strong>{source.title || source.provider || source.source_id}</strong>
                <StatusBadge status={source.source_type || "source"} technicalLabel={source.source_type || "source"} />
              </div>
              {source.excerpt && <p>{source.excerpt}</p>}
              <div className="artifact-meta">
                {source.provider && <span>{source.provider}</span>}
                {source.published_at && <span>发布 {readableTimestamp(source.published_at)}</span>}
                {source.fetched_at && <span>抓取 {readableTimestamp(source.fetched_at)}</span>}
                {source.data_timestamp && <span>数据 {readableTimestamp(source.data_timestamp)}</span>}
              </div>
              <a href={sourceHref(source, endpoint)} onClick={(event) => openAgentEvidence(event, sourceHref(source, endpoint), apiToken)} rel="noreferrer" target="_blank">
                <ExternalLink size={13} />
                {source.url || source.source_id}
              </a>
              {!compact && <RawEvidencePanel title="Source evidence" value={source} />}
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          body="行情 provider、新闻链接、网页引用和本地数据来源会在运行完成后显示。"
          icon={<Link2 size={24} />}
          title="暂无来源证据"
        />
      )}
    </section>
  );
}

export function ArtifactCard({ artifact, compact = false, apiToken }: { artifact: TaskArtifact; compact?: boolean; apiToken?: string }) {
  const Icon = artifactIcon(artifact.kind);
  return (
    <article className={`artifact-card ${artifact.severity || "info"}`}>
      <div className="artifact-icon">
        {artifact.thumbnailPath ? <img alt="" src={artifact.thumbnailPath} /> : <Icon size={16} />}
      </div>
      <div>
        <div className="artifact-card-head">
          <strong>{artifact.title}</strong>
          <StatusBadge status={artifact.status || "ready"} technicalLabel={artifact.status || artifact.kind} />
        </div>
        {artifact.description && <p>{artifact.description}</p>}
        <div className="artifact-meta">
          <span>{artifact.kind}</span>
          {artifact.sourceView && <span>{artifact.sourceView}</span>}
          {artifact.source && <span>{artifact.source}</span>}
          {artifact.targetPath && <span>{artifact.targetPath}</span>}
          {artifact.path && <span>{artifact.path}</span>}
        </div>
        {artifact.href && (
          <a className="artifact-evidence-link" href={artifact.href} onClick={(event) => openAgentEvidence(event, artifact.href || "", apiToken)} rel="noreferrer" target="_blank">
            <ExternalLink size={13} />
            Open evidence
          </a>
        )}
        {artifact.value !== undefined && !compact && (
          <RawEvidencePanel title="Raw evidence" value={artifact.value} />
        )}
      </div>
    </article>
  );
}

export function ReviewComment({ comment }: { comment: TaskReviewComment }) {
  return (
    <article className={`review-comment ${comment.severity || "info"}`}>
      <div>
        <strong>{comment.targetType}</strong>
        <span>{comment.targetPath || comment.targetId}</span>
      </div>
      <p>{comment.body}</p>
      <StatusBadge status={comment.status || "open"} technicalLabel={comment.status || "open"} />
    </article>
  );
}

export function ArtifactsPanel({
  artifacts,
  compact = false,
  apiToken
}: {
  artifacts: TaskArtifact[];
  compact?: boolean;
  apiToken?: string;
}) {
  return (
    <section className={`task-panel ${compact ? "compact" : ""}`}>
      <div className="section-header">
        <div>
          <span>{artifacts.length} 个产物</span>
          <h3>任务产物</h3>
        </div>
        <ClipboardCheck size={18} />
      </div>
      {artifacts.length ? (
        <div className="artifact-list">
          {artifacts.map((artifact) => <ArtifactCard artifact={artifact} compact={compact} apiToken={apiToken} key={artifact.id} />)}
        </div>
      ) : (
        <EmptyState
          body="Durable artifacts from the Agent artifacts API will appear here after a run records quotes, generated files, scripts, or terminal output."
          icon={<ClipboardCheck size={24} />}
          title="No durable artifacts"
        />
      )}
    </section>
  );
}

export function ReviewPanel({
  comments,
  compact = false
}: {
  comments: TaskReviewComment[];
  compact?: boolean;
}) {
  return (
    <section className={`task-panel ${compact ? "compact" : ""}`}>
      <div className="section-header">
        <div>
          <span>{comments.length} 条评论</span>
          <h3>审查队列</h3>
        </div>
        <MessageSquare size={18} />
      </div>
      {comments.length ? (
        <div className="review-comment-list">
          {comments.map((comment) => <ReviewComment comment={comment} key={comment.id} />)}
        </div>
      ) : (
        <EmptyState
          body="需要处理的产物、审批、截图和运行结果会出现在这里。"
          icon={<ClipboardCheck size={24} />}
          title="暂无审查评论"
        />
      )}
    </section>
  );
}
