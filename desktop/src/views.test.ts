import { describe, expect, it } from "vitest";
import { INTERNAL_EXTENSION_PAGES, INTERNAL_EXTENSION_SLOTS } from "./extensions/extensionRegistry";
import type { MainView } from "./types";
import { getViewItem, VIEW_GROUPS, VIEW_REGISTRY } from "./views";

const routedViews: Array<{ id: MainView; label: string; route: string }> = [
  { id: "workbench", label: "Workbench", route: "/workbench" },
  { id: "projects-contexts", label: "Projects / Contexts", route: "/projects-contexts" },
  { id: "sessions", label: "Sessions", route: "/sessions" },
  { id: "runs-events", label: "Runs / Events", route: "/runs-events" },
  { id: "tools-intents-approvals", label: "Approvals", route: "/tools-intents-approvals" },
  { id: "finance-lab", label: "Finance Lab", route: "/finance-lab" },
  { id: "integrations", label: "Integrations", route: "/integrations" },
  { id: "automation", label: "Automations", route: "/automations" },
  { id: "plugins-skills", label: "Plugins / Skills", route: "/plugins-skills" },
  { id: "factory-events", label: "Factory Events", route: "/factory-events" },
  { id: "mcp-connectors", label: "MCP / Connectors", route: "/mcp-connectors" },
  { id: "gateway", label: "Gateway", route: "/gateway" },
  { id: "readiness-health", label: "Readiness / Health", route: "/readiness-health" },
  { id: "extensions-pilot", label: "Extensions Pilot", route: "/extensions-pilot" },
];

describe("VIEW_REGISTRY", () => {
  it("keeps the new routed pages on clean public labels and routes", () => {
    for (const expected of routedViews) {
      const view = getViewItem(expected.id);
      expect(view?.label).toBe(expected.label);
      expect(view?.route).toBe(expected.route);
    }
  });

  it("keeps grouped and replacement views resolvable", () => {
    const ids = new Set(VIEW_REGISTRY.map((view) => view.id));
    expect(ids.size).toBe(VIEW_REGISTRY.length);

    for (const group of VIEW_GROUPS) {
      for (const item of group.items) {
        expect(ids.has(item.id)).toBe(true);
      }
    }

    for (const view of VIEW_REGISTRY) {
      if (view.replacementView) {
        expect(ids.has(view.replacementView)).toBe(true);
      }
    }
  });

  it("keeps the primary navigation focused on eight workspace entries", () => {
    const primary = VIEW_GROUPS.find((group) => group.id === "primary");
    expect(primary?.items.map((item) => item.id)).toEqual([
      "workbench",
      "projects-contexts",
      "runs-events",
      "tools-intents-approvals",
      "finance-lab",
      "integrations",
      "automation",
      "settings",
    ]);
  });

  it("keeps advanced and legacy groups collapsed by default", () => {
    expect(VIEW_GROUPS.find((group) => group.id === "advanced-finance")?.defaultCollapsed).toBe(true);
    expect(VIEW_GROUPS.find((group) => group.id === "advanced-ops")?.defaultCollapsed).toBe(true);
    const legacy = VIEW_GROUPS.find((group) => group.id === "legacy");
    expect(legacy?.defaultCollapsed).toBe(true);
    expect(legacy?.diagnosticOnly).toBe(true);
    expect(legacy?.items.every((item) => item.diagnosticOnly)).toBe(true);
  });

  it("keeps internal extension routes synchronized with registered view routes", () => {
    const routes = new Set(VIEW_REGISTRY.map((view) => view.route).filter(Boolean));

    for (const page of INTERNAL_EXTENSION_PAGES) {
      expect(routes.has(page.route)).toBe(true);
    }

    for (const slot of INTERNAL_EXTENSION_SLOTS) {
      if (slot.route) {
        expect(routes.has(slot.route)).toBe(true);
      }
    }
  });
});
