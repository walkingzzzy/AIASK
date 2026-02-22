import { Injectable } from '@nestjs/common';
import { DbService } from '../db/db.service';

export type UserContext = {
  riskLevel?: string;
  recentEmotions?: string[];
  kycLevel?: string;
  profileSummary?: string;
};

const EMOTION_LABELS = ['极度焦虑', '偏焦虑', '理性', '偏乐观', '极度贪婪'] as const;

@Injectable()
export class UserContextService {
  /** In-memory store for emotion history per user (last 5 labels) */
  private emotionHistory = new Map<string, string[]>();

  constructor(private readonly dbService: DbService) {}

  /**
   * Build user context to inject into the system prompt.
   * Reads risk level, KYC level, and profile summary from DB; recent emotions from memory.
   */
  async getUserContext(userId: string): Promise<UserContext> {
    const ctx: UserContext = {};

    if (this.dbService.enabled) {
      try {
        const result = await this.dbService.query<{
          risk_level: string;
          preferences: string | null;
        }>(
          'SELECT risk_level, preferences FROM app_users WHERE id = $1',
          [userId],
        );
        const row = result.rows[0];
        ctx.riskLevel = row?.risk_level ?? 'moderate';

        if (row?.preferences) {
          try {
            const prefs = typeof row.preferences === 'string'
              ? JSON.parse(row.preferences)
              : row.preferences;
            ctx.kycLevel = prefs.kyc_level;
            ctx.profileSummary = prefs.profile_summary;
          } catch { /* ignore parse errors */ }
        }
      } catch {
        ctx.riskLevel = 'moderate';
      }
    } else {
      ctx.riskLevel = 'moderate';
    }

    // Attach recent emotion labels
    const history = this.emotionHistory.get(userId);
    if (history?.length) {
      ctx.recentEmotions = [...history];
    }

    return ctx;
  }

  /**
   * Record an emotion label for a user (called after each chat turn).
   * Keeps the most recent 5 entries.
   */
  recordEmotion(userId: string, label: string): void {
    if (!EMOTION_LABELS.includes(label as typeof EMOTION_LABELS[number])) return;
    const history = this.emotionHistory.get(userId) ?? [];
    history.push(label);
    if (history.length > 5) history.shift();
    this.emotionHistory.set(userId, history);
  }
}
