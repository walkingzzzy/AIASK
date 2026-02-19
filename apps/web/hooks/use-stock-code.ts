'use client';

import { useState, useCallback } from 'react';

const STOCK_CODE_RE = /^\d{6}$/;

export function useStockCode(initial = '600519') {
  const [code, setCode] = useState(initial);
  const [codeError, setCodeError] = useState<string | null>(null);

  const validate = useCallback(
    (value?: string): boolean => {
      const v = (value ?? code).trim();
      if (!STOCK_CODE_RE.test(v)) {
        setCodeError('股票代码必须为 6 位数字');
        return false;
      }
      setCodeError(null);
      return true;
    },
    [code],
  );

  return { code, setCode, codeError, setCodeError, validate, trimmedCode: code.trim() };
}
