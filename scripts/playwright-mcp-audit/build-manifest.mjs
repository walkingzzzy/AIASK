import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

function parseArgs(argv) {
  const args = {
    outputDir: null,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
    }
  }

  if (!args.outputDir) {
    throw new Error('missing --output-dir');
  }

  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
  const catalogPath = path.join(root, 'apps', 'web', 'e2e', 'realworld', 'catalog.json');
  const outputPath = path.join(args.outputDir, 'raw', 'surface-manifest.json');
  const catalog = JSON.parse(await fs.readFile(catalogPath, 'utf8'));

  const surfaces = catalog.map((surface, index) => ({
    ordinal: index + 1,
    surfaceId: surface.surfaceId,
    label: surface.label,
    group: surface.group,
    route: surface.route,
    auth: surface.auth,
    mutationRisk: surface.mutationRisk,
    emptyStatePolicy: surface.emptyStatePolicy,
    scenarioSet: surface.scenarioSet,
    seedDependencies: surface.seedDependencies,
  }));

  const manifest = {
    generatedAt: new Date().toISOString(),
    total: surfaces.length,
    byAuth: surfaces.reduce((acc, surface) => {
      acc[surface.auth] = (acc[surface.auth] || 0) + 1;
      return acc;
    }, {}),
    byGroup: surfaces.reduce((acc, surface) => {
      acc[surface.group] = (acc[surface.group] || 0) + 1;
      return acc;
    }, {}),
    surfaces,
  };

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, JSON.stringify(manifest, null, 2), 'utf8');
  process.stdout.write(`${outputPath}\n`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
