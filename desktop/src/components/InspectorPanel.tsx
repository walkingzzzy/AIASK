import { Activity, ChevronDown, ClipboardCheck, Layers3, MessageSquare, PanelRight, Settings, ShieldCheck, Wrench } from "lucide-react";
import type { ElementType } from "react";
import { DiagnosticsPanel } from "./DiagnosticsPanel";
import { IntentsPanel, ToolCatalog } from "./InspectorPanels";
import { JsonPanel, compact } from "./shared";
import { SettingsWorkspace } from "../features/settings/SettingsWorkspace";
import { SkillsPanel } from "../features/skills/SkillsPanel";
import type {
  AgentResponse,
  CapabilityParity,
  FullModeConsoleData,
  HealthDetailed,
  HermesStatus,
  InspectorTab,
  IntentRecord,
  LocalProfile,
  TaskThread,
  ToolCatalogItem,
  ToolEnvelope
} from "../types";

const inspectorTabs: Array<{ id: InspectorTab; label: string; icon: ElementType }> = [
  { id: "details", label: "Summary", icon: PanelRight },
  { id: "diagnostics", label: "Diagnostics", icon: Activity },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "skills", label: "Skills", icon: Layers3 },
  { id: "intents", label: "Approvals", icon: ShieldCheck },
  { id: "settings", label: "Settings", icon: Settings }
];

function RunDetailsPanel({
  agentMode,
  busy,
  onLoadRunEvents,
  selectedAuditEventCount,
  selectedResponse,
  selectedResponseRecord,
  selectedRunId,
  selectedThread
}: {
  agentMode: "finance_safe" | "hermes_full";
  busy: boolean;
  onLoadRunEvents: (runId: string) => void;
  selectedAuditEventCount: number;
  selectedResponse: AgentResponse | null;
  selectedResponseRecord: (AgentResponse & { model?: string; usage?: { total_tokens?: number } }) | null;
  selectedRunId: string;
  selectedThread: TaskThread | null;
}) {
  return (
    <div className="inspector-scroll">
      <div className="panel-heading">
        <div>
          <span>Current task</span>
          <h2>Review summary</h2>
        </div>
      </div>
      {selectedThread ? (
        <>
          <div className="kv-grid">
            <span>Status</span>
            <strong>{selectedThread.status}</strong>
            <span>Mode</span>
            <strong>{selectedResponse?.metadata?.mode || agentMode}</strong>
            <span>Session</span>
            <strong>{selectedThread.sessionId || "-"}</strong>
            <span>Run</span>
            <strong>{selectedRunId || "-"}</strong>
          </div>
          {selectedRunId && (
            <button
              aria-label="Load run events for selected task"
              className="primary-button"
              disabled={busy}
              onClick={() => onLoadRunEvents(selectedRunId)}
              title="Load run events for selected task"
              type="button"
            >
              <Activity size={15} />
              Load run events
            </button>
          )}
          <div className="response-summary">
            <div className="kv-grid">
              <span>Response</span>
              <strong>{selectedResponse?.id || "-"}</strong>
              <span>Model</span>
              <strong>{selectedResponseRecord?.model || "-"}</strong>
              <span>Events</span>
              <strong>{selectedAuditEventCount}</strong>
              <span>Tokens</span>
              <strong>{selectedResponseRecord?.usage?.total_tokens ?? "-"}</strong>
            </div>
          </div>
          <details className="raw-details">
            <summary>
              Raw response
              <ChevronDown size={14} />
            </summary>
            <JsonPanel value={selectedResponse} />
          </details>
        </>
      ) : (
        <div className="empty-mini review-empty">
          <ClipboardCheck size={24} />
          <strong>Review waits for a thread</strong>
          <span>No task selected.</span>
          <small>Start a run in the composer to populate response, model, token, approval, and event details.</small>
        </div>
      )}
    </div>
  );
}

