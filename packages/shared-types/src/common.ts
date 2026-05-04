export type Envelope<T = unknown> = {
    ok?: boolean;
    success?: boolean;
    data?: T;
    error?: string | {
        code?: string;
        message?: string;
        detail?: unknown;
    };
    meta?: CacheMeta;
    traceId?: string;
};

export type CacheMeta = {
    cachedAt?: string;
    expiresAt?: string;
    stale?: boolean;
    fetchedAt?: string;
    cache?: {
        hit?: boolean;
        backend?: string;
        ttlSeconds?: number;
    };
};

export const SKILL_STATUSES = [
    'registered',
    'executable',
    'deprecated',
] as const;

export type SkillStatus = typeof SKILL_STATUSES[number];

export const SKILL_EXECUTION_MODES = [
    'orchestrated',
    'no_handler',
    'deprecated',
] as const;

export type SkillExecutionMode = typeof SKILL_EXECUTION_MODES[number];

export const SKILL_ERROR_CODES = [
    'SKILL_NOT_FOUND',
    'SKILL_NOT_EXECUTABLE',
    'SKILL_DEPRECATED',
    'SKILL_EXECUTION_FAILED',
    'SKILLS_REGISTRY_UNAVAILABLE',
] as const;

export type SkillErrorCode = typeof SKILL_ERROR_CODES[number];

export type SkillSchema = Record<string, unknown>;

export type SkillDescriptor = {
    id: string;
    name?: string;
    category?: string;
    description?: string;
    path?: string;
    status: SkillStatus;
    executable: boolean;
    deprecated?: boolean;
    handler_available?: boolean;
    execution_mode?: SkillExecutionMode;
    input_schema?: SkillSchema;
    output_schema?: SkillSchema;
    supported_tasks?: string[];
};

export type AlertItem = {
    id: string;
    code: string;
    indicator: string;
    condition: string;
    value: number | null;
};

export type AlertsListData = {
    status: string;
    items: AlertItem[];
    sourceTool: 'alerts_manager';
    argsMatched: Record<string, unknown>;
    meta: CacheMeta;
};

export type NotificationType = 'alert' | 'signal' | 'trade' | 'system' | 'news';

export type NotificationLevel = 'info' | 'warn' | 'error';

export type NotificationItem = {
    id: string;
    type: NotificationType;
    level: NotificationLevel;
    title: string;
    body: string;
    read: boolean;
    createdAt: string;
};

export type NotificationsListData = {
    items: NotificationItem[];
    total: number;
    unread: number;
};

export type ToolArgs = Record<string, unknown>;

export type ToolCacheBackend = 'redis' | 'memory' | 'none';

export type ToolCacheInfo = {
    hit: boolean;
    backend: ToolCacheBackend;
    key: string;
    ttlSeconds: number;
};

export type ToolMeta = {
    fetchedAt: string;
    cache: ToolCacheInfo;
};

export type AcceptanceStatus = 'degraded' | 'prerequisite_missing' | 'unavailable';

export type DataQualityStatus =
    | 'trusted'
    | 'degraded'
    | 'partial'
    | 'conflict'
    | 'empty'
    | 'unavailable';

export type DataQualitySource = {
    name: string;
    status: DataQualityStatus | 'failed';
    freshness?: string | null;
    error?: string | null;
    sampleCount?: number | null;
};

export type DataQuality = {
    status: DataQualityStatus;
    reasons: string[];
    sources: DataQualitySource[];
    quality_flags: string[];
    empty_reason?: string;
};

export type McpTransportMode = 'stdio' | 'streamable-http' | 'sse' | 'auto';

export type McpTransportKind = 'stdio' | 'streamable-http' | 'sse';

export type McpResolvedTransportKind = McpTransportKind | 'none';

export type McpTransportSnapshot = {
    requested_transport: McpTransportMode;
    active_transport: McpResolvedTransportKind;
    degraded: boolean;
    fallback_reason: string | null;
    source_chain: McpResolvedTransportKind[];
    endpoint: string | null;
    last_error: string | null;
};

export type McpToolTransportMeta = {
    backend_requested: string | null;
    backend_used: string | null;
    fallback_used: boolean;
    fallback_reason: string | null;
    latency_ms: number;
    transport?: McpTransportSnapshot | null;
};

export type McpTransportFailureDetail = {
    acceptance_status: Extract<AcceptanceStatus, 'degraded' | 'unavailable'>;
    path?: string | null;
    upstream?: unknown;
    transport: McpTransportSnapshot;
};

export type CreateMcpToolJobInput = {
    tool_name: string;
    arguments?: ToolArgs;
    timeout_ms?: number | null;
    idempotency_key?: string | null;
};

export const MCP_JOB_STATUSES = [
    'queued',
    'running',
    'succeeded',
    'failed',
] as const;

export type McpJobStatus = typeof MCP_JOB_STATUSES[number];

export type McpJobErrorCode =
    | 'MCP_JOB_EXECUTION_FAILED'
    | 'MCP_JOB_TIMEOUT'
    | 'MCP_JOB_TRANSPORT_UNAVAILABLE';

export type McpJobTarget = {
    kind: 'tool';
    name: string;
    arguments: ToolArgs;
    timeout_ms: number;
};

export type McpJobMeta = {
    transport?: McpTransportSnapshot | null;
    [key: string]: unknown;
};

export type McpJobRecord = {
    job_id: string;
    status: McpJobStatus;
    submitted_at: string;
    started_at?: string | null;
    completed_at?: string | null;
    poll_path: string;
    idempotency_key: string | null;
    target: McpJobTarget;
    result: unknown | null;
    error: string | null;
    error_code: McpJobErrorCode | null;
    trace_id: string | null;
    meta?: McpJobMeta | null;
};

export type McpJobAcceptedResponse = {
    accepted: boolean;
    deduplicated: boolean;
    job: McpJobRecord;
};
