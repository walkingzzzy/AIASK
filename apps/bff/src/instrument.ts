import { diag, DiagConsoleLogger, DiagLogLevel } from '@opentelemetry/api';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { NodeSDK } from '@opentelemetry/sdk-node';
import * as Sentry from '@sentry/nestjs';
import { nodeProfilingIntegration } from '@sentry/profiling-node';

let otelSdk: NodeSDK | null = null;

function isEnabled(raw: string | undefined, fallback = true) {
  if (raw == null) return fallback;
  return !['0', 'false', 'no'].includes(raw.trim().toLowerCase());
}

if (isEnabled(process.env.OTEL_ENABLED, true)) {
  if (isEnabled(process.env.OTEL_DIAG_ENABLED, false)) {
    diag.setLogger(new DiagConsoleLogger(), DiagLogLevel.INFO);
  }
  const traceExporter = new OTLPTraceExporter(
    process.env.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT || process.env.OTEL_EXPORTER_OTLP_ENDPOINT
      ? {
          url:
            process.env.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
            || process.env.OTEL_EXPORTER_OTLP_ENDPOINT,
        }
      : undefined,
  );
  otelSdk = new NodeSDK({
    traceExporter,
    resource: resourceFromAttributes({
      'service.name': process.env.OTEL_SERVICE_NAME || 'aiask-bff',
      'service.version': process.env.npm_package_version || '0.1.0',
      'deployment.environment.name': process.env.NODE_ENV || 'development',
    }),
    instrumentations: [
      getNodeAutoInstrumentations({
        '@opentelemetry/instrumentation-fs': { enabled: false },
      }),
    ],
  });
  void Promise.resolve(otelSdk.start()).catch((error) => {
    console.error('[observability] failed to start OpenTelemetry', error);
  });
  const shutdown = () => {
    if (!otelSdk) return;
    void otelSdk.shutdown().catch((error) => {
      console.error('[observability] failed to shutdown OpenTelemetry', error);
    });
  };
  process.once('SIGTERM', shutdown);
  process.once('SIGINT', shutdown);
}

Sentry.init({
  dsn: process.env.SENTRY_DSN || '',
  environment: process.env.NODE_ENV || 'development',
  enabled: !!process.env.SENTRY_DSN,
  integrations: [nodeProfilingIntegration()],
  tracesSampleRate: process.env.NODE_ENV === 'production' ? 0.2 : 1.0,
  profilesSampleRate: 0.1,
});
