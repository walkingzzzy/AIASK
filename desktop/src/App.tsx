import { useEffect, useMemo, useState } from "react";
import { formatApiError, normalizeEndpoint } from "./api";
import { AppContextPanel } from "./components/AppContextPanel";
import { AppSidebar } from "./components/AppSidebar";
import { DiagnosticsPanel } from "./components/DiagnosticsPanel";
import { InspectorPanel } from "./components/InspectorPanel";
import { ToolCatalog } from "./components/InspectorPanels";
import { WorkbenchView } from "./components/WorkbenchView";
import { AgentWorkspace } from "./features/agent/AgentWorkspace";
import { AlertsWorkspace } from "./features/alerts/AlertsWorkspace";
import { AutomationWorkspace } from "./features/automation/AutomationWorkspace";
import { CapabilitiesWorkspace } from "./features/capabilities/CapabilitiesWorkspace";
import { CoverageWorkspace } from "./features/coverage/CoverageWorkspace";
import { DataSyncWorkspace } from "./features/data/DataSyncWorkspace";
import { DecisionWorkspace } from "./features/decision/DecisionWorkspace";
import { EventConsolePanel } from "./features/event-console/EventConsolePanel";
import { FactoryEventTriggerPanel } from "./features/factory-events/FactoryEventTriggerPanel";
import { FactorFactoryPanel } from "./features/factor/FactorFactoryPanel";
import { FinancialManagerWorkspace } from "./features/financial-manager/FinancialManagerWorkspace";
import { FundFlowWorkspace } from "./features/fund-flow/FundFlowWorkspace";
import { FundamentalWorkspace } from "./features/fundamental/FundamentalWorkspace";
import { IncubationFactoryPanel } from "./features/incubation/IncubationFactoryPanel";
import { LimitUpWorkspace } from "./features/limit-up/LimitUpWorkspace";
import { MacroWorkspace } from "./features/macro/MacroWorkspace";
import { ModelsWorkspace } from "./features/models/ModelsWorkspace";
import { OverviewWorkspace } from "./features/overview/OverviewWorkspace";
import { QuantResearchWorkspace } from "./features/quant/QuantResearchWorkspace";
import { SettingsWorkspace } from "./features/settings/SettingsWorkspace";
import { SkillsPanel } from "./features/skills/SkillsPanel";
import { TradePlanWorkspace } from "./features/trade-plan/TradePlanWorkspace";
import { LocalUserWorkspace } from "./features/user/LocalUserWorkspace";
import { ValuationWorkspace } from "./features/valuation/ValuationWorkspace";
import { WorkflowsWorkspace } from "./features/workflows/WorkflowsWorkspace";
import { useAgentWorkbench } from "./hooks/useAgentWorkbench";
import { useHermesConsole } from "./hooks/useHermesConsole";
import { isMockEndpoint, MOCK_CONTROL_TOKEN } from "./mockApi";
import { AiaskApi } from "./services/aiaskApi";
import type { HealthDetailed, InspectorTab, LocalProfile, MainView, SkillView, ToolCatalogItem } from "./types";
import { VIEW_GROUPS } from "./views";

const ENDPOINT_KEY = "aiask.endpoint";
const DEFAULT_ENDPOINT = "http://127.0.0.1:8767";
const VERIFIED_ENDPOINT_KEY = "aiask.endpoint.verified";
const AUTO_CONNECT_KEY = "aiask.endpoint.autoconnect";

function isMockMode(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("mock") === "1";
  } catch {
    return false;
  }
}

function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Desktop can run under test or restricted webview origins where localStorage is unavailable.
  }
}

function storageRemove(key: string) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Desktop can run under test or restricted webview origins where localStorage is unavailable.
  }
}

