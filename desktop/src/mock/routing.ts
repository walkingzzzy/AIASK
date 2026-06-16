export function normalizeMockMethod(method?: string): string {
  return (method || "GET").toUpperCase();
}

export function mockBodyRecord(body: unknown): Record<string, unknown> {
  return (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
}

export function parseMockPath(path: string): { cleanPath: string; query: URLSearchParams } {
  const [cleanPath, query = ""] = path.split("?");
  return { cleanPath, query: new URLSearchParams(query) };
}

export function ok<T>(payload: T): Promise<T> {
  return Promise.resolve(payload);
}
