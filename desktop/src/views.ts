import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  Boxes,
  BrainCircuit,
  CalendarClock,
  ClipboardList,
  Database,
  Landmark,
  Factory,
  Flame,
  FlaskConical,
  Gauge,
  LineChart,
  Layers3,
  MessageSquare,
  Radio,
  Scale,
  ServerCog,
  Settings,
  UserRound,
  Wrench,
  Zap
} from "lucide-react";
import type { ElementType } from "react";
import type { MainView } from "./types";

export interface ViewRegistryItem {
  id: MainView;
  label: string;
  icon: ElementType;
  description: string;
  visibleInPrimaryNav?: boolean;
  settingsSection?: string;
  workflowGroup?: string;
}

export interface ViewGroup {
  id: string;
  label: string;
  items: ViewRegistryItem[];
}

export const VIEW_REGISTRY: ViewRegistryItem[] = [
  { id: "workbench", label: "对话", icon: MessageSquare, description: "AI 对话与任务线程", visibleInPrimaryNav: true },
  { id: "skills", label: "技能", icon: Layers3, description: "技能选择与使用", visibleInPrimaryNav: true },
  { id: "automation", label: "自动化", icon: CalendarClock, description: "计划任务与手动运行", visibleInPrimaryNav: true },
  { id: "workflows", label: "工作流", icon: Factory, description: "量化研究与工厂流程", visibleInPrimaryNav: true },
  { id: "financial-manager", label: "金融经理台", icon: Landmark, description: "组合、风控、研究、纸上交易与券商只读", visibleInPrimaryNav: true, workflowGroup: "data" },
  { id: "overview", label: "运行概览", icon: Boxes, description: "运行指挥台", settingsSection: "advanced" },
  { id: "models", label: "模型", icon: BrainCircuit, description: "模型状态与 AI smoke", settingsSection: "models" },
  { id: "data", label: "数据与同步", icon: Database, description: "数据质量与同步计划", workflowGroup: "data" },
  { id: "quant", label: "量化研究", icon: LineChart, description: "研究运行与报告", workflowGroup: "data" },
  { id: "strategy-factory", label: "策略工厂", icon: Factory, description: "生成、运行与评审", workflowGroup: "factory" },
  { id: "factor-factory", label: "因子工厂", icon: BarChart3, description: "挖掘与活跃池健康", workflowGroup: "factory" },
  { id: "incubation", label: "孵化工厂", icon: FlaskConical, description: "生命周期和命中率", workflowGroup: "factory" },
  { id: "coverage", label: "能力覆盖矩阵", icon: ClipboardList, description: "能力状态矩阵", settingsSection: "advanced" },
  { id: "mcp", label: "MCP", icon: ServerCog, description: "服务、资源与提示词", settingsSection: "mcp" },
  { id: "tools", label: "工具", icon: Wrench, description: "工具目录和调用测试", settingsSection: "advanced" },
  { id: "capabilities", label: "能力中心", icon: Boxes, description: "运行时能力评审", settingsSection: "advanced" },
  { id: "event-console", label: "事件控制台", icon: Zap, description: "事件流和详情", settingsSection: "advanced" },
  { id: "factory-events", label: "工厂事件", icon: Radio, description: "事件创建、预览和血缘", settingsSection: "workflow" },
  { id: "valuation", label: "估值分析", icon: LineChart, description: "DCF/DDM/相对/情景/共识估值", workflowGroup: "data" },
  { id: "trade-plan", label: "交易计划", icon: Activity, description: "入场方案、止损止盈与仓位", workflowGroup: "data" },
  { id: "fund-flow", label: "资金流向", icon: BarChart3, description: "北向/行业/概念/个股资金流", workflowGroup: "data" },
  { id: "decision", label: "买卖决策", icon: Scale, description: "买入/卖出/共识/统一决策", workflowGroup: "analysis" },
  { id: "fundamental", label: "基本面", icon: Gauge, description: "基本面分析、杜邦和同行对比", workflowGroup: "analysis" },
  { id: "macro", label: "宏观经济", icon: LineChart, description: "宏观指标与市场概览", workflowGroup: "analysis" },
  { id: "alerts", label: "告警管理", icon: Bell, description: "告警检查与规则创建", workflowGroup: "analysis" },
  { id: "limit-up", label: "涨停与龙虎", icon: Flame, description: "涨停统计、大宗交易与异动", workflowGroup: "analysis" },
  { id: "diagnostics", label: "诊断", icon: Activity, description: "Hermes 与系统诊断", settingsSection: "advanced" },
  { id: "agent", label: "智能体状态", icon: Bot, description: "Agent 工具和授权状态", settingsSection: "advanced" },
  { id: "user", label: "本地用户", icon: UserRound, description: "本地 profile", settingsSection: "general" },
  { id: "settings", label: "设置", icon: Settings, description: "连接、令牌和偏好" }
];

function pick(ids: MainView[]): ViewRegistryItem[] {
  return ids.map((id) => {
    const view = VIEW_REGISTRY.find((item) => item.id === id);
    if (!view) throw new Error(`Missing view registry item: ${id}`);
    return view;
  });
}

export const VIEW_GROUPS: ViewGroup[] = [
  {
    id: "primary",
    label: "AI 工作台",
    items: pick(["workbench", "skills", "automation", "financial-manager", "workflows"])
  }
];
