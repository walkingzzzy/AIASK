import { describe, expect, it } from "vitest";
import { isViewRouteActive, routeToView, viewToRoute } from "./routes";

describe("desktop routes", () => {
  it("maps core views to canonical hash-router paths", () => {
    expect(viewToRoute("workbench")).toBe("/");
    expect(viewToRoute("runs-events")).toBe("/runs");
    expect(viewToRoute("artifacts")).toBe("/artifacts");
    expect(viewToRoute("integrations")).toBe("/integrations");
    expect(viewToRoute("finance-lab")).toBe("/finance");
    expect(viewToRoute("readiness-health")).toBe("/readiness");
  });

  it("resolves finance and integration child routes", () => {
    expect(routeToView("/finance/quant")).toEqual({ view: "quant", matched: true });
    expect(routeToView("/finance/market-temperature")).toEqual({ view: "market-temperature", matched: true });
    expect(routeToView("/artifacts")).toEqual({ view: "artifacts", matched: true });
    expect(routeToView("/integrations/mcp")).toEqual({ view: "mcp-connectors", matched: true });
    expect(routeToView("/integrations/tools")).toEqual({ view: "tools-intents-approvals", matched: true });
  });

  it("keeps old public paths as aliases", () => {
    expect(routeToView("/finance-lab")).toEqual({ view: "finance-lab", matched: true });
    expect(routeToView("/runs-events")).toEqual({ view: "runs-events", matched: true });
    expect(routeToView("/agent-artifacts")).toEqual({ view: "artifacts", matched: true });
    expect(routeToView("/automations")).toEqual({ view: "automation", matched: true });
    expect(routeToView("/plugins-skills")).toEqual({ view: "plugins-skills", matched: true });
  });

  it("activates parent navigation groups for nested routes", () => {
    expect(isViewRouteActive("/finance/factor", "finance-lab")).toBe(true);
    expect(isViewRouteActive("/integrations/gateway", "integrations")).toBe(true);
    expect(isViewRouteActive("/missing", "workbench")).toBe(false);
  });
});
