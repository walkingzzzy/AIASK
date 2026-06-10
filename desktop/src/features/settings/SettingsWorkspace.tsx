import {
  Archive,
  ArrowLeft,
  Bot,
  BrainCircuit,
  CalendarClock,
  Cable,
  ChevronDown,
  Database,
  Factory,
  Globe2,
  KeyRound,
  Laptop,
  Layers3,
  Monitor,
  RefreshCw,
  RotateCcw,
  ServerCog,
  ShieldCheck,
  SlidersHorizontal,
  Webhook,
  Wrench
} from "lucide-react";
import type { ElementType, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError, normalizeEndpoint } from "../../api";
import { JsonPanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload, DesktopSettingsStatus, HealthDetailed, LocalProfile, MainView } from "../../types";
import { CapabilitiesWorkspace } from "../capabilities/CapabilitiesWorkspace";
import { AutomationWorkspace } from "../automation/AutomationWorkspace";
import { IntegrationsManagementPanel } from "./IntegrationsManagementPanel";
import { LearningRlPanel } from "./LearningRlPanel";
import { SecurityPanel } from "./SecurityPanel";
import { SkillsPanel } from "../skills/SkillsPanel";
import { WebhooksPanel } from "./WebhooksPanel";

type SettingsSectionId =
  | "general"
  | "connection"
  | "tokens"
  | "models"
  | "mcp"
  | "skillsManagement"
  | "automationManagement"
  | "integrations"
  | "webhooks"
  | "pluginsManagement"
  | "learningRl"
  | "security"
  | "workflow"
  | "data"
  | "advanced"
  | "about";

type SettingsSectionGroup = "基础设置" | "高级管理" | "状态与入口";

const SETTINGS_SECTIONS: Array<{
  id: SettingsSectionId;
  label: string;
  description: string;
  icon: ElementType;
  group: SettingsSectionGroup;
}> = [
  { id: "general", label: "常规", description: "默认模式、本地用户和基础行为", icon: SlidersHorizontal, group: "基础设置" },
  { id: "connection", label: "连接", description: "Agent 端点与连接恢复", icon: Globe2, group: "基础设置" },
  { id: "tokens", label: "令牌与权限", description: "API 令牌、控制令牌和完整模式", icon: KeyRound, group: "基础设置" },
  { id: "skillsManagement", label: "技能管理", description: "安装、更新、删除和原始快照", icon: Layers3, group: "高级管理" },
  { id: "automationManagement", label: "自动化管理", description: "高级调度、工具集和删除任务", icon: CalendarClock, group: "高级管理" },
  { id: "integrations", label: "应用集成", description: "连接器、Gateway 平台与消息审批", icon: Cable, group: "高级管理" },
  { id: "webhooks", label: "Webhook", description: "订阅、删除与受控触发", icon: Webhook, group: "高级管理" },
  { id: "pluginsManagement", label: "插件与技能包", description: "原生插件和 skill pack 治理", icon: Wrench, group: "高级管理" },
  { id: "models", label: "模型状态", description: "只读查看 LLM 提供方、模型和密钥状态", icon: Bot, group: "状态与入口" },
  { id: "mcp", label: "MCP 管理入口", description: "进入 MCP 服务、资源、提示词和 OAuth 页面", icon: ServerCog, group: "状态与入口" },
  { id: "workflow", label: "工作流入口", description: "进入数据、策略、因子、孵化和工厂事件", icon: Factory, group: "状态与入口" },
  { id: "data", label: "数据路径", description: "只读查看本地数据库与量化数据路径", icon: Database, group: "状态与入口" },
  { id: "learningRl", label: "学习 / RL", description: "学习建议、RL 运行和结果", icon: BrainCircuit, group: "状态与入口" },
  { id: "security", label: "安全扫描", description: "扫描与修复建议", icon: ShieldCheck, group: "状态与入口" },
  { id: "advanced", label: "高级诊断入口", description: "进入能力、工具、诊断和状态台账", icon: Wrench, group: "状态与入口" },
  { id: "about", label: "关于", description: "版本、API 契约和原始状态", icon: Laptop, group: "状态与入口" }
];

