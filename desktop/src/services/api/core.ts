import type { ApiProblem, ConnectionSettings, UnknownRecord } from "../../types";

const SENSITIVE_KEY_PATTERN = /(api[_-]?key|token|secret|password|credential|authorization|bearer)/i;

export class ApiError extends Error {
  problem: ApiProblem;

  constructor(problem: ApiProblem) {
    super(problem.detail || problem.title);
    this.name = "ApiError";
    this.problem = problem;
  }
}

export function redactSecrets<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => redactSecrets(item)) as T;
  }
  if (value && typeof value === "object") {
    const result: UnknownRecord = {};
    Object.entries(value as UnknownRecord).forEach(([key, item]) => {
      result[key] = SENSITIVE_KEY_PATTERN.test(key) ? "[redacted]" : redactSecrets(item);
    });
    return result as T;
  }
  return value;
}

export function toList<T = UnknownRecord>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object") {
    const record = payload as UnknownRecord;
    if (Array.isArray(record.data)) return record.data as T[];
    if (record.data && typeof record.data === "object") {
      const data = record.data as UnknownRecord;
      const firstArray = Object.values(data).find(Array.isArray);
      if (Array.isArray(firstArray)) return firstArray as T[];
    }
  }
  return [];
}

export function objectData<T = UnknownRecord>(payload: unknown, fallback: T): T {
  if (payload && typeof payload === "object") {
    const record = payload as UnknownRecord;
    if (record.data && typeof record.data === "object" && !Array.isArray(record.data)) {
      return record.data as T;
    }
    return record as T;
  }
  return fallback;
}

function buildUrl(baseUrl: string, path: string, query?: Record<string, unknown>): string {
  const url = new URL(path, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
  Object.entries(query || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    url.searchParams.set(key, String(value));
  });
  return url.toString();
}

function authHeaders(settings: ConnectionSettings, needsControl: boolean): HeadersInit {
  const headers: Record<string, string> = {
    Accept: "application/json"
  };
  if (settings.apiToken.trim()) {
    headers.Authorization = `Bearer ${settings.apiToken.trim()}`;
    headers["X-AIASK-Agent-Token"] = settings.apiToken.trim();
  }
  if (settings.controlToken.trim() && needsControl) {
    headers["X-AIASK-Agent-Control-Token"] = settings.controlToken.trim();
    headers["X-AIASK-Local-Control-Token"] = settings.controlToken.trim();
  }
  if (settings.userId.trim()) {
    headers["X-AIASK-User-Id"] = settings.userId.trim();
  }
  return headers;
}

async function parseError(response: Response): Promise<ApiProblem> {
  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    raw = await response.text().catch(() => undefined);
  }
  const record = raw && typeof raw === "object" ? (raw as UnknownRecord) : {};
  return {
    status: response.status,
    title: String(record.title || response.statusText || "Request failed"),
    detail: String(record.detail || record.error || raw || ""),
    code: typeof record.error_code === "string" ? record.error_code : typeof record.code === "string" ? record.code : undefined,
    raw: redactSecrets(raw)
  };
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, unknown>;
  control?: boolean;
  signal?: AbortSignal;
  timeoutMs?: number;
  headers?: HeadersInit;
}

export async function requestJson<T>(
  settings: ConnectionSettings,
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs ?? 20_000);
  const headers = {
    ...authHeaders(settings, Boolean(options.control)),
    ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
    ...(options.headers || {})
  };

  try {
    const response = await fetch(buildUrl(settings.baseUrl, path, options.query), {
      method: options.method ?? (options.body === undefined ? "GET" : "POST"),
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal ?? controller.signal
    });
    if (!response.ok) {
      throw new ApiError(await parseError(response));
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return redactSecrets((await response.json()) as T);
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function requestText(
  settings: ConnectionSettings,
  path: string,
  options: RequestOptions = {}
): Promise<string> {
  const response = await fetch(buildUrl(settings.baseUrl, path, options.query), {
    method: options.method ?? "GET",
    headers: authHeaders(settings, Boolean(options.control)),
    signal: options.signal
  });
  if (!response.ok) {
    throw new ApiError(await parseError(response));
  }
  return response.text();
}

export function parseSsePayload(text: string): unknown[] {
  const chunks = text
    .split(/\n\n+/)
    .map((chunk) =>
      chunk
        .split(/\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("")
    )
    .filter(Boolean);
  return chunks.map((chunk) => {
    try {
      return JSON.parse(chunk);
    } catch {
      return { message: chunk };
    }
  });
}
