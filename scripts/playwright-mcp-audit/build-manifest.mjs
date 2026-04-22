import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { normalizeSurfaceContract } from './platform-contract.mjs';

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

  const surfaces = catalog.map((surface, index) => {
    const contract = normalizeSurfaceContract(surface);
    return {
      ordinal: index + 1,
      surfaceId: contract.surfaceId,
      label: contract.label,
      group: contract.group,
      route: contract.route,
      path: contract.path || contract.route,
      auth: contract.auth,
      requiresAuth: Boolean(contract.requiresAuth ?? contract.auth !== 'public'),
      family: contract.family || contract.group,
      budgetClass: contract.budgetClass || 'overview',
      dynamicResolver: contract.dynamicResolver || null,
      mutationRisk: contract.mutationRisk,
      mutationMode: contract.mutationMode,
      emptyStatePolicy: contract.emptyStatePolicy,
      scenarioSet: contract.scenarioSet,
      seedDependencies: contract.seedDependencies,
      proofMode: contract.proofMode,
      readProofRequired: contract.readProofRequired,
      writeProofRequired: contract.writeProofRequired,
      prerequisites: contract.prerequisites,
      seedStrategy: contract.seedStrategy,
      cleanupStrategy: contract.cleanupStrategy,
      artifactKey: contract.artifactKey,
      inScope: contract.inScope,
    };
  });

  const manifest = {
    generatedAt: new Date().toISOString(),
    total: surfaces.length,
    byAuth: surfaces.reduce((acc, surface) => {
      acc[surface.auth] = (acc[surface.auth] || 0) + 1;
      return acc;
    }, {}),
    byScope: surfaces.reduce((acc, surface) => {
      const key = surface.inScope ? 'inScope' : 'outOfScope';
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {}),
    byGroup: surfaces.reduce((acc, surface) => {
      acc[surface.group] = (acc[surface.group] || 0) + 1;
      return acc;
    }, {}),
    byFamily: surfaces.reduce((acc, surface) => {
      acc[surface.family] = (acc[surface.family] || 0) + 1;
      return acc;
    }, {}),
    byBudgetClass: surfaces.reduce((acc, surface) => {
      acc[surface.budgetClass] = (acc[surface.budgetClass] || 0) + 1;
      return acc;
    }, {}),
    byProofMode: surfaces.reduce((acc, surface) => {
      acc[surface.proofMode] = (acc[surface.proofMode] || 0) + 1;
      return acc;
    }, {}),
    byMutationMode: surfaces.reduce((acc, surface) => {
      acc[surface.mutationMode] = (acc[surface.mutationMode] || 0) + 1;
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
