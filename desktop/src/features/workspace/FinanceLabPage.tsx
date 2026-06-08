import { BarChart3, Database, Factory, FlaskConical, Landmark, LineChart, Radio } from "lucide-react";
import { StatusBadge } from "../../components/shared";
import type { MainView } from "../../types";

const financeTemplates: Array<{
  id: MainView;
  title: string;
  label: string;
  description: string;
  icon: typeof Landmark;
}> = [
  {
    id: "financial-manager",
    title: "Portfolio and risk",
    label: "Financial Manager",
    description: "Portfolio, watchlist, risk, and controlled execution entry point.",
    icon: Landmark
  },
  {
    id: "quant",
    title: "Research run",
    label: "Quant Research",
    description: "Structured research runs and report review.",
    icon: LineChart
  },
  {
    id: "strategy-factory",
    title: "Strategy generation",
    label: "Strategy Factory",
    description: "Generate, review, and gate strategy candidates.",
    icon: Factory
  },
  {
    id: "factor-factory",
    title: "Factor mining",
    label: "Factor Factory",
    description: "Mine factors and inspect active pool health.",
    icon: BarChart3
  },
  {
    id: "incubation",
    title: "Incubation lifecycle",
    label: "Incubation Factory",
    description: "Review hit-rate, lifecycle state, and promotion readiness.",
    icon: FlaskConical
  },
  {
    id: "data",
    title: "Data readiness",
    label: "Data",
    description: "Check data freshness, sync planning, and preflight status.",
    icon: Database
  },
  {
    id: "factory-events",
    title: "Factory events",
    label: "Factory Events",
    description: "Create, preview, approve, and review factory events.",
    icon: Radio
  }
];

export function FinanceLabPage({
  onOpenView
}: {
  onOpenView: (view: MainView) => void;
}) {
  return (
    <section className="capabilities-workspace optimization-page">
      <header className="capabilities-header">
        <div>
          <span>Finance</span>
          <h1>Finance Lab</h1>
          <p>Start finance work as task templates. Results should flow back into the current thread as artifacts and approval items.</p>
        </div>
        <div className="header-actions">
          <StatusBadge status="ready" label={`${financeTemplates.length} templates`} />
        </div>
      </header>

      <div className="capabilities-body">
        <div className="optimization-grid">
          {financeTemplates.map((template) => {
            const Icon = template.icon;
            return (
              <button className="optimization-card action-card" key={template.id} onClick={() => onOpenView(template.id)} type="button">
                <Icon size={18} />
                <span>{template.label}</span>
                <h2>{template.title}</h2>
                <p>{template.description}</p>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
