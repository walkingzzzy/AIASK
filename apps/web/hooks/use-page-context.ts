'use client';

import { useEffect, useRef } from 'react';
import type { CopilotPageContext } from '@/lib/copilot-types';
import { useCopilotStore } from '@/store/copilot-store';

type PageContextInput = Omit<CopilotPageContext, 'updatedAt'>;

function buildContextSignature(context: PageContextInput) {
  return JSON.stringify({
    pageKey: context.pageKey,
    title: context.title,
    summary: context.summary ?? null,
    stockCode: context.stockCode ?? null,
    tags: context.tags ?? [],
    suggestions: context.suggestions ?? [],
    raw: context.raw ?? null,
  });
}

export function usePageContext(context: PageContextInput) {
  const setPageContext = useCopilotStore((state) => state.setPageContext);
  const clearPageContext = useCopilotStore((state) => state.clearPageContext);
  const signature = buildContextSignature(context);
  const latestContextRef = useRef(context);
  const pageKey = context.pageKey;

  useEffect(() => {
    latestContextRef.current = context;
  }, [context, signature]);

  useEffect(() => {
    const writeTimer = window.setTimeout(() => {
      setPageContext({
        ...latestContextRef.current,
        updatedAt: Date.now(),
      });
    }, 0);

    return () => {
      window.clearTimeout(writeTimer);
      window.setTimeout(() => {
        clearPageContext(pageKey);
      }, 0);
    };
  }, [clearPageContext, pageKey, setPageContext, signature]);
}
