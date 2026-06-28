import { Radio } from "lucide-react";
import { useMemo, useState } from "react";

import { DryRunPreview } from "../components/IntentComponents";
import { McpAddButton } from "../components/McpAddDialog";
import { SkillAddButton } from "../components/SkillAddDialog";
import { StatusLight, inferStatusFromData } from "../components/StatusLight";
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
      title="Integrations"
      description="Overview for MCP, connectors, plugins, skills, gateway, and readiness."
      badge={<GatedNotice controlAvailable={controlAvailable} action="integration management" />}
      metrics={[
        metric("MCP Servers", list(mcp.data).length, "success"),
        metric("Connectors Ready", connectorData.ready ?? "-", "info"),
        metric("Plugins", list(plugins.data).length, "success"),
        metric("Gateway", gatewayData.mode || gatewayData.status || "unknown", statusTone(gatewayData.mode || gatewayData.status))
      ]}
    >
      <div className="grid-3">
        <LinkCard to="/mcp-connectors" title="MCP / Connectors" detail="Servers, tools, resources, prompts, OAuth, and connector health." tone="info" meta="P0 entry" />
        <LinkCard to="/plugins-skills" title="Plugins / Skills" detail="Runtime skills, plugins, tests, and controlled changes." tone="success" meta="P0 entry" />
        <LinkCard to="/gateway-webhooks" title="Gateway" detail="Platform status, directory, daemon state, pairing, and webhook feedback." tone="warning" meta="P1 entry" />
        <LinkCard to="/readiness" title="Health & Readiness" detail="Agent, Hermes, and financial readiness." meta="Diagnostics" />
        <LinkCard to="/settings" title="Settings" detail="Base URL, tokens, mode, and global boundaries." meta="Secrets redaction" />
        <LinkCard to="/tools-approvals" title="Approvals" detail="Intent and approval review flow." tone="gated" meta="ActionIntent" />
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

  async function handleAddMcp(data: { name: string; command: string; args?: string[]; env?: Record<string, string> }) {
    await api.mcpServerAdd(data);
    await servers.reload();
    setActionResult({ success: true, message: "MCP server added" });
  }

  async function toggleServer(serverId: string, enabled: boolean) {
    await api.mcpServerUpdate(serverId, { enabled });
    await servers.reload();
    setActionResult({ success: true, message: enabled ? "MCP server enabled" : "MCP server disabled" });
  }

  async function deleteServer(serverId: string, name: string) {
    if (!window.confirm(`Delete MCP server "${name}"?`)) return;
    await api.mcpServerDelete(serverId);
    await servers.reload();
    setActionResult({ success: true, message: "MCP server deleted" });
  }

  return (
    <PageShell
      title="MCP / Connectors"
      description="Manage MCP servers, resources, prompts, and connector health."
      badge={<GatedNotice controlAvailable={controlAvailable} action="MCP management" />}
      actions={controlAvailable ? <McpAddButton onAdd={handleAddMcp} /> : undefined}
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
                { key: "name", header: "Name" },
                { key: "transport", header: "Transport" },
                { key: "status", header: "Status", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> },
                {
                  key: "id",
                  header: "Actions",
                  render: (item) => (
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <Button onClick={() => void toggleServer(String(item.id || ""), !Boolean(item.enabled))} disabled={!controlAvailable || !item.id}>
                        {item.enabled ? "Disable" : "Enable"}
                      </Button>
                      <Button tone="danger" onClick={() => void deleteServer(String(item.id || ""), String(item.name || item.id || ""))} disabled={!controlAvailable || !item.id}>
                        Delete
                      </Button>
                    </div>
                  )
                }
              ]}
            />
          )}
        </ResourcePanel>

        <ResourcePanel title="Connectors" resource={connectors}>
          {(data) => (
            <DataTable
              items={list(data)}
              columns={[
                { key: "name", header: "Name" },
                { key: "category", header: "Category" },
                { key: "status", header: "Status", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }
              ]}
            />
          )}
        </ResourcePanel>
      </div>

      <div className="grid-3">
        <Panel title="Tools">
          <DataTable items={list(tools.data)} columns={[{ key: "name", header: "Tool" }, { key: "server", header: "Server" }, { key: "status", header: "Status" }]} />
        </Panel>
        <Panel title="Resources">
          <DataTable items={resourceRows} columns={[{ key: "uri", header: "URI" }, { key: "server", header: "Server" }, { key: "status", header: "Status" }]} />
        </Panel>
        <Panel title="Prompts / OAuth">
          <DataTable items={[...promptRows, ...list(oauth.data)]} columns={[{ key: "name", header: "Name" }, { key: "server", header: "Server" }, { key: "status", header: "Status" }]} />
        </Panel>
      </div>

      <Panel title="MCP Actions">
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
    </PageShell>
  );
}

