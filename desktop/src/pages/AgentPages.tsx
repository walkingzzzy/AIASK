import { Play, Save, Send, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { useAsyncResource } from "../hooks/useAsyncResource";
import { mockMessages } from "../mock/mockData";
import type { RunEvent, UnknownRecord, WorkbenchMessage } from "../types";
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

function WorkbenchPage({ api, settings, controlAvailable }: PageProps) {
  const summary = useAsyncResource(() => api.workbenchSummary(), [api]);
  const aiStatus = useAsyncResource(() => api.aiStatus(), [api]);
  const [prompt, setPrompt] = useState("请检查数据状态，并给出下一步研究建议。");
  const [messages, setMessages] = useState<WorkbenchMessage[]>(mockMessages);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [responseEvidence, setResponseEvidence] = useState<unknown>(null);

  const summaryData = dataObject(summary.data, {});
  const stats = dataObject<UnknownRecord>(summaryData.stats, {});
  const recentRuns = firstArray(summaryData, ["runs", "recent_runs"]);
  const recentSessions = firstArray(summaryData, ["sessions", "recent_sessions"]);

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
    setMessages((current) => [...current, userMessage]);
    try {
      const result = await api.response({ prompt, user_id: settings?.userId, context: { source: "desktop_workbench" } });
      const record = dataObject(result, {});
      const response = dataObject<UnknownRecord>(record.response, {});
      setMessages((current) => [
        ...current,
        {
          id: String(record.id || `assistant_${Date.now()}`),
          role: "assistant",
          content: String(response.content || record.output_text || "Agent 已返回响应，请查看证据面板。"),
          created_at: new Date().toISOString(),
          status: String(dataObject<UnknownRecord>(record.run, {}).status || "completed")
        }
      ]);
      setEvents(Array.isArray(record.events) ? (record.events as RunEvent[]) : []);
      setResponseEvidence(result);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell
      title="AI 对话工作台"
      description="V1 默认入口，聚合模型状态、任务输入、运行事件、来源证据和金融上下文；副作用能力只创建意图或进入审批。"
      badge={<StatusBadge tone={settings?.mode === "mock" ? "warning" : "success"}>{settings?.mode === "mock" ? "Mock 模式" : "Live Agent"}</StatusBadge>}
      metrics={[
        metric("活跃会话", stats.active_sessions ?? recentSessions.length, "info"),
        metric("今日运行", stats.runs_today ?? recentRuns.length, "success"),
        metric("待审批", stats.pending_approvals ?? 0, Number(stats.pending_approvals || 0) > 0 ? "warning" : "neutral"),
        metric("数据门禁", stats.data_gates ?? 0, Number(stats.data_gates || 0) > 0 ? "warning" : "success")
      ]}
    >
      <div className="chat-layout">
        <div className="stack">
          <Panel title="任务输入" action={<GatedNotice controlAvailable={controlAvailable} action="高权限动作" />}>
            <div className="composer">
              <label className="field">
                <span>Prompt</span>
                <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} />
                <small>模型不可用时页面会显示门禁；真实发送只通过 `/v1/responses`。</small>
              </label>
              <Button tone="success" icon={<Send size={16} />} busy={busy} onClick={() => void submitPrompt()}>
                发送任务
              </Button>
            </div>
          </Panel>
          <Panel title="消息">
            <div className="messages">
              {messages.map((message) => (
                <article className={`message ${message.role}`} key={message.id}>
                  <div className="message-head">
                    <span>{message.role === "user" ? "用户" : "AIASK"}</span>
                    <span>{message.status || "ready"}</span>
                  </div>
                  <div>{message.content}</div>
                </article>
              ))}
            </div>
          </Panel>
          <Panel title="运行事件">
            {events.length ? (
              <div className="timeline">
                {events.map((event, index) => (
                  <div className="timeline-item" key={String(event.event_id || event.id || index)}>
                    <strong>{event.type || event.name || "event"}</strong>
                    <span>{event.status || event.timestamp || event.created_at}</span>
                    <p>{event.message || "事件已记录"}</p>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="暂无当前运行事件" detail="发送任务后会显示 run events、工具调用和产物创建状态。" />
            )}
          </Panel>
        </div>
        <div className="stack">
          <ResourcePanel title="模型状态" resource={aiStatus}>
            {(data) => {
              const item = dataObject(data, {});
              return (
                <div className="stack">
                  <StatusBadge tone={item.configured ? "success" : "warning"}>{item.configured ? "已配置" : "缺配置"}</StatusBadge>
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
          <ResourcePanel title="最近运行" resource={summary}>
            {() => (
              <DataTable
                items={recentRuns}
                columns={[
                  { key: "title", header: "运行" },
                  {
                    key: "status",
                    header: "状态",
                    render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge>
                  },
                  { key: "toolset", header: "Toolset" }
                ]}
              />
            )}
          </ResourcePanel>
          {responseEvidence ? <JsonPanel data={responseEvidence} title="响应证据" /> : null}
        </div>
      </div>
    </PageShell>
  );
}

function ModelsPage({ api, controlAvailable }: PageProps) {
  const status = useAsyncResource(() => api.aiStatus(), [api]);
  const config = useAsyncResource(() => api.aiConfig(), [api]);
  const models = useAsyncResource(() => api.aiModels(), [api]);
  const [form, setForm] = useState({ provider: "openai-compatible", model: "gpt-4.1-compatible", base_url: "", api_key: "" });
  const [result, setResult] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

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
      setResult(await api.aiSmoke({ provider: form.provider, model: form.model }));
    } finally {
      setBusy(false);
    }
  }

  const statusItem = dataObject(status.data, {});
  const configItem = dataObject(config.data, {});
  const modelRows = list(models.data);

  return (
    <PageShell
      title="模型配置与 LLM 可用性"
      description="展示 provider、model、base URL 和 key 配置状态；密钥只写入配置请求，不在页面回显。"
      badge={<StatusBadge tone={statusItem.configured ? "success" : "warning"}>{statusItem.configured ? "模型可用" : "需要配置"}</StatusBadge>}
      metrics={[
        metric("Provider", statusItem.provider || configItem.provider, "info"),
        metric("Model", statusItem.model || configItem.model, "success"),
        metric("API Key", statusItem.api_key_configured || configItem.api_key_configured ? "已配置" : "缺失", statusItem.api_key_configured || configItem.api_key_configured ? "success" : "warning"),
        metric("模型列表", modelRows.length, modelRows.length ? "success" : "warning")
      ]}
    >
      <div className="grid-2">
        <Panel title="配置表单" action={<GatedNotice controlAvailable={controlAvailable} action="保存配置" />}>
          <div className="form-grid">
            <label className="field">
              <span>Provider</span>
              <input value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })} />
            </label>
            <label className="field">
              <span>Model</span>
              <input value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} />
            </label>
            <label className="field">
              <span>Base URL</span>
              <input value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder="https://.../v1" />
            </label>
            <label className="field">
              <span>API Key</span>
              <input type="password" value={form.api_key} onChange={(event) => setForm({ ...form, api_key: event.target.value })} placeholder="只发送，不显示" />
            </label>
          </div>
          <div className="page-actions">
            <Button icon={<Save size={16} />} disabled={!controlAvailable} busy={busy} onClick={() => void saveConfig()}>
              保存配置
            </Button>
            <Button icon={<Play size={16} />} busy={busy} onClick={() => void smoke()}>
              LLM 测试
            </Button>
          </div>
        </Panel>
        <Panel title="模型列表">
          {models.loading ? <LoadingState /> : null}
          <DataTable
            items={modelRows}
            columns={[
              { key: "id", header: "模型" },
              { key: "provider", header: "Provider" },
              { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> }
            ]}
          />
        </Panel>
      </div>
      <JsonPanel data={{ status: status.data, config: config.data, last_result: result }} title="模型证据" />
    </PageShell>
  );
}

