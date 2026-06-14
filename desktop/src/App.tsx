import type { ReactNode } from "react";
import { lazy, Suspense, useEffect, useState } from "react";
import { formatApiError } from "./api";
import { AppContextPanel } from "./components/AppContextPanel";
import { AppSidebar } from "./components/AppSidebar";
import { DiagnosticsPanel } from "./components/DiagnosticsPanel";
import { InspectorPanel } from "./components/InspectorPanel";
import { ToolCatalog } from "./components/InspectorPanels";
import { WorkbenchView } from "./components/WorkbenchView";
import { ExtensionsPilotPage, SlotRenderer } from "./extensions/extensionRegistry";
import { useAppConnectionSettings } from "./hooks/useAppConnectionSettings";
import { useAgentWorkbench } from "./hooks/useAgentWorkbench";
import { useHermesConsole } from "./hooks/useHermesConsole";
import { AiaskApi } from "./services/aiaskApi";
import type { InspectorTab, MainView, SessionResumeContextPayload, SkillView } from "./types";
import { getViewItem, VIEW_GROUPS } from "./views";

const AgentWorkspace = lazy(() => import("./features/agent/AgentWorkspace").then((module) => ({ default: module.AgentWorkspace })));
const AutomationWorkspace = lazy(() => import("./features/automation/AutomationWorkspace").then((module) => ({ default: module.AutomationWorkspace })));
const CapabilitiesWorkspace = lazy(() => import("./features/capabilities/CapabilitiesWorkspace").then((module) => ({ default: module.CapabilitiesWorkspace })));
const CoverageWorkspace = lazy(() => import("./features/coverage/CoverageWorkspace").then((module) => ({ default: module.CoverageWorkspace })));
const DataSyncWorkspace = lazy(() => import("./features/data/DataSyncWorkspace").then((module) => ({ default: module.DataSyncWorkspace })));
const EventConsolePanel = lazy(() => import("./features/event-console/EventConsolePanel").then((module) => ({ default: module.EventConsolePanel })));
const FactoryEventTriggerPanel = lazy(() => import("./features/factory-events/FactoryEventTriggerPanel").then((module) => ({ default: module.FactoryEventTriggerPanel })));
const FactorFactoryPanel = lazy(() => import("./features/factor/FactorFactoryPanel").then((module) => ({ default: module.FactorFactoryPanel })));
const FinanceLabPage = lazy(() => import("./features/workspace/FinanceLabPage").then((module) => ({ default: module.FinanceLabPage })));
const FinancialManagerWorkspace = lazy(() => import("./features/financial-manager/FinancialManagerWorkspace").then((module) => ({ default: module.FinancialManagerWorkspace })));
const GatewayPage = lazy(() => import("./features/agent-pages/GatewayPage").then((module) => ({ default: module.GatewayPage })));
const IncubationFactoryPanel = lazy(() => import("./features/incubation/IncubationFactoryPanel").then((module) => ({ default: module.IncubationFactoryPanel })));
const IntegrationsPage = lazy(() => import("./features/workspace/IntegrationsPage").then((module) => ({ default: module.IntegrationsPage })));
const LegacyViewShell = lazy(() => import("./features/agent-pages/LegacyViewShell").then((module) => ({ default: module.LegacyViewShell })));
const LocalUserWorkspace = lazy(() => import("./features/user/LocalUserWorkspace").then((module) => ({ default: module.LocalUserWorkspace })));
const MarketTemperatureWorkspace = lazy(() => import("./features/market-temperature/MarketTemperatureWorkspace").then((module) => ({ default: module.MarketTemperatureWorkspace })));
const McpConnectorsPage = lazy(() => import("./features/agent-pages/McpConnectorsPage").then((module) => ({ default: module.McpConnectorsPage })));
const ModelsWorkspace = lazy(() => import("./features/models/ModelsWorkspace").then((module) => ({ default: module.ModelsWorkspace })));
const OverviewWorkspace = lazy(() => import("./features/overview/OverviewWorkspace").then((module) => ({ default: module.OverviewWorkspace })));
const PluginsSkillsPage = lazy(() => import("./features/agent-pages/PluginsSkillsPage").then((module) => ({ default: module.PluginsSkillsPage })));
const ProjectsContextsPage = lazy(() => import("./features/workspace/ProjectsContextsPage").then((module) => ({ default: module.ProjectsContextsPage })));
const QuantResearchWorkspace = lazy(() => import("./features/quant/QuantResearchWorkspace").then((module) => ({ default: module.QuantResearchWorkspace })));
const ReadinessHealthPage = lazy(() => import("./features/agent-pages/ReadinessHealthPage").then((module) => ({ default: module.ReadinessHealthPage })));
const RunsEventsPage = lazy(() => import("./features/agent-pages/RunsEventsPage").then((module) => ({ default: module.RunsEventsPage })));
const SessionsPage = lazy(() => import("./features/agent-pages/SessionsPage").then((module) => ({ default: module.SessionsPage })));
const SettingsWorkspace = lazy(() => import("./features/settings/SettingsWorkspace").then((module) => ({ default: module.SettingsWorkspace })));
const SkillsPanel = lazy(() => import("./features/skills/SkillsPanel").then((module) => ({ default: module.SkillsPanel })));
const ToolsIntentsApprovalsPage = lazy(() => import("./features/agent-pages/ToolsIntentsApprovalsPage").then((module) => ({ default: module.ToolsIntentsApprovalsPage })));
const WorkflowsWorkspace = lazy(() => import("./features/workflows/WorkflowsWorkspace").then((module) => ({ default: module.WorkflowsWorkspace })));

