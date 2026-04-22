import { HttpException, HttpStatus, ServiceUnavailableException } from '@nestjs/common';
import type { AcceptanceStatus } from '@aiask/shared-types';

function normalizeDetail(detail: unknown) {
  if (detail == null) return null;
  if (typeof detail === 'object') return detail;
  return { message: String(detail) };
}

export function buildUnavailableException(
  detail: unknown,
  options: {
    code?: string;
    message?: string;
    traceId?: string | null;
  } = {},
) {
  const payload: Record<string, unknown> = {
    code: options.code ?? 'UPSTREAM_UNAVAILABLE',
    message: options.message ?? '上游能力暂不可用',
    acceptanceStatus: 'unavailable' satisfies AcceptanceStatus,
    detail: normalizeDetail(detail),
  };
  if (options.traceId) {
    payload.traceId = options.traceId;
  }
  return new ServiceUnavailableException(payload);
}

export function buildPrerequisiteMissingException(
  message: string,
  detail?: unknown,
  options: {
    code?: string;
    traceId?: string | null;
  } = {},
) {
  const payload: Record<string, unknown> = {
    code: options.code ?? 'PREREQUISITE_MISSING',
    message,
    acceptanceStatus: 'prerequisite_missing' satisfies AcceptanceStatus,
    detail: normalizeDetail(detail),
  };
  if (options.traceId) {
    payload.traceId = options.traceId;
  }
  return new HttpException(payload, HttpStatus.PRECONDITION_FAILED);
}
