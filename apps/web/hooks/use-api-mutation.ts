'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { authedFetch } from '@/lib/api';
import type { Envelope } from '@aiask/shared-types';

type FetchOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  headers?: Record<string, string>;
};

/**
 * Wraps authedFetch + React Query useMutation.
 * Replaces the manual try/catch/finally + useState loading/error/data pattern.
 *
 * Usage:
 *   const { trigger, data, isPending, error, reset } = useApiMutation<ResponseType>();
 *   trigger('/market/quote?code=600519');
 *   trigger('/factor/calculate', { method: 'POST' }, { factor_name: 'momentum', stock_codes: ['600519'] });
 */
export function useApiMutation<TData = unknown>() {
  const [data, setData] = useState<TData | null>(null);

  const mutation = useMutation<TData, Error, { path: string; options?: FetchOptions; body?: unknown }>({
    mutationFn: async ({ path, options, body }) => {
      const method = options?.method ?? (body ? 'POST' : 'GET');
      const init: RequestInit = { method };
      if (body) {
        init.headers = { 'content-type': 'application/json', ...options?.headers };
        init.body = JSON.stringify(body);
      } else if (options?.headers) {
        init.headers = options.headers;
      }
      const resp = await authedFetch(path, init);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const envelope = (await resp.json()) as Envelope<TData>;
      return (envelope.data ?? null) as TData;
    },
    onSuccess: (result) => setData(result),
  });

  function trigger(path: string, options?: FetchOptions, body?: unknown) {
    mutation.mutate({ path, options, body });
  }

  function triggerAsync(path: string, options?: FetchOptions, body?: unknown) {
    return mutation.mutateAsync({ path, options, body });
  }

  function reset() {
    setData(null);
    mutation.reset();
  }

  return {
    trigger,
    triggerAsync,
    data,
    isPending: mutation.isPending,
    error: mutation.error?.message ?? null,
    reset,
  };
}
