import { ListChecks, Play, Puzzle, Save, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact, localizeBlockedReason } from "../../components/shared";
import { PluginLifecycleCard, inferPluginLifecycleState } from "../../components/PluginLifecycleCard";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload, PluginCommand, PluginSummaryView, SkillPackStatusView } from "../../types";
import "../../components/PluginLifecycleCard.css";

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
  const [commandsByPlugin, setCommandsByPlugin] = useState<Record<string, PluginCommand[]>>({});
  const [upsertDraft, setUpsertDraft] = useState('{\n  "name": "local-plugin",\n  "enabled": true\n}');
  const [busy, setBusy] = useState(false);
  if (!payload) return <p className="muted">请刷新能力评审以加载插件状态。</p>;
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

  async function upsertPlugin() {
    if (!api) return;
    setBusy(true);
    try {
      const parsed = JSON.parse(upsertDraft || "{}") as Record<string, unknown>;
      const result = await api.pluginUpsert(parsed);
      setActionResult(result);
      await onRefresh?.();
    } catch (error) {
      setActionResult({ success: false, error: error instanceof SyntaxError ? "PLUGIN_JSON_INVALID" : formatApiError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function loadCommands(plugin: PluginSummaryView) {
    if (!api || !plugin.name) return;
    setBusy(true);
    try {
      const payload = await api.pluginCommands(plugin.name);
      setCommandsByPlugin((current) => ({ ...current, [plugin.name || ""]: payload.data || [] }));
      setActionResult(payload);
    } catch (error) {
      setActionResult({ success: false, error: formatApiError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function testCommand(plugin: PluginSummaryView, command: PluginCommand) {
    if (!api || !plugin.name) return;
    const commandName = String(command.name || command.command || "");
    if (!commandName) return;
    setBusy(true);
    try {
      setActionResult(await api.pluginCommandTest(plugin.name, commandName, {}));
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
          <span>插件</span>
          <h2>原生插件与技能包治理</h2>
          <p>这里是只读注册表视图，不会加载或执行外部 Hermes dashboard 插件 JavaScript。</p>
        </div>
        <StatusBadge status={status} label={gated ? "受控" : plugins.length ? "已加载" : "空"} />
      </div>

      {gated && (
        <div className="notice warn">
          <ShieldCheck size={15} />
          {localizeBlockedReason(pluginMeta.reason) || "需要控制令牌 Control token 才能查看原生插件注册表。"}
        </div>
      )}

      <div className="diagnostics-summary wide">
        <div className="metric-card">
          <span>插件</span>
          <strong>{plugins.length}</strong>
        </div>
        <div className="metric-card">
          <span>已启用</span>
          <strong>{enabledCount}</strong>
        </div>
        <div className="metric-card">
          <span>技能包</span>
          <strong>{availablePacks}</strong>
        </div>
        <div className="metric-card">
          <span>来源</span>
          <strong>{String(pluginMeta.source || skillPackPayload.object || "aiask_native")}</strong>
        </div>
      </div>

      <section className="capability-grid two">
        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{plugins.length} 项</span>
              <h3>原生插件</h3>
            </div>
          </div>

          {/* 使用新的生命周期卡片 */}
          <div className="plugins-lifecycle-list">
            {plugins.map((plugin, index) => {
              const lifecycleState = inferPluginLifecycleState({
                name: plugin.name || "unnamed-plugin",
                enabled: plugin.enabled ?? false,
                ready: typeof plugin.ready === 'boolean' ? plugin.ready : false,
                tools: plugin.tools ?? [],
                error: plugin.error ? String(plugin.error) : undefined
              });

              return (
                <PluginLifecycleCard
                  key={`${plugin.name || "plugin"}:${index}`}
                  name={plugin.name || "unnamed-plugin"}
                  state={lifecycleState}
                  onToggle={() => togglePlugin(plugin)}
                  onConfigure={() => {
                    setActionResult({
                      object: "aiask.plugin.configure_hint",
                      plugin: plugin.name,
                      note: "Edit the plugin manifest JSON below, then save through POST /v1/plugins.",
                    });
                  }}
                  onTest={() => testPlugin(plugin)}
                />
              );
            })}
          </div>

          {/* 保留原有的详细列表（可选展开） */}
          <details className="legacy-plugin-list" style={{ marginTop: "16px" }}>
            <summary>查看详细列表（传统视图）</summary>
            <div className="mini-list">
            {plugins.map((plugin, index) => (
              <article key={`${plugin.name || "plugin"}:${index}`}>
                <strong>{plugin.name || "unnamed-plugin"}</strong>
                <span>{plugin.source || plugin.version || "local"}</span>
                <StatusBadge status={plugin.enabled ? "implemented" : "disabled"} label={plugin.enabled ? "enabled" : "disabled"} />
                <p>{plugin.description || compact({ tools: plugin.tools?.length, commands: plugin.commands?.length, hooks: plugin.hooks?.length })}</p>
                <div className="row-actions">
                  <button
                    aria-label={plugin.enabled ? "禁用插件" : "启用插件"}
                    className="small-button"
                    disabled={busy || !(controlToken || "").trim()}
                    onClick={() => togglePlugin(plugin)}
                    title={plugin.enabled ? "禁用插件" : "启用插件"}
                    type="button"
                  >
                    {plugin.enabled ? "禁用" : "启用"}
                  </button>
                  <button
                    className="small-button"
                    disabled={busy || !(controlToken || "").trim()}
                    onClick={() => testPlugin(plugin)}
                    title={(plugin.tools || []).length ? "运行第一个已注册插件工具" : "对没有工具的插件运行 manifest 自检"}
                    type="button"
                  >
                    {(plugin.tools || []).length ? "测试工具" : "自检"}
                  </button>
                  <button
                    className="small-button"
                    disabled={busy || !(controlToken || "").trim()}
                    onClick={() => loadCommands(plugin)}
                    title="加载插件命令"
                    type="button"
                  >
                    <ListChecks size={13} />
                    命令
                  </button>
                </div>
                {!!commandsByPlugin[plugin.name || ""]?.length && (
                  <div className="mini-list">
                    {commandsByPlugin[plugin.name || ""].map((command, commandIndex) => {
                      const commandName = String(command.name || command.command || commandIndex);
                      return (
                        <article className="job-row" key={`${plugin.name}:${commandName}`}>
                          <div>
                            <strong>{commandName}</strong>
                            <span>{compact(command.description || command.enabled || "-")}</span>
                          </div>
                          <button
                            className="small-button"
                            disabled={busy || !(controlToken || "").trim()}
                            onClick={() => testCommand(plugin, command)}
                            title="测试插件命令"
                            type="button"
                          >
                            <Play size={13} />
                            测试
                          </button>
                        </article>
                      );
                    })}
                  </div>
                )}
              </article>
            ))}
            {!plugins.length && (
              <div className="empty-mini">
                <Puzzle size={24} />
                <span>尚未加载原生插件。</span>
              </div>
            )}
            </div>
          </details>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{String(skillPackPayload.status || skillPackPayload.object || "skill_packs")}</span>
              <h3>技能包</h3>
            </div>
            <StatusBadge status={String(skillPackPayload.status || "ready")} />
          </div>
          <JsonPanel value={skillPackPayload} />
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>POST /v1/plugins</span>
              <h3>插件 Upsert</h3>
            </div>
            <StatusBadge status={(controlToken || "").trim() ? "ready" : "gated"} />
          </div>
          <label className="field-row">
            <span>JSON</span>
            <textarea value={upsertDraft} onChange={(event) => setUpsertDraft(event.target.value)} />
          </label>
          <button className="small-button" disabled={busy || !(controlToken || "").trim()} onClick={upsertPlugin} type="button">
            <Save size={14} />
            保存插件
          </button>
        </div>
      </section>

      {resultRecord && (
        <div className={resultRecord.success === false ? "notice warn" : "notice ok"}>
          <strong>{String(resultRecord.error_code || resultRecord.object || "plugin_action")}</strong>
          <span>{String(resultRecord.error || resultData?.note || resultData?.test_type || "插件操作已完成。")}</span>
        </div>
      )}

      <details className="raw-details">
        <summary>原始插件 payload</summary>
        <JsonPanel value={{ plugins: pluginsPayload, skill_packs: skillPackPayload, actionResult }} />
      </details>
    </div>
  );
}
