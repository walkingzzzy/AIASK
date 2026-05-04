export type ChatToolTraceItemKind = 'mcp' | 'local_context' | 'client_action' | 'compliance';
export type ChatToolTraceItemStatus = 'pending' | 'success' | 'error';
export type ChatToolTraceStatus = 'empty' | 'running' | 'completed' | 'partial_error';
export type ChatToolTraceEvidenceMode =
  | 'mcp_supported'
  | 'tool_supported'
  | 'page_context_supported'
  | 'advisory_only';

export type ChatToolTraceScopeDto = {
  mode?: string;
  pageKey?: string;
  objectType?: string;
  objectId?: string;
  stockCode?: string;
};

export type ChatToolTraceItemDto = {
  id: string;
  referenceLabel: string;
  kind: ChatToolTraceItemKind;
  toolName: string;
  status: ChatToolTraceItemStatus;
  startedAt: string;
  finishedAt?: string;
  durationMs?: number;
  inputSummary: string[];
  outputSummary: string[];
  errorMessage?: string;
  citedInAnswer?: boolean;
};

export type ChatToolTraceAnswerReferenceDto = {
  itemId: string;
  referenceLabel: string;
  toolName: string;
  evidenceSummary: string;
};

export type ChatToolTraceDto = {
  schemaVersion: 'tool_trace.v1';
  id: string;
  visibility: 'owner_only';
  generatedAt: string;
  status: ChatToolTraceStatus;
  scope: ChatToolTraceScopeDto;
  items: ChatToolTraceItemDto[];
  answerReferences: ChatToolTraceAnswerReferenceDto[];
  evidenceMode: ChatToolTraceEvidenceMode;
  advisoryOnly: boolean;
  advisoryReason?: string;
};

type CreateTraceInput = {
  mode?: string;
  pageKey?: string;
  objectType?: string;
  objectId?: string;
  stockCode?: string;
};

type AddTraceItemInput = {
  kind: ChatToolTraceItemKind;
  toolName: string;
  args: Record<string, unknown>;
  startedAt?: Date;
};

const INPUT_PRIORITY_KEYS = [
  'stock_code',
  'stock_codes',
  'code',
  'codes',
  'index_code',
  'strategy_id',
  'strategy_ids',
  'strategy',
  'account_id',
  'accountId',
  'portfolio_id',
  'portfolioId',
  'order_id',
  'orderId',
  'action',
  'tool_name',
  'query',
  'keyword',
  'period',
  'limit',
  'days',
  'start_date',
  'end_date',
  'initial_capital',
  'risk_aversion',
  'method',
  'underlying',
  'indicator',
];

const OMIT_INPUT_KEYS = new Set([
  'user_id',
  'actor_id',
  'actorId',
  'api_key',
  'apiKey',
  'authorization',
  'cookie',
  'password',
  'refresh_token',
  'access_token',
]);

const SENSITIVE_KEY_PATTERN = /(secret|token|password|cookie|authorization|api[_-]?key|credential)/i;
const MAX_SUMMARY_ITEMS = 8;
const MAX_TEXT_LENGTH = 180;

let traceCounter = 0;

function nowIso(date = new Date()) {
  return date.toISOString();
}

function nextTraceId() {
  traceCounter += 1;
  return `trace_${Date.now()}_${traceCounter}`;
}

function truncate(value: string, max = MAX_TEXT_LENGTH) {
  const compact = value.replace(/\s+/g, ' ').trim();
  return compact.length > max ? `${compact.slice(0, max - 1)}...` : compact;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function safeString(value: unknown): string {
  if (typeof value === 'string') return truncate(value);
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value == null) return 'null';
  if (Array.isArray(value)) {
    const sample = value.slice(0, 3).map((item) => safeString(item)).join(', ');
    return `数组 ${value.length} 项${sample ? `: ${sample}` : ''}`;
  }
  const record = asRecord(value);
  if (record) {
    const identifiers = ['id', 'code', 'stock_code', 'strategy_id', 'account_id', 'name', 'status']
      .map((key) => record[key])
      .filter((item) => item != null)
      .map((item) => safeString(item));
    if (identifiers.length) return identifiers.join(' / ');
    return `对象 ${Object.keys(record).length} 字段`;
  }
  return truncate(String(value));
}

function shouldOmitInputKey(key: string) {
  return OMIT_INPUT_KEYS.has(key) || SENSITIVE_KEY_PATTERN.test(key);
}

export function summarizeToolInput(args: Record<string, unknown>): string[] {
  const entries = Object.entries(args ?? {}).filter(([key]) => !shouldOmitInputKey(key));
  if (!entries.length) return ['无显式输入参数'];

  const byKey = new Map(entries);
  const prioritized: Array<[string, unknown]> = [];
  for (const key of INPUT_PRIORITY_KEYS) {
    if (byKey.has(key)) {
      prioritized.push([key, byKey.get(key)]);
    }
  }

  const remaining = entries.filter(([key]) => !INPUT_PRIORITY_KEYS.includes(key));
  return [...prioritized, ...remaining]
    .slice(0, MAX_SUMMARY_ITEMS)
    .map(([key, value]) => `${key}: ${safeString(value)}`);
}

