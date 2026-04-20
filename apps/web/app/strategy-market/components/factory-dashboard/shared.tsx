'use client';

import { Badge } from '@/components/ui';

import { formatArtifactValue, isObjectRecord } from './formatters';

export function FactoryPreviewSection({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded border border-border bg-surface-alt px-3 py-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">{title}</div>
        {typeof count === 'number' && <Badge variant="neutral">{count} 条</Badge>}
      </div>
      {children}
    </div>
  );
}

export function FactoryArtifactCard({
  title,
  artifact,
  fields,
}: {
  title: string;
  artifact: Record<string, unknown>;
  fields: Array<{ key: string; label: string }>;
}) {
  if (!isObjectRecord(artifact) || !artifact.available) return null;

  return (
    <div className="rounded border border-border bg-surface px-3 py-3 space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs font-medium text-text-primary">{title}</div>
        <Badge variant="success">已观测</Badge>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs text-text-secondary">
        <div>契约版本：{formatArtifactValue(artifact.contract_version)}</div>
        {fields.map((field) => (
          <div key={field.key}>
            {field.label}：{formatArtifactValue(artifact[field.key])}
          </div>
        ))}
      </div>
    </div>
  );
}
