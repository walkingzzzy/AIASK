import type { CapabilityIssue, CapabilityMatrixItem } from "../../types";

export function itemLabel(item: Record<string, unknown>): string {
  return String(item.feature || item.hermes_tool || item.platform || item.reference || item.name || "item");
}

export function collectCapabilityRows(payload: {
  hermes?: {
    tool_mapping?: unknown[];
    platform_mapping?: unknown[];
    feature_mapping?: unknown[];
    parity?: {
      v014_delta?: { missing?: unknown[]; partial?: unknown[]; implemented?: unknown[] };
      v016_delta?: { missing?: unknown[]; partial?: unknown[]; implemented?: unknown[] };
    };
  };
} | null): CapabilityMatrixItem[] {
  const hermes = payload?.hermes || {};
  const delta014 = hermes.parity?.v014_delta || {};
  const delta016 = hermes.parity?.v016_delta || {};
  return [
    ...(hermes.feature_mapping || []),
    ...(hermes.tool_mapping || []),
    ...(hermes.platform_mapping || []),
    ...(delta014.missing || []),
    ...(delta014.partial || []),
    ...(delta014.implemented || []),
    ...(delta016.missing || []),
    ...(delta016.partial || []),
    ...(delta016.implemented || [])
  ] as CapabilityMatrixItem[];
}

export function filterRows<T extends Record<string, unknown>>(rows: T[], query: string, status: string): T[] {
  const normalizedQuery = query.trim().toLowerCase();
  return rows.filter((item) => {
    const matchesQuery = !normalizedQuery || JSON.stringify(item).toLowerCase().includes(normalizedQuery);
    const matchesStatus = status === "all" || String(item.status || item.live_status || "").toLowerCase() === status;
    return matchesQuery && matchesStatus;
  });
}

export function capabilityIssues(payload: {
  hermes?: { issues?: CapabilityIssue[] };
} | null): CapabilityIssue[] {
  return payload?.hermes?.issues || [];
}
