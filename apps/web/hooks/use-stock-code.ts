'use client';

import { useState, useCallback } from 'react';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { useHydrated } from '@/hooks/use-hydrated';
import { useStockContext } from '@/store/stock-context';

const STOCK_CODE_RE = /^\d{6}$/;

/**
 * 增强版股票代码 hook — 支持 URL query param 同步 + 全局上下文
 *
 * 优先级：URL ?code= > 全局上下文 > initial 参数
 *
 * @param initial  默认代码（仅在 URL 和全局上下文都为空时使用）
 * @param syncUrl  是否同步到 URL query param（默认 true）
 */
export function useStockCode(initial = '', syncUrl = true) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const hydrated = useHydrated();
  const { code: globalCode, setStock } = useStockContext();
  const urlCode = searchParams.get('code') || '';
  const normalizedUrlCode = STOCK_CODE_RE.test(urlCode) ? urlCode : '';
  const normalizedGlobalCode = STOCK_CODE_RE.test(globalCode) ? globalCode : '';
  const resolvedCode = normalizedUrlCode || (hydrated ? normalizedGlobalCode : '') || null;
  const resolvedInitial = resolvedCode || initial;

  const [draftCode, setDraftCode] = useState<string | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const code = draftCode ?? resolvedInitial;

  const setCode = useCallback((value: string) => {
    setDraftCode(value);
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
      return true;
    },
    [code, syncToUrl, setStock],
  );

  return { code, setCode, codeError, setCodeError, validate, trimmedCode: code.trim(), resolvedCode };
}