export function InspectorPanel({
  agentMode,
  apiToken,
  busy,
  controlToken,
  currentIntent,
  endpoint,
  fullConsole,
  fullConsoleMessage,
  health,
  hermesStatus,
  hermesTools,
  inspectorTab,
  intentEnvelope,
  intentIdInput,
  intentIds,
  intentMessage,
  onAgentModeChange,
  onApiTokenChange,
  onControlTokenChange,
  onEndpointChange,
  onFetchIntent,
  onLoadRunEvents,
  onProfileChange,
  onRefreshHealth,
  onRefreshHermes,
  onSetInspectorTab,
  onSetIntentIdInput,
  onUpdateIntent,
  parity,
  profileName,
  selectedAuditEventCount,
  selectedResponse,
  selectedResponseRecord,
  selectedRunId,
  selectedThread,
  tools,
  userId
}: {
  agentMode: "finance_safe" | "hermes_full";
  apiToken: string;
  busy: boolean;
  controlToken: string;
  currentIntent: IntentRecord | null;
  endpoint: string;
  fullConsole: FullModeConsoleData;
  fullConsoleMessage: string;
  health: HealthDetailed | null;
  hermesStatus: HermesStatus | null;
  hermesTools: ToolCatalogItem[];
  inspectorTab: InspectorTab;
  intentEnvelope: ToolEnvelope | null;
  intentIdInput: string;
  intentIds: string[];
  intentMessage: string;
  onAgentModeChange: (value: "finance_safe" | "hermes_full") => void;
  onApiTokenChange: (value: string) => void;
  onControlTokenChange: (value: string) => void;
  onEndpointChange: (value: string) => void;
  onFetchIntent: (id?: string) => void;
  onLoadRunEvents: (runId: string) => void;
  onProfileChange: (profile: LocalProfile) => void;
  onRefreshHealth: () => void;
  onRefreshHermes: (options?: { keepInspector?: boolean }) => void;
  onSetInspectorTab: (tab: InspectorTab) => void;
  onSetIntentIdInput: (value: string) => void;
  onUpdateIntent: (action: "confirm" | "deny") => void;
  parity?: CapabilityParity;
  profileName: string;
  selectedAuditEventCount: number;
  selectedResponse: AgentResponse | null;
  selectedResponseRecord: (AgentResponse & { model?: string; usage?: { total_tokens?: number } }) | null;
  selectedRunId: string;
  selectedThread: TaskThread | null;
  tools: ToolCatalogItem[];
  userId: string;
}) {
  return (
    <aside className="inspector">
      <div className="inspector-tabs">
        {inspectorTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              aria-label={tab.label}
              aria-pressed={inspectorTab === tab.id}
              className={inspectorTab === tab.id ? "active" : ""}
              key={tab.id}
              onClick={() => onSetInspectorTab(tab.id)}
              title={tab.label}
              type="button"
            >
              <Icon size={15} />
            </button>
          );
        })}
      </div>

      {inspectorTab === "details" && (
        <RunDetailsPanel
          agentMode={agentMode}
          busy={busy}
          onLoadRunEvents={onLoadRunEvents}
          selectedAuditEventCount={selectedAuditEventCount}
          selectedResponse={selectedResponse}
          selectedResponseRecord={selectedResponseRecord}
          selectedRunId={selectedRunId}
          selectedThread={selectedThread}
        />
      )}

      {inspectorTab === "diagnostics" && (
        <DiagnosticsPanel
          busy={busy}
          controlToken={controlToken}
          fullConsole={fullConsole}
          health={health}
          hermesStatus={hermesStatus}
          message={fullConsoleMessage}
          onRefresh={onRefreshHermes}
          parity={parity}
        />
      )}

      {inspectorTab === "tools" && (
        <ToolCatalog
          apiToken={apiToken}
          controlToken={controlToken}
          endpoint={endpoint}
          hermesTools={hermesTools}
          tools={tools}
        />
      )}

      {inspectorTab === "skills" && (
        <div className="inspector-scroll">
          <SkillsPanel
            compact
            controlToken={controlToken}
            skillsPayload={
              (fullConsole.skills as { gated?: boolean; reason?: string; skills?: []; root?: string } | undefined) ||
              (controlToken.trim() ? { skills: [], root: "-" } : { gated: true, reason: "Control token required to inspect skills." })
            }
          />
        </div>
      )}

      {inspectorTab === "intents" && (
        <IntentsPanel
          busy={busy}
          controlToken={controlToken}
          compactValue={compact}
          currentIntent={currentIntent}
          intentEnvelope={intentEnvelope}
          intentIdInput={intentIdInput}
          intentIds={intentIds}
          intentMessage={intentMessage}
          onFetchIntent={onFetchIntent}
          onIntentInput={onSetIntentIdInput}
          onUpdateIntent={onUpdateIntent}
        />
      )}

      {inspectorTab === "settings" && (
        <SettingsWorkspace
          agentMode={agentMode}
          apiToken={apiToken}
          busy={busy}
          controlToken={controlToken}
          endpoint={endpoint}
          health={health}
          onAgentModeChange={onAgentModeChange}
          onApiTokenChange={onApiTokenChange}
          onControlTokenChange={onControlTokenChange}
          onEndpointChange={onEndpointChange}
          onProfileChange={onProfileChange}
          onRefresh={onRefreshHealth}
          profileName={profileName}
          userId={userId}
        />
      )}
    </aside>
  );
}
