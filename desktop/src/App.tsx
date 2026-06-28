import {
  Activity,
  Boxes,
  CircleDot,
  FileSearch,
  FolderKanban,
  Loader2,
  MessageSquarePlus,
  MonitorDot,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Search,
  Settings,
  Wifi,
  WifiOff
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { Button, JsonPanel, StatusBadge } from "./components/ui";
import { FinanceContextBody, FinanceContextPanel } from "./components/FinanceContextPanel";
import { TerminalPanel } from "./components/TerminalPanel";
import { useAsyncResource } from "./hooks/useAsyncResource";
import { useConnectionSettings } from "./hooks/useConnectionSettings";
import { useSSE } from "./hooks/useWebSocket";
import { AgentPages } from "./pages/AgentPages";
import { FinancePages } from "./pages/FinancePages";
import { IntegrationPages } from "./pages/IntegrationPages";
import { OpsPages } from "./pages/OpsPages";
import { MyStrategyPage } from "./pages/MyStrategyPage";
import { MyStocksPage } from "./pages/MyStocksPage";
import { dataObject, list, valueOf } from "./pages/pageUtils";
import { routeToView, V1_COMPATIBLE_ALIASES, viewToRoute } from "./routes";
import { AiaskApi } from "./services/aiaskApi";
import type {
  ApiProblem,
  ConnectionSettings,
  UnknownRecord,
  ViewId,
  WorkbenchContext,
  WorkbenchMessage,
  WorkbenchThreadSummary
} from "./types";
import { V1_VIEWS } from "./views";

type ConnectionShape = ReturnType<typeof useConnectionSettings>;
type RailMode = "wide" | "drawer" | "sheet";

function isWorkbenchView(view: ViewId) {
  return view === "workbench";
}

function isSettingsView(view: ViewId) {
  return view === "settings-security";
}

function isFinanceView(view: ViewId) {
  return (
    view === "finance-lab" ||
    view === "stock-data-sources" ||
    view === "data-sync" ||
    view === "stock-radar" ||
    view === "market-temperature" ||
    view === "quant-research" ||
    view === "financial-manager" ||
    view === "my-strategy" ||
    view === "my-stocks"
  );
}

function primaryNavViews() {
  const ids: ViewId[] = [
    "workbench",
    "projects-contexts",
    "user-profile",
    "sessions-runs",
    "tools-approvals",
    "finance-lab",
    "my-strategy",
    "my-stocks",
    "integrations",
    "automation",
    "readiness-health"
  ];
  return ids.map((id) => V1_VIEWS.find((view) => view.id === id)).filter(Boolean) as typeof V1_VIEWS;
}

function detectRailMode(width = window.innerWidth): RailMode {
  if (width <= 760) return "sheet";
  if (width <= 1180) return "drawer";
  return "wide";
}

function viewSectionLabel(view: ViewId) {
  if (view === "workbench") return "Task Workspace";
  if (view === "projects-contexts" || view === "models") return "Projects & Models";
  if (view === "user-profile") return "Projects & Models";
  if (view === "sessions-runs") return "Runs";
  if (view === "tools-approvals") return "Approvals";
  if (
    view === "finance-lab" ||
    view === "stock-data-sources" ||
    view === "data-sync" ||
    view === "stock-radar" ||
    view === "market-temperature" ||
    view === "quant-research" ||
    view === "financial-manager"
  ) {
    return "Finance Lab";
  }
  if (view === "integrations" || view === "mcp-connectors" || view === "plugins-skills" || view === "gateway-webhooks") {
    return "Integrations";
  }
  if (view === "automation" || view === "workflows") return "Automations";
  if (
    view === "readiness-health" ||
    view === "local-user-memory" ||
    view === "learning-rl" ||
    view === "native-diagnostics"
  ) {
    return "Operations";
  }
  if (view === "settings-security") return "Settings";
  return "Workbench";
}

function viewTabs(view: ViewId) {
  switch (view) {
    case "projects-contexts":
    case "user-profile":
    case "models":
      return [
        { label: "Projects", to: viewToRoute("projects-contexts"), active: view === "projects-contexts" },
        { label: "Profile", to: viewToRoute("user-profile"), active: view === "user-profile" },
        { label: "Models", to: viewToRoute("models"), active: view === "models" }
      ];
    case "finance-lab":
    case "stock-data-sources":
    case "data-sync":
    case "stock-radar":
    case "market-temperature":
    case "quant-research":
    case "financial-manager":
      return [
        { label: "Overview", to: viewToRoute("finance-lab"), active: view === "finance-lab" },
        {
          label: "Data",
          to: viewToRoute("stock-data-sources"),
          active: view === "stock-data-sources" || view === "data-sync"
        },
        { label: "Radar", to: viewToRoute("stock-radar"), active: view === "stock-radar" },
        { label: "Temperature", to: viewToRoute("market-temperature"), active: view === "market-temperature" },
        { label: "Quant", to: viewToRoute("quant-research"), active: view === "quant-research" },
        { label: "Manager", to: viewToRoute("financial-manager"), active: view === "financial-manager" }
      ];
    case "integrations":
    case "mcp-connectors":
    case "plugins-skills":
    case "gateway-webhooks":
      return [
        { label: "Overview", to: viewToRoute("integrations"), active: view === "integrations" },
        { label: "MCP / Connectors", to: viewToRoute("mcp-connectors"), active: view === "mcp-connectors" },
        { label: "Plugins / Skills", to: viewToRoute("plugins-skills"), active: view === "plugins-skills" },
        { label: "Gateway", to: viewToRoute("gateway-webhooks"), active: view === "gateway-webhooks" }
      ];
    case "automation":
    case "workflows":
      return [
        { label: "Triage Inbox", to: viewToRoute("automation"), active: view === "automation" },
        { label: "Workflow", to: viewToRoute("workflows"), active: view === "workflows" }
      ];
    case "readiness-health":
    case "local-user-memory":
    case "learning-rl":
    case "native-diagnostics":
      return [
        { label: "Readiness", to: viewToRoute("readiness-health"), active: view === "readiness-health" },
        { label: "Memory", to: viewToRoute("local-user-memory"), active: view === "local-user-memory" },
        { label: "Learning / RL", to: viewToRoute("learning-rl"), active: view === "learning-rl" },
        { label: "Native Diagnostics", to: viewToRoute("native-diagnostics"), active: view === "native-diagnostics" }
      ];
    default:
      return [];
  }
}

function normalizeThreads(payload: unknown): WorkbenchThreadSummary[] {
  return list(payload).map((item, index) => ({
    id: String(item.id || item.session_id || `thread_${index}`),
    title: valueOf(item, ["title", "name"], `Thread ${index + 1}`),
    status: valueOf(item, ["status"], "idle"),
    updatedAt: valueOf(item, ["updated_at", "created_at"], "-"),
    messageCount: Number(item.message_count || item.messages || 0)
  }));
}

function formatTime(value: string) {
  if (!value || value === "-") return "Not updated";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function findRunId(value: UnknownRecord) {
  return String(value.id || value.run_id || "");
}

function findRecordId(value: UnknownRecord, fallback: string) {
  return String(value.id || value.message_id || value.artifact_id || value.approval_id || fallback);
}

function threadRuns(payload: unknown, threadId: string) {
  const allRuns = list(payload);
  if (!threadId) return allRuns;
  const matching = allRuns.filter((run) => String(run.session_id || run.thread_id || "") === threadId);
  return matching.length ? matching : allRuns;
}

function threadMessages(payload: unknown): WorkbenchMessage[] {
  return list<WorkbenchMessage>(payload).map((message, index) => ({
    id: String(message.id || `message_${index}`),
    role: message.role || "assistant",
    content: String(message.content || ""),
    created_at: String(message.created_at || new Date().toISOString()),
    status: message.status,
    sources: message.sources
  }));
}

function detectPrimaryStockCode(payload: unknown) {
  const codePattern = /\b(?:SH|SZ)?\s?(60\d{4}|68\d{4}|30\d{4}|00\d{4})\b/i;
  for (const message of threadMessages(payload)) {
    const match = String(message.content || "").match(codePattern);
    if (match?.[1]) {
      return match[1];
    }
  }
  return "";
}

function threadApprovals(payload: unknown, threadId: string, runId: string) {
  const allApprovals = list(payload);
  if (!threadId && !runId) return allApprovals;
  const matching = allApprovals.filter((approval) => {
    const approvalThread = String(approval.session_id || approval.thread_id || "");
    const approvalRun = String(approval.run_id || "");
    return approvalThread === threadId || approvalRun === runId;
  });
  return matching.length ? matching : allApprovals;
}

function ViewRenderer({
  view,
  ...connection
}: ConnectionShape & {
  view: ViewId;
  workbench: WorkbenchContext;
  setSelectedThreadId: (threadId: string) => void;
  setSelectedRunId: (runId: string) => void;
  setSelectedMessageId: (messageId: string) => void;
  setSelectedApprovalId: (approvalId: string) => void;
  setSelectedArtifactId: (artifactId: string) => void;
  setSelectedReviewTab: (tab: WorkbenchContext["selectedReviewTab"]) => void;
  reloadWorkbench: () => Promise<void>;
}) {
  if (
    view === "workbench" ||
    view === "models" ||
    view === "projects-contexts" ||
    view === "user-profile" ||
    view === "sessions-runs" ||
    view === "tools-approvals"
  ) {
    return <AgentPages view={view} {...connection} />;
  }

  if (
    view === "finance-lab" ||
    view === "stock-data-sources" ||
    view === "data-sync" ||
    view === "stock-radar" ||
    view === "market-temperature" ||
    view === "quant-research" ||
    view === "financial-manager"
  ) {
    return <FinancePages view={view} {...connection} />;
  }

  if (view === "my-strategy") {
    return <MyStrategyPage view={view} {...connection} />;
  }

  if (view === "my-stocks") {
    return <MyStocksPage view={view} {...connection} />;
  }

  if (view === "integrations" || view === "mcp-connectors" || view === "plugins-skills" || view === "gateway-webhooks") {
    return <IntegrationPages view={view} {...connection} />;
  }

  return <OpsPages view={view} {...connection} />;
}

function ThreadRail({
  settings,
  activeView,
  selectedThreadId,
  onSelectThread,
  threads,
  loading
}: {
  settings: ConnectionSettings;
  activeView: ViewId;
  selectedThreadId: string;
  onSelectThread: (threadId: string) => void;
  threads: WorkbenchThreadSummary[];
  loading: boolean;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const filteredThreads = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return threads;
    return threads.filter((thread) => thread.title.toLowerCase().includes(keyword) || thread.id.toLowerCase().includes(keyword));
  }, [query, threads]);

  useEffect(() => {
    if (!selectedThreadId && threads[0]) {
      onSelectThread(threads[0].id);
    }
  }, [onSelectThread, selectedThreadId, threads]);

  return (
    <>
      <section className="sidebar-section sidebar-context-switcher">
        <div className="sidebar-section-header">
          <span className="sidebar-eyebrow">Project / Context</span>
          <FolderKanban size={16} />
        </div>
        <button
          className={`context-switch-card ${
            activeView === "projects-contexts" || activeView === "user-profile" || activeView === "models" ? "active" : ""
          }`}
          onClick={() => navigate(viewToRoute("projects-contexts"))}
          type="button"
        >
          <div>
            <strong>{settings.userId || "local-user"}</strong>
            <p>Current API: {settings.baseUrl}</p>
          </div>
          <StatusBadge tone={settings.mode === "mock" ? "warning" : "info"}>{settings.mode === "mock" ? "Mock" : "Live"}</StatusBadge>
        </button>
      </section>

      <section className="sidebar-section sidebar-thread-rail">
        <div className="sidebar-section-header">
          <span className="sidebar-eyebrow">New Task + Threads</span>
          <Button
            type="button"
            className="thread-create-button"
            icon={<MessageSquarePlus size={16} />}
            onClick={() => navigate(viewToRoute("workbench"))}
          >
            New Task
          </Button>
        </div>

        <label className="thread-search" aria-label="Thread search">
          <Search size={14} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search threads or session IDs" />
        </label>

        <div className="thread-list" role="list" aria-label="Thread list">
          {loading ? (
            <div className="thread-list-empty">
              <Loader2 size={16} className="spin" />
              <span>Loading threads</span>
            </div>
          ) : null}

          {!loading && filteredThreads.length === 0 ? (
            <div className="thread-list-empty">
              <FileSearch size={16} />
              <span>No matching threads</span>
            </div>
          ) : null}

          {filteredThreads.map((thread) => (
            <button
              key={thread.id}
              type="button"
              className={`thread-card ${thread.id === selectedThreadId ? "active" : ""}`}
              onClick={() => {
                onSelectThread(thread.id);
                if (!isWorkbenchView(activeView)) {
                  navigate(viewToRoute("workbench"));
                }
              }}
            >
              <div className="thread-card-top">
                <strong>{thread.title}</strong>
                <StatusBadge tone={thread.status === "active" ? "success" : "neutral"}>{thread.status}</StatusBadge>
              </div>
              <p>{thread.id}</p>
              <div className="thread-card-meta">
                <span>{thread.messageCount} messages</span>
                <span>{formatTime(thread.updatedAt)}</span>
              </div>
            </button>
          ))}
        </div>
      </section>
    </>
  );
}

function Sidebar({
  settings,
  activeView,
  selectedThreadId,
  onSelectThread,
  threads,
  loading
}: {
  settings: ConnectionSettings;
  activeView: ViewId;
  selectedThreadId: string;
  onSelectThread: (threadId: string) => void;
  threads: WorkbenchThreadSummary[];
  loading: boolean;
}) {
  const primaryViews = primaryNavViews();
  return (
    <aside className="sidebar app-sidebar" aria-label="AIASK navigation">
      <div className="brand">
        <div className="brand-mark">AI</div>
        <div>
          <strong>AIASK</strong>
          <span>Desktop Workbench</span>
        </div>
      </div>

      <ThreadRail
        settings={settings}
        activeView={activeView}
        selectedThreadId={selectedThreadId}
        onSelectThread={onSelectThread}
        threads={threads}
        loading={loading}
      />

      <section className="sidebar-section sidebar-primary-nav">
        <div className="sidebar-section-header">
          <span className="sidebar-eyebrow">Primary Navigation</span>
          <Activity size={16} />
        </div>
        <nav className="primary-nav">
          {primaryViews.map((view) => {
            const Icon = view.icon;
            return (
              <NavLink className="nav-link primary-nav-link" key={view.id} to={view.route} end={view.route === "/"}>
                <Icon size={18} aria-hidden="true" />
                <div>
                  <strong>{view.shortLabel}</strong>
                  <span>{viewSectionLabel(view.id)}</span>
                </div>
              </NavLink>
            );
          })}
        </nav>
      </section>

      <div className="sidebar-footer">
        <NavLink className="nav-link settings-link" to={viewToRoute("settings-security")}>
          <Settings size={18} aria-hidden="true" />
          <div>
            <strong>Settings</strong>
            <span>Connection, token, mode, theme, shortcuts</span>
          </div>
        </NavLink>
        <div className="sidebar-status">
          <span>Boundary</span>
          <strong>Desktop to Agent HTTP</strong>
        </div>
      </div>
    </aside>
  );
}

function Topbar({
  active,
  settings,
  updateSettings,
  health,
  onRefresh,
  showRailToggle,
  railOpen,
  onToggleRail,
  showTerminalToggle,
  terminalVisible,
  onToggleTerminal
}: {
  active: (typeof V1_VIEWS)[number];
  settings: ConnectionShape["settings"];
  updateSettings: ConnectionShape["updateSettings"];
  health: ReturnType<typeof useAsyncResource>;
  onRefresh: () => void;
  showRailToggle: boolean;
  railOpen: boolean;
  onToggleRail: () => void;
  showTerminalToggle: boolean;
  terminalVisible: boolean;
  onToggleTerminal: () => void;
}) {
  const isLive = settings.mode === "live";
  const tabs = viewTabs(active.id);

  return (
    <header className="topbar app-topbar">
      <div className="topbar-copy">
        <span className="topbar-section">{viewSectionLabel(active.id)}</span>
        <h2>{active.shortLabel}</h2>
        <p>{active.description}</p>
      </div>

      <div className="topbar-controls">
        {showRailToggle ? (
          <Button
            data-testid="right-rail-toggle"
            icon={railOpen ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
            onClick={onToggleRail}
          >
            {railOpen ? "Hide right rail" : "Show right rail"}
          </Button>
        ) : null}

        {showTerminalToggle ? (
          <Button
            data-testid="terminal-toggle"
            icon={<MonitorDot size={16} />}
            onClick={onToggleTerminal}
            tone={terminalVisible ? "info" : "neutral"}
          >
            {terminalVisible ? "Hide terminal" : "Show terminal"}
          </Button>
        ) : null}

        <div className="segmented" aria-label="API mode">
          <button className={!isLive ? "active" : ""} onClick={() => updateSettings({ mode: "mock" })}>
            Mock
          </button>
          <button className={isLive ? "active" : ""} onClick={() => updateSettings({ mode: "live" })}>
            Live
          </button>
        </div>

        <StatusBadge tone={health.error ? "danger" : health.loading ? "warning" : "success"}>
          {health.error ? <WifiOff size={14} /> : <Wifi size={14} />}
          {health.error ? "Agent offline" : health.loading ? "Checking" : "Agent healthy"}
        </StatusBadge>

        <Button icon={<RefreshCw size={16} />} onClick={onRefresh}>
          Refresh
        </Button>
      </div>

      {tabs.length > 0 ? (
        <div className="page-tabs" role="tablist" aria-label={`${active.shortLabel} tabs`}>
          {tabs.map((tab) => (
            <NavLink key={tab.to} to={tab.to} className={`page-tab ${tab.active ? "active" : ""}`}>
              {tab.label}
            </NavLink>
          ))}
        </div>
      ) : null}
    </header>
  );
}

function WorkbenchInspector({
  workbench,
  summary,
  activeView,
  onSelectReviewTab,
  quotePayload,
  newsPayload,
  snapshotPayload,
  realtimeConnected,
  financeLoading,
  financeError,
  onRefreshFinance
}: {
  workbench: WorkbenchContext;
  summary: UnknownRecord;
  activeView: ViewId;
  onSelectReviewTab: (tab: WorkbenchContext["selectedReviewTab"]) => void;
  quotePayload: unknown;
  newsPayload: unknown;
  snapshotPayload: unknown;
  realtimeConnected: boolean;
  financeLoading: boolean;
  financeError: ApiProblem | null;
  onRefreshFinance: () => void;
}) {
  const reviewTabs: Array<{ id: WorkbenchContext["selectedReviewTab"]; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "artifacts", label: "Artifacts" },
    { id: "approvals", label: "Approvals" },
    { id: "review", label: "Review" },
    { id: "diagnostics", label: "Diagnostics" }
  ];
  const approvalList = threadApprovals(workbench.approvals, workbench.selectedThreadId, workbench.selectedRunId);

  return (
    <aside className="right-rail workbench-inspector" data-testid="workbench-inspector" aria-label="Workbench inspector">
      <div className="rail-header">
        <h3>InspectorPanel</h3>
        <p>Overview / Artifacts / Approvals / Review / Diagnostics</p>
      </div>

      <div className="rail-stack">
        <section className="rail-card">
          <span className="rail-card-title">Current thread</span>
          <strong>{workbench.currentThread?.title || "No thread selected"}</strong>
          <p>
            {activeView === "workbench"
              ? "The timeline and composer are focused on this thread."
              : "Return to Workbench to continue from this thread."}
          </p>
        </section>

        <section className="rail-card">
          <span className="rail-card-title">Current run</span>
          <strong>{valueOf(workbench.currentRun || {}, ["title", "id", "run_id"], "No active run")}</strong>
          <p>{valueOf(workbench.currentRun || {}, ["status"], "Not started yet")}</p>
        </section>

        <section className="rail-card">
          <span className="rail-card-title">Review focus</span>
          <div className="rail-tab-strip">
            {reviewTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`rail-tab ${workbench.selectedReviewTab === tab.id ? "active" : ""}`}
                onClick={() => onSelectReviewTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </section>

        <section className="rail-card">
          <span className="rail-card-title">Artifacts and approvals</span>
          <strong>{workbench.selectedRunArtifacts.length} artifact(s)</strong>
          <p>
            {approvalList.length
              ? `There are ${approvalList.length} approval item(s) linked to the current focus.`
              : "There are no pending approvals for the current focus."}
          </p>
        </section>

        <JsonPanel
          title="Workbench evidence"
          data={{
            summary,
            current_thread: workbench.currentThread,
            current_run: workbench.currentRun,
            messages: workbench.selectedSessionMessages,
            events: workbench.selectedRunEvents,
            artifacts: workbench.selectedRunArtifacts,
            sources: workbench.selectedRunSources,
            tools: workbench.selectedRunTools,
            approvals: approvalList
          }}
        />

        <section className="rail-card">
          <span className="rail-card-title">Finance extension</span>
          <p>Stock mentions, linked quote, market heat, and related news for the current thread.</p>
        </section>

        <FinanceContextBody
          workbench={workbench}
          quotePayload={quotePayload}
          newsPayload={newsPayload}
          snapshotPayload={snapshotPayload}
          realtimeConnected={realtimeConnected}
          loading={financeLoading}
          error={financeError}
          onRefresh={onRefreshFinance}
        />
      </div>
    </aside>
  );
}

function PageContextDrawer({
  active,
  settings,
  health,
  api,
  workbench
}: {
  active: (typeof V1_VIEWS)[number];
  settings: ConnectionShape["settings"];
  health: ReturnType<typeof useAsyncResource>;
  api: AiaskApi;
  workbench: WorkbenchContext;
}) {
  const settingsStatus = useAsyncResource(() => api.settingsStatus(), [api]);

  return (
    <aside className="right-rail page-context-drawer" data-testid="page-context-drawer" aria-label="Page context drawer">
      <div className="rail-header">
        <h3>Context Drawer</h3>
        <p>{viewSectionLabel(active.id)}</p>
      </div>

      <div className="rail-stack">
        <section className="rail-card">
          <span className="rail-card-title">Current page</span>
          <strong>{active.shortLabel}</strong>
          <p>{active.description}</p>
        </section>

        <section className="rail-card">
          <span className="rail-card-title">Current context</span>
          <strong>{settings.userId}</strong>
          <p>{settings.baseUrl}</p>
          <StatusBadge tone={settings.mode === "mock" ? "warning" : "info"}>
            {settings.mode === "mock" ? "Mock validation" : "Live Agent"}
          </StatusBadge>
        </section>

        <section className="rail-card">
          <span className="rail-card-title">Thread focus</span>
          <strong>{workbench.currentThread?.title || "No thread selected"}</strong>
          <p>
            {workbench.currentRun
              ? `Linked run: ${valueOf(workbench.currentRun, ["title", "id", "run_id"])}`
              : "This page is not currently linked to an active run."}
          </p>
        </section>

        <JsonPanel
          title="Page context evidence"
          data={{
            health: health.data || health.error || { status: "loading" },
            settings_status: settingsStatus.data,
            current_thread: workbench.currentThread,
            current_run: workbench.currentRun,
            spec: active.spec
          }}
        />
      </div>
    </aside>
  );
}

function ResponsiveRightRail({
  mode,
  open,
  onClose,
  children
}: {
  mode: RailMode;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  if (mode === "wide") {
    return <>{children}</>;
  }

  return (
    <div className={`right-rail-layer ${mode} ${open ? "open" : ""}`}>
      <button className="right-rail-backdrop" type="button" aria-label="Close right rail" onClick={onClose} />
      <div className={`right-rail-floating ${mode}`}>{children}</div>
    </div>
  );
}

export function App() {
  const location = useLocation();
  const connection = useConnectionSettings();
  const activeView = routeToView(location.pathname);
  const active = V1_VIEWS.find((view) => view.id === activeView) ?? V1_VIEWS[0];
  const health = useAsyncResource(() => connection.api.health(), [connection.api]);
  const summary = useAsyncResource(() => connection.api.workbenchSummary(), [connection.api, connection.settings.userId]);
  const sessions = useAsyncResource(() => connection.api.sessions({ include_archived: true }), [connection.api, connection.settings.userId]);
  const approvals = useAsyncResource(() => connection.api.approvals(), [connection.api, connection.settings.userId]);
  const [selectedThreadId, setSelectedThreadId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedMessageId, setSelectedMessageId] = useState("");
  const [selectedApprovalId, setSelectedApprovalId] = useState("");
  const [selectedArtifactId, setSelectedArtifactId] = useState("");
  const [selectedReviewTab, setSelectedReviewTab] = useState<WorkbenchContext["selectedReviewTab"]>("overview");
  const [railMode, setRailMode] = useState<RailMode>(() => detectRailMode());
  const [railOpen, setRailOpen] = useState(false);
  const [terminalVisible, setTerminalVisible] = useState(false);

  const selectedRunIdForStream = selectedRunId || "";
  const eventStreamUrl =
    connection.settings.mode === "live" && selectedRunIdForStream
      ? `${connection.settings.baseUrl.replace(/\/+$/, "")}/v1/runs/${encodeURIComponent(selectedRunIdForStream)}/events/stream`
      : "";
  const liveRunEvents = useSSE({
    url: eventStreamUrl,
    enabled: Boolean(eventStreamUrl),
    onMessage: () => {
      void Promise.all([runEvents.reload(), runArtifacts.reload(), runSources.reload(), runTools.reload()]);
    }
  });

  const summaryData = dataObject(summary.data, {});
  const threads = useMemo(() => {
    const sessionThreads = normalizeThreads(sessions.data);
    if (sessionThreads.length) return sessionThreads;
    return normalizeThreads(summaryData.sessions);
  }, [sessions.data, summaryData.sessions]);

  const runs = useAsyncResource(
    () => connection.api.desktopRuns(selectedThreadId ? { session_id: selectedThreadId } : undefined),
    [connection.api, connection.settings.userId, selectedThreadId]
  );
  const sessionMessages = useAsyncResource(
    () => (selectedThreadId ? connection.api.sessionMessages(selectedThreadId) : Promise.resolve([])),
    [connection.api, selectedThreadId]
  );
  const runEvents = useAsyncResource(
    () => (selectedRunId ? connection.api.runEvents(selectedRunId) : Promise.resolve([])),
    [connection.api, selectedRunId]
  );
  const runArtifacts = useAsyncResource(
    () => (selectedRunId ? connection.api.runArtifacts(selectedRunId) : Promise.resolve([])),
    [connection.api, selectedRunId]
  );
  const runSources = useAsyncResource(
    () => (selectedRunId ? connection.api.runSources(selectedRunId) : Promise.resolve([])),
    [connection.api, selectedRunId]
  );
  const runTools = useAsyncResource(
    () => (selectedRunId ? connection.api.runToolInvocations(selectedRunId) : Promise.resolve([])),
    [connection.api, selectedRunId]
  );
  const primaryStockCode = useMemo(() => {
    const fromSession = detectPrimaryStockCode(sessionMessages.data);
    if (fromSession) return fromSession;
    return detectPrimaryStockCode(summaryData.messages);
  }, [sessionMessages.data, summaryData.messages]);
  const marketQuote = useAsyncResource(
    () => (primaryStockCode ? connection.api.stockLiveQuote(primaryStockCode) : Promise.resolve(null)),
    [connection.api, primaryStockCode]
  );
  const relatedNews = useAsyncResource(
    () => (primaryStockCode ? connection.api.stockNewsDigest(primaryStockCode, 5) : Promise.resolve(null)),
    [connection.api, primaryStockCode]
  );
  const temperatureHistory = useAsyncResource(() => connection.api.marketTemperatureHistory(7, true), [connection.api]);
  const terminalBackends = useAsyncResource(() => connection.api.terminalBackends(), [connection.api]);
  const terminalSessions = useAsyncResource(() => connection.api.terminalSessions(), [connection.api]);

  const availableRuns = useMemo(() => threadRuns(runs.data || summaryData.runs, selectedThreadId), [runs.data, selectedThreadId, summaryData.runs]);
  const selectedSessionMessages = useMemo(() => threadMessages(sessionMessages.data), [sessionMessages.data]);
  const selectedRunArtifacts = useMemo(() => list(runArtifacts.data), [runArtifacts.data]);
  const selectedRunSources = useMemo(() => list(runSources.data), [runSources.data]);
  const selectedRunTools = useMemo(() => list(runTools.data), [runTools.data]);
  const approvalRows = useMemo(() => list(approvals.data), [approvals.data]);

  useEffect(() => {
    if (!selectedThreadId && threads[0]) {
      setSelectedThreadId(threads[0].id);
    }
  }, [selectedThreadId, threads]);

  useEffect(() => {
    if (!selectedThreadId) return;
    const exists = threads.some((thread) => thread.id === selectedThreadId);
    if (!exists) {
      setSelectedThreadId(threads[0]?.id || "");
    }
  }, [selectedThreadId, threads]);

  useEffect(() => {
    const nextRunId = findRunId(availableRuns[0] || {});
    if (!availableRuns.length) {
      if (selectedRunId) {
        setSelectedRunId("");
      }
      return;
    }
    if (!selectedRunId || !availableRuns.some((run) => findRunId(run) === selectedRunId)) {
      setSelectedRunId(nextRunId);
    }
  }, [availableRuns, selectedRunId]);

  useEffect(() => {
    if (!selectedMessageId && selectedSessionMessages[0]) {
      setSelectedMessageId(findRecordId(selectedSessionMessages[0] as UnknownRecord, "message_0"));
    }
  }, [selectedMessageId, selectedSessionMessages]);

  useEffect(() => {
    if (!selectedArtifactId && selectedRunArtifacts[0]) {
      setSelectedArtifactId(findRecordId(selectedRunArtifacts[0], "artifact_0"));
    }
  }, [selectedArtifactId, selectedRunArtifacts]);

  useEffect(() => {
    const currentApprovals = threadApprovals(approvalRows, selectedThreadId, selectedRunId);
    if (!selectedApprovalId && currentApprovals[0]) {
      setSelectedApprovalId(findRecordId(currentApprovals[0], "approval_0"));
    }
  }, [approvalRows, selectedApprovalId, selectedRunId, selectedThreadId]);

  useEffect(() => {
    const handleResize = () => setRailMode(detectRailMode(window.innerWidth));
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (railMode === "wide") {
      setRailOpen(false);
    }
  }, [railMode]);

  useEffect(() => {
    setRailOpen(false);
  }, [active.id]);

  useEffect(() => {
    if (!isWorkbenchView(active.id)) {
      setTerminalVisible(false);
    }
  }, [active.id]);

  const currentThread = threads.find((thread) => thread.id === selectedThreadId) || threads[0] || null;
  const currentRun = availableRuns.find((run) => findRunId(run) === selectedRunId) || availableRuns[0] || null;
  const workbench: WorkbenchContext = {
    selectedThreadId,
    selectedRunId,
    selectedMessageId,
    selectedApprovalId,
    selectedArtifactId,
    selectedReviewTab,
    selectedSessionMessages,
    selectedRunEvents: runEvents.data || [],
    selectedRunArtifacts,
    selectedRunSources,
    selectedRunTools,
    availableThreads: threads,
    availableRuns,
    approvals: approvalRows,
    currentThread,
    currentRun
  };

  async function reloadWorkbench() {
    await Promise.all([
      summary.reload(),
      sessions.reload(),
      approvals.reload(),
      runs.reload(),
      sessionMessages.reload(),
      runEvents.reload(),
      runArtifacts.reload(),
      runSources.reload(),
      runTools.reload(),
      marketQuote.reload(),
      relatedNews.reload(),
      temperatureHistory.reload(),
      terminalBackends.reload(),
      terminalSessions.reload()
    ]);
  }

  const shouldShowRightRail = !isSettingsView(active.id);
  const showRailToggle = shouldShowRightRail && railMode !== "wide";
  const shellClassName = [
    "app-shell",
    isWorkbenchView(active.id) ? "shell-workbench" : "shell-page",
    shouldShowRightRail ? "has-right-rail" : "no-right-rail"
  ].join(" ");

  const rightRail = shouldShowRightRail ? (
    isWorkbenchView(active.id) ? (
      <WorkbenchInspector
        workbench={workbench}
        summary={summaryData}
        activeView={active.id}
        onSelectReviewTab={setSelectedReviewTab}
        quotePayload={marketQuote.data}
        newsPayload={relatedNews.data}
        snapshotPayload={temperatureHistory.data}
        realtimeConnected={liveRunEvents.connected}
        financeLoading={marketQuote.loading || relatedNews.loading || temperatureHistory.loading}
        financeError={marketQuote.error || relatedNews.error || temperatureHistory.error}
        onRefreshFinance={() => {
          void Promise.all([marketQuote.reload(), relatedNews.reload(), temperatureHistory.reload()]);
        }}
      />
    ) : isFinanceView(active.id) ? (
      <FinanceContextPanel
        workbench={workbench}
        quotePayload={marketQuote.data}
        newsPayload={relatedNews.data}
        snapshotPayload={temperatureHistory.data}
        realtimeConnected={liveRunEvents.connected}
        loading={marketQuote.loading || relatedNews.loading || temperatureHistory.loading}
        error={marketQuote.error || relatedNews.error || temperatureHistory.error}
        onRefresh={() => {
          void Promise.all([marketQuote.reload(), relatedNews.reload(), temperatureHistory.reload()]);
        }}
      />
    ) : (
      <PageContextDrawer active={active} settings={connection.settings} health={health} api={connection.api} workbench={workbench} />
    )
  ) : null;

  return (
    <div className={shellClassName}>
      <Sidebar
        settings={connection.settings}
        activeView={active.id}
        selectedThreadId={selectedThreadId}
        onSelectThread={setSelectedThreadId}
        threads={threads}
        loading={sessions.loading}
      />

      <div className="main-frame">
        <Topbar
          active={active}
          settings={connection.settings}
          updateSettings={connection.updateSettings}
          health={health}
          onRefresh={() => {
            void Promise.all([health.reload(), reloadWorkbench()]);
          }}
          showRailToggle={showRailToggle}
          railOpen={railOpen}
          onToggleRail={() => setRailOpen((current) => !current)}
          showTerminalToggle={isWorkbenchView(active.id)}
          terminalVisible={terminalVisible}
          onToggleTerminal={() => setTerminalVisible((current) => !current)}
        />

        <main className="page-host" id="main-content">
          <Routes>
            {V1_VIEWS.map((view) => (
              <Route
                key={view.id}
                path={view.route}
                element={
                  <ViewRenderer
                    view={view.id}
                    {...connection}
                    workbench={workbench}
                    setSelectedThreadId={setSelectedThreadId}
                    setSelectedRunId={setSelectedRunId}
                    setSelectedMessageId={setSelectedMessageId}
                    setSelectedApprovalId={setSelectedApprovalId}
                    setSelectedArtifactId={setSelectedArtifactId}
                    setSelectedReviewTab={setSelectedReviewTab}
                    reloadWorkbench={reloadWorkbench}
                  />
                }
              />
            ))}

            {V1_COMPATIBLE_ALIASES.map((alias) => (
              <Route key={alias.path} path={alias.path} element={<Navigate to={viewToRoute(alias.view)} replace />} />
            ))}

            <Route path="*" element={<Navigate to={viewToRoute("workbench")} replace />} />
          </Routes>

          {isWorkbenchView(active.id) ? (
            <TerminalPanel
              visible={terminalVisible}
              controlAvailable={Boolean(connection.settings.controlToken) || connection.settings.mode === "mock"}
              backends={terminalBackends.data}
              sessions={terminalSessions.data}
              loading={terminalBackends.loading || terminalSessions.loading}
              error={terminalBackends.error || terminalSessions.error}
              onRefresh={() => {
                void Promise.all([terminalBackends.reload(), terminalSessions.reload()]);
              }}
              onExecute={(payload) => connection.api.terminalExecute(payload)}
            />
          ) : null}
        </main>
      </div>

      {rightRail ? (
        <ResponsiveRightRail mode={railMode} open={railOpen} onClose={() => setRailOpen(false)}>
          {rightRail}
        </ResponsiveRightRail>
      ) : null}

      <div hidden aria-hidden="true">
        <Boxes />
        <CircleDot />
      </div>
    </div>
  );
}
