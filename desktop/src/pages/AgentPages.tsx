import { Play, Save, Send, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ApprovalQueue, DryRunPreview, GatedActionButton, type ActionIntent } from "../components/IntentComponents";
import { EmptyState as SharedEmptyState, MockDataNotice } from "../components/StateComponents";
import {
  Button,
  DataTable,
  EmptyState,
  GatedNotice,
  JsonPanel,
  LoadingState,
  PageShell,
  Panel,
  ResourcePanel,
  StatusBadge
} from "../components/ui";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { mockMessages } from "../mock/mockData";
import type { RunEvent, UnknownRecord, WorkbenchMessage } from "../types";
import { dataObject, firstArray, list, metric, type PageProps, statusTone, valueOf } from "./pageUtils";

export function AgentPages(props: PageProps) {
  switch (props.view) {
    case "workbench":
      return <WorkbenchPage {...props} />;
    case "models":
      return <ModelsPage {...props} />;
    case "projects-contexts":
      return <ProjectsContextsPage {...props} />;
    case "sessions-runs":
      return <SessionsRunsPage {...props} />;
    case "tools-approvals":
      return <ToolsApprovalsPage {...props} />;
    default:
      return null;
  }
}

function buildIntentPreview(intent: UnknownRecord | null | undefined) {
  if (!intent) return [];
  return [
    { label: "动作", after: valueOf(intent, ["action", "title"], "-") },
    { label: "状态", after: valueOf(intent, ["status"], "-") },
    { label: "副作用", after: valueOf(intent, ["side_effect", "risk"], "-") }
  ];
}

function normalizeIntent(item: UnknownRecord): ActionIntent {
  return {
    id: String(item.id || item.intent_id || ""),
    action: valueOf(item, ["action", "title"], "unknown"),
    payload: (item.payload || item.params || item.data) as UnknownRecord | undefined,
    side_effect: valueOf(item, ["side_effect", "risk"], ""),
    risk_level: (String(item.risk_level || item.risk || "medium").toLowerCase() as ActionIntent["risk_level"]) || "medium",
    status: (String(item.status || "pending").toLowerCase() as ActionIntent["status"]) || "pending",
    created_at: String(item.created_at || ""),
    reason: valueOf(item, ["rationale", "reason"], "")
  };
}

