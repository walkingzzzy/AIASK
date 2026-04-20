import { IsArray, IsBoolean, IsInt, IsOptional, IsString, Max, Min } from 'class-validator';
import { Type, Transform } from 'class-transformer';

export class ListDto {
  @IsOptional() @IsString() status?: string;
  @IsOptional() @IsString() strategy_type?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(100) limit?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(0) offset?: number;
}

export class RankDto {
  @IsOptional() @IsString() status?: string;
  @IsOptional() @IsString() strategy_type?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(0) offset?: number;
  @IsOptional() @Transform(({ value }) => (typeof value === 'string' ? value.split(',') : value))
  @IsArray() @IsString({ each: true })
  rank_keys?: string[];
}

export class RefreshRankingDto {
  @IsOptional()
  @Transform(({ value }) => (typeof value === 'string' ? value.split(',') : value))
  @IsArray() @IsString({ each: true })
  strategy_types?: string[];

  @IsOptional()
  @Transform(({ value }) => (typeof value === 'string' ? value.split(',').map((x: string) => Number(x)) : value))
  @IsArray() @IsInt({ each: true }) @Min(1, { each: true }) @Max(200, { each: true })
  limits?: number[];

  @IsOptional()
  rank_keys_sets?: string[][];
}

export class CreateDto {
  @IsString() name!: string;
  @IsString() strategy_type!: string;
  @IsOptional() @IsString() description?: string;
  @IsOptional() @IsString() author_id?: string;
  @IsOptional() params?: Record<string, unknown>;
  @IsOptional() factor_weights?: Record<string, number>;
  @IsOptional() @IsArray() @IsString({ each: true }) tags?: string[];
  @IsOptional() @IsString() backtest_artifact_id?: string;
}

export class SubscribeDto {
}

export class ReviewDto {
  @Type(() => Number) @IsInt() @Min(1) @Max(5) rating!: number;
  @IsOptional() @IsString() comment?: string;
}

export class UpdateMetricsDto {
  @IsOptional() @IsString() period?: string;
  @IsOptional() metrics?: Record<string, unknown>;
}

export class SignalsQueryDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

export class EventsQueryDto {
  @IsOptional() @IsString() event_type?: string;
  @IsOptional() @IsString() from_status?: string;
  @IsOptional() @IsString() to_status?: string;
  @IsOptional() @IsString() actor_id?: string;
  @IsOptional() @IsString() start_time?: string;
  @IsOptional() @IsString() end_time?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

export class FactoryRunsQueryDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(100) limit?: number;
}

export class ReviewWorkflowQueryDto {
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() include_factory_status?: boolean;
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() include_review_report?: boolean;
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() include_runtime_alerts?: boolean;
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() run_factory_once?: boolean;
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() run_runtime_cycle?: boolean;
  @IsOptional() @IsString() idempotency_key?: string;
  @IsOptional() @IsString() as_of?: string;
}

export class DailySnapshotsQueryDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
  @IsOptional() @IsString() start_date?: string;
  @IsOptional() @IsString() end_date?: string;
}

export class IncubationMetricsQueryDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(365) limit?: number;
  @IsOptional() @IsString() start_date?: string;
  @IsOptional() @IsString() end_date?: string;
}

export class PaperOrdersQueryDto {
  @IsOptional() @IsString() signal_date?: string;
  @IsOptional() @IsString() status?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

export class PaperNavQueryDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(365) limit?: number;
}

export class IncubationSyncRunDto {
  @IsOptional() @IsString() signal_date?: string;
}

export class ExecutionAuditAcceptanceDto {
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() backfill?: boolean;
}

