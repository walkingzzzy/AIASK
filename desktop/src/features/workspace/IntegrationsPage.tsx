import { Cable, CircleGauge, PlugZap, Puzzle, ShieldCheck } from "lucide-react";
import { StatusBadge } from "../../components/shared";
import type { HealthDetailed, HermesStatus, MainView, ToolCatalogItem } from "../../types";

const integrationEntries: Array<{
  id: MainView;
  title: string;
  label: string;
  description: string;
  icon: typeof PlugZap;
  needsControl?: boolean;
}> = [
  {
    id: "mcp-connectors",
    title: "MCP and connectors",
    label: "MCP / Connectors",
    description: "Discover MCP servers, resources, prompts, OAuth status, and connector health.",
    icon: PlugZap,
    needsControl: true
  },
  {
    id: "gateway",
    title: "Gateway delivery",
    label: "Gateway",
    description: "Inspect platforms, daemon state, messages, directory, retry, and send intents.",
    icon: Cable,
    needsControl: true
  },
  {
    id: "plugins-skills",
    title: "Plugins and skills",
    label: "Plugins / Skills",
    description: "Manage native plugin lifecycle and apply skills back into the Workbench.",
    icon: Puzzle,
    needsControl: true
  },
  {
    id: "readiness-health",
    title: "Readiness and health",
    label: "Readiness / Health",
    description: "Review provider, MCP, gateway, plugin, and finance readiness gates.",
    icon: CircleGauge
  }
];

export function IntegrationsPage({
  controlToken,
  health,
  hermesStatus,
  onOpenView,
  tools
}: {
  controlToken: string;
  health: HealthDetailed | null;
  hermesStatus: HermesStatus | null;
  onOpenView: (view: MainView) => void;
  tools: ToolCatalogItem[];
}) {
  const controlReady = Boolean(controlToken.trim());
  const fullModeReady = Boolean(health?.hermes?.full_mode_active || hermesStatus?.full_mode_active);

  return (
    <section className="capabilities-workspace optimization-page">
      <header className="capabilities-header">
        <div>
          <span>Ops</span>
          <h1>Integrations</h1>
          <p>Unified hub for MCP, Gateway, Plugins, Skills, connectors, and readiness. Gated actions remain visible and safe.</p>
        </div>
        <div className="header-actions">
          <StatusBadge status={controlReady ? "ready" : "gated"} label={controlReady ? "control ready" : "control gated"} />
          <StatusBadge status={fullModeReady ? "ready" : "gated"} label={fullModeReady ? "full mode" : "safe mode"} />
          <StatusBadge status="ready" label={`${tools.length || health?.tools?.count || 0} tools`} />
        </div>
      </header>

      <div className="capabilities-body">
        <div className="optimization-grid">
          {integrationEntries.map((entry) => {
            const Icon = entry.icon;
            const gated = entry.needsControl && !controlReady;
            return (
              <button className="optimization-card action-card" key={entry.id} onClick={() => onOpenView(entry.id)} type="button">
                <Icon size={18} />
                <span>{entry.label}</span>
                <h2>{entry.title}</h2>
                <p>{entry.description}</p>
                <StatusBadge status={gated ? "gated" : "ready"} label={gated ? "control token required" : "ready"} />
              </button>
            );
          })}
        </div>

        <section className="capability-section">
          <div className="section-header">
            <div>
              <span>Safety</span>
              <h3>ActionIntent remains authoritative</h3>
            </div>
            <ShieldCheck size={18} />
          </div>
          <p className="muted">
            This hub only reorganizes the frontend entry points. Stateful integration actions still use the existing Agent
            routes, Control token gates, and approval flows.
          </p>
        </section>
      </div>
    </section>
  );
}
