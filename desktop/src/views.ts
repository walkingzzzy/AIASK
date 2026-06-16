import {
  Activity,
  BarChart3,
  Bot,
  Boxes,
  BrainCircuit,
  CalendarClock,
  ClipboardList,
  Database,
  Factory,
  FlaskConical,
  FolderGit2,
  GitBranchPlus,
  Landmark,
  LayoutList,
  LineChart,
  MessageSquare,
  MessagesSquare,
  PackageOpen,
  PlugZap,
  Puzzle,
  Radio,
  SearchCheck,
  ServerCog,
  Settings,
  ShieldCheck,
  Thermometer,
  UserRound,
  Wrench,
  Zap,
} from "lucide-react";
import type { ElementType } from "react";
import type { ComponentType, ReactNode } from "react";
import { viewToRoute } from "./routes";
import type { MainView } from "./types";

export interface ViewRegistryItem {
  id: MainView;
  label: string;
  icon: ElementType;
  description: string;
  group: "workspace" | "finance" | "ops" | "settings" | "agent" | "legacy";
  route?: string;
  requiresControlToken?: boolean;
  requiresFullMode?: boolean;
  mountPosition?: "primary" | "secondary" | "hidden";
  render?: () => ReactNode;
  component?: ComponentType<Record<string, never>>;
  legacy?: boolean;
  replacementView?: MainView;
  badge?: string;
  diagnosticOnly?: boolean;
}

export interface ViewGroup {
  id: string;
  label: string;
  items: ViewRegistryItem[];
  defaultCollapsed?: boolean;
  diagnosticOnly?: boolean;
}

