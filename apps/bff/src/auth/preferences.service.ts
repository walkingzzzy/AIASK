import { BadRequestException, Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { DbService } from '../db/db.service';
import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from 'crypto';

export type LlmConfig = { apiKey: string; baseUrl: string; model: string };
export type SaveLlmConfigInput = { apiKey?: string | null; baseUrl: string; model: string };
export type MaskedLlmConfig = {
  baseUrl: string;
  model: string;
  hasStoredApiKey: boolean;
  apiKeyMasked: string;
};
type UserPreferences = { llm?: LlmConfig; [key: string]: unknown };

@Injectable()
export class PreferencesService {
  private readonly memStore = new Map<string, UserPreferences>();
  private readonly encKey: Buffer;

  constructor(
    private readonly dbService: DbService,
    private readonly configService: ConfigService,
  ) {
    const secret = this.configService.get<string>('APP_ENCRYPT_SECRET', 'aiask-default-encrypt-key!');
    this.encKey = scryptSync(secret, 'aiask-salt', 32);
  }

  async getLlmConfig(userId: string): Promise<LlmConfig | null> {
    const prefs = await this.getUserPreferences(userId);
    if (!prefs?.llm?.apiKey) return null;
    try {
      return { ...prefs.llm, apiKey: this.decrypt(prefs.llm.apiKey) };
    } catch {
      return null;
    }
  }

  async setLlmConfig(userId: string, config: SaveLlmConfigInput): Promise<LlmConfig> {
    const prefs = await this.getUserPreferences(userId);
    const existingEncryptedKey = prefs?.llm?.apiKey;
    const nextApiKey = this.resolveNextApiKey(config.apiKey, existingEncryptedKey);
    const updated: UserPreferences = {
      ...prefs,
      llm: {
        apiKey: nextApiKey.encrypted,
        baseUrl: config.baseUrl,
        model: config.model,
      },
    };
    await this.setUserPreferences(userId, updated);
    return { apiKey: nextApiKey.decrypted, baseUrl: config.baseUrl, model: config.model };
  }

  async getMaskedLlmConfig(userId: string): Promise<MaskedLlmConfig | null> {
    const prefs = await this.getUserPreferences(userId);
    if (!prefs?.llm?.apiKey) return null;
    try {
      const realKey = this.decrypt(prefs.llm.apiKey);
      return {
        baseUrl: prefs.llm.baseUrl,
        model: prefs.llm.model,
        hasStoredApiKey: true,
        apiKeyMasked: this.maskApiKey(realKey),
      };
    } catch {
      return null;
    }
  }

  maskApiKey(key: string): string {
    if (key.length <= 8) return '****';
    return key.slice(0, 3) + '****' + key.slice(-4);
  }

  async getUserPreferences(userId: string): Promise<UserPreferences> {
    if (this.dbService.enabled) {
      try {
        const result = await this.dbService.query<{ preferences: UserPreferences }>(
          'SELECT preferences FROM app_users WHERE id = $1',
          [userId],
        );
        return result.rows[0]?.preferences ?? {};
      } catch {
        return {};
      }
    }
    return this.memStore.get(userId) ?? {};
  }

  async setUserPreferences(userId: string, prefs: UserPreferences): Promise<void> {
    if (this.dbService.enabled) {
      const result = await this.dbService.query(
        'UPDATE app_users SET preferences = $2::jsonb WHERE id = $1',
        [userId, JSON.stringify(prefs ?? {})],
      );
      if (result.rowCount && result.rowCount > 0) {
        return;
      }
    }
    this.memStore.set(userId, prefs);
  }

  async mergeUserPreferences(userId: string, patch: UserPreferences): Promise<UserPreferences> {
    const current = await this.getUserPreferences(userId);
    const next = { ...current, ...patch };
    await this.setUserPreferences(userId, next);
    return next;
  }

  private encrypt(text: string): string {
    const iv = randomBytes(16);
    const cipher = createCipheriv('aes-256-gcm', this.encKey, iv);
    const encrypted = Buffer.concat([cipher.update(text, 'utf8'), cipher.final()]);
    const tag = cipher.getAuthTag();
    return iv.toString('hex') + ':' + tag.toString('hex') + ':' + encrypted.toString('hex');
  }

  private decrypt(data: string): string {
    const [ivHex, tagHex, encHex] = data.split(':');
    if (!ivHex || !tagHex || !encHex) return data; // not encrypted, return as-is
    const iv = Buffer.from(ivHex, 'hex');
    const tag = Buffer.from(tagHex, 'hex');
    const encrypted = Buffer.from(encHex, 'hex');
    const decipher = createDecipheriv('aes-256-gcm', this.encKey, iv);
    decipher.setAuthTag(tag);
    return decipher.update(encrypted) + decipher.final('utf8');
  }

  private resolveNextApiKey(input: string | null | undefined, existingEncryptedKey?: string): {
    encrypted: string;
    decrypted: string;
  } {
    const trimmed = String(input ?? '').trim();
    if (!trimmed) {
      if (!existingEncryptedKey) {
        throw new BadRequestException('请填写 API Key');
      }
      return {
        encrypted: existingEncryptedKey,
        decrypted: this.decrypt(existingEncryptedKey),
      };
    }

    if (this.looksLikeMaskedApiKey(trimmed)) {
      throw new BadRequestException('请不要提交脱敏后的 API Key；留空即可保留原有 Key');
    }

    return {
      encrypted: this.encrypt(trimmed),
      decrypted: trimmed,
    };
  }

  private looksLikeMaskedApiKey(value: string): boolean {
    return /^sk-[A-Za-z0-9]{0,6}\*{2,}[A-Za-z0-9]{0,8}$/.test(value) || /\*{2,}/.test(value);
  }
}
