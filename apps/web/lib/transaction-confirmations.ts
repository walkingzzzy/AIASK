'use client';

export type TransactionConfirmKey = 'paperOrder' | 'paperCancel' | 'alertRuleChange' | 'portfolioRebalance';

export type TransactionConfirmations = Record<TransactionConfirmKey, boolean>;

export const DEFAULT_TRANSACTION_CONFIRMATIONS: TransactionConfirmations = {
  paperOrder: true,
  paperCancel: true,
  alertRuleChange: true,
  portfolioRebalance: true,
};

function extractPreferences(profile: Record<string, unknown> | null): Record<string, unknown> {
  const raw = profile?.preferences;
  return raw && typeof raw === 'object' && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
}

export function readTransactionConfirmations(profile: Record<string, unknown> | null): TransactionConfirmations {
  const prefs = extractPreferences(profile);
  const raw = prefs.transactionConfirmations;
  const stored = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw as Record<string, unknown> : {};
  return {
    paperOrder: stored.paperOrder !== false,
    paperCancel: stored.paperCancel !== false,
    alertRuleChange: stored.alertRuleChange !== false,
    portfolioRebalance: stored.portfolioRebalance !== false,
  };
}
