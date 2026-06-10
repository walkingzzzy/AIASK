import { BarChart3, ClipboardCheck, FileJson, FileText, Image, MessageSquare, ShieldCheck, Sparkles } from "lucide-react";
import { EmptyState, RawEvidencePanel, StatusBadge } from "./shared";
import type { AgentResponse, DesktopRunSummary, TaskArtifact, TaskReviewComment, TaskThread, TimelineEvent } from "../types";

function artifactIcon(kind: TaskArtifact["kind"]) {
  switch (kind) {
    case "screenshot":
      return Image;
    case "json":
      return FileJson;
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

export function buildTaskArtifacts({
  selectedThread,
  selectedResponse,
  recentRuns,
  timelineEvents
}: {
  selectedThread: TaskThread | null;
  selectedResponse?: AgentResponse | null;
  recentRuns?: DesktopRunSummary[];
  timelineEvents?: TimelineEvent[];
}): TaskArtifact[] {
  const artifacts: TaskArtifact[] = [];
  const response = selectedResponse || selectedThread?.response || null;
  if (selectedThread) {
    artifacts.push({
      id: `thread:${selectedThread.id}`,
      kind: "note",
      title: selectedThread.title || "当前线程",
      description: selectedThread.prompt || "线程已就绪，可以继续后续工作。",
      status: selectedThread.status,
      source: selectedThread.sessionId || selectedThread.id,
      createdAt: selectedThread.createdAt,
      sourceView: "workbench",
      targetPath: selectedThread.sessionId ? `sessions/${selectedThread.sessionId}` : `threads/${selectedThread.id}`,
      severity: selectedThread.status.toLowerCase() === "blocked" ? "critical" : selectedThread.status.toLowerCase() === "queued" ? "warning" : "info"
    });
  }
  if (response) {
    artifacts.push({
      id: `response:${response.id}`,
      kind: "report",
      title: "Agent 回复摘要",
      description: response.output_text || "已捕获回复 payload，等待复核。",
      status: response.status,
      source: response.metadata?.run_id || response.metadata?.session_id || response.id,
      sourceView: "workbench",
      targetPath: response.metadata?.run_id ? `runs/${response.metadata.run_id}` : `responses/${response.id}`,
      severity: response.status?.toLowerCase?.() === "failed" ? "critical" : "info",
      value: response
    });
    if (response.metadata?.tool_calls?.length) {
      artifacts.push({
        id: `tools:${response.id}`,
        kind: "json",
        title: "工具调用证据",
        description: `${response.metadata.tool_calls.length} 条工具调用记录`,
        status: "ready",
        source: response.id,
        sourceView: "tools-intents-approvals",
        targetPath: `responses/${response.id}/tool-calls`,
        severity: "info",
        value: response.metadata.tool_calls
      });
    }
  }
  (recentRuns || []).slice(0, 3).forEach((run) => {
    artifacts.push({
      id: `run:${run.run_id}`,
      kind: "run",
      title: `运行 ${run.run_id}`,
      description: `工具 ${run.tool_call_count ?? 0} / 审批 ${run.approval_count ?? 0} / 错误 ${run.error_count ?? 0}`,
      status: run.status,
      source: run.run_id,
      sourceView: "runs-events",
      targetPath: `runs/${run.run_id}`,
      severity: run.error_count ? "critical" : run.has_pending_approval ? "warning" : "info",
      value: run
    });
  });
  const approvalEvents = (timelineEvents || []).filter((event) => event.kind === "approval").slice(0, 3);
  approvalEvents.forEach((event) => {
    artifacts.push({
      id: `approval:${event.id}`,
      kind: "approval",
      title: event.title || "审批事件",
      description: event.body || "当前时间线中捕获到审批事件。",
      status: "approval_required",
      source: event.id,
      sourceView: "tools-intents-approvals",
      targetPath: `timeline/${event.id}`,
      severity: "warning",
      value: event
    });
  });
  if (!artifacts.length) {
    artifacts.push({
      id: "empty:guide",
      kind: "note",
      title: "暂无产物",
      description: "运行任务或选择线程后，这里会收集回复、工具证据、审批、截图和报告。",
      status: "idle",
      sourceView: "workbench",
      severity: "info"
    });
  }
  return artifacts;
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

export function ArtifactCard({ artifact, compact = false }: { artifact: TaskArtifact; compact?: boolean }) {
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
  compact = false
}: {
  artifacts: TaskArtifact[];
  compact?: boolean;
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
      <div className="artifact-list">
        {artifacts.map((artifact) => <ArtifactCard artifact={artifact} compact={compact} key={artifact.id} />)}
      </div>
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
