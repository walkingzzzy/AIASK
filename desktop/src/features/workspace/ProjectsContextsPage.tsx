import { Database, FolderGit2, RefreshCw, ShieldCheck, Zap } from "lucide-react";
import { StatusBadge } from "../../components/shared";
import type { HealthDetailed, MainView } from "../../types";

export function ProjectsContextsPage({
  agentMode,
  apiToken,
  controlToken,
  defaultEndpoint,
  endpoint,
  health,
  mockMode,
  onOpenView,
  onRefresh,
  profileName,
  status,
  userId
}: {
  agentMode: "finance_safe" | "hermes_full";
  apiToken: string;
  controlToken: string;
  defaultEndpoint: string;
  endpoint: string;
  health: HealthDetailed | null;
  mockMode: boolean;
  onOpenView: (view: MainView) => void;
  onRefresh: () => void;
  profileName?: string;
  status: string;
  userId?: string;
}) {
  return (
    <section className="capabilities-workspace optimization-page">
      <header className="capabilities-header">
        <div>
          <span>Workspace</span>
          <h1>Projects / Contexts</h1>
          <p>Manage the current Agent endpoint, backend mode, operator profile, and readiness gates for thread-first work.</p>
        </div>
        <div className="header-actions">
          <StatusBadge status={mockMode ? "mock" : "live"} label={mockMode ? "mock" : "live"} />
          <StatusBadge status={status === "AIASK_ONLINE" ? "ready" : status} label={status === "AIASK_ONLINE" ? "online" : status} />
          <button className="small-button" onClick={onRefresh} type="button">
            <RefreshCw size={14} />
            Sync
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="optimization-grid">
          <article className="optimization-card">
            <FolderGit2 size={18} />
            <span>Context</span>
            <h2>{profileName || "Local workspace"}</h2>
            <p>User: {userId || "local"}</p>
            <p>Mode: {agentMode}</p>
          </article>
          <article className="optimization-card">
            <Database size={18} />
            <span>Endpoint</span>
            <h2>{endpoint}</h2>
            <p>Default: {defaultEndpoint}</p>
            <p>Service: {health?.service || "not loaded"}</p>
          </article>
          <article className="optimization-card">
            <ShieldCheck size={18} />
            <span>Access</span>
            <h2>{controlToken.trim() ? "Control ready" : "Control gated"}</h2>
            <p>API token: {apiToken.trim() ? "configured" : "missing"}</p>
            <p>Full mode: {health?.hermes?.full_mode_active ? "active" : "not active"}</p>
          </article>
        </div>

        <div className="capability-grid two">
          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>Recommended actions</span>
                <h3>Keep context visible</h3>
              </div>
              <Zap size={18} />
            </div>
            <div className="button-row">
              <button className="primary-button" onClick={() => onOpenView("settings")} type="button">Open Settings</button>
              <button className="small-button" onClick={() => onOpenView("readiness-health")} type="button">Readiness / Health</button>
              <button className="small-button" onClick={() => onOpenView("workbench")} type="button">Back to Workbench</button>
            </div>
          </section>
          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>Design note</span>
                <h3>Thread-first context</h3>
              </div>
            </div>
            <p className="muted">
              This page is the lightweight project/context hub for the current Desktop client. It keeps mock/live, endpoint,
              profile, token, and full-mode state in one place without adding backend dependencies.
            </p>
          </section>
        </div>
      </div>
    </section>
  );
}
