'use client';

import { authedFetch } from '@/lib/api';
import { hasLoggedInHint } from '@/lib/auth';

export type BehaviorEventDraft = {
  pageKey: string;
  route: string;
  eventType: string;
  targetType?: string;
  targetLabel?: string;
  targetId?: string;
  targetTestId?: string;
  payload?: Record<string, unknown>;
  source?: string;
  occurredAt?: string;
};

const SESSION_STORAGE_KEY = 'aiask.behavior.session-id';
const FLUSH_INTERVAL_MS = 4_000;
const MAX_BATCH_SIZE = 50;

let queue: BehaviorEventDraft[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let inFlightFlush: Promise<void> | null = null;

function randomId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export function ensureBehaviorSessionId() {
  if (typeof window === 'undefined') return 'server-session';
  const stored = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (stored) return stored;
  const next = randomId();
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, next);
  return next;
}

export function resolveBehaviorPageKey(pathname: string) {
  if (pathname === '/') return 'home';
  if (/^\/strategy-market\/[^/]+/.test(pathname)) return 'strategy-detail';
  return pathname.split('/').filter(Boolean).join('.') || 'unknown';
}

export function describeActionableElement(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return null;
  const element = target.closest<HTMLElement>('button, a, [role="button"], [role="tab"], [data-testid], [data-action-testid]');
  if (!element) return null;

  const tagName = element.tagName.toLowerCase();
  const role = element.getAttribute('role');
  const targetType = role || tagName;
  const targetLabel = (
    element.getAttribute('aria-label')
    || element.getAttribute('title')
    || element.textContent
    || ''
  ).replace(/\s+/g, ' ').trim().slice(0, 120);
  const targetId = element.id || element.getAttribute('name') || undefined;
  const targetTestId = element.getAttribute('data-action-testid') || element.getAttribute('data-testid') || undefined;

  const payload: Record<string, unknown> = {};
  if (tagName === 'a') {
    payload.href = (element as HTMLAnchorElement).href;
  }
  if (role === 'tab') {
    payload.selected = element.getAttribute('aria-selected') === 'true';
  }

  return {
    eventType: role === 'tab' ? 'tab_switch' : tagName === 'a' ? 'link_click' : 'button_click',
    targetType,
    targetLabel: targetLabel || undefined,
    targetId,
    targetTestId,
    payload,
  };
}

export function trackBehaviorEvent(event: BehaviorEventDraft) {
  if (typeof window === 'undefined') return;
  if (!hasLoggedInHint()) return;
  queue.push({
    ...event,
    source: event.source || 'web',
    occurredAt: event.occurredAt || new Date().toISOString(),
  });

  if (queue.length >= MAX_BATCH_SIZE) {
    void flushBehaviorEvents();
    return;
  }

  if (!flushTimer) {
    flushTimer = setTimeout(() => {
      flushTimer = null;
      void flushBehaviorEvents();
    }, FLUSH_INTERVAL_MS);
  }
}

export async function flushBehaviorEvents() {
  if (typeof window === 'undefined') return;
  if (!hasLoggedInHint()) {
    queue = [];
    return;
  }
  if (inFlightFlush) return inFlightFlush;
  if (!queue.length) return;

  const sessionId = ensureBehaviorSessionId();
  const batch = queue.splice(0, MAX_BATCH_SIZE);
  if (!batch.length) return;

  inFlightFlush = authedFetch('/behavior/events', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ sessionId, events: batch }),
  }, { redirectOnUnauthorized: false })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`behavior flush failed: ${response.status}`);
      }
      await response.json().catch(() => null);
    })
    .catch(() => {
      queue = [...batch, ...queue].slice(-200);
    })
    .finally(() => {
      inFlightFlush = null;
    });

  return inFlightFlush;
}
