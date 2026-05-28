import { ChevronDown, FolderGit2, Plus, Settings, Terminal } from "lucide-react";
import { IconButton, StatusBadge } from "./shared";
import type { HealthDetailed, HermesStatus, InspectorTab, MainView, TaskThread } from "../types";
import type { ViewGroup, ViewRegistryItem } from "../views";

function SidebarNavGroup({
  group,
  inspectorTab,
  mainView,
  onSelectView
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
          <IconButton active={active} key={view.id} label={view.label} onClick={() => onSelectView(view.id)}>
            <Icon size={16} />
          </IconButton>
        );
      })}
    </section>
  );
}

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
  viewGroups
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
  viewGroups: ViewGroup[];
}) {
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
              <span>新对话后，会话、工具调用和审批状态会显示在这里。</span>
            </div>
          )}
        </div>
      </div>

      <div className="sidebar-footer">
        <button
          aria-label="设置"
          className={`settings-entry ${mainView === "settings" ? "active" : ""}`}
          onClick={() => onSelectView("settings")}
          type="button"
        >
          <Settings size={16} />
          <span>设置</span>
        </button>
        <StatusBadge status={status} label={status} />
        <span>{health?.tools?.count ?? 0} 个工具</span>
        <span>{hermesStatus?.full_mode_enabled ? "Hermes full 已开启" : "Hermes full 未开启"}</span>
      </div>
    </aside>
  );
}
