import { Boxes, CircleDot, RefreshCw, Wifi, WifiOff } from "lucide-react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { NAV_GROUPS, V1_VIEWS } from "./views";
import { routeToView, viewToRoute } from "./routes";
import { useAsyncResource } from "./hooks/useAsyncResource";
import { useConnectionSettings } from "./hooks/useConnectionSettings";
import { Button, JsonPanel, StatusBadge } from "./components/ui";
import { AgentPages } from "./pages/AgentPages";
import { FinancePages } from "./pages/FinancePages";
import { IntegrationPages } from "./pages/IntegrationPages";
import { OpsPages } from "./pages/OpsPages";
import type { ViewId } from "./types";

function ViewRenderer({
  view,
  api,
  settings,
  updateSettings,
  controlAvailable
}: ReturnType<typeof useConnectionSettings> & { view: ViewId }) {
  if (
    view === "workbench" ||
    view === "models" ||
    view === "projects-contexts" ||
    view === "sessions-runs" ||
    view === "tools-approvals"
  ) {
    return <AgentPages view={view} api={api} settings={settings} controlAvailable={controlAvailable} />;
  }
  if (
    view === "integrations" ||
    view === "mcp-connectors" ||
    view === "plugins-skills" ||
    view === "gateway-webhooks"
  ) {
    return <IntegrationPages view={view} api={api} controlAvailable={controlAvailable} />;
  }
  if (
    view === "stock-data-sources" ||
    view === "data-sync" ||
    view === "finance-lab" ||
    view === "stock-radar" ||
    view === "market-temperature" ||
    view === "quant-research" ||
    view === "financial-manager"
  ) {
    return <FinancePages view={view} api={api} controlAvailable={controlAvailable} />;
  }
  return <OpsPages view={view} api={api} settings={settings} updateSettings={updateSettings} controlAvailable={controlAvailable} />;
}

function Sidebar() {
  return (
    <aside className="sidebar" aria-label="AIASK V1 navigation">
      <div className="brand">
        <div className="brand-mark">AI</div>
        <div>
          <strong>AIASK</strong>
          <span>V1 Desktop</span>
        </div>
      </div>
      <nav>
        {NAV_GROUPS.map((group) => {
          const views = V1_VIEWS.filter((view) => view.group === group.id);
          return (
            <div className="nav-group" key={group.id}>
              <span className="nav-group-label">{group.label}</span>
              {views.map((view) => {
                const Icon = view.icon;
                return (
                  <NavLink className="nav-link" key={view.id} to={view.route} end={view.route === "/"}>
                    <Icon size={18} aria-hidden="true" />
                    <span>{view.shortLabel}</span>
                  </NavLink>
                );
              })}
            </div>
          );
        })}
      </nav>
      <div className="sidebar-foot">
        <p>所有能力通过 Agent HTTP；副作用动作走意图或审批。</p>
      </div>
    </aside>
  );
}

function Topbar({
  active,
  settings,
  updateSettings,
  health,
  onRefresh
}: {
  active: (typeof V1_VIEWS)[number];
  settings: ReturnType<typeof useConnectionSettings>["settings"];
  updateSettings: ReturnType<typeof useConnectionSettings>["updateSettings"];
  health: ReturnType<typeof useAsyncResource>;
  onRefresh: () => void;
}) {
  const isLive = settings.mode === "live";
  return (
    <header className="topbar">
      <div>
        <h2>{active.label}</h2>
        <p>{active.description}</p>
      </div>
      <div className="topbar-controls">
        <span className="segmented" aria-label="API mode">
          <button className={!isLive ? "active" : ""} onClick={() => updateSettings({ mode: "mock" })}>
            Mock
          </button>
          <button className={isLive ? "active" : ""} onClick={() => updateSettings({ mode: "live" })}>
            Live
          </button>
        </span>
        <StatusBadge tone={health.error ? "danger" : health.loading ? "warning" : "success"}>
          {health.error ? <WifiOff size={14} /> : <Wifi size={14} />}
          {health.error ? "Agent 未连接" : health.loading ? "检查中" : "Agent 正常"}
        </StatusBadge>
        <Button icon={<RefreshCw size={16} />} onClick={onRefresh}>
          刷新
        </Button>
      </div>
    </header>
  );
}

function ContextPanel({
  active,
  settings,
  health
}: {
  active: (typeof V1_VIEWS)[number];
  settings: ReturnType<typeof useConnectionSettings>["settings"];
  health: ReturnType<typeof useAsyncResource>;
}) {
  return (
    <aside className="context-panel" aria-label="AIASK context">
      <h2>上下文</h2>
      <StatusBadge tone={settings.mode === "mock" ? "warning" : "info"}>{settings.mode === "mock" ? "Mock 验收" : "Live Agent"}</StatusBadge>
      <div className="context-list">
        <div className="context-item">
          <span>当前页面</span>
          <strong>{active.label}</strong>
        </div>
        <div className="context-item">
          <span>规范来源</span>
          <strong>{active.spec}</strong>
        </div>
        <div className="context-item">
          <span>API Base</span>
          <strong>{settings.baseUrl}</strong>
        </div>
        <div className="context-item">
          <span>Control Token</span>
          <strong>{settings.controlToken ? "已输入" : "未输入"}</strong>
        </div>
        <div className="context-item">
          <span>边界</span>
          <strong>Desktop to Agent HTTP</strong>
        </div>
      </div>
      <JsonPanel title="健康检查证据" data={health.data || health.error || { status: "loading" }} />
    </aside>
  );
}

export function App() {
  const location = useLocation();
  const connection = useConnectionSettings();
  const activeView = routeToView(location.pathname);
  const active = V1_VIEWS.find((view) => view.id === activeView) ?? V1_VIEWS[0];
  const health = useAsyncResource(() => connection.api.health(), [connection.api]);

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-frame">
        <Topbar active={active} settings={connection.settings} updateSettings={connection.updateSettings} health={health} onRefresh={() => void health.reload()} />
        <main className="page-host" id="main-content">
          <Routes>
            {V1_VIEWS.map((view) => (
              <Route
                key={view.id}
                path={view.route === "/" ? "/" : view.route}
                element={<ViewRenderer view={view.id} {...connection} />}
              />
            ))}
            <Route path="/strategy-factory" element={<Navigate to={viewToRoute("finance-lab")} replace />} />
            <Route path="/factor-factory" element={<Navigate to={viewToRoute("finance-lab")} replace />} />
            <Route path="/incubation" element={<Navigate to={viewToRoute("finance-lab")} replace />} />
            <Route path="/factory-events" element={<Navigate to={viewToRoute("finance-lab")} replace />} />
            <Route path="*" element={<Navigate to={viewToRoute("workbench")} replace />} />
          </Routes>
        </main>
      </div>
      <ContextPanel active={active} settings={connection.settings} health={health} />
      <div hidden aria-hidden="true">
        <Boxes />
        <CircleDot />
      </div>
    </div>
  );
}