function ProjectsContextsPage({ api, settings }: PageProps) {
  const profile = useAsyncResource(() => api.localProfile(), [api]);
  const summary = useAsyncResource(() => api.workbenchSummary(), [api]);
  const sessions = firstArray(dataObject(summary.data, {}), ["sessions", "recent_sessions"]);
  return (
    <PageShell
      title="项目与上下文"
      description="整理本地用户、项目偏好、会话上下文和证据引用。V1 先做引用与证据展示，不假装已实现真实上传。"
      metrics={[
        metric("User", settings?.userId || "local-user", "info"),
        metric("上下文会话", sessions.length, "success"),
        metric("上传能力", "Deferred", "gated"),
        metric("证据引用", "Ready", "success")
      ]}
    >
      <div className="grid-2">
        <ResourcePanel title="本地画像" resource={profile}>
          {(data) => <JsonPanel data={data} title="画像数据" />}
        </ResourcePanel>
        <Panel title="上下文引用">
          <DataTable
            items={sessions}
            columns={[
              { key: "title", header: "会话" },
              { key: "message_count", header: "消息数" },
              { key: "updated_at", header: "更新时间" }
            ]}
          />
        </Panel>
      </div>
    </PageShell>
  );
}

function SessionsRunsPage({ api }: PageProps) {
  const sessions = useAsyncResource(() => api.sessions(), [api]);
  const runs = useAsyncResource(() => api.desktopRuns(), [api]);
  const runRows = list(runs.data);
  const [selectedRun, setSelectedRun] = useState<string>("run_20260621_001");
  const events = useAsyncResource(() => api.runEvents(selectedRun), [api, selectedRun]);
  const artifacts = useAsyncResource(() => api.runArtifacts(selectedRun), [api, selectedRun]);
  const sources = useAsyncResource(() => api.runSources(selectedRun), [api, selectedRun]);
  const sessionRows = list(sessions.data);

  return (
    <PageShell
      title="会话、运行、事件与产物"
      description="把历史对话、运行事件、产物、来源和工具调用放在同一排障视图里。"
      metrics={[
        metric("会话", sessionRows.length, "info"),
        metric("运行", runRows.length, "success"),
        metric("事件", events.data?.length || 0, "warning"),
        metric("证据", list(artifacts.data).length + list(sources.data).length, "info")
      ]}
    >
      <div className="grid-2">
        <Panel title="会话">
          <DataTable
            items={sessionRows}
            columns={[
              { key: "title", header: "标题" },
              { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> },
              { key: "message_count", header: "消息" }
            ]}
          />
        </Panel>
        <Panel title="运行">
          <DataTable
            items={runRows}
            columns={[
              { key: "title", header: "标题" },
              { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> },
              {
                key: "id",
                header: "详情",
                render: (item) => (
                  <Button onClick={() => setSelectedRun(String(item.id || ""))} disabled={!item.id}>
                    查看
                  </Button>
                )
              }
            ]}
          />
        </Panel>
      </div>
      <div className="grid-3">
        <Panel title="事件时间线">
          <div className="timeline">
            {(events.data || []).map((event, index) => (
              <div className="timeline-item" key={String(event.event_id || event.id || index)}>
                <strong>{event.type || event.name || "event"}</strong>
                <span>{event.status || event.timestamp || event.created_at}</span>
                <p>{event.message || "事件已记录"}</p>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="产物">
          <DataTable items={list(artifacts.data)} columns={[{ key: "kind", header: "类型" }, { key: "title", header: "标题" }, { key: "created_at", header: "时间" }]} />
        </Panel>
        <Panel title="来源">
          <DataTable items={list(sources.data)} columns={[{ key: "source_type", header: "来源类型" }, { key: "title", header: "标题" }, { key: "uri", header: "URI" }]} />
        </Panel>
      </div>
    </PageShell>
  );
}

function ToolsApprovalsPage({ api, controlAvailable }: PageProps) {
  const tools = useAsyncResource(() => api.tools(), [api]);
  const intents = useAsyncResource(() => api.intents(), [api]);
  const approvals = useAsyncResource(() => api.approvals(), [api]);
  const toolRows = useMemo(
    () =>
      list(tools.data).filter((tool) => {
        const name = String(tool.name || "");
        return name.startsWith("agent_") && !/(strategy_factory|factor_factory|incubation|factory_event)/i.test(name);
      }),
    [tools.data]
  );

  async function createSafeIntent() {
    await api.createIntent({
      title: "V1 safe diagnostic intent",
      action: "diagnostic_preview",
      side_effect: "none",
      reason: "desktop V1 gated flow check"
    });
    await intents.reload();
  }

  return (
    <PageShell
      title="Agent 工具、Intent 与审批"
      description="只展示 agent_* 工具门面；有副作用的动作必须走 ActionIntent 或审批，不暴露 raw manager。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="创建意图/审批决策" />}
      actions={
        <Button icon={<ShieldCheck size={16} />} disabled={!controlAvailable} onClick={() => void createSafeIntent()}>
          创建诊断意图
        </Button>
      }
      metrics={[
        metric("agent_* 工具", toolRows.length, "success"),
        metric("Intent", list(intents.data).length, "warning"),
        metric("审批", list(approvals.data).length, "warning"),
        metric("Raw manager", "隐藏", "success")
      ]}
    >
      <div className="grid-3">
        <Panel title="工具目录">
          <DataTable
            items={toolRows}
            columns={[
              { key: "name", header: "工具" },
              { key: "category", header: "分类" },
              { key: "side_effect", header: "副作用", render: (item) => <StatusBadge tone={statusTone(item.side_effect)}>{valueOf(item, ["side_effect"])}</StatusBadge> }
            ]}
          />
        </Panel>
        <Panel title="ActionIntent">
          <DataTable
            items={list(intents.data)}
            columns={[
              { key: "title", header: "意图" },
              { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> },
              { key: "side_effect", header: "风险" }
            ]}
          />
        </Panel>
        <Panel title="审批队列">
          <DataTable
            items={list(approvals.data)}
            columns={[
              { key: "title", header: "审批" },
              { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> },
              { key: "risk", header: "风险" }
            ]}
          />
        </Panel>
      </div>
      <JsonPanel data={{ tools: tools.data, intents: intents.data, approvals: approvals.data }} title="工具与审批证据" />
    </PageShell>
  );
}
