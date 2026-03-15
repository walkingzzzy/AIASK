'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { authedFetch, extractApiErrorMessage, unwrapApiEnvelope } from '@/lib/api';
import { useToast } from '@/components/ui/toast';
import type { Envelope } from '@aiask/shared-types';

type FetchOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  headers?: Record<string, string>;
};

type UseApiMutationOptions<TData> = {
  /** 成功后自动 invalidate 的 query key 列表 */
  invalidates?: readonly (readonly unknown[] | unknown[])[];
  /** 成功回调 */
  onSuccess?: (data: TData) => void;
  /** 成功时 toast 文案（传 false 禁用） */
  successToast?: string | false;
  /** 失败时自动 toast（默认 true） */
  errorToast?: boolean;
  /** 可选数据解析器：用于运行时 schema 校验/结构转换 */
  parse?: (raw: unknown) => TData;
};

/**
 * 写操作 hook — 基于 useMutation + authedFetch。
 * 读请求请使用 useApiQuery。
 */
export function useApiMutation<TData = unknown>(options: UseApiMutationOptions<TData> = {}) {
  const qc = useQueryClient();
  const { toast } = useToast();

  const mutation = useMutation<TData, Error, { path: string; options?: FetchOptions; body?: unknown }>({
    mutationFn: async ({ path, options: fetchOpts, body }) => {
      const method = fetchOpts?.method ?? (body ? 'POST' : 'GET');
      const init: RequestInit = { method };
      if (body) {
        init.headers = { 'content-type': 'application/json', ...fetchOpts?.headers };
        init.body = JSON.stringify(body);
      } else if (fetchOpts?.headers) {
        init.headers = fetchOpts.headers;
      }
      const resp = await authedFetch(path, init);
      const bodyPayload = await resp.json().catch(() => null);
      if (!resp.ok) {
        let msg = `HTTP ${resp.status} @ ${path}`;
        const detail = extractApiErrorMessage(bodyPayload, msg);
        if (detail !== msg) msg = `${detail} @ ${path}`;
        const traceId = bodyPayload && typeof bodyPayload === 'object' && typeof (bodyPayload as { traceId?: unknown }).traceId === 'string'
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
      if (options.parse) {
        try {
          return options.parse(rawData);
        } catch (err) {
          const detail = err instanceof Error ? err.message : String(err);
          throw new Error(`数据结构异常: ${detail} @ ${path}${trace}`);
        }
      }
      return rawData as TData;
    },
    onSuccess: (result) => {
      if (options.invalidates) {
        options.invalidates.forEach((key) => qc.invalidateQueries({ queryKey: [...key] }));
      }
      if (options.successToast) toast(options.successToast, 'success');
      options.onSuccess?.(result);
    },
    onError: (err) => {
      if (options.errorToast !== false) toast(err.message || '操作失败', 'error');
    },
  });

  function trigger(path: string, fetchOpts?: FetchOptions, body?: unknown) {
    mutation.mutate({ path, options: fetchOpts, body });
  }

  function triggerAsync(path: string, fetchOpts?: FetchOptions, body?: unknown) {
    return mutation.mutateAsync({ path, options: fetchOpts, body });
  }

  function reset() {
    mutation.reset();
  }

  return {
    trigger,
    triggerAsync,
    data: mutation.data ?? null,
    isPending: mutation.isPending,
    error: mutation.error?.message ?? null,
    reset,
  };
}
