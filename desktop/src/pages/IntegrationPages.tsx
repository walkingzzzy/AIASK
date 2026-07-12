import { Radio } from "lucide-react";
import { useMemo, useState } from "react";

import { DryRunPreview } from "../components/IntentComponents";
import { McpAddButton } from "../components/McpAddDialog";
import { SkillAddButton } from "../components/SkillAddDialog";
import { StatusLight, inferStatusFromData } from "../components/StatusLight";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { Button, DataTable, GatedNotice, JsonPanel, LinkCard, PageShell, Panel, ResourcePanel, StatusBadge } from "../components/ui";
import type { UnknownRecord } from "../types";
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

function gatedListPayload(area: string): UnknownRecord {
  return {
    object: "list",
    data: [],
    gated: true,
    status: "control_required",
    error_code: "control_token_required",
    message: `${area} requires a control token`
  };
}

function gatedStatusPayload(area: string): UnknownRecord {
  return {
    object: "gated.status",
    gated: true,
    status: "control_required",
    error_code: "control_token_required",
    message: `${area} requires a control token`
  };
}

function useControlGatedResource<T>(controlAvailable: boolean, loader: () => Promise<T>, fallback: T, deps: unknown[] = []) {
  return useAsyncResource(() => (controlAvailable ? loader() : Promise.resolve(fallback)), [controlAvailable, ...deps]);
}

function IntegrationsOverview({ api, controlAvailable }: PageProps) {
  const mcp = useAsyncResource(() => api.mcpServers(), [api]);
  const connectors = useControlGatedResource(controlAvailable, () => api.connectorsSummary(), gatedStatusPayload("connectors summary"), [api]);
  const plugins = useControlGatedResource(controlAvailable, () => api.plugins(), gatedListPayload("plugins"), [api]);
  const gateway = useControlGatedResource(controlAvailable, () => api.gatewayStatus(), gatedStatusPayload("gateway status"), [api]);
  const readiness = useAsyncResource(() => api.healthDetailed(), [api]);
  const connectorData = dataObject(connectors.data, {});
  const gatewayData = dataObject(gateway.data, {});

  return (
    <PageShell
      title="集成连接"
      description="集中查看 MCP、连接器、插件、技能、消息网关和系统可用状态。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="集成管理" />}
      metrics={[
        metric("MCP 服务", list(mcp.data).length, "success"),
        metric("连接器可用", connectorData.ready ?? "-", "info"),
        metric("插件", list(plugins.data).length, "success"),
        metric("消息网关", gatewayData.mode || gatewayData.status || "未知", statusTone(gatewayData.mode || gatewayData.status))
      ]}
    >
      <div className="grid-3">
        <LinkCard to="/mcp-connectors" title="MCP 连接" detail="查看服务、工具、资源、提示词、授权和连接器健康状态。" tone="info" meta="核心入口" />
        <LinkCard to="/plugins-skills" title="插件与技能" detail="管理运行时技能、插件、自检和受控变更。" tone="success" meta="核心入口" />
        <LinkCard to="/gateway-webhooks" title="消息网关" detail="查看平台状态、消息目录、后台服务、配对和 Webhook 反馈。" tone="warning" meta="扩展入口" />
        <LinkCard to="/readiness" title="健康与就绪" detail="检查 Agent、Hermes 和金融系统可用状态。" meta="诊断" />
        <LinkCard to="/settings" title="设置" detail="管理服务地址、权限令牌、模式和全局边界。" meta="敏感信息隐藏" />
        <LinkCard to="/tools-approvals" title="审批" detail="复核受控操作和审批队列。" tone="gated" meta="受控操作" />
      </div>

      <JsonPanel data={{ mcp: mcp.data, connectors: connectors.data, plugins: plugins.data, gateway: gateway.data, readiness: readiness.data }} title="集成证据" />
    </PageShell>
  );
}

