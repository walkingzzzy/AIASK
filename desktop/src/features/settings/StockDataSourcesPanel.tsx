import { CheckCircle2, Database, ExternalLink, Globe2, KeyRound, PlugZap, RefreshCw, Save, TestTube2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact, statusLabel } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { StockDataSourceConfig, StockDataSourcePreset, StockDataSourceTestResult, StockDataSourcesStatus } from "../../types";

type StockSourceForm = {
  id: string;
  provider: string;
  name: string;
  enabled: boolean;
  priority: string;
  base_url: string;
  host: string;
  port: string;
  api_key: string;
  username: string;
  password: string;
  client_path: string;
  account_id: string;
  session_id: string;
  symbol: string;
  interval: string;
  dataset: string;
  timeout_seconds: string;
  rate_limit_per_minute: string;
  markets: string;
  notes: string;
  search_depth: string;
};

const SEARCH_PROVIDERS = new Set(["duckduckgo", "tavily", "brave_search", "serpapi", "exa"]);
const SECRET_REQUIRED_FIELDS = new Set(["api_key", "token", "password", "secret", "subscription_token"]);

function emptyForm(preset?: StockDataSourcePreset): StockSourceForm {
  return {
    id: "",
    provider: preset?.provider || "akshare",
    name: preset?.label || "",
    enabled: true,
    priority: "100",
    base_url: preset?.default_base_url || "",
    host: preset?.default_host || "",
    port: preset?.default_port ? String(preset.default_port) : "",
    api_key: "",
    username: "",
    password: "",
    client_path: "",
    account_id: "",
    session_id: "",
    symbol: "",
    interval: "",
    dataset: "",
    timeout_seconds: "8",
    rate_limit_per_minute: "",
    markets: preset?.markets?.join(", ") || "",
    notes: preset?.note || "",
    search_depth: preset?.provider === "tavily" ? "advanced" : "basic"
  };
}

function formFromSource(source: StockDataSourceConfig, preset?: StockDataSourcePreset): StockSourceForm {
  return {
    ...emptyForm(preset),
    id: source.id || "",
    provider: source.provider || preset?.provider || "akshare",
    name: source.name || source.label || preset?.label || "",
    enabled: source.enabled !== false,
    priority: source.priority === undefined || source.priority === null ? "100" : String(source.priority),
    base_url: String(source.base_url || preset?.default_base_url || ""),
    host: String(source.host || preset?.default_host || ""),
    port: source.port === undefined || source.port === null ? (preset?.default_port ? String(preset.default_port) : "") : String(source.port),
    api_key: "",
    username: source.username || "",
    password: "",
    client_path: String(source.client_path || ""),
    account_id: String(source.account_id || ""),
    session_id: String(source.session_id || ""),
    symbol: String(source.symbol || ""),
    interval: String(source.interval || ""),
    dataset: String(source.dataset || ""),
    timeout_seconds: source.timeout_seconds === undefined || source.timeout_seconds === null ? "8" : String(source.timeout_seconds),
    rate_limit_per_minute: source.rate_limit_per_minute === undefined || source.rate_limit_per_minute === null ? "" : String(source.rate_limit_per_minute),
    markets: Array.isArray(source.markets) ? source.markets.join(", ") : preset?.markets?.join(", ") || "",
    notes: String(source.notes || preset?.note || ""),
    search_depth: String(source.search_depth || "basic")
  };
}

function optionalNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function numberOrDefault(value: string, fallback: number): number {
  const parsed = optionalNumber(value);
  return parsed === null ? fallback : parsed;
}

