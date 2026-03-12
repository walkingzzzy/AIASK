import { Body, Controller, Get, Param, Post, Query, Req } from '@nestjs/common';
import { StrategyMarketService } from './strategy.service';
import {
  VectorProfilesQueryDto,
  VectorIndexesQueryDto,
  VectorIndexSnapshotsQueryDto,
  VectorAnnSearchQueryDto,
  VectorReconcileDto,
  VectorRebuildDto,
  VectorHealthQueryDto,
  VectorCleanupDto,
  DomainEventsQueryDto,
  DomainProjectionQueryDto,
  DomainProjectionRebuildDto,
  Req_,
  tid,
} from './dto';

@Controller('strategy-market')
export class StrategyVectorController {
  constructor(private readonly svc: StrategyMarketService) {}

  @Get(':id/vector-profiles')
  async vectorProfiles(@Param('id') id: string, @Query() q: VectorProfilesQueryDto, @Req() req: Req_) {
    const data = await this.svc.vectorProfiles(id, { profile_type: q.profile_type, similar_to: q.similar_to, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('vector-indexes')
  async vectorIndexes(@Query() q: VectorIndexesQueryDto, @Req() req: Req_) {
    const data = await this.svc.vectorIndexes({ index_name: q.index_name, status: q.status, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('vector-indexes/snapshots')
  async vectorIndexSnapshots(@Query() q: VectorIndexSnapshotsQueryDto, @Req() req: Req_) {
    const data = await this.svc.vectorIndexSnapshots({ index_name: q.index_name, index_version: q.index_version, status: q.status, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/vector-ann-search')
  async vectorAnnSearch(@Param('id') id: string, @Query() q: VectorAnnSearchQueryDto, @Req() req: Req_) {
    const data = await this.svc.vectorAnnSearch(id, { index_name: q.index_name, index_version: q.index_version, profile_type: q.profile_type, candidate_limit: q.candidate_limit, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('vector-indexes/reconcile')
  async vectorReconcile(@Body() body: VectorReconcileDto, @Req() req: Req_) {
    const data = await this.svc.vectorReconcile({ index_name: body.index_name, profile_type: body.profile_type, limit_profiles: body.limit_profiles });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('vector-indexes/rebuild')
  async vectorRebuild(@Body() body: VectorRebuildDto, @Req() req: Req_) {
    const data = await this.svc.vectorRebuild({ index_name: body.index_name, index_version: body.index_version, statuses: body.statuses, limit: body.limit, profile_type: body.profile_type, vector_method: body.vector_method });
    return { success: true, data, traceId: tid(req) };
  }

  @Get('vector-health')
  async vectorHealth(@Query() q: VectorHealthQueryDto, @Req() req: Req_) {
    const data = await this.svc.vectorHealth({ index_name: q.index_name, limit_versions: q.limit_versions, include_hnsw_indexes: q.include_hnsw_indexes });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('vector-indexes/cleanup')
  async vectorCleanup(@Body() body: VectorCleanupDto, @Req() req: Req_) {
    const data = await this.svc.vectorCleanup({ index_name: body.index_name, keep_versions: body.keep_versions, dry_run: body.dry_run, cleanup_hnsw: body.cleanup_hnsw, limit_versions: body.limit_versions, protect_versions: body.protect_versions });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/domain-events')
  async domainEvents(@Param('id') id: string, @Query() q: DomainEventsQueryDto, @Req() req: Req_) {
    const data = await this.svc.domainEvents(id, { aggregate_type: q.aggregate_type, event_type: q.event_type, source: q.source, correlation_id: q.correlation_id, limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/domain-projection')
  async domainProjection(@Param('id') id: string, @Query() q: DomainProjectionQueryDto, @Req() req: Req_) {
    const data = await this.svc.domainProjection(id, { limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Get(':id/domain-projection/snapshot')
  async domainProjectionSnapshot(@Param('id') id: string, @Query() q: DomainProjectionQueryDto, @Req() req: Req_) {
    const data = await this.svc.domainProjectionSnapshot(id, { limit: q.limit });
    return { success: true, data, traceId: tid(req) };
  }

  @Post(':id/domain-projection/rebuild')
  async rebuildDomainProjection(@Param('id') id: string, @Body() body: DomainProjectionRebuildDto, @Req() req: Req_) {
    const data = await this.svc.rebuildDomainProjection(id, { limit: body.limit, statuses: body.statuses, source: body.source });
    return { success: true, data, traceId: tid(req) };
  }

  @Post('domain-projections/rebuild')
  async rebuildDomainProjections(@Body() body: DomainProjectionRebuildDto, @Req() req: Req_) {
    const data = await this.svc.rebuildDomainProjection(undefined, { limit: body.limit, statuses: body.statuses, source: body.source });
    return { success: true, data, traceId: tid(req) };
  }
}
