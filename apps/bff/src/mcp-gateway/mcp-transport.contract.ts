import type {
  AcceptanceStatus,
  McpResolvedTransportKind,
  McpToolTransportMeta,
  McpTransportFailureDetail,
  McpTransportKind,
  McpTransportMode,
  McpTransportSnapshot,
} from '@aiask/shared-types';

export type GatewayTransportSnapshotLike = {
  requestedTransport: McpTransportMode;
  transportKind: McpResolvedTransportKind;
  degraded: boolean;
  fallbackReason: string | null;
  sourceChain: string[];
  endpoint: string | null;
  lastError: string | null;
};

function normalizeTransportMode(value: unknown): McpTransportMode {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'stdio') return 'stdio';
  if (normalized === 'streamable-http' || normalized === 'streamable_http' || normalized === 'http') {
    return 'streamable-http';
  }
  if (normalized === 'sse') return 'sse';
  return 'auto';
}

function normalizeTransportKind(value: unknown): McpResolvedTransportKind {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'stdio') return 'stdio';
  if (normalized === 'streamable-http' || normalized === 'streamable_http' || normalized === 'http') {
    return 'streamable-http';
  }
  if (normalized === 'sse') return 'sse';
  return 'none';
}

function normalizeSourceChain(chain: readonly string[] | null | undefined, activeTransport: McpResolvedTransportKind) {
  const resolved = (Array.isArray(chain) ? chain : [])
    .map((item) => normalizeTransportKind(item))
    .filter((item, index, list) => list.indexOf(item) === index);

  if (resolved.length > 0) {
    return resolved;
  }
  return [activeTransport];
}

export function toMcpTransportSnapshot(snapshot: GatewayTransportSnapshotLike): McpTransportSnapshot {
  const activeTransport = normalizeTransportKind(snapshot.transportKind);
  return {
    requested_transport: normalizeTransportMode(snapshot.requestedTransport),
    active_transport: activeTransport,
    degraded: Boolean(snapshot.degraded),
    fallback_reason: snapshot.fallbackReason ?? null,
    source_chain: normalizeSourceChain(snapshot.sourceChain, activeTransport),
    endpoint: snapshot.endpoint ?? null,
    last_error: snapshot.lastError ?? null,
  };
}

export function withToolTransportMeta(
  payload: Omit<McpToolTransportMeta, 'transport'>,
  snapshot?: GatewayTransportSnapshotLike | null,
): McpToolTransportMeta {
  return {
    ...payload,
    transport: snapshot ? toMcpTransportSnapshot(snapshot) : null,
  };
}

export function buildMcpTransportFailureDetail(
  snapshot: GatewayTransportSnapshotLike,
  options: {
    acceptanceStatus: Extract<AcceptanceStatus, 'degraded' | 'unavailable'>;
    path?: string | null;
    upstream?: unknown;
  },
): McpTransportFailureDetail {
  return {
    acceptance_status: options.acceptanceStatus,
    ...(options.path !== undefined ? { path: options.path } : {}),
    ...(options.upstream !== undefined ? { upstream: options.upstream } : {}),
    transport: toMcpTransportSnapshot(snapshot),
  };
}

export function toGatewayTransportSnapshot(
  transport: McpTransportSnapshot,
): GatewayTransportSnapshotLike {
  return {
    requestedTransport: transport.requested_transport,
    transportKind: transport.active_transport,
    degraded: transport.degraded,
    fallbackReason: transport.fallback_reason,
    sourceChain: transport.source_chain as Array<McpTransportKind | 'none'>,
    endpoint: transport.endpoint,
    lastError: transport.last_error,
  };
}
