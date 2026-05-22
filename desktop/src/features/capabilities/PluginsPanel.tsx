import { Puzzle, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload, PluginSummaryView, SkillPackStatusView } from "../../types";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function pluginList(value: unknown): PluginSummaryView[] {
  if (Array.isArray(value)) return value.filter((item) => item && typeof item === "object") as PluginSummaryView[];
  const record = asRecord(value);
  const data = record.data;
  if (Array.isArray(data)) return data.filter((item) => item && typeof item === "object") as PluginSummaryView[];
  return [];
}

function actionRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

export function PluginsPanel({
  payload,
  endpoint,
  apiToken,
  controlToken,
  onRefresh
}: {
  payload: CapabilityWorkbenchPayload | null;
  endpoint?: string;
  apiToken?: string;
  controlToken?: string;
  onRefresh?: () => Promise<unknown>;
}) {
  const api = useMemo(
    () => (endpoint ? new AiaskApi({ endpoint, apiToken: apiToken || "", controlToken: controlToken || "" }) : null),
    [apiToken, controlToken, endpoint]
  );
  const [actionResult, setActionResult] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!payload) return <p className="muted">Refresh capabilities to load plugin state.</p>;
  const pluginsPayload = payload.plugins;
  const skillPackPayload = (payload.skill_packs || payload.hermes?.skill_packs || {}) as SkillPackStatusView;
  const plugins = pluginList(pluginsPayload);
  const pluginMeta = asRecord(pluginsPayload);
  const gated = pluginMeta.gated === true;
  const enabledCount = plugins.filter((plugin) => plugin.enabled).length;
  const status = gated ? "gated" : plugins.length ? "implemented" : "not_loaded";
  const availablePacks = Array.isArray(skillPackPayload.packs) ? skillPackPayload.packs.length : skillPackPayload.available_count ?? "-";
  const resultRecord = actionRecord(actionResult);
  const resultData = actionRecord(resultRecord?.data);

  async function togglePlugin(plugin: PluginSummaryView) {
    if (!api || !plugin.name) return;
    setBusy(true);
    try {
      const result = await api.pluginToggle(plugin.name, !plugin.enabled);
      setActionResult(result);
      await onRefresh?.();
    } catch (error) {
      setActionResult({ success: false, error: formatApiError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function testPlugin(plugin: PluginSummaryView) {
    if (!api || !plugin.name) return;
    const firstTool = (plugin.tools || []).find((tool) => tool && typeof tool === "object") as Record<string, unknown> | undefined;
    const toolName = String(firstTool?.name || "__manifest__");
    setBusy(true);
    try {
      setActionResult(await api.pluginToolTest(plugin.name, toolName, {}));
    } catch (error) {
      setActionResult({ success: false, error: formatApiError(error) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>Plugins</span>
          <h2>Native plugin and skill-pack governance</h2>
          <p>Read-only registry view. External Hermes dashboard plugin JavaScript is not loaded or executed.</p>
        </div>
        <StatusBadge status={status} label={gated ? "gated" : plugins.length ? "loaded" : "empty"} />
      </div>

      {gated && (
        <div className="notice warn">
          <ShieldCheck size={15} />
          {String(pluginMeta.reason || "Control token required to inspect native plugin registry.")}
        </div>
      )}

      <div className="diagnostics-summary wide">
        <div className="metric-card">
          <span>Plugins</span>
          <strong>{plugins.length}</strong>
        </div>
        <div className="metric-card">
          <span>Enabled</span>
          <strong>{enabledCount}</strong>
        </div>
        <div className="metric-card">
          <span>Skill packs</span>
          <strong>{availablePacks}</strong>
        </div>
        <div className="metric-card">
          <span>Source</span>
          <strong>{String(pluginMeta.source || skillPackPayload.object || "aiask_native")}</strong>
        </div>
      </div>

      <section className="capability-grid two">
        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{plugins.length} items</span>
              <h3>Native plugins</h3>
            </div>
          </div>
          <div className="mini-list">
            {plugins.map((plugin, index) => (
              <article key={`${plugin.name || "plugin"}:${index}`}>
                <strong>{plugin.name || "unnamed-plugin"}</strong>
                <span>{plugin.source || plugin.version || "local"}</span>
                <StatusBadge status={plugin.enabled ? "implemented" : "disabled"} label={plugin.enabled ? "enabled" : "disabled"} />
                <p>{plugin.description || compact({ tools: plugin.tools?.length, commands: plugin.commands?.length, hooks: plugin.hooks?.length })}</p>
                <div className="row-actions">
                  <button className="small-button" disabled={busy || !(controlToken || "").trim()} onClick={() => togglePlugin(plugin)} type="button">
                    {plugin.enabled ? "Disable" : "Enable"}
                  </button>
                  <button
                    className="small-button"
                    disabled={busy || !(controlToken || "").trim()}
                    onClick={() => testPlugin(plugin)}
                    title={(plugin.tools || []).length ? "Run the first registered plugin tool" : "Run a manifest self-test for plugins without tools"}
                    type="button"
                  >
                    {(plugin.tools || []).length ? "Test tool" : "Self-test"}
                  </button>
                </div>
              </article>
            ))}
            {!plugins.length && (
              <div className="empty-mini">
                <Puzzle size={24} />
                <span>{gated ? "Unlock with a control token to inspect plugins." : "No native plugins registered."}</span>
              </div>
            )}
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{String(skillPackPayload.status || skillPackPayload.object || "skill_packs")}</span>
              <h3>Skill packs</h3>
            </div>
            <StatusBadge status={String(skillPackPayload.status || "ready")} />
          </div>
          <JsonPanel value={skillPackPayload} />
        </div>
      </section>

      {resultRecord && (
        <div className={resultRecord.success === false ? "notice warn" : "notice ok"}>
          <strong>{String(resultRecord.error_code || resultRecord.object || "plugin_action")}</strong>
          <span>{String(resultRecord.error || resultData?.note || resultData?.test_type || "Plugin action completed.")}</span>
        </div>
      )}

      <details className="raw-details">
        <summary>Raw plugin payload</summary>
        <JsonPanel value={{ plugins: pluginsPayload, skill_packs: skillPackPayload, actionResult }} />
      </details>
    </div>
  );
}
