'use client';

import { normalizeFactoryMarketViewResponse, normalizeStrategyDetailResponse } from '@aiask/shared-types';
import type {
  FactoryMarketViewResponse,
  IncubationOverviewResponse,
  FactoryRunDetailResponse,
  FactoryRunsResponse,
  FactoryStatusResponse,
  ReviewReportResponse,
  StrategyCoreChainAcceptanceResponse,
  StrategyDetailResponse,
  StrategyRuntimeActionContract,
  StrategyPaperContextResponse,
  StrategyCapabilityDiagnosticsResponse,
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
  if (detail.runtime_action_contract != null) {
    parseStrategyRuntimeActionContract(detail.runtime_action_contract);
  }
  return detail;
}

export function parseStrategyRuntimeActionContract(raw: unknown): StrategyRuntimeActionContract {
  const contract = assertRecord(raw, '策略运行时动作合同');
  assertArrayIfPresent(contract.actions, '策略运行时动作合同.actions');
  assertArrayIfPresent(contract.default_order, '策略运行时动作合同.default_order');
  assertRecordIfPresent(contract.actor, '策略运行时动作合同.actor');
  assertRecordIfPresent(contract.state, '策略运行时动作合同.state');
  assertRecordIfPresent(contract.summary, '策略运行时动作合同.summary');
  return contract as StrategyRuntimeActionContract;
}

export function parseStrategyPaperContextResponse(raw: unknown): StrategyPaperContextResponse {
  const context = assertRecord(raw, '策略模拟盘上下文');
  assertRecordIfPresent(context.personal, '策略模拟盘上下文.personal');
  assertRecordIfPresent(context.incubation, '策略模拟盘上下文.incubation');
  return context as StrategyPaperContextResponse;
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

export function parseFactoryMarketViewResponse(raw: unknown): FactoryMarketViewResponse {
  const view = normalizeFactoryMarketViewResponse(raw);
  assertRecordIfPresent(view.capabilities, '策略超市工厂视图.capabilities');
  if (view.status != null) {
    parseFactoryStatusResponse(view.status);
  }
  if (view.runs != null) {
    parseFactoryRunsResponse(view.runs);
  }
  if (view.expanded_run != null) {
    parseFactoryRunDetailResponse(view.expanded_run);
  }
  assertRecordIfPresent(view.observability, '策略超市工厂视图.observability');
  assertArrayIfPresent(view.errors, '策略超市工厂视图.errors');
  assertRecordIfPresent(view.section_errors, '策略超市工厂视图.section_errors');
  assertRecordIfPresent(view.surface, '策略超市工厂视图.surface');
  assertArrayIfPresent(view.surface?.overview_cards, '策略超市工厂视图.surface.overview_cards');
  assertArrayIfPresent(view.surface?.hero_cards, '策略超市工厂视图.surface.hero_cards');
  assertArrayIfPresent(view.surface?.observability_cards, '策略超市工厂视图.surface.observability_cards');
  assertArrayIfPresent(view.surface?.visible_outputs, '策略超市工厂视图.surface.visible_outputs');
  return view;
}

export function parseStrategyCapabilityDiagnosticsResponse(raw: unknown): StrategyCapabilityDiagnosticsResponse {
  const diagnostics = assertRecord(raw, '策略能力缺口诊断');
  assertRecordIfPresent(diagnostics.summary, '策略能力缺口诊断.summary');
  assertArrayIfPresent(diagnostics.items, '策略能力缺口诊断.items');
  assertArrayIfPresent(diagnostics.critical_unmatched, '策略能力缺口诊断.critical_unmatched');
  return diagnostics as StrategyCapabilityDiagnosticsResponse;
}

export function parseCoreChainAcceptanceResponse(raw: unknown): StrategyCoreChainAcceptanceResponse {
  const payload = assertRecord(raw, '核心链路诊断');
  assertRecordIfPresent(payload.actor, '核心链路诊断.actor');
  assertRecordIfPresent(payload.environment, '核心链路诊断.environment');
  assertRecordIfPresent(payload.target, '核心链路诊断.target');
  assertRecordIfPresent(payload.summary, '核心链路诊断.summary');
  assertArrayIfPresent(payload.steps, '核心链路诊断.steps');
  return payload as StrategyCoreChainAcceptanceResponse;
}
