'use client';

export function qualityBadgeVariant(
  value: unknown,
): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'strong' || normalized === 'comparable_ready' || normalized === 'passed') return 'success';
  if (normalized === 'candidate') return 'info';
  if (normalized === 'mixed' || normalized === 'diagnostic_ready') return 'info';
  if (normalized === 'insufficient_evidence' || normalized === 'insufficient') return 'warning';
  if (normalized === 'weak' || normalized === 'missing') return 'danger';
  return 'neutral';
}

export function qualityLabelText(value: unknown) {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'strong') return '强';
  if (normalized === 'mixed') return '混合';
  if (normalized === 'weak') return '弱';
  if (normalized === 'insufficient_evidence') return '证据不足';
  if (normalized === 'missing') return '缺失';
  if (normalized === 'insufficient') return '样本不足';
  if (normalized === 'candidate') return '候选';
  if (normalized === 'passed') return '通过';
  if (normalized === 'diagnostic_ready') return '诊断可用';
  if (normalized === 'comparable_ready') return '可比较';
  return normalized || '-';
}
