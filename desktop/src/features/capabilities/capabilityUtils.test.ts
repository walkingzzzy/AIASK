import { describe, expect, it } from "vitest";
import { capabilityIssues, collectCapabilityRows, filterRows } from "./capabilityUtils";

describe("capability utils", () => {
  const payload = {
    hermes: {
      feature_mapping: [{ feature: "mcp_tools", area: "mcp", status: "implemented" }],
      tool_mapping: [{ hermes_tool: "terminal", area: "terminal", status: "implemented" }],
      platform_mapping: [{ platform: "discord", area: "platform", status: "live_unverified" }],
      issues: [{ feature: "discord", status: "live_unverified" }]
    }
  };

  it("collects feature, tool, and platform rows", () => {
    expect(collectCapabilityRows(payload)).toHaveLength(3);
  });

  it("filters by text and exact status", () => {
    const rows = collectCapabilityRows(payload);
    expect(filterRows(rows, "discord", "all")).toHaveLength(1);
    expect(filterRows(rows, "", "implemented")).toHaveLength(2);
  });

  it("returns actionable issues", () => {
    expect(capabilityIssues(payload)).toEqual([{ feature: "discord", status: "live_unverified" }]);
  });
});

