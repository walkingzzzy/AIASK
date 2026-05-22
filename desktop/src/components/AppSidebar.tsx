import { ChevronDown, FolderGit2, Plus, Terminal } from "lucide-react";
import { IconButton, StatusBadge } from "./shared";
import type { HealthDetailed, HermesStatus, InspectorTab, MainView, TaskThread } from "../types";
import type { ViewRegistryItem } from "../views";

export function AppSidebar({
  health,
  hermesStatus,
  inspectorTab,
  mainView,
  onNewTask,
  onSelectThread,
  onSelectView,
  selectedThreadId,
  status,
  threads,
  views
}: {
  health: HealthDetailed | null;
  hermesStatus: HermesStatus | null;
  inspectorTab: InspectorTab;
  mainView: MainView;
  onNewTask: () => void;
  onSelectThread: (id: string) => void;
  onSelectView: (view: MainView) => void;
  selectedThreadId?: string;
  status: string;
  threads: TaskThread[];
  views: ViewRegistryItem[];
}) {
  return (
    <aside className="sidebar">
      <div className="brand-row">
        <div className="brand-mark">
          <Terminal size={18} />
        </div>
        <div>
          <strong>AIASK</strong>
          <span>Agent Command Center</span>
        </div>
        <ChevronDown className="brand-chevron" size={15} />
      </div>

      <button className="new-task-button" onClick={onNewTask} type="button">
        <Plus size={16} />
        New Thread
      </button>

      <nav className="side-actions">
        <div className="section-label nav-label">
          <FolderGit2 size={13} />
          <span>Workspace</span>
        </div>
        {views.map((view) => {
          const Icon = view.icon;
          const active = mainView === view.id && (view.id !== "workbench" || inspectorTab === "details");
          return (
            <IconButton active={active} key={view.id} label={view.label} onClick={() => onSelectView(view.id)}>
              <Icon size={16} />
            </IconButton>
          );
        })}
      </nav>

      <div className="sidebar-section">
        <div className="section-label">
          <span>Threads</span>
          <small>{threads.length}</small>
        </div>
        <div className="thread-list">
          {threads.map((thread) => (
            <button
              className={selectedThreadId === thread.id ? "active" : ""}
              key={thread.id}
              onClick={() => onSelectThread(thread.id)}
              type="button"
            >
              <span>{thread.sessionId || thread.id}</span>
              <strong>{thread.title}</strong>
              <em>{thread.status}</em>
            </button>
          ))}
          {!threads.length && <p className="muted">Recent tasks will appear here.</p>}
        </div>
      </div>

      <div className="sidebar-footer">
        <StatusBadge status={status} label={status} />
        <span>{health?.tools?.count ?? 0} tools</span>
        <span>{hermesStatus?.full_mode_enabled ? "Hermes full ready" : "Hermes full off"}</span>
      </div>
    </aside>
  );
}
