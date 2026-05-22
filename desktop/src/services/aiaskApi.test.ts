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
        profile: { user_id: "local", profile_name: "Local Operator" },
        secrets_redacted: true
      });
    }
    if (url.includes("/v1/desktop/data/status")) {
      return jsonResponse({ object: "aiask.desktop_data_status", status: "ready", codes: ["600519"], missing_count: 0, stale_count: 0 });
    }
    if (url.includes("/v1/desktop/data/sync-plan")) {
      return jsonResponse({ object: "aiask.desktop_data_sync_plan", status: "ready", intent_request: { action: "data_sync.sync", params: {} } });
    }
    if (url.includes("/v1/desktop/users/local-profile")) {
      return jsonResponse({ object: "aiask.local_profile", user_id: "local", profile_name: "Local Operator" });
    }
    if (url.includes("/v1/desktop/factor-factory/status")) {
      return jsonResponse({ object: "aiask.desktop.factor_factory_status", status: "ready", active_factors: [] });
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
    await api.dataStatus({ codes: ["600519", "000001"], max_stale_days: 3 });
    await api.dataSyncPlan({ codes: ["600519"], task_type: "kline" });
    await api.localProfileGet();
    await api.localProfileSave({ user_id: "local", profile_name: "Local Operator" });
    await api.factorFactoryStatus(7);
    await api.connectorsSummary();

    expect(calls.map((call) => call.url)).toEqual([
      "http://127.0.0.1:8767/v1/desktop/settings/status",
      "http://127.0.0.1:8767/v1/desktop/data/status?codes=600519%2C000001&max_stale_days=3",
      "http://127.0.0.1:8767/v1/desktop/data/sync-plan",
      "http://127.0.0.1:8767/v1/desktop/users/local-profile",
      "http://127.0.0.1:8767/v1/desktop/users/local-profile",
      "http://127.0.0.1:8767/v1/desktop/factor-factory/status?limit=7",
      "http://127.0.0.1:8767/v1/connectors/summary"
    ]);
    expect(calls[0].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(calls[1].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer api-token" }));
    expect(calls[2].init.method).toBe("POST");
    expect(requestBody(calls[2])).toEqual({ codes: ["600519"], task_type: "kline" });
    expect(calls[4].init.method).toBe("PATCH");
    expect(calls[6].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
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
});
