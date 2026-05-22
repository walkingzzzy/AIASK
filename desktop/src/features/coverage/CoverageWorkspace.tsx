import { RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type {
  CapabilityWorkbenchPayload,
  DesktopDataStatus,
  DesktopSettingsStatus,
  FactorFactoryStatus,
  HealthDetailed,
  ToolCatalogItem
} from "../../types";
import { CoverageMatrixPanel } from "../capabilities/CoverageMatrixPanel";

export function CoverageWorkspace({
  apiToken,
  controlToken,
  endpoint,
  health: initialHealth,
  tools: initialTools
}: {
  apiToken: string;
  controlToken: string;
  endpoint: string;
  health: HealthDetailed | null;
  tools: ToolCatalogItem[];
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [health, setHealth] = useState<HealthDetailed | null>(initialHealth);
  const [tools, setTools] = useState<ToolCatalogItem[]>(initialTools);
  const [settings, setSettings] = useState<DesktopSettingsStatus | null>(null);
  const [data, setData] = useState<DesktopDataStatus | null>(null);
  const [capabilities, setCapabilities] = useState<CapabilityWorkbenchPayload | null>(null);
  const [factor, setFactor] = useState<FactorFactoryStatus | null>(null);
  const [jobs, setJobs] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const [healthPayload, toolsPayload, settingsPayload, dataPayload, capabilitiesPayload, factorPayload, jobsPayload] = await Promise.all([
        api.health(),
        api.tools(),
        api.settingsStatus(),
        api.dataStatus(),
        api.capabilities(),
        api.factorFactoryStatus(80),
        api.jobsList()
      ]);
      setHealth(healthPayload);
      setTools(toolsPayload.data || []);
      setSettings(settingsPayload);
      setData(dataPayload);
      setCapabilities(capabilitiesPayload);
      setFactor(factorPayload);
      setJobs(jobsPayload.data || []);
      setMessage("COVERAGE_MATRIX_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>Coverage Matrix</span>
          <h1>Actual capability coverage</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? message : capabilities?.summary.source || "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            Refresh
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <CoverageMatrixPanel
          capabilities={capabilities}
          data={data}
          factor={factor}
          health={health}
          jobs={jobs}
          settings={settings}
          tools={tools}
        />
      </div>
    </section>
  );
}
