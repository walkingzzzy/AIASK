/**
 * T-039: TOTP Two-Factor Authentication Service
 * Google Authenticator compatible TOTP implementation.
 */
import { Injectable } from '@nestjs/common';
import * as crypto from 'crypto';

@Injectable()
export class TotpService {
    private readonly PERIOD = 30;
    private readonly DIGITS = 6;
    private readonly ALGORITHM = 'sha1';

    /** Generate a new TOTP secret (base32 encoded) */
    generateSecret(length = 20): string {
        const buffer = crypto.randomBytes(length);
        return this.base32Encode(buffer);
    }

    /** Generate provisioning URI for QR code (Google Authenticator compatible) */
    generateUri(secret: string, accountName: string, issuer = 'AIASK'): string {
        const encodedIssuer = encodeURIComponent(issuer);
        const encodedAccount = encodeURIComponent(accountName);
        return `otpauth://totp/${encodedIssuer}:${encodedAccount}?secret=${secret}&issuer=${encodedIssuer}&algorithm=${this.ALGORITHM.toUpperCase()}&digits=${this.DIGITS}&period=${this.PERIOD}`;
    }

    /** Verify a TOTP token (allows ±1 time step drift) */
    verify(token: string, secret: string): boolean {
        const now = Math.floor(Date.now() / 1000);
        for (let drift = -1; drift <= 1; drift++) {
            const timeStep = Math.floor((now + drift * this.PERIOD) / this.PERIOD);
            const expected = this.generateToken(secret, timeStep);
            if (this.timingSafeEqual(token, expected)) return true;
        }
        return false;
    }

    /** Generate TOTP token for a given time step */
    private generateToken(secret: string, timeStep: number): string {
        const buffer = Buffer.alloc(8);
        buffer.writeBigUInt64BE(BigInt(timeStep));

        const key = this.base32Decode(secret);
        const hmac = crypto.createHmac(this.ALGORITHM, key);
        hmac.update(buffer);
        const hash = hmac.digest();

        const offset = hash[hash.length - 1] & 0x0f;
        const code = (
            ((hash[offset] & 0x7f) << 24) |
            ((hash[offset + 1] & 0xff) << 16) |
            ((hash[offset + 2] & 0xff) << 8) |
            (hash[offset + 3] & 0xff)
        ) % Math.pow(10, this.DIGITS);

        return code.toString().padStart(this.DIGITS, '0');
    }

    /** Generate backup codes (one-time use) */
    generateBackupCodes(count = 8): string[] {
        return Array.from({ length: count }, () =>
            crypto.randomBytes(4).toString('hex').toUpperCase(),
        );
    }

    private timingSafeEqual(a: string, b: string): boolean {
        if (a.length !== b.length) return false;
        return crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));
    }

    private base32Encode(buffer: Buffer): string {
        const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
        let bits = 0;
        let value = 0;
        let output = '';
        for (let i = 0; i < buffer.length; i++) {
            value = (value << 8) | buffer[i];
            bits += 8;
            while (bits >= 5) {
                output += alphabet[(value >>> (bits - 5)) & 31];
                bits -= 5;
            }
        }
        if (bits > 0) output += alphabet[(value << (5 - bits)) & 31];
        return output;
    }

    private base32Decode(encoded: string): Buffer {
        const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
        let bits = 0;
        let value = 0;
        const output: number[] = [];
        for (const char of encoded.toUpperCase()) {
            const idx = alphabet.indexOf(char);
            if (idx === -1) continue;
            value = (value << 5) | idx;
            bits += 5;
            if (bits >= 8) {
                output.push((value >>> (bits - 8)) & 0xff);
                bits -= 8;
            }
        }
        return Buffer.from(output);
    }
}
