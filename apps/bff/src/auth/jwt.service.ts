import { createHash, createHmac, randomUUID, timingSafeEqual } from 'crypto';
import type { AccessPayload } from './auth.types';

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
