import { type Page, type Route } from "@playwright/test";
import { CONTROL_TOKEN } from "./capabilitiesNavigation";
import { API_ORIGIN } from "./capabilitiesMockConstants";
import { handleDesktopGovernanceRoutes } from "./capabilitiesMockDesktopRoutes";
import {
  aiConfigPayload,
  aiStatus,
  capabilityPayload,
  hermesTools,
  localProfilePayload,
  type FactoryMode,
} from "./capabilitiesMockCorePayloads";
import {
  dataSyncPlanPayload,
  desktopDataStatusPayload,
  factorFactoryStatusPayload,
  factoryEventLineagePayload,
  factoryEventListPayload,
  factoryEventPreviewTasksPayload,
  incubationStatusEnvelope,
  intentEnvelope,
  jobsPayload,
  marketTemperatureCacheHistoryPayload,
  marketTemperatureCacheReadinessPayload,
  marketTemperatureForwardValidationPayload,
  marketTemperatureIndustryConstituentsPayload,
  marketTemperatureIndustryHistoryPayload,
  marketTemperatureSnapshotPayload,
  mergeStockDataSourceDraft,
  quantPresetsPayload,
  quantResearchRunPayload,
  redactStockDataSource,
  stockDataSourcesPayload,
  stockRadarCandidatesPayload,
  stockRadarDigestPayload,
  stockRadarStatusPayload,
  strategyEventsEnvelope,
} from "./capabilitiesMockDataMarket";
import {
  queryRecord,
  tradePredictionEnvelope,
  tradePredictionMatrix,
  tradePredictionOutcomes,
  tradePredictionStatus,
} from "./capabilitiesMockTradePrediction";
import {
  brokerAnalyticsFixture,
  brokerAccountsFixture,
  brokerDealsFixture,
  brokerOrdersFixture,
  brokerPositionsFixture,
  brokerProfileFixture,
  brokerReadinessPayload,
  brokerSnapshotPayload,
  connectorFixture,
  connectorFixtureList,
  connectorsSummaryPayload,
  financialManagerCatalogPayload,
  financialManagerQueryPayload,
  workbenchSummaryPayload,
} from "./capabilitiesMockDesktopFixtures";
export type { FactoryMode } from "./capabilitiesMockCorePayloads";
export { API_ORIGIN } from "./capabilitiesMockConstants";

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload)
  });
}

