'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
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
  const { code: globalCode, setStock } = useStockContext();

  // 初始值优先级：URL > 全局上下文 > initial
  const urlCode = searchParams.get('code') || '';
  const resolvedInitial = urlCode || globalCode || initial;

  const [code, setCodeLocal] = useState(resolvedInitial);
  const [codeError, setCodeError] = useState<string | null>(null);
  // resolvedCode: 仅当代码来自 URL 或 Store（非页面默认值）时有值，供页面自动查询使用
  const [resolvedCode, setResolvedCode] = useState<string | null>(null);
  const initialized = useRef(false);

  // 首次挂载：单向同步 URL → 全局上下文
  // 注意：只允许 URL code 触发自动查询（resolvedCode）和 URL 同步。
  // 若 URL 无 code 但全局上下文有 code，仅预填输入框，不自动触发查询，
  // 也不修改 URL，避免行情/个股详情等页面相互污染全局 code 状态。
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (urlCode && STOCK_CODE_RE.test(urlCode)) {
      // URL 有 code → 同步到 store，并标记 resolvedCode 供页面自动查询
      setCodeLocal(urlCode);
      setStock(urlCode);
      setResolvedCode(urlCode);
    } else if (globalCode && STOCK_CODE_RE.test(globalCode)) {
      // store 有 code 但 URL 没有 → 预填输入框 + 触发自动查询（恢复跨页连续体验）
      // 注意：只设 resolvedCode（自动查询），不调用 router.replace（不改 URL）
      // 这样避免了 URL 被污染导致的页面跳转 bug，同时保留了"延续上次浏览"的体验
      setCodeLocal(globalCode);
      setResolvedCode(globalCode);
      // 不调用 router.replace，URL 保持干净
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setCode = useCallback((value: string) => {
    setCodeLocal(value);
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
