import { createUnifiedDecisionTestApp } from '../test/helpers/unified-decision-test-app';

const args = new Map<string, string>();
for (const raw of process.argv.slice(2)) {
  const [key, ...rest] = raw.split('=');
  if (!key.startsWith('--')) continue;
  args.set(key.slice(2), rest.length ? rest.join('=') : 'true');
}

const port = Number(args.get('port') || process.env.BFF_PORT || '3301');

async function main() {
  const app = await createUnifiedDecisionTestApp();
  await app.listen(port, '127.0.0.1');
  const url = await app.getUrl();
  // eslint-disable-next-line no-console
  console.log(`[unified-decision-harness] listening on ${url}/api`);

  const shutdown = async () => {
    await app.close();
    process.exit(0);
  };

  process.on('SIGINT', () => void shutdown());
  process.on('SIGTERM', () => void shutdown());
}

main().catch((error) => {
  // eslint-disable-next-line no-console
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
});
