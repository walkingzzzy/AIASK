import { Activity, Database, Factory, Filter, Layers3, ServerCog, ShieldCheck, UserRound, Wrench } from "lucide-react";
import { useMemo, useState } from "react";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import type {
  CapabilityMatrixItem,
  CapabilityWorkbenchPayload,
  DesktopDataStatus,
  DesktopSettingsStatus,
  FactorFactoryStatus,
  HealthDetailed,
  ToolCatalogItem
} from "../../types";
import { collectCapabilityRows, itemLabel } from "./capabilityUtils";

interface CoverageRow {
  id: string;
  domain: string;
  capability: string;
  backend: string;
  desktopApi: string;
  frontend: string;
  testPath: string;
  status: string;
  notes?: string;
  source?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function sideEffectLabel(tool: ToolCatalogItem): string {
  const sideEffect = tool.side_effect;
  if (typeof sideEffect === "string") return sideEffect || "unknown";
  if (isRecord(sideEffect) && typeof sideEffect.level === "string") return sideEffect.level || "unknown";
  return "unknown";
}

function rowStatus(value: unknown, fallback = "not_loaded"): string {
  if (!value) return fallback;
  if (typeof value === "string") return value;
  if (!isRecord(value)) return fallback;
  if (value.success === true) return "implemented";
  if (value.success === false) return value.error_code ? "unconfigured" : "failed";
  if (typeof value.status === "string") return value.status;
  return fallback;
}

function normalizeStatus(status: string): string {
  const value = status.toLowerCase();
  if (["ready", "implemented", "passed", "success", "live_backend"].includes(value)) return "implemented";
  if (["partial", "live_unverified", "skipped_missing_credentials", "unconfigured", "gated"].includes(value)) return value;
  if (["failed", "missing", "blocked", "error"].includes(value)) return "failed";
  return value || "not_loaded";
}

function rowFromTool(tool: ToolCatalogItem): CoverageRow {
  const sideEffect = sideEffectLabel(tool);
  const readOnly = sideEffect === "read_only";
  return {
    id: `tool:${tool.name}`,
    domain: tool.category || tool.capability || "agent_tool",
    capability: tool.name,
    backend: "Agent tool registry",
    desktopApi: readOnly ? `/v1/tools/${tool.name}` : "控制令牌 / 意图门控",
    frontend: readOnly ? "工具页安全探测" : "工具页受控操作记录",
    testPath: readOnly ? "在工具页点击“填充示例”或“运行安全探测”。" : "验证禁用/受控状态；仅从已审批面板创建意图。",
    status: normalizeStatus(tool.status || (readOnly ? "implemented" : "gated")),
    notes: tool.description,
    source: tool
  };
}

function rowFromHermes(item: CapabilityMatrixItem, index: number): CoverageRow {
  const tools = Array.isArray(item.aiask_tools) ? item.aiask_tools.join(", ") : compact(item.aiask_tools);
  return {
    id: `hermes:${itemLabel(item)}:${index}`,
    domain: `Hermes / ${item.area || "parity"}`,
    capability: itemLabel(item),
    backend: String(item.code_status || item.live_status || item.status || "mapped"),
    desktopApi: tools || "/v1/hermes/status",
    frontend: "能力中心 / Hermes 与覆盖矩阵",
    testPath: "筛选 Hermes 行，验证已映射的 AIASK 工具或凭证缺口。",
    status: normalizeStatus(String(item.status || item.live_status || item.code_status || "live_unverified")),
    notes: String(item.description || item.error || item.required_env || ""),
    source: item
  };
}

function appendIf(rows: CoverageRow[], row: CoverageRow | null | undefined) {
  if (row) rows.push(row);
}

export function buildCoverageRows({
  capabilities,
  data,
  factor,
  health,
  jobs = [],
  settings,
  tools = []
}: {
  capabilities?: CapabilityWorkbenchPayload | null;
  data?: DesktopDataStatus | null;
  factor?: FactorFactoryStatus | null;
  health?: HealthDetailed | null;
  jobs?: Array<Record<string, unknown>>;
  settings?: DesktopSettingsStatus | null;
  tools?: ToolCatalogItem[];
}): CoverageRow[] {
  const rows: CoverageRow[] = [];
  rows.push(...tools.map(rowFromTool));
  rows.push(...collectCapabilityRows(capabilities || null).map(rowFromHermes));

  appendIf(rows, {
    id: "runtime:agent",
    domain: "Agent 运行时",
    capability: "health, tool registry, response runtime",
    backend: health?.service || "AIASK Agent",
    desktopApi: "/health/detailed, /v1/tools, /v1/responses",
    frontend: "总览、智能体、工作台、工具",
    testPath: "点击同步/刷新，运行安全提示词，检查时间线和运行事件。",
    status: normalizeStatus(health?.status || "not_loaded"),
    notes: `${health?.tools?.count ?? 0} tools / ${health?.tools?.toolset || "unknown"}`
  });

  const llm = settings?.llm.ai_status;
  appendIf(rows, {
    id: "runtime:llm",
    domain: "模型",
    capability: "LLM provider, model, root project API env",
    backend: llm?.configured ? "configured" : "missing/mock",
    desktopApi: "/v1/desktop/settings/status, /v1/ai/status, /v1/ai/models",
    frontend: "模型、设置、能力中心 / AI 测试",
    testPath: "刷新模型并运行 AI 冒烟测试；确认密钥被脱敏。",
    status: normalizeStatus(llm?.configured ? "implemented" : "unconfigured"),
    notes: `${llm?.provider || "-"} / ${llm?.model || "-"}`
  });

  appendIf(rows, {
    id: "data:sync",
    domain: "数据与同步",
    capability: "SQLite/AKShare 新鲜度、质量门控、同步计划意图",
    backend: data?.database?.writable === false ? "database blocked" : data?.status || "not_loaded",
    desktopApi: "/v1/desktop/data/status, /v1/desktop/data/sync-plan, /intents",
    frontend: "数据与同步",
    testPath: "刷新数据、生成计划，并且只在有控制令牌时创建审批意图。",
    status: normalizeStatus(data?.status || "not_loaded"),
    notes: `${data?.codes?.length || 0} 个代码 / 缺失 ${data?.missing_count ?? "-"} / 过期 ${data?.stale_count ?? "-"}`
  });

  const mcp = capabilities?.mcp;
  appendIf(rows, {
    id: "mcp:service",
    domain: "MCP",
    capability: "已注册服务、工具、资源、提示词与 OAuth",
    backend: mcp?.gated ? "control gated" : mcp?.discovery_status || "not_loaded",
    desktopApi: "/v1/mcp/* via Agent",
    frontend: "MCP、能力中心 / MCP",
    testPath: "在 mock/控制模式下发现服务、读取安全资源、获取提示词、启动 OAuth。",
    status: normalizeStatus(mcp?.gated ? "gated" : mcp?.discovery_status || "not_loaded"),
    notes: `${mcp?.tools?.length || 0} 个工具 / ${mcp?.resources?.length || 0} 个资源 / ${mcp?.prompts?.length || 0} 个提示词`
  });
  (mcp?.tools || []).forEach((tool, index) => {
    rows.push({
      id: `mcp-tool:${tool.server || "server"}:${tool.wrapped_name || tool.name}:${index}`,
      domain: `MCP / ${tool.domain || tool.server || "server"}`,
      capability: tool.wrapped_name || tool.name,
      backend: tool.configured === false ? "unconfigured" : "discovered",
      desktopApi: "/v1/mcp/tools, /v1/tools/agent_mcp_*",
      frontend: "MCP 动态工具、工具页安全探测",
      testPath: "检查工具契约；仅运行只读包装的 MCP 工具。",
      status: normalizeStatus(tool.configured === false ? "unconfigured" : "implemented"),
      notes: tool.description || tool.name,
      source: tool
    });
  });

  const strategy = capabilities?.strategy_factory;
  appendIf(rows, {
    id: "factory:strategy",
    domain: "策略工厂",
    capability: "调度器状态、最近运行、评审快照、运行意图",
    backend: rowStatus(strategy?.status),
    desktopApi: "agent_factory_status, agent_factory_runs, /intents",
    frontend: "策略工厂、能力中心 / 策略工厂",
    testPath: "刷新状态并创建运行意图；只通过审批检查器确认。",
    status: normalizeStatus(rowStatus(strategy?.status)),
    source: strategy
  });

  appendIf(rows, {
    id: "factory:factor",
    domain: "因子挖掘工厂",
    capability: "活跃池、引擎健康、运行和维护意图",
    backend: factor?.configured === false ? "unconfigured" : factor?.status || "not_loaded",
    desktopApi: "/v1/desktop/factor-factory/status, /intents",
    frontend: "因子工厂",
    testPath: "在 mock/控制模式下刷新状态、创建运行意图与维护意图。",
    status: normalizeStatus(factor?.status || "not_loaded"),
    notes: `${factor?.active_factors?.length || 0} active factors`,
    source: factor
  });

  appendIf(rows, {
    id: "factory:incubation",
    domain: "孵化工厂",
    capability: "运行器状态、生命周期事件、命中率看板、运行/试运行/维护意图",
    backend: rowStatus(strategy?.review_snapshot),
    desktopApi: "agent_incubation_factory_status, agent_strategy_domain_events, /intents",
    frontend: "孵化工厂",
    testPath: "在 mock/控制模式下刷新生命周期看板，创建运行/试运行/维护意图。",
    status: normalizeStatus(rowStatus(strategy?.review_snapshot)),
    source: strategy?.review_snapshot
  });

  const profile = settings?.profile;
  appendIf(rows, {
    id: "user:local",
    domain: "本地用户",
    capability: "本地画像、user_id 作用域、会话、消息与记忆搜索",
    backend: profile?.status || "ready",
    desktopApi: "/v1/desktop/users/local-profile, /v1/hermes/sessions, /v1/search, agent_memory_search",
    frontend: "本地用户、设置、工作台",
    testPath: "保存本地画像、列出会话、加载消息、搜索用户数据和记忆。",
    status: normalizeStatus(profile?.status || "implemented"),
    notes: `${profile?.user_id || "local"} / ${profile?.profile_name || "本地操作者"}`
  });

  appendIf(rows, {
    id: "automation:jobs",
    domain: "自动化",
    capability: "任务列表、创建、更新、删除、运行与用户归属",
    backend: jobs.length ? "configured" : "empty",
    desktopApi: "/v1/jobs",
    frontend: "自动化",
    testPath: "创建、查看、暂停/恢复、运行并删除 mock 任务。",
    status: normalizeStatus(jobs.length ? "implemented" : "not_loaded"),
    notes: `${jobs.length} jobs`
  });

  const skills = capabilities?.skills?.skills || [];
  appendIf(rows, {
    id: "skills:native",
    domain: "技能",
    capability: "native skill list, install/update/delete, skill packs",
    backend: capabilities?.skills?.gated ? "control gated" : "loaded",
    desktopApi: "/v1/skills, agent_skill_*",
    frontend: "技能、能力中心 / 技能与插件",
    testPath: "验证受控状态；仅在 mock/控制模式下安装、更新、删除。",
    status: normalizeStatus(capabilities?.skills?.gated ? "gated" : "implemented"),
    notes: `${Array.isArray(skills) ? skills.length : 0} skills`
  });

  const pluginList = Array.isArray(capabilities?.plugins)
    ? capabilities?.plugins
    : isRecord(capabilities?.plugins) && Array.isArray(capabilities?.plugins.data)
      ? capabilities?.plugins.data
      : [];
  appendIf(rows, {
    id: "plugins:native",
    domain: "插件",
    capability: "native plugin registry, enable/disable, tool test",
    backend: isRecord(capabilities?.plugins) && capabilities?.plugins.gated ? "control gated" : "loaded",
    desktopApi: "/v1/plugins, agent_plugin_*",
    frontend: "能力中心 / 插件",
    testPath: "验证受控状态；仅在 mock/控制模式下切换与测试工具。",
    status: normalizeStatus(isRecord(capabilities?.plugins) && capabilities?.plugins.gated ? "gated" : "implemented"),
    notes: `${pluginList?.length || 0} plugins`
  });

  return rows;
}

export function CoverageMatrixPanel({
  capabilities,
  data,
  factor,
  health,
  jobs = [],
  settings,
  tools = []
}: {
  capabilities?: CapabilityWorkbenchPayload | null;
  data?: DesktopDataStatus | null;
  factor?: FactorFactoryStatus | null;
  health?: HealthDetailed | null;
  jobs?: Array<Record<string, unknown>>;
  settings?: DesktopSettingsStatus | null;
  tools?: ToolCatalogItem[];
}) {
  const [query, setQuery] = useState("");
  const [domain, setDomain] = useState("all");
  const [status, setStatus] = useState("all");
  const rows = useMemo(
    () => buildCoverageRows({ capabilities, data, factor, health, jobs, settings, tools }),
    [capabilities, data, factor, health, jobs, settings, tools]
  );
  const domains = useMemo(() => Array.from(new Set(rows.map((row) => row.domain))).sort(), [rows]);
  const statuses = useMemo(() => Array.from(new Set(rows.map((row) => row.status))).sort(), [rows]);
  const visible = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return rows.filter((row) => {
      const matchesQuery = !normalizedQuery || JSON.stringify(row).toLowerCase().includes(normalizedQuery);
      const matchesDomain = domain === "all" || row.domain === domain;
      const matchesStatus = status === "all" || row.status === status;
      return matchesQuery && matchesDomain && matchesStatus;
    });
  }, [domain, query, rows, status]);

  const counts = rows.reduce<Record<string, number>>((bucket, row) => {
    bucket[row.status] = (bucket[row.status] || 0) + 1;
    return bucket;
  }, {});
  const implemented = counts.implemented || counts.ready || 0;
  const gated = (counts.gated || 0) + (counts.unconfigured || 0);
  const failed = (counts.failed || 0) + (counts.missing || 0) + (counts.blocked || 0);

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>覆盖矩阵</span>
          <h2>项目真实能力覆盖</h2>
          <p>
            这张矩阵来自真实 Agent HTTP 接口、Hermes parity、MCP 发现、工厂、本地用户状态和 Desktop API 覆盖情况。
          </p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={failed ? "failed" : gated ? "partial" : "implemented"} label={`${rows.length} 项能力`} />
          <StatusBadge status={capabilities?.summary.source || "not_loaded"} label={capabilities?.summary.source || "未加载"} />
        </div>
      </div>

      <div className="diagnostics-summary wide">
        <MetricCard label="已实现" value={implemented} status="implemented" />
        <MetricCard label="受控/配置" value={gated} status={gated ? "partial" : "implemented"} />
        <MetricCard label="失败/缺失" value={failed} status={failed ? "failed" : "implemented"} />
        <MetricCard label="行数" value={rows.length} status={rows.length ? "ready" : "not_loaded"} />
      </div>

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>可追溯性</span>
            <h3>从来源到前端测试路径</h3>
          </div>
          <Filter size={18} />
        </div>
        <div className="coverage-filters">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索能力、API、前端、工具..." />
          <select value={domain} onChange={(event) => setDomain(event.target.value)}>
            <option value="all">全部领域</option>
            {domains.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">全部状态</option>
            {statuses.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <div className="coverage-table">
          <div className="coverage-row coverage-head">
            <span>能力</span>
            <span>后端</span>
            <span>Desktop API</span>
            <span>前端</span>
            <span>测试路径</span>
            <span>状态</span>
          </div>
          {visible.map((row) => (
            <details className="coverage-row coverage-item" key={row.id}>
              <summary>
                <strong>{row.capability}</strong>
                <span>{row.backend}</span>
                <span>{row.desktopApi}</span>
                <span>{row.frontend}</span>
                <span>{row.testPath}</span>
                <StatusBadge status={row.status} />
              </summary>
              <div className="coverage-detail">
                <div className="kv-grid">
                  <span>领域</span>
                  <strong>{row.domain}</strong>
                  <span>备注</span>
                  <strong>{row.notes || "-"}</strong>
                </div>
                <JsonPanel value={row.source || row} />
              </div>
            </details>
          ))}
          {!visible.length && <p className="muted table-empty">没有符合筛选条件的能力行。</p>}
        </div>
      </section>

      <section className="capability-grid three">
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>Finance Safe</span>
              <h3>Agent 与量化只读工具</h3>
            </div>
            <ShieldCheck size={18} />
          </div>
          <p className="muted">股票分析、数据闸门、因子验证、回测、风险、策略事件、记忆和会话搜索都通过安全探测验证。</p>
        </article>
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>Hermes Full</span>
              <h3>完整模式对齐</h3>
            </div>
            <Wrench size={18} />
          </div>
          <p className="muted">文件、终端、浏览器、网页、多模态、网关、学习、RL、技能、插件、MCP 和任务都保持控制令牌受控。</p>
        </article>
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>工厂</span>
              <h3>审批型操作</h3>
            </div>
            <Factory size={18} />
          </div>
          <p className="muted">策略、因子与孵化工厂提供状态读取路径，并为状态变更创建可追踪的持久意图。</p>
        </article>
      </section>

      <section className="capability-grid three">
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>数据平面</span>
              <h3>DB 与 MCP</h3>
            </div>
            <Database size={18} />
          </div>
          <p className="muted">SQLite/AKShare 就绪度、TDX/Tushare 源状态、动态 MCP 工具、资源、提示词与 OAuth 都通过 Agent HTTP 覆盖。</p>
        </article>
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>用户平面</span>
              <h3>画像与记忆</h3>
            </div>
            <UserRound size={18} />
          </div>
          <p className="muted">本地画像、user_id 传递、会话、消息、回复、任务和金融记忆搜索都可见且可测试。</p>
        </article>
        <article className="capability-section">
          <div className="section-header">
            <div>
              <span>扩展</span>
              <h3>技能与插件</h3>
            </div>
            <Layers3 size={18} />
          </div>
          <p className="muted">原生技能和插件管理保持显式、受控，并可在 mock 模式测试，不加载外部 dashboard JavaScript。</p>
        </article>
      </section>
    </div>
  );
}
