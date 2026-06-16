import { formatApiError, requestJson } from "../../api";
import type {
  CapabilityParity,
  FullModeConsoleData,
  HermesConsoleSnapshot,
  HermesStatus,
  ToolCatalogItem
} from "../../types";
import { compactForSearch } from "./core";
import type { AiaskApiCore } from "./core";

async function controlData<T>(client: AiaskApiCore, path: string, fallback: T): Promise<T> {
  try {
    return await requestJson<T>(client.endpoint, path, { token: client.controlToken });
  } catch (error) {
    const reason = (() => {
      if (typeof (error as { status?: number })?.status === "number") {
        const status = (error as { status: number }).status;
        if (status === 401) return "control_token_invalid";
        if (status === 403) return "control_token_forbidden";
        if (status === 503) return "control_token_unconfigured";
        return `http_${status}`;
      }
      return "network";
    })();
    if (fallback && typeof fallback === "object" && !Array.isArray(fallback)) {
      return {
        ...(fallback as Record<string, unknown>),
        status: "degraded",
        error: formatApiError(error),
        reason
      } as T;
    }
    return fallback;
  }
}

export async function fullConsoleSnapshot(client: AiaskApiCore): Promise<HermesConsoleSnapshot> {
  const [hermesStatus, parity, readiness] = await Promise.all([
    requestJson<HermesStatus>(client.endpoint, "/v1/hermes/status", { token: client.apiToken }),
    requestJson<CapabilityParity>(client.endpoint, "/v1/capabilities/parity", { token: client.apiToken }),
    requestJson<unknown>(client.endpoint, "/v1/hermes/readiness", { token: client.apiToken })
  ]);
  const fullConsole: FullModeConsoleData = {
    parity,
    readiness,
    providers: hermesStatus.providers,
    memory: hermesStatus.memory,
    acp: hermesStatus.acp,
    security: hermesStatus.security,
    skillPacks: hermesStatus.skill_packs
  };

  if (!client.controlToken.trim()) {
    return {
      hermesStatus,
      hermesTools: [],
      fullConsole,
      message: "CONTROL_TOKEN_REQUIRED"
    };
  }

  const [
    catalog,
    processes,
    browserSessions,
    skills,
    plugins,
    mcpServers,
    mcpTools,
    mcpResources,
    mcpPrompts,
    mcpOauth,
    webhooks,
    approvals,
    jobs,
    gatewayStatus,
    gatewayPlatforms,
    gatewayMessages,
    gatewayDirectory,
    terminalBackends,
    terminalSessions,
    learningStatus,
    learningReview,
    rlEnvironments,
    rlRuns
  ] = await Promise.all([
    controlData<{ data: ToolCatalogItem[] }>(client, "/v1/hermes/tools", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/processes", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/browser/sessions", { data: [] }),
    controlData<{ data: unknown }>(client, "/v1/skills", { data: {} }),
    controlData<{ data: unknown[] }>(client, "/v1/plugins", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/mcp/servers?all=true", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/mcp/tools?all=true", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/mcp/resources?all=true", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/mcp/prompts?all=true", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/mcp/oauth_status?all=true", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/webhooks", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/approvals", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/jobs", { data: [] }),
    controlData<unknown>(client, "/v1/gateway/status", {}),
    controlData<{ data: unknown[] }>(client, "/v1/gateway/platforms", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/gateway/messages", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/gateway/directory", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/terminal/backends", { data: [] }),
    controlData<{ data: unknown[] }>(client, "/v1/terminal/sessions", { data: [] }),
    controlData<unknown>(client, "/v1/learning/status", {}),
    controlData<{ data: unknown[] }>(client, "/v1/learning/review", { data: [] }),
    controlData<{ data: unknown }>(client, "/v1/rl/environments", { data: {} }),
    controlData<{ data: unknown[] }>(client, "/v1/rl/runs", { data: [] })
  ]);

  Object.assign(fullConsole, {
    processes: processes.data || [],
    browserSessions: browserSessions.data || [],
    skills: skills.data,
    plugins: plugins.data || [],
    mcpServers: mcpServers.data || [],
    mcpTools: mcpTools.data || [],
    mcpResources: mcpResources.data || [],
    mcpPrompts: mcpPrompts.data || [],
    mcpOauth: mcpOauth.data || [],
    webhooks: webhooks.data || [],
    approvals: approvals.data || [],
    jobs: jobs.data || [],
    gatewayStatus,
    gatewayPlatforms: gatewayPlatforms.data || [],
    gatewayMessages: gatewayMessages.data || [],
    gatewayDirectory: gatewayDirectory.data || [],
    terminalBackends: terminalBackends.data || [],
    terminalSessions: terminalSessions.data || [],
    learningStatus,
    learningReview: learningReview.data || [],
    rlEnvironments: rlEnvironments.data,
    rlRuns: rlRuns.data || [],
    homeAssistant: (hermesStatus.parity?.matrix || []).filter((item) => item.reference === "homeassistant"),
    moa: (catalog.data || []).filter((tool) => tool.name === "agent_moa"),
    dynamicMcpTools: (mcpTools.data || []).filter((tool) => compactForSearch(tool).includes("agent_mcp_")),
    dynamicPluginTools: (plugins.data || []).filter((plugin) => compactForSearch(plugin).includes("tools")),
    pluginHooks: (readiness as { plugins?: unknown }).plugins,
    tuiController: (readiness as { tui?: unknown }).tui || hermesStatus.tui || {},
    rlReadiness: (readiness as { rl?: unknown }).rl,
    providers: hermesStatus.providers || (readiness as { providers?: unknown }).providers,
    memory: hermesStatus.memory || (readiness as { memory?: unknown }).memory,
    acp: hermesStatus.acp || (readiness as { acp?: unknown }).acp,
    security: hermesStatus.security || (readiness as { security?: unknown }).security,
    skillPacks: hermesStatus.skill_packs || (readiness as { skill_packs?: unknown }).skill_packs
  });

  return {
    hermesStatus,
    hermesTools: catalog.data || [],
    fullConsole,
    message: "FULL_CONSOLE_SYNCED"
  };
}