function McpConnectorsPage({ api, controlAvailable }: PageProps) {
  const servers = useAsyncResource(() => api.mcpServers(), [api]);
  const tools = useControlGatedResource(controlAvailable, () => api.mcpTools(), gatedListPayload("MCP tools"), [api]);
  const resources = useControlGatedResource(controlAvailable, () => api.mcpResources(), gatedListPayload("MCP resources"), [api]);
  const prompts = useControlGatedResource(controlAvailable, () => api.mcpPrompts(), gatedListPayload("MCP prompts"), [api]);
  const oauth = useControlGatedResource(controlAvailable, () => api.mcpOauth(), gatedListPayload("MCP OAuth status"), [api]);
  const connectors = useControlGatedResource(controlAvailable, () => api.connectors(), gatedListPayload("connectors"), [api]);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const toolRows = list(tools.data);
  const resourceRows = list(resources.data);
  const promptRows = list(prompts.data);
  const promptOauthRows = [...promptRows, ...list(oauth.data)];
  const connectorRows = list(connectors.data);

  function renderServerActions(item: UnknownRecord) {
    return (
      <>
        <Button onClick={() => void toggleServer(String(item.id || ""), !Boolean(item.enabled))} disabled={!controlAvailable || !item.id}>
          {item.enabled ? "停用" : "启用"}
        </Button>
        <Button tone="danger" onClick={() => void deleteServer(String(item.id || ""), String(item.name || item.id || ""))} disabled={!controlAvailable || !item.id}>
          删除
        </Button>
      </>
    );
  }

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

  async function handleAddMcp(data: { name: string; command: string; args?: string[]; env?: Record<string, string> }) {
    await api.mcpServerAdd(data);
    await servers.reload();
    setActionResult({ success: true, message: "MCP 服务已添加" });
  }

  async function toggleServer(serverId: string, enabled: boolean) {
    await api.mcpServerUpdate(serverId, { enabled });
    await servers.reload();
    setActionResult({ success: true, message: enabled ? "MCP 服务已启用" : "MCP 服务已停用" });
  }

  async function deleteServer(serverId: string, name: string) {
    if (!window.confirm(`确认删除 MCP 服务“${name}”？`)) return;
    await api.mcpServerDelete(serverId);
    await servers.reload();
    setActionResult({ success: true, message: "MCP 服务已删除" });
  }

  return (
    <PageShell
      title="MCP 连接"
      description="管理 MCP 服务、资源、提示词和连接器健康状态。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="MCP 管理" />}
      actions={controlAvailable ? <McpAddButton onAdd={handleAddMcp} /> : undefined}
      metrics={[
        metric("服务", list(servers.data).length, "success"),
        metric("工具", toolRows.length, "info"),
        metric("资源", resourceRows.length, "info"),
        metric("连接器", connectorRows.length, "warning")
      ]}
    >
      <div className="grid-2">
        <ResourcePanel title="MCP 服务" resource={servers}>
          {(data) => (
            <DataTable
              items={list(data)}
              columns={[
                { key: "name", header: "名称" },
                { key: "transport", header: "传输方式" },
                { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> },
                {
                  key: "id",
                  header: "操作",
                  render: (item) => <div style={{ display: "flex", gap: "0.5rem" }}>{renderServerActions(item)}</div>
                }
              ]}
              mobileCard={(item) => ({
                title: valueOf(item, ["name", "id"], "未命名服务"),
                subtitle: `传输方式：${valueOf(item, ["transport", "command"], "未配置")}`,
                details: [
                  { label: "状态", value: <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> },
                  { label: "标识", value: valueOf(item, ["id", "server"], "-") }
                ],
                actions: renderServerActions(item)
              })}
            />
          )}
        </ResourcePanel>

        <ResourcePanel title="连接器" resource={connectors}>
          {(data) => (
            <DataTable
              items={list(data)}
              columns={[
                { key: "name", header: "名称" },
                { key: "category", header: "类别" },
                { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }
              ]}
              mobileCard={(item) => ({
                title: valueOf(item, ["name", "id"], "未命名连接器"),
                subtitle: `类别：${valueOf(item, ["category", "type", "connector_type"], "未分类")}`,
                details: [
                  { label: "状态", value: <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> },
                  { label: "服务", value: valueOf(item, ["server", "server_name", "slug"], "-") }
                ]
              })}
            />
          )}
        </ResourcePanel>
      </div>

      <div className="grid-3">
        <Panel title="工具">
          <DataTable
            items={toolRows}
            columns={[{ key: "name", header: "工具" }, { key: "server", header: "服务" }, { key: "status", header: "状态" }]}
            mobileCard={(item) => ({
              title: valueOf(item, ["name", "tool"], "未命名工具"),
              subtitle: `服务：${valueOf(item, ["server", "server_name"], "-")}`,
              details: [{ label: "状态", value: valueOf(item, ["status"], "可用性未知") }]
            })}
          />
        </Panel>
        <Panel title="资源">
          <DataTable
            items={resourceRows}
            columns={[{ key: "uri", header: "URI" }, { key: "server", header: "服务" }, { key: "status", header: "状态" }]}
            mobileCard={(item) => ({
              title: valueOf(item, ["name", "uri"], "未命名资源"),
              subtitle: valueOf(item, ["uri"], "未提供 URI"),
              details: [
                { label: "服务", value: valueOf(item, ["server", "server_name"], "-") },
                { label: "状态", value: valueOf(item, ["status"], "可用性未知") }
              ]
            })}
          />
        </Panel>
        <Panel title="提示词与授权">
          <DataTable
            items={promptOauthRows}
            columns={[{ key: "name", header: "名称" }, { key: "server", header: "服务" }, { key: "status", header: "状态" }]}
            mobileCard={(item) => ({
              title: valueOf(item, ["name", "prompt", "server"], "未命名项目"),
              subtitle: `服务：${valueOf(item, ["server", "server_name"], "-")}`,
              details: [{ label: "状态", value: valueOf(item, ["status", "oauth_status"], "可用性未知") }]
            })}
          />
        </Panel>
      </div>

      <Panel title="MCP 操作">
        <div className="page-actions">
          <Button data-testid="mcp-read-first-resource" disabled={!controlAvailable || !resourceRows.length} onClick={() => void readFirstResource()}>
            读取第一个资源
          </Button>
          <Button data-testid="mcp-get-first-prompt" disabled={!controlAvailable || !promptRows.length} onClick={() => void getFirstPrompt()}>
            获取第一个提示词
          </Button>
          <Button data-testid="connector-test-first" disabled={!controlAvailable || !connectorRows.length} onClick={() => void testFirstConnector()}>
            测试第一个连接器
          </Button>
        </div>
        {actionResult ? <JsonPanel data={actionResult} title="MCP 操作结果" /> : null}
      </Panel>
    </PageShell>
  );
}