function extractErrorMessage(result: unknown): string | null {
  if (result instanceof Error) return result.message;
  if (typeof result === 'string') return null;
  const root = asRecord(result);
  if (!root) return null;

  const candidates = [
    root.error,
    asRecord(root.result)?.error,
    asRecord(root.data)?.error,
    asRecord(asRecord(root.result)?.data)?.error,
  ];

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) return truncate(candidate, 240);
    const nested = asRecord(candidate);
    if (nested) {
      const message = nested.message ?? nested.code ?? nested.detail;
      if (typeof message === 'string' && message.trim()) return truncate(message, 240);
    }
  }
  if (root.success === false) return '工具返回 success=false';
  return null;
}

function summarizeArray(name: string, value: unknown[]): string {
  const sample = value
    .slice(0, 3)
    .map((item) => {
      const record = asRecord(item);
      if (!record) return safeString(item);
      const code = record.code ?? record.stock_code ?? record.symbol ?? record.strategy_id ?? record.id;
      const label = record.name ?? record.strategy_name ?? record.title ?? record.status;
      return [code, label].filter((part) => part != null).map((part) => safeString(part)).join(' / ') || safeString(item);
    })
    .filter(Boolean)
    .join('; ');
  return `${name}: ${value.length} 项${sample ? `，样例 ${sample}` : ''}`;
}

function summarizeRecordFields(record: Record<string, unknown>): string[] {
  const lines: string[] = [];
  const scalarKeys = [
    'tool',
    'source',
    'timestamp',
    'data_timestamp',
    'as_of',
    'status',
    'name',
    'stock_name',
    'price',
    'latest_price',
    'close',
    'pct_chg',
    'change_pct',
    'total_return',
    'cagr',
    'max_drawdown',
    'sharpe',
    'nav',
    'cash',
    'account_id',
    'strategy_id',
    'run_id',
    'artifact_id',
    'audit_event_id',
  ];

  for (const key of scalarKeys) {
    const value = record[key];
    if (value == null || typeof value === 'object') continue;
    lines.push(`${key}: ${safeString(value)}`);
    if (lines.length >= MAX_SUMMARY_ITEMS) return lines;
  }

  for (const [key, value] of Object.entries(record)) {
    if (lines.length >= MAX_SUMMARY_ITEMS) break;
    if (key === 'data' || key === 'result' || key === 'meta' || key === 'error') continue;
    if (Array.isArray(value)) {
      lines.push(summarizeArray(key, value));
    } else if (value && typeof value === 'object') {
      lines.push(`${key}: ${safeString(value)}`);
    }
  }

  return lines;
}

export function summarizeToolResult(result: unknown): { success: boolean; summary: string[]; errorMessage?: string } {
  const errorMessage = extractErrorMessage(result);
  if (errorMessage) {
    return { success: false, summary: [`错误: ${errorMessage}`], errorMessage };
  }

  if (typeof result === 'string') {
    return { success: true, summary: [truncate(result, 240)] };
  }
  if (Array.isArray(result)) {
    return { success: true, summary: [summarizeArray('返回列表', result)] };
  }

  const root = asRecord(result);
  if (!root) {
    return { success: true, summary: [`返回: ${safeString(result)}`] };
  }

  const summary: string[] = [];
  const meta = asRecord(root.meta);
  const data = asRecord(root.data);
  const resultRecord = asRecord(root.result);
  const payload = asRecord(resultRecord?.data) ?? resultRecord ?? data ?? root;

  if (typeof root.tool === 'string') summary.push(`tool: ${truncate(root.tool)}`);
  if (typeof root.source === 'string') summary.push(`source: ${truncate(root.source)}`);
  if (typeof root.timestamp === 'string') summary.push(`timestamp: ${truncate(root.timestamp)}`);
  if (meta) {
    if (typeof meta.audit_event_id === 'string') summary.push(`audit_event_id: ${truncate(meta.audit_event_id, 120)}`);
    if (typeof meta.degraded === 'boolean') summary.push(`degraded: ${meta.degraded}`);
    const sourceChain = Array.isArray(meta.source_chain) ? meta.source_chain.join(' > ') : '';
    if (sourceChain) summary.push(`source_chain: ${truncate(sourceChain, 160)}`);
    const lineage = asRecord(meta.lineage);
    if (lineage) {
      ['run_id', 'dataset_id', 'artifact_id', 'model_id', 'strategy_id', 'review_id'].forEach((key) => {
        if (lineage[key] != null) summary.push(`${key}: ${safeString(lineage[key])}`);
      });
    }
  }

  if (payload) {
    summary.push(...summarizeRecordFields(payload));
  }

  return {
    success: true,
    summary: Array.from(new Set(summary)).slice(0, MAX_SUMMARY_ITEMS).length
      ? Array.from(new Set(summary)).slice(0, MAX_SUMMARY_ITEMS)
      : [`返回对象 ${Object.keys(root).length} 字段`],
  };
}