function WorkbenchPage({
  api,
  settings,
  controlAvailable,
  workbench,
  reloadWorkbench,
  setSelectedRunId,
  setSelectedMessageId,
  setSelectedArtifactId,
  setSelectedApprovalId,
  setSelectedReviewTab
}: PageProps) {
  const summary = useAsyncResource(() => api.workbenchSummary(), [api]);
  const aiStatus = useAsyncResource(() => api.aiStatus(), [api]);
  const [prompt, setPrompt] = useState("请检查当前线程的上下文、运行状态和证据链，然后给出下一步建议。");
  const [busy, setBusy] = useState(false);
  const [responseEvidence, setResponseEvidence] = useState<unknown>(null);
  const [localMessages, setLocalMessages] = useState<WorkbenchMessage[]>([]);

  const summaryData = dataObject(summary.data, {});
  const stats = dataObject<UnknownRecord>(summaryData.stats, {});
  const recentRuns = list(workbench?.availableRuns);
  const recentSessions = workbench?.availableThreads || [];
  const messages = useMemo(() => {
    const threadMessages = workbench?.selectedSessionMessages || [];
    if (threadMessages.length) return [...threadMessages, ...localMessages];
    return [...mockMessages, ...localMessages];
  }, [localMessages, workbench?.selectedSessionMessages]);

  async function submitPrompt() {
    if (!prompt.trim()) return;
    setBusy(true);
    const userMessage: WorkbenchMessage = {
      id: `user_${Date.now()}`,
      role: "user",
      content: prompt,
      created_at: new Date().toISOString(),
      status: "sent"
    };
    setLocalMessages((current) => [...current, userMessage]);
    setSelectedMessageId?.(userMessage.id);

    try {
      const result = await api.response({
        prompt,
        user_id: settings?.userId,
        session_id: workbench?.selectedThreadId,
        context: {
          source: "desktop_workbench",
          selected_run_id: workbench?.selectedRunId
        }
      });
      const record = dataObject(result, {});
      const response = dataObject<UnknownRecord>(record.response, {});
      const nextMessage: WorkbenchMessage = {
        id: String(record.id || `assistant_${Date.now()}`),
        role: "assistant",
        content: String(response.content || record.output_text || "Agent 已返回响应，请查看证据面板。"),
        created_at: new Date().toISOString(),
        status: String(dataObject<UnknownRecord>(record.run, {}).status || "completed")
      };
      setLocalMessages((current) => [...current, nextMessage]);
      setSelectedMessageId?.(nextMessage.id);
      setResponseEvidence(result);

      const runId = String(dataObject<UnknownRecord>(record.run, {}).id || "");
      if (runId) {
        setSelectedRunId?.(runId);
      }
      await Promise.all([summary.reload(), reloadWorkbench?.() || Promise.resolve()]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell
      title="AI 任务工作台"
      description="以线程为中心组织消息、运行事件、产物、审批和复核入口。中间区始终围绕当前线程展开。"
      badge={<StatusBadge tone={settings?.mode === "mock" ? "warning" : "success"}>{settings?.mode === "mock" ? "Mock 模式" : "Live Agent"}</StatusBadge>}
      metrics={[
        metric("活跃会话", stats.active_sessions ?? recentSessions.length, "info"),
        metric("当前运行", workbench?.currentRun ? valueOf(workbench.currentRun, ["status"]) : "未选择", workbench?.currentRun ? statusTone(workbench.currentRun.status) : "warning"),
        metric("待审批", list(workbench?.approvals).length, list(workbench?.approvals).length ? "warning" : "neutral"),
        metric("当前产物", workbench?.selectedRunArtifacts.length || 0, workbench?.selectedRunArtifacts.length ? "success" : "neutral")
      ]}
    >
      {settings?.mode === "mock" ? <MockDataNotice /> : null}
      <div className="chat-layout">
        <div className="stack">
          <Panel title="任务头部" action={<GatedNotice controlAvailable={controlAvailable} action="高权限动作" />}>
            <div className="workbench-header-grid">
              <div className="workbench-header-card">
                <span>线程</span>
                <strong>{workbench?.currentThread?.title || "未选择线程"}</strong>
                <p>{workbench?.selectedThreadId || "请先在左侧选择线程"}</p>
              </div>
              <div className="workbench-header-card">
                <span>运行</span>
                <strong>{valueOf(workbench?.currentRun || {}, ["title", "id", "run_id"], "暂无运行")}</strong>
                <p>{valueOf(workbench?.currentRun || {}, ["status"], "尚未开始")}</p>
              </div>
              <div className="workbench-header-card">
                <span>审阅焦点</span>
                <strong>{workbench?.selectedReviewTab || "overview"}</strong>
                <p>右侧 Inspector 与当前线程保持同步。</p>
              </div>
            </div>
          </Panel>

          <Panel title="Composer" action={<GatedNotice controlAvailable={controlAvailable} action="发送任务" />}>
            <div className="composer">
              <label className="field">
                <span>Prompt</span>
                <textarea data-testid="workbench-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} />
                <small>真实请求只通过 `/v1/responses` 发出，并携带当前线程与运行上下文。</small>
              </label>
              <Button data-testid="workbench-submit" tone="success" icon={<Send size={16} />} busy={busy} onClick={() => void submitPrompt()}>
                发送任务
              </Button>
            </div>
          </Panel>

          <Panel title="消息时间线">
            {messages.length ? (
              <div className="messages">
                {messages.map((message) => (
                  <article
                    className={`message ${message.role} ${workbench?.selectedMessageId === message.id ? "selected" : ""}`}
                    key={message.id}
                    onClick={() => setSelectedMessageId?.(message.id)}
                  >
                    <div className="message-head">
                      <span>{message.role === "user" ? "用户" : message.role === "assistant" ? "AIASK" : "System"}</span>
                      <span>{message.status || "ready"}</span>
                    </div>
                    <div>{message.content}</div>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState title="暂无消息" detail="选择线程后会展示历史消息，发送新任务后会继续追加。" />
            )}
          </Panel>

          <Panel title="当前运行事件时间线">
            {workbench?.selectedRunEvents.length ? (
              <div className="timeline">
                {workbench.selectedRunEvents.map((event, index) => (
                  <div className="timeline-item" key={String(event.event_id || event.id || index)}>
                    <strong>{event.type || event.name || "event"}</strong>
                    <span>{event.status || event.timestamp || event.created_at}</span>
                    <p>{event.message || "事件已记录"}</p>
                  </div>
                ))}
              </div>
            ) : (
              <SharedEmptyState title="暂无当前运行事件" detail="选择一个运行后，这里会展示事件时间线。" />
            )}
          </Panel>
        </div>

        <div className="stack">
          <ResourcePanel title="模型状态" resource={aiStatus}>
            {(data) => {
              const item = dataObject(data, {});
              return (
                <div className="stack">
                  <StatusBadge tone={item.configured ? "success" : "warning"}>{item.configured ? "已配置" : "缺少配置"}</StatusBadge>
                  <DataTable
                    items={[item]}
                    columns={[
                      { key: "provider", header: "Provider" },
                      { key: "model", header: "Model" },
                      { key: "source_mode", header: "Mode" }
                    ]}
                  />
                </div>
              );
            }}
          </ResourcePanel>

          <Panel title="产物摘要">
            <DataTable
              items={workbench?.selectedRunArtifacts || []}
              columns={[
                { key: "kind", header: "类型" },
                { key: "title", header: "标题" },
                {
                  key: "id",
                  header: "查看",
                  render: (item) => (
                    <Button onClick={() => {
                      setSelectedArtifactId?.(String(item.id || item.artifact_id || ""));
                      setSelectedReviewTab?.("artifacts");
                    }}>
                      审阅
                    </Button>
                  )
                }
              ]}
              empty="暂无产物"
            />
          </Panel>

          <Panel title="审批与复核入口">
            <div className="page-actions">
              <Button onClick={() => setSelectedReviewTab?.("approvals")}>查看审批</Button>
              <Button onClick={() => setSelectedReviewTab?.("review")}>进入复核</Button>
              <Button onClick={() => setSelectedReviewTab?.("diagnostics")}>查看诊断</Button>
            </div>
          </Panel>

          <JsonPanel
            data={{
              response_evidence: responseEvidence,
              thread: workbench?.currentThread,
              run: workbench?.currentRun,
              raw_events: workbench?.selectedRunEvents,
              raw_sources: workbench?.selectedRunSources,
              raw_tools: workbench?.selectedRunTools
            }}
            title="折叠 Raw Evidence"
          />
        </div>
      </div>
    </PageShell>
  );
}

function ModelsPage({ api, controlAvailable }: PageProps) {
  const status = useAsyncResource(() => api.aiStatus(), [api]);
  const config = useAsyncResource(() => api.aiConfig(), [api]);
  const models = useAsyncResource(() => api.aiModels(), [api]);
  const [form, setForm] = useState({ provider: "", model: "", base_url: "", api_key: "" });
  const [result, setResult] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const statusItem = dataObject(status.data, {});
  const configItem = dataObject(config.data, {});
  const modelRows = list(models.data);

  useEffect(() => {
    setForm((current) => {
      if (current.provider || current.model || current.base_url) return current;
      const provider = String(configItem.provider || statusItem.provider || "");
      const model = String(configItem.model || statusItem.model || "");
      const baseUrl = String(configItem.base_url || statusItem.base_url || "");
      if (!provider && !model && !baseUrl) return current;
      return { ...current, provider, model, base_url: baseUrl };
    });
  }, [configItem.base_url, configItem.model, configItem.provider, statusItem.base_url, statusItem.model, statusItem.provider]);

  async function saveConfig() {
    setBusy(true);
    try {
      setResult(await api.aiConfigSave(form));
      await Promise.all([status.reload(), config.reload()]);
    } finally {
      setBusy(false);
    }
  }

  async function smoke() {
    setBusy(true);
    try {
      setResult(
        await api.aiSmoke({
          provider: form.provider.trim() || String(statusItem.provider || configItem.provider || ""),
          model: form.model.trim() || String(statusItem.model || configItem.model || "")
        })
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell
      title="模型配置与 Readiness"
      description="统一展示 provider、model、base URL、密钥配置状态，以及 smoke 测试与模型可用性。"
      badge={<StatusBadge tone={statusItem.configured ? "success" : "warning"}>{statusItem.configured ? "模型可用" : "需要配置"}</StatusBadge>}
      metrics={[
        metric("Provider", statusItem.provider || configItem.provider, "info"),
        metric("Model", statusItem.model || configItem.model, "success"),
        metric(
          "API Key",
          statusItem.api_key_configured || configItem.api_key_configured ? "已配置" : "缺失",
          statusItem.api_key_configured || configItem.api_key_configured ? "success" : "warning"
        ),
        metric("模型列表", modelRows.length, modelRows.length ? "success" : "warning")
      ]}
    >
      <div className="grid-2">
        <Panel title="配置表单" action={<GatedNotice controlAvailable={controlAvailable} action="保存配置" />}>
          <div className="form-grid">
            <label className="field">
              <span>Provider</span>
              <input data-testid="model-provider" value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })} />
            </label>
            <label className="field">
              <span>Model</span>
              <input data-testid="model-name" value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} />
            </label>
            <label className="field">
              <span>Base URL</span>
              <input
                data-testid="model-base-url"
                value={form.base_url}
                onChange={(event) => setForm({ ...form, base_url: event.target.value })}
                placeholder="https://.../v1"
              />
            </label>
            <label className="field">
              <span>API Key</span>
              <input type="password" value={form.api_key} onChange={(event) => setForm({ ...form, api_key: event.target.value })} placeholder="仅发送，不回显" />
            </label>
          </div>
          <div className="page-actions">
            <Button data-testid="model-save-config" icon={<Save size={16} />} disabled={!controlAvailable} busy={busy} onClick={() => void saveConfig()}>
              保存配置
            </Button>
            <Button data-testid="model-smoke" icon={<Play size={16} />} busy={busy} onClick={() => void smoke()}>
              LLM 测试
            </Button>
          </div>
        </Panel>

        <Panel title="模型可用性">
          {models.loading ? <LoadingState /> : null}
          <DataTable
            items={modelRows}
            columns={[
              { key: "id", header: "模型" },
              { key: "provider", header: "Provider" },
              {
                key: "status",
                header: "状态",
                render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge>
              }
            ]}
          />
        </Panel>
      </div>
      <JsonPanel data={{ status: status.data, config: config.data, last_result: result }} title="模型证据" />
    </PageShell>
  );
}

function ProjectsContextsPage({ api, settings, workbench }: PageProps) {
  const profile = useAsyncResource(() => api.localProfile(), [api]);

  return (
    <PageShell
      title="项目上下文"
      description="承接项目上下文、用户画像、证据引用和 endpoint/profile，保持线程上下文与项目视角一致。"
      metrics={[
        metric("User", settings?.userId || "local-user", "info"),
        metric("当前线程", workbench?.currentThread?.title || "未选择", "success"),
        metric("关联会话", workbench?.availableThreads.length || 0, "success"),
        metric("证据引用", workbench?.selectedRunSources.length || 0, "info")
      ]}
    >
      <div className="grid-2">
        <ResourcePanel title="用户画像与 Profile" resource={profile}>
          {(data) => <JsonPanel data={data} title="Profile 数据" />}
        </ResourcePanel>

        <Panel title="上下文引用">
          <DataTable
            items={workbench?.availableThreads || []}
            columns={[
              { key: "title", header: "会话" },
              { key: "messageCount", header: "消息数" },
              { key: "updatedAt", header: "最近更新时间" }
            ]}
            empty="暂无上下文会话"
          />
        </Panel>
      </div>

      <Panel title="当前线程证据">
        <DataTable
          items={workbench?.selectedRunSources || []}
          columns={[
            { key: "source_type", header: "来源类型" },
            { key: "title", header: "标题" },
            { key: "uri", header: "URI" }
          ]}
          empty="暂无证据来源"
        />
      </Panel>
    </PageShell>
  );
}

function SessionsRunsPage({
  api,
  controlAvailable,
  workbench,
  setSelectedThreadId,
  setSelectedRunId,
  reloadWorkbench
}: PageProps) {
  const [controlResult, setControlResult] = useState<unknown>(null);
  const [showPreview, setShowPreview] = useState<null | "cancel" | "stop" | "steer">(null);
  const [steerInstruction, setSteerInstruction] = useState("请总结当前运行状态，并只继续安全动作。");
  const selectedRunId = workbench?.selectedRunId || "";
  const sessionRows = (workbench?.availableThreads || []).map((thread) => ({
    id: thread.id,
    title: thread.title,
    status: thread.status,
    message_count: thread.messageCount,
    updated_at: thread.updatedAt
  }));
  const runRows = workbench?.availableRuns || [];

  async function controlRun(action: "cancel" | "stop" | "steer") {
    if (!selectedRunId) return;
    const result =
      action === "cancel"
        ? await api.runCancel(selectedRunId)
        : action === "stop"
          ? await api.runStop(selectedRunId)
          : await api.runSteer(selectedRunId, steerInstruction);
    setControlResult(result);
    setShowPreview(null);
    await reloadWorkbench?.();
  }

  return (
    <PageShell
      title="Runs 工作面"
      description="用会话、运行、事件、产物、来源和工具调用组成联动式工作面，默认跟随当前线程。"
      metrics={[
        metric("会话", sessionRows.length, "info"),
        metric("运行", runRows.length, "success"),
        metric("事件", workbench?.selectedRunEvents.length || 0, "warning"),
        metric("工具调用", workbench?.selectedRunTools.length || 0, "info")
      ]}
    >
      <div className="grid-2">
        <Panel title="会话列表">
          <DataTable
            items={sessionRows}
            columns={[
              { key: "title", header: "标题" },
              {
                key: "status",
                header: "状态",
                render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge>
              },
              { key: "message_count", header: "消息" },
              {
                key: "id",
                header: "联动",
                render: (item) => (
                  <Button onClick={() => setSelectedThreadId?.(String(item.id || ""))}>
                    选中线程
                  </Button>
                )
              }
            ]}
            empty="暂无会话"
          />
        </Panel>

        <Panel title="运行列表">
          <DataTable
            items={runRows}
            columns={[
              { key: "title", header: "标题" },
              {
                key: "status",
                header: "状态",
                render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge>
              },
              { key: "toolset", header: "Toolset" },
              {
                key: "id",
                header: "详情",
                render: (item) => (
                  <Button onClick={() => setSelectedRunId?.(String(item.id || ""))} disabled={!item.id}>
                    查看
                  </Button>
                )
              }
            ]}
            empty="暂无运行"
          />
        </Panel>
      </div>

      <div className="grid-3">
        <Panel title="事件时间线">
          {workbench?.selectedRunEvents.length ? (
            <div className="timeline">
              {workbench.selectedRunEvents.map((event, index) => (
                <div className="timeline-item" key={String(event.event_id || event.id || index)}>
                  <strong>{event.type || event.name || "event"}</strong>
                  <span>{event.status || event.timestamp || event.created_at}</span>
                  <p>{event.message || "事件已记录"}</p>
                </div>
              ))}
            </div>
          ) : (
            <SharedEmptyState title="暂无运行事件" detail="选中运行后会在这里展示事件时间线。" />
          )}
        </Panel>

        <Panel title="产物">
          <DataTable
            items={workbench?.selectedRunArtifacts || []}
            columns={[
              { key: "kind", header: "类型" },
              { key: "title", header: "标题" },
              { key: "created_at", header: "时间" }
            ]}
            empty="暂无产物"
          />
        </Panel>

        <Panel title="来源与工具">
          <DataTable
            items={[...(workbench?.selectedRunSources || []), ...(workbench?.selectedRunTools || [])]}
            columns={[
              { key: "source_type", header: "来源/工具" },
              { key: "title", header: "标题" },
              { key: "uri", header: "URI / Name" }
            ]}
            empty="暂无来源或工具调用"
          />
        </Panel>
      </div>

      <Panel title="Run Control">
        <div className="form-grid">
          <label className="field">
            <span>Run ID</span>
            <input data-testid="run-id-input" value={selectedRunId} onChange={(event) => setSelectedRunId?.(event.target.value)} />
          </label>
          <label className="field">
            <span>Steer instruction</span>
            <input data-testid="run-steer-instruction" value={steerInstruction} onChange={(event) => setSteerInstruction(event.target.value)} />
          </label>
        </div>

        <div className="page-actions">
          <Button data-testid="run-steer" disabled={!controlAvailable || !selectedRunId} onClick={() => setShowPreview("steer")}>
            Steer
          </Button>
          <Button data-testid="run-stop" disabled={!controlAvailable || !selectedRunId} onClick={() => setShowPreview("stop")}>
            Stop
          </Button>
          <Button data-testid="run-cancel" disabled={!controlAvailable || !selectedRunId} onClick={() => setShowPreview("cancel")}>
            Cancel
          </Button>
        </div>

        {showPreview ? (
          <DryRunPreview
            title="确认 Run Control 动作"
            changes={[
              { label: "Run ID", after: selectedRunId || "-" },
              { label: "动作", after: showPreview },
              { label: "说明", after: showPreview === "steer" ? steerInstruction : "将请求后端执行受控动作" }
            ]}
            onCancel={() => setShowPreview(null)}
            onConfirm={() => void controlRun(showPreview)}
          />
        ) : null}

        {controlResult ? <JsonPanel data={controlResult} title="Run control result" /> : null}
      </Panel>
    </PageShell>
  );
}

function ToolsApprovalsPage({
  api,
  controlAvailable,
  workbench,
  setSelectedApprovalId,
  reloadWorkbench
}: PageProps) {
  const tools = useAsyncResource(() => api.tools(), [api]);
  const intents = useAsyncResource(() => api.intents(), [api]);
  const approvals = useAsyncResource(() => api.approvals(), [api]);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const [pendingIntentId, setPendingIntentId] = useState("");
  const [previewIntent, setPreviewIntent] = useState<UnknownRecord | null>(null);

  const toolRows = useMemo(
    () =>
      list(tools.data).filter((tool) => {
        const name = String(tool.name || "");
        return name.startsWith("agent_") && !/(strategy_factory|factor_factory|incubation|factory_event)/i.test(name);
      }),
    [tools.data]
  );
  const intentRows = list(intents.data);
  const approvalRows = list(approvals.data);
  const normalizedIntents = intentRows.map(normalizeIntent);

  async function createSafeIntent() {
    const result = await api.createIntent({
      title: "V1 safe data sync dry-run intent",
      action: "data_sync.sync",
      params: { task_type: "preflight", codes: ["600519"], dry_run: true },
      rationale: "desktop V1 gated flow check"
    });
    const envelope = result && typeof result === "object" ? (result as UnknownRecord) : {};
    const data = envelope.data && typeof envelope.data === "object" ? (envelope.data as UnknownRecord) : {};
    const intent = dataObject(data.intent || envelope.intent || data, {});
    setPendingIntentId(String(intent.intent_id || intent.id || ""));
    setActionResult(result);
    setPreviewIntent(intent);
    await Promise.all([intents.reload(), reloadWorkbench?.() || Promise.resolve()]);
  }

  async function decideFirstIntent(decision: "confirm" | "deny") {
    const first = intentRows.find((item) => /pending|awaiting/i.test(String(item.status || ""))) || intentRows[0];
    const intentId = pendingIntentId || String(first?.id || first?.intent_id || "");
    if (!intentId) return;
    const result = decision === "confirm" ? await api.intentConfirm(intentId) : await api.intentDeny(intentId);
    setPendingIntentId("");
    setActionResult(result);
    await Promise.all([intents.reload(), reloadWorkbench?.() || Promise.resolve()]);
  }

  async function decideFirstApproval(decision: "approve" | "deny") {
    const first = approvalRows[0];
    const approvalId = String(first?.id || first?.approval_id || "");
    if (!approvalId) return;
    setSelectedApprovalId?.(approvalId);
    const result = await api.approvalDecision(approvalId, decision);
    setActionResult(result);
    await Promise.all([approvals.reload(), reloadWorkbench?.() || Promise.resolve()]);
  }

  return (
    <PageShell
      title="Approvals 审阅流"
      description="把工具目录、pending intents、approvals、风险说明和确认结果放在同一条审阅流里。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="创建意图 / 审批决策" />}
      actions={
        <GatedActionButton
          action="data_sync.sync"
          payload={{ task_type: "preflight", codes: ["600519"], dry_run: true }}
          onCreateIntent={async () => {
            await createSafeIntent();
          }}
          controlAvailable={controlAvailable}
          requiresApproval
          riskLevel="medium"
        >
          <span data-testid="create-safe-intent">创建诊断意图</span>
        </GatedActionButton>
      }
      metrics={[
        metric("agent_* 工具", toolRows.length, "success"),
        metric("Intent", intentRows.length, "warning"),
        metric("审批", approvalRows.length, "warning"),
        metric("当前线程审批", list(workbench?.approvals).length, list(workbench?.approvals).length ? "warning" : "success")
      ]}
    >
      <div className="grid-3">
        <Panel title="工具目录">
          <DataTable
            items={toolRows}
            columns={[
              { key: "name", header: "工具" },
              { key: "category", header: "分类" },
              {
                key: "side_effect",
                header: "副作用",
                render: (item) => <StatusBadge tone={statusTone(item.side_effect)}>{valueOf(item, ["side_effect"])}</StatusBadge>
              }
            ]}
          />
        </Panel>

        <Panel title="Pending Intents">
          <ApprovalQueue
            intents={normalizedIntents}
            onApprove={(id) => api.intentConfirm(id).then((result) => {
              setActionResult(result);
            })}
            onDeny={(id) => api.intentDeny(id).then((result) => {
              setActionResult(result);
            })}
            canManage={controlAvailable}
          />
        </Panel>

        <Panel title="审批队列">
          <DataTable
            items={approvalRows}
            columns={[
              { key: "title", header: "审批" },
              {
                key: "status",
                header: "状态",
                render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge>
              },
              { key: "risk", header: "风险" },
              {
                key: "id",
                header: "审阅",
                render: (item) => (
                  <Button onClick={() => setSelectedApprovalId?.(String(item.id || item.approval_id || ""))}>
                    查看
                  </Button>
                )
              }
            ]}
          />
        </Panel>
      </div>

      <Panel title="决策结果与风险说明">
        <div className="page-actions">
          <span className="muted" data-testid="pending-intent-id">{pendingIntentId || "none"}</span>
          <Button data-testid="intent-confirm-first" disabled={!controlAvailable || (!pendingIntentId && !intentRows.length)} onClick={() => void decideFirstIntent("confirm")}>
            Confirm first intent
          </Button>
          <Button data-testid="intent-deny-first" disabled={!controlAvailable || (!pendingIntentId && !intentRows.length)} onClick={() => void decideFirstIntent("deny")}>
            Deny first intent
          </Button>
          <Button data-testid="approval-approve-first" disabled={!controlAvailable || !approvalRows.length} onClick={() => void decideFirstApproval("approve")}>
            Approve first approval
          </Button>
          <Button data-testid="approval-deny-first" disabled={!controlAvailable || !approvalRows.length} onClick={() => void decideFirstApproval("deny")}>
            Deny first approval
          </Button>
        </div>

        {previewIntent ? (
          <DryRunPreview
            title="新建意图预览"
            changes={buildIntentPreview(previewIntent)}
            onCancel={() => setPreviewIntent(null)}
            onConfirm={() => setPreviewIntent(null)}
          />
        ) : null}

        {actionResult ? <JsonPanel data={actionResult} title="Decision result" /> : null}
      </Panel>

      <JsonPanel data={{ tools: tools.data, intents: intents.data, approvals: approvals.data }} title="工具与审批证据" />
    </PageShell>
  );
}
