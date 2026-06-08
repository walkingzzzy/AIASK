import {
  Activity,
  ChevronDown,
  ClipboardCheck,
  FileSearch,
  Layers3,
  MessageSquare,
  PanelRight,
  RefreshCw,
  Settings,
  ShieldCheck,
  Square,
  Trash2,
  Wrench,
  XCircle
} from "lucide-react";
import type { ElementType } from "react";
import { useMemo, useState } from "react";
import { formatApiError } from "../api";
import { DiagnosticsPanel } from "./DiagnosticsPanel";
import { GeneralApprovalsPanel, IntentsPanel, ToolCatalog } from "./InspectorPanels";
import { ArtifactsPanel, ReviewPanel, buildTaskArtifacts, buildTaskReviewComments } from "./TaskPanels";
import { ConfirmActionButton, EmptyState, RawEvidencePanel, compact } from "./shared";
import { AiaskApi } from "../services/aiaskApi";
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
  ResponseRecord,
  RunRecord,
  TaskThread,
  ToolCatalogItem,
  ToolEnvelope
} from "../types";

const inspectorTabs: Array<{ id: InspectorTab; label: string; icon: ElementType }> = [
  { id: "details", label: "Summary", icon: PanelRight },
  { id: "artifacts", label: "Artifacts", icon: FileSearch },
  { id: "review", label: "Review", icon: MessageSquare },
  { id: "diagnostics", label: "Diagnostics", icon: Activity },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "skills", label: "Skills", icon: Layers3 },
  { id: "intents", label: "Approvals", icon: ShieldCheck },
  { id: "settings", label: "Settings", icon: Settings }
];