export function createChatToolTrace(input: CreateTraceInput): ChatToolTraceDto {
  return {
    schemaVersion: 'tool_trace.v1',
    id: nextTraceId(),
    visibility: 'owner_only',
    generatedAt: nowIso(),
    status: 'empty',
    scope: {
      mode: input.mode,
      pageKey: input.pageKey,
      objectType: input.objectType,
      objectId: input.objectId,
      stockCode: input.stockCode,
    },
    items: [],
    answerReferences: [],
    evidenceMode: 'advisory_only',
    advisoryOnly: true,
    advisoryReason: '本次回答尚未产生实际工具调用。',
  };
}

export function addToolTraceItem(trace: ChatToolTraceDto, input: AddTraceItemInput): ChatToolTraceItemDto {
  const startedAt = input.startedAt ?? new Date();
  const item: ChatToolTraceItemDto = {
    id: `${trace.id}_item_${trace.items.length + 1}`,
    referenceLabel: `T${trace.items.length + 1}`,
    kind: input.kind,
    toolName: input.toolName,
    status: 'pending',
    startedAt: nowIso(startedAt),
    inputSummary: summarizeToolInput(input.args),
    outputSummary: [],
  };
  trace.items.push(item);
  updateTraceStatus(trace);
  return item;
}

export function finishToolTraceItem(trace: ChatToolTraceDto, itemId: string, result: unknown, finishedAt = new Date()) {
  const item = trace.items.find((candidate) => candidate.id === itemId);
  if (!item) return null;
  const summarized = summarizeToolResult(result);
  item.status = summarized.success ? 'success' : 'error';
  item.finishedAt = nowIso(finishedAt);
  item.durationMs = Math.max(0, new Date(item.finishedAt).getTime() - new Date(item.startedAt).getTime());
  item.outputSummary = summarized.summary;
  item.errorMessage = summarized.errorMessage;
  updateTraceStatus(trace);
  return item;
}

export function recordCompletedToolTraceItem(
  trace: ChatToolTraceDto,
  input: AddTraceItemInput,
  result: unknown,
  finishedAt = new Date(),
) {
  const item = addToolTraceItem(trace, input);
  finishToolTraceItem(trace, item.id, result, finishedAt);
  return item;
}

export function finalizeToolTrace(
  trace: ChatToolTraceDto,
  answerContent: string,
  options: { hasPageContextEvidence?: boolean } = {},
): ChatToolTraceDto {
  const citedLabels = new Set(Array.from(answerContent.matchAll(/\[(T\d+)\]/g)).map((match) => match[1]));
  trace.answerReferences = trace.items
    .filter((item) => item.status === 'success' && citedLabels.has(item.referenceLabel))
    .map((item) => {
      item.citedInAnswer = true;
      return {
        itemId: item.id,
        referenceLabel: item.referenceLabel,
        toolName: item.toolName,
        evidenceSummary: item.outputSummary[0] ?? `${item.toolName} 返回成功`,
      };
    });

  updateTraceStatus(trace);
  const hasSuccessfulMcp = trace.items.some((item) => item.kind === 'mcp' && item.status === 'success');
  const hasSuccessfulTool = trace.items.some((item) => item.status === 'success');
  if (hasSuccessfulMcp) {
    trace.evidenceMode = 'mcp_supported';
    trace.advisoryOnly = false;
    delete trace.advisoryReason;
  } else if (hasSuccessfulTool) {
    trace.evidenceMode = 'tool_supported';
    trace.advisoryOnly = false;
    delete trace.advisoryReason;
  } else if (options.hasPageContextEvidence) {
    trace.evidenceMode = 'page_context_supported';
    trace.advisoryOnly = false;
    trace.advisoryReason = '本次没有成功的 MCP 工具调用，回答主要依赖页面上下文。';
  } else {
    trace.evidenceMode = 'advisory_only';
    trace.advisoryOnly = true;
    trace.advisoryReason = trace.items.length
      ? '本次工具调用未成功返回可用证据，回答仍属于纯建议态。'
      : '本次没有实际 MCP 工具调用或页面证据，回答属于纯建议态。';
  }
  trace.generatedAt = nowIso();
  return trace;
}

export function cloneToolTrace(trace: ChatToolTraceDto): ChatToolTraceDto {
  return JSON.parse(JSON.stringify(trace)) as ChatToolTraceDto;
}

function updateTraceStatus(trace: ChatToolTraceDto) {
  if (!trace.items.length) {
    trace.status = 'empty';
    return;
  }
  if (trace.items.some((item) => item.status === 'pending')) {
    trace.status = 'running';
    return;
  }
  trace.status = trace.items.some((item) => item.status === 'error') ? 'partial_error' : 'completed';
}
