import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..');
const exportScript = resolve(repoRoot, 'scripts/export-strategy-contracts.py');
const targetFile = resolve(repoRoot, 'packages/shared-types/src/strategy/contracts.generated.ts');

function resolvePythonBin() {
  for (const candidate of ['python3', 'python']) {
    try {
      execFileSync(candidate, ['--version'], { stdio: 'ignore' });
      return candidate;
    } catch {
      continue;
    }
  }
  throw new Error('python3/python is required to generate strategy contracts');
}

const pythonBin = resolvePythonBin();
const raw = execFileSync(pythonBin, [exportScript], {
  cwd: repoRoot,
  encoding: 'utf8',
});
const surface = JSON.parse(raw);
const strategyManager = surface.strategy_manager ?? {};
const actions = Array.isArray(strategyManager.actions) ? strategyManager.actions : [];
const contractVersion = typeof strategyManager.contract_version === 'string'
  ? strategyManager.contract_version
  : 'strategy_manager.contract.unknown';

const actionLines = actions.map((action) => `  '${String(action)}',`).join('\n');
const fileBody = `// Auto-generated from packages/akshare-mcp Python contract surface.\n// Do not edit manually.\n\nexport const STRATEGY_MANAGER_CONTRACT_VERSION = '${contractVersion}' as const;\n\nexport const STRATEGY_MANAGER_ACTIONS = [\n${actionLines}\n] as const;\n\nexport type StrategyManagerAction = typeof STRATEGY_MANAGER_ACTIONS[number];\n`;

writeFileSync(targetFile, fileBody, 'utf8');
