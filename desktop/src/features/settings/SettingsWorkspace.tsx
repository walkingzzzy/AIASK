import { ChevronDown, KeyRound, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { AutoField } from "../../components/AutoField";
import { JsonPanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { DesktopSettingsStatus, HealthDetailed, LocalProfile, SettingsFieldSchema } from "../../types";

const settingsSchema: SettingsFieldSchema[] = [
  {
    key: "endpoint",
    label: "Endpoint",
    type: "text",
    description: "AIASK agent API base URL, normally http://127.0.0.1:8767."
  },
  {
    key: "apiToken",
    label: "API token",
    type: "password",
    description: "Optional on trusted loopback deployments."
  },
  {
    key: "controlToken",
    label: "Control token",
    type: "password",
    description: "Required for full mode controls, plugins, skills, MCP management, and approvals."
  },
  {
    key: "agentMode",
    label: "Default mode",
    type: "select",
    description: "finance_safe remains the default operating boundary.",
    options: [
      { label: "finance_safe", value: "finance_safe" },
      { label: "hermes_full", value: "hermes_full" }
    ]
  }
];

export function SettingsWorkspace({
  endpoint,
  apiToken,
  controlToken,
  agentMode,
  health,
  busy,
  onEndpointChange,
  onApiTokenChange,
  onControlTokenChange,
  onAgentModeChange,
  onRefresh,
  userId,
  profileName,
  onProfileChange
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  agentMode: "finance_safe" | "hermes_full";
  health: HealthDetailed | null;
  busy: boolean;
  userId: string;
  profileName: string;
  onEndpointChange: (value: string) => void;
  onApiTokenChange: (value: string) => void;
  onControlTokenChange: (value: string) => void;
  onAgentModeChange: (value: "finance_safe" | "hermes_full") => void;
  onRefresh: () => void;
  onProfileChange: (profile: LocalProfile) => void;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [settingsStatus, setSettingsStatus] = useState<DesktopSettingsStatus | null>(null);
  const [draftUserId, setDraftUserId] = useState(userId);
  const [draftProfileName, setDraftProfileName] = useState(profileName);
  const [message, setMessage] = useState("NOT_LOADED");
  const [statusBusy, setStatusBusy] = useState(false);
  const values = { endpoint, apiToken, controlToken, agentMode };
  const setters = {
    endpoint: onEndpointChange,
    apiToken: onApiTokenChange,
    controlToken: onControlTokenChange,
    agentMode: (value: string) => onAgentModeChange(value as "finance_safe" | "hermes_full")
  };

  async function refreshStatus() {
    setStatusBusy(true);
    try {
      const payload = await api.settingsStatus();
      setSettingsStatus(payload);
      setDraftUserId(payload.profile.user_id);
      setDraftProfileName(payload.profile.profile_name);
      onProfileChange(payload.profile);
      setMessage("SETTINGS_STATUS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setStatusBusy(false);
    }
  }

  async function saveProfile() {
    setStatusBusy(true);
    try {
      const profile = await api.localProfileSave({ user_id: draftUserId, profile_name: draftProfileName });
      onProfileChange(profile);
      setSettingsStatus((current) => current ? { ...current, profile } : current);
      setMessage("LOCAL_PROFILE_SAVED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setStatusBusy(false);
    }
  }

  useEffect(() => {
    refreshStatus().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  const llm = settingsStatus?.llm.ai_status;
  const databases = settingsStatus?.databases || {};

  return (
    <div className="inspector-scroll settings-workspace">
      <div className="panel-heading">
        <div>
          <span>Settings</span>
          <h2>Configuration center</h2>
        </div>
        <button className="small-button" disabled={busy || statusBusy} onClick={refreshStatus} type="button">
          <RefreshCw size={14} className={statusBusy ? "spin" : ""} />
          Refresh
        </button>
      </div>

      <section className="settings-form-grid">
        {settingsSchema.map((schema) => (
          <AutoField
            key={schema.key}
            schema={schema}
            value={values[schema.key]}
            onChange={setters[schema.key]}
          />
        ))}
      </section>

      <div className="capability-section compact-section">
        <div className="section-header">
          <div>
            <span>Full Mode</span>
            <h3>Hermes control readiness</h3>
          </div>
          <StatusBadge status={health?.hermes?.full_mode_enabled && health?.control?.token_configured ? "implemented" : "gated"} />
        </div>
        <div className="kv-grid">
          <span>Full mode</span>
          <strong>{health?.hermes?.full_mode_enabled ? "enabled" : "set AIASK_AGENT_ENABLE_HERMES_FULL=1"}</strong>
          <span>Control token</span>
          <strong>{health?.control?.token_configured ? "configured" : "set AIASK_AGENT_CONTROL_TOKEN"}</strong>
        </div>
      </div>

      <div className="capability-section compact-section">
        <div className="section-header">
          <div>
            <span>LLM</span>
            <h3>Provider and model</h3>
          </div>
          <StatusBadge status={llm?.configured ? "implemented" : "unconfigured"} label={llm?.provider || "not loaded"} />
        </div>
        <div className="kv-grid">
          <span>Model</span>
          <strong>{llm?.model || "-"}</strong>
          <span>Base URL</span>
          <strong>{llm?.base_url_configured ? "configured" : "default"}</strong>
          <span>API key</span>
          <strong>{llm?.api_key_configured ? "configured" : "missing/mock"}</strong>
          <span>Config source</span>
          <strong>{llm?.config_source?.loaded ? `${llm.config_source.source || "project"} .env` : "process env"}</strong>
          <span>Secrets</span>
          <strong>{llm?.secrets_redacted ? "redacted" : "not loaded"}</strong>
        </div>
      </div>

      <div className="capability-section compact-section">
        <div className="section-header">
          <div>
            <span>Databases</span>
            <h3>Storage paths</h3>
          </div>
          <StatusBadge status="implemented" label="local" />
        </div>
        <div className="kv-grid">
          <span>Agent state</span>
          <strong>{compact((databases.agent_state as Record<string, unknown> | undefined)?.path)}</strong>
          <span>Intent state</span>
          <strong>{compact((databases.intent_state as Record<string, unknown> | undefined)?.path)}</strong>
          <span>Quant state</span>
          <strong>{compact((databases.quant_research as Record<string, unknown> | undefined)?.path)}</strong>
          <span>AKShare DB</span>
          <strong>{compact((databases.akshare as Record<string, unknown> | undefined)?.path)}</strong>
        </div>
      </div>

      <div className="capability-section compact-section">
        <div className="section-header">
          <div>
            <span>Local user</span>
            <h3>Profile scope</h3>
          </div>
          <StatusBadge status={settingsStatus?.profile.status || "ready"} />
        </div>
        <label className="field-row">
          <span>User ID</span>
          <input value={draftUserId} onChange={(event) => setDraftUserId(event.target.value)} />
        </label>
        <label className="field-row">
          <span>Profile name</span>
          <input value={draftProfileName} onChange={(event) => setDraftProfileName(event.target.value)} />
        </label>
        <button className="small-button" disabled={busy || statusBusy || !draftUserId.trim() || !draftProfileName.trim()} onClick={saveProfile} type="button">
          Save profile
        </button>
      </div>

      <button className="primary-button" disabled={busy} onClick={onRefresh} type="button">
        <KeyRound size={15} />
        Test connection
      </button>
      <details className="raw-details">
        <summary>
          Health and settings
          <ChevronDown size={14} />
        </summary>
        <p className="status-line">{message}</p>
        <JsonPanel value={{ health, settingsStatus }} />
      </details>
    </div>
  );
}
