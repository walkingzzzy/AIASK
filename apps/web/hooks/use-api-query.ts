'use client';

import { useCallback, useEffect, useRef } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import {
  authedFetch,
  buildApiError,
  extractDataTrust,
  getApiErrorAcceptanceStatus,
  isAbortLikeError,
  rejectFallbackPayload,
  unwrapApiEnvelope,
} from '@/lib/api';
import type { DataTrust } from '@/lib/api';
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
  /** 关键查询中允许契约化空结果作为正常 EmptyState 展示 */
  allowEmpty?: boolean;
  /** 覆盖 React Query retry；默认沿用全局配置 */
  retry?: boolean | number | ((failureCount: number, error: Error) => boolean);
  /** 覆盖默认请求超时；<=0 表示仅使用 React Query signal */
  timeoutMs?: number;
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
    allowEmpty = false,
    retry,
    timeoutMs,
  } = options;
  const isLoggingOut = useAuthStore((s) => s.isLoggingOut);
  const bffAvailability = useBffAvailability({ probeOnMount: enabled && path != null });
  const prevReachableRef = useRef(bffAvailability.reachable);
  const hasFallbackData = fallbackData !== undefined;

  // Extract module from path (e.g. '/portfolio/list' → 'portfolio')
  // so invalidateQueries({ queryKey: ['api', 'portfolio'] }) matches all portfolio queries.
  const module = path?.split('/').filter(Boolean)[0] ?? '__disabled__';
  const qk = ['api', module, path ?? '__disabled__', ...keyExtra, ...(body != null ? [body] : [])];

  const queryEnabled = !isLoggingOut && enabled && path != null && !bffAvailability.unavailable;

  const queryRetry = retry ?? ((failureCount: number, error: Error) => !isAbortLikeError(error) && failureCount < 1);

  const query = useQuery<TData, Error>({
    queryKey: qk,
    queryFn: async ({ signal }) => {
      const method = fetchOptions?.method ?? (body ? 'POST' : 'GET');
      const requestTimeoutMs = timeoutMs ?? (critical ? 10_000 : 12_000);
      const controller = requestTimeoutMs > 0 ? new AbortController() : null;
      let timedOut = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const abortFromQuery = () => controller?.abort(signal.reason);
      if (controller) {
        if (signal.aborted) controller.abort(signal.reason);
        else signal.addEventListener('abort', abortFromQuery, { once: true });
        timer = setTimeout(() => {
          timedOut = true;
          controller.abort(new DOMException('请求超时', 'AbortError'));
        }, requestTimeoutMs);
      }
      const init: RequestInit = { method, signal: controller?.signal ?? signal };
      if (body) {
        init.headers = { 'content-type': 'application/json', ...fetchOptions?.headers };
        init.body = JSON.stringify(body);
      } else if (fetchOptions?.headers) {
        init.headers = fetchOptions.headers;
      }
      try {
        let resp: Response;
        try {
          resp = await authedFetch(path!, init, { redirectOnUnauthorized });
        } catch (error) {
          if (timedOut && isAbortLikeError(error)) {
            throw new Error(`服务响应较慢，已超过 ${Math.round(requestTimeoutMs / 1000)} 秒；可稍后刷新或重试 @ ${path}`);
          }
          throw error;
        }
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
          const fallbackReason = rejectFallbackPayload(rawData, { allowEmpty });
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
      } finally {
        if (timer) clearTimeout(timer);
        if (controller) signal.removeEventListener('abort', abortFromQuery);
      }
    },
    enabled: queryEnabled,
    refetchInterval: refetchInterval as number | false | undefined,
    staleTime,
    retry: queryRetry,
    placeholderData: placeholderData === 'keepPrevious' ? keepPreviousData : undefined,
  });

  const queryData = query.data;
  const queryError = query.error;
  const queryIsFetching = query.isFetching;
  const queryIsPending = query.isPending;
  const queryRefetch = query.refetch;
  const queryDataUpdatedAt = query.dataUpdatedAt;
  const hasQueryData = queryData != null;
  const hasUsableDataResolved = hasQueryData || hasFallbackData;
  const disabledByOffline = enabled && path != null && bffAvailability.unavailable && !hasUsableDataResolved;
  const queryCanceled = isAbortLikeError(queryError);
  const acceptanceStatus = disabledByOffline
    ? 'unavailable'
    : bffAvailability.unavailable && hasUsableDataResolved
      ? 'degraded'
      : queryCanceled
        ? null
        : getApiErrorAcceptanceStatus(queryError);
  const derivedError = nonFatal
    ? null
    : disabledByOffline
      ? '数据服务暂不可用'
      : queryCanceled
        ? null
        : (queryError?.message ?? null);
  const derivedPending = queryIsPending || (enabled && path != null && bffAvailability.checking && !hasUsableDataResolved);
  const refetch = useCallback(async () => {
    if (enabled && path != null && !bffAvailability.reachable) {
      const reachable = await ensureBffAvailability({ force: true });
      if (!reachable) return queryRefetch();
    }
    return queryRefetch();
  }, [bffAvailability.reachable, enabled, path, queryRefetch]);

  useEffect(() => {
    const recovered = !prevReachableRef.current && bffAvailability.reachable;
    prevReachableRef.current = bffAvailability.reachable;

    if (!recovered) return;
    if (isLoggingOut || !enabled || path == null) return;
    if (queryIsFetching) return;
    if (queryData != null && !queryError) return;

    void queryRefetch();
  }, [
    bffAvailability.reachable,
    enabled,
    isLoggingOut,
    path,
    queryData,
    queryError,
    queryIsFetching,
    queryRefetch,
  ]);

  const trust: DataTrust = extractDataTrust(queryData ?? fallbackData ?? null);

  return {
    data: queryData ?? fallbackData ?? null,
    isPending: derivedPending,
    isFetching: queryIsFetching,
    error: derivedError,
    rawError: queryError ?? null,
    acceptanceStatus,
    dataUpdatedAt: queryDataUpdatedAt,
    trust,
    refetch,
    serviceUnavailable: disabledByOffline,
  };
}
