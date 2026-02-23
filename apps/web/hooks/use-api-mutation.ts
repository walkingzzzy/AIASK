'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { authedFetch } from '@/lib/api';
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
      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try { const b = await resp.json(); if (b?.error?.message) msg = b.error.message; } catch {}
        throw new Error(msg);
      }
      const envelope = (await resp.json()) as Envelope<TData>;
      return (envelope.data ?? null) as TData;
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
