export function recordFromUnknown(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function arrayFromUnknown(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
    if (value !== null && value !== undefined && typeof value !== "object") return String(value);
  }
  return "-";
}

export function numberFromUnknown(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatMoney(value: unknown): string {
  const parsed = numberFromUnknown(value);
  if (parsed === null) return "-";
  return parsed.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

export function formatPercent(value: unknown): string {
  const parsed = numberFromUnknown(value);
  if (parsed === null) return "-";
  return `${(parsed * 100).toFixed(1)}%`;
}
