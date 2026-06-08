import { ChevronDown, ChevronRight, FolderGit2, Plus, Search, Terminal } from "lucide-react";
import { useMemo, useState } from "react";
import { SlotRenderer } from "../extensions/extensionRegistry";
import { IconButton, StatusBadge } from "./shared";
import type { HealthDetailed, HermesStatus, InspectorTab, MainView, TaskThread } from "../types";
import type { ViewGroup, ViewRegistryItem } from "../views";

function SidebarNavGroup({
  group,
  inspectorTab,
  mainView,
  onSelectView,
}: {
  group: ViewGroup;
  inspectorTab: InspectorTab;
  mainView: MainView;
  onSelectView: (view: MainView) => void;
}) {
  const [collapsed, setCollapsed] = useState(Boolean(group.defaultCollapsed));
  const advanced = group.id.startsWith("advanced") || group.id === "legacy";
  return (
    <section className={`sidebar-nav-group ${advanced ? "advanced" : ""}`} aria-label={group.label}>
      <button
        aria-label={group.label}
        className="section-label nav-label nav-group-toggle"
        onClick={() => setCollapsed((value) => !value)}
        title={group.label}
        type="button"
      >
        <span>{group.label}</span>
        {collapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
      </button>
      {!collapsed && group.items.map((view: ViewRegistryItem) => {
        const Icon = view.icon;
        const active = mainView === view.id && (view.id !== "workbench" || inspectorTab === "details");
        return (
          <div className="sidebar-nav-item" key={view.id}>
            <IconButton active={active} label={view.label} onClick={() => onSelectView(view.id)}>
              <Icon size={16} />
            </IconButton>
            {view.badge && <span className="sidebar-nav-badge">{view.badge}</span>}
          </div>
        );
      })}
    </section>
  );
}

export function AppSidebar({
  controlToken,
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
  viewGroups,
}: {
  controlToken: string;
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
  viewGroups: ViewGroup[];
}) {
  const fullModeActive = Boolean(health?.hermes?.full_mode_active || hermesStatus?.full_mode_active);
  const primaryGroups = useMemo(() => viewGroups.filter((group) => group.id === "primary"), [viewGroups]);
  const advancedGroups = useMemo(() => viewGroups.filter((group) => group.id !== "primary"), [viewGroups]);

  return (
    <aside className="sidebar app-sidebar">
      <div className="brand-row">
        <div className="brand-mark">
          <Terminal size={18} />
        </div>
        <div>
          <strong>AIASK</strong>
          <span>Agent 工作台</span>
        </div>
        <ChevronDown className="brand-chevron" size={15} />
      </div>

      <button className="new-task-button" onClick={onNewTask} type="button">
        <Plus size={16} />
        New thread
      </button>

      <div className="sidebar-project-card">
        <div>
          <span>Project / Context</span>
          <strong>{health?.service || "Local AIASK"}</strong>
          <small>{health?.host ? `${health.host}:${health.port || ""}` : "Desktop client"}</small>
        </div>
        <StatusBadge status={status === "AIASK_ONLINE" ? "ready" : status} label={status === "AIASK_ONLINE" ? "online" : status} />
      </div>

      <div className="extension-slot-row sidebar-slot">
        <SlotRenderer
          controlToken={controlToken}
          fullModeActive={fullModeActive}
          onOpenView={onSelectView}
          slot="sidebar-top"
        />
      </div>

      <div className="sidebar-section thread-section">
        <div className="section-label">
          <span>Threads</span>
          <small>{threads.length}</small>
        </div>
        <button className="thread-search-button" onClick={() => onSelectView("runs-events")} type="button">
          <Search size={14} />
          Search and history
        </button>
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
          {!threads.length && (
            <div className="sidebar-empty">
              <strong>No threads yet</strong>
              <span>Start a thread to collect prompts, runs, tool calls, approvals, and artifacts here.</span>
            </div>
          )}
        </div>
      </div>

      <nav className="side-actions grouped" aria-label="Main navigation">
        <div className="section-label nav-label root-label">
          <FolderGit2 size={13} />
          <span>Navigation</span>
        </div>
        {primaryGroups.map((group) => (
          <SidebarNavGroup
            group={group}
            inspectorTab={inspectorTab}
            key={group.id}
            mainView={mainView}
            onSelectView={onSelectView}
          />
        ))}
        {advancedGroups.map((group) => (
          <SidebarNavGroup
            group={group}
            inspectorTab={inspectorTab}
            key={group.id}
            mainView={mainView}
            onSelectView={onSelectView}
          />
        ))}
      </nav>

      <div className="extension-slot-row sidebar-slot secondary">
        <SlotRenderer
          controlToken={controlToken}
          fullModeActive={fullModeActive}
          onOpenView={onSelectView}
          slot="sidebar-secondary"
        />
      </div>

      <div className="sidebar-footer">
        <StatusBadge status={status} label={status} />
        <span>{health?.tools?.count ?? 0} tools</span>
        <span>{hermesStatus?.full_mode_enabled ? "Hermes full enabled" : "Hermes full off"}</span>
      </div>
    </aside>
  );
}
