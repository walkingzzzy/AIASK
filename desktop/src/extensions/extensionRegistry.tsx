import { Braces, Cable, CircleGauge, MessageSquareText, Puzzle, ShieldCheck } from "lucide-react";
import type { ElementType, ReactNode } from "react";
import { StatusBadge } from "../components/shared";
import type { MainView } from "../types";

export type ExtensionGroup = "agent" | "finance" | "ops" | "internal";
export type ExtensionMountPosition = "primary" | "secondary" | "hidden";
export type ExtensionSlotId =
  | "sidebar-top"
  | "sidebar-secondary"
  | "header-left"
  | "header-right"
  | "pre-main"
  | "post-main"
  | "overlay"
  | "workbench.quick-actions";

export const EXTENSION_SLOT_IDS: ExtensionSlotId[] = [
  "sidebar-top",
  "sidebar-secondary",
  "header-left",
  "header-right",
  "pre-main",
  "post-main",
  "overlay",
  "workbench.quick-actions",
];

export interface ExtensionRenderContext {
  controlToken: string;
  fullModeActive: boolean;
  onOpenView: (view: MainView) => void;
}

export interface InternalExtensionPage {
  id: MainView;
  label: string;
  group: ExtensionGroup;
  icon: ElementType;
  route: string;
  requiresControlToken?: boolean;
  requiresFullMode?: boolean;
  mountPosition: ExtensionMountPosition;
}

export interface InternalExtensionSlot {
  id: string;
  slot: ExtensionSlotId;
  label: string;
  group: ExtensionGroup;
  icon: ElementType;
  route?: string;
  requiresControlToken?: boolean;
  requiresFullMode?: boolean;
  mountPosition: ExtensionMountPosition;
  render: (context: ExtensionRenderContext) => ReactNode;
}

export const INTERNAL_EXTENSION_PAGES: InternalExtensionPage[] = [
  {
    id: "extensions-pilot",
    label: "扩展注册表",
    group: "internal",
    icon: Braces,
    route: "/extensions-pilot",
    requiresControlToken: true,
    mountPosition: "secondary",
  },
];

export const INTERNAL_EXTENSION_SLOTS: InternalExtensionSlot[] = [
  {
    id: "aiask.sessions.sidebar-top",
    slot: "sidebar-top",
    label: "会话",
    group: "agent",
    icon: MessageSquareText,
    route: "/sessions",
    requiresControlToken: true,
    requiresFullMode: true,
    mountPosition: "secondary",
    render: ({ controlToken, fullModeActive, onOpenView }) => (
      <button className="small-button" onClick={() => onOpenView("sessions")} type="button">
        <MessageSquareText size={13} />
        会话
        <StatusBadge status={controlToken.trim() && fullModeActive ? "ready" : "gated"} />
      </button>
    ),
  },
  {
    id: "aiask.readiness.header-left",
    slot: "header-left",
    label: "准备度 / 健康",
    group: "ops",
    icon: CircleGauge,
    route: "/readiness-health",
    mountPosition: "primary",
    render: ({ onOpenView }) => (
      <button className="small-button" onClick={() => onOpenView("readiness-health")} type="button">
        <CircleGauge size={13} />
        准备度
      </button>
    ),
  },
  {
    id: "aiask.gateway.header-right",
    slot: "header-right",
    label: "Gateway",
    group: "ops",
    icon: Cable,
    route: "/gateway",
    requiresControlToken: true,
    mountPosition: "primary",
    render: ({ controlToken, onOpenView }) => (
      <button className="small-button" onClick={() => onOpenView("gateway")} type="button">
        <Cable size={13} />
        Gateway
        <StatusBadge status={controlToken.trim() ? "ready" : "gated"} />
      </button>
    ),
  },
  {
    id: "aiask.plugins-skills.quick-action",
    slot: "workbench.quick-actions",
    label: "插件 / 技能生命周期",
    group: "ops",
    icon: Puzzle,
    route: "/plugins-skills",
    requiresControlToken: true,
    mountPosition: "primary",
    render: ({ controlToken, onOpenView }) => (
      <button className="small-button" onClick={() => onOpenView("plugins-skills")} type="button">
        <Puzzle size={13} />
        插件 / 技能
        <StatusBadge status={controlToken.trim() ? "ready" : "gated"} />
      </button>
    ),
  },
  {
    id: "aiask.extension-registry.sidebar-secondary",
    slot: "sidebar-secondary",
    label: "内部扩展注册表",
    group: "internal",
    icon: Braces,
    route: "/extensions-pilot",
    requiresControlToken: true,
    mountPosition: "secondary",
    render: ({ controlToken, onOpenView }) => (
      <button className="small-button" onClick={() => onOpenView("extensions-pilot")} type="button">
        <Braces size={13} />
        扩展
        <StatusBadge status={controlToken.trim() ? "ready" : "gated"} label="内部" technicalLabel="internal" />
      </button>
    ),
  },
  {
    id: "aiask.extension-registry.workbench-quick-action",
    slot: "workbench.quick-actions",
    label: "内部扩展注册表",
    group: "internal",
    icon: Braces,
    route: "/extensions-pilot",
    requiresControlToken: true,
    mountPosition: "secondary",
    render: ({ controlToken, onOpenView }) => (
      <button className="small-button" onClick={() => onOpenView("extensions-pilot")} type="button">
        <Braces size={13} />
        扩展
        <StatusBadge status={controlToken.trim() ? "ready" : "gated"} label="内部" technicalLabel="internal" />
      </button>
    ),
  },
];

