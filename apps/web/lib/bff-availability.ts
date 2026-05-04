'use client';

import { useEffect, useSyncExternalStore } from 'react';

export type BffAvailabilityStatus = 'unknown' | 'checking' | 'online' | 'offline';

const PROBE_TIMEOUT_MS = 5000;
const OFFLINE_RETRY_COOLDOWN_MS = 30_000;
const OFFLINE_PROBE_INTERVAL_MS = 5_000;

let status: BffAvailabilityStatus = 'unknown';
let lastCheckedAt = 0;
let probePromise: Promise<boolean> | null = null;
const listeners = new Set<() => void>();

function isAbortLikeError(error: unknown) {
  if (error instanceof DOMException && error.name === 'AbortError') return true;
  return error instanceof Error && /abort(?:ed|error)|the user aborted a request|signal is aborted/i.test(error.message);
}

function emitChange() {
  listeners.forEach((listener) => listener());
}

function setStatus(next: BffAvailabilityStatus) {
  if (status === next) return;
  status = next;
  emitChange();
}

function withTimeout(signal?: AbortSignal) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);

  if (signal) {
    signal.addEventListener(
      'abort',
      () => {
        controller.abort();
      },
      { once: true },
    );
  }

  return {
    signal: controller.signal,
    cleanup() {
      window.clearTimeout(timer);
    },
  };
}

export function markBffAvailable() {
  lastCheckedAt = Date.now();
  setStatus('online');
}

export function markBffUnavailable() {
  lastCheckedAt = Date.now();
  setStatus('offline');
}

export function getBffAvailabilityStatus() {
  return status;
}

export async function ensureBffAvailability(options: { force?: boolean } = {}) {
  if (typeof window === 'undefined') return true;

  const { force = false } = options;
  const now = Date.now();

  if (!force) {
    if (status === 'online') return true;
    if (status === 'offline' && now - lastCheckedAt < OFFLINE_RETRY_COOLDOWN_MS) return false;
  }

  if (probePromise) return probePromise;

  const previousStatus = status;
  setStatus('checking');
  probePromise = (async () => {
    const { signal, cleanup } = withTimeout();
    try {
      const response = await fetch('/api/bff-availability', {
        method: 'GET',
        cache: 'no-store',
        signal,
      });
      const payload = (await response.json().catch(() => null)) as { reachable?: boolean } | null;

      if (payload?.reachable) {
        markBffAvailable();
        return true;
      }

      markBffUnavailable();
      return false;
    } catch (error) {
      if (isAbortLikeError(error)) {
        setStatus(previousStatus === 'checking' ? 'unknown' : previousStatus);
        return previousStatus === 'online';
      }
      markBffUnavailable();
      return false;
    } finally {
      cleanup();
      probePromise = null;
    }
  })();

  return probePromise;
}

export function useBffAvailability(options: { probeOnMount?: boolean } = {}) {
  const { probeOnMount = true } = options;
  const currentStatus = useSyncExternalStore(
    (onStoreChange) => {
      listeners.add(onStoreChange);
      return () => listeners.delete(onStoreChange);
    },
    () => status,
    () => 'unknown',
  );

  useEffect(() => {
    if (!probeOnMount) return;
    if (currentStatus === 'online' || currentStatus === 'checking') return;
    void ensureBffAvailability();
  }, [currentStatus, probeOnMount]);

  useEffect(() => {
    if (!probeOnMount) return;
    if (currentStatus !== 'offline') return;

    const timer = window.setTimeout(() => {
      void ensureBffAvailability({ force: true });
    }, OFFLINE_PROBE_INTERVAL_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [currentStatus, probeOnMount]);

  return {
    status: currentStatus,
    reachable: currentStatus === 'online',
    unavailable: currentStatus === 'offline',
    checking: currentStatus === 'unknown' || currentStatus === 'checking',
  };
}
