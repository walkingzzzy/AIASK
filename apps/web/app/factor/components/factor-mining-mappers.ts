import { extractObject } from '@/lib/data-utils';

export function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

export function splitCodes(raw: string) {
  return raw
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseOptionalInt(raw: string) {
  if (!raw.trim()) return undefined;
  const value = Number(raw);
  return Number.isFinite(value) ? Math.trunc(value) : undefined;
}

export function joinList(value: unknown) {
  if (Array.isArray(value))
    return value
      .map((item) => String(item))
      .filter(Boolean)
      .join(', ');
  if (value == null) return '-';
  return String(value);
}

export function countRows(value: unknown, keyLabel: string) {
  if (!isRecord(value)) return [];
  return Object.entries(value)
    .map(([key, count]) => ({
      [keyLabel]: key,
      count: Number(count ?? 0),
    }))
    .sort((left, right) => Number(right.count ?? 0) - Number(left.count ?? 0));
}

export function readArtifactId(payload: unknown) {
  const root = extractObject(payload);
  const summary = isRecord(root.summary) ? root.summary : {};
  const generation = isRecord(root.generation) ? root.generation : {};
  const validation = isRecord(root.validation) ? root.validation : {};
  const value = root.artifact_id ?? summary.artifact_id ?? generation.artifact_id ?? validation.artifact_id;
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

export function mcpError(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  if (payload.success === false && payload.error) return String(payload.error);
  if (Array.isArray(payload.steps)) {
    const failedStep = payload.steps.find((step) => isRecord(step) && step.success === false);
    if (isRecord(failedStep)) {
      const output = isRecord(failedStep.output) ? failedStep.output : {};
      if (output.error) return String(output.error);
      if (output.message) return String(output.message);
      return `${String(failedStep.step ?? 'workflow')} 执行失败`;
    }
  }
  if (isRecord(payload.data)) return mcpError(payload.data);
  return null;
}

export function flattenMemoryRows(rows: Array<Record<string, unknown>>) {
  return rows.map((row) => {
    const candidate = isRecord(row.candidate) ? row.candidate : {};
    const rating = isRecord(row.rating) ? row.rating : {};
    return {
      artifact_id: row.artifact_id,
      status: row.status,
      name: candidate.name,
      family: candidate.family,
      expression_dsl: candidate.expression_dsl ?? candidate.expression,
      grade: rating.grade,
      recommendation: rating.recommendation,
      total_score: rating.total_score,
      tags: joinList(row.tags),
    };
  });
}

export function flattenRegistryRows(rows: Array<Record<string, unknown>>) {
  return rows.map((row) => {
    const candidate = isRecord(row.candidate) ? row.candidate : {};
    const rating = isRecord(row.rating) ? row.rating : {};
    return {
      artifact_id: row.artifact_id,
      name: candidate.name,
      family: candidate.family,
      grade: rating.grade,
      recommendation: rating.recommendation,
      total_score: rating.total_score,
      codes: joinList(row.codes),
      updated_at: row.updated_at ?? row.created_at,
    };
  });
}

export function flattenReplayRows(rows: Array<Record<string, unknown>>) {
  return rows.map((row) => ({
    artifact_id: row.artifact_id,
    source_artifact_id: row.source_artifact_id,
    validated_count: row.validated_count,
    failed_count: row.failed_count,
    candidate_limit: row.candidate_limit,
    codes: joinList(row.codes),
    created_at: row.created_at,
  }));
}
