import { Radio, Send, ShieldCheck } from "lucide-react";
import { useState } from "react";

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
      title="集成能力总览"
      description="统一展示 MCP、连接器、插件/技能、Gateway、Webhooks 和 readiness；所有变更动作受 control token 或后端审批约束。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="集成管理" />}
      metrics={[
        metric("MCP Servers", list(mcp.data).length, "success"),
        metric("Connectors Ready", connectorData.ready ?? "-", "info"),
        metric("Plugins", list(plugins.data).length, "success"),
        metric("Gateway", gatewayData.mode || gatewayData.status || "unknown", statusTone(gatewayData.mode || gatewayData.status))
      ]}
    >
      <div className="grid-3">
        <LinkCard to="/mcp-connectors" title="MCP 与连接器" detail="Servers、tools、resources、prompts、OAuth 和统一连接器。" tone="info" meta="MCP 官方分层" />
        <LinkCard to="/plugins-skills" title="插件与技能" detail="Runtime skills、插件、命令和工具自测。" tone="success" meta="变更受控" />
        <LinkCard to="/gateway-webhooks" title="Gateway 与 Webhooks" detail="平台状态、消息、目录、daemon 和入站 webhook。" tone="warning" meta="外部投递需意图" />
        <LinkCard to="/readiness" title="健康诊断" detail="Agent、Hermes、capabilities、financial readiness。" meta="排障入口" />
        <LinkCard to="/settings" title="设置与安全" detail="API base、token、模式和全局门禁。" meta="Secret redaction" />
        <LinkCard to="/tools-approvals" title="审批队列" detail="Intent 和 approvals 的统一跟踪。" tone="gated" meta="ActionIntent" />
      </div>
      <JsonPanel data={{ mcp: mcp.data, connectors: connectors.data, plugins: plugins.data, gateway: gateway.data, readiness: readiness.data }} title="集成证据" />
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
    setActionResult(await api.connectorTest(String(first.type || first.connector_type || first.category || "mcp"), String(first.name || first.id || "")));
  }

  return (
    <PageShell
      title="MCP 服务与统一连接器"
      description="按 servers/tools/resources/prompts/OAuth 分层管理 MCP；连接器展示配置、连通、缺失环境和测试状态。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="MCP discovery/OAuth/resource read" />}
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
          <Button disabled={!controlAvailable || !resourceRows.length} onClick={() => void readFirstResource()}>Read first resource</Button>
          <Button disabled={!controlAvailable || !promptRows.length} onClick={() => void getFirstPrompt()}>Get first prompt</Button>
          <Button disabled={!controlAvailable || !connectorRows.length} onClick={() => void testFirstConnector()}>Test first connector</Button>
        </div>
        {actionResult ? <JsonPanel data={actionResult} title="MCP action result" /> : null}
      </Panel>
      <JsonPanel data={{ servers: servers.data, tools: tools.data, resources: resources.data, prompts: prompts.data, oauth: oauth.data, connectors: connectors.data }} title="MCP/Connector 证据" />
    </PageShell>
  );
}