const SETTINGS_SECTION_GROUPS: SettingsSectionGroup[] = ["基础设置", "高级管理", "状态与入口"];

const workflowShortcuts: Array<{ id: MainView; label: string; description: string; icon: ElementType }> = [
  { id: "data", label: "数据与同步", description: "配置数据源、同步计划和数据新鲜度检查。", icon: Database },
  { id: "quant", label: "量化研究", description: "运行结构化量化研究并查看报告。", icon: BrainCircuit },
  { id: "strategy-factory", label: "策略工厂", description: "进入策略生成、运行和评审流程。", icon: Factory },
  { id: "factor-factory", label: "因子工厂", description: "查看因子挖掘、活跃池和引擎健康。", icon: Factory },
  { id: "incubation", label: "孵化工厂", description: "检查生命周期、命中率报告和晋升信号。", icon: ShieldCheck },
  { id: "factory-events", label: "工厂事件", description: "创建、预览和审批工厂事件。", icon: CalendarClock }
];

const advancedShortcuts: Array<{ id: MainView; label: string; description: string; icon: ElementType }> = [
  { id: "overview", label: "运行概览", description: "系统运行摘要，作为对话页内模块和高级入口保留。", icon: SlidersHorizontal },
  { id: "coverage", label: "能力覆盖矩阵", description: "查看已实现、部分就绪、已阻塞等能力状态。", icon: ShieldCheck },
  { id: "tools", label: "工具目录", description: "打开工具目录、详情和受控测试入口。", icon: Wrench },
  { id: "capabilities", label: "能力中心", description: "查看 Hermes、MCP、插件、AI 和工厂能力台账。", icon: Laptop },
  { id: "diagnostics", label: "诊断", description: "查看准备度、进程、浏览器、终端和 Gateway 信息。", icon: Monitor },
  { id: "agent", label: "智能体状态", description: "查看 Agent 健康、授权、工具组和完整模式状态。", icon: Bot },
  { id: "user", label: "本地用户", description: "打开本地画像的独立管理页。", icon: SlidersHorizontal },
  { id: "event-console", label: "事件控制台", description: "查看事件流、详情和错误展示。", icon: Archive }
];

function SettingsCard({
  children,
  description,
  status,
  statusLabel,
  title
}: {
  children: ReactNode;
  description?: string;
  status?: string;
  statusLabel?: string;
  title: string;
}) {
  return (
    <section className="settings-card">
      <div className="settings-card-head">
        <div>
          <h3>{title}</h3>
          {description && <p>{description}</p>}
        </div>
        {status && <StatusBadge status={status} label={statusLabel} />}
      </div>
      <div className="settings-card-body">{children}</div>
    </section>
  );
}

function SettingsRow({ children, description, title }: { children: ReactNode; description?: string; title: string }) {
  return (
    <label className="settings-row">
      <div>
        <strong>{title}</strong>
        {description && <span>{description}</span>}
      </div>
      {children}
    </label>
  );
}

function ShortcutGrid({
  items,
  onOpenView
}: {
  items: Array<{ id: MainView; label: string; description: string; icon: ElementType }>;
  onOpenView?: (view: MainView) => void;
}) {
  return (
    <div className="settings-shortcut-grid">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <button
            className="settings-shortcut"
            disabled={!onOpenView}
            key={item.id}
            onClick={() => onOpenView?.(item.id)}
            type="button"
          >
            <Icon size={16} />
            <strong>{item.label}</strong>
            <span>{item.description}</span>
          </button>
        );
      })}
    </div>
  );
}

