import { BrainCircuit, CheckCircle2, ExternalLink, KeyRound, ListRestart, PlugZap, RefreshCw, Save, Search, TestTube2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact, statusLabel } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { AiConfigPayload, AiProviderPreset, AiSmokeResult, DesktopSettingsStatus } from "../../types";

type ModelForm = {
  preset: string;
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  replace_api_key: boolean;
  prompt_cache_enabled: boolean;
  prompt_cache_recent_messages: number;
};

type ModelsPayload = {
  data?: Array<Record<string, unknown>>;
  configured?: boolean;
  unsupported?: boolean;
  error?: string;
  warning?: string;
  warning_code?: string;
  secrets_redacted?: boolean;
};

const DEFAULT_PROMPT = "Reply with AIASK_MODEL_OK.";

function firstString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function modelId(item: Record<string, unknown>): string {
  return firstString(item.id) || firstString(item.name) || firstString(item.model);
}

function fuzzyMatch(query: string, values: unknown[]): boolean {
  const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const haystack = values
    .flatMap((value) => Array.isArray(value) ? value : [value])
    .map((value) => String(value || "").toLowerCase())
    .join(" ");
  return tokens.every((token) => haystack.includes(token) || orderedTokenMatch(haystack, token));
}

function orderedTokenMatch(haystack: string, token: string): boolean {
  let offset = 0;
  for (const char of token) {
    const found = haystack.indexOf(char, offset);
    if (found < 0) return false;
    offset = found + 1;
  }
  return true;
}

function presetMatchesCurrent(preset: AiProviderPreset, current: AiConfigPayload["current"] | undefined): boolean {
  if (!current) return false;
  if (preset.provider !== current.provider) return false;
  if (preset.id === "custom-openai-compatible") return false;
  return Boolean((preset.default_model && preset.default_model === current.model) || (preset.base_url && preset.base_url === current.base_url));
}

function formFromConfig(config: AiConfigPayload | null): ModelForm {
  const current = config?.current;
  const preset = config?.presets.find((item) => presetMatchesCurrent(item, current));
  return {
    preset: preset?.id || (current?.provider === "mock" ? "mock" : "custom-openai-compatible"),
    provider: current?.provider || "openai",
    model: current?.model || "gpt-4.1-mini",
    base_url: current?.base_url || "",
    api_key: "",
    replace_api_key: false,
    prompt_cache_enabled: Boolean(current?.prompt_cache?.requested_enabled ?? current?.prompt_cache?.enabled ?? current?.provider === "anthropic"),
    prompt_cache_recent_messages: Number(current?.prompt_cache?.recent_non_system_messages ?? 3) || 3
  };
}

function applyPreset(form: ModelForm, preset?: AiProviderPreset): ModelForm {
  if (!preset) return form;
  const keyOptional = preset.provider === "mock" || Boolean(preset.api_key_optional);
  return {
    ...form,
    preset: preset.id,
    provider: preset.provider,
    model: preset.default_model || form.model,
    base_url: preset.base_url || "",
    api_key: "",
    replace_api_key: keyOptional,
    prompt_cache_enabled: preset.provider === "anthropic" ? true : form.prompt_cache_enabled,
    prompt_cache_recent_messages: form.prompt_cache_recent_messages || 3
  };
}

const CATEGORY_ORDER = ["domestic", "international", "local", "custom", "mock"] as const;

const CATEGORY_LABELS: Record<string, string> = {
  domestic: "国产厂商",
  international: "国际厂商",
  local: "本地部署",
  custom: "自定义",
  mock: "开发 / Mock"
};

function presetCategory(preset: AiProviderPreset): string {
  const category = (preset.category || "").trim();
  if (category && category in CATEGORY_LABELS) return category;
  if (preset.provider === "mock") return "mock";
  if (preset.id === "custom-openai-compatible") return "custom";
  return "custom";
}

function groupPresets(presets: AiProviderPreset[]): Array<{ key: string; label: string; items: AiProviderPreset[] }> {
  const buckets = new Map<string, AiProviderPreset[]>();
  for (const preset of presets) {
    const key = presetCategory(preset);
    const bucket = buckets.get(key) || [];
    bucket.push(preset);
    buckets.set(key, bucket);
  }
  const ordered = [...CATEGORY_ORDER, ...[...buckets.keys()].filter((key) => !CATEGORY_ORDER.includes(key as (typeof CATEGORY_ORDER)[number]))];
  const groups: Array<{ key: string; label: string; items: AiProviderPreset[] }> = [];
  for (const key of ordered) {
    const items = buckets.get(key);
    if (items && items.length) {
      groups.push({ key, label: CATEGORY_LABELS[key] || key, items });
    }
  }
  return groups;
}

