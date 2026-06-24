import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../services/api/core";
import type { ApiProblem } from "../types";

export interface ResourceState<T> {
  data: T | null;
  loading: boolean;
  error: ApiProblem | null;
  reload: () => Promise<void>;
}

function normalizeError(error: unknown): ApiProblem {
  if (error instanceof ApiError) return error.problem;
  if (error instanceof Error) return { status: 0, title: error.name, detail: error.message };
  return { status: 0, title: "Unknown error", detail: String(error) };
}

export function useAsyncResource<T>(loader: () => Promise<T>, deps: unknown[] = []): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiProblem | null>(null);
  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);

  const reload = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    if (mountedRef.current) {
      setLoading(true);
      setError(null);
    }
    try {
      const result = await loader();
      if (!mountedRef.current || requestId !== requestIdRef.current) return;
      setData(result);
    } catch (err) {
      if (!mountedRef.current || requestId !== requestIdRef.current) return;
      setError(normalizeError(err));
    } finally {
      if (mountedRef.current && requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    mountedRef.current = true;
    void reload();
    return () => {
      mountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, [reload]);

  return { data, loading, error, reload };
}