function ViewLoading() {
  return (
    <section className="capabilities-workspace" aria-busy="true" aria-label="Loading view">
      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="notice info compact">Loading view...</div>
        </div>
      </div>
    </section>
  );
}

function legacyMeta(view: MainView): {
  title: string;
  description: string;
  replacementView?: MainView;
  replacementLabel?: string;
} {
  const item = getViewItem(view);
  const replacement = item?.replacementView ? getViewItem(item.replacementView) : undefined;
  const replacementLabel = replacement ? `前往 ${replacement.label}` : undefined;

  switch (view) {
    case "tools":
      return {
        title: "旧入口：工具",
        description: "主路径已迁移到审批，此页仅保留为高级工具目录诊断。",
        replacementView: "tools-intents-approvals",
        replacementLabel,
      };
    case "mcp":
      return {
        title: "旧入口：MCP",
        description: "主路径已迁移到集成，此页仅保留为 MCP 高级诊断快捷入口。",
        replacementView: "integrations",
        replacementLabel,
      };
    case "diagnostics":
      return {
        title: "旧入口：诊断",
        description: "主路径已迁移到准备度 / 健康，此页保留为旧诊断快照。",
        replacementView: "readiness-health",
        replacementLabel,
      };
    case "event-console":
      return {
        title: "旧入口：事件控制台",
        description: "主路径已迁移到运行 / 事件，此页保留为高级事件控制台。",
        replacementView: "runs-events",
        replacementLabel,
      };
    case "agent":
      return {
        title: "旧入口：智能体",
        description: "工作台已成为 Agent 默认工作面，此页仅保留旧运行时上下文。",
        replacementView: "workbench",
        replacementLabel,
      };
    case "user":
      return {
        title: "旧入口：本地用户",
        description: "设置已承载画像与模式配置，此页仅保留本地用户旧详情。",
        replacementView: "settings",
        replacementLabel,
      };
    default:
      return {
        title: `旧入口：${item?.label || view}`,
        description: "此页在导航迁移期间保留于 Advanced，仅用于高级诊断或旧数据查看。",
        replacementView: item?.replacementView,
        replacementLabel,
      };
  }
}