function RunDetailsPanel({
  agentMode,
  apiToken,
  busy,
  controlToken,
  endpoint,
  onLoadRunEvents,
  onRemoveResponseThread,
  selectedAuditEventCount,
  selectedResponse,
  selectedResponseRecord,
  selectedRunId,
  selectedThread
}: {
  agentMode: "finance_safe" | "hermes_full";
  apiToken: string;
  busy: boolean;
  controlToken: string;
  endpoint: string;
  onLoadRunEvents: (runId: string) => void;
  onRemoveResponseThread: (responseId: string) => void;
  selectedAuditEventCount: number;
  selectedResponse: AgentResponse | null;
  selectedResponseRecord: (AgentResponse & { model?: string; usage?: { total_tokens?: number } }) | null;
  selectedRunId: string;
  selectedThread: TaskThread | null;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [runDetail, setRunDetail] = useState<RunRecord | null>(null);
  const [responseDetail, setResponseDetail] = useState<ResponseRecord | null>(null);
  const [steerInstruction, setSteerInstruction] = useState("");
  const [actionResult, setActionResult] = useState<unknown>(null);
  const [message, setMessage] = useState("READY");
  const [localBusy, setLocalBusy] = useState(false);
  const disabled = busy || localBusy;
  const responseId = selectedResponse?.id || selectedThread?.response?.id || "";

  async function runAction(action: "detail" | "cancel" | "stop" | "steer") {
    if (!selectedRunId) return;
    setLocalBusy(true);
    setMessage(`RUN_${action.toUpperCase()}_RUNNING`);
    try {
      const result =
        action === "detail"
          ? await api.runGet(selectedRunId)
          : action === "cancel"
            ? await api.runCancel(selectedRunId)
            : action === "stop"
              ? await api.runStop(selectedRunId)
              : await api.runSteer(selectedRunId, steerInstruction.trim());
      setActionResult(result);
      if (action === "detail") setRunDetail(result as RunRecord);
      setMessage(`RUN_${action.toUpperCase()}_OK`);
      if (action !== "detail") onLoadRunEvents(selectedRunId);
      if (action === "steer") setSteerInstruction("");
    } catch (error) {
      setMessage(formatApiError(error));
      setActionResult({ success: false, error: formatApiError(error) });
    } finally {
      setLocalBusy(false);
    }
  }

  async function loadResponse() {
    if (!responseId) return;
    setLocalBusy(true);
    setMessage("RESPONSE_LOADING");
    try {
      const result = await api.responseGet(responseId);
      setResponseDetail(result);
      setActionResult(result);
      setMessage("RESPONSE_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
      setActionResult({ success: false, error: formatApiError(error) });
    } finally {
      setLocalBusy(false);
    }
  }

  async function deleteResponse() {
    if (!responseId) return;
    setLocalBusy(true);
    setMessage("RESPONSE_DELETE_RUNNING");
    try {
      const result = await api.responseDelete(responseId);
      setActionResult(result);
      setMessage(result.deleted ? "RESPONSE_DELETED" : "RESPONSE_DELETE_NOOP");
      onRemoveResponseThread(responseId);
    } catch (error) {
      setMessage(formatApiError(error));
      setActionResult({ success: false, error: formatApiError(error) });
    } finally {
      setLocalBusy(false);
    }
  }

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
            <div className="button-row">
              <button
                aria-label="Load events for the selected run"
                className="primary-button"
                disabled={disabled}
                onClick={() => onLoadRunEvents(selectedRunId)}
                title="Load run events"
                type="button"
              >
                <Activity size={15} />
                Load events
              </button>
              <button className="small-button" disabled={disabled} onClick={() => runAction("detail")} type="button">
                <RefreshCw size={14} />
                Details
              </button>
              <ConfirmActionButton
                actionLabel="取消运行"
                className="small-button"
                confirmDetail={`Run: ${selectedRunId}`}
                disabled={disabled}
                isDanger
                onConfirmed={() => runAction("cancel")}
              >
                <XCircle size={14} />
                Cancel
              </ConfirmActionButton>
              <ConfirmActionButton
                actionLabel="停止运行"
                className="small-button"
                confirmDetail={`Run: ${selectedRunId}`}
                disabled={disabled}
                isDanger
                onConfirmed={() => runAction("stop")}
              >
                <Square size={14} />
                Stop
              </ConfirmActionButton>
            </div>
          )}
          {selectedRunId && (
            <div className="inline-form">
              <input
                value={steerInstruction}
                onChange={(event) => setSteerInstruction(event.target.value)}
                placeholder="Add a steer instruction to the current run"
              />
              <button disabled={disabled || !steerInstruction.trim()} onClick={() => runAction("steer")} type="button">
                <MessageSquare size={14} />
                Steer
              </button>
            </div>
          )}
          <div className="response-summary">
            <div className="kv-grid">
              <span>Response</span>
              <strong>{responseId || "-"}</strong>
              <span>Model</span>
              <strong>{selectedResponseRecord?.model || "-"}</strong>
              <span>Events</span>
              <strong>{selectedAuditEventCount}</strong>
              <span>Token</span>
              <strong>{selectedResponseRecord?.usage?.total_tokens ?? "-"}</strong>
            </div>
            <div className="button-row">
              <button className="small-button" disabled={disabled || !responseId} onClick={loadResponse} type="button">
                <RefreshCw size={14} />
                Reload
              </button>
              <ConfirmActionButton
                actionLabel="删除响应"
                className="small-button"
                confirmDetail={`Response: ${responseId}`}
                disabled={disabled || !responseId}
                isDanger
                onConfirmed={deleteResponse}
              >
                <Trash2 size={14} />
                Delete
              </ConfirmActionButton>
            </div>
          </div>
          <p className="status-line">{message}</p>
          {(runDetail || responseDetail || actionResult) && (
            <RawEvidencePanel title="Run / Response result" value={{ runDetail, responseDetail, actionResult }} />
          )}
          <RawEvidencePanel title="Raw response" value={selectedResponse} />
        </>
      ) : (
        <EmptyState
          body="Start a task or select a thread to review responses, model usage, approvals, and events."
          icon={<ClipboardCheck size={24} />}
          title="No selected thread"
        />
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
  onRemoveResponseThread,
  onSetInspectorTab,
  onSetIntentIdInput,
  onUpdateIntent,
  parity,
  profileName,
  recentRuns,
  selectedAuditEventCount,
  selectedResponse,
  selectedResponseRecord,
  selectedRunId,
  selectedThread,
  timelineEvents,
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
  onRemoveResponseThread: (responseId: string) => void;
  onSetInspectorTab: (tab: InspectorTab) => void;
  onSetIntentIdInput: (value: string) => void;
  onUpdateIntent: (action: "confirm" | "deny") => void;
  parity?: CapabilityParity;
  profileName: string;
  recentRuns: import("../types").DesktopRunSummary[];
  selectedAuditEventCount: number;
  selectedResponse: AgentResponse | null;
  selectedResponseRecord: (AgentResponse & { model?: string; usage?: { total_tokens?: number } }) | null;
  selectedRunId: string;
  selectedThread: TaskThread | null;
  timelineEvents: import("../types").TimelineEvent[];
  tools: ToolCatalogItem[];
  userId: string;
}) {
  const artifacts = buildTaskArtifacts({ selectedThread, selectedResponse, recentRuns, timelineEvents });
  const comments = buildTaskReviewComments(artifacts);

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
          apiToken={apiToken}
          busy={busy}
          controlToken={controlToken}
          endpoint={endpoint}
          onLoadRunEvents={onLoadRunEvents}
          onRemoveResponseThread={onRemoveResponseThread}
          selectedAuditEventCount={selectedAuditEventCount}
          selectedResponse={selectedResponse}
          selectedResponseRecord={selectedResponseRecord}
          selectedRunId={selectedRunId}
          selectedThread={selectedThread}
        />
      )}

      {inspectorTab === "artifacts" && (
        <div className="inspector-scroll">
          <ArtifactsPanel artifacts={artifacts} />
        </div>
      )}

      {inspectorTab === "review" && (
        <div className="inspector-scroll">
          <ReviewPanel comments={comments} />
        </div>
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
              (controlToken.trim() ? { skills: [], root: "-" } : { gated: true, reason: "需要 Control token 才能查看技能。" })
            }
          />
        </div>
      )}

      {inspectorTab === "intents" && (
        <div className="inspector-scroll">
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
          <GeneralApprovalsPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} />
        </div>
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
