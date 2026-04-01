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
