import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CapabilitiesWorkspace } from "./CapabilitiesWorkspace";

const payload = {
  object: "aiask.desktop_capabilities",
  summary: {
    source: "gated",
    status: "in_progress",
    counts: { implemented: 4, live_unverified: 2, unconfigured: 1, failed: 0, missing: 0 },
    issue_count: 1,
    control: {
      authorized: false,
      reason: "control token is not configured",
      full_mode_enabled: true,
      control_token_configured: false,
      control_authorized: false,
      gated_reason: "control token is not configured"
    },
    refreshed_at: 1777392000
  },
  hermes: {
    status: {
      implementation: "aiask_native",
      baseline: "Hermes v0.14.0 full runtime capability reference",
      embedded_vendor_runtime: false,
      full_mode_enabled: true,
      full_mode_active: false
    },
    parity: {
      object: "aiask.capability_parity",
      baseline: "Hermes v0.14.0 full runtime capability reference",
      scope: "hermes_full_runtime",
      embedded_vendor_runtime: false,
      required_count: 1,
      covered_count: 1,
      complete_count: 0,
      coverage_ratio: 1,
      complete_ratio: 0,
      status: "in_progress",
      strict_status: "in_progress",
      matrix: []
    },
    readiness: {},
    tool_mapping: [{ hermes_tool: "terminal", area: "terminal", status: "implemented", aiask_tools: ["agent_terminal"] }],
    platform_mapping: [{ platform: "discord", area: "platform", status: "live_unverified", aiask_adapter: "discord" }],
    feature_mapping: [{ feature: "mcp_tools", area: "mcp", status: "implemented", aiask_tools: ["agent_mcp_manage"] }],
    issues: [{ platform: "discord", area: "platform", status: "live_unverified" }]
  },
  mcp: {
    gated: true,
    registration_status: "not_registered",
    discovery_status: "not_registered",
    configured: false,
    config_path: "/tmp/mcp_servers.json",
    config_exists: false,
    auth_configured: false,
    discovered_counts: { tools: 0, resources: 0, prompts: 0 },
    servers: [],
    tools: [],
    resources: [],
    prompts: [],
    oauth: []
  },
  strategy_factory: {
    status: { success: false, data: { configured: false }, error: "missing", error_code: "MISSING_AKSHARE_MCP" },
    runs: { success: false, data: { configured: false }, error: "missing", error_code: "MISSING_AKSHARE_MCP" },
    review_snapshot: { success: false, data: { configured: false }, error: "missing", error_code: "MISSING_AKSHARE_MCP" }
  },
  skills: { gated: true, reason: "control token is not configured" },
  plugins: { gated: true },
  ai: {
    object: "aiask.ai_status",
    provider: "mock",
    model: "gpt-4.1-mini",
    base_url_configured: false,
    api_key_configured: false,
    mock: true,
    configured: true,
    secrets_redacted: true
  },
  raw_refs: { ai_status: "/v1/ai/status" }
};

const authorizedPayload = {
  ...payload,
  summary: {
    ...payload.summary,
    source: "live_backend",
    control: {
      ...payload.summary.control,
      authorized: true,
      reason: null,
      control_authorized: true,
      gated_reason: null
    }
  },
  hermes: {
    ...payload.hermes,
    skill_packs: { object: "aiask.skill_pack_status", status: "ready", packs: [{ name: "finance-modeling" }] }
  },
  skill_packs: { object: "aiask.skill_pack_status", status: "ready", packs: [{ name: "finance-modeling" }] },
  plugins: [{ name: "audit-plugin", enabled: true, source: "local", description: "Audit hooks" }]
};

