type MockMcpCapabilities = {
  servers?: unknown;
  tools?: unknown;
  resources?: unknown;
  prompts?: unknown;
  oauth?: unknown;
};

export function mockSkillsList(skills: unknown) {
  return { data: skills };
}

export function mockSkillInstall(body: Record<string, unknown>) {
  return { object: "skill", status: "installed", name: body.name };
}

export function mockSkillUpdate() {
  return { object: "skill", status: "updated" };
}

export function mockSkillDelete() {
  return { object: "skill", status: "deleted" };
}

export function mockPluginsList(plugins: unknown) {
  return { data: plugins };
}

export function mockPluginUpsert(body: Record<string, unknown>) {
  return { object: "plugin_upserted", success: true, data: { name: body.name || "local-plugin", enabled: body.enabled ?? true } };
}

export function mockPluginUpdate(body: Record<string, unknown>) {
  return { object: "plugin_updated", enabled: body.enabled };
}

export function mockPluginCommands() {
  return { object: "list", data: [{ name: "doctor", description: "Run plugin diagnostics", enabled: true }] };
}

export function mockPluginCommandTest(plugin: string, command: string) {
  return { object: "plugin.command_test", success: true, data: { plugin, command, status: "ready" }, error: null };
}

export function mockPluginToolTest() {
  return { object: "plugin_tool_tested", success: true };
}

export function mockMcpServers(mcp: MockMcpCapabilities) {
  return { data: mcp.servers };
}

export function mockMcpTools(mcp: MockMcpCapabilities) {
  return { data: mcp.tools };
}

export function mockMcpResources(mcp: MockMcpCapabilities) {
  return { data: mcp.resources };
}

export function mockMcpPrompts(mcp: MockMcpCapabilities) {
  return { data: mcp.prompts };
}

export function mockMcpOauthStatus(mcp: MockMcpCapabilities) {
  return { data: mcp.oauth };
}

export function mockMcpRegisterLocal(body: Record<string, unknown>) {
  return { success: true, data: { status: "registered", server: body.name || "akshare-local" } };
}

export function mockMcpDiscover(body: Record<string, unknown>, tools: unknown) {
  return { success: true, data: { status: "discovered", server: body.server || "akshare-local", tools } };
}

export function mockMcpResourceRead(body: Record<string, unknown>) {
  return { success: true, data: { uri: body.uri, result: { text: "quote resource ok" } } };
}

export function mockMcpPromptGet(body: Record<string, unknown>) {
  return { success: true, data: { prompt: "risk prompt ok", name: body.name } };
}

export function mockMcpOauthStart(body: Record<string, unknown>) {
  return { success: false, error_code: "oauth_required", data: { server: body.server, configured: false } };
}

export function mockConnectorsSummary() {
  return {
    status: "ready",
    data: {
      total: 3,
      connected: 1,
      configured: 2,
      connectors: [
        { type: "mcp", name: "akshare-local", status: "ready" },
        { type: "platform", name: "discord", status: "missing_credentials", missing_env: ["DISCORD_BOT_TOKEN"] },
        { type: "financial", name: "tongdaxin", status: "ready" }
      ]
    }
  };
}

export function mockConnectorsList() {
  return {
    object: "list",
    data: [
      { type: "mcp", name: "akshare-local", category: "data", status: "ready", configured: true, connected: true },
      { type: "platform", name: "discord", category: "communication", status: "missing_credentials", configured: false, connected: false, missing_env: ["DISCORD_BOT_TOKEN"] },
      { type: "financial", name: "tongdaxin", category: "data", status: "ready", configured: true, connected: true }
    ]
  };
}

export function mockConnectorDetail(type: string, name: string, object: "connector.detail" | "connector.test") {
  return { object, data: { type, name, configured: true, connected: true, status: "ready", missing_env: [] } };
}
