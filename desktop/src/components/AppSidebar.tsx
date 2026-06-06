import { ChevronDown, FolderGit2, Plus, Terminal } from "lucide-react";
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
  return (
    <section className="sidebar-nav-group" aria-label={group.label}>
      <div className="section-label nav-label">
        <span>{group.label}</span>
      </div>
      {group.items.map((view: ViewRegistryItem) => {
        const Icon = view.icon;
        const active = mainView === view.id && (view.id !== "workbench" || inspectorTab === "details");
        return (
          <div className="sidebar-nav-item" key={view.id}>
            <IconButton active={active} label={view.label} onClick={() => onSelectView(view.id)}>
              <Icon size={16} />
            </IconButton>
            {(view.legacy || view.badge) && (
              <span className={`sidebar-nav-badge ${view.legacy ? "legacy" : ""}`}>
                {view.legacy ? "Legacy" : view.badge}
              </span>
            )}
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

  return (
    <aside className="sidebar app-sidebar">
      <div className="brand-row">
        <div className="brand-mark">
          <Terminal size={18} />
        </div>
        <div>
          <strong>AIASK</strong>
          <span>智能体量化工作台</span>
        </div>
        <ChevronDown className="brand-chevron" size={15} />
      </div>

      <button className="new-task-button" onClick={onNewTask} type="button">
        <Plus size={16} />
        新对话
      </button>

      <div className="extension-slot-row sidebar-slot">
        <SlotRenderer
          controlToken={controlToken}
          fullModeActive={fullModeActive}
          onOpenView={onSelectView}
          slot="sidebar-top"
        />
      </div>

      <nav className="side-actions grouped" aria-label="主导航">
        <div className="section-label nav-label root-label">
          <FolderGit2 size={13} />
          <span>应用导航</span>
        </div>
        {viewGroups.map((group) => (
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

      <div className="sidebar-section">
        <div className="section-label">
          <span>任务线程</span>
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
          {!threads.length && (
            <div className="sidebar-empty">
              <strong>暂无任务线程</strong>
              <span>发起一次对话后，会话、工具调用和审批状态会显示在这里。</span>
            </div>
          )}
        </div>
      </div>

      <div className="sidebar-footer">
        <StatusBadge status={status} label={status} />
        <span>{health?.tools?.count ?? 0} 个工具</span>
        <span>{hermesStatus?.full_mode_enabled ? "Hermes full 已启用" : "Hermes full 未启用"}</span>
      </div>
    </aside>
  );
}
