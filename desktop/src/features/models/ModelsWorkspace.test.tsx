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

  it("loads model config, saves settings, fetches models, tests smoke, and redacts raw secrets", async () => {
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
          prompt_cache: { enabled: true, requested_enabled: true, supported: true, recent_non_system_messages: 3, secrets_redacted: true },
          config_source: { loaded: true, source: "project" },
          secrets_redacted: true
        },
        providers: {
          status: "ready",
          configured_count: 1,
          prompt_cache: { enabled: true, requested_enabled: true, supported: true, recent_non_system_messages: 3, secrets_redacted: true },
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
    const configPayload = {
      object: "aiask.ai_config",
      status: "ready",
      current: {
        provider: "openai",
        model: "mock-live-model",
        base_url: "http://localhost:8317/v1",
        configured: true,
        api_key_configured: true,
        base_url_configured: true,
        prompt_cache: { enabled: true, requested_enabled: true, supported: true, recent_non_system_messages: 3, secrets_redacted: true },
        mock: false,
        secrets_redacted: true
      },
      editable: {
        provider_env: "AIASK_AGENT_MODEL_PROVIDER",
        model_env: "AIASK_AGENT_MODEL",
        base_url_env: "OPENAI_BASE_URL",
        api_key_env: "OPENAI_API_KEY",
        env_file: ".env",
        env_source: "project_root"
      },
      presets: [
        { id: "openai", label: "OpenAI", provider: "openai", default_model: "mock-live-model", base_url: "http://localhost:8317/v1", api_key_url: "https://platform.openai.com/api-keys", docs_url: "https://platform.openai.com/docs/api-reference/models/list" },
        { id: "deepseek", label: "DeepSeek", provider: "openai", default_model: "deepseek-chat", base_url: "https://api.deepseek.com" },
        { id: "mock", label: "本地 Mock", provider: "mock", default_model: "mock-local", base_url: "" }
      ],
      secrets_redacted: true
    };
    const modelsPayload = {
      object: "list",
      configured: true,
      data: [
        { id: "mock-live-model", object: "model", api_key: "sk-model-secret-value-1234567890" },
        { id: "deepseek-chat", object: "model" }
      ],
      secrets_redacted: true
    };
    const savePayload = {
      object: "aiask.ai_config",
      saved: true,
      provider: "openai",
      model: "mock-live-model",
      base_url_configured: true,
      api_key_configured: true,
      mock: false,
      configured: true,
      prompt_cache: { enabled: true, requested_enabled: true, supported: true, recent_non_system_messages: 3, secrets_redacted: true },
      updated_keys: ["AIASK_AGENT_MODEL"],
      secrets_redacted: true
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = pathFor(input);
      if (path === "/v1/desktop/settings/status") return ok(settingsPayload);
      if (path === "/v1/ai/config" && init?.method === "PATCH") return ok(savePayload);
      if (path === "/v1/ai/config") return ok(configPayload);
      if (path === "/v1/ai/models") return ok(modelsPayload);
      if (path === "/v1/ai/smoke") return ok({ object: "aiask.ai_smoke", configured: true, success: true, model: "mock-live-model", response_preview: "AIASK_MODEL_OK", secrets_redacted: true });
      return Promise.resolve(new Response(JSON.stringify({ error: path }), { status: 404 }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ModelsWorkspace apiToken="api-token" controlToken="control-token" endpoint="http://127.0.0.1:8767" />);

    expect((await screen.findAllByText("mock-live-model")).length).toBeGreaterThan(0);
    expect(screen.getByText("Prompt Cache")).toBeInTheDocument();
    expect(screen.getByText(/已对 system prompt/)).toBeInTheDocument();
    await screen.findByText("project-root-api");
    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => pathFor(input));
      const settingsCalls = paths.filter((path) => path === "/v1/desktop/settings/status").length;
      const modelsCalls = paths.filter((path) => path === "/v1/ai/models").length;
      expect(settingsCalls).toBeGreaterThan(0);
      expect(modelsCalls).toBeGreaterThan(0);
    });

    const settingsCall = fetchMock.mock.calls.find(([input]) => pathFor(input) === "/v1/desktop/settings/status");
    const modelsCall = fetchMock.mock.calls.find(([input]) => pathFor(input) === "/v1/ai/models");
    const configCall = fetchMock.mock.calls.find(([input]) => pathFor(input) === "/v1/ai/config");
    expect((settingsCall?.[1]?.headers as Record<string, string>).Authorization).toBe("Bearer control-token");
    expect((modelsCall?.[1]?.headers as Record<string, string>).Authorization).toBe("Bearer api-token");
    expect((configCall?.[1]?.headers as Record<string, string>).Authorization).toBe("Bearer api-token");

    fireEvent.change(screen.getByLabelText("Search provider presets"), { target: { value: "deep" } });
    expect(screen.getByText("DeepSeek")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search provider presets"), { target: { value: "nomatch" } });
    expect(screen.getByText("No provider presets match the current search.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search provider presets"), { target: { value: "" } });

    fireEvent.change(screen.getByLabelText("Search available models"), { target: { value: "deep" } });
    expect(screen.getByRole("option", { name: "deepseek-chat" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "mock-live-model" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search available models"), { target: { value: "" } });

    const firstCounts = fetchMock.mock.calls.reduce(
      (counts, [input]) => {
        const path = pathFor(input);
        if (path === "/v1/desktop/settings/status") counts.settings += 1;
        if (path === "/v1/ai/models") counts.models += 1;
        return counts;
      },
      { settings: 0, models: 0 }
    );

    fireEvent.click(screen.getByRole("button", { name: /保存配置/ }));

    await waitFor(() => {
      const saveCall = fetchMock.mock.calls.find(([input, init]) => pathFor(input) === "/v1/ai/config" && init?.method === "PATCH");
      expect(saveCall?.[1]?.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    });

    fireEvent.click(screen.getByRole("button", { name: /获取模型/ }));

    await waitFor(() => {
      const paths = fetchMock.mock.calls.map(([input]) => pathFor(input));
      const settingsCalls = paths.filter((path) => path === "/v1/desktop/settings/status").length;
      const modelsCalls = paths.filter((path) => path === "/v1/ai/models").length;
      expect(settingsCalls).toBeGreaterThan(firstCounts.settings);
      expect(modelsCalls).toBeGreaterThan(firstCounts.models);
    });

    fireEvent.click(screen.getByRole("button", { name: /测试模型/ }));
    await screen.findByText("AIASK_MODEL_OK");

    const body = document.body.textContent || "";
    expect(body).toContain("[redacted]");
    expect(body).not.toContain("sk-provider-secret-value");
    expect(body).not.toContain("sk-model-secret-value");
  });
});
