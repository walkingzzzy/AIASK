import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { formatApiError } from "./api";
import { AppContextPanel } from "./components/AppContextPanel";
import { AppSidebar } from "./components/AppSidebar";
import { DiagnosticsPanel } from "./components/DiagnosticsPanel";
import { InspectorPanel } from "./components/InspectorPanel";
import { ToolCatalog } from "./components/InspectorPanels";
import { WorkbenchView } from "./components/WorkbenchView";
import { EventConsolePanel } from "./features/event-console/EventConsolePanel";
import { AgentWorkspace } from "./features/agent/AgentWorkspace";
import { GatewayPage } from "./features/agent-pages/GatewayPage";
import { LegacyViewShell } from "./features/agent-pages/LegacyViewShell";
import { McpConnectorsPage } from "./features/agent-pages/McpConnectorsPage";
import { ReadinessHealthPage } from "./features/agent-pages/ReadinessHealthPage";
import { RunsEventsPage } from "./features/agent-pages/RunsEventsPage";
import { SessionsPage } from "./features/agent-pages/SessionsPage";
import { PluginsSkillsPage } from "./features/agent-pages/PluginsSkillsPage";
import { ToolsIntentsApprovalsPage } from "./features/agent-pages/ToolsIntentsApprovalsPage";
import { ExtensionsPilotPage, SlotRenderer } from "./extensions/extensionRegistry";
import { AutomationWorkspace } from "./features/automation/AutomationWorkspace";
import { CapabilitiesWorkspace } from "./features/capabilities/CapabilitiesWorkspace";
import { CoverageWorkspace } from "./features/coverage/CoverageWorkspace";
import { DataSyncWorkspace } from "./features/data/DataSyncWorkspace";
import { FactoryEventTriggerPanel } from "./features/factory-events/FactoryEventTriggerPanel";
import { FactorFactoryPanel } from "./features/factor/FactorFactoryPanel";
import { FinancialManagerWorkspace } from "./features/financial-manager/FinancialManagerWorkspace";
import { IncubationFactoryPanel } from "./features/incubation/IncubationFactoryPanel";
import { ModelsWorkspace } from "./features/models/ModelsWorkspace";
import { OverviewWorkspace } from "./features/overview/OverviewWorkspace";
import { QuantResearchWorkspace } from "./features/quant/QuantResearchWorkspace";
import { SettingsWorkspace } from "./features/settings/SettingsWorkspace";
import { SkillsPanel } from "./features/skills/SkillsPanel";
import { LocalUserWorkspace } from "./features/user/LocalUserWorkspace";
import { WorkflowsWorkspace } from "./features/workflows/WorkflowsWorkspace";
import { useAppConnectionSettings } from "./hooks/useAppConnectionSettings";
import { useAgentWorkbench } from "./hooks/useAgentWorkbench";
import { useHermesConsole } from "./hooks/useHermesConsole";
import type { InspectorTab, MainView, SkillView } from "./types";
import { getViewItem, VIEW_GROUPS } from "./views";

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
        title: "Legacy: Tools",
        description: "新主路径已经迁移到 Tools / Intents / Approvals，这个页面仍保留到阶段 2 结束。",
        replacementView: "tools-intents-approvals",
        replacementLabel,
      };
    case "mcp":
      return {
        title: "Legacy: MCP",
        description: "新主路径已经迁移到 MCP / Connectors，这个页面继续保留为高级入口。",
        replacementView: "mcp-connectors",
        replacementLabel,
      };
    case "diagnostics":
      return {
        title: "Legacy: Diagnostics",
        description: "Readiness / Health 负责新的运维主路径，这里继续保留为 legacy 诊断快照。",
        replacementView: "readiness-health",
        replacementLabel,
      };
    case "event-console":
      return {
        title: "Legacy: Event Console",
        description: "Runs / Events 已经承担新的运行与事件主路径，这里继续保留旧控制台入口。",
        replacementView: "runs-events",
        replacementLabel,
      };
    case "agent":
      return {
        title: "Legacy: Agent",
        description: "Workbench 已成为新的 Agent 首页，这里保留旧版运行时总览。",
        replacementView: "workbench",
        replacementLabel,
      };
    case "user":
      return {
        title: "Legacy: User",
        description: "Settings / Mode 已经承担新的配置与用户主路径，这里保留旧版本地用户页。",
        replacementView: "settings",
        replacementLabel,
      };
    default:
      return {
        title: `Legacy: ${item?.label || view}`,
        description: "这个页面仍然保留在 Legacy / Advanced 组中，供迁移期继续使用。",
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

    if (["diagnostics", "readiness-health", "gateway", "tools", "tools-intents-approvals", "skills", "plugins-skills", "extensions-pilot"].includes(view)) {
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

  function resumeSession(sessionId: string) {
    if (!sessionId.trim()) return;
    workbench.setSessionId(sessionId);
    setSessionDetailId(sessionId);
    setMainView("workbench");
    setInspectorTab("details");
  }

  function applySkillToChat(skill: SkillView | null) {
    if (!skill) return;
    const nextPrompt = `请使用 ${skill.name} 技能协助我完成：${skill.description || "分析当前任务并给出可执行建议。"}`;
    workbench.setPrompt(nextPrompt);
    setMainView("workbench");
    setInspectorTab("details");
  }

  useEffect(() => {
    if (mockMode || autoConnectEnabled) {
      void refreshHealth();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoConnectEnabled, mockMode]);

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
    models: () =>
      renderLegacyShell(
        "models",
        <ModelsWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
      ),
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
          busy={busy}
          controlToken={controlToken}
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
    if (item?.render) return item.render();
    return (viewRenderers[item?.id || mainView] || viewRenderers.workbench)?.();
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
          onProfileChange={updateLocalProfile}
          onRefreshHealth={refreshHealth}
          onRefreshHermes={refreshHermes}
          onRemoveResponseThread={workbench.removeResponseThread}
          onSetInspectorTab={setInspectorTab}
          onSetIntentIdInput={workbench.setIntentIdInput}
          onUpdateIntent={workbench.updateIntent}
          parity={parity}
          profileName={profileName}
          selectedAuditEventCount={workbench.selectedAuditEventCount}
          selectedResponse={workbench.selectedResponse}
          selectedResponseRecord={workbench.selectedResponseRecord}
          selectedRunId={workbench.selectedRunId}
          selectedThread={workbench.selectedThread}
          tools={tools}
          userId={userId}
        />
      )}

      {!settingsMode && !inspectorVisible && (
        <AppContextPanel
          controlToken={controlToken}
          endpoint={normalizedEndpoint}
          health={health}
          hermesStatus={hermes.hermesStatus}
          selectedThread={workbench.selectedThread}
          status={status}
          tools={tools}
        />
      )}
    </div>
  );
}
