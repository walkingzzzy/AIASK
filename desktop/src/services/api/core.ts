import { normalizeEndpoint } from "../../api";

export interface AiaskClientOptions {
  endpoint: string;
  apiToken?: string;
  controlToken?: string;
}

export interface AiaskTokenSource {
  apiToken?: string;
  controlToken?: string;
}

export function controlOrApiToken(options: AiaskTokenSource): string {
  return options.controlToken?.trim() || options.apiToken?.trim() || "";
}

export function compactForSearch(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export class AiaskApiCore {
  endpoint: string;
  apiToken: string;
  controlToken: string;

  constructor(options: AiaskClientOptions) {
    this.endpoint = normalizeEndpoint(options.endpoint);
    this.apiToken = options.apiToken || "";
    this.controlToken = options.controlToken || "";
  }
}