export function App() {
  const mockMode = isMockMode();
  const verifiedEndpoint = storageGet(VERIFIED_ENDPOINT_KEY) === "1";
  const [endpoint, setEndpoint] = useState(() =>
    mockMode
      ? "mock://aiask"
      : verifiedEndpoint
        ? storageGet(ENDPOINT_KEY) || DEFAULT_ENDPOINT
        : DEFAULT_ENDPOINT
  );
  const [apiToken, setApiToken] = useState("");
  const [controlToken, setControlToken] = useState(() => (mockMode ? MOCK_CONTROL_TOKEN : ""));
  const [agentMode, setAgentMode] = useState<"finance_safe" | "hermes_full">("finance_safe");
  const [mainView, setMainView] = useState<MainView>("workbench");
  const [userId, setUserId] = useState(() => storageGet("aiask.local.user_id") || "local");
  const [profileName, setProfileName] = useState(() => storageGet("aiask.local.profile_name") || "本地操作者");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("details");
  const [health, setHealth] = useState<HealthDetailed | null>(null);
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [status, setStatus] = useState(() =>
    verifiedEndpoint ? "AIASK_OFFLINE" : "AIASK_DISCONNECTED"
  );
  const [connectionBusy, setConnectionBusy] = useState(false);

  const normalizedEndpoint = normalizeEndpoint(endpoint);
  const canLoadAgentHistory =
    mockMode || !!health || (storageGet(VERIFIED_ENDPOINT_KEY) === "1" && storageGet(AUTO_CONNECT_KEY) === "1");
  const api = useMemo(() => new AiaskApi({ endpoint: normalizedEndpoint, apiToken, controlToken }), [apiToken, controlToken, normalizedEndpoint]);
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
    }
  });

  const busy = connectionBusy || hermes.busy || workbench.busy;
  const parity = hermes.fullConsole.parity || hermes.hermesStatus?.parity || health?.hermes?.parity;
  const inspectorVisible = mainView === "workbench";
  const settingsMode = mainView === "settings";

  async function refreshHealth() {
    setConnectionBusy(true);
    try {
      const [nextHealth, nextTools] = await Promise.all([api.health(), api.tools()]);
      setHealth(nextHealth);
      setTools(nextTools.data || []);
      setStatus("AIASK_ONLINE");
      if (!isMockEndpoint(normalizedEndpoint)) {
        storageSet(ENDPOINT_KEY, normalizedEndpoint);
        storageSet(VERIFIED_ENDPOINT_KEY, "1");
        storageSet(AUTO_CONNECT_KEY, "1");
      }
      try {
        const nativeHermes = await api.hermesStatus();
        hermes.setHermesStatus(nativeHermes);
        if (nativeHermes.parity) {
          hermes.setFullConsole((current) => ({ ...current, parity: nativeHermes.parity }));
        }
      } catch {
        hermes.setHermesStatus(null);
      }
    } catch (error) {
      setStatus(formatApiError(error));
      setHealth(null);
      setTools([]);
    } finally {
      setConnectionBusy(false);
    }
  }

  function resetEndpointToDefault() {
    setEndpoint(mockMode ? "mock://aiask" : DEFAULT_ENDPOINT);
    setHealth(null);
    setTools([]);
    setStatus("AIASK_DISCONNECTED");
    if (!mockMode) {
      storageRemove(ENDPOINT_KEY);
      storageRemove(VERIFIED_ENDPOINT_KEY);
      storageRemove(AUTO_CONNECT_KEY);
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
    if (view === "diagnostics" && !hermes.fullConsole.parity) {
      void refreshHermes({ keepInspector: true });
    }
    if (view === "skills" && !hermes.fullConsole.skills && controlToken.trim()) {
      void refreshHermes({ keepInspector: true });
    }
    if (view === "tools" && !hermes.hermesTools.length && controlToken.trim()) {
      void refreshHermes({ keepInspector: true });
    }
  }

  function updateLocalProfile(profile: LocalProfile) {
    const nextUserId = profile.user_id || "local";
    const nextProfileName = profile.profile_name || "本地操作者";
    setUserId(nextUserId);
    setProfileName(nextProfileName);
    storageSet("aiask.local.user_id", nextUserId);
    storageSet("aiask.local.profile_name", nextProfileName);
  }

  function startNewTask() {
    setMainView("workbench");
    workbench.startNewTask();
  }

  function selectThread(id: string) {
    setMainView("workbench");
    workbench.selectThread(id);
  }

  function applySkillToChat(skill: SkillView | null) {
    if (!skill) return;
    const nextPrompt = `请使用 ${skill.name} 技能协助我完成：${skill.description || "分析当前任务并给出可执行建议。"}`;
    workbench.setPrompt(nextPrompt);
    setMainView("workbench");
    setInspectorTab("details");
  }

  useEffect(() => {
    if (mockMode || (storageGet(VERIFIED_ENDPOINT_KEY) === "1" && storageGet(AUTO_CONNECT_KEY) === "1")) {
      refreshHealth();
    }
    // Initial auto-connect is limited to an endpoint that was both verified and explicitly tested.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mockMode]);

  return (
    <div className={`app-shell ${settingsMode ? "settings-mode" : inspectorVisible ? "task-mode" : "context-mode"}`}>
      {!settingsMode && (
        <AppSidebar
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
        {mainView === "overview" && (
          <OverviewWorkspace
            apiToken={apiToken}
            autoRefresh={mockMode || !!health || (storageGet(VERIFIED_ENDPOINT_KEY) === "1" && storageGet(AUTO_CONNECT_KEY) === "1")}
            controlToken={controlToken}
            endpoint={normalizedEndpoint}
            health={health}
          />
        )}
        {mainView === "agent" && (
          <AgentWorkspace
            apiToken={apiToken}
            controlToken={controlToken}
            endpoint={normalizedEndpoint}
            health={health}
            onRefreshHealth={refreshHealth}
          />
        )}
        {mainView === "coverage" && (
          <CoverageWorkspace
            apiToken={apiToken}
            controlToken={controlToken}
            endpoint={normalizedEndpoint}
            health={health}
            tools={tools}
          />
        )}
        {mainView === "models" && <ModelsWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />}
        {mainView === "data" && <DataSyncWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />}
        {mainView === "mcp" && (
          <CapabilitiesWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} initialTab="mcp" />
        )}
        {mainView === "automation" && (
          <AutomationWorkspace
            apiToken={apiToken}
            controlToken={controlToken}
            endpoint={normalizedEndpoint}
            userId={userId}
          />
        )}
        {mainView === "workflows" && <WorkflowsWorkspace onOpenView={selectView} />}
        {mainView === "financial-manager" && (
          <FinancialManagerWorkspace
            apiToken={apiToken}
            controlToken={controlToken}
            endpoint={normalizedEndpoint}
            userId={userId}
          />
        )}
        {mainView === "strategy-factory" && (
          <CapabilitiesWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} initialTab="factory" />
        )}
        {mainView === "factor-factory" && (
          <section className="capabilities-workspace">
            <header className="capabilities-header">
              <div>
                <span>因子工厂</span>
                <h1>因子挖掘与活跃池</h1>
              </div>
            </header>
            <div className="capabilities-body">
              <FactorFactoryPanel apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
            </div>
          </section>
        )}
        {mainView === "incubation" && (
          <section className="capabilities-workspace">
            <header className="capabilities-header">
              <div>
                <span>孵化工厂</span>
                <h1>生命周期与命中率控制</h1>
              </div>
            </header>
            <div className="capabilities-body">
              <IncubationFactoryPanel apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
            </div>
          </section>
        )}
        {mainView === "capabilities" && (
          <CapabilitiesWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
        )}
        {mainView === "quant" && <QuantResearchWorkspace apiToken={apiToken} endpoint={normalizedEndpoint} userId={userId} />}
        {mainView === "event-console" && <EventConsolePanel apiToken={apiToken} endpoint={normalizedEndpoint} />}
        {mainView === "factory-events" && (
          <FactoryEventTriggerPanel
            apiToken={apiToken}
            controlToken={controlToken}
            endpoint={normalizedEndpoint}
          />
        )}
        {mainView === "valuation" && (
          <ValuationWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
        )}
        {mainView === "trade-plan" && (
          <TradePlanWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
        )}
        {mainView === "fund-flow" && (
          <FundFlowWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
        )}
        {mainView === "decision" && (
          <DecisionWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} userId={userId} />
        )}
        {mainView === "fundamental" && (
          <FundamentalWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} userId={userId} />
        )}
        {mainView === "macro" && (
          <MacroWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} userId={userId} />
        )}
        {mainView === "alerts" && (
          <AlertsWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} userId={userId} />
        )}
        {mainView === "limit-up" && (
          <LimitUpWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} userId={userId} />
        )}
        {mainView === "diagnostics" && (
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
        )}
        {mainView === "tools" && (
          <ToolCatalog
            apiToken={apiToken}
            controlToken={controlToken}
            endpoint={normalizedEndpoint}
            hermesTools={hermes.hermesTools}
            tools={tools}
          />
        )}
        {mainView === "skills" && (
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
        )}
        {mainView === "settings" && (
          <SettingsWorkspace
            agentMode={agentMode}
            apiToken={apiToken}
            busy={busy}
            controlToken={controlToken}
            endpoint={endpoint}
            connectionStatus={status}
            defaultEndpoint={mockMode ? "mock://aiask" : DEFAULT_ENDPOINT}
            health={health}
            profileName={profileName}
            userId={userId}
            onAgentModeChange={setAgentMode}
            onApiTokenChange={setApiToken}
            onBackToApp={() => setMainView("workbench")}
            onControlTokenChange={setControlToken}
            onEndpointChange={setEndpoint}
            onOpenView={selectView}
            onProfileChange={updateLocalProfile}
            onRefresh={refreshHealth}
            onResetEndpoint={resetEndpointToDefault}
          />
        )}
        {mainView === "user" && (
          <LocalUserWorkspace
            apiToken={apiToken}
            controlToken={controlToken}
            endpoint={normalizedEndpoint}
            profileName={profileName}
            userId={userId}
            onProfileChange={updateLocalProfile}
          />
        )}
        {mainView === "workbench" && (
          <WorkbenchView
            agentMode={agentMode}
            busy={busy}
            controlToken={controlToken}
            endpoint={normalizedEndpoint}
            health={health}
            onAgentModeChange={setAgentMode}
            onComposerKeyDown={workbench.handleComposerKeyDown}
            onPromptChange={workbench.setPrompt}
            onRefresh={refreshHealth}
            onSessionIdChange={workbench.setSessionId}
            onSubmit={workbench.sendResponse}
            prompt={workbench.prompt}
            profileName={profileName}
            selectedThread={workbench.selectedThread}
            sessionId={workbench.sessionId}
            status={status}
            timelineEvents={workbench.timelineEvents}
            tools={tools}
            userId={userId}
          />
        )}
      </main>

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