export function getInternalSlots(slot: ExtensionSlotId): InternalExtensionSlot[] {
  return INTERNAL_EXTENSION_SLOTS.filter((item) => item.slot === slot);
}

export function getSupportedExtensionSlots(): ExtensionSlotId[] {
  return [...EXTENSION_SLOT_IDS];
}

export function SlotRenderer({
  slot,
  controlToken,
  fullModeActive,
  onOpenView,
}: ExtensionRenderContext & { slot: ExtensionSlotId }) {
  const entries = getInternalSlots(slot).filter((entry) => {
    if (entry.requiresControlToken && !controlToken.trim()) return true;
    if (entry.requiresFullMode && !fullModeActive) return true;
    return true;
  });

  if (!entries.length) return null;
  return <>{entries.map((entry) => <span className="extension-slot-item" key={`${entry.slot}:${entry.id}`}>{entry.render({ controlToken, fullModeActive, onOpenView })}</span>)}</>;
}

export function ExtensionsPilotPage({ controlToken, fullModeActive }: { controlToken: string; fullModeActive: boolean }) {
  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>内部扩展</span>
          <h1>扩展注册表</h1>
        </div>
        <div className="header-actions">
          <StatusBadge
            status={controlToken.trim() ? "ready" : "gated"}
            label={controlToken.trim() ? "控制已就绪" : "缺少控制令牌"}
            technicalLabel={controlToken.trim() ? "control ready" : "control token required"}
          />
          <StatusBadge status={fullModeActive ? "ready" : "gated"} label={fullModeActive ? "完整模式" : "金融安全模式"} />
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>AIASK 原生静态注册表</span>
              <h2>仅展示仓库内页面与插槽</h2>
              <p>这里不会加载或执行外部 JavaScript；注册内容必须是当前仓库中的 React 组件。</p>
            </div>
            <ShieldCheck size={22} />
          </div>

          <section className="capability-grid two">
            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{INTERNAL_EXTENSION_PAGES.length} 个页面</span>
                  <h3>页面注册表</h3>
                </div>
              </div>
              <div className="data-table">
                <div className="table-head">
                  <span>id</span>
                  <span>路由</span>
                  <span>挂载</span>
                  <span>门控</span>
                </div>
                {INTERNAL_EXTENSION_PAGES.map((page) => (
                  <div className="table-row" key={page.id}>
                    <strong>{page.id}</strong>
                    <span>{page.route}</span>
                    <span>{page.mountPosition}</span>
                    <span>{page.requiresControlToken ? "控制令牌" : "无"}{page.requiresFullMode ? " + 完整模式" : ""}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{INTERNAL_EXTENSION_SLOTS.length} 个入口 / {EXTENSION_SLOT_IDS.length} 个插槽</span>
                  <h3>插槽注册表</h3>
                </div>
              </div>
              <div className="data-table">
                <div className="table-head">
                  <span>id</span>
                  <span>slot</span>
                  <span>路由</span>
                  <span>挂载</span>
                </div>
                {INTERNAL_EXTENSION_SLOTS.map((entry) => (
                  <div className="table-row" key={entry.id}>
                    <strong>{entry.id}</strong>
                    <span>{entry.slot}</span>
                    <span>{entry.route || "-"}</span>
                    <span>{entry.mountPosition}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{EXTENSION_SLOT_IDS.length} 个可用插槽</span>
                  <h3>支持的插槽</h3>
                </div>
              </div>
              <div className="mini-list">
                {EXTENSION_SLOT_IDS.map((slot) => (
                  <article key={slot}>
                    <strong>{slot}</strong>
                    <span>{getInternalSlots(slot).length} 个已注册入口</span>
                  </article>
                ))}
              </div>
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}