export function App() {
  const {
    agentMode,
    agentReachable,
    apiToken,
    autoConnectEnabled,
    connectionBusy,
    controlToken,
    defaultEndpoint,
    defaultEndpointActive,
    endpoint,
    health,
    mockMode,
    normalizedEndpoint,
    profileName,
    refreshHealth: refreshConnectionHealth,
    resetEndpointToDefault,
    setAgentMode,
    setApiToken,
    setControlToken,
    setEndpoint,
    setStatus,
    status,
    tools,
    updateLocalProfile,
    userId,
  } = useAppConnectionSettings();
  const [mainView, setMainView] = useState<MainView>("workbench");
  const [sessionDetailId, setSessionDetailId] = useState("");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("details");

  const canLoadAgentHistory = agentReachable;
  const hermes = useHermesConsole(normalizedEndpoint, apiToken, controlToken);
  const workbench = useAgentWorkbench({
    endpoint: normalizedEndpoint,
    apiToken,
    controlToken,
    agentMode,
    canLoadHistory: canLoadAgentHistory,
    userId,
    onAgentStatus: setStatus,
    onInspectorTab: setInspectorTab,
    onRunEventsLoaded: (events) => {
      hermes.setFullConsole((current) => ({ ...current, runEvents: events }));
      hermes.setMessage("RUN_EVENTS_LOADED");
    },
  });

  const busy = connectionBusy || hermes.busy || workbench.busy;
  const parity = hermes.fullConsole.parity || hermes.hermesStatus?.parity || health?.hermes?.parity;
  const inspectorVisible = mainView === "workbench";
  const settingsMode = mainView === "settings";
  const sessionsAccess = workbench.summary?.access;
  const fullModeActive = Boolean(sessionsAccess?.full_mode_active || health?.hermes?.full_mode_active);
  const sessionsAdminAvailable = Boolean(sessionsAccess?.sessions_admin_available);

  async function refreshHealth() {
    try {
      const result = await refreshConnectionHealth();
      hermes.setHermesStatus(result.hermesStatus);
      if (result.hermesStatus?.parity) {
        hermes.setFullConsole((current) => ({ ...current, parity: result.hermesStatus?.parity }));
      }
    } catch (error) {
      setStatus(formatApiError(error));
    }
  }

  async function refreshHermes(options: { keepInspector?: boolean } = {}) {
    if (!options.keepInspector) setInspectorTab("diagnostics");
    try {
      await hermes.refresh();
      setStatus("AIASK_ONLINE");
    } catch (error) {
      setStatus(formatApiError(error));
    }
  }

  function selectView(view: MainView) {
    setMainView(view);
    if (view === "workbench") {
      setInspectorTab("details");
      return;
    }

    if (["integrations", "diagnostics", "readiness-health", "gateway", "tools", "tools-intents-approvals", "skills", "plugins-skills", "extensions-pilot"].includes(view)) {
      if (controlToken.trim()) {
        void refreshHermes({ keepInspector: true });
      }
    }
  }

  function startNewTask() {
    setMainView("workbench");
    workbench.startNewTask();
  }

  function selectThread(id: string) {
    setMainView("workbench");
    workbench.selectThread(id);
  }

  function openSessionDetail(sessionId: string) {
    setSessionDetailId(sessionId);
    setMainView("sessions");
  }

  function resumeSession(sessionId: string, resumeContext?: SessionResumeContextPayload) {
    if (!sessionId.trim()) return;
    workbench.setSessionId(sessionId);
    const prompt = resumeContext?.resume_context?.resume_prompt;
    if (prompt) workbench.setPrompt(prompt);
    setSessionDetailId(sessionId);
    setMainView("workbench");
    setInspectorTab("details");
  }

  function applySkillToChat(skill: SkillView | null) {
    if (!skill) return;
    const nextPrompt = `请使用 ${skill.name} 技能协助我完成：${skill.description || "分析当前请求并给出可执行下一步。"}`;
    workbench.setPrompt(nextPrompt);
    setMainView("workbench");
    setInspectorTab("details");
  }

  useEffect(() => {
    if (mockMode || autoConnectEnabled || defaultEndpointActive) {
      void refreshHealth();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoConnectEnabled, defaultEndpointActive, mockMode]);

  useEffect(() => {
    if (!normalizedEndpoint) return;
    const api = new AiaskApi({ endpoint: normalizedEndpoint, apiToken, controlToken });
    void api.recordEvents({
      user_id: userId,
      session_id: workbench.sessionId || undefined,
      page_key: mainView,
      route: `/${mainView}`,
      event_type: "page_view",
      source: mockMode ? "desktop.mock" : "desktop",
      payload: {
        agent_mode: agentMode,
        mock_mode: mockMode,
        status,
      },
    }).catch(() => undefined);
  }, [agentMode, apiToken, controlToken, mainView, mockMode, normalizedEndpoint, status, userId, workbench.sessionId]);

  function renderLegacyShell(view: MainView, child: ReactNode) {
    const meta = legacyMeta(view);
    return (
      <LegacyViewShell
        title={meta.title}
        description={meta.description}
        replacementLabel={meta.replacementLabel}
        replacementView={meta.replacementView}
        onOpenReplacement={selectView}
      >
        {child}
      </LegacyViewShell>
    );
  }

  const viewRenderers: Partial<Record<MainView, () => ReactNode>> = {
    "projects-contexts": () => (
      <ProjectsContextsPage
        agentMode={agentMode}
        apiToken={apiToken}
        controlToken={controlToken}
        defaultEndpoint={defaultEndpoint}
        endpoint={normalizedEndpoint}
        health={health}
        mockMode={mockMode}
        onOpenView={selectView}
        onRefresh={refreshHealth}
        profileName={profileName}
        status={status}
        userId={userId}
      />
    ),
    "finance-lab": () => (
      <FinanceLabPage
        apiToken={apiToken}
        controlToken={controlToken}
        endpoint={normalizedEndpoint}
        onOpenView={selectView}
      />
    ),
    integrations: () => (
      <IntegrationsPage
        controlToken={controlToken}
        health={health}
        hermesStatus={hermes.hermesStatus}
        onOpenView={selectView}
        tools={tools}
      />
    ),
    overview: () =>
      renderLegacyShell(
        "overview",
        <OverviewWorkspace
          apiToken={apiToken}
          autoRefresh={mockMode || !!health || autoConnectEnabled}
          controlToken={controlToken}
          endpoint={normalizedEndpoint}
          health={health}
        />
      ),
    agent: () =>
      renderLegacyShell(
        "agent",
        <AgentWorkspace
          apiToken={apiToken}
          controlToken={controlToken}
          endpoint={normalizedEndpoint}
          health={health}
          onRefreshHealth={refreshHealth}
        />
      ),
    coverage: () =>
      renderLegacyShell(
        "coverage",
        <CoverageWorkspace
          apiToken={apiToken}
          controlToken={controlToken}
          endpoint={normalizedEndpoint}
          health={health}
          tools={tools}
        />
      ),
    models: () => <ModelsWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />,
    data: () => <DataSyncWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />,
    mcp: () =>
      renderLegacyShell(
        "mcp",
        <CapabilitiesWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} initialTab="mcp" />
      ),
    automation: () => (
      <AutomationWorkspace
        apiToken={apiToken}
        controlToken={controlToken}
        endpoint={normalizedEndpoint}
        userId={userId}
      />
    ),
    workflows: () => <WorkflowsWorkspace onOpenView={selectView} />,
    "financial-manager": () => (
      <FinancialManagerWorkspace
        apiToken={apiToken}
        controlToken={controlToken}
        endpoint={normalizedEndpoint}
        userId={userId}
      />
    ),
    "market-temperature": () => <MarketTemperatureWorkspace apiToken={apiToken} endpoint={normalizedEndpoint} />,
    "strategy-factory": () => <CapabilitiesWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} initialTab="factory" />,
    "factor-factory": () => (
      <section className="capabilities-workspace">
        <header className="capabilities-header">
          <div>
            <span>因子工厂</span>
            <h1>因子挖掘与活跃池</h1>
          </div>
        </header>
        <div className="capabilities-body">
          <div className="capability-stack">
            <FactorFactoryPanel apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
          </div>
        </div>
      </section>
    ),
    incubation: () => (
      <section className="capabilities-workspace">
        <header className="capabilities-header">
          <div>
            <span>孵化工厂</span>
            <h1>生命周期与命中率控制</h1>
          </div>
        </header>
        <div className="capabilities-body">
          <div className="capability-stack">
            <IncubationFactoryPanel apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
          </div>
        </div>
      </section>
    ),
    capabilities: () =>
      renderLegacyShell(
        "capabilities",
        <CapabilitiesWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
      ),
    quant: () => <QuantResearchWorkspace apiToken={apiToken} endpoint={normalizedEndpoint} userId={userId} />,
    "event-console": () =>
      renderLegacyShell(
        "event-console",
        <EventConsolePanel apiToken={apiToken} endpoint={normalizedEndpoint} />
      ),
    "factory-events": () => (
      <FactoryEventTriggerPanel
        apiToken={apiToken}
        controlToken={controlToken}
        endpoint={normalizedEndpoint}
      />
    ),
    diagnostics: () =>
      renderLegacyShell(
        "diagnostics",
        <DiagnosticsPanel
          apiToken={apiToken}
          busy={busy}
          controlToken={controlToken}
          endpoint={normalizedEndpoint}
          fullConsole={hermes.fullConsole}
          health={health}
          hermesStatus={hermes.hermesStatus}
          message={hermes.message}
          onRefresh={refreshHermes}
          parity={parity}
        />
      ),
    tools: () =>
      renderLegacyShell(
        "tools",
        <ToolCatalog
          apiToken={apiToken}
          controlToken={controlToken}
          endpoint={normalizedEndpoint}
          hermesTools={hermes.hermesTools}
          tools={tools}
        />
      ),
    skills: () =>
      renderLegacyShell(
        "skills",
        <SkillsPanel
          apiToken={apiToken}
          controlToken={controlToken}
          endpoint={normalizedEndpoint}
          onRefresh={() => refreshHermes({ keepInspector: true })}
          onApplyToChat={applySkillToChat}
          skillsPayload={
            (hermes.fullConsole.skills as { gated?: boolean; reason?: string; skills?: []; root?: string } | undefined) ||
            (controlToken.trim() ? { skills: [], root: "-" } : { gated: true, reason: "需要控制令牌才能查看技能。" })
          }
        />
      ),
    "plugins-skills": () => (
      <PluginsSkillsPage
        apiToken={apiToken}
        controlToken={controlToken}
        endpoint={normalizedEndpoint}
        onApplyToChat={applySkillToChat}
      />
    ),
    settings: () => (
      <SettingsWorkspace
        agentMode={agentMode}
        apiToken={apiToken}
        busy={busy}
        controlToken={controlToken}
        connectionStatus={status}
        defaultEndpoint={defaultEndpoint}
        endpoint={endpoint}
        health={health}
        onAgentModeChange={setAgentMode}
        onApiTokenChange={setApiToken}
        onBackToApp={() => setMainView("workbench")}
        onControlTokenChange={setControlToken}
        onEndpointChange={setEndpoint}
        onOpenView={selectView}
        onProfileChange={updateLocalProfile}
        onRefresh={refreshHealth}
        onResetEndpoint={resetEndpointToDefault}
        profileName={profileName}
        userId={userId}
      />
    ),
    user: () =>
      renderLegacyShell(
        "user",
        <LocalUserWorkspace
          apiToken={apiToken}
          controlToken={controlToken}
          endpoint={normalizedEndpoint}
          profileName={profileName}
          userId={userId}
          onProfileChange={updateLocalProfile}
        />
      ),
    sessions: () => (
      <SessionsPage
        apiToken={apiToken}
        controlToken={controlToken}
        endpoint={normalizedEndpoint}
        fullModeActive={fullModeActive}
        onResumeSession={resumeSession}
        sessionsAdminAvailable={sessionsAdminAvailable}
        selectedSessionId={sessionDetailId}
        userId={userId}
      />
    ),
    "runs-events": () => (
      <RunsEventsPage
        apiToken={apiToken}
        controlToken={controlToken}
        endpoint={normalizedEndpoint}
        onOpenView={selectView}
      />
    ),
    "tools-intents-approvals": () => (
      <ToolsIntentsApprovalsPage
        apiToken={apiToken}
        controlToken={controlToken}
        endpoint={normalizedEndpoint}
        hermesTools={hermes.hermesTools}
        tools={tools}
      />
    ),
    "mcp-connectors": () => <McpConnectorsPage apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />,
    gateway: () => <GatewayPage apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} userId={userId} />,
    "readiness-health": () => (
      <ReadinessHealthPage
        apiToken={apiToken}
        controlToken={controlToken}
        endpoint={normalizedEndpoint}
        fullConsole={hermes.fullConsole}
        health={health}
        hermesStatus={hermes.hermesStatus}
        onOpenView={selectView}
        onRefreshHermes={() => {
          void refreshHermes({ keepInspector: true });
        }}
      />
    ),
    "extensions-pilot": () => <ExtensionsPilotPage controlToken={controlToken} fullModeActive={fullModeActive} />,
    workbench: () => (
      <WorkbenchView
        agentMode={agentMode}
        apiToken={apiToken}
        busy={busy}
        controlToken={controlToken}
        endpoint={normalizedEndpoint}
        health={health}
        mockMode={mockMode}
        onAgentModeChange={setAgentMode}
        onComposerKeyDown={workbench.handleComposerKeyDown}
        onOpenView={selectView}
        onOpenSession={openSessionDetail}
        onPromptChange={workbench.setPrompt}
        onRefresh={refreshHealth}
        onSessionIdChange={workbench.setSessionId}
        onSubmit={workbench.sendResponse}
        profileName={profileName}
        prompt={workbench.prompt}
        recentRuns={workbench.recentRuns}
        selectedRunArtifacts={workbench.selectedRunArtifacts}
        selectedRunSources={workbench.selectedRunSources}
        selectedThread={workbench.selectedThread}
        sessionId={workbench.sessionId}
        status={status}
        summary={workbench.summary}
        timelineEvents={workbench.timelineEvents}
        tools={tools}
        userId={userId}
      />
    ),
  };

  function renderMainView() {
    const item = getViewItem(mainView);
    const content = item?.render
      ? item.render()
      : (viewRenderers[item?.id || mainView] || viewRenderers.workbench)?.();
    return <Suspense fallback={<ViewLoading />}>{content}</Suspense>;
  }

  return (
    <div className={`app-shell ${settingsMode ? "settings-mode" : inspectorVisible ? "task-mode" : "context-mode"}`}>
      {!settingsMode && (
        <AppSidebar
          controlToken={controlToken}
          health={health}
          hermesStatus={hermes.hermesStatus}
          inspectorTab={inspectorTab}
          mainView={mainView}
          onNewTask={startNewTask}
          onSelectThread={selectThread}
          onSelectView={selectView}
          selectedThreadId={workbench.selectedThreadId}
          status={status}
          threads={workbench.threads}
          viewGroups={VIEW_GROUPS}
        />
      )}

      <main className="workbench">
        <div className="extension-slot-row main-slot">
          <SlotRenderer
            controlToken={controlToken}
            fullModeActive={fullModeActive}
            onOpenView={selectView}
            slot="pre-main"
          />
        </div>
        {renderMainView()}
        <div className="extension-slot-row main-slot">
          <SlotRenderer
            controlToken={controlToken}
            fullModeActive={fullModeActive}
            onOpenView={selectView}
            slot="post-main"
          />
        </div>
      </main>

      <div className="extension-overlay-slot">
        <SlotRenderer
          controlToken={controlToken}
          fullModeActive={fullModeActive}
          onOpenView={selectView}
          slot="overlay"
        />
      </div>

      {inspectorVisible && (
        <InspectorPanel
          agentMode={agentMode}
          apiToken={apiToken}
          busy={busy}
          controlToken={controlToken}
          currentIntent={workbench.currentIntent}
          endpoint={endpoint}
          fullConsole={hermes.fullConsole}
          fullConsoleMessage={hermes.message}
          health={health}
          hermesStatus={hermes.hermesStatus}
          hermesTools={hermes.hermesTools}
          inspectorTab={inspectorTab}
          intentEnvelope={workbench.intentEnvelope}
          intentIdInput={workbench.intentIdInput}
          intentIds={workbench.intentIds}
          intentMessage={workbench.intentMessage}
          onAgentModeChange={setAgentMode}
          onApiTokenChange={setApiToken}
          onControlTokenChange={setControlToken}
          onEndpointChange={setEndpoint}
          onFetchIntent={workbench.fetchIntent}
          onLoadRunEvents={workbench.loadRunEvents}
          onOpenView={selectView}
          onProfileChange={updateLocalProfile}
          onRefreshHealth={refreshHealth}
          onRefreshHermes={refreshHermes}
          onRemoveResponseThread={workbench.removeResponseThread}
          onSetInspectorTab={setInspectorTab}
          onSetIntentIdInput={workbench.setIntentIdInput}
          onUpdateIntent={workbench.updateIntent}
          parity={parity}
          profileName={profileName}
          recentRuns={workbench.recentRuns}
          selectedAuditEventCount={workbench.selectedAuditEventCount}
          selectedResponse={workbench.selectedResponse}
          selectedResponseRecord={workbench.selectedResponseRecord}
          selectedRunId={workbench.selectedRunId}
          selectedRunArtifacts={workbench.selectedRunArtifacts}
          selectedRunSources={workbench.selectedRunSources}
          selectedThread={workbench.selectedThread}
          timelineEvents={workbench.timelineEvents}
          tools={tools}
          userId={userId}
        />
      )}

      {!settingsMode && !inspectorVisible && (
        <AppContextPanel
          compact
          controlToken={controlToken}
          endpoint={normalizedEndpoint}
          health={health}
          hermesStatus={hermes.hermesStatus}
          onOpenSettings={() => selectView("settings")}
          onOpenWorkbench={() => selectView("workbench")}
          selectedThread={workbench.selectedThread}
          status={status}
          tools={tools}
        />
      )}
    </div>
  );
}
