import { describe, expect, it } from "vitest";

import { isDeferredView, routeToView, V1_DEFERRED_VIEWS, V1_ROUTES } from "./routes";

describe("V1 route scope", () => {
  it("promotes factory views into product routes", () => {
    expect(V1_DEFERRED_VIEWS).toEqual([]);
    for (const view of ["strategy-factory", "factor-factory", "incubation", "factory-events"]) {
      expect(isDeferredView(view)).toBe(false);
      expect(Object.keys(V1_ROUTES)).toContain(view);
    }
  });

  it("aliases compatibility paths to current pages", () => {
    expect(routeToView("/approvals")).toBe("tools-approvals");
    expect(routeToView("/mcp")).toBe("mcp-connectors");
    expect(routeToView("/connectors")).toBe("mcp-connectors");
    expect(routeToView("/skills")).toBe("plugins-skills");
    expect(routeToView("/plugins")).toBe("plugins-skills");
    expect(routeToView("/gateway")).toBe("gateway-webhooks");
    expect(routeToView("/finance-lab")).toBe("finance-lab");
    expect(routeToView("/user")).toBe("local-user-memory");
    expect(routeToView("/strategy-factory")).toBe("strategy-factory");
    expect(routeToView("/factor-factory")).toBe("factor-factory");
    expect(routeToView("/incubation")).toBe("incubation");
    expect(routeToView("/factory-events")).toBe("factory-events");
    expect(routeToView("/finance/strategy")).toBe("strategy-factory");
    expect(routeToView("/finance/factor")).toBe("factor-factory");
    expect(routeToView("/finance/incubation")).toBe("incubation");
    expect(routeToView("/finance/events")).toBe("factory-events");
  });

  it("resolves visible V1 pages", () => {
    expect(routeToView("/")).toBe("workbench");
    expect(routeToView("/models")).toBe("models");
    expect(routeToView("/stock-radar")).toBe("stock-radar");
    expect(routeToView("/readiness")).toBe("readiness-health");
  });
});
