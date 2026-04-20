const BFF_PORT = process.env.BFF_PORT || '3001';
const PROMETHEUS_PORT = process.env.PROMETHEUS_PORT || '9090';
const ALERTMANAGER_PORT = process.env.ALERTMANAGER_PORT || '9093';
const OTEL_HEALTH_PORT = process.env.OTEL_HEALTH_PORT || '13133';
const POSTGRES_EXPORTER_PORT = process.env.POSTGRES_EXPORTER_PORT || '9187';
const BLACKBOX_EXPORTER_PORT = process.env.BLACKBOX_EXPORTER_PORT || '9115';

async function check({ name, url, expectStatus = 200, contentIncludes = [] }) {
  const response = await fetch(url);
  if (response.status !== expectStatus) {
    throw new Error(`${name} unexpected status ${response.status} @ ${url}`);
  }
  const body = await response.text();
  for (const snippet of contentIncludes) {
    if (!body.includes(snippet)) {
      throw new Error(`${name} missing expected content "${snippet}" @ ${url}`);
    }
  }
  return { name, url, status: response.status };
}

async function main() {
  const checks = [
    {
      name: 'bff-metrics',
      url: `http://127.0.0.1:${BFF_PORT}/api/metrics`,
      contentIncludes: ['aiask_bff_http_requests_total', 'aiask_bff_mcp_calls_total'],
    },
    {
      name: 'bff-health-live',
      url: `http://127.0.0.1:${BFF_PORT}/api/health/live`,
      contentIncludes: ['"probe":"liveness"'],
    },
    {
      name: 'bff-health-startup',
      url: `http://127.0.0.1:${BFF_PORT}/api/health/startup`,
      contentIncludes: ['"probe":"startup"'],
    },
    {
      name: 'prometheus-ready',
      url: `http://127.0.0.1:${PROMETHEUS_PORT}/-/ready`,
    },
    {
      name: 'postgres-exporter-metrics',
      url: `http://127.0.0.1:${POSTGRES_EXPORTER_PORT}/metrics`,
      contentIncludes: ['pg_up', 'aiask_timescaledb_extension_up', 'aiask_pgvector_extension_up'],
    },
    {
      name: 'blackbox-exporter-metrics',
      url: `http://127.0.0.1:${BLACKBOX_EXPORTER_PORT}/metrics`,
      contentIncludes: ['blackbox_exporter_build_info'],
    },
    {
      name: 'alertmanager-ready',
      url: `http://127.0.0.1:${ALERTMANAGER_PORT}/-/ready`,
    },
    {
      name: 'otel-collector-health',
      url: `http://127.0.0.1:${OTEL_HEALTH_PORT}/`,
    },
  ];

  const results = [];
  for (const item of checks) {
    results.push(await check(item));
  }
  console.log(JSON.stringify({ ok: true, checks: results }, null, 2));
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: String(error?.message || error) }, null, 2));
  process.exitCode = 1;
});
