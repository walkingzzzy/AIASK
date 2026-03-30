'use client';

import { useCallback } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { authedFetch, extractApiErrorMessage, unwrapApiEnvelope } from '@/lib/api';
import { ensureBffAvailability, useBffAvailability } from '@/lib/bff-availability';
import { useAuthStore } from '@/store/auth-store';
import type { Envelope } from '@aiask/shared-types';

type FetchOptions = {
  method?: 'GET' | 'POST';
  headers?: Record<string, string>;
};

export type UseApiQueryOptions<TData> = {
  /** 额外 key 片段，附加在 ['api', path] 之后 */
  queryKey?: unknown[];
  /** false 禁用自动请求 */
  enabled?: boolean;
  /** 轮询间隔（ms），传函数可动态控制 */
  refetchInterval?: number | false | (() => number | false);
  /** 覆盖默认 staleTime */
  staleTime?: number;
  /** POST 读请求的 body */
  body?: unknown;
  /** 额外 fetch 选项 */
  fetchOptions?: FetchOptions;
  /** 'keepPrevious' 切换参数时保留旧数据 */
  placeholderData?: 'keepPrevious';
  /** 可选数据解析器：用于运行时 schema 校验/结构转换 */
  parse?: (raw: unknown) => TData;
  /** 401 时是否跳转到登录页；公共承载页可关闭为静默失败 */
  redirectOnUnauthorized?: boolean;
};

/**
 * 读请求 hook — 基于 useQuery + authedFetch。
 * path 为 null 时自动禁用查询。
 */
export function useApiQuery<TData = unknown>(path: string | null, options: UseApiQueryOptions<TData> = {}) {
  const {
    queryKey: keyExtra = [],
    enabled = true,
    refetchInterval,
    staleTime,
    body,
    fetchOptions,
    placeholderData,
    parse,
    redirectOnUnauthorized = true,
  } = options;
  const isLoggingOut = useAuthStore((s) => s.isLoggingOut);
  const bffAvailability = useBffAvailability({ probeOnMount: enabled && path != null });

  // Extract module from path (e.g. '/portfolio/list' → 'portfolio')
  // so invalidateQueries({ queryKey: ['api', 'portfolio'] }) matches all portfolio queries.
  const module = path?.split('/').filter(Boolean)[0] ?? '__disabled__';
  const qk = ['api', module, path ?? '__disabled__', ...keyExtra, ...(body != null ? [body] : [])];

  const query = useQuery<TData, Error>({
    queryKey: qk,
    queryFn: async ({ signal }) => {
      const method = fetchOptions?.method ?? (body ? 'POST' : 'GET');
      const init: RequestInit = { method, signal };
      if (body) {
        init.headers = { 'content-type': 'application/json', ...fetchOptions?.headers };
        init.body = JSON.stringify(body);
      } else if (fetchOptions?.headers) {
        init.headers = fetchOptions.headers;
      }
      const resp = await authedFetch(path!, init, { redirectOnUnauthorized });
      const bodyPayload = await resp.json().catch(() => null);
      if (!resp.ok) {
        let msg = `HTTP ${resp.status} @ ${path}`;
        const detail = extractApiErrorMessage(bodyPayload, msg);
        if (detail !== msg) msg = `${detail} @ ${path}`;
        const traceId =
          bodyPayload &&
          typeof bodyPayload === 'object' &&
          typeof (bodyPayload as { traceId?: unknown }).traceId === 'string'
            ? (bodyPayload as { traceId: string }).traceId
            : undefined;
        if (traceId) msg = `${msg} (traceId: ${traceId})`;
        throw new Error(msg);
      }
      const envelope = bodyPayload as Envelope<TData>;
      const unwrapped = unwrapApiEnvelope<TData>(envelope);
      const trace = unwrapped.traceId ? ` (traceId: ${unwrapped.traceId})` : '';
      if (unwrapped.errorMessage) {
        throw new Error(`${unwrapped.errorMessage} @ ${path}${trace}`);
      }
      const rawData = unwrapped.data;
      if (parse) {
        try {
          return parse(rawData);
        } catch (err) {
          const detail = err instanceof Error ? err.message : String(err);
          throw new Error(`数据结构异常: ${detail} @ ${path}${trace}`);
        }
      }
      return rawData as TData;
    },
    enabled: !isLoggingOut && enabled && path != null && bffAvailability.reachable,
    refetchInterval: refetchInterval as number | false | undefined,
    staleTime,
    placeholderData: placeholderData === 'keepPrevious' ? keepPreviousData : undefined,
  });

  const disabledByOffline = enabled && path != null && bffAvailability.unavailable;
  const derivedError = disabledByOffline ? '数据服务暂不可用' : (query.error?.message ?? null);
  const derivedPending = (enabled && path != null && bffAvailability.checking) || query.isPending;
  const refetch = useCallback(async () => {
    if (enabled && path != null && !bffAvailability.reachable) {
      const reachable = await ensureBffAvailability({ force: true });
      if (!reachable) return query.refetch();
    }
    return query.refetch();
  }, [bffAvailability.reachable, enabled, path, query]);

  return {
    data: query.data ?? null,
    isPending: derivedPending,
    isFetching: query.isFetching,
    error: derivedError,
    dataUpdatedAt: query.dataUpdatedAt,
    refetch,
    serviceUnavailable: disabledByOffline,
  };
}
