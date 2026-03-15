/**
 * T-035: JWT Cookie Auth Service Enhancement
 * Provides HttpOnly cookie setters for secure JWT storage.
 */
import { Response } from 'express';
import { randomFillSync } from 'node:crypto';

const COOKIE_OPTIONS = {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict' as const,
    path: '/',
};

/** Set access token as HttpOnly cookie */
export function setAccessTokenCookie(res: Response, token: string, maxAgeMs = 15 * 60 * 1000) {
    res.cookie('access_token', token, {
        ...COOKIE_OPTIONS,
        maxAge: maxAgeMs,
    });
}

/** Set refresh token as HttpOnly cookie */
export function setRefreshTokenCookie(res: Response, token: string, maxAgeMs = 7 * 24 * 60 * 60 * 1000) {
    res.cookie('refresh_token', token, {
        ...COOKIE_OPTIONS,
        maxAge: maxAgeMs,
    });
}

/** Clear auth cookies on logout */
export function clearAuthCookies(res: Response) {
    res.clearCookie('access_token', { path: '/' });
    res.clearCookie('refresh_token', { path: '/' });
}

/** Generate CSRF token */
export function generateCsrfToken(): string {
    const array = new Uint8Array(32);
    randomFillSync(array);
    return Buffer.from(array).toString('hex');
}
