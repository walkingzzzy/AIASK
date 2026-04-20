import { spawn } from 'node:child_process';

export async function runCommand(command, args, options = {}) {
  const {
    cwd,
    env,
    allowFailure = false,
    stdoutFile = null,
    stderrFile = null,
  } = options;

  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: env ? { ...process.env, ...env } : process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (chunk) => {
      const text = chunk.toString();
      stdout += text;
      if (stdoutFile?.write) stdoutFile.write(text);
    });
    child.stderr.on('data', (chunk) => {
      const text = chunk.toString();
      stderr += text;
      if (stderrFile?.write) stderrFile.write(text);
    });
    child.on('error', reject);
    child.on('close', (code) => {
      const result = {
        code: code ?? 0,
        stdout,
        stderr,
        command,
        args,
      };
      if (code === 0 || allowFailure) {
        resolve(result);
        return;
      }
      const error = new Error(stderr.trim() || stdout.trim() || `${command} exited with code ${code}`);
      error.result = result;
      reject(error);
    });
  });
}

export function slugify(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/gi, '-')
    .replace(/^-+|-+$/g, '') || 'item';
}
