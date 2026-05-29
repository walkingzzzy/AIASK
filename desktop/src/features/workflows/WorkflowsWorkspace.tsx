import { ArrowUpDown, BarChart3, Bell, Database, Factory, Flame, FlaskConical, Gauge, Landmark, LineChart, Radio, Scale, TrendingUp, Crosshair, Zap } from "lucide-react";
import type { MainView } from "../../types";
import { StatusBadge } from "../../components/shared";

const workflowCards: Array<{
  id: MainView;
  label: string;
  eyebrow: string;
  description: string;
  status: string;
  statusLabel: string;
  icon: typeof Factory;
}> = [
  {
    id: "data",
    label: "数据与同步",
    eyebrow: "数据准备",
    description: "检查 codes、周期、数据新鲜度和同步计划，是量化任务进入 AI 对话前的证据层。",
    status: "ready",
    statusLabel: "工作流入口",
    icon: Database
  },
  {
    id: "financial-manager",
    label: "金融经理台",
    eyebrow: "投资经理台",
    description: "统一查看组合、自选、风控、绩效、研究、量化、纸上交易、执行计划和券商只读连接。",
    status: "ready",
    statusLabel: "安全网关",
    icon: Landmark
  },
  {
    id: "quant",
    label: "量化研究",
    eyebrow: "研究报告",
    description: "运行结构化量化研究、查看阶段结果和报告，把研究证据接回对话与工厂。",
    status: "ready",
    statusLabel: "研究",
    icon: LineChart
  },
  {
    id: "strategy-factory",
    label: "策略工厂",
    eyebrow: "策略生成",
    description: "查看工厂状态、运行记录和评审快照，把策略生成作为 AI 可调用业务流程。",
    status: "ready",
    statusLabel: "工厂",
    icon: Factory
  },
  {
    id: "factor-factory",
    label: "因子工厂",
    eyebrow: "因子挖掘",
    description: "跟踪活跃因子池、引擎健康和 pool health，让因子挖掘沉到工作流层。",
    status: "ready",
    statusLabel: "研究",
    icon: BarChart3
  },
  {
    id: "incubation",
    label: "孵化工厂",
    eyebrow: "验证闭环",
    description: "观察策略生命周期、命中率报告和晋升信号，支持从研究到孵化的闭环。",
    status: "ready",
    statusLabel: "孵化",
    icon: FlaskConical
  },
  {
    id: "valuation",
    label: "估值分析",
    eyebrow: "内在价值",
    description: "DCF / DDM / 相对估值 / 情景 DCF / 共识估值一键生成，辅助价值判断。",
    status: "ready",
    statusLabel: "估值",
    icon: TrendingUp
  },
  {
    id: "trade-plan",
    label: "交易计划",
    eyebrow: "风险管理",
    description: "关键价位、ATR 止损止盈和场景化入场方案，生成完整交易计划。",
    status: "ready",
    statusLabel: "计划",
    icon: Crosshair
  },
  {
    id: "fund-flow",
    label: "资金流向",
    eyebrow: "市场资金",
    description: "北向资金、行业/概念资金流和个股主力资金，监控市场资金动向。",
    status: "ready",
    statusLabel: "资金",
    icon: ArrowUpDown
  }
];

const advancedWorkflowCards: Array<{
  id: MainView;
  label: string;
  description: string;
  icon: typeof Factory;
}> = [
  {
    id: "factory-events",
    label: "工厂事件",
    description: "创建、预览、审批和更新工厂事件，适合高级运营或排障时进入。",
    icon: Radio
  },
  {
    id: "event-console",
    label: "事件控制台",
    description: "查看事件流、空态和错误详情，默认不占用普通用户首屏。",
    icon: Zap
  }
];

const financialAnalysisCards: Array<{
  id: MainView;
  label: string;
  description: string;
  icon: typeof Factory;
}> = [
  {
    id: "decision",
    label: "买卖决策",
    description: "买入/卖出建议、决策共识和统一决策，不再只藏在金融经理台动作列表中。",
    icon: Scale
  },
  {
    id: "fundamental",
    label: "基本面",
    description: "基本面分析、杜邦分解和同行对比，统一进入专门工作台。",
    icon: Gauge
  },
  {
    id: "macro",
    label: "宏观经济",
    description: "GDP/CPI/PMI/M2 等宏观指标与市场概览。",
    icon: LineChart
  },
  {
    id: "alerts",
    label: "告警管理",
    description: "告警检查、指标告警和组合告警规则创建入口。",
    icon: Bell
  },
  {
    id: "limit-up",
    label: "涨停与龙虎",
    description: "涨停列表、涨停统计和大宗交易异动。",
    icon: Flame
  }
];

export function WorkflowsWorkspace({ onOpenView }: { onOpenView: (view: MainView) => void }) {
  return (
    <section className="capabilities-workspace workflow-hub">
      <header className="capabilities-header">
        <div>
          <span>工作流</span>
          <h1>AI 可调用的量化流程</h1>
          <p>这里聚合数据、策略、因子和孵化流程。普通用户通过对话发起任务，专业用户可在这里进入具体业务面板。</p>
        </div>
        <StatusBadge status="ready" label="业务入口" />
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>从对话到执行</span>
              <h2>把复杂工厂能力收拢成清晰工作流</h2>
              <p>策略、因子、孵化和数据同步仍完整保留，但它们不再抢占一级导航；AI 对话负责提出任务，这里负责业务运行和复核。</p>
            </div>
            <StatusBadge status="implemented" label="已重排" />
          </div>

          <section className="workflow-hub-grid" aria-label="核心工作流">
            {workflowCards.map((card) => {
              const Icon = card.icon;
              return (
                <article className="workflow-hub-card" key={card.id}>
                  <div className="workflow-hub-card-head">
                    <div className="workflow-icon">
                      <Icon size={18} />
                    </div>
                    <StatusBadge status={card.status} label={card.statusLabel} />
                  </div>
                  <span>{card.eyebrow}</span>
                  <h2>{card.label}</h2>
                  <p>{card.description}</p>
                  <button className="primary-button" onClick={() => onOpenView(card.id)} type="button">
                    打开{card.label}
                  </button>
                </article>
              );
            })}
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>金融分析扩展</span>
                <h3>把后端已实现能力做成明确入口</h3>
              </div>
              <StatusBadge status="implemented" label="专门面板" />
            </div>
            <div className="settings-shortcut-grid">
              {financialAnalysisCards.map((card) => {
                const Icon = card.icon;
                return (
                  <button className="settings-shortcut" key={card.id} onClick={() => onOpenView(card.id)} type="button">
                    <Icon size={16} />
                    <strong>{card.label}</strong>
                    <span>{card.description}</span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>高级入口</span>
                <h3>事件和排障留给专业场景</h3>
              </div>
              <StatusBadge status="not_required" label="默认收起" />
            </div>
            <div className="settings-shortcut-grid">
              {advancedWorkflowCards.map((card) => {
                const Icon = card.icon;
                return (
                  <button className="settings-shortcut" key={card.id} onClick={() => onOpenView(card.id)} type="button">
                    <Icon size={16} />
                    <strong>{card.label}</strong>
                    <span>{card.description}</span>
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}
