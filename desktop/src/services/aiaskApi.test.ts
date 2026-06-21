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

  it("returns market temperature through agent tool facade", async () => {
    const api = new AiaskApi(settings);
    const result = await api.marketTemperatureSnapshot();
    expect(result).toMatchObject({ success: true });
    expect(JSON.stringify(result)).toContain("agent_market_temperature_snapshot");
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
