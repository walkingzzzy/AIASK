import { describe, expect, it } from "vitest";

import { AiaskApi } from "./aiaskApi";
import { redactSecrets } from "./api/core";
import type { ConnectionSettings } from "../types";

const settings: ConnectionSettings = {
  baseUrl: "http://127.0.0.1:8765",
  apiToken: "api-token",
  controlToken: "control-token",
  mode: "mock",
  userId: "local-user"
};

describe("AiaskApi", () => {
  it("uses mock payloads without network", async () => {
    const api = new AiaskApi(settings);
    await expect(api.health()).resolves.toMatchObject({ status: "ok" });
    await expect(api.stockRadarStatus()).resolves.toMatchObject({ success: true });
  });

  it("supports stock radar query filters in mock mode", async () => {
    const api = new AiaskApi(settings);
    const candidates = await api.stockRadarCandidates({ tier: "A", symbol: "600519", min_score: 80, limit: 5 });
    expect(candidates).toMatchObject({
      success: true,
      data: {
        count: 1,
        candidates: [{ symbol: "600519", tier: "A" }]
      }
    });

    const digest = await api.stockRadarDigest({ run_id: "radar_filtered", channels: "local,wecom", limit: 2 });
    expect(digest).toMatchObject({
      success: true,
      data: {
        run_id: "radar_filtered",
        channels: ["local", "wecom"],
        limit: 2
      }
    });
  });

  it("supports gateway pairing status and create in mock mode", async () => {
    const api = new AiaskApi(settings);
    const status = await api.gatewayPairing({ platform: "feishu", user_id: "desk-user", session_id: "sess_1" });
    expect(status).toMatchObject({
      object: "gateway.pairing",
      success: true,
      data: {
        action: "status",
        platform: "feishu",
        user_id: "desk-user",
        session_id: "sess_1",
        configured: true
      }
    });

    const created = await api.gatewayPairingCreate({ platform: "discord", user_id: "desk-user", session_id: "sess_2" });
    expect(created).toMatchObject({
      object: "gateway.pairing",
      success: true,
      data: {
        action: "create",
        platform: "discord",
        user_id: "desk-user",
        session_id: "sess_2",
        configured: true
      }
    });
  });

  it("returns market temperature through agent tool facade", async () => {
    const api = new AiaskApi(settings);
    const result = await api.marketTemperatureSnapshot();
    expect(result).toMatchObject({ success: true });
    expect(JSON.stringify(result)).toContain("agent_market_temperature_snapshot");
  });

  it("exposes controlled factory surfaces in mock mode", async () => {
    const api = new AiaskApi(settings);
    const tools = await api.tools();
    expect(JSON.stringify(tools)).toContain("agent_factory_status");
    expect(JSON.stringify(tools)).toContain("agent_incubation_factory_status");

    await expect(api.strategyFactoryStatus()).resolves.toMatchObject({ success: true });
    await expect(api.factorFactoryStatus()).resolves.toMatchObject({ object: "aiask.desktop.factor_factory_status", status: "ready" });
    await expect(api.incubationFactoryStatus()).resolves.toMatchObject({ success: true });
    await expect(api.factoryEventList({ limit: 5 })).resolves.toMatchObject({ success: true });
    await expect(api.tradePredictionStatus({ limit: 10 })).resolves.toMatchObject({ success: true });
  });

  it("redacts sensitive values recursively", () => {
    const redacted = redactSecrets({
      api_key: "secret",
      nested: { token: "secret", safe: "visible" },
      list: [{ password: "secret" }]
    });
    expect(redacted).toEqual({
      api_key: "[redacted]",
      nested: { token: "[redacted]", safe: "visible" },
      list: [{ password: "[redacted]" }]
    });
  });
});
