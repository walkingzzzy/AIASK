import { describe, expect, it } from "vitest";

import { isDeferredView, routeToView, V1_DEFERRED_VIEWS, V1_ROUTES } from "./routes";

describe("V1 route scope", () => {
  it("keeps deferred views out of product routes", () => {
    expect(V1_DEFERRED_VIEWS).toEqual(["strategy-factory", "factor-factory", "incubation", "factory-events"]);
    for (const view of V1_DEFERRED_VIEWS) {
      expect(isDeferredView(view)).toBe(true);
      expect(Object.keys(V1_ROUTES)).not.toContain(view);
    }
  });

  it("aliases deferred paths back to finance lab", () => {
    expect(routeToView("/strategy-factory")).toBe("finance-lab");
    expect(routeToView("/factor-factory")).toBe("finance-lab");
    expect(routeToView("/incubation")).toBe("finance-lab");
    expect(routeToView("/factory-events")).toBe("finance-lab");
  });

  it("resolves visible V1 pages", () => {
    expect(routeToView("/")).toBe("workbench");
    expect(routeToView("/models")).toBe("models");
    expect(routeToView("/stock-radar")).toBe("stock-radar");
    expect(routeToView("/readiness")).toBe("readiness-health");
  });
});