function statusFromMessage(message: string, configured?: boolean): string {
  const normalized = message.toUpperCase();
  if (normalized.includes("FAILED") || normalized.includes("ERROR") || normalized.includes("DENIED") || normalized.includes("BLOCKED")) return "failed";
  if (normalized.includes("REQUIRED")) return "gated";
  if (message === "NOT_LOADED") return "not_loaded";
  if (normalized.includes("LOADED") || normalized.includes("PASSED") || normalized.includes("CONFIGURED")) return "ready";
  if (normalized.includes("UNCONFIGURED")) return "unconfigured";
  if (configured) return "ready";
  return "unconfigured";
}

function userMessage(message?: string): string {
  if (!message) return "";
  const normalized = message.toLowerCase();
  if (normalized.includes("permissiondenied") || normalized.includes("blocked")) {
    return "模型请求被服务商或网络策略拦截；当前配置仍已保存，请检查 Base URL、密钥权限、模型名或网络出口。";
  }
  if (normalized.includes("control_token_required")) return "需要控制令牌后才能保存配置。";
  return statusLabel(message);
}

function presetNote(preset?: AiProviderPreset): string {
  const note = preset?.notes?.[0] || "";
  if (note.toLowerCase().includes("fill in provider base url")) {
    return "填写提供方控制台给出的 Base URL、API Key 和模型名；已保存的密钥不会在页面回显。";
  }
  return note || "选择预设后只需要补齐密钥；自定义兼容服务需要同时填写 Base URL 和模型 ID。";
}

