import { ChevronDown, ChevronRight, FolderGit2, Plus, Search, Terminal } from "lucide-react";
import { useMemo, useState } from "react";
import { SlotRenderer } from "../extensions/extensionRegistry";
import { IconButton, StatusBadge, statusLabel } from "./shared";
import type { HealthDetailed, HermesStatus, InspectorTab, MainView, TaskThread } from "../types";
import type { ViewGroup, ViewRegistryItem } from "../views";

function connectionSummary(status: string) {
  if (status === "AIASK_ONLINE") return { label: "在线", detail: "Agent 已连接" };
  if (status === "AIASK_DISCONNECTED") return { label: "未连接", detail: "等待连接 Agent" };
  return { label: statusLabel(status), detail: "需要查看连接状态" };
}

function fullModeSummary(enabled?: boolean) {
  return enabled ? "完整工具已启用" : "仅金融安全模式";
}

function looksLikeTechnicalId(value?: string) {
  return Boolean(value && /^[a-f0-9_-]{18,}$/i.test(value.trim()));
}

function shortId(value?: string) {
  if (!value) return "-";
  return value.length > 18 ? `${value.slice(0, 8)}...${value.slice(-6)}` : value;
}

function readableTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function threadSummary(thread: TaskThread) {
  const status = statusLabel(thread.status);
  const title = thread.title && !looksLikeTechnicalId(thread.title) ? thread.title : `${status}会话`;
  const lastSeen = thread.lastMessageAt ? `最近更新 ${readableTime(thread.lastMessageAt)}` : "等待新的运行记录";
  return {
    title,
    detail: `${status} · ${lastSeen}`,
    technical: shortId(thread.sessionId || thread.id),
  };
}

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
    <section className={`sidebar-nav-group ${advanced ? "advanced" : ""}`} aria-label={group.label} data-view-group-id={group.id}>
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
            <IconButton active={active} data-view-id={view.id} label={view.label} onClick={() => onSelectView(view.id)}>
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
  const connection = connectionSummary(status);
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
        新建线程
      </button>

      <div className="sidebar-project-card">
        <div>
          <span>项目 / 上下文</span>
          <strong>{health?.service || "本地 AIASK"}</strong>
          <small>{connection.detail} · {health?.host ? `${health.host}:${health.port || ""}` : "桌面客户端"}</small>
        </div>
        <StatusBadge status={status === "AIASK_ONLINE" ? "ready" : status} label={connection.label} />
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
          <span>任务线程</span>
          <small>{threads.length}</small>
        </div>
        <button className="thread-search-button" onClick={() => onSelectView("runs-events")} type="button">
          <Search size={14} />
          搜索与历史
        </button>
        <div className="thread-list">
          {threads.map((thread) => (
            <button
              className={selectedThreadId === thread.id ? "active" : ""}
              key={thread.id}
              onClick={() => onSelectThread(thread.id)}
              type="button"
            >
              {(() => {
                const item = threadSummary(thread);
                return (
                  <>
                    <strong>{item.title}</strong>
                    <span>{item.detail}</span>
                    <em>{item.technical}</em>
                  </>
                );
              })()}
            </button>
          ))}
          {!threads.length && (
            <div className="sidebar-empty">
              <strong>暂无线程</strong>
              <span>新建线程后，这里会收集提示词、运行、工具调用、审批和产物。</span>
            </div>
          )}
        </div>
      </div>

      <nav className="side-actions grouped" aria-label="Main navigation">
        <div className="section-label nav-label root-label">
          <FolderGit2 size={13} />
          <span>导航</span>
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
        <StatusBadge status={status} label={connection.label} />
        <span>{health?.tools?.count ?? 0} 个可用工具</span>
        <span>{fullModeSummary(hermesStatus?.full_mode_enabled)}</span>
      </div>
    </aside>
  );
}
