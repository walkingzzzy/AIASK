import { afterEach, describe, expect, it, vi } from "vitest";
import { AiaskApi } from "./aiaskApi";

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

function mockFetch() {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init: init || {} });
    if (url.includes("/v1/desktop/settings/status")) {
      return jsonResponse({
        object: "aiask.desktop_settings_status",
        llm: { providers: { configured: true } },
        memory: { default_provider: "sqlite" },
        databases: {},
        profile: { user_id: "local", profile_name: "本地操作者" },
        secrets_redacted: true
      });
    }
    if (url.includes("/v1/ai/config")) {
      return jsonResponse({
        object: "aiask.ai_config",
        status: "ready",
        current: { provider: "openai", model: "gpt-4.1-mini", api_key_configured: true, base_url_configured: true, mock: false, configured: true, secrets_redacted: true },
        editable: { provider_env: "AIASK_AGENT_MODEL_PROVIDER", model_env: "AIASK_AGENT_MODEL", base_url_env: "OPENAI_BASE_URL", api_key_env: "OPENAI_API_KEY", env_file: ".env", env_source: "project_root" },
        presets: [{ id: "openai", label: "OpenAI", provider: "openai", default_model: "gpt-4.1-mini", base_url: "https://api.openai.com/v1" }],
        secrets_redacted: true
      });
    }
    if (url.includes("/v1/desktop/data/status")) {
      return jsonResponse({ object: "aiask.desktop_data_status", status: "ready", codes: ["600519"], missing_count: 0, stale_count: 0 });
    }
    if (url.includes("/v1/desktop/data/sync-plan")) {
      return jsonResponse({ object: "aiask.desktop_data_sync_plan", status: "ready", intent_request: { action: "data_sync.sync", params: {} } });
    }
    if (url.includes("/v1/desktop/stock-data-sources/test")) {
      return jsonResponse({ object: "aiask.stock_data_source_test", provider: "tavily", mode: "connectivity", success: true, status: "ready", secrets_redacted: true });
    }
    if (url.includes("/v1/desktop/stock-data-sources")) {
      return jsonResponse({
        object: "aiask.stock_data_sources",
        status: "ready",
        configured_count: 1,
        ready_count: 1,
        presets: [],
        sources: [],
        secrets_redacted: true
      });
    }
    if (url.includes("/v1/runs/run%201/artifacts")) {
      return jsonResponse({
        object: "list",
        run_id: "run 1",
        data: [{ artifact_id: "art_1", kind: "quote_snapshot", title: "Quote", status: "ready" }]
      });
    }
    if (url.includes("/v1/runs/run%201/sources")) {
      return jsonResponse({
        object: "list",
        run_id: "run 1",
        data: [{ source_id: "src_1", source_type: "news", title: "News", url: "https://example.com/news" }]
      });
    }
    if (url.includes("/v1/sessions/sess%201/artifacts")) {
      return jsonResponse({
        object: "list",
        session_id: "sess 1",
        data: [{ artifact_id: "art_2", kind: "script", title: "Script", status: "ready" }]
      });
    }
    if (url.includes("/v1/sessions/sess%201/sources")) {
      return jsonResponse({
        object: "list",
        session_id: "sess 1",
        data: [{ source_id: "src_2", source_type: "market_quote", provider: "sina" }]
      });
    }
    if (url.includes("/v1/tools/agent_quant_data_gate")) {
      return jsonResponse({ success: true, data: { status: "passed", missing: [], stale: [] }, error: null });
    }
    if (url.includes("/v1/tools/agent_market_temperature_snapshot")) {
      return jsonResponse({
        success: true,
        data: {
          contract_version: "market_temperature.v1",
          as_of: "2026-06-08",
          market: { stock_count: 3, temperature: 55.8, state: "neutral" },
          hot_industries: [],
          cold_industries: [],
          industries: [],
          quality: { status: "healthy", warnings: [] }
        },
        error: null
      });
    }
    if (url.includes("/v1/tools/agent_market_temperature_cache_readiness")) {
      return jsonResponse({
        success: true,
        data: {
          ready: true,
          status: "fresh",
          read_only: true,
          as_of: "2026-06-08",
          max_stale_days: 2,
          staleness_days: 1,
          blockers: []
        },
        error: null
      });
    }
    if (url.includes("/v1/tools/agent_market_temperature_cache_history")) {
      return jsonResponse({
        success: true,
        data: {
          items: [{ as_of: "2026-06-08", market_temperature: 55.5, quality_status: "healthy" }],
          count: 1,
          limit: 5,
          include_snapshot: false
        },
        error: null
      });
    }
    if (url.includes("/v1/tools/agent_market_temperature_industry_history")) {
      return jsonResponse({
        success: true,
        data: {
          items: [{ as_of: "2026-06-08", name: "bank", temperature: 60.0, quality_status: "healthy" }],
          count: 1,
          limit: 5,
          industry: "bank"
        },
        error: null
      });
    }
    if (url.includes("/v1/desktop/users/local-profile")) {
      return jsonResponse({ object: "aiask.local_profile", user_id: "local", profile_name: "本地操作者" });
    }
    if (url.includes("/v1/desktop/events")) {
      return jsonResponse({ object: "list", data: [{ event_type: "page_view" }], count: 1, secrets_redacted: true });
    }
    if (url.includes("/v1/desktop/feedback")) {
      return jsonResponse({ object: "aiask.feedback_event", data: { feedback_type: "thumbs_up" }, secrets_redacted: true });
    }
    if (url.includes("/v1/desktop/users/local/activity")) {
      return jsonResponse({
        object: "aiask.user_activity",
        user_id: "local",
        sessions: [],
        runs: [],
        events: [{ event_type: "page_view" }],
        tool_invocations: [],
        feedback: [],
        policy: {
          user_id: "local",
          event_ttl_days: 90,
          audit_ttl_days: 180,
          run_event_ttl_days: 180,
          tool_payload_ttl_days: 90,
          conversation_retention: "keep_until_user_deletes",
          allow_product_analytics: true,
          allow_learning: false
        },
        secrets_redacted: true
      });
    }
    if (url.includes("/v1/desktop/analytics/summary")) {
      return jsonResponse({
        object: "aiask.analytics_summary",
        scope: "user",
        user_id: "local",
        totals: { events: 1, tool_invocations: 1, feedback: 1 },
        events_by_type: [{ event_type: "page_view", count: 1 }],
        pages: [{ page_key: "workbench", count: 1 }],
        tools: [{ tool_name: "agent_tool_catalog", count: 1, succeeded: 1, failed: 0, failure_rate: 0, avg_duration_ms: 5 }],
        feedback: [{ target_type: "page", feedback_type: "thumbs_up", count: 1, avg_rating: 5 }],
        secrets_redacted: true
      });
    }
    if (url.includes("/v1/desktop/users/local/export")) {
      return jsonResponse({
        object: "aiask.user_data_export",
        user_id: "local",
        exported_at: "2026-06-12T00:00:00Z",
        profile_policy: {
          user_id: "local",
          event_ttl_days: 30,
          audit_ttl_days: 180,
          run_event_ttl_days: 180,
          tool_payload_ttl_days: 90,
          conversation_retention: "keep_until_user_deletes",
          allow_product_analytics: true,
          allow_learning: true
        },
        sessions: [],
        messages: [],
        runs: [],
        run_events: [],
        activity_events: [],
        tool_invocations: [],
        feedback: [],
        analytics: { object: "aiask.analytics_summary", scope: "user", user_id: "local", totals: { events: 0, tool_invocations: 0, feedback: 0 }, events_by_type: [], pages: [], tools: [], feedback: [], secrets_redacted: true },
        secrets_redacted: true
      });
    }
    if (url.includes("/v1/desktop/users/local/delete")) {
      return jsonResponse({
        object: "aiask.user_data_delete",
        user_id: "local",
        dry_run: true,
        hard_delete: false,
        anonymized_user_id: "deleted:local",
        counts: { sessions: 1, messages: 2, responses: 0, runs: 1, run_events: 1, activity_events: 1, tool_invocations: 1, feedback: 1, sources: 0, artifacts: 0, search_rows: 0 },
        secrets_redacted: true
      });
    }
    if (url.includes("/v1/desktop/retention/sweep")) {
      return jsonResponse({
        object: "aiask.retention_sweep",
        dry_run: true,
        user_id: "local",
        counts: { user_activity_events: 0, tool_invocations_payloads: 0, run_events: 0, feedback_events: 0, messages: 0 },
        tables: ["user_activity_events", "tool_invocations_payloads", "run_events", "feedback_events", "messages"],
        market_data_affected: false,
        secrets_redacted: true
      });
    }
    if (url.includes("/v1/desktop/users/local/learning-dataset")) {
      return jsonResponse({ object: "aiask.learning_dataset", user_id: "local", allowed: true, items: [{ feedback_type: "thumbs_up" }], count: 1, secrets_redacted: true });
    }
    if (url.includes("/v1/desktop/users/local/recommendations")) {
      return jsonResponse({ object: "aiask.workflow_recommendations", user_id: "local", data_source: "local_user_activity", data: [{ id: "feedback:collect" }], count: 1, secrets_redacted: true });
    }
    if (url.includes("/v1/desktop/users/local/data-policy")) {
      return jsonResponse({
        object: "aiask.user_data_policy",
        data: {
          user_id: "local",
          event_ttl_days: 30,
          audit_ttl_days: 180,
          run_event_ttl_days: 180,
          tool_payload_ttl_days: 90,
          conversation_retention: "keep_until_user_deletes",
          allow_product_analytics: true,
          allow_learning: true
        }
      });
    }
    if (url.includes("/v1/desktop/factor-factory/status")) {
      return jsonResponse({ object: "aiask.desktop.factor_factory_status", status: "ready", active_factors: [] });
    }
    if (url.includes("/v1/desktop/trade-predictions/status")) {
      return jsonResponse({ success: true, data: { object: "trade_prediction.status", status: "ready", prediction_count: 1 }, error: null });
    }
    if (url.includes("/v1/desktop/trade-predictions/outcomes")) {
      return jsonResponse({ success: true, data: { object: "trade_prediction.outcomes", items: [], count: 0 }, error: null });
    }
    if (url.includes("/v1/desktop/trade-predictions/matrix")) {
      return jsonResponse({ success: true, data: { object: "trade_prediction.matrix", rows: [], row_count: 0 }, error: null });
    }
    if (url.includes("/intents")) {
      return jsonResponse({ success: true, data: { intent: { intent_id: "intent_1" } }, error: null });
    }
    if (url.includes("/v1/jobs/job%201/run")) {
      return jsonResponse({ success: true, data: { run_id: "run_1" }, error: null });
    }
    if (url.includes("/v1/jobs")) {
      return jsonResponse({ object: "list", data: [] });
    }
    if (url.includes("/v1/connectors/summary")) {
      return jsonResponse({ object: "connector.summary", data: { connectors: [] } });
    }
    return jsonResponse({ object: "ok" });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