function sourcePayload(form: StockSourceForm): StockDataSourceConfig {
  const port = optionalNumber(form.port);
  const timeoutSeconds = optionalNumber(form.timeout_seconds);
  const rateLimitPerMinute = optionalNumber(form.rate_limit_per_minute);
  const payload: StockDataSourceConfig = {
    provider: form.provider,
    name: form.name.trim(),
    enabled: form.enabled,
    priority: numberOrDefault(form.priority, 100),
    base_url: form.base_url.trim() || null,
    host: form.host.trim() || null,
    port,
    username: form.username.trim(),
    client_path: form.client_path.trim() || null,
    account_id: form.account_id.trim() || null,
    session_id: form.session_id.trim() || null,
    symbol: form.symbol.trim() || null,
    interval: form.interval.trim() || null,
    dataset: form.dataset.trim() || null,
    timeout_seconds: timeoutSeconds,
    rate_limit_per_minute: rateLimitPerMinute,
    markets: form.markets.split(",").map((item) => item.trim()).filter(Boolean),
    notes: form.notes.trim() || null
  };
  if (form.id.trim()) payload.id = form.id.trim();
  if (form.api_key.trim()) payload.api_key = form.api_key.trim();
  if (form.password.trim()) payload.password = form.password.trim();
  if (form.search_depth.trim()) payload.search_depth = form.search_depth.trim();
  return payload;
}

function comparablePayload(form: StockSourceForm): Record<string, unknown> {
  const payload = { ...sourcePayload(form) };
  delete payload.api_key;
  delete payload.password;
  return payload;
}

function payloadChanged(form: StockSourceForm, source?: StockDataSourceConfig, preset?: StockDataSourcePreset): boolean {
  if (!source) return false;
  return JSON.stringify(comparablePayload(form)) !== JSON.stringify(comparablePayload(formFromSource(source, preset)));
}

function connectionTestPayload(
  form: StockSourceForm,
  options: {
    changed: boolean;
    hasInlineSecret: boolean;
    mode?: "connectivity" | "sample";
  }
): Record<string, unknown> {
  const id = form.id.trim();
  const provider = form.provider.trim();
  const shouldSendSource = !id || options.changed || options.hasInlineSecret;
  const payload: Record<string, unknown> = {
    mode: options.mode || "connectivity",
    provider
  };
  if (id) payload.id = id;
  if (shouldSendSource) payload.source = sourcePayload(form);
  return payload;
}

function presetSummary(preset?: StockDataSourcePreset): string {
  if (!preset) return "选择一个数据源预设后，系统会自动填入默认地址和必填项提示。";
  const required = preset.required_fields?.length ? `必填：${preset.required_fields.join(", ")}` : "无必填密钥";
  return `${preset.markets.join(" / ")} | ${preset.categories.join(" / ")} | ${required}`;
}

function isSearchPreset(preset?: StockDataSourcePreset | StockDataSourceConfig): boolean {
  if (!preset) return false;
  const categories = Array.isArray(preset.categories) ? preset.categories.map(String) : [];
  return categories.includes("web_search") || SEARCH_PROVIDERS.has(String(preset.provider || ""));
}

function requiresSecret(preset?: StockDataSourcePreset): boolean {
  return Boolean(preset?.required_fields?.some((field) => SECRET_REQUIRED_FIELDS.has(String(field))));
}

function secretStatusLabel({
  form,
  preset,
  selectedSource
}: {
  form: StockSourceForm;
  preset?: StockDataSourcePreset;
  selectedSource?: StockDataSourceConfig;
}): string {
  const typedSecret = Boolean(form.api_key.trim() || form.password.trim());
  const storedSecret = Boolean(selectedSource?.api_key_configured);
  if (typedSecret) return "本次将写入新密钥";
  if (storedSecret) return "已配置，已脱敏";
  if (requiresSecret(preset)) return "待填写密钥";
  return "无需密钥";
}

function sourceSecretLabel(source: StockDataSourceConfig, preset?: StockDataSourcePreset): string {
  if (source.api_key_configured) return "密钥已配置";
  if (requiresSecret(preset)) return "缺少密钥";
  return "无需密钥";
}

function sourceKindLabel(source?: StockDataSourceConfig | StockDataSourcePreset): string {
  return isSearchPreset(source) ? "联网搜索" : "行情/数据";
}

function statusMessage(message: string): string {
  if (message.startsWith("AIASK_")) return message;
  if (message === "NOT_LOADED") return "not_loaded";
  if (message.includes("FAILED")) return "failed";
  return "ready";
}

