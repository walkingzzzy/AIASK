import { describe, expect, it } from "vitest";
import { INTERNAL_EXTENSION_PAGES, INTERNAL_EXTENSION_SLOTS } from "./extensions/extensionRegistry";
import type { MainView } from "./types";
import { getViewItem, VIEW_GROUPS, VIEW_REGISTRY } from "./views";

const routedViews: Array<{ id: MainView; label: string; route: string }> = [
  { id: "workbench", label: "工作台", route: "/" },
  { id: "projects-contexts", label: "项目 / 上下文", route: "/projects" },
  { id: "sessions", label: "会话", route: "/sessions" },
  { id: "runs-events", label: "运行 / 事件", route: "/runs" },
  { id: "artifacts", label: "产物", route: "/artifacts" },
  { id: "tools-intents-approvals", label: "审批", route: "/integrations/tools" },
  { id: "finance-lab", label: "金融实验室", route: "/finance" },
  { id: "market-temperature", label: "市场温度", route: "/finance/market-temperature" },
  { id: "integrations", label: "集成", route: "/integrations" },
  { id: "automation", label: "自动化", route: "/automation" },
  { id: "plugins-skills", label: "插件 / 技能", route: "/integrations/plugins" },
  { id: "factory-events", label: "工厂事件", route: "/finance/events" },
  { id: "mcp-connectors", label: "MCP / 连接器", route: "/integrations/mcp" },
  { id: "gateway", label: "Gateway", route: "/integrations/gateway" },
  { id: "readiness-health", label: "准备度 / 健康", route: "/readiness" },
  { id: "extensions-pilot", label: "扩展注册表", route: "/extensions" },
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

  it("keeps the primary navigation focused on the core entries", () => {
    const core = VIEW_GROUPS.find((group) => group.id === "core");
    expect(core?.items.map((item) => item.id)).toEqual([
      "workbench",
      "runs-events",
      "integrations",
      "finance-lab",
      "readiness-health",
    ]);
  });

  it("keeps sidebar navigation targets unique across groups", () => {
    const seen = new Map<MainView, string>();

    for (const group of VIEW_GROUPS) {
      for (const item of group.items) {
        expect(seen.get(item.id), `${item.id} appears in both ${seen.get(item.id)} and ${group.id}`).toBeUndefined();
        seen.set(item.id, group.id);
      }
    }
  });

  it("keeps a single core navigation group while non-nav views stay registered", () => {
    expect(VIEW_GROUPS).toHaveLength(1);
    expect(VIEW_GROUPS[0]?.id).toBe("core");

    const ids = new Set(VIEW_REGISTRY.map((view) => view.id));
    for (const offNav of ["settings", "projects-contexts", "sessions", "diagnostics"] as MainView[]) {
      expect(ids.has(offNav)).toBe(true);
    }
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