function requestBody(call: { init: RequestInit }): Record<string, unknown> {
  return JSON.parse(String(call.init.body || "{}")) as Record<string, unknown>;
}

describe("AiaskApi desktop contract", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses desktop settings, data, profile, and factor factory endpoints", async () => {
    const { calls } = mockFetch();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767/", apiToken: "api-token", controlToken: "control-token" });

    await api.settingsStatus();
    await api.modelProviderStatus();
    await api.memoryStatus();
    await api.aiConfig();
    await api.aiConfigSave({ preset: "openai", provider: "openai", model: "gpt-4.1-mini", base_url: "https://api.openai.com/v1", api_key: "sk-test" });
    await api.dataStatus({ codes: ["600519", "000001"], max_stale_days: 3 });
    await api.dataGate({ codes: ["600519"], max_stale_days: 3 });
    await api.dataSyncPlan({ codes: ["600519"], task_type: "kline" });
    await api.stockDataSources();
    await api.stockDataSourceSave({ provider: "tavily", name: "Tavily", api_key: "tvly-test" });
    await api.stockDataSourceTest({ provider: "tavily", mode: "connectivity" });
    await api.localProfileGet();
    await api.localProfileSave({ user_id: "local", profile_name: "本地操作者" });
    await api.factorFactoryStatus(7);
    await api.connectorsSummary();

    expect(calls.map((call) => call.url)).toEqual([
      "http://127.0.0.1:8767/v1/desktop/settings/status",
      "http://127.0.0.1:8767/v1/desktop/settings/status",
      "http://127.0.0.1:8767/v1/desktop/settings/status",
      "http://127.0.0.1:8767/v1/ai/config",
      "http://127.0.0.1:8767/v1/ai/config",
      "http://127.0.0.1:8767/v1/desktop/data/status?codes=600519%2C000001&max_stale_days=3",
      "http://127.0.0.1:8767/v1/tools/agent_quant_data_gate",
      "http://127.0.0.1:8767/v1/desktop/data/sync-plan",
      "http://127.0.0.1:8767/v1/desktop/stock-data-sources",
      "http://127.0.0.1:8767/v1/desktop/stock-data-sources",
      "http://127.0.0.1:8767/v1/desktop/stock-data-sources/test",
      "http://127.0.0.1:8767/v1/desktop/users/local-profile",
      "http://127.0.0.1:8767/v1/desktop/users/local-profile",
      "http://127.0.0.1:8767/v1/desktop/factor-factory/status?limit=7",
      "http://127.0.0.1:8767/v1/connectors/summary"
    ]);
    expect(calls[0].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(calls[1].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(calls[2].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(calls[3].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(calls[4].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(calls[4].init.method).toBe("PATCH");
    expect(requestBody(calls[4])).toEqual({ preset: "openai", provider: "openai", model: "gpt-4.1-mini", base_url: "https://api.openai.com/v1", api_key: "sk-test" });
    expect(calls[5].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(calls[6].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(calls[6].init.method).toBe("POST");
    expect(requestBody(calls[6])).toEqual({ codes: ["600519"], max_stale_days: 3 });
    expect(calls[7].init.method).toBe("POST");
    expect(requestBody(calls[7])).toEqual({ codes: ["600519"], task_type: "kline" });
    expect(calls[8].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(calls[9].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(calls[9].init.method).toBe("POST");
    expect(requestBody(calls[9])).toEqual({ provider: "tavily", name: "Tavily", api_key: "tvly-test" });
    expect(calls[10].init.method).toBe("POST");
    expect(requestBody(calls[10])).toEqual({ provider: "tavily", mode: "connectivity" });
    expect(calls[12].init.method).toBe("PATCH");
    expect(calls[14].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
  });

  it("uses user activity, feedback, and data policy endpoints", async () => {
    const { calls } = mockFetch();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767/", apiToken: "api-token", controlToken: "control-token" });

    await api.recordEvents({ user_id: "local", event_type: "page_view", page_key: "workbench" });
    await api.recordFeedback({ user_id: "local", target_type: "page", target_id: "workbench", feedback_type: "thumbs_up" });
    await api.userActivity("local", 10);
    await api.userAnalyticsSummary("local", 10);
    await api.userDataExport("local", 25);
    await api.userDataDelete("local", { dry_run: true, reason: "preview" });
    await api.retentionSweep({ user_id: "local", dry_run: true });
    await api.userLearningDataset("local", 10);
    await api.userRecommendations("local", 5);
    await api.userDataPolicyGet("local");
    await api.userDataPolicySave("local", { event_ttl_days: 30, allow_learning: true });

    expect(calls.map((call) => [call.init.method || "GET", call.url])).toEqual([
      ["POST", "http://127.0.0.1:8767/v1/desktop/events"],
      ["POST", "http://127.0.0.1:8767/v1/desktop/feedback"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/users/local/activity?limit=10"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/analytics/summary?user_id=local&limit=10"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/users/local/export?limit=25"],
      ["POST", "http://127.0.0.1:8767/v1/desktop/users/local/delete"],
      ["POST", "http://127.0.0.1:8767/v1/desktop/retention/sweep"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/users/local/learning-dataset?limit=10"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/users/local/recommendations?limit=5"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/users/local/data-policy"],
      ["PATCH", "http://127.0.0.1:8767/v1/desktop/users/local/data-policy"]
    ]);
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe("Bearer api-token");
    expect((calls[1].init.headers as Record<string, string>).Authorization).toBe("Bearer api-token");
    expect((calls[2].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[3].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[4].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[5].init.headers as Record<string, string>).Authorization).toBe("Bearer api-token");
    expect((calls[6].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[7].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[8].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[9].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[10].init.headers as Record<string, string>).Authorization).toBe("Bearer api-token");
    expect(requestBody(calls[0])).toEqual({ events: [{ user_id: "local", event_type: "page_view", page_key: "workbench" }] });
    expect(requestBody(calls[1])).toEqual({ user_id: "local", target_type: "page", target_id: "workbench", feedback_type: "thumbs_up" });
    expect(requestBody(calls[5])).toEqual({ dry_run: true, reason: "preview" });
    expect(requestBody(calls[6])).toEqual({ user_id: "local", dry_run: true });
    expect(requestBody(calls[10])).toEqual({ event_ttl_days: 30, allow_learning: true });
  });

  it("uses durable artifact and source endpoints for runs and sessions", async () => {
    const { calls } = mockFetch();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767/", apiToken: "api-token", controlToken: "control-token" });

    const runArtifacts = await api.runArtifacts("run 1", { kind: "quote_snapshot", limit: 10 });
    const runSources = await api.runSources("run 1", { source_type: "news", limit: 5 });
    const sessionArtifacts = await api.sessionArtifacts("sess 1", { kind: "script", limit: 3 });
    const sessionSources = await api.sessionSources("sess 1", { source_type: "market_quote", limit: 2 });

    expect(runArtifacts.data[0].artifact_id).toBe("art_1");
    expect(runSources.data[0].source_id).toBe("src_1");
    expect(sessionArtifacts.data[0].artifact_id).toBe("art_2");
    expect(sessionSources.data[0].source_id).toBe("src_2");
    expect(calls.map((call) => [call.init.method || "GET", call.url])).toEqual([
      ["GET", "http://127.0.0.1:8767/v1/runs/run%201/artifacts?kind=quote_snapshot&limit=10"],
      ["GET", "http://127.0.0.1:8767/v1/runs/run%201/sources?source_type=news&limit=5"],
      ["GET", "http://127.0.0.1:8767/v1/sessions/sess%201/artifacts?kind=script&limit=3"],
      ["GET", "http://127.0.0.1:8767/v1/sessions/sess%201/sources?source_type=market_quote&limit=2"]
    ]);
    expect(calls[0].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(calls[1].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(calls[2].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(calls[3].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
  });

  it("uses readonly desktop trade prediction endpoints", async () => {
    const { calls } = mockFetch();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767/", apiToken: "api-token", controlToken: "control-token" });

    await api.tradePredictionStatus({ strategy_id: "strategy_1", stock_code: "600519", limit: 5 });
    await api.tradePredictionOutcomes({
      score_version: "trade_prediction_score_v2",
      score_status: "partial_intraday_missing",
      data_quality_status: "intraday_missing",
      limit: 12
    });
    await api.tradePredictionMatrix({ dimensions: ["family", "regime"], limit: 20 });

    expect(calls.map((call) => [call.init.method || "GET", call.url])).toEqual([
      ["GET", "http://127.0.0.1:8767/v1/desktop/trade-predictions/status?strategy_id=strategy_1&stock_code=600519&limit=5"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/trade-predictions/outcomes?score_version=trade_prediction_score_v2&score_status=partial_intraday_missing&data_quality_status=intraday_missing&limit=12"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/trade-predictions/matrix?dimensions=family%2Cregime&limit=20"]
    ]);
    expect(calls.every((call) => (call.init.headers as Record<string, string>).Authorization === "Bearer api-token")).toBe(true);
  });

  it("uses the read-only market temperature agent tools", async () => {
    const { calls } = mockFetch();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767/", apiToken: "api-token", controlToken: "control-token" });

    await api.marketTemperatureSnapshot({ limit: 300, top_n: 8, min_bars: 20, as_of: "2026-06-08" });
    await api.marketTemperatureCacheReadiness({ as_of: "2026-06-08", max_stale_days: 2 });
    await api.marketTemperatureCacheHistory({ limit: 5, include_snapshot: false });
    await api.marketTemperatureIndustryHistory({ industry: "bank", limit: 5, top_n: 3 });
    await api.marketTemperatureIndustryConstituents({ industry: "bank", limit: 20, offset: 0 });
    await api.marketTemperatureForwardValidation({
      limit: 30,
      horizons: [1, 3],
      target_field: "benchmark_return",
      benchmark_code: "000300"
    });

    expect(calls.map((call) => [call.init.method || "GET", call.url])).toEqual([
      ["POST", "http://127.0.0.1:8767/v1/tools/agent_market_temperature_snapshot"],
      ["POST", "http://127.0.0.1:8767/v1/tools/agent_market_temperature_cache_readiness"],
      ["POST", "http://127.0.0.1:8767/v1/tools/agent_market_temperature_cache_history"],
      ["POST", "http://127.0.0.1:8767/v1/tools/agent_market_temperature_industry_history"],
      ["POST", "http://127.0.0.1:8767/v1/tools/agent_market_temperature_industry_constituents"],
      ["POST", "http://127.0.0.1:8767/v1/tools/agent_market_temperature_forward_validation"]
    ]);
    expect(calls[0].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(requestBody(calls[0])).toEqual({ limit: 300, top_n: 8, min_bars: 20, as_of: "2026-06-08" });
    expect(calls[1].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(requestBody(calls[1])).toEqual({ as_of: "2026-06-08", max_stale_days: 2 });
    expect(calls[2].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(requestBody(calls[2])).toEqual({ limit: 5, include_snapshot: false });
    expect(calls[3].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(requestBody(calls[3])).toEqual({ industry: "bank", limit: 5, top_n: 3 });
    expect(calls[4].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(requestBody(calls[4])).toEqual({ industry: "bank", limit: 20, offset: 0 });
    expect(calls[5].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(requestBody(calls[5])).toEqual({
      limit: 30,
      horizons: [1, 3],
      target_field: "benchmark_return",
      benchmark_code: "000300"
    });
  });

  it("uses approval intents for factory and sync operations", async () => {
    const { calls } = mockFetch();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.factoryIntentCreate("factory_run_once", { execution_mode: "dry_run" }, "Run strategy factory");
    await api.factorFactoryRunIntent({ candidate_count: 1 });
    await api.factorFactoryMaintenanceIntent();

    expect(calls).toHaveLength(3);
    expect(calls.every((call) => call.url === "http://127.0.0.1:8767/intents")).toBe(true);
    expect(calls.every((call) => call.init.method === "POST")).toBe(true);
    expect(calls.every((call) => (call.init.headers as Record<string, string>).Authorization === "Bearer control-token")).toBe(true);
    expect(requestBody(calls[0]).action).toBe("factory_run_once");
    expect(requestBody(calls[1]).action).toBe("factor_factory.run_once");
    expect(requestBody(calls[2]).action).toBe("factor_factory.maintenance");
  });

  it("covers jobs aliases and encoded job routes", async () => {
    const { calls } = mockFetch();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.jobsList();
    await api.jobsCreate({ name: "Daily", prompt: "Review" });
    await api.jobsUpdate("job 1", { enabled: false });
    await api.jobsRun("job 1");
    await api.jobsDelete("job 1");

    expect(calls.map((call) => [call.init.method || "GET", call.url])).toEqual([
      ["GET", "http://127.0.0.1:8767/v1/jobs"],
      ["POST", "http://127.0.0.1:8767/v1/jobs"],
      ["PATCH", "http://127.0.0.1:8767/v1/jobs/job%201"],
      ["POST", "http://127.0.0.1:8767/v1/jobs/job%201/run"],
      ["DELETE", "http://127.0.0.1:8767/v1/jobs/job%201"]
    ]);
    expect(calls.every((call) => (call.init.headers as Record<string, string>).Authorization === "Bearer api-token")).toBe(true);
  });

  it("covers missing frontend v1 run, response, plugin, gateway, approval, rl, and quant routes", async () => {
    const { calls } = mockFetch();
    const api = new AiaskApi({ endpoint: "http://127.0.0.1:8767", apiToken: "api-token", controlToken: "control-token" });

    await api.responseGet("resp 1");
    await api.responseDelete("resp 1");
    await api.runGet("run 1");
    await api.runCancel("run 1");
    await api.runStop("run 1");
    await api.runSteer("run 1", "slow down");
    await api.pluginUpsert({ name: "audit-plugin", enabled: true });
    await api.pluginCommands("audit-plugin");
    await api.pluginCommandTest("audit-plugin", "doctor", { verbose: true });
    await api.gatewayDaemonStatus();
    await api.gatewayMessageRetry("msg 1");
    await api.approvalDecide("approval 1", "deny", "not safe");
    await api.rlRunGet("rl 1");
    await api.rlRunResults("rl 1");
    await api.rlRunLogs("rl 1");
    await api.terminalBackendSessions("local powershell", 7);
    await api.quantResearchGet("qr 1");
    await api.quantResearchReport("qr 1");
    await api.financialManagerCatalog();
    await api.financialManagerStatus();
    await api.financialManagerQuery({ capability_id: "portfolio", action_id: "risk", params: { codes: ["600519"] } });
    await api.financialManagerIntent({ capability_id: "portfolio", action_id: "create", params: { name: "Desk" }, rationale: "review", user_id: "local" });
    await api.brokerReadiness();
    await api.brokerSync({ provider: "qmt", consent: true, user_id: "local" });
    await api.brokerAccounts("local", "qmt");
    await api.brokerPositions("local", "qmt");
    await api.brokerOrders("local", "qmt");
    await api.brokerAnalyticsRun({ user_id: "local", provider: "qmt" });
    await api.brokerAnalyticsLatest("local", "qmt");
    await api.brokerSync({ provider: "tonghuashun", consent: true, user_id: "local" });
    await api.brokerAccounts("local", "tonghuashun");
    await api.brokerAnalyticsLatest("local", "tonghuashun");

    expect(calls.map((call) => [call.init.method || "GET", call.url])).toEqual([
      ["GET", "http://127.0.0.1:8767/v1/responses/resp%201"],
      ["DELETE", "http://127.0.0.1:8767/v1/responses/resp%201"],
      ["GET", "http://127.0.0.1:8767/v1/runs/run%201"],
      ["POST", "http://127.0.0.1:8767/v1/runs/run%201/cancel"],
      ["POST", "http://127.0.0.1:8767/v1/runs/run%201/stop"],
      ["POST", "http://127.0.0.1:8767/v1/runs/run%201/steer"],
      ["POST", "http://127.0.0.1:8767/v1/plugins"],
      ["GET", "http://127.0.0.1:8767/v1/plugins/audit-plugin/commands"],
      ["POST", "http://127.0.0.1:8767/v1/plugins/audit-plugin/commands/doctor/test"],
      ["GET", "http://127.0.0.1:8767/v1/gateway/daemon/status"],
      ["POST", "http://127.0.0.1:8767/v1/gateway/messages/msg%201/retry"],
      ["POST", "http://127.0.0.1:8767/v1/approvals/approval%201/deny"],
      ["GET", "http://127.0.0.1:8767/v1/rl/runs/rl%201"],
      ["GET", "http://127.0.0.1:8767/v1/rl/runs/rl%201/results"],
      ["GET", "http://127.0.0.1:8767/v1/rl/runs/rl%201/logs"],
      ["GET", "http://127.0.0.1:8767/v1/terminal/backends/local%20powershell/sessions?limit=7"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/quant/research-runs/qr%201"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/quant/research-runs/qr%201/report"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/financial-manager/catalog"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/financial-manager/status"],
      ["POST", "http://127.0.0.1:8767/v1/desktop/financial-manager/query"],
      ["POST", "http://127.0.0.1:8767/v1/desktop/financial-manager/intent"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/broker-readiness"],
      ["POST", "http://127.0.0.1:8767/v1/desktop/broker/sync"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/broker/accounts?user_id=local&provider=qmt"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/broker/positions?user_id=local&provider=qmt"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/broker/orders?user_id=local&provider=qmt"],
      ["POST", "http://127.0.0.1:8767/v1/desktop/broker/analytics/run"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/broker/analytics/latest?user_id=local&provider=qmt"],
      ["POST", "http://127.0.0.1:8767/v1/desktop/broker/sync"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/broker/accounts?user_id=local&provider=tonghuashun"],
      ["GET", "http://127.0.0.1:8767/v1/desktop/broker/analytics/latest?user_id=local&provider=tonghuashun"]
    ]);
    expect(requestBody(calls[5])).toEqual({ instruction: "slow down" });
    expect(requestBody(calls[6])).toEqual({ name: "audit-plugin", enabled: true });
    expect(requestBody(calls[8])).toEqual({ verbose: true });
    expect(requestBody(calls[11])).toEqual({ reason: "not safe" });
    expect(requestBody(calls[20])).toEqual({ capability_id: "portfolio", action_id: "risk", params: { codes: ["600519"] } });
    expect(requestBody(calls[21])).toEqual({ capability_id: "portfolio", action_id: "create", params: { name: "Desk" }, rationale: "review", user_id: "local" });
    expect(requestBody(calls[23])).toEqual({ provider: "qmt", consent: true, user_id: "local" });
    expect(requestBody(calls[27])).toEqual({ user_id: "local", provider: "qmt" });
    expect((calls[9].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[15].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[17].init.headers as Record<string, string>).Authorization).toBe("Bearer api-token");
    expect((calls[21].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[22].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((calls[23].init.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
  });
});