function PluginsSkillsPage({ api, controlAvailable }: PageProps) {
  const skills = useAsyncResource(() => api.skills(), [api]);
  const plugins = useAsyncResource(() => api.plugins(), [api]);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const skillData = dataObject(skills.data, {});
  const installedSkills = Array.isArray(skillData.installed) ? skillData.installed.map((name) => ({ name })) : list(skills.data);
  const pluginRows = list(plugins.data);

  async function createSampleSkill() {
    setActionResult(
      await api.skillCreate({
        name: "desktop-v1-smoke-skill",
        description: "Created by AIASK Desktop V1 closed-loop smoke.",
        content: "# Desktop V1 Smoke Skill\n\nThis skill is created through the gated Agent HTTP API."
      })
    );
    await skills.reload();
  }

  async function deleteSampleSkill() {
    setActionResult(await api.skillDelete("desktop-v1-smoke-skill"));
    await skills.reload();
  }

  async function toggleFirstPlugin() {
    const first = pluginRows[0];
    const name = String(first?.name || first?.id || "");
    if (!name) return;
    setActionResult(await api.pluginToggle(name, !Boolean(first.enabled)));
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
      title="Skills 与 Plugins 管理"
      description="展示 runtime skills、插件、命令与工具自测状态；安装、启停、删除等变更走 full/control 门禁。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="插件/技能变更" />}
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
              { key: "status", header: "状态", render: (item) => <StatusBadge tone={statusTone(item.status || "installed")}>{valueOf(item, ["status"], "installed")}</StatusBadge> }
            ]}
          />
        </Panel>
        <Panel title="Plugins">
          <DataTable
            items={pluginRows}
            columns={[
              { key: "name", header: "插件" },
              { key: "enabled", header: "启用", render: (item) => <StatusBadge tone={item.enabled ? "success" : "warning"}>{item.enabled ? "enabled" : "disabled"}</StatusBadge> },
              { key: "tools", header: "工具" },
              { key: "commands", header: "命令" }
            ]}
          />
        </Panel>
      </div>
      <Panel title="Skill / Plugin Actions">
        <div className="page-actions">
          <Button disabled={!controlAvailable} onClick={() => void createSampleSkill()}>Create sample skill</Button>
          <Button disabled={!controlAvailable} onClick={() => void deleteSampleSkill()}>Delete sample skill</Button>
          <Button disabled={!controlAvailable || !pluginRows.length} onClick={() => void toggleFirstPlugin()}>Toggle first plugin</Button>
          <Button disabled={!controlAvailable || !pluginRows.length} onClick={() => void testFirstPlugin()}>Self-test first plugin</Button>
        </div>
        {actionResult ? <JsonPanel data={actionResult} title="Skill/plugin action result" /> : null}
      </Panel>
      <JsonPanel data={{ skills: skills.data, plugins: plugins.data }} title="插件技能证据" />
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
    await messages.reload();
  }

  function firstPlatform(): string {
    const first = platformRows[0];
    return String(first?.platform || first?.name || first?.id || "local");
  }

  async function refreshDirectory() {
    setSendResult(await api.gatewayDirectoryRefresh());
    await directory.reload();
  }

  async function retryFirstMessage() {
    const first = messageRows[0];
    const messageId = String(first?.id || first?.message_id || "");
    if (!messageId) return;
    setSendResult(await api.gatewayRetry(messageId));
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
    await platforms.reload();
  }

  return (
    <PageShell
      title="Gateway 与 Webhooks"
      description="管理跨平台投递、消息目录、daemon、平台健康与 webhook；外部投递必须清楚标注预览、意图或审批。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="外部投递/平台控制" />}
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
            <textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
            <small>按钮会创建受控投递请求；缺 control token 时禁用。</small>
          </label>
          <Button icon={<Send size={16} />} disabled={!controlAvailable} onClick={() => void createDeliveryIntent()}>
            创建投递请求
          </Button>
        </Panel>
        <Panel title="平台状态">
          <DataTable
            items={platformRows}
            columns={[
              { key: "platform", header: "平台" },
              { key: "configured", header: "配置" },
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
          <Button disabled={!controlAvailable} onClick={() => void refreshDirectory()}>Refresh directory</Button>
          <Button disabled={!controlAvailable || !messageRows.length} onClick={() => void retryFirstMessage()}>Retry first message</Button>
          <Button disabled={!controlAvailable || !platformRows.length} onClick={() => void platformAction("health")}>Platform health</Button>
          <Button disabled={!controlAvailable || !platformRows.length} onClick={() => void platformAction("start")}>Start platform</Button>
          <Button disabled={!controlAvailable || !platformRows.length} onClick={() => void platformAction("stop")}>Stop platform</Button>
        </div>
      </Panel>
      <JsonPanel data={{ status: status.data, daemon: daemon.data, send_result: sendResult }} title="Gateway 证据" />
      <Panel title="成熟方案约束" action={<Radio size={18} />}>
        <p>Webhook 入站验签、平台目录刷新、daemon start/stop 和直接投递都由 Agent route/adapter 控制；前端只展示状态和发起受控请求。</p>
      </Panel>
    </PageShell>
  );
}
