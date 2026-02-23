/** A 股交易时段判断 */
export function isTradingHours(): boolean {
  const now = new Date();
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  const hhmm = now.getHours() * 100 + now.getMinutes();
  return (hhmm >= 925 && hhmm <= 1131) || (hhmm >= 1255 && hhmm <= 1501);
}

/** 返回 refetchInterval 函数：交易时段内按 ms 轮询，非交易时段停止 */
export function tradingInterval(ms: number) {
  return () => (isTradingHours() ? ms : false as const);
}
