import { Radio, Send } from "lucide-react";
import { useMemo, useState } from "react";

import { DryRunPreview } from "../components/IntentComponents";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { Button, DataTable, GatedNotice, JsonPanel, LinkCard, PageShell, Panel, ResourcePanel, StatusBadge } from "../components/ui";
import { dataObject, list, metric, type PageProps, statusTone, valueOf } from "./pageUtils";

export function IntegrationPages(props: PageProps) {
  switch (props.view) {
    case "integrations":
      return <IntegrationsOverview {...props} />;
    case "mcp-connectors":
      return <McpConnectorsPage {...props} />;
    case "plugins-skills":
      return <PluginsSkillsPage {...props} />;
    case "gateway-webhooks":
      return <GatewayWebhooksPage {...props} />;
    default:
      return null;
  }
}

function IntegrationsOverview({ api, controlAvailable }: PageProps) {
  const mcp = useAsyncResource(() => api.mcpServers(), [api]);
  const connectors = useAsyncResource(() => api.connectorsSummary(), [api]);
  const plugins = useAsyncResource(() => api.plugins(), [api]);
  const gateway = useAsyncResource(() => api.gatewayStatus(), [api]);
  const readiness = useAsyncResource(() => api.healthDetailed(), [api]);
  const connectorData = dataObject(connectors.data, {});
  const gatewayData = dataObject(gateway.data, {});

  return (
    <PageShell
      title="Integrations 总览"
      description="统一汇总 MCP、Connectors、Plugins / Skills、Gateway 和 readiness，并把受控动作反馈收敛到二级页。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="集成管理" />}
      metrics={[
        metric("MCP Servers", list(mcp.data).length, "success"),
        metric("Connectors Ready", connectorData.ready ?? "-", "info"),
        metric("Plugins", list(plugins.data).length, "success"),
        metric("Gateway", gatewayData.mode || gatewayData.status || "unknown", statusTone(gatewayData.mode || gatewayData.status))
      ]}
    >
      <div className="grid-3">
        <LinkCard to="/mcp-connectors" title="MCP / Connectors" detail="Servers、tools、resources、prompts、OAuth 与连接器健康。" tone="info" meta="统一聚合入口" />
        <LinkCard to="/plugins-skills" title="Plugins / Skills" detail="Runtime skills、插件、自测动作与最近变更反馈。" tone="success" meta="受控变更" />
        <LinkCard to="/gateway-webhooks" title="Gateway" detail="平台状态、消息、目录、Webhook 与外部动作反馈。" tone="warning" meta="外部投递受控" />
        <LinkCard to="/readiness" title="Health & Readiness" detail="Agent、Hermes、capabilities 和 financial readiness。" meta="排障入口" />
        <LinkCard to="/settings" title="Settings" detail="Base URL、Token、模式与全局安全边界。" meta="Secret redaction" />
        <LinkCard to="/tools-approvals" title="Approvals" detail="Intent 与 approval 的统一审阅流。" tone="gated" meta="ActionIntent" />
      </div>

      <JsonPanel data={{ mcp: mcp.data, connectors: connectors.data, plugins: plugins.data, gateway: gateway.data, readiness: readiness.data }} title="Integrations evidence" />
    </PageShell>
  );
}

