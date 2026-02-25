'use client';

import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { authedFetch } from '@/lib/api';
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
};

/**
 * 读请求 hook — 基于 useQuery + authedFetch。
 * path 为 null 时自动禁用查询。
 */
export function useApiQuery<TData = unknown>(
  path: string | null,
  options: UseApiQueryOptions<TData> = {},
) {
  const {
    queryKey: keyExtra = [],
    enabled = true,
    refetchInterval,
    staleTime,
    body,
    fetchOptions,
    placeholderData,
    parse,
  } = options;

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
      const resp = await authedFetch(path!, init);
      if (!resp.ok) {
        let msg = `HTTP ${resp.status} @ ${path}`;
        try {
          const b = await resp.json() as { error?: { message?: string }; traceId?: string };
          if (b?.error?.message) msg = `${b.error.message} @ ${path}`;
          if (b?.traceId) msg = `${msg} (traceId: ${b.traceId})`;
        } catch {}
        throw new Error(msg);
      }
      const envelope = (await resp.json()) as Envelope<TData>;
      const trace = envelope.traceId ? ` (traceId: ${envelope.traceId})` : '';
      const rawData = (envelope.data ?? null) as unknown;
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
    enabled: enabled && path != null,
    refetchInterval: refetchInterval as number | false | undefined,
    staleTime,
    placeholderData: placeholderData === 'keepPrevious' ? keepPreviousData : undefined,
  });

  return {
    data: query.data ?? null,
    isPending: query.isPending,
    isFetching: query.isFetching,
    error: query.error?.message ?? null,
    dataUpdatedAt: query.dataUpdatedAt,
    refetch: query.refetch,
  };
}
