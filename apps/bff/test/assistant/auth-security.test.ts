import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { AuthService } from '../../src/auth/auth.service';
import {
  hash,
  hashPasswordSync,
  isLegacyPasswordHash,
  verifyPassword,
} from '../../src/auth/jwt.service';

test('password hashing uses scrypt while remaining compatible with legacy sha256 hashes', async () => {
  const secureHash = hashPasswordSync('super-secret-password');

  assert.equal(secureHash.startsWith('scrypt$'), true);
  assert.equal(isLegacyPasswordHash(secureHash), false);
  assert.equal(await verifyPassword('super-secret-password', secureHash), true);
  assert.equal(await verifyPassword('wrong-password', secureHash), false);

  const legacyHash = hash('legacy-password');
  assert.equal(isLegacyPasswordHash(legacyHash), true);
  assert.equal(await verifyPassword('legacy-password', legacyHash), true);
});

test('auth service rejects weak JWT secrets in production mode', () => {
  const configService = {
    get<T = string>(key: string, fallback?: T): T {
      const values: Record<string, unknown> = {
        NODE_ENV: 'production',
        APP_JWT_SECRET: 'dev-secret-change-me',
        APP_ADMIN_PASSWORD: 'a-very-strong-admin-password',
        APP_ENABLE_DEMO_USER: 'false',
      };
      return (values[key] as T | undefined) ?? (fallback as T);
    },
  };

  assert.throws(
    () => new AuthService(configService as never, { enabled: false } as never, {} as never),
    /APP_JWT_SECRET/,
  );
});