function PluginsSkillsPage({ api, controlAvailable }: PageProps) {
  const skills = useAsyncResource(() => api.skills(), [api]);
  const plugins = useAsyncResource(() => api.plugins(), [api]);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "create-skill" | "delete-skill" | "toggle-plugin">(null);
  const sampleSkillName = useMemo(() => `desktop-v1-smoke-skill-${Date.now().toString(36)}`, []);
  const installedSkills = list(skills.data);
  const pluginRows = list(plugins.data);

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
      setActionResult({ success: false, error: `Skill not found: ${name}` });
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
    setActionResult({ success: true, message: "Skill added" });
  }

  async function toggleSkill(skillId: string, enabled: boolean) {
    await api.skillUpdate(skillId, { enabled });
    await skills.reload();
    setActionResult({ success: true, message: enabled ? "Skill enabled" : "Skill disabled" });
  }

  async function deleteSkill(skillId: string, name: string) {
    if (!window.confirm(`Delete skill "${name}"?`)) return;
    await api.skillDelete(skillId);
    await skills.reload();
    setActionResult({ success: true, message: "Skill deleted" });
  }

  return (
    <PageShell
      title="Plugins / Skills"
      description="Manage runtime skills, plugins, tests, and controlled changes."
      badge={<GatedNotice controlAvailable={controlAvailable} action="plugin / skill changes" />}
      actions={controlAvailable ? <SkillAddButton onAdd={handleAddSkill} /> : undefined}
      metrics={[
        metric("Skills", installedSkills.length, "success"),
        metric("Plugins", pluginRows.length, "info"),
        metric("Mutations", controlAvailable ? "allowed" : "gated", controlAvailable ? "success" : "gated"),
        metric("Secrets", "Redacted", "success")
      ]}
    >
      <div className="grid-2">
        <Panel title="Skills">
          <DataTable
            items={installedSkills}
            columns={[
              { key: "name", header: "Name" },
              { key: "type", header: "Type" },
              { key: "status", header: "Status", render: (item) => <StatusLight status={inferStatusFromData(item.status || item.enabled)} label={valueOf(item, ["status"], item.enabled ? "enabled" : "disabled")} /> },
              {
                key: "id",
                header: "Actions",
                render: (item) => (
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <Button onClick={() => void toggleSkill(String(item.id || ""), !Boolean(item.enabled))} disabled={!controlAvailable || !item.id}>
                      {item.enabled ? "Disable" : "Enable"}
                    </Button>
                    <Button tone="danger" onClick={() => void deleteSkill(String(item.id || ""), String(item.name || item.id || ""))} disabled={!controlAvailable || !item.id}>
                      Delete
                    </Button>
                  </div>
                )
              }
            ]}
          />
        </Panel>

        <Panel title="Plugins">
          <DataTable
            items={pluginRows}
            columns={[
              { key: "name", header: "Plugin" },
              { key: "enabled", header: "Enabled", render: (item) => <StatusLight status={item.enabled ? "connected" : "disconnected"} label={item.enabled ? "enabled" : "disabled"} /> },
              { key: "tools", header: "Tools" },
              { key: "commands", header: "Commands" }
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
            title="Plugin / Skill preview"
            changes={[
              { label: "Action", after: previewAction },
              { label: "Target", after: previewAction.includes("skill") ? sampleSkillName : String(pluginRows[0]?.name || pluginRows[0]?.id || "-") },
              { label: "Mode", after: "controlled change" }
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

        {actionResult ? <JsonPanel data={actionResult} title="Skill / plugin action result" /> : null}
      </Panel>
    </PageShell>
  );
}

function GatewayWebhooksPage({ api, controlAvailable, settings }: PageProps) {
  const [gatewayForm, setGatewayForm] = useState({
    platform: "local",
    user_id: settings?.userId || "local-user",
    session_id: "gateway-session",
    target: "Research Desk"
  });
  const status = useAsyncResource(() => api.gatewayStatus(), [api]);
  const daemon = useAsyncResource(() => api.gatewayDaemon(), [api]);
  const platforms = useAsyncResource(() => api.gatewayPlatforms(), [api]);
  const pairing = useAsyncResource(
    () =>
      api.gatewayPairing({
        platform: gatewayForm.platform,
        user_id: gatewayForm.user_id,
        session_id: gatewayForm.session_id
      }),
    [api, gatewayForm.platform, gatewayForm.user_id, gatewayForm.session_id]
  );
  const messages = useAsyncResource(() => api.gatewayMessages(), [api]);
  const directory = useAsyncResource(() => api.gatewayDirectory(), [api]);
  const webhooks = useAsyncResource(() => api.webhooks(), [api]);
  const [draft, setDraft] = useState("Radar digest preview: confirm before delivery.");
  const [sendResult, setSendResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "send" | "refresh-directory" | "retry" | "start" | "stop" | "pair-create">(null);
  const [pairingResult, setPairingResult] = useState<unknown>(null);
  const statusData = dataObject(status.data, {});
  const daemonData = dataObject(daemon.data, {});
  const pairingData = dataObject(pairing.data, {});
  const platformRows = list(platforms.data);
  const messageRows = list(messages.data);

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
      title="Gateway / Webhooks"
      description="Manage outbound delivery, pairing status, message directory, daemon state, platforms, and webhooks."
      badge={<GatedNotice controlAvailable={controlAvailable} action="external delivery / platform control" />}
      metrics={[
        metric("Gateway", statusData.mode || statusData.status || "unknown", statusTone(statusData.mode || statusData.status)),
        metric("Daemon", daemonData.running ? "running" : "stopped", daemonData.running ? "success" : "warning"),
        metric("Platforms", platformRows.length, "info"),
        metric("Webhooks", list(webhooks.data).length, "info")
      ]}
    >
      <Panel title="Gateway Configuration">
        <div className="form-grid">
          <label className="field">
            <span>Platform</span>
            <select
              data-testid="gateway-platform"
              value={gatewayForm.platform}
              onChange={(event) => setGatewayForm({ ...gatewayForm, platform: event.target.value })}
            >
              <option value="local">local</option>
              <option value="feishu">feishu</option>
              <option value="wecom">wecom</option>
              <option value="discord">discord</option>
            </select>
          </label>
          <label className="field">
            <span>User</span>
            <input data-testid="gateway-user" value={gatewayForm.user_id} onChange={(event) => setGatewayForm({ ...gatewayForm, user_id: event.target.value })} />
          </label>
          <label className="field">
            <span>Session</span>
            <input
              data-testid="gateway-session"
              value={gatewayForm.session_id}
              onChange={(event) => setGatewayForm({ ...gatewayForm, session_id: event.target.value })}
            />
          </label>
          <label className="field">
            <span>Target</span>
            <input data-testid="gateway-target" value={gatewayForm.target} onChange={(event) => setGatewayForm({ ...gatewayForm, target: event.target.value })} />
          </label>
        </div>
      </Panel>

      <div className="grid-2">
        <Panel title="Pairing status">
          <div data-testid="gateway-pairing-panel">
            <div className="form-grid">
              <div className="field">
                <span>Platform</span>
                <strong>{valueOf(pairingData, ["platform"], "local")}</strong>
              </div>
              <div className="field">
                <span>User</span>
                <strong>{valueOf(pairingData, ["user_id"], settings?.userId || "-")}</strong>
              </div>
              <div className="field">
                <span>Session</span>
                <strong>{valueOf(pairingData, ["session_id"], "-")}</strong>
              </div>
              <div className="field">
                <span>Configured</span>
                <StatusBadge tone={pairingData.configured ? "success" : "warning"}>{pairingData.configured ? "true" : "false"}</StatusBadge>
              </div>
            </div>
            <div className="page-actions">
              <Button data-testid="gateway-pairing-refresh" onClick={() => void pairing.reload()}>
                Refresh pairing
              </Button>
              <Button data-testid="gateway-pairing-create" disabled={!controlAvailable} onClick={() => setPreviewAction("pair-create")}>
                Create pairing
              </Button>
            </div>
            {pairingResult ? <JsonPanel data={pairingResult} title="Pairing result" /> : null}
          </div>
        </Panel>

        <Panel title="Delivery Preview">
          <label className="field">
            <span>Message</span>
            <textarea data-testid="gateway-message" value={draft} onChange={(event) => setDraft(event.target.value)} />
            <small>Creates a controlled delivery request rather than sending directly.</small>
          </label>
          <Button data-testid="gateway-send-local" disabled={!controlAvailable} onClick={() => setPreviewAction("send")}>
            Create delivery intent
          </Button>
        </Panel>
      </div>

      <div className="grid-3">
        <Panel title="Platforms">
          <DataTable
            items={platformRows}
            columns={[
              { key: "platform", header: "Platform" },
              { key: "configured", header: "Configured" },
              { key: "status", header: "Status", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }
            ]}
          />
        </Panel>
        <Panel title="Messages">
          <DataTable items={messageRows} columns={[{ key: "platform", header: "Platform" }, { key: "direction", header: "Direction" }, { key: "status", header: "Status" }]} />
        </Panel>
        <Panel title="Directory / Webhooks">
          <DataTable items={[...list(directory.data), ...list(webhooks.data)]} columns={[{ key: "platform", header: "Platform" }, { key: "kind", header: "Kind" }, { key: "name", header: "Name" }]} />
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
            title="Gateway preview"
            changes={[
              { label: "Action", after: previewAction },
              { label: "Platform", after: firstPlatform() },
              {
                label: "Detail",
                after:
                  previewAction === "send"
                    ? draft
                    : previewAction === "pair-create"
                      ? `pair ${settings?.userId || "local-user"} to ${firstPlatform()}`
                      : "Controlled Agent route action"
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

      <JsonPanel data={{ status: status.data, daemon: daemon.data, pairing: pairing.data, send_result: sendResult }} title="Gateway evidence" />
      <Panel title="Boundary" action={<Radio size={18} />}>
        <p>Outbound delivery, pairing, daemon control, directory refresh, and platform actions stay behind Agent HTTP routes and visible control gates.</p>
      </Panel>
    </PageShell>
  );
}
