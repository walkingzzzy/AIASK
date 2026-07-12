import {
  Activity,
  BarChart3,
  Bot,
  Boxes,
  BrainCircuit,
  BriefcaseBusiness,
  ClipboardCheck,
  CloudCog,
  Database,
  Gauge,
  GitBranch,
  HeartPulse,
  KeyRound,
  LayoutDashboard,
  LineChart,
  MemoryStick,
  MessageSquareText,
  Network,
  PlugZap,
  Radar,
  ScrollText,
  Settings,
  Sparkles,
  UserRound,
  TableProperties,
  TrendingUp,
  Star
} from "lucide-react";

import { V1_ROUTES } from "./routes";
import type { ViewDefinition } from "./types";

export const V1_VIEWS: ViewDefinition[] = [
  {
    id: "workbench",
    label: "任务工作台",
    shortLabel: "工作台",
    route: V1_ROUTES.workbench,
    group: "core",
    description: "围绕会话推进任务，集中查看对话、产物、审批和复核入口。",
    icon: MessageSquareText,
    spec: "workbench-layout"
  },
  {
    id: "projects-contexts",
    label: "项目与模型",
    shortLabel: "项目",
    route: V1_ROUTES["projects-contexts"],
    group: "core",
    description: "管理项目上下文、个人资料、证据引用和运行边界。",
    icon: BriefcaseBusiness,
    spec: "projects-context"
  },
  {
    id: "user-profile",
    label: "项目与模型",
    shortLabel: "个人资料",
    route: V1_ROUTES["user-profile"],
    group: "core",
    description: "维护投资偏好、记忆线索和可复用的个人上下文。",
    icon: UserRound,
    spec: "user-profile"
  },
  {
    id: "models",
    label: "项目与模型",
    shortLabel: "模型",
    route: V1_ROUTES.models,
    group: "core",
    description: "查看模型供应方可用性、连接设置和基础连通检查。",
    icon: KeyRound,
    spec: "model-readiness"
  },
  {
    id: "sessions-runs",
    label: "运行记录",
    shortLabel: "运行",
    route: V1_ROUTES["sessions-runs"],
    group: "core",
    description: "查看会话、运行、事件、产物和证据链路。",
    icon: ScrollText,
    spec: "runs-evidence"
  },
  {
    id: "tools-approvals",
    label: "审批",
    shortLabel: "审批",
    route: V1_ROUTES["tools-approvals"],
    group: "core",
    description: "统一复核工具调用、受控操作、审批队列和处理结果。",
    icon: ClipboardCheck,
    spec: "approvals-flow"
  },
  {
    id: "finance-lab",
    label: "金融研究",
    shortLabel: "总览",
    route: V1_ROUTES["finance-lab"],
    group: "finance",
    description: "进入数据、雷达、市场温度、量化研究和金融管理工作区。",
    icon: LayoutDashboard,
    spec: "finance-lab"
  },
  {
    id: "stock-data-sources",
    label: "金融研究",
    shortLabel: "数据源",
    route: V1_ROUTES["stock-data-sources"],
    group: "finance",
    description: "配置和检查股票数据源、敏感信息隐藏和可用状态。",
    icon: Database,
    spec: "stock-data-sources"
  },
  {
    id: "data-sync",
    label: "金融研究",
    shortLabel: "数据同步",
    route: V1_ROUTES["data-sync"],
    group: "finance",
    description: "查看数据库状态、数据新鲜度、缺失项和同步预案。",
    icon: TableProperties,
    spec: "data-sync"
  },
  {
    id: "stock-radar",
    label: "金融研究",
    shortLabel: "股票雷达",
    route: V1_ROUTES["stock-radar"],
    group: "finance",
    description: "查看候选股票、摘要、风险信号和受控操作。",
    icon: Radar,
    spec: "stock-radar"
  },
  {
    id: "market-temperature",
    label: "金融研究",
    shortLabel: "市场温度",
    route: V1_ROUTES["market-temperature"],
    group: "finance",
    description: "查看市场广度、冷热行业、缓存状态和只读诊断。",
    icon: Gauge,
    spec: "market-temperature"
  },
  {
    id: "quant-research",
    label: "金融研究",
    shortLabel: "量化研究",
    route: V1_ROUTES["quant-research"],
    group: "finance",
    description: "查看研究模板、运行记录、报告指标和证据面板。",
    icon: LineChart,
    spec: "quant-research"
  },
  {
    id: "strategy-factory",
    label: "金融研究",
    shortLabel: "策略工厂",
    route: V1_ROUTES["strategy-factory"],
    group: "finance",
    description: "通过 Agent 安全 facade 查看策略工厂状态、运行、领域事件和交易预测，只读调用不触发交易。",
    icon: GitBranch,
    spec: "strategy-factory"
  },
  {
    id: "factor-factory",
    label: "金融研究",
    shortLabel: "因子工厂",
    route: V1_ROUTES["factor-factory"],
    group: "finance",
    description: "查看因子挖掘工厂、引擎健康、活跃因子池和受控 dry-run 意图。",
    icon: Boxes,
    spec: "factor-factory"
  },
  {
    id: "incubation",
    label: "金融研究",
    shortLabel: "孵化工厂",
    route: V1_ROUTES.incubation,
    group: "finance",
    description: "查看孵化工厂 runner、编排器就绪状态，并通过受控意图预演观察流程。",
    icon: BrainCircuit,
    spec: "incubation-factory"
  },
  {
    id: "factory-events",
    label: "金融研究",
    shortLabel: "工厂事件",
    route: V1_ROUTES["factory-events"],
    group: "finance",
    description: "查看事件注入列表、任务预览、血缘、主题暴露和 outbox 状态。",
    icon: Activity,
    spec: "factory-events"
  },
  {
    id: "financial-manager",
    label: "金融研究",
    shortLabel: "金融管理",
    route: V1_ROUTES["financial-manager"],
    group: "finance",
    description: "查看目录、状态、只读查询、受控意图和券商只读数据。",
    icon: BarChart3,
    spec: "financial-manager"
  },
  {
    id: "my-strategy",
    label: "个人资产",
    shortLabel: "我的策略",
    route: "/personal/my-strategy",
    group: "personal",
    description: "管理个人投资策略，跟踪表现和持仓关联。",
    icon: TrendingUp,
    spec: "my-strategy"
  },
  {
    id: "my-stocks",
    label: "个人资产",
    shortLabel: "我的股票",
    route: "/personal/my-stocks",
    group: "personal",
    description: "管理个人股票池、标签和备注。",
    icon: Star,
    spec: "my-stocks"
  },
  {
    id: "integrations",
    label: "集成连接",
    shortLabel: "总览",
    route: V1_ROUTES.integrations,
    group: "integrations",
    description: "集中查看 MCP、连接器、插件、技能和消息网关。",
    icon: Network,
    spec: "integrations-overview"
  },
  {
    id: "mcp-connectors",
    label: "集成连接",
    shortLabel: "MCP 连接",
    route: V1_ROUTES["mcp-connectors"],
    group: "integrations",
    description: "查看 MCP 服务、工具、资源、提示词、授权和连接器健康状态。",
    icon: PlugZap,
    spec: "mcp-connectors"
  },
  {
    id: "plugins-skills",
    label: "集成连接",
    shortLabel: "插件技能",
    route: V1_ROUTES["plugins-skills"],
    group: "integrations",
    description: "管理运行时技能、插件、命令、自检和受控变更。",
    icon: Sparkles,
    spec: "plugins-skills"
  },
  {
    id: "gateway-webhooks",
    label: "集成连接",
    shortLabel: "消息网关",
    route: V1_ROUTES["gateway-webhooks"],
    group: "integrations",
    description: "查看平台状态、消息目录、后台服务和 Webhook 反馈。",
    icon: CloudCog,
    spec: "gateway-webhooks"
  },
  {
    id: "automation",
    label: "自动化",
    shortLabel: "待处理",
    route: V1_ROUTES.automation,
    group: "ops",
    description: "查看待处理事项、历史运行、计划任务和受控作业操作。",
    icon: GitBranch,
    spec: "automation-triage"
  },
  {
    id: "workflows",
    label: "自动化",
    shortLabel: "流程",
    route: V1_ROUTES.workflows,
    group: "ops",
    description: "查看从数据接入到雷达、市场、量化、管理和投递的流程图。",
    icon: Activity,
    spec: "workflow-map"
  },
  {
    id: "readiness-health",
    label: "运维",
    shortLabel: "健康检查",
    route: V1_ROUTES["readiness-health"],
    group: "ops",
    description: "查看环境状态、权限门禁、健康诊断、能力清单和下一步处理。",
    icon: HeartPulse,
    spec: "readiness-health"
  },
  {
    id: "local-user-memory",
    label: "运维",
    shortLabel: "本地记忆",
    route: V1_ROUTES["local-user-memory"],
    group: "ops",
    description: "查看本地资料、活动记录、数据策略、导出和删除预览。",
    icon: MemoryStick,
    spec: "local-user-memory"
  },
  {
    id: "learning-rl",
    label: "运维",
    shortLabel: "学习训练",
    route: V1_ROUTES["learning-rl"],
    group: "ops",
    description: "查看学习状态、待复核建议、训练环境和运行检查。",
    icon: BrainCircuit,
    spec: "learning-rl"
  },
  {
    id: "native-diagnostics",
    label: "运维",
    shortLabel: "本机诊断",
    route: V1_ROUTES["native-diagnostics"],
    group: "ops",
    description: "只读检查文件、终端、浏览器和进程能力。",
    icon: Bot,
    spec: "native-diagnostics"
  },
  {
    id: "settings-security",
    label: "设置",
    shortLabel: "设置",
    route: V1_ROUTES["settings-security"],
    group: "ops",
    description: "管理连接、权限令牌、模式、主题、快捷键和高级设置。",
    icon: Settings,
    spec: "settings-security"
  }
];

export const NAV_GROUPS = [
  { id: "core", label: "任务工作台" },
  { id: "finance", label: "金融研究" },
  { id: "personal", label: "个人资产" },
  { id: "integrations", label: "集成连接" },
  { id: "ops", label: "自动化与运维" }
] as const;