function McpConnectorsPage({ api, controlAvailable }: PageProps) {
  const servers = useAsyncResource(() => api.mcpServers(), [api]);
  const tools = useAsyncResource(() => api.mcpTools(), [api]);
  const resources = useAsyncResource(() => api.mcpResources(), [api]);
  const prompts = useAsyncResource(() => api.mcpPrompts(), [api]);
  const oauth = useAsyncResource(() => api.mcpOauth(), [api]);
  const connectors = useAsyncResource(() => api.connectors(), [api]);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const resourceRows = list(resources.data);
  const promptRows = list(prompts.data);
  const connectorRows = list(connectors.data);

  async function readFirstResource() {
    const first = resourceRows[0];
    if (!first) return;
    setActionResult(await api.mcpResourceRead({ server: first.server || first.server_name, uri: first.uri }));
  }

  async function getFirstPrompt() {
    const first = promptRows[0];
    if (!first) return;
    setActionResult(await api.mcpPromptGet({ server: first.server || first.server_name, name: first.name || first.prompt, arguments: {} }));
  }

  async function testFirstConnector() {
    const first = connectorRows[0];
    if (!first) return;
    const connectorId = String(first.id || "");
    const [connectorType, connectorName] = connectorId.includes(":")
      ? (connectorId.split(":", 2) as [string, string])
      : [String(first.type || first.connector_type || first.category || "mcp"), String(first.slug || first.name || connectorId)];
    if (!connectorType || !connectorName) return;
    setActionResult(await api.connectorTest(connectorType, connectorName));
  }

  return (
    <PageShell
      title="MCP 服务与连接器"
      description="按 servers、tools、resources、prompts、OAuth 和 connectors 分层编排，展示健康、最近错误和动作反馈。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="MCP discovery / OAuth / resource read" />}
      metrics={[
        metric("Servers", list(servers.data).length, "success"),
        metric("Tools", list(tools.data).length, "info"),
        metric("Resources", resourceRows.length, "info"),
        metric("Connectors", connectorRows.length, "warning")
      ]}
    >
      <div className="grid-2">
        <ResourcePanel title="MCP Servers" resource={servers}>
          {(data) => (
            <DataTable
              items={list(data)}
              columns={[
                { key: "name", header: "服务" },
                { key: "transport", header: "Transport" },
                { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> }
              ]}
            />
          )}
        </ResourcePanel>

        <ResourcePanel title="Connectors" resource={connectors}>
          {(data) => (
            <DataTable
              items={list(data)}
              columns={[
                { key: "name", header: "名称" },
                { key: "category", header: "分类" },
                { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> }
              ]}
            />
          )}
        </ResourcePanel>
      </div>

      <div className="grid-3">
        <Panel title="Tools">
          <DataTable items={list(tools.data)} columns={[{ key: "name", header: "工具" }, { key: "server", header: "服务" }, { key: "status", header: "状态" }]} />
        </Panel>
        <Panel title="Resources">
          <DataTable items={resourceRows} columns={[{ key: "uri", header: "URI" }, { key: "server", header: "服务" }, { key: "status", header: "状态" }]} />
        </Panel>
        <Panel title="Prompts / OAuth">
          <DataTable items={[...promptRows, ...list(oauth.data)]} columns={[{ key: "name", header: "名称" }, { key: "server", header: "服务" }, { key: "status", header: "状态" }]} />
        </Panel>
      </div>

      <Panel title="MCP / Connector Actions">
        <div className="page-actions">
          <Button data-testid="mcp-read-first-resource" disabled={!controlAvailable || !resourceRows.length} onClick={() => void readFirstResource()}>
            Read first resource
          </Button>
          <Button data-testid="mcp-get-first-prompt" disabled={!controlAvailable || !promptRows.length} onClick={() => void getFirstPrompt()}>
            Get first prompt
          </Button>
          <Button data-testid="connector-test-first" disabled={!controlAvailable || !connectorRows.length} onClick={() => void testFirstConnector()}>
            Test first connector
          </Button>
        </div>
        {actionResult ? <JsonPanel data={actionResult} title="MCP action result" /> : null}
      </Panel>

      <JsonPanel data={{ servers: servers.data, tools: tools.data, resources: resources.data, prompts: prompts.data, oauth: oauth.data, connectors: connectors.data }} title="MCP / Connector evidence" />
    </PageShell>
  );
}

