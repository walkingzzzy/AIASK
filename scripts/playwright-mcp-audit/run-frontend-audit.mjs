import fs from 'node:fs/promises';
import path from 'node:path';

import { ensureDir } from './browser-common.mjs';
import { runCommand } from './process-common.mjs';

function parseArgs(argv) {
  const args = {
    outputDir: path.resolve(process.cwd(), 'frontend-audit-report'),
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
    }
  }

  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const scriptsDir = path.join(process.cwd(), 'scripts', 'playwright-mcp-audit');
  await fs.rm(args.outputDir, { recursive: true, force: true });
  await ensureDir(path.join(args.outputDir, 'raw'));

  let snapshotCreated = false;
  let auditError = null;

  try {
    await runCommand('node', [path.join(scriptsDir, 'build-manifest.mjs'), '--output-dir', args.outputDir]);
    await runCommand('node', [path.join(scriptsDir, 'env-snapshot.mjs'), '--output-dir', args.outputDir]);
    snapshotCreated = true;

    await runCommand('node', [path.join(scriptsDir, 'run-local-audit.mjs'), '--output-dir', args.outputDir]);
    await runCommand('node', [path.join(scriptsDir, 'run-responsive-audit.mjs'), '--output-dir', args.outputDir]);
    await runCommand('node', [path.join(scriptsDir, 'run-flow-audit.mjs'), '--output-dir', args.outputDir]);
  } catch (error) {
    auditError = error;
  } finally {
    if (snapshotCreated) {
      await runCommand('node', [path.join(scriptsDir, 'env-restore.mjs'), '--output-dir', args.outputDir], {
        allowFailure: true,
      });
    }
  }

  await runCommand('node', [path.join(scriptsDir, 'render-frontend-audit-report.mjs'), '--output-dir', args.outputDir]);
  if (auditError) {
    throw auditError;
  }
  process.stdout.write(`${path.join(args.outputDir, 'index.md')}\n`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
