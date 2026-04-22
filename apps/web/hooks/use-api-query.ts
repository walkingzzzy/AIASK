'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import {
  authedFetch,
  buildApiError,
  getApiErrorAcceptanceStatus,
  rejectFallbackPayload,
  unwrapApiEnvelope,
} from '@/lib/api';
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
  /** 提供非致命回退数据，避免壳层接口失败时破坏页面主体 */
  fallbackData?: TData | null;
  /** 当接口属于非致命依赖时，失败不向页面冒泡 error */
  nonFatal?: boolean;
  /** 关键依赖：拒绝 degraded/fallback/空壳成功态 */
  critical?: boolean;
  /** 额外业务校验，返回错误文案则视为失败 */
  reject?: (raw: unknown) => string | null;
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
    fallbackData,
    nonFatal = false,
    critical = false,
    reject,
  } = options;
  const isLoggingOut = useAuthStore((s) => s.isLoggingOut);
  const bffAvailability = useBffAvailability({ probeOnMount: enabled && path != null });
  const prevReachableRef = useRef(bffAvailability.reachable);

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
        throw buildApiError(bodyPayload, {
          status: resp.status,
          path: path!,
          fallbackMessage: `HTTP ${resp.status}`,
        });
      }
      const envelope = bodyPayload as Envelope<TData>;
      const unwrapped = unwrapApiEnvelope<TData>(envelope);
      const trace = unwrapped.traceId ? ` (traceId: ${unwrapped.traceId})` : '';
      if (unwrapped.errorMessage) {
        throw new Error(`${unwrapped.errorMessage} @ ${path}${trace}`);
      }
      const rawData = unwrapped.data;
      if (critical) {
        const fallbackReason = rejectFallbackPayload(rawData);
        if (fallbackReason) {
          throw new Error(`关键数据不可用: ${fallbackReason} @ ${path}${trace}`);
        }
      }
      if (reject) {
        const rejection = reject(rawData);
        if (rejection) {
          throw new Error(`${rejection} @ ${path}${trace}`);
        }
      }
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
  const acceptanceStatus = disabledByOffline ? 'unavailable' : getApiErrorAcceptanceStatus(query.error);
  const derivedError = nonFatal
    ? null
    : disabledByOffline
      ? '数据服务暂不可用'
      : (query.error?.message ?? null);
  const hasFallbackData = fallbackData !== undefined;
  const derivedPending = ((enabled && path != null && bffAvailability.checking && !hasFallbackData) || query.isPending);
  const refetch = useCallback(async () => {
    if (enabled && path != null && !bffAvailability.reachable) {
      const reachable = await ensureBffAvailability({ force: true });
      if (!reachable) return query.refetch();
    }
    return query.refetch();
  }, [bffAvailability.reachable, enabled, path, query]);

  useEffect(() => {
    const recovered = !prevReachableRef.current && bffAvailability.reachable;
    prevReachableRef.current = bffAvailability.reachable;

    if (!recovered) return;
    if (isLoggingOut || !enabled || path == null) return;
    if (query.isFetching) return;
    if (query.data != null && !query.error) return;

    void query.refetch();
  }, [
    bffAvailability.reachable,
    enabled,
    isLoggingOut,
    path,
    query.data,
    query.error,
    query.isFetching,
    query.refetch,
  ]);

  return {
    data: query.data ?? fallbackData ?? null,
    isPending: derivedPending,
    isFetching: query.isFetching,
    error: derivedError,
    rawError: query.error ?? null,
    acceptanceStatus,
    dataUpdatedAt: query.dataUpdatedAt,
    refetch,
    serviceUnavailable: disabledByOffline,
  };
}