function PluginsSkillsPage({ api, controlAvailable }: PageProps) {
  const skills = useControlGatedResource(controlAvailable, () => api.skills(), gatedListPayload("skills"), [api]);
  const plugins = useControlGatedResource(controlAvailable, () => api.plugins(), gatedListPayload("plugins"), [api]);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "create-skill" | "delete-skill" | "toggle-plugin">(null);
  const sampleSkillName = useMemo(() => `desktop-v1-smoke-skill-${Date.now().toString(36)}`, []);
  const installedSkills = list(skills.data);
  const pluginRows = list(plugins.data);
  const previewActionLabel: Record<NonNullable<typeof previewAction>, string> = {
    "create-skill": "创建示例技能",
    "delete-skill": "删除示例技能",
    "toggle-plugin": "切换第一个插件"
  };

  async function createSampleSkill() {
    setActionResult(
      await api.skillCreate({
        name: sampleSkillName,
        type: "local",
        path: `C:/skills/${sampleSkillName}/SKILL.md`,
        config: { source: "desktop-smoke" }
      })
    );
    setPreviewAction(null);
    await skills.reload();
  }

  async function deleteSampleSkillByName(name: string) {
    const target = installedSkills.find((item) => String(item.name || "") === name);
    if (!target?.id) {
      setActionResult({ success: false, error: `未找到技能：${name}` });
      return;
    }
    setActionResult(await api.skillDelete(String(target.id)));
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

  async function handleAddSkill(data: { name: string; type: string; path: string; config?: Record<string, unknown> }) {
    await api.skillCreate(data);
    await skills.reload();
    setActionResult({ success: true, message: "技能已添加" });
  }

  async function toggleSkill(skillId: string, enabled: boolean) {
    await api.skillUpdate(skillId, { enabled });
    await skills.reload();
    setActionResult({ success: true, message: enabled ? "技能已启用" : "技能已停用" });
  }

  async function deleteSkill(skillId: string, name: string) {
    if (!window.confirm(`确认删除技能“${name}”？`)) return;
    await api.skillDelete(skillId);
    await skills.reload();
    setActionResult({ success: true, message: "技能已删除" });
  }

  return (
    <PageShell
      title="插件与技能"
      description="管理运行时技能、插件、自检和受控变更。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="插件和技能变更" />}
      actions={controlAvailable ? <SkillAddButton onAdd={handleAddSkill} /> : undefined}
      metrics={[
        metric("技能", installedSkills.length, "success"),
        metric("插件", pluginRows.length, "info"),
        metric("变更操作", controlAvailable ? "允许" : "受控", controlAvailable ? "success" : "gated"),
        metric("敏感信息", "已隐藏", "success")
      ]}
    >
      <div className="grid-2">
        <Panel title="技能">
          <DataTable
            items={installedSkills}
            columns={[
              { key: "name", header: "名称" },
              { key: "type", header: "类型" },
              { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item.status || item.enabled)} label={valueOf(item, ["status"], item.enabled ? "已启用" : "已停用")} /> },
              {
                key: "id",
                header: "操作",
                render: (item) => (
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <Button onClick={() => void toggleSkill(String(item.id || ""), !Boolean(item.enabled))} disabled={!controlAvailable || !item.id}>
                      {item.enabled ? "停用" : "启用"}
                    </Button>
                    <Button tone="danger" onClick={() => void deleteSkill(String(item.id || ""), String(item.name || item.id || ""))} disabled={!controlAvailable || !item.id}>
                      删除
                    </Button>
                  </div>
                )
              }
            ]}
          />
        </Panel>

        <Panel title="插件">
          <DataTable
            items={pluginRows}
            columns={[
              { key: "name", header: "插件" },
              { key: "enabled", header: "启用状态", render: (item) => <StatusLight status={item.enabled ? "connected" : "disconnected"} label={item.enabled ? "已启用" : "已停用"} /> },
              { key: "tools", header: "工具" },
              { key: "commands", header: "命令" }
            ]}
          />
        </Panel>
      </div>

      <Panel title="技能与插件操作">
        <div className="page-actions">
          <Button data-testid="skill-create-sample" disabled={!controlAvailable} onClick={() => setPreviewAction("create-skill")}>
            创建示例技能
          </Button>
          <Button data-testid="skill-delete-sample" disabled={!controlAvailable} onClick={() => setPreviewAction("delete-skill")}>
            删除示例技能
          </Button>
          <Button data-testid="plugin-toggle-first" disabled={!controlAvailable || !pluginRows.length} onClick={() => setPreviewAction("toggle-plugin")}>
            切换第一个插件
          </Button>
          <Button data-testid="plugin-self-test-first" disabled={!controlAvailable || !pluginRows.length} onClick={() => void testFirstPlugin()}>
            自检第一个插件
          </Button>
        </div>

        {previewAction ? (
          <DryRunPreview
            title="插件与技能操作预览"
            changes={[
              { label: "操作", after: previewActionLabel[previewAction] },
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
                void deleteSampleSkillByName(sampleSkillName);
                return;
              }
              void toggleFirstPlugin();
            }}
          />
        ) : null}

        {actionResult ? <JsonPanel data={actionResult} title="技能与插件操作结果" /> : null}
      </Panel>
    </PageShell>
  );
}

