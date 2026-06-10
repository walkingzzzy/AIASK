import { describe, expect, it } from "vitest";
import {
  desktopChunkName,
  resolveDesktopModulePreloadDependencies,
  shouldPreloadEntryDependency
} from "./buildPreloadPolicy";

describe("build preload policy", () => {
  it("groups desktop build chunks by runtime ownership", () => {
    expect(desktopChunkName("C:/repo/desktop/node_modules/react/index.js")).toBe("vendor-react");
    expect(desktopChunkName("C:/repo/desktop/node_modules/react-dom/index.js")).toBe("vendor-react");
    expect(desktopChunkName("C:/repo/desktop/node_modules/lucide-react/dist/esm/icons/chart.js")).toBe("vendor-icons");
    expect(desktopChunkName("C:/repo/desktop/node_modules/vite/dist/client/client.mjs")).toBe("vendor");
    expect(desktopChunkName("C:/repo/desktop/src/features/agent-pages/GatewayPage.tsx")).toBe("agent-pages");
    expect(desktopChunkName("C:/repo/desktop/src/features/financial-manager/FinancialManagerWorkspace.tsx")).toBe("workspaces");
    expect(desktopChunkName("C:/repo/desktop/src/App.tsx")).toBeUndefined();
  });

  it("keeps heavy lazy workspaces out of the entry HTML preload list", () => {
    expect(shouldPreloadEntryDependency("assets/vendor-react-abc.js")).toBe(true);
    expect(shouldPreloadEntryDependency("assets/workspaces-abc.js")).toBe(false);
    expect(shouldPreloadEntryDependency("assets/agent-pages-abc.js")).toBe(false);

    expect(
      resolveDesktopModulePreloadDependencies(
        [
          "assets/vendor-react-abc.js",
          "assets/vendor-icons-abc.js",
          "assets/workspaces-abc.js",
          "assets/agent-pages-abc.js"
        ],
        "html"
      )
    ).toEqual(["assets/vendor-react-abc.js", "assets/vendor-icons-abc.js"]);
  });

  it("preserves dynamic import preloads for non-entry hosts", () => {
    const deps = ["assets/workspaces-abc.js", "assets/agent-pages-abc.js"];
    expect(resolveDesktopModulePreloadDependencies(deps, "js")).toEqual(deps);
  });
});
