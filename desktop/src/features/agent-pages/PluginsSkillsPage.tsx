import { Puzzle, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useMemo } from "react";
import { MetricCard, StatusBadge, compact } from "../../components/shared";
import { PluginsPanel } from "../capabilities/PluginsPanel";
import { SkillsPanel } from "../skills/SkillsPanel";
import { useCapabilityWorkbench } from "../../hooks/useCapabilityWorkbench";
import type { CapabilityWorkbenchPayload, PluginSummaryView, SkillPackStatusView, SkillView } from "../../types";
import "../../components/AgentEnhancements.css";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function pluginList(value: unknown): PluginSummaryView[] {
  if (Array.isArray(value)) return value.filter((item) => item && typeof item === "object") as PluginSummaryView[];
  const record = asRecord(value);
  return Array.isArray(record.data)
    ? (record.data.filter((item) => item && typeof item === "object") as PluginSummaryView[])
    : [];
}

function readinessOf(plugin: PluginSummaryView): string {
  if (plugin.error || plugin.failure_reason || plugin.error_code) return "failed";
  if (plugin.ready === true || plugin.status === "ready") return "ready";
  if (plugin.configured === false) return "unconfigured";
  if (plugin.enabled) return "enabled";
  return "disabled";
}

function summarize(payload: CapabilityWorkbenchPayload | null) {
  const skillsPayload = payload?.skills;
  const skills = Array.isArray(skillsPayload?.skills) ? (skillsPayload.skills as SkillView[]) : [];
  const plugins = pluginList(payload?.plugins);
  const skillPacks = (payload?.skill_packs || payload?.hermes?.skill_packs || {}) as SkillPackStatusView;
  const enabledPlugins = plugins.filter((plugin) => plugin.enabled).length;
  const configuredPlugins = plugins.filter((plugin) => plugin.configured === true || (plugin.tools || []).length || (plugin.commands || []).length).length;
  const readyPlugins = plugins.filter((plugin) => readinessOf(plugin) === "ready").length;
  const failedPlugins = plugins.filter((plugin) => readinessOf(plugin) === "failed").length;
  const toolCount = plugins.reduce((total, plugin) => total + (plugin.tools || []).length, 0);
  const commandCount = plugins.reduce((total, plugin) => total + (plugin.commands || []).length, 0);
  const hookCount = plugins.reduce((total, plugin) => total + (plugin.hooks || []).length, 0);
  return {
    skills,
    plugins,
    skillPacks,
    enabledPlugins,
    configuredPlugins,
    readyPlugins,
    failedPlugins,
    toolCount,
    commandCount,
    hookCount,
  };
}

export function PluginsSkillsPage({
  endpoint,
  apiToken,
  controlToken,
  onApplyToChat,
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  onApplyToChat: (skill: SkillView | null) => void;
}) {
  const { payload, message, busy, refresh } = useCapabilityWorkbench(endpoint, apiToken, controlToken);
  const summary = useMemo(() => summarize(payload), [payload]);

  useEffect(() => {
    refresh().catch(() => undefined);
  }, [refresh]);

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>集成能力</span>
          <h1>插件 / 技能</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={controlToken.trim() ? "ready" : "gated"} label={controlToken.trim() ? "控制已就绪" : "需要控制令牌"} />
          <StatusBadge status={message || "not_loaded"} label={message || "未加载"} />
          <button className="small-button" disabled={busy} onClick={() => refresh()} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>生命周期</span>
              <h2>原生插件与技能操作</h2>
              <p>安装、启用、配置、准备度、失败原因，以及工具/命令/钩子数量都来自 Agent API。</p>
            </div>
            <Puzzle size={22} />
          </div>

          <div className="diagnostics-summary wide">
            <MetricCard label="技能" value={summary.skills.length} status={summary.skills.length ? "ready" : "not_loaded"} />
            <MetricCard label="插件" value={summary.plugins.length} status={summary.plugins.length ? "ready" : "not_loaded"} />
            <MetricCard label="已启用" value={summary.enabledPlugins} status={summary.enabledPlugins ? "ready" : "disabled"} />
            <MetricCard label="已配置" value={summary.configuredPlugins} status={summary.configuredPlugins ? "ready" : "unconfigured"} />
            <MetricCard label="就绪" value={summary.readyPlugins} status={summary.readyPlugins ? "ready" : "not_loaded"} />
            <MetricCard label="失败" value={summary.failedPlugins} status={summary.failedPlugins ? "failed" : "ready"} />
            <MetricCard label="工具" value={summary.toolCount} status={summary.toolCount ? "ready" : "not_loaded"} />
            <MetricCard label="命令" value={summary.commandCount} status={summary.commandCount ? "ready" : "not_loaded"} />
            <MetricCard label="钩子" value={summary.hookCount} status={summary.hookCount ? "ready" : "not_loaded"} />
          </div>

          <section className="agent-management-panel">
            <div className="section-header inline-section-header">
                <div>
                  <span>应用到对话</span>
                  <h3>技能</h3>
                </div>
                <Sparkles size={18} />
              </div>
              <SkillsPanel
                apiToken={apiToken}
                controlToken={controlToken}
                endpoint={endpoint}
                management
                onApplyToChat={onApplyToChat}
                onRefresh={refresh}
                payload={payload}
              />
          </section>

          <section className="agent-management-panel">
            <div className="section-header inline-section-header">
                <div>
                  <span>{compact(summary.skillPacks.status || summary.skillPacks.object || "skill_packs")}</span>
                  <h3>插件</h3>
                </div>
                <StatusBadge status={summary.failedPlugins ? "failed" : summary.readyPlugins ? "ready" : "not_loaded"} />
              </div>
              <PluginsPanel
                apiToken={apiToken}
                controlToken={controlToken}
                endpoint={endpoint}
                onRefresh={refresh}
                payload={payload}
              />
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>失败原因</span>
                <h3>插件准备度详情</h3>
              </div>
            </div>
            <div className="data-table plugin-readiness-table">
              <div className="table-head">
                <span>插件</span>
                <span>准备度</span>
                <span>数量</span>
                <span>失败原因</span>
              </div>
              {summary.plugins.map((plugin, index) => (
                <div className="table-row" key={`${plugin.name || "plugin"}:${index}`}>
                  <strong>{plugin.name || "unnamed-plugin"}</strong>
                  <span>{readinessOf(plugin)}</span>
                  <span>
                    工具 {(plugin.tools || []).length} / 命令 {(plugin.commands || []).length} / 钩子 {(plugin.hooks || []).length}
                  </span>
                  <span>{String(plugin.failure_reason || plugin.error || plugin.error_code || "-")}</span>
                </div>
              ))}
              {!summary.plugins.length && <div className="table-empty">暂无插件。</div>}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}