const VIEW_REGISTRY_BASE = [
  {
    id: "workbench",
    label: "工作台",
    icon: MessageSquare,
    description: "以任务线程为中心的 Agent 默认工作面。",
    group: "workspace",
    route: "/workbench",
    mountPosition: "primary",
  },
  {
    id: "projects-contexts",
    label: "项目 / 上下文",
    icon: FolderGit2,
    description: "Agent 端点、项目上下文、后端模式和环境准备度。",
    group: "workspace",
    route: "/projects-contexts",
    mountPosition: "primary",
  },
  {
    id: "sessions",
    label: "会话",
    icon: MessagesSquare,
    description: "会话管理与详情查看。",
    group: "agent",
    route: "/sessions",
    requiresControlToken: true,
    requiresFullMode: true,
    badge: "Full",
  },
  {
    id: "runs-events",
    label: "运行 / 事件",
    icon: LayoutList,
    description: "运行摘要、时间线视图和事件过滤。",
    group: "agent",
    route: "/runs-events",
  },
  {
    id: "artifacts",
    label: "产物",
    icon: PackageOpen,
    description: "聚合最近运行沉淀的 durable artifacts。",
    group: "agent",
    route: "/artifacts",
  },
  {
    id: "tools-intents-approvals",
    label: "审批",
    icon: ShieldCheck,
    description: "工具目录、意图、审批和受控流程。",
    group: "workspace",
    route: "/tools-intents-approvals",
  },
  {
    id: "finance-lab",
    label: "金融实验室",
    icon: SearchCheck,
    description: "金融研究、策略、因子、数据和事件任务模板。",
    group: "finance",
    route: "/finance-lab",
    mountPosition: "primary",
  },
  {
    id: "integrations",
    label: "集成",
    icon: PlugZap,
    description: "统一查看 MCP、Gateway、插件、技能和连接器健康。",
    group: "ops",
    route: "/integrations",
    mountPosition: "primary",
  },
  {
    id: "plugins-skills",
    label: "插件 / 技能",
    icon: Puzzle,
    description: "原生插件和技能生命周期操作。",
    group: "ops",
    route: "/plugins-skills",
    requiresControlToken: true,
    mountPosition: "primary",
  },
  {
    id: "financial-manager",
    label: "金融经理台",
    icon: Landmark,
    description: "组合、自选、风控和受控执行入口。",
    group: "finance",
  },
  {
    id: "market-temperature",
    label: "市场温度",
    icon: Thermometer,
    description: "市场宽度、冷热行业和数据质量快照。",
    group: "finance",
    route: "/market-temperature",
  },
  {
    id: "quant",
    label: "量化研究",
    icon: LineChart,
    description: "研究运行和结构化报告。",
    group: "finance",
  },
  {
    id: "strategy-factory",
    label: "策略工厂",
    icon: Factory,
    description: "策略生成、评审和工厂状态。",
    group: "finance",
  },
  {
    id: "factor-factory",
    label: "因子工厂",
    icon: BarChart3,
    description: "因子挖掘和活跃池健康。",
    group: "finance",
  },
  {
    id: "incubation",
    label: "孵化工厂",
    icon: FlaskConical,
    description: "生命周期管理和命中率复核。",
    group: "finance",
  },
  {
    id: "data",
    label: "数据",
    icon: Database,
    description: "数据健康、同步计划和新鲜度检查。",
    group: "finance",
  },
  {
    id: "automation",
    label: "自动化",
    icon: CalendarClock,
    description: "自动化收件箱、调度和工作流运行。",
    group: "workspace",
    route: "/automations",
    mountPosition: "primary",
  },
  {
    id: "workflows",
    label: "工作流",
    icon: GitBranchPlus,
    description: "金融运营工作流入口。",
    group: "finance",
  },
  {
    id: "factory-events",
    label: "工厂事件",
    icon: Radio,
    description: "工厂事件创建、预览和复核。",
    group: "finance",
    route: "/factory-events",
  },
  {
    id: "mcp-connectors",
    label: "MCP / 连接器",
    icon: PlugZap,
    description: "MCP 发现、授权与连接器健康。",
    group: "ops",
    route: "/mcp-connectors",
  },
  {
    id: "gateway",
    label: "Gateway",
    icon: ServerCog,
    description: "Gateway 平台、消息与目录状态。",
    group: "ops",
    route: "/gateway",
  },
  {
    id: "readiness-health",
    label: "准备度 / 健康",
    icon: Activity,
    description: "运维健康与系统准备度。",
    group: "ops",
    route: "/readiness-health",
  },
  {
    id: "extensions-pilot",
    label: "扩展注册表",
    icon: PlugZap,
    description: "AIASK 原生内部页面与插槽注册表。",
    group: "ops",
    route: "/extensions-pilot",
    requiresControlToken: true,
    mountPosition: "secondary",
    badge: "内部",
  },
  {
    id: "settings",
    label: "设置",
    icon: Settings,
    description: "Agent 端点、令牌、画像和模式控制。",
    group: "settings",
  },
  {
    id: "overview",
    label: "总览",
    icon: Boxes,
    description: "旧系统概览入口。",
    group: "legacy",
    legacy: true,
    diagnosticOnly: true,
  },
  {
    id: "agent",
    label: "智能体",
    icon: Bot,
    description: "旧 Agent 运行时页面。",
    group: "legacy",
    legacy: true,
    replacementView: "workbench",
    diagnosticOnly: true,
  },
  {
    id: "capabilities",
    label: "能力中心",
    icon: Boxes,
    description: "旧能力工作台入口。",
    group: "legacy",
    legacy: true,
    diagnosticOnly: true,
  },
  {
    id: "coverage",
    label: "覆盖矩阵",
    icon: ClipboardList,
    description: "旧覆盖矩阵入口。",
    group: "legacy",
    legacy: true,
    diagnosticOnly: true,
  },
  {
    id: "tools",
    label: "工具",
    icon: Wrench,
    description: "旧工具目录入口。",
    group: "legacy",
    legacy: true,
    replacementView: "tools-intents-approvals",
    diagnosticOnly: true,
  },
  {
    id: "mcp",
    label: "MCP",
    icon: PlugZap,
    description: "旧 MCP 入口。",
    group: "legacy",
    legacy: true,
    replacementView: "mcp-connectors",
    diagnosticOnly: true,
  },
  {
    id: "diagnostics",
    label: "诊断",
    icon: Activity,
    description: "旧诊断入口。",
    group: "legacy",
    legacy: true,
    replacementView: "readiness-health",
    diagnosticOnly: true,
  },
  {
    id: "event-console",
    label: "事件控制台",
    icon: Zap,
    description: "旧事件控制台入口。",
    group: "legacy",
    legacy: true,
    replacementView: "runs-events",
    diagnosticOnly: true,
  },
  {
    id: "skills",
    label: "技能",
    icon: BrainCircuit,
    description: "旧技能页面。",
    group: "legacy",
    legacy: true,
    replacementView: "plugins-skills",
    diagnosticOnly: true,
  },
  {
    id: "user",
    label: "本地用户",
    icon: UserRound,
    description: "旧本地用户页面。",
    group: "legacy",
    legacy: true,
    replacementView: "settings",
    diagnosticOnly: true,
  },
  {
    id: "models",
    label: "模型配置",
    icon: BrainCircuit,
    description: "配置 LLM 提供方、获取模型列表并执行冒烟测试。",
    group: "ops",
    route: "/models",
  },
] satisfies ViewRegistryItem[];

export const VIEW_REGISTRY: ViewRegistryItem[] = VIEW_REGISTRY_BASE.map((view) => ({
  ...view,
  route: viewToRoute(view.id),
}));

function pick(ids: MainView[]): ViewRegistryItem[] {
  return ids.map((id) => {
    const item = VIEW_REGISTRY.find((view) => view.id === id);
    if (!item) throw new Error(`Missing view registry item: ${id}`);
    return item;
  });
}

export const VIEW_GROUPS: ViewGroup[] = [
  {
    id: "core",
    label: "核心功能",
    items: pick([
      "workbench",
      "runs-events",
      "integrations",
      "finance-lab",
      "readiness-health"
    ]),
  },
];

export function getViewItem(view: MainView): ViewRegistryItem | undefined {
  return VIEW_REGISTRY.find((item) => item.id === view);
}
