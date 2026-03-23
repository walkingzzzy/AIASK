import { createHash, createHmac, randomBytes, randomUUID, scryptSync, timingSafeEqual } from 'crypto';
import type { AccessPayload } from './auth.types';

const PASSWORD_HASH_PREFIX = 'scrypt';
const PASSWORD_HASH_N = 16384;
const PASSWORD_HASH_R = 8;
const PASSWORD_HASH_P = 1;
const PASSWORD_HASH_KEYLEN = 64;
const PASSWORD_HASH_MAXMEM = 64 * 1024 * 1024;

export function hash(text: string): string {
  return createHash('sha256').update(text).digest('hex');
}

export function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return timingSafeEqual(ab, bb);
}

export function base64Url(text: string): string {
  return Buffer.from(text).toString('base64url');
}

export function newJti(): string {
  return randomUUID().replace(/-/g, '');
}

export function newRefreshToken(): string {
  return `rtk_${randomUUID().replace(/-/g, '')}`;
}

function encodePasswordHash(salt: string, derived: Buffer): string {
  return [
    PASSWORD_HASH_PREFIX,
    String(PASSWORD_HASH_N),
    String(PASSWORD_HASH_R),
    String(PASSWORD_HASH_P),
    salt,
    derived.toString('base64url'),
  ].join('$');
}

function parsePasswordHash(storedHash: string): {
  n: number;
  r: number;
  p: number;
  salt: string;
  derived: Buffer;
} | null {
  const parts = String(storedHash || '').split('$');
  if (parts.length !== 6 || parts[0] !== PASSWORD_HASH_PREFIX) {
    return null;
  }

  const n = Number(parts[1]);
  const r = Number(parts[2]);
  const p = Number(parts[3]);
  const salt = parts[4];
  const derived = Buffer.from(parts[5], 'base64url');
  if (!Number.isFinite(n) || !Number.isFinite(r) || !Number.isFinite(p) || !salt || derived.length === 0) {
    return null;
  }

  return { n, r, p, salt, derived };
}

export function hashPasswordSync(password: string): string {
  const salt = randomBytes(16).toString('base64url');
  const derived = scryptSync(password, salt, PASSWORD_HASH_KEYLEN, {
    N: PASSWORD_HASH_N,
    r: PASSWORD_HASH_R,
    p: PASSWORD_HASH_P,
    maxmem: PASSWORD_HASH_MAXMEM,
  });
  return encodePasswordHash(salt, derived);
}

export async function hashPassword(password: string): Promise<string> {
  return hashPasswordSync(password);
}

export async function verifyPassword(password: string, storedHash: string): Promise<boolean> {
  const parsed = parsePasswordHash(storedHash);
  if (!parsed) {
    return safeEqual(hash(password), String(storedHash || ''));
  }

  const derived = scryptSync(password, parsed.salt, parsed.derived.length, {
    N: parsed.n,
    r: parsed.r,
    p: parsed.p,
    maxmem: PASSWORD_HASH_MAXMEM,
  });
  return timingSafeEqual(derived, parsed.derived);
}

export function isLegacyPasswordHash(storedHash: string): boolean {
  return parsePasswordHash(storedHash) == null;
}

export function signJwt(payload: AccessPayload, secret: string): string {
  const header = base64Url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = base64Url(JSON.stringify(payload));
  const message = `${header}.${body}`;
  const signature = createHmac('sha256', secret).update(message).digest('base64url');
  return `${message}.${signature}`;
}

export function verifyJwt(token: string, secret: string): AccessPayload | null {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  const [header, body, signature] = parts;
  const message = `${header}.${body}`;
  const expected = createHmac('sha256', secret).update(message).digest('base64url');
  if (!safeEqual(signature, expected)) return null;

  try {
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf-8')) as AccessPayload;
    if (!payload || payload.typ !== 'access') return null;
    if (!payload.exp || payload.exp <= Math.floor(Date.now() / 1000)) return null;
    if (!payload.sub || !payload.jti || !payload.username || !payload.role) return null;
    return payload;
  } catch {
    return null;
  }
}
