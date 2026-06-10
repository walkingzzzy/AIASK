import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ModelsWorkspace } from "./ModelsWorkspace";

function ok(payload: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })
  );
}

function pathFor(input: RequestInfo | URL) {
  return new URL(String(input)).pathname;
}

describe("ModelsWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("loads model status with one settings request per models request and redacts raw secrets", async () => {
    const settingsPayload = {
      object: "aiask.desktop_settings_status",
      agent: { control_authorized: true },
      llm: {
        ai_status: {
          provider: "aiask_mock",
          model: "mock-live-model",
          configured: true,
          api_key_configured: true,
          base_url_configured: true,
          config_source: { loaded: true, source: "project" },
          secrets_redacted: true
        },
        providers: {
          status: "ready",
          configured_count: 1,
          providers: [
            {
              name: "project-root-api",
              type: "openai_compatible",
              model: "mock-live-model",
              configured: true,
              status: "ready",
              api_key: "sk-provider-secret-value-1234567890"
            }
          ]
        }
      },
      memory: {},
      databases: {},
      profile: { user_id: "local", profile_name: "Local" },
      secrets_redacted: true
    };
    const modelsPayload = {
      object: "list",
      configured: true,
      data: [{ id: "mock-live-model", object: "model", api_key: "sk-model-secret-value-1234567890" }]
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = pathFor(input);
      if (path === "/v1/desktop/settings/status") return ok(settingsPayload);
      if (path === "/v1/ai/models") return ok(modelsPayload);
      return Promise.resolve(new Response(JSON.stringify({ error: path }), { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ModelsWorkspace apiToken="api-token" controlToken="control-token" endpoint="http://127.0.0.1:8767" />);

    await screen.findByText("mock-live-model");
    await screen.findByText("project-root-api");
    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => pathFor(input));
      const settingsCalls = paths.filter((path) => path === "/v1/desktop/settings/status").length;
      const modelsCalls = paths.filter((path) => path === "/v1/ai/models").length;
      expect(settingsCalls).toBe(modelsCalls);
      expect(modelsCalls).toBeGreaterThan(0);
    });

    const settingsCall = fetchMock.mock.calls.find(([input]) => pathFor(input) === "/v1/desktop/settings/status");
    const modelsCall = fetchMock.mock.calls.find(([input]) => pathFor(input) === "/v1/ai/models");
    expect((settingsCall?.[1]?.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((modelsCall?.[1]?.headers as Record<string, string>).Authorization).toBe("Bearer api-token");

    const firstCounts = fetchMock.mock.calls.reduce(
      (counts, [input]) => {
        const path = pathFor(input);
        if (path === "/v1/desktop/settings/status") counts.settings += 1;
        if (path === "/v1/ai/models") counts.models += 1;
        return counts;
      },
      { settings: 0, models: 0 }
    );

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => pathFor(input));
      const settingsCalls = paths.filter((path) => path === "/v1/desktop/settings/status").length;
      const modelsCalls = paths.filter((path) => path === "/v1/ai/models").length;
      expect(settingsCalls).toBeGreaterThan(firstCounts.settings);
      expect(modelsCalls).toBeGreaterThan(firstCounts.models);
      expect(settingsCalls).toBe(modelsCalls);
    });

    const body = document.body.textContent || "";
    expect(body).toContain("[redacted]");
    expect(body).not.toContain("sk-provider-secret-value");
    expect(body).not.toContain("sk-model-secret-value");
  });
});
