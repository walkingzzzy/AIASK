'use client';

import { useMemo } from 'react';

type FreshnessLevel = 'fresh' | 'stale' | 'old' | 'unknown';

export type FreshnessTagProps = {
  /** 数据更新时间（ISO 字符串 或 Date 或 Unix 毫秒戳） */
  updatedAt?: string | Date | number | null;
  /** 自定义标签文本（不传则自动根据时间计算） */
  label?: string;
  /** 强制指定新鲜度等级（不传则自动推算） */
  level?: FreshnessLevel;
  /** 数据来源说明（hover 显示） */
  source?: string;
  className?: string;
};

function toMs(v: string | Date | number): number {
  if (typeof v === 'number') return v;
  if (v instanceof Date) return v.getTime();
  return new Date(v).getTime();
}

function inferLevel(ms: number): FreshnessLevel {
  const age = Date.now() - ms;
  if (age < 5 * 60_000) return 'fresh';       // < 5 min
  if (age < 60 * 60_000) return 'stale';      // < 1 h
  if (age < 24 * 60 * 60_000) return 'old';   // < 24 h
  return 'unknown';
}

function formatAge(ms: number): string {
  const age = Date.now() - ms;
  if (age < 60_000) return '刚刚';
  if (age < 60 * 60_000) return `${Math.floor(age / 60_000)} 分钟前`;
  if (age < 24 * 60 * 60_000) return `${Math.floor(age / 3_600_000)} 小时前`;
  return `${Math.floor(age / 86_400_000)} 天前`;
}

const LEVEL_STYLES: Record<FreshnessLevel, string> = {
  fresh: 'bg-green-500/15 text-green-400 border-green-500/30',
  stale: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  old: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  unknown: 'bg-surface-alt text-text-secondary border-border',
};

const LEVEL_DOTS: Record<FreshnessLevel, string> = {
  fresh: 'bg-green-400',
  stale: 'bg-yellow-400',
  old: 'bg-orange-400',
  unknown: 'bg-text-secondary',
};

/**
 * FreshnessTag — 数据新鲜度标识
 *
 * 根据 updatedAt 自动推算数据陈旧程度，
 * 支持 fresh / stale / old / unknown 四级语义。
 *
 * ```tsx
 * <FreshnessTag updatedAt="2026-03-24T10:00:00Z" source="AkShare 行情" />
 * ```
 */
export function FreshnessTag({
  updatedAt,
  label,
  level: levelProp,
  source,
  className = '',
}: FreshnessTagProps) {
  const { level, displayLabel } = useMemo(() => {
    if (levelProp) {
      return { level: levelProp, displayLabel: label ?? levelProp };
    }
    if (!updatedAt) {
      return { level: 'unknown' as FreshnessLevel, displayLabel: label ?? '数据时间未知' };
    }
    const ms = toMs(updatedAt);
    if (Number.isNaN(ms)) {
      return { level: 'unknown' as FreshnessLevel, displayLabel: label ?? '时间格式错误' };
    }
    const lvl = inferLevel(ms);
    return { level: lvl, displayLabel: label ?? formatAge(ms) };
  }, [updatedAt, label, levelProp]);

  const title = source
    ? `数据来源：${source}${updatedAt ? `，更新于 ${typeof updatedAt === 'string' ? updatedAt : new Date(updatedAt).toLocaleString('zh-CN')}` : ''}`
    : updatedAt
    ? `更新于 ${typeof updatedAt === 'string' ? updatedAt : new Date(updatedAt).toLocaleString('zh-CN')}`
    : undefined;

  return (
    <span
      className={[
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium',
        LEVEL_STYLES[level],
        className,
      ].join(' ')}
      title={title}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${LEVEL_DOTS[level]}`} aria-hidden="true" />
      {displayLabel}
    </span>
  );
}
