'use client';

import { normalizeStrategyDetailResponse } from '@aiask/shared-types';
import type {
  IncubationOverviewResponse,
  FactoryRunDetailResponse,
  FactoryRunsResponse,
  FactoryStatusResponse,
  ReviewReportResponse,
  StrategyDetailResponse,
} from '../types';

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function assertRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error(`${label}返回结构异常（应为对象）`);
  }
  return value;
}

function assertRecordIfPresent(value: unknown, label: string) {
  if (value == null) return;
  if (!isRecord(value)) {
    throw new Error(`${label}返回结构异常（应为对象）`);
  }
}

function assertArrayIfPresent(value: unknown, label: string) {
  if (value == null) return;
  if (!Array.isArray(value)) {
    throw new Error(`${label}返回结构异常（应为数组）`);
  }
}

export function parseStrategyDetailResponse(raw: unknown): StrategyDetailResponse {
  const detail = normalizeStrategyDetailResponse(raw);
  assertArrayIfPresent(detail.metrics, '策略详情.metrics');
  assertArrayIfPresent(detail.reviews, '策略详情.reviews');
  assertArrayIfPresent(detail.nav_series, '策略详情.nav_series');
  assertRecordIfPresent(detail.view_model, '策略详情.view_model');
  return detail;
}

export function parseReviewReportResponse(raw: unknown): ReviewReportResponse {
  const report = assertRecord(raw, '策略评审报告');
  assertRecordIfPresent(report.summary, '策略评审报告.summary');
  assertRecordIfPresent(report.evidence_alignment_audit, '策略评审报告.evidence_alignment_audit');
  assertArrayIfPresent(report.reports, '策略评审报告.reports');
  return report as ReviewReportResponse;
}

export function parseIncubationOverviewResponse(raw: unknown): IncubationOverviewResponse {
  const overview = assertRecord(raw, '策略孵化概览');
  assertRecordIfPresent(overview.signal_quality, '策略孵化概览.signal_quality');
  assertRecordIfPresent(overview.signal_quality_snapshot, '策略孵化概览.signal_quality_snapshot');
  assertRecordIfPresent(overview.execution_quality, '策略孵化概览.execution_quality');
  assertRecordIfPresent(overview.execution_quality_snapshot, '策略孵化概览.execution_quality_snapshot');
  assertRecordIfPresent(overview.execution_diagnostics, '策略孵化概览.execution_diagnostics');
  assertRecordIfPresent(overview.prediction_trace_ledger, '策略孵化概览.prediction_trace_ledger');
  assertRecordIfPresent(overview.runtime_playbook_provenance, '策略孵化概览.runtime_playbook_provenance');
  assertRecordIfPresent(overview.semantic_lineage, '策略孵化概览.semantic_lineage');
  assertRecordIfPresent(overview.execution_lineage, '策略孵化概览.execution_lineage');
  assertRecordIfPresent(overview.hard_gate_result, '策略孵化概览.hard_gate_result');
  return overview as IncubationOverviewResponse;
}

export function parseFactoryStatusResponse(raw: unknown): FactoryStatusResponse {
  const status = assertRecord(raw, '策略工厂状态');
  assertRecordIfPresent(status.last_summary, '策略工厂状态.last_summary');
  assertRecordIfPresent(status.feature_flags, '策略工厂状态.feature_flags');
  assertRecordIfPresent(status.quality_baseline, '策略工厂状态.quality_baseline');
  assertRecordIfPresent(status.signal_quality_registry, '策略工厂状态.signal_quality_registry');
  assertRecordIfPresent(status.research_window, '策略工厂状态.research_window');
  assertRecordIfPresent(status.full_market_topn, '策略工厂状态.full_market_topn');
  return status as FactoryStatusResponse;
}

export function parseFactoryRunsResponse(raw: unknown): FactoryRunsResponse {
  const runs = assertRecord(raw, '策略工厂运行列表');
  assertArrayIfPresent(runs.items, '策略工厂运行列表.items');
  if (runs.latest != null && !isRecord(runs.latest)) {
    throw new Error('策略工厂运行列表.latest返回结构异常（应为对象或 null）');
  }
  return runs as FactoryRunsResponse;
}

export function parseFactoryRunDetailResponse(raw: unknown): FactoryRunDetailResponse {
  const detail = assertRecord(raw, '策略工厂运行详情');
  assertRecordIfPresent(detail.summary, '策略工厂运行详情.summary');
  assertRecordIfPresent(detail.stages, '策略工厂运行详情.stages');
  assertRecordIfPresent(detail.pipeline, '策略工厂运行详情.pipeline');
  assertRecordIfPresent(detail.feedback_summary, '策略工厂运行详情.feedback_summary');
  assertRecordIfPresent(detail.research_window, '策略工厂运行详情.research_window');
  assertRecordIfPresent(detail.full_market_topn, '策略工厂运行详情.full_market_topn');
  return detail as FactoryRunDetailResponse;
}
