import { isMockEndpoint, mockRequestJson } from "./mockApi";

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

export type ApiHeaders = Record<string, string>;

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function normalizeEndpoint(endpoint: string): string {
  return (endpoint || "http://127.0.0.1:8767").trim().replace(/\/+$/, "");
}

export function authHeaders(token: string): ApiHeaders {
  const headers: ApiHeaders = { "Content-Type": "application/json" };
  if (token.trim()) {
    headers.Authorization = `Bearer ${token.trim()}`;
  }
  return headers;
}

export async function requestJson<T>(
  endpoint: string,
  path: string,
  options: {
    method?: string;
    token?: string;
    body?: unknown;
    headers?: ApiHeaders;
  } = {}
): Promise<T> {
  const normalizedEndpoint = normalizeEndpoint(endpoint);
  if (isMockEndpoint(normalizedEndpoint)) {
    return mockRequestJson<T>(path, options);
  }
  const url = `${normalizedEndpoint}${path}`;
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: { ...authHeaders(options.token || ""), ...(options.headers || {}) },
    body: options.body === undefined ? undefined : JSON.stringify(options.body)
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message =
      typeof payload === "object" && payload && "error" in payload
        ? JSON.stringify((payload as { error: unknown }).error)
        : response.statusText;
    throw new ApiError(message, response.status, payload);
  }
  return payload as T;
}

export function formatApiError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "AIASK_UNAUTHORIZED";
    if (error.status === 403) return "AIASK_FORBIDDEN";
    if (error.status === 404) return "AIASK_NOT_FOUND";
    if (error.status === 409) return "AIASK_CONFLICT";
    return `AIASK_HTTP_${error.status}`;
  }
  if (error instanceof TypeError) return "AIASK_OFFLINE";
  if (error instanceof Error) return error.message;
  return "AIASK_ERROR";
}

export function parseSseEvents<T = Record<string, unknown>>(text: string): T[] {
  return text
    .split(/\r?\n\r?\n/)
    .map((chunk): T | null => {
      const lines = chunk.split(/\r?\n/);
      let eventName = "";
      let eventId = "";
      const dataLines: string[] = [];
      lines.forEach((line) => {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("id:")) eventId = line.slice(3).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      });
      const dataText = dataLines.join("\n").trim();
      if (!dataText || dataText === "[DONE]") return null;
      const parsed = JSON.parse(dataText);
      const eventData: Record<string, unknown> =
        parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : { value: parsed };
      return {
        ...eventData,
        id: eventId || eventData.id,
        event: eventName || eventData.event || eventData.type || "message",
        data: eventData.data ?? eventData
      } as T;
    })
    .filter((event): event is T => !!event);
}

export async function streamJson<T>(
  endpoint: string,
  path: string,
  options: {
    method?: string;
    token?: string;
    body?: unknown;
    headers?: ApiHeaders;
    onChunk?: (chunk: T) => void;
    onDone?: () => void;
  } = {}
): Promise<void> {
  const url = `${normalizeEndpoint(endpoint)}${path}`;
  const response = await fetch(url, {
    method: options.method || "GET",
    headers: { ...authHeaders(options.token || ""), ...(options.headers || {}) },
    body: options.body === undefined ? undefined : JSON.stringify(options.body)
  });

  if (!response.ok) {
    const text = await response.text();
    let payload = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch (e) {
      // ignore
    }
    const message =
      typeof payload === "object" && payload && "error" in payload
        ? JSON.stringify((payload as { error: unknown }).error)
        : response.statusText;
    throw new ApiError(message, response.status, payload);
  }

  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const chunk = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        try {
          for (const event of parseSseEvents<T>(chunk)) {
            if (options.onChunk) options.onChunk(event);
          }
        } catch (e) {
          // ignore parse errors for partial/corrupted chunks
        }
        if (chunk.includes("data: [DONE]")) {
          if (options.onDone) options.onDone();
          return;
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
  if (options.onDone) options.onDone();
}