export function ModelsWorkspace({
  endpoint,
  apiToken,
  controlToken
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [settings, setSettings] = useState<DesktopSettingsStatus | null>(null);
  const [config, setConfig] = useState<AiConfigPayload | null>(null);
  const [models, setModels] = useState<ModelsPayload | null>(null);
  const [smoke, setSmoke] = useState<AiSmokeResult | null>(null);
  const [form, setForm] = useState<ModelForm>(() => formFromConfig(null));
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [presetQuery, setPresetQuery] = useState("");
  const [modelQuery, setModelQuery] = useState("");
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState<"refresh" | "save" | "models" | "smoke" | null>(null);

  async function refresh() {
    setBusy("refresh");
    try {
      const [settingsPayload, configPayload, modelsPayload] = await Promise.all([
        api.settingsStatus(),
        api.aiConfig(),
        api.aiModels()
      ]);
      setSettings(settingsPayload);
      setConfig(configPayload);
      setModels(modelsPayload);
      setForm(formFromConfig(configPayload));
      setMessage("MODEL_STATUS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(null);
    }
  }

  async function saveConfig() {
    setBusy("save");
    try {
      const saved = await api.aiConfigSave({
        preset: form.preset,
        provider: form.provider,
        model: form.model,
        base_url: form.base_url,
        api_key: form.api_key,
        replace_api_key: form.replace_api_key,
        prompt_cache_enabled: form.prompt_cache_enabled,
        prompt_cache_recent_messages: form.prompt_cache_recent_messages
      });
      setMessage(saved.saved ? "CONFIGURED" : "AIASK_ERROR");
      setForm((current) => ({ ...current, api_key: "", replace_api_key: false }));
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(null);
    }
  }

  async function fetchModels() {
    setBusy("models");
    try {
      const payload = await api.aiModels();
      setModels(payload);
      setMessage(payload.configured ? "MODELS_LOADED" : payload.error || "UNCONFIGURED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(null);
    }
  }

  async function runSmoke() {
    setBusy("smoke");
    try {
      const result = await api.aiSmoke(prompt, form.model);
      setSmoke(result);
      setMessage(result.success ? "PASSED" : result.error_code || "FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  const ai = settings?.llm.ai_status || config?.current;
  const providerStatus =
    settings?.llm.providers && typeof settings.llm.providers === "object"
      ? (settings.llm.providers as Record<string, unknown>)
      : {};
  const providers = Array.isArray(providerStatus.providers) ? providerStatus.providers as Array<Record<string, unknown>> : [];
  const presets = config?.presets || [];
  const activePreset = presets.find((item) => item.id === form.preset);
  const filteredPresets = presets.filter((preset) =>
    fuzzyMatch(presetQuery, [preset.id, preset.label, preset.provider, preset.provider_type, preset.base_url, preset.default_model, preset.notes])
  );
  const presetGroups = groupPresets(filteredPresets);
  const apiKeyOptional = form.provider === "mock" || Boolean(activePreset?.api_key_optional);
  const availableModels = Array.isArray(models?.data) ? models.data.filter((item) => modelId(item)) : [];
  const filteredModels = availableModels.filter((item) => fuzzyMatch(modelQuery, [modelId(item), item.owned_by, item.display_name, item.object]));
  const hasKeyForSave = apiKeyOptional || Boolean(form.api_key.trim()) || Boolean(config?.current.api_key_configured);
  const canSave = Boolean(controlToken.trim()) && Boolean(form.provider.trim()) && hasKeyForSave && (form.provider === "mock" || Boolean(form.model.trim()));
  const selectedProvider = form.provider === "anthropic" ? "Anthropic" : form.provider === "mock" ? "本地 Mock" : "OpenAI 兼容";
  const configSource = settings?.llm.ai_status?.config_source || config?.config_source;
  const promptCache = config?.current.prompt_cache || settings?.llm.ai_status?.prompt_cache;

  return (
    <section className="capabilities-workspace models-workspace">
      <header className="capabilities-header">
        <div>
          <span>模型配置</span>
          <h1>LLM 提供方、模型获取与测试</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={statusFromMessage(message, ai?.configured)} label={userMessage(message) || statusLabel(message)} technicalLabel={message} />
          <button className="small-button" disabled={busy !== null} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy === "refresh" ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>{ai?.provider || "-"}</span>
              <h2>{ai?.model || "模型未加载"}</h2>
              <p>在应用端选择提供方、填写模型和密钥，Agent 会写入项目 .env 并刷新运行时模型客户端。保存后可立即获取模型列表，并用一次最小请求验证密钥、Base URL、模型名和网络连通性。</p>
            </div>
            <BrainCircuit size={24} />
          </div>

          <div className="diagnostics-summary wide">
            <MetricCard label="当前提供方" value={ai?.provider || "-"} status={ai?.configured ? "ready" : "unconfigured"} />
            <MetricCard label="API 密钥" value={ai?.api_key_configured ? "已配置" : "缺失 / Mock"} status={ai?.api_key_configured || ai?.mock ? "ready" : "partial"} />
            <MetricCard label="Base URL" value={ai?.base_url_configured ? "已配置" : "默认"} status="ready" />
            <MetricCard label="配置来源" value={configSource?.loaded ? String(configSource.source || "project") : "进程环境"} status="ready" />
            <MetricCard label="提供方池" value={compact(providerStatus.configured_count || 0)} status={(providerStatus.configured_count as number) ? "ready" : "partial"} />
            <MetricCard label="Prompt Cache" value={promptCache?.enabled ? "已启用" : promptCache?.requested_enabled ? "待支持" : "关闭"} status={promptCache?.enabled ? "ready" : promptCache?.supported ? "partial" : "not_loaded"} />
          </div>

          <section className="capability-grid two">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>简易配置</span>
                  <h3>选择提供方预设</h3>
                </div>
                <StatusBadge status={controlToken.trim() ? "ready" : "gated"} label={controlToken.trim() ? "可保存" : "需要控制令牌"} />
              </div>

              <label className="model-picker-search">
                <Search size={14} />
                <input
                  aria-label="Search provider presets"
                  onChange={(event) => setPresetQuery(event.target.value)}
                  placeholder="Search providers, endpoints, models"
                  type="search"
                  value={presetQuery}
                />
              </label>

              <div className="preset-groups">
                {presetGroups.map((group) => (
                  <div className="preset-group" key={group.key}>
                    <span className="preset-group-title">{group.label}</span>
                    <div className="preset-grid">
                      {group.items.map((preset) => (
                        <button
                          className={`preset-tile ${form.preset === preset.id ? "active" : ""}`}
                          key={preset.id}
                          onClick={() => setForm((current) => applyPreset(current, preset))}
                          title={preset.notes?.[0] || preset.label}
                          type="button"
                        >
                          <span>{preset.label}</span>
                          <small>{preset.default_model || preset.provider_type || preset.provider}</small>
                          {form.preset === preset.id ? <CheckCircle2 size={15} /> : <PlugZap size={15} />}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
                {!presetGroups.length ? <p className="muted">No provider presets match the current search.</p> : null}
              </div>

              <div className="settings-form-grid">
                <label>
                  <span>Provider</span>
                  <select value={form.provider} onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value, preset: "custom-openai-compatible" }))}>
                    <option value="openai">OpenAI 兼容</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="mock">Mock</option>
                  </select>
                </label>
                <label>
                  <span>模型</span>
                  <input value={form.model} onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))} placeholder={activePreset?.default_model || "gpt-4.1-mini"} />
                </label>
                <label className="wide-field">
                  <span>Base URL</span>
                  <input value={form.base_url} onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))} placeholder={activePreset?.base_url || "https://api.openai.com/v1"} />
                </label>
                <label className="wide-field">
                  <span>API Key</span>
                  <input
                    autoComplete="off"
                    type="password"
                    value={form.api_key}
                    onChange={(event) => setForm((current) => ({ ...current, api_key: event.target.value }))}
                    placeholder={
                      apiKeyOptional
                        ? "本地服务可留空（或填任意占位符，如 ollama）"
                        : config?.current.api_key_configured
                          ? "已配置，留空则沿用现有密钥"
                          : "粘贴提供方控制台创建的 API Key"
                    }
                  />
                </label>
                <label className="inline-check wide-field">
                  <input checked={form.replace_api_key} onChange={(event) => setForm((current) => ({ ...current, replace_api_key: event.target.checked }))} type="checkbox" />
                  <span>替换现有 API Key；勾选且留空会清空密钥</span>
                </label>
                <label className="inline-check wide-field">
                  <input checked={form.prompt_cache_enabled} onChange={(event) => setForm((current) => ({ ...current, prompt_cache_enabled: event.target.checked }))} type="checkbox" />
                  <span>启用 Anthropic prompt cache 标记</span>
                </label>
                <label>
                  <span>缓存最近消息数</span>
                  <input
                    min={0}
                    max={20}
                    type="number"
                    value={form.prompt_cache_recent_messages}
                    onChange={(event) => setForm((current) => ({ ...current, prompt_cache_recent_messages: Number(event.target.value) || 0 }))}
                  />
                </label>
              </div>

              <div className="settings-actions">
                <button className="primary-button" disabled={!canSave || busy !== null} onClick={saveConfig} type="button">
                  <Save size={15} />
                  保存配置
                </button>
                {activePreset?.api_key_url ? (
                  <a className="small-button link-button" href={activePreset.api_key_url} rel="noreferrer" target="_blank">
                    <KeyRound size={14} />
                    获取密钥
                  </a>
                ) : null}
                {activePreset?.docs_url ? (
                  <a className="small-button link-button" href={activePreset.docs_url} rel="noreferrer" target="_blank">
                    <ExternalLink size={14} />
                    官方文档
                  </a>
                ) : null}
              </div>

              <div className="mini-list model-config-notes">
                <article>
                  <strong>{selectedProvider}</strong>
                  <span>{presetNote(activePreset)}</span>
                  <StatusBadge status={form.provider === "mock" || hasKeyForSave ? "ready" : "partial"} />
                </article>
                {!controlToken.trim() ? (
                  <article>
                    <strong>控制令牌缺失</strong>
                    <span>保存配置会修改 Agent 管理的 .env，因此需要在设置中填写控制令牌。</span>
                    <StatusBadge status="gated" />
                  </article>
                ) : null}
                {!hasKeyForSave ? (
                  <article>
                    <strong>需要 API Key</strong>
                    <span>真实模型提供方需要密钥；Mock 可用于无外网或开发验证。</span>
                    <StatusBadge status="partial" />
                  </article>
                ) : null}
                <article>
                  <strong>Prompt cache</strong>
                  <span>
                    {promptCache?.enabled
                      ? `已对 system prompt 和最近 ${promptCache.recent_non_system_messages ?? 0} 条非 system 消息启用 cache_control。`
                      : promptCache?.supported
                        ? "提供方支持 prompt cache，可保存配置后启用。"
                        : "当前提供方未声明兼容 Anthropic cache_control。"}
                  </span>
                  <StatusBadge status={promptCache?.enabled ? "ready" : promptCache?.supported ? "partial" : "not_loaded"} />
                </article>
              </div>
            </article>

            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>获取与测试</span>
                  <h3>模型列表 / 冒烟测试</h3>
                </div>
                <StatusBadge status={smoke?.success ? "passed" : models ? "ready" : "not_loaded"} />
              </div>

              <div className="settings-actions">
                <button className="small-button" disabled={busy !== null} onClick={fetchModels} type="button">
                  <ListRestart size={14} />
                  获取模型
                </button>
                <button className="primary-button" disabled={busy !== null || !form.model.trim()} onClick={runSmoke} type="button">
                  <TestTube2 size={15} />
                  测试模型
                </button>
              </div>

              <label className="model-select">
                <div className="model-picker-search">
                  <Search size={14} />
                  <input
                    aria-label="Search available models"
                    disabled={!availableModels.length}
                    onChange={(event) => setModelQuery(event.target.value)}
                    placeholder="Search model ids"
                    type="search"
                    value={modelQuery}
                  />
                </div>
                <span>可用模型</span>
                <select
                  disabled={!availableModels.length}
                  value={form.model}
                  onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
                >
                  {!filteredModels.length ? <option value={form.model}>{availableModels.length ? "No matching models" : form.model || "暂无模型列表"}</option> : null}
                  {filteredModels.map((item) => {
                    const id = modelId(item);
                    return <option key={id} value={id}>{id}</option>;
                  })}
                </select>
              </label>

              <label className="wide-field">
                <span>测试提示词</span>
                <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={3} />
              </label>

              <div className="mini-list">
                <article>
                  <strong>{smoke?.success ? "测试通过" : smoke ? userMessage(smoke.error_code || "AI_SMOKE_FAILED") : "等待测试"}</strong>
                  <span>{smoke?.response_preview || userMessage(smoke?.error) || "保存配置后执行一次最小请求，验证密钥、Base URL、模型名和网络连通性。"}</span>
                  <StatusBadge status={smoke?.success ? "passed" : smoke ? "failed" : "not_loaded"} />
                </article>
                {models?.unsupported ? (
                  <article>
                    <strong>列表降级</strong>
                    <span>{userMessage(models.warning || models.error) || "提供方未返回标准模型列表，已展示当前配置模型。"}</span>
                    <StatusBadge status="partial" />
                  </article>
                ) : null}
              </div>
            </article>
          </section>

          <section className="capability-grid two">
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>提供方池</span>
                  <h3>已配置提供方</h3>
                </div>
                <StatusBadge status={providerStatus.status as string || "not_loaded"} />
              </div>
              <div className="mini-list">
                {providers.map((provider) => (
                  <article key={String(provider.name)}>
                    <strong>{String(provider.name)}</strong>
                    <span>{String(provider.type || provider.model || "provider")}</span>
                    <StatusBadge status={String(provider.status || "not_loaded")} label={provider.configured ? "已配置" : String(provider.status || "缺失")} />
                  </article>
                ))}
                {!providers.length && <p className="muted">尚未加载提供方池条目。</p>}
              </div>
            </article>
            <article className="capability-section">
              <div className="section-header">
                <div>
                  <span>模型列表</span>
                  <h3>提供方响应</h3>
                </div>
                <StatusBadge status={models ? "ready" : "not_loaded"} label={availableModels.length ? `${availableModels.length} 个模型` : undefined} />
              </div>
              <div className="mini-list model-list-preview">
                {filteredModels.slice(0, 8).map((item) => {
                  const id = modelId(item);
                  return (
                    <article key={id}>
                      <strong>{id}</strong>
                      <span>{firstString(item.owned_by) || firstString(item.display_name) || firstString(item.object) || "model"}</span>
                      <StatusBadge status={item.fallback ? "partial" : "ready"} label={item.fallback ? "当前配置" : "可选"} />
                    </article>
                  );
                })}
                {!availableModels.length && <p className="muted">点击“获取模型”后，标准兼容提供方会返回可选模型；不支持列表的提供方会显示当前配置模型。</p>}
                {availableModels.length > 0 && !filteredModels.length ? <p className="muted">No models match the current search.</p> : null}
              </div>
            </article>
          </section>

          <details className="raw-details">
            <summary>原始模型配置</summary>
            <JsonPanel value={{ config, settings, models, smoke }} />
          </details>
        </div>
      </div>
    </section>
  );
}