export async function setupApiMocks(page: Page, options: { factoryMode?: FactoryMode } = {}) {
  const factoryMode = options.factoryMode || "success";
  let webhookSubscriptions = [
    {
      webhook_id: "webhook_fixture",
      name: "Mock Webhook",
      events: ["MCP UI smoke test"],
      prompt: "mock",
      enabled: true,
      status: "ready"
    }
  ];
  let stockDataSources: Array<Record<string, unknown>> = [
    {
      id: "e2e:akshare",
      provider: "akshare",
      name: "E2E AKShare 本地源",
      enabled: true,
      priority: 10,
      base_url: "",
      status: "ready",
      configured: true,
      categories: ["quote", "kline", "fundamental"],
      markets: ["CN", "HK", "US"],
      timeout_seconds: 8,
      notes: "E2E default source"
    },
    {
      id: "e2e:tushare",
      provider: "tushare",
      name: "Tushare 主账号",
      enabled: true,
      priority: 20,
      base_url: "http://api.tushare.pro",
      api_key: "mock-stock-token",
      status: "ready",
      configured: true,
      categories: ["quote", "kline", "fundamental"],
      markets: ["CN"],
      symbol: "600519",
      timeout_seconds: 8
    },
    {
      id: "e2e:duckduckgo",
      provider: "duckduckgo",
      name: "DuckDuckGo fallback",
      enabled: true,
      priority: 50,
      base_url: "https://duckduckgo.com/html/",
      status: "ready",
      configured: true,
      categories: ["web_search", "research"],
      markets: ["Global"]
    }
  ];
  await page.route(`${API_ORIGIN}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const authorized = request.headers().authorization === `Bearer ${CONTROL_TOKEN}`;

    if (path === "/health/detailed") {
      return fulfillJson(route, {
        object: "aiask.health",
        status: "ok",
        service: "AIASK Agent E2E Mock",
        runtime: { model: "gpt-5.4", max_iterations: 12, model_timeout_seconds: 60, tool_timeout_seconds: 30 },
        tools: { count: 13, toolset: "finance_safe" },
        hermes: { full_mode_enabled: true, full_mode_active: authorized, parity: capabilityPayload(authorized, factoryMode).hermes.parity },
        control: { loopback_only: true, token_configured: true }
      });
    }
    if (path === "/v1/tools") {
      return fulfillJson(route, {
        object: "list",
        data: [
          { name: "agent_terminal", capability: "terminal", category: "system", status: "ready", side_effect: "read_only", description: "Mock terminal metadata" },
          { name: "agent_factory_status", capability: "factory", category: "quant", status: "ready", side_effect: "read_only", description: "Mock factory status" },
          { name: "agent_mcp_manage", capability: "mcp", category: "integration", status: "gated", side_effect: "stateful", description: "Mock MCP management" },
          { name: "agent_quant_data_gate", capability: "data", category: "quant", status: "ready", side_effect: "read_only", description: "Mock data gate" },
          { name: "agent_portfolio_risk", capability: "portfolio_risk", category: "financial_read", status: "ready", side_effect: "read_only", description: "Mock portfolio risk" },
          { name: "agent_memory_search", capability: "memory", category: "memory", status: "ready", side_effect: "read_only", description: "Mock memory search" },
          { name: "agent_action_intent_create", capability: "approval", category: "governance", status: "ready", side_effect: "stateful", description: "Mock approval intent" }
        ]
      });
    }
    if (path === "/v1/hermes/status") {
      return fulfillJson(route, {
        object: "aiask.hermes_status",
        implementation: "aiask_native",
        baseline: "Hermes v0.16.0 full runtime capability reference",
        baseline_version: "0.16.0",
        baseline_release_tag: "v2026.6.5",
        embedded_vendor_runtime: false,
        full_mode_enabled: true,
        parity: capabilityPayload(authorized, factoryMode).hermes.parity
      });
    }
    if (path === "/v1/desktop/capabilities") {
      return fulfillJson(route, capabilityPayload(authorized, factoryMode));
    }
    if (path === "/v1/desktop/workbench/summary") {
      return fulfillJson(route, workbenchSummaryPayload());
    }
    if (await handleDesktopGovernanceRoutes({ route, request, url, path, authorized, fulfillJson })) return;
    if (path === "/v1/desktop/data/status") {
      const codes = url.searchParams.get("codes")?.split(",").filter(Boolean) || ["600519", "000001", "000858"];
      const maxStaleDays = Number(url.searchParams.get("max_stale_days") || 5);
      return fulfillJson(route, desktopDataStatusPayload(codes, maxStaleDays));
    }
    if (path === "/v1/desktop/stock-data-sources") {
      if (request.method() === "POST") {
        const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
        const id = String(body.id || `e2e:${body.provider || "source"}:${stockDataSources.length + 1}`);
        const saved = { ...body, id, status: "ready", configured: true, updated_at: "2026-06-12T00:00:00Z" };
        stockDataSources = [saved, ...stockDataSources.filter((source) => source.id !== id)];
        return fulfillJson(route, { object: "aiask.stock_data_source", source: redactStockDataSource(saved), secrets_redacted: true });
      }
      return fulfillJson(route, stockDataSourcesPayload(stockDataSources));
    }
    if (path === "/v1/desktop/stock-data-sources/test") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      const inline = body.source && typeof body.source === "object" && !Array.isArray(body.source)
        ? body.source as Record<string, unknown>
        : null;
      const inlineId = String(inline?.id || body.id || "");
      const source = inline
        ? mergeStockDataSourceDraft(stockDataSources.find((item) => item.id === inlineId), inline)
        : stockDataSources.find((item) => item.id === body.id) || stockDataSources[0];
      return fulfillJson(route, {
        object: "aiask.stock_data_source_test",
        provider: source.provider || "akshare",
        mode: body.mode || "connectivity",
        success: true,
        status: "ready",
        configured: true,
        latency_ms: 12,
        sample_count: 3,
        source: redactStockDataSource(source),
        secrets_redacted: true
      });
    }
    if (path === "/v1/desktop/data/sync-plan") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, dataSyncPlanPayload(body));
    }
    if (path === "/v1/desktop/financial-manager/catalog") {
      return fulfillJson(route, financialManagerCatalogPayload());
    }
    if (path === "/v1/desktop/financial-manager/status") {
      return fulfillJson(route, {
        object: "aiask.desktop.financial_manager.status",
        status: "ready",
        catalog_summary: financialManagerCatalogPayload().summary,
        broker: { live_trading_enabled: false, read_only_surfaces: ["ths_query_position"], blocked_actions: ["ths_place_order"] },
        mcp: { registration: "registered", servers: [{ name: "finance-demo", domain: "financial" }] },
        secrets_redacted: true
      });
    }
    if (path === "/v1/desktop/financial-manager/query") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, financialManagerQueryPayload(body));
    }
    if (path === "/v1/desktop/broker-readiness") {
      return fulfillJson(route, brokerReadinessPayload());
    }
    if (path === "/v1/desktop/broker/sync") {
      return fulfillJson(route, {
        object: "aiask.desktop.broker_readonly",
        success: true,
        data: {
          sync_id: "broker_sync_e2e_qmt",
          profile: brokerProfileFixture,
          counts: {
            accounts: brokerAccountsFixture.length,
            positions: brokerPositionsFixture.length,
            orders: brokerOrdersFixture.length,
            deals: brokerDealsFixture.length
          },
          errors: [],
          analytics: brokerAnalyticsFixture()
        },
        error: null,
        read_only: true,
        live_trading_enabled: false,
        secrets_redacted: true,
        source_chain: ["desktop.e2e.fixture", "aiask_agent.broker_readonly"]
      });
    }
    if (path === "/v1/desktop/broker/accounts" || path === "/v1/desktop/broker/positions" || path === "/v1/desktop/broker/orders") {
      return fulfillJson(route, brokerSnapshotPayload());
    }
    if (path === "/v1/desktop/broker/analytics/latest" || path === "/v1/desktop/broker/analytics/run") {
      return fulfillJson(route, {
        object: "aiask.desktop.broker_readonly.analytics",
        success: true,
        data: brokerAnalyticsFixture(),
        error: null,
        read_only: true,
        live_trading_enabled: false,
        secrets_redacted: true,
        source_chain: ["desktop.e2e.fixture", "aiask_agent.broker_readonly"]
      });
    }
    if (path === "/v1/desktop/stock-radar/status") {
      return fulfillJson(route, { success: true, data: stockRadarStatusPayload(), error: null, error_code: null });
    }
    if (path === "/v1/desktop/stock-radar/candidates") {
      return fulfillJson(route, {
        success: true,
        data: stockRadarCandidatesPayload(url.searchParams.get("tier") || ""),
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/desktop/stock-radar/digest") {
      return fulfillJson(route, { success: true, data: stockRadarDigestPayload(), error: null, error_code: null });
    }
    if (path === "/v1/desktop/users/local-profile") {
      if (request.method() === "PATCH") {
        const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
        return fulfillJson(route, localProfilePayload(body));
      }
      return fulfillJson(route, localProfilePayload());
    }
    if (path === "/v1/desktop/factor-factory/status") {
      return fulfillJson(route, factorFactoryStatusPayload());
    }
    if (path === "/v1/desktop/quant/presets") {
      return fulfillJson(route, quantPresetsPayload());
    }
    if (path === "/v1/desktop/quant/research-runs") {
      return fulfillJson(route, quantResearchRunPayload());
    }
    if (path === "/v1/hermes/readiness") {
      return fulfillJson(route, capabilityPayload(true, factoryMode).hermes.readiness);
    }
    if (path === "/v1/capabilities/parity") {
      return fulfillJson(route, capabilityPayload(true, factoryMode).hermes.parity);
    }
    if (path === "/v1/hermes/tools") {
      return fulfillJson(route, { data: hermesTools().map((tool) => ({ name: tool.aiask_tools[0], capability: tool.area, category: tool.area, status: tool.status, side_effect: "read_only", description: tool.hermes_tool })) });
    }
    if (path === "/v1/hermes/admin/tools/agent_security_scan") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        success: true,
        data: {
          status: "completed",
          target: body.text ? "text" : body.path || ".",
          include_env: body.include_env === true,
          findings: [],
          arguments: body
        },
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/processes") {
      return fulfillJson(route, { data: [{ pid: 101, name: "aiask-agent", status: "running" }] });
    }
    if (path === "/v1/browser/sessions") {
      return fulfillJson(route, { data: [{ id: "browser_e2e", status: "idle" }] });
    }
    if (path === "/v1/skills") {
      if (request.method() === "POST") return fulfillJson(route, { success: true, data: { name: "e2e-skill", status: "installed" } });
      return fulfillJson(route, { data: { root: "/tmp/aiask-skills", skills: [{ name: "risk-review", description: "Risk review", path: "/tmp/aiask-skills/risk-review/SKILL.md", updated_at: "2026-05-21T08:00:00.000Z" }] } });
    }
    if (path.startsWith("/v1/skills/")) {
      if (request.method() === "DELETE") return fulfillJson(route, { success: true, data: { status: "deleted" } });
      return fulfillJson(route, { success: true, data: { status: "updated" } });
    }
    if (path === "/v1/plugins") {
      return fulfillJson(route, {
        data: [
          {
            name: "audit-plugin",
            enabled: true,
            source: "local",
            version: "0.1.0",
            description: "Mock audit plugin",
            tools: [{ name: "audit_echo" }],
            commands: [],
            hooks: []
          }
        ]
      });
    }
    if (path.startsWith("/v1/plugins/") && path.endsWith("/test")) {
      return fulfillJson(route, { success: true, data: { status: "plugin_tool_tested" } });
    }
    if (path.startsWith("/v1/plugins/")) {
      return fulfillJson(route, { success: true, data: { status: "plugin_updated" } });
    }
    if (path === "/v1/mcp/servers") {
      return fulfillJson(route, { data: capabilityPayload(true, factoryMode).mcp.servers });
    }
    if (path === "/v1/mcp/tools") {
      return fulfillJson(route, { data: capabilityPayload(true, factoryMode).mcp.tools });
    }
    if (path === "/v1/mcp/resources") {
      return fulfillJson(route, { data: capabilityPayload(true, factoryMode).mcp.resources });
    }
    if (path === "/v1/mcp/prompts") {
      return fulfillJson(route, { data: capabilityPayload(true, factoryMode).mcp.prompts });
    }
    if (path === "/v1/mcp/oauth_status") {
      return fulfillJson(route, { data: capabilityPayload(true, factoryMode).mcp.oauth });
    }
    if (path === "/v1/mcp/resources/read") {
      return fulfillJson(route, { object: "mcp.resource", data: { success: true, server: "finance-demo", uri: "aiask://quotes", result: { text: "quote resource ok" } } });
    }
    if (path === "/v1/mcp/prompts/get") {
      return fulfillJson(route, { object: "mcp.prompt", data: { success: true, server: "finance-demo", name: "risk-review", prompt: "risk prompt ok" } });
    }
    if (path === "/v1/mcp/oauth/start") {
      return fulfillJson(route, { object: "mcp.oauth_start", data: { status: "oauth_required", server: "finance-demo", authorization_url: "https://auth.local/authorize" } });
    }
    if (path === "/v1/mcp/register-local") {
      return fulfillJson(route, { object: "mcp.registration", success: true, data: { server: { name: "finance-demo", url: "http://127.0.0.1:3100/mcp" } } });
    }
    if (path === "/v1/mcp/discover") {
      return fulfillJson(route, { object: "mcp.discovery", success: true, data: { server: "finance-demo", tools_count: 1, resources_count: 1, prompts_count: 1 } });
    }
    if (path === "/v1/connectors/summary") {
      return fulfillJson(route, connectorsSummaryPayload());
    }
    if (path === "/v1/connectors") {
      const type = url.searchParams.get("type");
      const category = url.searchParams.get("category");
      const connectors = connectorFixtureList().filter((connector) => {
        const typeMatches = !type || String(connector.type || "") === type;
        const categoryMatches = !category || String(connector.category || "") === category;
        return typeMatches && categoryMatches;
      });
      return fulfillJson(route, { object: "list", data: connectors });
    }
    const connectorTestMatch = path.match(/^\/v1\/connectors\/([^/]+)\/([^/]+)\/test$/);
    if (connectorTestMatch) {
      const connectorType = decodeURIComponent(connectorTestMatch[1]);
      const connectorName = decodeURIComponent(connectorTestMatch[2]);
      const connector = connectorFixture(connectorType, connectorName) || { type: connectorType, name: connectorName };
      return fulfillJson(route, {
        object: "aiask.connector_test",
        data: { ...connector, last_test_status: "passed", test_result: { status: "passed", action: "connector.test" } }
      });
    }
    const connectorDetailMatch = path.match(/^\/v1\/connectors\/([^/]+)\/([^/]+)$/);
    if (connectorDetailMatch) {
      const connectorType = decodeURIComponent(connectorDetailMatch[1]);
      const connectorName = decodeURIComponent(connectorDetailMatch[2]);
      const connector = connectorFixture(connectorType, connectorName) || { type: connectorType, name: connectorName };
      return fulfillJson(route, { object: "aiask.connector_detail", data: connector });
    }
    if (path === "/v1/ai/status") {
      return fulfillJson(route, aiStatus());
    }
    if (path === "/v1/ai/config") {
      if (request.method() === "PATCH") {
        const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
        return fulfillJson(route, {
          object: "aiask.ai_config",
          saved: true,
          provider: body.provider || "openai",
          model: body.model || "gpt-5.4",
          base_url_configured: true,
          api_key_configured: true,
          mock: false,
          configured: true,
          updated_keys: ["AIASK_AGENT_MODEL_PROVIDER", "AIASK_AGENT_MODEL", "OPENAI_BASE_URL"],
          env_file: "/tmp/aiask/.env",
          secrets_redacted: true
        });
      }
      return fulfillJson(route, aiConfigPayload());
    }
    if (path === "/v1/ai/smoke") {
      return fulfillJson(route, {
        object: "aiask.ai_smoke",
        configured: true,
        success: true,
        provider: "openai",
        mock: false,
        model: "gpt-5.4",
        latency_ms: 123,
        response_preview: "AIASK model smoke ok.",
        usage: { total_tokens: 12 },
        tool_call_count: 0,
        secrets_redacted: true
      });
    }
    if (path === "/v1/ai/models") {
      return fulfillJson(route, {
        object: "list",
        configured: true,
        provider: "openai",
        unsupported: false,
        data: [
          { id: "gpt-5.4", owned_by: "fixture" },
          { id: "gpt-5.2", owned_by: "fixture" }
        ]
      });
    }
    if (path === "/v1/responses") {
      return fulfillJson(route, {
        id: "resp_fixture",
        object: "response",
        created_at: 1777467084,
        status: "completed",
        model: "gpt-5.4",
        output_text: "AIASK_OK",
        output: [{ type: "message", role: "assistant", content: [{ type: "output_text", text: "AIASK_OK" }] }],
        usage: { total_tokens: 20 },
        metadata: {
          session_id: "session_fixture",
          run_id: "run_fixture",
          mode: "finance_safe",
          tool_calls: [],
          audit_events: [
            { event: "run.started", run_id: "run_fixture", created_at: "2026-04-29T12:51:17.000Z" },
            { event: "model.started", run_id: "run_fixture", created_at: "2026-04-29T12:51:18.000Z" },
            { event: "model.completed", run_id: "run_fixture", created_at: "2026-04-29T12:51:19.000Z" },
            { event: "model.delta", run_id: "run_fixture", content: "AIASK_OK", created_at: "2026-04-29T12:51:19.000Z" },
            { event: "run.completed", run_id: "run_fixture", status: "completed", created_at: "2026-04-29T12:51:20.000Z" }
          ]
        }
      });
    }
    if (path === "/v1/runs/run_fixture/events") {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          "id: 1",
          "event: run.started",
          "data: {\"id\":\"evt_1\",\"kind\":\"system\",\"title\":\"run.started\",\"run_id\":\"run_fixture\",\"created_at\":\"2026-05-21T08:00:00.000Z\",\"status\":\"started\"}",
          "",
          "id: 2",
          "event: model.started",
          "data: {\"id\":\"evt_2\",\"kind\":\"system\",\"title\":\"model.started\",\"run_id\":\"run_fixture\",\"created_at\":\"2026-05-21T08:00:01.000Z\"}",
          "",
          "id: 3",
          "event: model.completed",
          "data: {\"id\":\"evt_3\",\"kind\":\"system\",\"title\":\"model.completed\",\"run_id\":\"run_fixture\",\"created_at\":\"2026-05-21T08:00:02.000Z\"}",
          "",
          "id: 4",
          "event: model.delta",
          "data: {\"id\":\"evt_4\",\"kind\":\"system\",\"title\":\"model.delta\",\"run_id\":\"run_fixture\",\"created_at\":\"2026-05-21T08:00:02.500Z\",\"data\":{\"content\":\"AIASK_OK\"}}",
          "",
          "id: 5",
          "event: run.completed",
          "data: {\"id\":\"evt_5\",\"kind\":\"system\",\"title\":\"run.completed\",\"run_id\":\"run_fixture\",\"created_at\":\"2026-05-21T08:00:03.000Z\",\"status\":\"completed\"}",
          "",
          ""
        ].join("\n")
      });
    }
    const runArtifactsMatch = path.match(/^\/v1\/runs\/([^/]+)\/artifacts$/);
    if (runArtifactsMatch) {
      const runId = decodeURIComponent(runArtifactsMatch[1]);
      return fulfillJson(route, {
        object: "list",
        run_id: runId,
        data: [
          {
            artifact_id: "artifact_e2e_summary",
            run_id: runId,
            session_id: "session_fixture",
            user_id: "local-e2e",
            kind: "report",
            title: "Agent 回复摘要",
            preview_text: "AIASK_OK",
            status: "completed",
            created_at: "2026-05-21T08:00:03.000Z"
          }
        ]
      });
    }
    const runSourcesMatch = path.match(/^\/v1\/runs\/([^/]+)\/sources$/);
    if (runSourcesMatch) {
      const runId = decodeURIComponent(runSourcesMatch[1]);
      return fulfillJson(route, {
        object: "list",
        run_id: runId,
        data: [
          {
            source_id: "source_e2e_run",
            run_id: runId,
            session_id: "session_fixture",
            user_id: "local-e2e",
            provider: "e2e",
            source_type: "fixture",
            title: "E2E run source",
            excerpt: "Mock source for run evidence.",
            source_tier: "fixture",
            credibility_score: 1,
            created_at: "2026-05-21T08:00:03.000Z"
          }
        ]
      });
    }
    const sessionArtifactsMatch = path.match(/^\/v1\/sessions\/([^/]+)\/artifacts$/);
    if (sessionArtifactsMatch) {
      const sessionId = decodeURIComponent(sessionArtifactsMatch[1]);
      return fulfillJson(route, {
        object: "list",
        session_id: sessionId,
        data: [
          {
            artifact_id: "artifact_e2e_session",
            session_id: sessionId,
            user_id: "local-e2e",
            kind: "note",
            title: "Session fixture artifact",
            preview_text: "AIASK_OK session artifact",
            status: "completed",
            created_at: "2026-05-21T08:00:03.000Z"
          }
        ]
      });
    }
    const sessionSourcesMatch = path.match(/^\/v1\/sessions\/([^/]+)\/sources$/);
    if (sessionSourcesMatch) {
      const sessionId = decodeURIComponent(sessionSourcesMatch[1]);
      return fulfillJson(route, {
        object: "list",
        session_id: sessionId,
        data: [
          {
            source_id: "source_e2e_session",
            session_id: sessionId,
            user_id: "local-e2e",
            provider: "e2e",
            source_type: "fixture",
            title: "E2E session source",
            excerpt: "Mock source for session evidence.",
            source_tier: "fixture",
            credibility_score: 1,
            created_at: "2026-05-21T08:00:03.000Z"
          }
        ]
      });
    }
    if (path === "/v1/jobs") {
      if (request.method() === "POST") {
        return fulfillJson(route, {
          object: "aiask.job",
          job_id: "job_e2e_created",
          status: "created",
          enabled: true,
          name: "每日研究监控"
        });
      }
      return fulfillJson(route, jobsPayload());
    }
    if (path.match(/^\/v1\/jobs\/[^/]+\/run$/)) {
      return fulfillJson(route, {
        success: true,
        data: { job_id: "job_e2e_research", run_id: "run_job_e2e", status: "completed", output_text: "job ok" },
        error: null,
        error_code: null
      });
    }
    if (path.match(/^\/v1\/jobs\/[^/]+\/runs$/)) {
      return fulfillJson(route, {
        object: "list",
        data: [
          {
            run_id: "run_job_e2e",
            job_id: "job_e2e_research",
            status: "completed",
            started_at: "2026-05-21T07:30:00.000Z",
            finished_at: "2026-05-21T07:30:03.000Z",
            duration_ms: 3000,
            output_text: "job ok"
          }
        ]
      });
    }
    if (path.match(/^\/v1\/jobs\/[^/]+$/)) {
      if (request.method() === "DELETE") return fulfillJson(route, { object: "aiask.job", job_id: "job_e2e_research", status: "deleted" });
      return fulfillJson(route, { object: "aiask.job", job_id: "job_e2e_research", status: "updated", enabled: false });
    }
    if (path === "/intents") {
      if (request.method() === "GET") {
        return fulfillJson(route, {
          object: "list",
          data: [
            {
              ...intentEnvelope("data_sync.run_once").data.intent,
              action: "data_sync.run_once"
            }
          ]
        });
      }
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, intentEnvelope(String(body.action || "desktop.intent")));
    }
    if (path.match(/^\/intents\/[^/]+$/)) {
      return fulfillJson(route, intentEnvelope("desktop.intent"));
    }
    if (path.match(/^\/intents\/[^/]+\/(confirm|deny)$/)) {
      const action = path.endsWith("/confirm") ? "confirmed" : "denied";
      return fulfillJson(route, {
        success: true,
        data: { intent: { ...intentEnvelope("desktop.intent").data.intent, status: action } },
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_incubation_factory_status") {
      return fulfillJson(route, incubationStatusEnvelope());
    }
    if (path === "/v1/desktop/trade-predictions/status") {
      return fulfillJson(route, tradePredictionEnvelope(tradePredictionStatus(queryRecord(url.searchParams))));
    }
    if (path === "/v1/desktop/trade-predictions/outcomes") {
      return fulfillJson(route, tradePredictionEnvelope(tradePredictionOutcomes(queryRecord(url.searchParams))));
    }
    if (path === "/v1/desktop/trade-predictions/matrix") {
      return fulfillJson(route, tradePredictionEnvelope(tradePredictionMatrix(queryRecord(url.searchParams))));
    }
    if (path === "/v1/tools/agent_market_temperature_snapshot") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, { success: true, data: marketTemperatureSnapshotPayload(body), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_market_temperature_cache_readiness") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, { success: true, data: marketTemperatureCacheReadinessPayload(body), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_market_temperature_cache_history") {
      return fulfillJson(route, { success: true, data: marketTemperatureCacheHistoryPayload(), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_market_temperature_industry_history") {
      return fulfillJson(route, { success: true, data: marketTemperatureIndustryHistoryPayload(), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_market_temperature_industry_constituents") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, { success: true, data: marketTemperatureIndustryConstituentsPayload(body), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_market_temperature_forward_validation") {
      return fulfillJson(route, { success: true, data: marketTemperatureForwardValidationPayload(), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_strategy_domain_events") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, strategyEventsEnvelope(typeof body.event_type === "string" ? body.event_type : null));
    }
    if (path === "/v1/tools/agent_factory_event_list") {
      return fulfillJson(route, { success: true, data: factoryEventListPayload(), error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_factory_event_preview_tasks") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        success: true,
        data: factoryEventPreviewTasksPayload(String(body.event_id || "evt_e2e_001")),
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_factory_event_lineage") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        success: true,
        data: factoryEventLineagePayload(String(body.event_id || "evt_e2e_001")),
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_factory_theme_exposure_status") {
      return fulfillJson(route, {
        success: true,
        data: { row_count: 42, symbol_count: 12, theme_count: 3, latest_updated_at: "2026-06-08T14:24:00+08:00" },
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_factory_event_outbox_status") {
      return fulfillJson(route, {
        success: true,
        data: { counts: { processed: 2, failed: 0 }, latest: [] },
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_quant_data_gate") {
      return fulfillJson(route, { success: true, data: { status: "partial", missing: ["000858"], stale: ["000001"] }, error: null, error_code: null });
    }
    if (path === "/v1/tools/agent_web_search") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, {
        success: true,
        data: {
          provider: body.provider || "duckduckgo",
          results: [
            { title: "AIASK data source guide", url: "https://example.test/aiask-data-source", snippet: "Mock search result for E2E." },
            { title: "Market data connectivity", url: "https://example.test/market-data", snippet: "Connectivity check passed." }
          ],
          query: body.query || "AIASK"
        },
        error: null,
        error_code: null
      });
    }
    if (path === "/v1/tools/agent_memory_search") {
      return fulfillJson(route, { success: true, data: [{ kind: "memory", content: "mock memory hit" }], error: null, error_code: null });
    }
    if (path === "/v1/hermes/sessions") {
      return fulfillJson(route, { object: "list", data: [{ session_id: "session_fixture", title: "E2E session", user_id: "local-e2e", updated_at: "2026-05-21T08:00:00.000Z" }] });
    }
    if (path.match(/^\/v1\/sessions\/[^/]+\/messages$/)) {
      return fulfillJson(route, { object: "list", data: [{ role: "assistant", content: "AIASK_OK" }] });
    }
    if (path === "/v1/search") {
      return fulfillJson(route, { object: "list", data: [{ kind: "response", object_id: "resp_fixture", session_id: "session_fixture", user_id: "local-e2e", content: "AIASK_OK search result" }] });
    }
    if (path === "/v1/webhooks") {
      if (request.method() === "POST") {
        const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
        const created = {
          webhook_id: "webhook_fixture_created",
          name: String(body.name || "Created Webhook"),
          events: Array.isArray(body.events) ? body.events : ["MCP UI smoke test"],
          prompt: String(body.prompt || ""),
          enabled: true,
          status: "ready"
        };
        webhookSubscriptions = [created, ...webhookSubscriptions];
        return fulfillJson(route, { object: "webhook", data: created });
      }
      return fulfillJson(route, { object: "list", data: webhookSubscriptions });
    }
    const webhookMatch = path.match(/^\/v1\/webhooks\/([^/]+)$/);
    if (webhookMatch && request.method() === "DELETE") {
      const webhookId = decodeURIComponent(webhookMatch[1]);
      webhookSubscriptions = webhookSubscriptions.filter((item) => item.webhook_id !== webhookId);
      return fulfillJson(route, { object: "webhook.deleted", deleted: true, webhook_id: webhookId });
    }
    if (path === "/v1/approvals") {
      return fulfillJson(route, { data: [intentEnvelope("desktop.intent").data.intent] });
    }
    if (path === "/v1/gateway/status") {
      return fulfillJson(route, { object: "aiask.gateway_status", status: "ready", configured: true, updated_at: "2026-05-21T08:00:00.000Z" });
    }
    if (path === "/v1/gateway/daemon/status") {
      return fulfillJson(route, { object: "aiask.gateway_daemon_status", data: { enabled: true, running: true, listeners: { local: "running" } } });
    }
    if (path === "/v1/gateway/platforms") {
      return fulfillJson(route, { object: "list", data: [{ platform: "local", status: "ready", enabled: true, configured: true }] });
    }
    if (path === "/v1/gateway/messages") {
      return fulfillJson(route, {
        object: "list",
        data: [
          {
            message_id: "gateway_msg_failed",
            platform: "local",
            target: "ops",
            status: "failed",
            content: "mock failed gateway message",
            error_message: "mock delivery failed",
            retry_count: 1,
            created_at: "2026-05-21T08:00:00.000Z"
          }
        ]
      });
    }
    if (path === "/v1/gateway/directory") {
      return fulfillJson(route, { object: "list", data: [{ platform: "local", kind: "channel", target: "ops", updated_at: "2026-05-21T08:00:00.000Z" }] });
    }
    if (path === "/v1/gateway/directory/refresh") {
      return fulfillJson(route, { object: "aiask.gateway_directory_refresh", success: true, data: { refreshed: true } });
    }
    if (path.match(/^\/v1\/gateway\/messages\/[^/]+\/retry$/)) {
      return fulfillJson(route, { object: "aiask.gateway_retry", success: true, data: { retried: true } });
    }
    if (path.match(/^\/v1\/gateway\/platforms\/[^/]+\/(start|stop)$/)) {
      return fulfillJson(route, { object: "aiask.gateway_platform_action", success: true, data: { status: "ok" } });
    }
    if (path.match(/^\/v1\/gateway\/platforms\/[^/]+\/health$/)) {
      return fulfillJson(route, { object: "aiask.gateway_platform_health", success: true, data: { status: "ready" } });
    }
    if (path === "/v1/terminal/backends") {
      return fulfillJson(route, {
        object: "list",
        data: [{ name: "local-powershell", shell: "powershell", status: "ready", read_only_probe: true }]
      });
    }
    if (path === "/v1/terminal/sessions") {
      return fulfillJson(route, {
        object: "list",
        data: [{ session_id: "terminal_fixture", backend: "local-powershell", status: "idle", user_id: "local-e2e" }]
      });
    }
    const terminalBackendSessionsMatch = path.match(/^\/v1\/terminal\/backends\/([^/]+)\/sessions$/);
    if (terminalBackendSessionsMatch) {
      const backend = decodeURIComponent(terminalBackendSessionsMatch[1]);
      return fulfillJson(route, {
        object: "list",
        backend,
        data: [{ session_id: "terminal_fixture", backend, status: "idle", user_id: "local-e2e" }]
      });
    }
    if (path === "/v1/learning/status") {
      return fulfillJson(route, { status: "ready" });
    }
    if (path === "/v1/learning/review") {
      return fulfillJson(route, { object: "list", data: [{ proposal_id: "learn_fixture", status: "pending_review", title: "Mock 学习建议", summary: "Apply a safer prompt." }] });
    }
    if (path === "/v1/learning/apply") {
      const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
      return fulfillJson(route, { object: "learning.proposal", data: { proposal_id: body.proposal_id || "learn_fixture", status: "applied" } });
    }
    if (path === "/v1/rl/environments") {
      return fulfillJson(route, { object: "list", data: { environments: [{ id: "finance_safe_eval", status: "ready" }], default: "finance_safe_eval" } });
    }
    if (path === "/v1/rl/config") {
      if (request.method() === "PATCH") return fulfillJson(route, { object: "aiask.rl_config", data: { status: "updated" } });
      return fulfillJson(route, { object: "aiask.rl_config", data: { provider: "mock", max_steps: 10, status: "configured" }, secrets_redacted: true });
    }
    if (path === "/v1/rl/runs") {
      if (request.method() === "POST") return fulfillJson(route, { object: "rl.run", data: { run_id: "rl_fixture_new", environment: "finance_safe_eval", status: "running" } });
      return fulfillJson(route, { object: "list", data: [{ run_id: "rl_fixture", environment: "finance_safe_eval", status: "dry_run_ready" }] });
    }
    const rlRunMatch = path.match(/^\/v1\/rl\/runs\/([^/]+)(?:\/(stop|results|logs))?$/);
    if (rlRunMatch) {
      const runId = decodeURIComponent(rlRunMatch[1]);
      const action = rlRunMatch[2];
      if (action === "stop") return fulfillJson(route, { object: "rl.stop", data: { run_id: runId, status: "stopped" } });
      if (action === "results") return fulfillJson(route, { object: "rl.results", data: { run_id: runId, metrics: { reward: 1 } } });
      if (action === "logs") return fulfillJson(route, { object: "rl.logs", data: { run_id: runId, lines: ["mock rl log"] } });
      return fulfillJson(route, { object: "rl.run", data: { run_id: runId, environment: "finance_safe_eval", status: "dry_run_ready" } });
    }
    return fulfillJson(route, { error: `Unhandled fixture route: ${path}` }, 500);
  });
}