export function SettingsWorkspace({
  endpoint,
  apiToken,
  controlToken,
  agentMode,
  health,
  busy,
  connectionStatus = "AIASK_DISCONNECTED",
  defaultEndpoint = "http://127.0.0.1:8767",
  onEndpointChange,
  onApiTokenChange,
  onControlTokenChange,
  onAgentModeChange,
  onRefresh,
  onResetEndpoint,
  onBackToApp,
  onOpenView,
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
  connectionStatus?: string;
  defaultEndpoint?: string;
  userId: string;
  profileName: string;
  onEndpointChange: (value: string) => void;
  onApiTokenChange: (value: string) => void;
  onControlTokenChange: (value: string) => void;
  onAgentModeChange: (value: "finance_safe" | "hermes_full") => void;
  onRefresh: () => void;
  onResetEndpoint?: () => void;
  onBackToApp?: () => void;
  onOpenView?: (view: MainView) => void;
  onProfileChange: (profile: LocalProfile) => void;
}) {
  const normalizedEndpoint = normalizeEndpoint(endpoint);
  const normalizedDefaultEndpoint = normalizeEndpoint(defaultEndpoint);
  const api = useMemo(() => new AiaskApi({ endpoint: normalizedEndpoint, apiToken, controlToken }), [apiToken, controlToken, normalizedEndpoint]);
  const [activeSection, setActiveSection] = useState<SettingsSectionId>("general");
  const [settingsStatus, setSettingsStatus] = useState<DesktopSettingsStatus | null>(null);
  const [managedSkillsPayload, setManagedSkillsPayload] = useState<CapabilityWorkbenchPayload["skills"] | null>(null);
  const [draftUserId, setDraftUserId] = useState(userId);
  const [draftProfileName, setDraftProfileName] = useState(profileName);
  const [message, setMessage] = useState("NOT_LOADED");
  const [statusBusy, setStatusBusy] = useState(false);

  const usesNonDefaultEndpoint = normalizedEndpoint !== normalizedDefaultEndpoint;
  const connectionIssue =
    connectionStatus !== "AIASK_ONLINE" && connectionStatus !== "AIASK_DISCONNECTED"
      ? connectionStatus
      : message !== "SETTINGS_STATUS_LOADED" && message !== "NOT_LOADED"
        ? message
        : "";
  const showEndpointRecovery = usesNonDefaultEndpoint && !!connectionIssue;
  const fullModeEnabled = Boolean(health?.hermes?.full_mode_enabled);
  const generalFullToolset = Boolean(health?.tools?.toolset === "general_full" || health?.hermes?.full_mode_active);
  const controlTokenConfigured = Boolean(health?.control?.token_configured);
  const controlAuthorized = Boolean((settingsStatus?.agent as { control_authorized?: boolean } | undefined)?.control_authorized);
  const controlReason = String((settingsStatus?.agent as { control_reason?: string | null } | undefined)?.control_reason || "");
  const hasControlTokenInput = Boolean(controlToken.trim());
  const fullModeReady = fullModeEnabled && generalFullToolset && controlTokenConfigured && hasControlTokenInput && controlAuthorized;
  const llm = settingsStatus?.llm?.ai_status;
  const databases = settingsStatus?.databases || {};

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
      setSettingsStatus((current) => (current ? { ...current, profile } : current));
      setMessage("LOCAL_PROFILE_SAVED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setStatusBusy(false);
    }
  }

  async function refreshManagedSkills() {
    if (!controlToken.trim()) {
      setManagedSkillsPayload({ gated: true, reason: "control token is not configured" });
      return null;
    }
    try {
      const payload = await api.skillsList();
      setManagedSkillsPayload(payload);
      return payload;
    } catch (error) {
      const reason = formatApiError(error);
      const payload = { gated: true, reason };
      setManagedSkillsPayload(payload);
      return payload;
    }
  }

  useEffect(() => {
    refreshStatus().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalizedEndpoint, apiToken, controlToken]);

  useEffect(() => {
    if (activeSection === "skillsManagement") {
      refreshManagedSkills().catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSection, normalizedEndpoint, controlToken]);

  return (
    <div className="settings-shell">
      <aside className="settings-nav">
        <button className="settings-back" onClick={onBackToApp} type="button">
          <ArrowLeft size={15} />
          返回对话
        </button>
        <div className="settings-nav-title">
          <strong>设置</strong>
          <span>可操作设置、管理入口与只读状态</span>
        </div>
        <nav aria-label="设置导航">
          {SETTINGS_SECTION_GROUPS.map((group) => (
            <div className="settings-nav-group" key={group}>
              <span className="settings-nav-group-label">{group}</span>
              {SETTINGS_SECTIONS.filter((section) => section.group === group).map((section) => {
                const Icon = section.icon;
                return (
                  <button
                    className={activeSection === section.id ? "active" : ""}
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    type="button"
                  >
                    <Icon size={16} />
                    <span>{section.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      <section className="settings-content inspector-scroll">
        <header className="settings-content-header">
          <div>
            <span>设置</span>
            <h1>设置中心</h1>
            <p>只保留真实可操作设置；模型、MCP、工作流、数据和诊断以只读状态或打开页面入口呈现。</p>
          </div>
          <button className="small-button" disabled={busy || statusBusy} onClick={refreshStatus} type="button">
            <RefreshCw size={14} className={statusBusy ? "spin" : ""} />
            刷新
          </button>
        </header>

        {activeSection === "general" && (
          <div className="settings-section-stack">
            <SettingsCard title="默认行为" description="设置智能体默认模式和本地用户身份。" status="ready" statusLabel="本地">
              <SettingsRow title="默认模式" description="finance_safe 用于日常金融研究；hermes_full 需要控制令牌和完整模式。">
                <select value={agentMode} onChange={(event) => onAgentModeChange(event.target.value as "finance_safe" | "hermes_full")}>
                  <option value="finance_safe">finance_safe</option>
                  <option value="hermes_full">hermes_full</option>
                </select>
              </SettingsRow>
              <SettingsRow title="用户 ID" description="用于会话、研究运行和本地存储作用域。">
                <input value={draftUserId} onChange={(event) => setDraftUserId(event.target.value)} />
              </SettingsRow>
              <SettingsRow title="画像名称" description="显示在对话、任务和本地用户页面。">
                <input value={draftProfileName} onChange={(event) => setDraftProfileName(event.target.value)} />
              </SettingsRow>
              <div className="settings-actions">
                <button className="small-button" disabled={busy || statusBusy || !draftUserId.trim() || !draftProfileName.trim()} onClick={saveProfile} type="button">
                  保存画像
                </button>
              </div>
            </SettingsCard>
          </div>
        )}

        {activeSection === "connection" && (
          <div className="settings-section-stack">
            <SettingsCard title="Agent 连接" description="只有健康检查成功后，当前 Agent 端点才会被标记为已验证。" status={connectionStatus === "AIASK_ONLINE" ? "implemented" : usesNonDefaultEndpoint ? "gated" : "ready"} statusLabel={connectionStatus}>
              <SettingsRow title="Agent 端点" description="AIASK Agent API 地址，默认使用 http://127.0.0.1:8767。">
                <input value={endpoint} onChange={(event) => onEndpointChange(event.target.value)} />
              </SettingsRow>
              {showEndpointRecovery ? (
                <div className="notice warn" role="status">
                  当前端点 {normalizedEndpoint} 不可达（{connectionIssue}）。建议恢复到默认本地 Agent 端点 {normalizedDefaultEndpoint}，然后执行“测试连接”。
                </div>
              ) : (
                <p className="muted">请先在 {normalizedDefaultEndpoint} 启动本地 Agent，再执行“测试连接”。通过后才会保存为已验证端点。</p>
              )}
              <div className="settings-actions">
                <button className="primary-button" disabled={busy} onClick={onRefresh} type="button">
                  <KeyRound size={15} />
                  测试连接
                </button>
                <button
                  aria-label="恢复默认 Agent 端点"
                  className="small-button"
                  disabled={!usesNonDefaultEndpoint || !onResetEndpoint}
                  onClick={onResetEndpoint}
                  title={`恢复端点到 ${normalizedDefaultEndpoint}`}
                  type="button"
                >
                  <RotateCcw size={14} />
                  恢复默认端点
                </button>
              </div>
            </SettingsCard>
          </div>
        )}

        {activeSection === "tokens" && (
          <div className="settings-section-stack">
            <SettingsCard title="令牌与完整模式" description="控制类操作需要 Agent 启动环境和桌面端填写同一个控制令牌。" status={fullModeReady ? "implemented" : "gated"} statusLabel={fullModeReady ? "已就绪" : "待配置"}>
              <SettingsRow title="API 令牌" description="可信本机回环部署通常可以留空。">
                <input type="password" value={apiToken} onChange={(event) => onApiTokenChange(event.target.value)} />
              </SettingsRow>
              <SettingsRow title="控制令牌" description="完整模式、插件、技能、MCP 管理和审批操作需要它。">
                <input type="password" value={controlToken} onChange={(event) => onControlTokenChange(event.target.value)} />
              </SettingsRow>
              {!fullModeReady && (
                <div className="notice warn" role="status">
                  完整模式操作需要启动 Agent 时设置 AIASK_AGENT_ENABLE_HERMES_FULL=1、AIASK_AGENT_TOOLSET=general_full、AIASK_AGENT_ENABLE_GENERAL_TOOLS=1，并在这里填写匹配的 AIASK_AGENT_CONTROL_TOKEN 或 AIASK_LOCAL_CONTROL_TOKEN。
                </div>
              )}
              <div className="settings-static-grid">
                <span>完整模式</span>
                <strong>{fullModeEnabled ? "已开启" : "设置 AIASK_AGENT_ENABLE_HERMES_FULL=1"}</strong>
                <span>通用工具</span>
                <strong>{generalFullToolset ? "general_full" : "set AIASK_AGENT_TOOLSET=general_full and AIASK_AGENT_ENABLE_GENERAL_TOOLS=1"}</strong>
                <span>Agent 控制令牌</span>
                <strong>{controlTokenConfigured ? "Agent 已配置" : "设置 AIASK_AGENT_CONTROL_TOKEN 或 AIASK_LOCAL_CONTROL_TOKEN"}</strong>
                <span>设置页令牌</span>
                <strong>{hasControlTokenInput ? "已填写" : "在此粘贴相同控制令牌"}</strong>
                <span>令牌验证</span>
                <strong>{controlAuthorized ? "已通过" : controlReason || "等待测试连接/刷新"}</strong>
              </div>
            </SettingsCard>
          </div>
        )}

        {activeSection === "models" && (
          <div className="settings-section-stack">
            <SettingsCard title="模型状态" description="只读查看模型提供方、当前模型、基础 URL 和密钥是否配置；密钥不会在前端展示或编辑。" status={llm?.configured ? "implemented" : "unconfigured"} statusLabel="只读状态">
              <div className="settings-static-grid">
                <span>提供方</span>
                <strong>{llm?.provider || "-"}</strong>
                <span>模型</span>
                <strong>{llm?.model || "-"}</strong>
                <span>基础 URL</span>
                <strong>{llm?.base_url_configured ? "已配置" : "默认"}</strong>
                <span>API 密钥</span>
                <strong>{llm?.api_key_configured ? "已配置" : "缺失 / mock"}</strong>
                <span>配置来源</span>
                <strong>{llm?.config_source?.loaded ? `${llm.config_source.source || "project"} .env` : "进程环境"}</strong>
                <span>密钥</span>
                <strong>{llm?.secrets_redacted ? "已脱敏" : "未加载"}</strong>
              </div>
              <ShortcutGrid
                items={[
                  {
                    id: "models",
                    label: "打开模型状态页",
                    description: "查看模型状态、列表加载和 AI 冒烟测试结果。",
                    icon: Bot
                  }
                ]}
                onOpenView={onOpenView}
              />
            </SettingsCard>
          </div>
        )}

        {activeSection === "mcp" && (
          <div className="settings-section-stack">
            <SettingsCard title="MCP 管理入口" description="设置页只显示授权说明和入口；注册、发现、资源读取、提示词获取和 OAuth 在 MCP 管理页执行。" status={fullModeReady ? "ready" : "gated"} statusLabel={fullModeReady ? "打开页面" : "需要控制权限"}>
              <div className="notice">
                桌面端不会读取 .env。请在 Agent 启动环境中配置 MCP 授权，并在“令牌与权限”中填写匹配的控制令牌。
              </div>
              <ShortcutGrid items={[{ id: "mcp", label: "打开 MCP 管理页", description: "进入 MCP 服务、资源、提示词和 OAuth 操作页。", icon: ServerCog }]} onOpenView={onOpenView} />
            </SettingsCard>
          </div>
        )}

        {activeSection === "skillsManagement" && (
          <div className="settings-section-stack">
            <SettingsCard title="技能管理" description="安装、更新、删除和原始快照属于高级管理，不放在前台技能使用页。" status={controlToken.trim() ? "ready" : "gated"} statusLabel={controlToken.trim() ? "可管理" : "需要控制令牌"}>
              <div className="notice">
                前台“技能”只用于选择和应用到对话；这里保留写入操作、原始快照和排障结果。
              </div>
            </SettingsCard>
            <SkillsPanel
              apiToken={apiToken}
              controlToken={controlToken}
              endpoint={normalizedEndpoint}
              management
              onRefresh={refreshManagedSkills}
              skillsPayload={managedSkillsPayload || (controlToken.trim() ? { skills: [], root: "-" } : { gated: true, reason: "control token is not configured" })}
            />
          </div>
        )}

        {activeSection === "automationManagement" && (
          <div className="settings-section-stack">
            <SettingsCard title="自动化管理" description="删除任务、高级定时表达式、间隔和工具集配置集中在这里。" status={controlToken.trim() ? "ready" : "gated"} statusLabel={controlToken.trim() ? "可管理" : "需要控制令牌"}>
              <div className="notice">
                前台“自动化”只保留日常创建、运行、暂停和恢复。删除任务和高级调度参数放在此处。
              </div>
            </SettingsCard>
            <AutomationWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} management userId={userId} />
          </div>
        )}

        {activeSection === "integrations" && (
          <div className="settings-section-stack">
            <SettingsCard title="应用集成" description="微信、飞书、Discord、Webhook、金融应用和 Home Assistant 等集成只通过环境变量配置密钥。" status={controlToken.trim() ? "ready" : "gated"} statusLabel={controlToken.trim() ? "可管理" : "需要控制令牌"}>
              <div className="notice">
                桌面端不会保存外部平台密钥；真实发送消息只创建审批意图，确认后才执行。
              </div>
            </SettingsCard>
            <IntegrationsManagementPanel apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} userId={userId} />
          </div>
        )}

        {activeSection === "webhooks" && (
          <div className="settings-section-stack">
            <SettingsCard title="Webhook" description="订阅和删除是真实管理操作；触发动作创建审批意图。" status={controlToken.trim() ? "ready" : "gated"} statusLabel={controlToken.trim() ? "可管理" : "需要控制令牌"}>
              <div className="notice">Webhook secret 可以通过 UI 创建，但不在页面回显；触发结果进入审批链。</div>
            </SettingsCard>
            <WebhooksPanel apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
          </div>
        )}

        {activeSection === "pluginsManagement" && (
          <div className="settings-section-stack">
            <SettingsCard title="插件与技能包" description="这里打开真实插件治理页面，支持启停和工具自检；skill pack 作为治理状态展示。" status={controlToken.trim() ? "ready" : "gated"} statusLabel={controlToken.trim() ? "可管理" : "需要控制令牌"}>
              <div className="notice">插件执行需要控制令牌；原始 payload 只放在折叠区。</div>
            </SettingsCard>
            <CapabilitiesWorkspace apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} initialTab="plugins" />
          </div>
        )}

        {activeSection === "workflow" && (
          <div className="settings-section-stack">
            <SettingsCard title="工作流入口" description="这里不配置工作流参数，只打开数据、策略、因子、孵化和工厂事件页面。" status="ready" statusLabel="打开页面">
              <ShortcutGrid items={workflowShortcuts} onOpenView={onOpenView} />
            </SettingsCard>
          </div>
        )}

        {activeSection === "data" && (
          <div className="settings-section-stack">
            <SettingsCard title="数据路径" description="只读展示 Agent、意图、量化研究和 AKShare 数据库路径，不在前端编辑路径。" status="implemented" statusLabel="只读状态">
              <div className="settings-static-grid">
                <span>Agent 状态</span>
                <strong>{compact((databases.agent_state as Record<string, unknown> | undefined)?.path)}</strong>
                <span>意图状态</span>
                <strong>{compact((databases.intent_state as Record<string, unknown> | undefined)?.path)}</strong>
                <span>量化状态</span>
                <strong>{compact((databases.quant_research as Record<string, unknown> | undefined)?.path)}</strong>
                <span>AKShare DB</span>
                <strong>{compact((databases.akshare as Record<string, unknown> | undefined)?.path)}</strong>
              </div>
            </SettingsCard>
          </div>
        )}

        {activeSection === "learningRl" && (
          <div className="settings-section-stack">
            <SettingsCard title="学习 / RL" description="学习建议、应用操作、RL 环境、配置、运行和日志结果。" status={controlToken.trim() ? "ready" : "gated"} statusLabel={controlToken.trim() ? "可管理" : "需要控制令牌"}>
              <div className="notice">RL 训练可能消耗本地资源；启动和停止都保留在受控设置页，不进入普通对话首屏。</div>
            </SettingsCard>
            <LearningRlPanel apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
          </div>
        )}

        {activeSection === "security" && (
          <div className="settings-section-stack">
            <SettingsCard title="安全扫描" description="运行 Agent 安全扫描工具，默认不包含环境变量内容。" status={controlToken.trim() ? "ready" : "gated"} statusLabel={controlToken.trim() ? "可运行" : "需要控制令牌"}>
              <div className="notice">扫描结果用于排障和修复建议；不会读取或展示本地密钥。</div>
            </SettingsCard>
            <SecurityPanel apiToken={apiToken} controlToken={controlToken} endpoint={normalizedEndpoint} />
          </div>
        )}

        {activeSection === "advanced" && (
          <div className="settings-section-stack">
            <SettingsCard title="高级诊断入口" description="打开运行概览、覆盖矩阵、工具目录、能力中心、诊断、智能体状态、本地用户和事件控制台。" status="ready" statusLabel="打开页面">
              <ShortcutGrid items={advancedShortcuts} onOpenView={onOpenView} />
            </SettingsCard>
          </div>
        )}

        {activeSection === "about" && (
          <div className="settings-section-stack">
            <SettingsCard title="关于 AIASK Desktop" description="桌面端只作为 Agent HTTP API 客户端，不绕过 UI、不直接调用 Python 包或 MCP manager。" status="ready" statusLabel="只读状态">
              <details className="raw-details" open>
                <summary>
                  健康状态与设置
                  <ChevronDown size={14} />
                </summary>
                <p className="status-line">{message}</p>
                <JsonPanel value={{ health, settingsStatus }} />
              </details>
            </SettingsCard>
          </div>
        )}
      </section>
    </div>
  );
}