export class IncubationPipelineQueryDto {
  @IsOptional() @IsString() pipeline_stage?: string;
  @IsOptional() @IsString() pipeline_status?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

export class IncubationPipelineRunDto {
  @IsOptional() @Transform(({ value }) => (typeof value === 'string' ? value.split(',') : value))
  @IsArray() @IsString({ each: true })
  statuses?: string[];
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(1000) limit?: number;
  @IsOptional() @IsString() source?: string;
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() auto_apply_review?: boolean;
}

export class RiskEventsQueryDto {
  @IsOptional() @IsString() account_id?: string;
  @IsOptional() @IsString() status?: string;
  @IsOptional() @IsString() severity?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

export class RiskSnapshotsQueryDto {
  @IsOptional() @IsString() posture_level?: string;
  @IsOptional() @IsString() control_mode?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

export class RiskScanRunDto {
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() enforce_actions?: boolean;
}

export class RiskRecoveryDto {
  @IsOptional() @IsString() source?: string;
}

export class RuntimeAlertsQueryDto {
  @IsOptional() @IsString() status?: string;
  @IsOptional() @IsString() category?: string;
  @IsOptional() @IsString() severity?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

export class RuntimeAlertDispatchDto {
  @IsOptional() @IsString() source?: string;
}

export class RuntimeAlertAckDto {
  @IsOptional() @IsString() acknowledged_by?: string;
  @IsOptional() @IsString() source?: string;
}

export class VectorProfilesQueryDto {
  @IsOptional() @IsString() profile_type?: string;
  @IsOptional() @IsString() similar_to?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

export class VectorIndexesQueryDto {
  @IsOptional() @IsString() index_name?: string;
  @IsOptional() @IsString() status?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

export class VectorIndexSnapshotsQueryDto {
  @IsOptional() @IsString() index_name?: string;
  @IsOptional() @IsString() index_version?: string;
  @IsOptional() @IsString() status?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

export class VectorAnnSearchQueryDto {
  @IsOptional() @IsString() index_name?: string;
  @IsOptional() @IsString() index_version?: string;
  @IsOptional() @IsString() profile_type?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) candidate_limit?: number;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(50) limit?: number;
}

export class VectorReconcileDto {
  @IsOptional() @IsString() index_name?: string;
  @IsOptional() @IsString() profile_type?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(5000) limit_profiles?: number;
}

export class VectorRebuildDto {
  @IsOptional() @IsString() index_name?: string;
  @IsOptional() @IsString() index_version?: string;
  @IsOptional() @Transform(({ value }) => (typeof value === 'string' ? value.split(',') : value))
  @IsArray() @IsString({ each: true })
  statuses?: string[];
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(1000) limit?: number;
  @IsOptional() @IsString() profile_type?: string;
  @IsOptional() @IsString() vector_method?: string;
}

export class VectorHealthQueryDto {
  @IsOptional() @IsString() index_name?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit_versions?: number;
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() include_hnsw_indexes?: boolean;
}

export class VectorCleanupDto {
  @IsOptional() @IsString() index_name?: string;
  @IsOptional() @IsString() scope?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(0) @Max(200) keep_versions?: number;
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() dry_run?: boolean;
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() cleanup_hnsw?: boolean;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit_versions?: number;
  @IsOptional() @Transform(({ value }) => (typeof value === 'string' ? value.split(',') : value))
  @IsArray() @IsString({ each: true })
  protect_versions?: string[];
}

export class DomainEventsQueryDto {
  @IsOptional() @IsString() aggregate_type?: string;
  @IsOptional() @IsString() event_type?: string;
  @IsOptional() @IsString() source?: string;
  @IsOptional() @IsString() correlation_id?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

export class DomainProjectionQueryDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(20) @Max(500) limit?: number;
}

export class DomainProjectionRebuildDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
  @IsOptional() @Transform(({ value }) => (typeof value === 'string' ? value.split(',') : value))
  @IsArray() @IsString({ each: true })
  statuses?: string[];
  @IsOptional() @IsString() source?: string;
}

export class RuntimeControlSetDto {
  @IsString() control_mode!: string;
  @IsOptional() @IsString() reason?: string;
  @IsOptional() @IsString() source?: string;
  @IsOptional() @IsString() trigger_event_type?: string;
}

export class PromotionReviewsQueryDto {
  @IsOptional() @IsString() status?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

export class PromotionReviewRunDto {
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() auto_apply?: boolean;
  @IsOptional() @IsString() source?: string;
}

export class ResolveRiskEventDto {
  @IsOptional() @IsString() resolution?: string;
}

export class AiGenerateDto {
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(10) limit?: number;
  @IsOptional() @IsString() parent_strategy_id?: string;
  @IsOptional() @Transform(({ value }) => value === true || value === 'true') @IsBoolean() auto_submit?: boolean;
}

export class AiExperimentsQueryDto {
  @IsOptional() @IsString() experiment_id?: string;
  @IsOptional() @IsString() strategy_id?: string;
  @IsOptional() @IsString() parent_strategy_id?: string;
  @IsOptional() @IsString() generated_strategy_id?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) task_run_id?: number;
  @IsOptional() @IsString() status?: string;
  @IsOptional() @IsString() source?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

export class TaskRunsQueryDto {
  @IsOptional() @IsString() strategy_id?: string;
  @IsOptional() @IsString() task_name?: string;
  @IsOptional() @IsString() task_scope?: string;
  @IsOptional() @IsString() status?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(500) limit?: number;
}

export type Req_ = {
  traceId?: string;
  headers?: Record<string, string | undefined>;
  user?: { id?: string };
};

export function tid(req: Req_) {
  return String(req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN');
}