const mcpAuthorizedPayload = {
  ...authorizedPayload,
  mcp: {
    ...payload.mcp,
    gated: false,
    registration_status: "registered",
    discovery_status: "discovered",
    auth_configured: true,
    configured: true,
    config_exists: true,
    config_path: "/tmp/mcp_servers.json",
    detected_service_port: 3100,
    suggested_registration_url: "http://127.0.0.1:3100/mcp",
    auth_env_vars: ["AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION"],
    discovered_counts: { tools: 2, resources: 1, prompts: 1 },
    servers: [{ name: "akshare-local", transport: "streamable_http", domain: "financial", configured: true }],
    tools: [{ server: "akshare-local", name: "quote", wrapped_name: "agent_mcp_quote", description: "Quote tool" }],
    resources: [{ uri: "aiask://quotes" }],
    prompts: [{ name: "risk-review" }],
    oauth: [{ server: "akshare-local" }]
  }
};

describe("CapabilitiesWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders operational capability data from the desktop aggregate endpoint", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );

    render(<CapabilitiesWorkspace endpoint="http://127.0.0.1:8767" apiToken="" controlToken="" />);

    await waitFor(() => expect(screen.getByText("Runtime review board")).toBeInTheDocument());
    expect(screen.getByText("Implemented")).toBeInTheDocument();
    expect(screen.getByText("Actionable gaps")).toBeInTheDocument();
    expect(screen.getAllByText("control token is not configured").length).toBeGreaterThan(0);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8767/v1/desktop/capabilities",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("renders the native plugins tab without loading external plugin JavaScript", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/tools/__manifest__/test")) {
        return new Response(
          JSON.stringify({
            object: "plugin.tool_test",
            success: true,
            data: { test_type: "manifest", note: "plugin surface is registered" },
            error: null
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(JSON.stringify(authorizedPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    });

    render(<CapabilitiesWorkspace endpoint="http://127.0.0.1:8767" apiToken="" controlToken="secret" />);

    await waitFor(() => expect(screen.getByText("Runtime review")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Plugins/ }));

    expect(screen.getByText("Native plugin and skill-pack governance")).toBeInTheDocument();
    expect(screen.getByText("audit-plugin")).toBeInTheDocument();
    expect(screen.getByText(/External Hermes dashboard plugin JavaScript is not loaded or executed/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Self-test" }));
    await waitFor(() => expect(screen.getByText("plugin surface is registered")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8767/v1/plugins/audit-plugin/tools/__manifest__/test",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("renders MCP connector review counts for authorized discovery", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(mcpAuthorizedPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );

    render(<CapabilitiesWorkspace endpoint="http://127.0.0.1:8767" apiToken="" controlToken="secret" />);

    await waitFor(() => expect(screen.getByText("Runtime review")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /MCP/ }));

    expect(screen.getByText("Connector review queue")).toBeInTheDocument();
    expect(screen.getAllByText("2 tools / 1 resources / 1 prompts").length).toBeGreaterThan(0);
    expect(screen.getByText("agent_mcp_quote")).toBeInTheDocument();
  });

  it("shows structured MCP resource errors without treating them as offline", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/v1/mcp/resources/read")) {
        return new Response(
          JSON.stringify({
            object: "mcp.resource",
            success: false,
            data: { server: "akshare-local", detail: "authorization required", missing_auth_env_vars: ["AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION"] },
            error: "authorization required",
            error_code: "MCP_DISCOVERY_AUTH_REQUIRED"
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(JSON.stringify(mcpAuthorizedPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    });

    render(<CapabilitiesWorkspace endpoint="http://127.0.0.1:8767" apiToken="" controlToken="secret" />);

    await waitFor(() => expect(screen.getByText("Runtime review")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /MCP/ }));
    fireEvent.click(screen.getByRole("button", { name: "Read MCP resource" }));

    await waitFor(() => expect(screen.getByText("MCP_DISCOVERY_AUTH_REQUIRED")).toBeInTheDocument());
    expect(screen.getByText("Set env vars: AIASK_MCP_AKSHARE_LOCAL_AUTHORIZATION")).toBeInTheDocument();
  });
});
