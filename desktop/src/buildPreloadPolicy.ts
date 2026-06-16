export function desktopChunkName(id: string): string | undefined {
  const normalized = id.replace(/\\/g, "/");
  if (
    normalized.includes("/node_modules/react/") ||
    normalized.includes("/node_modules/react-dom/") ||
    normalized.includes("/node_modules/scheduler/")
  ) {
    return "vendor-react";
  }
  if (normalized.includes("/node_modules/lucide-react/")) {
    return "vendor-icons";
  }
  if (normalized.includes("/node_modules/")) {
    return "vendor";
  }

  if (normalized.includes("/src/components/PageShell.")) {
    return "app-shell";
  }
  if (normalized.includes("/src/features/agent-pages/")) {
    return "agent-pages";
  }
  if (normalized.includes("/src/features/")) {
    return "workspaces";
  }
  return undefined;
}

export function shouldPreloadEntryDependency(dep: string): boolean {
  return !dep.includes("workspaces-") && !dep.includes("agent-pages-");
}

export function resolveDesktopModulePreloadDependencies(deps: string[], hostType: string): string[] {
  if (hostType !== "html") return deps;
  return deps.filter(shouldPreloadEntryDependency);
}