function PluginsSkillsPage({ api, controlAvailable }: PageProps) {
  const skills = useAsyncResource(() => api.skills(), [api]);
  const plugins = useAsyncResource(() => api.plugins(), [api]);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "create-skill" | "delete-skill" | "toggle-plugin">(null);
  const sampleSkillName = useMemo(() => `desktop-v1-smoke-skill-${Date.now().toString(36)}`, []);
  const skillData = dataObject(skills.data, {});
  const installedSkills = Array.isArray(skillData.installed) ? skillData.installed.map((name) => ({ name })) : list(skills.data);
  const pluginRows = list(plugins.data);

  async function createSampleSkill() {
    setActionResult(
      await api.skillCreate({
        name: sampleSkillName,
        description: "Created by AIASK Desktop V1 closed-loop smoke.",
        content: "# Desktop V1 Smoke Skill\n\nThis skill is created through the gated Agent HTTP API."
      })
    );
    setPreviewAction(null);
    await skills.reload();
  }

  async function deleteSampleSkill() {
    setActionResult(await api.skillDelete(sampleSkillName));
    setPreviewAction(null);
    await skills.reload();
  }

  async function toggleFirstPlugin() {
    const first = pluginRows[0];
    const name = String(first?.name || first?.id || "");
    if (!name) return;
    setActionResult(await api.pluginToggle(name, !Boolean(first.enabled)));
    setPreviewAction(null);
    await plugins.reload();
  }

  async function testFirstPlugin() {
    const first = pluginRows[0];
    const name = String(first?.name || first?.id || "");
    if (!name) return;
    setActionResult(await api.pluginToolTest(name, "__manifest__", {}));
  }

  return (
    <PageShell
      title="Plugins / Skills 管理"
      description="统一展示 runtime skills、插件、自测能力和最近动作反馈；所有变更继续受 control 门禁约束。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="插件 / 技能变更" />}
      metrics={[
        metric("Skills", installedSkills.length, "success"),
        metric("Plugins", pluginRows.length, "info"),
        metric("变更动作", controlAvailable ? "可发起" : "门禁", controlAvailable ? "success" : "gated"),
        metric("Secrets", "Redacted", "success")
      ]}
    >
      <div className="grid-2">
        <Panel title="Skills">
          <DataTable
            items={installedSkills}
            columns={[
              { key: "name", header: "技能" },
              {
                key: "status",
                header: "状态",
                render: (item) => <StatusBadge tone={statusTone(item.status || "installed")}>{valueOf(item, ["status"], "installed")}</StatusBadge>
              }
            ]}
          />
        </Panel>

        <Panel title="Plugins">
          <DataTable
            items={pluginRows}
            columns={[
              { key: "name", header: "插件" },
              {
                key: "enabled",
                header: "启用",
                render: (item) => <StatusBadge tone={item.enabled ? "success" : "warning"}>{item.enabled ? "enabled" : "disabled"}</StatusBadge>
              },
              { key: "tools", header: "工具" },
              { key: "commands", header: "命令" }
            ]}
          />
        </Panel>
      </div>

      <Panel title="Skill / Plugin Actions">
        <div className="page-actions">
          <Button data-testid="skill-create-sample" disabled={!controlAvailable} onClick={() => setPreviewAction("create-skill")}>
            Create sample skill
          </Button>
          <Button data-testid="skill-delete-sample" disabled={!controlAvailable} onClick={() => setPreviewAction("delete-skill")}>
            Delete sample skill
          </Button>
          <Button data-testid="plugin-toggle-first" disabled={!controlAvailable || !pluginRows.length} onClick={() => setPreviewAction("toggle-plugin")}>
            Toggle first plugin
          </Button>
          <Button data-testid="plugin-self-test-first" disabled={!controlAvailable || !pluginRows.length} onClick={() => void testFirstPlugin()}>
            Self-test first plugin
          </Button>
        </div>

        {previewAction ? (
          <DryRunPreview
            title="Plugin / Skill 变更预览"
            changes={[
              { label: "动作", after: previewAction },
              { label: "目标", after: previewAction.includes("skill") ? sampleSkillName : String(pluginRows[0]?.name || pluginRows[0]?.id || "-") },
              { label: "模式", after: "受控变更" }
            ]}
            onCancel={() => setPreviewAction(null)}
            onConfirm={() => {
              if (previewAction === "create-skill") {
                void createSampleSkill();
                return;
              }
              if (previewAction === "delete-skill") {
                void deleteSampleSkill();
                return;
              }
              void toggleFirstPlugin();
            }}
          />
        ) : null}

        {actionResult ? <JsonPanel data={actionResult} title="Skill / plugin action result" /> : null}
      </Panel>

      <JsonPanel data={{ skills: skills.data, plugins: plugins.data }} title="Plugins / skills evidence" />
    </PageShell>
  );
}