function GatewayWebhooksPage({ api, controlAvailable, settings }: PageProps) {
  const [gatewayForm, setGatewayForm] = useState({
    platform: "local",
    user_id: settings?.userId || "local-user",
    session_id: "gateway-session",
    target: "研究工作台"
  });
  const status = useControlGatedResource(controlAvailable, () => api.gatewayStatus(), gatedStatusPayload("gateway status"), [api]);
  const daemon = useControlGatedResource(controlAvailable, () => api.gatewayDaemon(), gatedStatusPayload("gateway daemon"), [api]);
  const platforms = useControlGatedResource(controlAvailable, () => api.gatewayPlatforms(), gatedListPayload("gateway platforms"), [api]);
  const pairing = useControlGatedResource(
    controlAvailable,
    () =>
      api.gatewayPairing({
        platform: gatewayForm.platform,
        user_id: gatewayForm.user_id,
        session_id: gatewayForm.session_id
      }),
    gatedStatusPayload("gateway pairing"),
    [api, gatewayForm.platform, gatewayForm.user_id, gatewayForm.session_id]
  );
  const messages = useControlGatedResource(controlAvailable, () => api.gatewayMessages(), gatedListPayload("gateway messages"), [api]);
  const directory = useControlGatedResource(controlAvailable, () => api.gatewayDirectory(), gatedListPayload("gateway directory"), [api]);
  const webhooks = useControlGatedResource(controlAvailable, () => api.webhooks(), gatedListPayload("webhooks"), [api]);
  const [draft, setDraft] = useState("股票雷达摘要预览：确认后再投递。");
  const [sendResult, setSendResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "send" | "refresh-directory" | "retry" | "start" | "stop" | "pair-create">(null);
  const [pairingResult, setPairingResult] = useState<unknown>(null);
  const statusData = dataObject(status.data, {});
  const daemonData = dataObject(daemon.data, {});
  const pairingData = dataObject(pairing.data, {});
  const platformRows = list(platforms.data);
  const messageRows = list(messages.data);
  const gatewayActionLabel: Record<NonNullable<typeof previewAction>, string> = {
    send: "创建投递审批",
    "refresh-directory": "刷新目录",
    retry: "重试第一条消息",
    start: "启动平台",
    stop: "停止平台",
    "pair-create": "创建配对"
  };

  async function createDeliveryIntent() {
    setSendResult(
      await api.gatewaySend({
        platform: gatewayForm.platform,
        target: gatewayForm.target,
        user_id: gatewayForm.user_id,
        session_id: gatewayForm.session_id,
        message: draft,
        deliver_mode: "intent_preview"
      })
    );
    setPreviewAction(null);
    await messages.reload();
  }

  function firstPlatform(): string {
    return gatewayForm.platform || "local";
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

  async function createPairing() {
    const result = await api.gatewayPairingCreate({
      platform: firstPlatform(),
      user_id: gatewayForm.user_id,
      session_id: gatewayForm.session_id
    });
    setPairingResult(result);
    setPreviewAction(null);
    await pairing.reload();
  }

  return (
    <PageShell
      title="消息网关与 Webhook"
      description="管理外部投递、配对状态、消息目录、后台服务、平台和 Webhook。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="外部投递和平台控制" />}
      metrics={[
        metric("网关", statusData.mode || statusData.status || "未知", statusTone(statusData.mode || statusData.status)),
        metric("后台服务", daemonData.running ? "运行中" : "已停止", daemonData.running ? "success" : "warning"),
        metric("平台", platformRows.length, "info"),
        metric("Webhook", list(webhooks.data).length, "info")
      ]}
    >
      <Panel title="网关配置">
        <div className="form-grid">
          <label className="field">
            <span>平台</span>
            <select
              data-testid="gateway-platform"
              value={gatewayForm.platform}
              onChange={(event) => setGatewayForm({ ...gatewayForm, platform: event.target.value })}
            >
              <option value="local">本地</option>
              <option value="feishu">飞书</option>
              <option value="wecom">企业微信</option>
              <option value="discord">Discord</option>
            </select>
          </label>
          <label className="field">
            <span>用户</span>
            <input data-testid="gateway-user" value={gatewayForm.user_id} onChange={(event) => setGatewayForm({ ...gatewayForm, user_id: event.target.value })} />
          </label>
          <label className="field">
            <span>会话</span>
            <input
              data-testid="gateway-session"
              value={gatewayForm.session_id}
              onChange={(event) => setGatewayForm({ ...gatewayForm, session_id: event.target.value })}
            />
          </label>
          <label className="field">
            <span>目标</span>
            <input data-testid="gateway-target" value={gatewayForm.target} onChange={(event) => setGatewayForm({ ...gatewayForm, target: event.target.value })} />
          </label>
        </div>
      </Panel>

      <div className="grid-2">
        <Panel title="配对状态">
          <div data-testid="gateway-pairing-panel">
            <div className="form-grid">
              <div className="field">
                <span>平台</span>
                <strong>{valueOf(pairingData, ["platform"], "local")}</strong>
              </div>
              <div className="field">
                <span>用户</span>
                <strong>{valueOf(pairingData, ["user_id"], settings?.userId || "-")}</strong>
              </div>
              <div className="field">
                <span>会话</span>
                <strong>{valueOf(pairingData, ["session_id"], "-")}</strong>
              </div>
              <div className="field">
                <span>配置状态</span>
                <StatusBadge tone={pairingData.configured ? "success" : "warning"}>{pairingData.configured ? "已配置" : "未配置"}</StatusBadge>
              </div>
            </div>
            <div className="page-actions">
              <Button data-testid="gateway-pairing-refresh" disabled={!controlAvailable} onClick={() => void pairing.reload()}>
                刷新配对
              </Button>
              <Button data-testid="gateway-pairing-create" disabled={!controlAvailable} onClick={() => setPreviewAction("pair-create")}>
                创建配对
              </Button>
            </div>
            {pairingResult ? <JsonPanel data={pairingResult} title="配对结果" /> : null}
          </div>
        </Panel>

        <Panel title="投递预览">
          <label className="field">
            <span>消息内容</span>
            <textarea data-testid="gateway-message" value={draft} onChange={(event) => setDraft(event.target.value)} />
            <small>这里会创建受控投递请求，不会直接发送。</small>
          </label>
          <Button data-testid="gateway-send-local" disabled={!controlAvailable} onClick={() => setPreviewAction("send")}>
            创建投递审批
          </Button>
        </Panel>
      </div>

      <div className="grid-3">
        <Panel title="平台">
          <DataTable
            items={platformRows}
            columns={[
              { key: "platform", header: "平台" },
              { key: "configured", header: "是否配置" },
              { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }
            ]}
          />
        </Panel>
        <Panel title="消息">
          <DataTable items={messageRows} columns={[{ key: "platform", header: "平台" }, { key: "direction", header: "方向" }, { key: "status", header: "状态" }]} />
        </Panel>
        <Panel title="目录与 Webhook">
          <DataTable items={[...list(directory.data), ...list(webhooks.data)]} columns={[{ key: "platform", header: "平台" }, { key: "kind", header: "类型" }, { key: "name", header: "名称" }]} />
        </Panel>
      </div>

      <Panel title="网关操作">
        <div className="page-actions">
          <Button data-testid="gateway-refresh-directory" disabled={!controlAvailable} onClick={() => setPreviewAction("refresh-directory")}>
            刷新目录
          </Button>
          <Button data-testid="gateway-retry-first" disabled={!controlAvailable || !messageRows.length} onClick={() => setPreviewAction("retry")}>
            重试第一条消息
          </Button>
          <Button data-testid="gateway-platform-health" disabled={!controlAvailable || !platformRows.length} onClick={() => void platformAction("health")}>
            检查平台健康
          </Button>
          <Button data-testid="gateway-platform-start" disabled={!controlAvailable || !platformRows.length} onClick={() => setPreviewAction("start")}>
            启动平台
          </Button>
          <Button data-testid="gateway-platform-stop" disabled={!controlAvailable || !platformRows.length} onClick={() => setPreviewAction("stop")}>
            停止平台
          </Button>
        </div>

        {previewAction ? (
          <DryRunPreview
            title="消息网关操作预览"
            changes={[
              { label: "操作", after: gatewayActionLabel[previewAction] },
              { label: "平台", after: firstPlatform() },
              {
                label: "详情",
                after:
                  previewAction === "send"
                    ? draft
                    : previewAction === "pair-create"
                      ? `将 ${settings?.userId || "local-user"} 配对到 ${firstPlatform()}`
                      : "通过 Agent 受控路由执行"
              }
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
              if (previewAction === "pair-create") {
                void createPairing();
                return;
              }
              void platformAction(previewAction === "start" ? "start" : "stop");
            }}
          />
        ) : null}
      </Panel>

      <JsonPanel data={{ status: status.data, daemon: daemon.data, pairing: pairing.data, send_result: sendResult }} title="消息网关证据" />
      <Panel title="边界" action={<Radio size={18} />}>
        <p>外部投递、配对、后台服务控制、目录刷新和平台操作都必须经过 Agent HTTP 路由和可见权限门禁。</p>
      </Panel>
    </PageShell>
  );
}
