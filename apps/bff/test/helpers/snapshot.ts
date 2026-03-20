import * as assert from 'node:assert/strict';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => stableValue(item));
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return Object.keys(record)
      .sort((a, b) => a.localeCompare(b))
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = stableValue(record[key]);
        return acc;
      }, {});
  }
  return value;
}

export function assertJsonSnapshot(relativePath: string, payload: unknown) {
  const fullPath = resolve(process.cwd(), 'test', 'snapshots', relativePath);
  const serialized = `${JSON.stringify(stableValue(payload), null, 2)}\n`;

  if (process.env.UPDATE_SNAPSHOTS === '1' || !existsSync(fullPath)) {
    mkdirSync(dirname(fullPath), { recursive: true });
    writeFileSync(fullPath, serialized, 'utf8');
    return;
  }

  const existing = readFileSync(fullPath, 'utf8');
  assert.equal(serialized, existing, `snapshot mismatch: ${relativePath}`);
}