function GatewayWebhooksPage({ api, controlAvailable }: PageProps) {
  const status = useAsyncResource(() => api.gatewayStatus(), [api]);
  const daemon = useAsyncResource(() => api.gatewayDaemon(), [api]);
  const platforms = useAsyncResource(() => api.gatewayPlatforms(), [api]);
  const messages = useAsyncResource(() => api.gatewayMessages(), [api]);
  const directory = useAsyncResource(() => api.gatewayDirectory(), [api]);
  const webhooks = useAsyncResource(() => api.webhooks(), [api]);
  const [draft, setDraft] = useState("雷达摘要预览：请确认后再投递。");
  const [sendResult, setSendResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "send" | "refresh-directory" | "retry" | "start" | "stop">(null);
  const statusData = dataObject(status.data, {});
  const daemonData = dataObject(daemon.data, {});
  const platformRows = list(platforms.data);
  const messageRows = list(messages.data);

  async function createDeliveryIntent() {
    setSendResult(
      await api.gatewaySend({
        platform: "local",
        target: "Research Desk",
        message: draft,
        deliver_mode: "intent_preview"
      })
    );
    setPreviewAction(null);
    await messages.reload();
  }

  function firstPlatform(): string {
    const first = platformRows[0];
    return String(first?.platform || first?.name || first?.id || "local");
  }

  async function refreshDirectory() {
    setSendResult(await api.gatewayDirectoryRefresh());
    setPreviewAction(null);
    await directory.reload();
  }

  async function retryFirstMessage() {
    const first = messageRows[0];
    const messageId = String(first?.id || first?.message_id || "");
    if (!messageId) return;
    setSendResult(await api.gatewayRetry(messageId));
    setPreviewAction(null);
    await messages.reload();
  }

  async function platformAction(action: "health" | "start" | "stop") {
    const platform = firstPlatform();
    const result =
      action === "health"
        ? await api.gatewayPlatformHealth(platform)
        : action === "start"
          ? await api.gatewayPlatformStart(platform)
          : await api.gatewayPlatformStop(platform);
    setSendResult(result);
    setPreviewAction(null);
    await platforms.reload();
  }

  return (
    <PageShell
      title="Gateway / Webhooks"
      description="统一管理跨平台投递、消息目录、daemon、平台健康和 webhook；所有外部动作都明确标注为受控操作。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="外部投递 / 平台控制" />}
      metrics={[
        metric("Gateway", statusData.mode || statusData.status || "unknown", statusTone(statusData.mode || statusData.status)),
        metric("Daemon", daemonData.running ? "running" : "stopped", daemonData.running ? "success" : "warning"),
        metric("Platforms", platformRows.length, "info"),
        metric("Webhooks", list(webhooks.data).length, "info")
      ]}
    >
      <div className="grid-2">
        <Panel title="投递预览">
          <label className="field">
            <span>消息内容</span>
            <textarea data-testid="gateway-message" value={draft} onChange={(event) => setDraft(event.target.value)} />
            <small>按钮只会创建受控投递请求；缺少 control token 时保持禁用。</small>
          </label>
          <Button data-testid="gateway-send-local" icon={<Send size={16} />} disabled={!controlAvailable} onClick={() => setPreviewAction("send")}>
            创建投递请求
          </Button>
        </Panel>

        <Panel title="平台状态">
          <DataTable
            items={platformRows}
            columns={[
              { key: "platform", header: "平台" },
              { key: "configured", header: "已配置" },
              { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status)}>{valueOf(item, ["status"])}</StatusBadge> }
            ]}
          />
        </Panel>
      </div>

      <div className="grid-3">
        <Panel title="消息">
          <DataTable items={messageRows} columns={[{ key: "platform", header: "平台" }, { key: "direction", header: "方向" }, { key: "status", header: "状态" }]} />
        </Panel>
        <Panel title="目录">
          <DataTable items={list(directory.data)} columns={[{ key: "platform", header: "平台" }, { key: "kind", header: "类型" }, { key: "name", header: "名称" }]} />
        </Panel>
        <Panel title="Webhooks">
          <DataTable items={list(webhooks.data)} columns={[{ key: "platform", header: "平台" }, { key: "status", header: "状态" }, { key: "verified", header: "验签" }]} />
        </Panel>
      </div>

      <Panel title="Gateway Actions">
        <div className="page-actions">
          <Button data-testid="gateway-refresh-directory" disabled={!controlAvailable} onClick={() => setPreviewAction("refresh-directory")}>
            Refresh directory
          </Button>
          <Button data-testid="gateway-retry-first" disabled={!controlAvailable || !messageRows.length} onClick={() => setPreviewAction("retry")}>
            Retry first message
          </Button>
          <Button data-testid="gateway-platform-health" disabled={!controlAvailable || !platformRows.length} onClick={() => void platformAction("health")}>
            Platform health
          </Button>
          <Button data-testid="gateway-platform-start" disabled={!controlAvailable || !platformRows.length} onClick={() => setPreviewAction("start")}>
            Start platform
          </Button>
          <Button data-testid="gateway-platform-stop" disabled={!controlAvailable || !platformRows.length} onClick={() => setPreviewAction("stop")}>
            Stop platform
          </Button>
        </div>

        {previewAction ? (
          <DryRunPreview
            title="Gateway 动作预览"
            changes={[
              { label: "动作", after: previewAction },
              { label: "平台", after: firstPlatform() },
              { label: "说明", after: previewAction === "send" ? draft : "通过 Agent route 发起受控动作" }
            ]}
            onCancel={() => setPreviewAction(null)}
            onConfirm={() => {
              if (previewAction === "send") {
                void createDeliveryIntent();
                return;
              }
              if (previewAction === "refresh-directory") {
                void refreshDirectory();
                return;
              }
              if (previewAction === "retry") {
                void retryFirstMessage();
                return;
              }
              void platformAction(previewAction === "start" ? "start" : "stop");
            }}
          />
        ) : null}
      </Panel>

      <JsonPanel data={{ status: status.data, daemon: daemon.data, send_result: sendResult }} title="Gateway evidence" />
      <Panel title="成熟方案约束" action={<Radio size={18} />}>
        <p>Webhook 验签、目录刷新、daemon start/stop 和外部投递全部由 Agent route 控制，前端只展示状态和受控入口。</p>
      </Panel>
    </PageShell>
  );
}
