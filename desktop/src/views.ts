import {
  Activity,
  BarChart3,
  Bot,
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
  TableProperties
} from "lucide-react";

import { V1_ROUTES } from "./routes";
import type { ViewDefinition } from "./types";

export const V1_VIEWS: ViewDefinition[] = [
  {
    id: "workbench",
    label: "AI 对话工作台",
    shortLabel: "工作台",
    route: V1_ROUTES.workbench,
    group: "core",
    description: "任务输入、模型状态、运行上下文、证据与审批的第一入口。",
    icon: MessageSquareText,
    spec: "01-AI对话与任务工作台.md"
  },
  {
    id: "models",
    label: "模型配置",
    shortLabel: "模型",
    route: V1_ROUTES.models,
    group: "core",
    description: "Provider、模型、密钥配置状态、模型列表和冒烟测试。",
    icon: KeyRound,
    spec: "02-模型配置与LLM可用性.md"
  },
  {
    id: "projects-contexts",
    label: "项目与上下文",
    shortLabel: "上下文",
    route: V1_ROUTES["projects-contexts"],
    group: "core",
    description: "用户、项目、会话上下文和证据引用，不假装已支持真实上传。",
    icon: BriefcaseBusiness,
    spec: "01-AI对话与任务工作台.md"
  },
  {
    id: "sessions-runs",
    label: "会话与运行",
    shortLabel: "会话运行",
    route: V1_ROUTES["sessions-runs"],
    group: "core",
    description: "会话、运行、事件、产物和来源链路。",
    icon: ScrollText,
    spec: "06-会话历史归档与运行事件.md"
  },
  {
    id: "tools-approvals",
    label: "工具与审批",
    shortLabel: "工具审批",
    route: V1_ROUTES["tools-approvals"],
    group: "core",
    description: "只展示 agent_* 工具门面、ActionIntent 和审批队列。",
    icon: ClipboardCheck,
    spec: "05-Agent工具与Hermes能力.md"
  },
  {
    id: "integrations",
    label: "集成总览",
    shortLabel: "集成",
    route: V1_ROUTES.integrations,
    group: "integrations",
    description: "MCP、Connectors、Plugins、Skills、Gateway、Webhooks 与健康状态入口。",
    icon: Network,
    spec: "24-Connectors统一连接器.md"
  },
  {
    id: "mcp-connectors",
    label: "MCP 与连接器",
    shortLabel: "MCP/连接器",
    route: V1_ROUTES["mcp-connectors"],
    group: "integrations",
    description: "Servers、tools、resources、prompts、OAuth 和统一连接器状态。",
    icon: PlugZap,
    spec: "03-MCP服务管理.md"
  },
  {
    id: "plugins-skills",
    label: "插件与技能",
    shortLabel: "插件技能",
    route: V1_ROUTES["plugins-skills"],
    group: "integrations",
    description: "Runtime skills、插件、命令、工具自测与门禁状态。",
    icon: Sparkles,
    spec: "04-Skills与Plugins管理.md"
  },
  {
    id: "gateway-webhooks",
    label: "Gateway 与 Webhooks",
    shortLabel: "Gateway",
    route: V1_ROUTES["gateway-webhooks"],
    group: "integrations",
    description: "跨平台投递、消息、目录、daemon 和 Webhook 管理。",
    icon: CloudCog,
    spec: "08-应用联动Gateway与Webhooks.md"
  },
  {
    id: "stock-data-sources",
    label: "股票数据源",
    shortLabel: "数据源",
    route: V1_ROUTES["stock-data-sources"],
    group: "finance",
    description: "AKShare、Tushare、TDX、TQCenter 等数据源配置、测试和密钥脱敏。",
    icon: Database,
    spec: "09-股票数据源配置与测试.md"
  },
  {
    id: "data-sync",
    label: "数据库与同步",
    shortLabel: "数据同步",
    route: V1_ROUTES["data-sync"],
    group: "finance",
    description: "本地数据库、数据新鲜度、同步计划和受控执行入口。",
    icon: TableProperties,
    spec: "10-数据库状态与数据同步.md"
  },
  {
    id: "finance-lab",
    label: "金融工作台",
    shortLabel: "金融",
    route: V1_ROUTES["finance-lab"],
    group: "finance",
    description: "V1 金融研究枢纽：数据、雷达、市场、量化、经理台、券商只读。",
    icon: LayoutDashboard,
    spec: "15-金融工作台.md"
  },
  {
    id: "stock-radar",
    label: "股票雷达",
    shortLabel: "股票雷达",
    route: V1_ROUTES["stock-radar"],
    group: "finance",
    description: "候选、摘要、运行意图、推送意图和调度意图。",
    icon: Radar,
    spec: "12-股票雷达.md"
  },
  {
    id: "market-temperature",
    label: "市场温度",
    shortLabel: "市场温度",
    route: V1_ROUTES["market-temperature"],
    group: "finance",
    description: "市场广度、行业冷热、缓存新鲜度和只读验证。",
    icon: Gauge,
    spec: "13-热力图与市场温度.md"
  },
  {
    id: "quant-research",
    label: "量化研究",
    shortLabel: "量化",
    route: V1_ROUTES["quant-research"],
    group: "finance",
    description: "Preset、运行、报告、指标、证据链和限制说明。",
    icon: LineChart,
    spec: "22-量化研究与报告.md"
  },
  {
    id: "financial-manager",
    label: "金融经理台",
    shortLabel: "经理台",
    route: V1_ROUTES["financial-manager"],
    group: "finance",
    description: "目录、状态、查询、受控意图、券商只读和风险标注。",
    icon: BarChart3,
    spec: "23-FinancialManager与Broker只读.md"
  },
  {
    id: "automation",
    label: "自动化任务",
    shortLabel: "自动化",
    route: V1_ROUTES.automation,
    group: "ops",
    description: "Jobs、运行历史、手动触发和调度门禁。",
    icon: GitBranch,
    spec: "11-自动化盯盘与任务处理.md"
  },
  {
    id: "workflows",
    label: "工作流",
    shortLabel: "工作流",
    route: V1_ROUTES.workflows,
    group: "ops",
    description: "V1 Data -> Radar -> Market -> Quant -> Manager -> Gateway/Automation 流程。",
    icon: Activity,
    spec: "11-自动化盯盘与任务处理.md"
  },
  {
    id: "settings-security",
    label: "设置与安全",
    shortLabel: "设置",
    route: V1_ROUTES["settings-security"],
    group: "ops",
    description: "连接、token、模式、安全门禁和脱敏状态。",
    icon: Settings,
    spec: "16-安全门禁与验收矩阵.md"
  },
  {
    id: "readiness-health",
    label: "健康诊断",
    shortLabel: "健康",
    route: V1_ROUTES["readiness-health"],
    group: "ops",
    description: "Agent、Hermes、financial readiness、capabilities 和 next actions。",
    icon: HeartPulse,
    spec: "20-Readiness健康诊断与运维.md"
  },
  {
    id: "local-user-memory",
    label: "个人能力与记忆",
    shortLabel: "用户记忆",
    route: V1_ROUTES["local-user-memory"],
    group: "ops",
    description: "本地画像、活动、记忆搜索、导出/删除预览和数据策略。",
    icon: MemoryStick,
    spec: "07-记忆与个人能力.md"
  },
  {
    id: "learning-rl",
    label: "学习与 RL",
    shortLabel: "学习/RL",
    route: V1_ROUTES["learning-rl"],
    group: "ops",
    description: "学习状态、review proposals、RL 环境/运行和 MoA 观察。",
    icon: BrainCircuit,
    spec: "21-Learning-RL-MoA学习能力.md"
  },
  {
    id: "native-diagnostics",
    label: "本机诊断",
    shortLabel: "本机",
    route: V1_ROUTES["native-diagnostics"],
    group: "ops",
    description: "文件、终端、浏览器、进程能力的只读诊断和门禁状态。",
    icon: Bot,
    spec: "19-Native文件代码终端浏览器能力.md"
  }
];

export const NAV_GROUPS = [
  { id: "core", label: "核心工作" },
  { id: "integrations", label: "集成能力" },
  { id: "finance", label: "金融研究" },
  { id: "ops", label: "运维安全" }
] as const;
