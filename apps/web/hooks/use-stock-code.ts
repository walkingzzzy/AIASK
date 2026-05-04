'use client';

import { useState, useCallback, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useHydrated } from '@/hooks/use-hydrated';
import { useStablePathname } from '@/hooks/use-stable-pathname';
import { useStableSearchParams } from '@/hooks/use-stable-search-params';
import { fetchUserDefaultContext, saveUserDefaultContext, type UserDefaultContext } from '@/lib/user-default-context';
import { normalizeStockCode, STOCK_CODE_RE, trustedUserStockCode } from '@/lib/stock-code-utils';
import { useStockContext } from '@/store/stock-context';
import { selectActiveWorkspace, useWorkbenchStore } from '@/store/workbench-store';

/**
 * 增强版股票代码 hook — 支持 URL query param 同步 + 全局上下文
 *
 * 优先级：URL ?code= > 已确认工作区上下文 > 用户默认上下文 > initial 参数
 *
 * @param initial  默认代码（仅在 URL、工作区和用户默认上下文都为空时使用）
 * @param syncUrl  是否同步到 URL query param（默认 true）
 */
export function useStockCode(initial = '', syncUrl = true) {
  const searchParams = useStableSearchParams();
  const router = useRouter();
  const pathname = useStablePathname();
  const hydrated = useHydrated();
  const { setStock } = useStockContext();
  const workbenchHydrated = useWorkbenchStore((state) => state.hydrated);
  const activeWorkspaceId = useWorkbenchStore((state) => state.activeWorkspaceId);
  const workspaces = useWorkbenchStore((state) => state.workspaces);
  const updateWorkspaceContext = useWorkbenchStore((state) => state.updateContext);
  const [remoteContext, setRemoteContext] = useState<UserDefaultContext | null>(null);
  const urlCode = searchParams.get('code') || '';
  const normalizedUrlCode = normalizeStockCode(urlCode);
  const activeWorkspace = useMemo(
    () => selectActiveWorkspace({ activeWorkspaceId, workspaces }),
    [activeWorkspaceId, workspaces],
  );
  const workspaceCode = workbenchHydrated
    ? trustedUserStockCode(activeWorkspace.context.stockCode, activeWorkspace.context.stockConfirmedAt)
    : '';
  const remoteCode = hydrated ? normalizeStockCode(remoteContext?.trustedStockCode ?? remoteContext?.stockCode) : '';
  const normalizedInitial = trustedUserStockCode(initial);
  const resolvedCode = normalizedUrlCode || workspaceCode || remoteCode || normalizedInitial || null;
  const resolvedInitial = resolvedCode || '';

  const [draftCode, setDraftCode] = useState<string | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const code = draftCode ?? resolvedInitial;

  useEffect(() => {
    if (!hydrated) return;
    let alive = true;
    fetchUserDefaultContext().then((context) => {
      if (alive) setRemoteContext(context);
    });
    return () => {
      alive = false;
    };
  }, [hydrated]);

  const setCode = useCallback((value: string) => {
    const nextValue = value.trim();
    setDraftCode((current) => (current === nextValue ? current : nextValue));
  }, []);

  // 写入 URL（在查询提交时调用，不在每次输入时调用）
  const syncToUrl = useCallback((c: string) => {
    if (!syncUrl) return;
    const trimmed = c.trim();
    if (!trimmed) return;
    const params = new URLSearchParams(searchParams.toString());
    if (params.get('code') === trimmed) return;
    params.set('code', trimmed);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }, [syncUrl, searchParams, router, pathname]);

  const validate = useCallback(
    (value?: string): boolean => {
      const v = (value ?? code).trim();
      if (!STOCK_CODE_RE.test(v)) {
        setCodeError('股票代码必须为 6 位数字');
        return false;
      }
      setCodeError(null);
      // 验证通过时同步到全局上下文和 URL
      syncToUrl(v);
      setStock(v);
      const stockConfirmedAt = new Date().toISOString();
      updateWorkspaceContext({ stockCode: v, stockConfirmedAt });
      void saveUserDefaultContext({ stockCode: v, workspaceId: activeWorkspace.id });
      return true;
    },
    [activeWorkspace.id, code, setStock, syncToUrl, updateWorkspaceContext],
  );

  return { code, setCode, codeError, setCodeError, validate, trimmedCode: code.trim(), resolvedCode };
}
