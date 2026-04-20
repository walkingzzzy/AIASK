import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import {
  collectDefaultMetrics,
  Counter,
  Gauge,
  Histogram,
  Registry,
} from 'prom-client';

type HttpMetric = {
  method: string;
  route: string;
  statusCode: number;
  durationMs: number;
  degraded: boolean;
};

type McpMetric = {
  name: string;
  latencyMs: number;
  errored: boolean;
  transportKind: string;
  degraded: boolean;
};

type DbMetric = {
  operation: string;
  durationMs: number;
  errored: boolean;
};

@Injectable()
export class ObservabilityService {
  private readonly registry = new Registry();
  private readonly serviceName: string;
  private readonly environment: string;
  private readonly httpRequestsTotal: Counter<string>;
  private readonly httpRequestDurationSeconds: Histogram<string>;
  private readonly mcpCallsTotal: Counter<string>;
  private readonly mcpCallDurationSeconds: Histogram<string>;
  private readonly dbQueriesTotal: Counter<string>;
  private readonly dbQueryDurationSeconds: Histogram<string>;
  private readonly dependencyStatus: Gauge<string>;

  constructor(private readonly configService: ConfigService) {
    this.serviceName = this.configService.get<string>('OTEL_SERVICE_NAME', 'aiask-bff');
    this.environment = this.configService.get<string>('NODE_ENV', 'development');
    this.registry.setDefaultLabels({
      service: this.serviceName,
      environment: this.environment,
    });
    collectDefaultMetrics({
      register: this.registry,
      prefix: 'aiask_bff_',
    });

    this.httpRequestsTotal = new Counter({
      name: 'aiask_bff_http_requests_total',
      help: 'Total number of HTTP requests handled by the BFF.',
      labelNames: ['method', 'route', 'status_code', 'degraded'],
      registers: [this.registry],
    });
    this.httpRequestDurationSeconds = new Histogram({
      name: 'aiask_bff_http_request_duration_seconds',
      help: 'HTTP request duration in seconds.',
      labelNames: ['method', 'route', 'status_code', 'degraded'],
      buckets: [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30],
      registers: [this.registry],
    });
    this.mcpCallsTotal = new Counter({
      name: 'aiask_bff_mcp_calls_total',
      help: 'Total number of MCP tool/resource calls made by the BFF.',
      labelNames: ['name', 'transport_kind', 'outcome', 'degraded'],
      registers: [this.registry],
    });
    this.mcpCallDurationSeconds = new Histogram({
      name: 'aiask_bff_mcp_call_duration_seconds',
      help: 'Latency of MCP tool/resource calls in seconds.',
      labelNames: ['name', 'transport_kind', 'outcome', 'degraded'],
      buckets: [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30],
      registers: [this.registry],
    });
    this.dbQueriesTotal = new Counter({
      name: 'aiask_bff_db_queries_total',
      help: 'Total number of BFF database queries.',
      labelNames: ['operation', 'outcome'],
      registers: [this.registry],
    });
    this.dbQueryDurationSeconds = new Histogram({
      name: 'aiask_bff_db_query_duration_seconds',
      help: 'Latency of BFF database queries in seconds.',
      labelNames: ['operation', 'outcome'],
      buckets: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5],
      registers: [this.registry],
    });
    this.dependencyStatus = new Gauge({
      name: 'aiask_bff_dependency_status',
      help: 'Dependency status gauge where 1 means healthy/ready and 0 means degraded or unavailable.',
      labelNames: ['dependency'],
      registers: [this.registry],
    });
  }

  recordHttpRequest(metric: HttpMetric): void {
    const labels = {
      method: String(metric.method || 'UNKNOWN').toUpperCase(),
      route: this.normalizeRoute(metric.route),
      status_code: String(metric.statusCode || 0),
      degraded: metric.degraded ? 'true' : 'false',
    };
    this.httpRequestsTotal.inc(labels);
    this.httpRequestDurationSeconds.observe(labels, Math.max(0, metric.durationMs) / 1000);
  }

  recordMcpCall(metric: McpMetric): void {
    const labels = {
      name: this.normalizeMetricName(metric.name),
      transport_kind: this.normalizeMetricName(metric.transportKind || 'none'),
      outcome: metric.errored ? 'error' : 'success',
      degraded: metric.degraded ? 'true' : 'false',
    };
    this.mcpCallsTotal.inc(labels);
    this.mcpCallDurationSeconds.observe(labels, Math.max(0, metric.latencyMs) / 1000);
  }

  recordDbQuery(metric: DbMetric): void {
    const labels = {
      operation: this.normalizeMetricName(metric.operation || 'query'),
      outcome: metric.errored ? 'error' : 'success',
    };
    this.dbQueriesTotal.inc(labels);
    this.dbQueryDurationSeconds.observe(labels, Math.max(0, metric.durationMs) / 1000);
  }

  setDependencyState(dependency: string, healthy: boolean): void {
    this.dependencyStatus.set(
      { dependency: this.normalizeMetricName(dependency || 'unknown') },
      healthy ? 1 : 0,
    );
  }

  async metrics(): Promise<string> {
    return this.registry.metrics();
  }

  contentType(): string {
    return this.registry.contentType;
  }

  snapshot() {
    return {
      service: this.serviceName,
      environment: this.environment,
      metricsEndpoint: '/api/metrics',
    };
  }

  private normalizeMetricName(value: string): string {
    const normalized = String(value || 'unknown')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9:_-]+/g, '_')
      .replace(/^_+|_+$/g, '');
    return normalized || 'unknown';
  }

  private normalizeRoute(route: string): string {
    const raw = String(route || 'UNKNOWN').split('?')[0].trim();
    if (!raw) return 'UNKNOWN';
    return raw
      .replace(/\/\d+/g, '/:id')
      .replace(/\/[a-f0-9]{8,}/gi, '/:id');
  }
}