function messageLabel(message: string): string {
  const normalized = message.toLowerCase();
  if (normalized.includes("permissiondenied") || normalized.includes("blocked")) {
    return "请求被服务商或网络策略拦截";
  }
  return statusLabel(message);
}

export function StockDataSourcesPanel({
  endpoint,
  apiToken,
  controlToken
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [status, setStatus] = useState<StockDataSourcesStatus | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [form, setForm] = useState<StockSourceForm>(() => emptyForm());
  const [query, setQuery] = useState("AIASK deep search data source");
  const [testResult, setTestResult] = useState<(StockDataSourceTestResult & Record<string, unknown>) | Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState<"refresh" | "save" | "test" | "search" | null>(null);

  const presets = status?.presets || [];
  const sources = status?.sources || [];
  const activePreset = presets.find((item) => item.provider === form.provider);
  const selectedSource = sources.find((item) => item.id === selectedId);
  const canSave = Boolean(controlToken.trim()) && Boolean(form.provider.trim()) && Boolean(form.name.trim());
  const formComplete = Boolean(form.provider.trim()) && Boolean(form.name.trim());
  const secretLabel = secretStatusLabel({ form, preset: activePreset, selectedSource });
  const searchSourceActive = isSearchPreset(activePreset) || SEARCH_PROVIDERS.has(form.provider);
  const canSearch = searchSourceActive && Boolean(query.trim()) && (Boolean(form.id.trim()) || form.provider === "duckduckgo");
  const resultRecord = (testResult || {}) as Record<string, unknown>;
  const hasInlineSecret = Boolean(form.api_key.trim() || form.password.trim());
  const draftChanged = payloadChanged(form, selectedSource, activePreset);
  const formStatus = controlToken.trim() ? (formComplete ? "ready" : "partial") : "gated";
  const formStatusLabel = controlToken.trim() ? (formComplete ? draftChanged ? "未保存变更" : "可保存" : "待填写") : (selectedId ? "已配置，只读查看" : "需要控制令牌");

  async function refresh(preferredSourceId?: string, successMessage = "STOCK_DATA_SOURCES_LOADED") {
    setBusy("refresh");
    try {
      const payload = await api.stockDataSources();
      setStatus(payload);
      const nextSource = payload.sources.find((item) => item.id === (preferredSourceId || selectedId)) || payload.sources[0];
      const nextPreset = payload.presets.find((item) => item.provider === (nextSource?.provider || form.provider)) || payload.presets.find(isSearchPreset) || payload.presets[0];
      if (nextSource) {
        setSelectedId(nextSource.id || "");
        setForm(formFromSource(nextSource, nextPreset));
      } else if (!form.provider || form.provider === "akshare") {
        setForm(emptyForm(nextPreset));
      }
      setMessage(successMessage);
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    setBusy("save");
    try {
      const saved = await api.stockDataSourceSave(sourcePayload(form));
      setSelectedId(saved.source.id || "");
      setForm((current) => ({ ...current, id: saved.source.id || current.id, api_key: "", password: "" }));
      setTestResult(null);
      await refresh(saved.source.id, "STOCK_DATA_SOURCE_SAVED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(null);
    }
  }

  async function testConnection() {
    setBusy("test");
    try {
      const result = await api.stockDataSourceTest(connectionTestPayload(form, { changed: draftChanged, hasInlineSecret }));
      setTestResult(result);
      setMessage(result.success ? "STOCK_DATA_SOURCE_TEST_PASSED" : result.error_code || result.error || "STOCK_DATA_SOURCE_TEST_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(null);
    }
  }

  async function callSearch() {
    setBusy("search");
    try {
      const result = await api.readOnlyTool<Record<string, unknown>>("agent_web_search", {
        query,
        limit: 5,
        provider: form.provider,
        source_id: form.id || undefined,
        search_depth: form.search_depth
      });
      const data = result.data || {};
      const results = Array.isArray((data as Record<string, unknown>).results) ? ((data as Record<string, unknown>).results as unknown[]) : [];
      setTestResult({
        object: "aiask.web_search_test",
        provider: String((data as Record<string, unknown>).provider || form.provider),
        status: result.success ? "ready" : "failed",
        success: result.success,
        sample_count: results.length,
        query,
        results,
        error: result.error,
        secrets_redacted: true
      });
      setMessage(result.success ? "WEB_SEARCH_PASSED" : "WEB_SEARCH_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(null);
    }
  }

  function choosePreset(provider: string) {
    const preset = presets.find((item) => item.provider === provider);
    setSelectedId("");
    setTestResult(null);
    setForm(emptyForm(preset));
  }

  function chooseSource(sourceId: string) {
    const source = sources.find((item) => item.id === sourceId);
    const preset = presets.find((item) => item.provider === source?.provider);
    setSelectedId(sourceId);
    if (source) setForm(formFromSource(source, preset));
    setTestResult(null);
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  return (
    <div className="capability-stack stock-data-sources-panel data-sources-workspace">
      <div className="capability-banner">
        <div>
          <Database size={20} />
          <span>数据源</span>
          <h2>数据源配置、调用与测试</h2>
          <p>选择联网搜索或股票行情预设，填写 URL、Key、主机等参数后保存；密钥只写入 Agent，不会在页面回显。保存后可直接连通测试，联网搜索源还可以调用 agent_web_search 验证。</p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={statusMessage(message)} label={messageLabel(message)} technicalLabel={message} />
          <button className="small-button" disabled={busy !== null} onClick={() => refresh()} type="button">
            <RefreshCw size={14} className={busy === "refresh" ? "spin" : ""} />
            刷新
          </button>
        </div>
      </div>

      {!controlToken.trim() ? <div className="notice warn">保存和测试数据源需要控制令牌；请先在“令牌与权限”中填写。</div> : null}

      <section className="diagnostics-summary wide">
        <div className="metric-card ok">
          <span>可选预设</span>
          <strong>{presets.length}</strong>
        </div>
        <div className="metric-card ok">
          <span>已配置</span>
          <strong>{status?.configured_count ?? 0}</strong>
        </div>
        <div className="metric-card ok">
          <span>可用</span>
          <strong>{status?.ready_count ?? 0}</strong>
        </div>
        <div className="metric-card neutral">
          <span>密钥状态</span>
          <strong>{secretLabel}</strong>
        </div>
        <div className="metric-card neutral">
          <span>当前类别</span>
          <strong>{searchSourceActive ? "联网搜索" : "股票行情"}</strong>
        </div>
      </section>

      <section className="capability-grid two">
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>预设</span>
              <h3>选择数据源类型</h3>
            </div>
            <StatusBadge status={activePreset ? "ready" : "not_loaded"} />
          </div>
          <div className="preset-grid stock-source-presets">
            {presets.map((preset) => (
              <button
                className={`preset-tile ${form.provider === preset.provider && !selectedId ? "active" : ""}`}
                key={preset.provider}
                onClick={() => choosePreset(preset.provider)}
                type="button"
              >
                <span>{preset.label}</span>
                <small>{preset.auth_type} | {preset.markets.join(" / ")}</small>
                {form.provider === preset.provider && !selectedId ? <CheckCircle2 size={15} /> : <PlugZap size={15} />}
              </button>
            ))}
          </div>
          <div className="notice info compact">{presetSummary(activePreset)}</div>
          <div className="notice compact">
            联网搜索源用于深度搜索、资料收集和研究问答；股票行情源用于量化研究、数据同步和行情验证。没有搜索 API Key 时可先用 DuckDuckGo fallback。
          </div>
          {activePreset?.documentation_url ? (
            <a className="small-button link-button stock-doc-link" href={activePreset.documentation_url} rel="noreferrer" target="_blank">
              <ExternalLink size={14} />
              打开官方文档
            </a>
          ) : null}
        </article>

        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>{sources.length} 个条目</span>
              <h3>已有数据源</h3>
            </div>
            <StatusBadge status={sources.length ? "ready" : "not_loaded"} />
          </div>
          <div className="mini-list">
            {sources.map((source) => (
              <button className={selectedId === source.id ? "active" : ""} key={source.id || source.provider} onClick={() => chooseSource(source.id || "")} type="button">
                <strong>{source.name || source.label || source.provider}</strong>
                <span>{source.provider} | {sourceKindLabel(source)} | {source.enabled === false ? "已停用" : source.configured ? "已配置" : "未配置"}</span>
                <StatusBadge status={source.status || "not_loaded"} label={sourceSecretLabel(source, presets.find((item) => item.provider === source.provider))} />
              </button>
            ))}
            {!sources.length ? <p className="muted">还没有保存的数据源。请选择左侧预设后填写表单。</p> : null}
          </div>
        </article>
      </section>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>{selectedId ? "编辑已有数据源" : "新增数据源"}</span>
            <h3>连接信息</h3>
          </div>
          <StatusBadge status={formStatus} label={formStatusLabel} />
        </div>
        <div className="notice info compact stock-secret-state">
          <KeyRound size={14} />
          <span>{secretLabel}；保存和测试结果只展示脱敏状态，原始密钥不会在前端回显。</span>
        </div>

        <div className="settings-form-grid stock-source-form">
          <label>
            <span>数据源类型</span>
            <select value={form.provider} onChange={(event) => choosePreset(event.target.value)}>
              {presets.map((preset) => <option key={preset.provider} value={preset.provider}>{preset.label}</option>)}
              {!presets.length ? <option value={form.provider}>{form.provider}</option> : null}
            </select>
          </label>
          <label>
            <span>显示名称</span>
            <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="例如：Tushare 主账号" />
          </label>
          <label>
            <span>优先级</span>
            <input inputMode="numeric" value={form.priority} onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value }))} />
          </label>
          <label>
            <span>超时秒数</span>
            <input inputMode="numeric" value={form.timeout_seconds} onChange={(event) => setForm((current) => ({ ...current, timeout_seconds: event.target.value }))} />
          </label>
          <label className="wide-field">
            <span>Base URL</span>
            <input value={form.base_url} onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))} placeholder={activePreset?.default_base_url || "可留空使用默认地址"} />
          </label>
          <label>
            <span>主机</span>
            <input value={form.host} onChange={(event) => setForm((current) => ({ ...current, host: event.target.value }))} placeholder={activePreset?.default_host || "例如 119.147.212.81"} />
          </label>
          <label>
            <span>端口</span>
            <input inputMode="numeric" value={form.port} onChange={(event) => setForm((current) => ({ ...current, port: event.target.value }))} placeholder={activePreset?.default_port ? String(activePreset.default_port) : ""} />
          </label>
          <label className="wide-field">
            <span>API Key / Token</span>
            <input
              autoComplete="off"
              type="password"
              value={form.api_key}
              onChange={(event) => setForm((current) => ({ ...current, api_key: event.target.value }))}
              placeholder={selectedSource?.api_key_configured ? "已配置，留空则沿用现有密钥" : "粘贴数据服务的 API Key 或 Token"}
            />
          </label>
          <label>
            <span>用户名</span>
            <input value={form.username} onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} />
          </label>
          <label>
            <span>密码</span>
            <input autoComplete="off" type="password" value={form.password} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} placeholder={selectedSource?.api_key_configured ? "已配置，留空则沿用" : ""} />
          </label>
          <label className="wide-field">
            <span>本地客户端路径</span>
            <input value={form.client_path} onChange={(event) => setForm((current) => ({ ...current, client_path: event.target.value }))} placeholder="QMT / XtQuant 本地客户端路径，可留空" />
          </label>
          <label>
            <span>账号 ID</span>
            <input value={form.account_id} onChange={(event) => setForm((current) => ({ ...current, account_id: event.target.value }))} />
          </label>
          <label>
            <span>会话 ID</span>
            <input value={form.session_id} onChange={(event) => setForm((current) => ({ ...current, session_id: event.target.value }))} />
          </label>
          <label>
            <span>测试代码</span>
            <input value={form.symbol} onChange={(event) => setForm((current) => ({ ...current, symbol: event.target.value }))} placeholder="AAPL / IBM / 600519" />
          </label>
          <label>
            <span>周期</span>
            <input value={form.interval} onChange={(event) => setForm((current) => ({ ...current, interval: event.target.value }))} placeholder="1day / daily" />
          </label>
          <label>
            <span>数据集</span>
            <input value={form.dataset} onChange={(event) => setForm((current) => ({ ...current, dataset: event.target.value }))} />
          </label>
          <label>
            <span>每分钟限流</span>
            <input inputMode="numeric" value={form.rate_limit_per_minute} onChange={(event) => setForm((current) => ({ ...current, rate_limit_per_minute: event.target.value }))} />
          </label>
          {searchSourceActive ? (
            <>
              <label>
                <span>搜索深度</span>
                <select value={form.search_depth} onChange={(event) => setForm((current) => ({ ...current, search_depth: event.target.value }))}>
                  <option value="basic">basic</option>
                  <option value="advanced">advanced</option>
                </select>
              </label>
              <label>
                <span>测试查询</span>
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入要搜索的问题或关键词" />
              </label>
            </>
          ) : null}
          <label className="wide-field">
            <span>覆盖市场</span>
            <input value={form.markets} onChange={(event) => setForm((current) => ({ ...current, markets: event.target.value }))} placeholder="CN, US, Global" />
          </label>
          <label className="wide-field">
            <span>备注</span>
            <textarea value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} rows={3} />
          </label>
          <label className="inline-check wide-field">
            <input checked={form.enabled} onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))} type="checkbox" />
            <span>启用这个数据源</span>
          </label>
        </div>

        <div className="settings-actions">
          <button className="primary-button" disabled={!canSave || busy !== null} onClick={save} type="button">
            <Save size={15} />
            保存数据源
          </button>
          <button className="small-button" disabled={!controlToken.trim() || busy !== null || !form.provider.trim()} onClick={testConnection} type="button">
            <TestTube2 size={14} />
            测试连接
          </button>
          {searchSourceActive ? (
            <button className="small-button" disabled={busy !== null || !canSearch} onClick={callSearch} type="button">
              <Globe2 size={14} />
              调用搜索
            </button>
          ) : null}
        </div>
      </section>

      <section className="capability-section">
        <div className="section-header">
          <h3>最近测试结果</h3>
          <StatusBadge
            status={resultRecord.success === true ? "passed" : testResult ? "failed" : "not_loaded"}
            label={resultRecord.status ? statusLabel(String(resultRecord.status)) : "未测试"}
            technicalLabel={resultRecord.status ? String(resultRecord.status) : undefined}
          />
        </div>
        <div className="settings-static-grid">
          <span>提供方</span>
          <strong>{String(resultRecord.provider || form.provider || "-")}</strong>
          <span>状态</span>
          <strong>{resultRecord.status ? statusLabel(String(resultRecord.status)) : "-"}</strong>
          <span>延迟</span>
          <strong>{resultRecord.latency_ms === undefined ? "-" : `${String(resultRecord.latency_ms)} ms`}</strong>
          <span>样本数</span>
          <strong>{compact(resultRecord.sample_count ?? "-")}</strong>
          <span>密钥</span>
          <strong>{resultRecord.secrets_redacted === true ? "已脱敏" : secretLabel}</strong>
          <span>错误</span>
          <strong>{messageLabel(String(resultRecord.error || resultRecord.error_code || "-"))}</strong>
        </div>
      </section>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>如何调用</span>
            <h3>当前配置调用示例</h3>
          </div>
          <StatusBadge status="read_only" />
        </div>
        <JsonPanel
          value={
            searchSourceActive
              ? {
                  route: "/v1/tools/agent_web_search",
                  body: {
                    query,
                    limit: 5,
                    provider: form.provider,
                    source_id: form.id || undefined,
                    search_depth: form.search_depth
                  }
                }
              : {
                  route: "/v1/desktop/stock-data-sources/test",
                  body: connectionTestPayload(form, { changed: draftChanged, hasInlineSecret, mode: "sample" })
                }
          }
        />
      </section>

      <details className="raw-details">
        <summary>原始数据源状态</summary>
        <JsonPanel value={{ status, testResult }} />
      </details>
    </div>
  );
}
