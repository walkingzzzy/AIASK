/**
 * 用户配置存储
 */

import Database from 'better-sqlite3';
import { app } from 'electron';
import path from 'path';

let db: Database.Database | null = null;

export interface UserConfig {
  aiModel: 'claude' | 'gpt-4' | 'local';
  apiKey?: string;
  apiBaseUrl?: string;
  apiModel?: string;
  riskTolerance: 'conservative' | 'moderate' | 'aggressive';
  investmentStyle: 'value' | 'growth' | 'momentum' | 'mixed';
  preferredSectors: string[];
  theme: 'light' | 'dark' | 'system';
  profileParams?: {
    stopLoss: number;
    takeProfit: number;
    maxPosition: number;
    riskScore: number;
    riskType: string;
    experience: string;
    investPeriod: string;
    style: string;
  };
  notificationPreferences?: {
    enabled: boolean;
    quietHours?: number[];
    maxDaily?: number;
    channels?: string[];
  };
}

export interface BehaviorSummary {
  periodDays: number;
  totalEvents: number;
  topTools: Array<{ name: string; count: number }>;
  topStocks: Array<{ code: string; count: number }>;
  recentQueries: string[];
  activeHours: number[];
}

export interface WatchlistMeta {
  stockCode: string;
  costPrice?: number | null;
  targetPrice?: number | null;
  stopLoss?: number | null;
  note?: string | null;
  updatedAt: number;
}

const DEFAULT_CONFIG: UserConfig = {
  aiModel: 'gpt-4',
  riskTolerance: 'moderate',
  investmentStyle: 'mixed',
  preferredSectors: [],
  theme: 'system',
  apiBaseUrl: '',
  apiModel: '',
  profileParams: {
    stopLoss: 8,
    takeProfit: 15,
    maxPosition: 20,
    riskScore: 50,
    riskType: '平衡型',
    experience: '中级',
    investPeriod: '中期',
    style: '平衡',
  },
  notificationPreferences: {
    enabled: true,
    quietHours: [22, 23, 0, 1, 2, 3, 4, 5, 6],
    maxDaily: 20,
    channels: ['desktop'],
  },
};

/**
 * 获取数据库路径
 */
function getDBPath(): string {
  const userDataPath = app.getPath('userData');
  return path.join(userDataPath, 'user.db');
}

/**
 * 初始化用户配置数据库
 */
export function initUserStore(): Database.Database {
  if (db) return db;

  const dbPath = getDBPath();
  console.log('[UserStore] Database path:', dbPath);

  db = new Database(dbPath);

  // 创建表
  db.exec(`
    CREATE TABLE IF NOT EXISTS user_config (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS watchlist (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      stock_code TEXT NOT NULL UNIQUE,
      added_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS behavior_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_type TEXT NOT NULL,
      tool_name TEXT,
      stock_code TEXT,
      query TEXT,
      created_at INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS watchlist_meta (
      stock_code TEXT PRIMARY KEY,
      cost_price REAL,
      target_price REAL,
      stop_loss REAL,
      note TEXT,
      updated_at INTEGER NOT NULL
    );
  `);

  console.log('[UserStore] Database initialized');
  return db;
}

/**
 * 获取用户配置
 */
export function getConfig(): UserConfig {
  if (!db) initUserStore();

  const row = db!.prepare(`SELECT value FROM user_config WHERE key = ?`).get('user_config') as { value: string } | undefined;

  if (row) {
    return { ...DEFAULT_CONFIG, ...JSON.parse(row.value) };
  }

  return DEFAULT_CONFIG;
}

/**
 * 保存用户配置
 */
export function saveConfig(config: Partial<UserConfig>): void {
  if (!db) initUserStore();

  console.log('[UserStore] Saving config:', config);

  const currentConfig = getConfig();
  const newConfig = { ...currentConfig, ...config };
  const now = Date.now();

  db!.prepare(`
    INSERT OR REPLACE INTO user_config (key, value, updated_at)
    VALUES (?, ?, ?)
  `).run('user_config', JSON.stringify(newConfig), now);

  console.log('[UserStore] Config saved. New full config:', newConfig);
}

/**
 * 获取自选股列表
 */
export function getWatchlist(): string[] {
  if (!db) initUserStore();

  const rows = db!.prepare(`SELECT stock_code FROM watchlist ORDER BY added_at DESC`).all() as { stock_code: string }[];
  return rows.map(r => r.stock_code);
}

/**
 * 添加自选股
 */
export function addToWatchlist(stockCode: string): void {
  if (!db) initUserStore();

  db!.prepare(`
    INSERT OR IGNORE INTO watchlist (stock_code, added_at)
    VALUES (?, ?)
  `).run(stockCode, Date.now());
}

/**
 * 从自选股移除
 */
export function removeFromWatchlist(stockCode: string): void {
  if (!db) initUserStore();

  db!.prepare(`DELETE FROM watchlist WHERE stock_code = ?`).run(stockCode);
}

/**
 * 获取自选股元数据
 */
export function getWatchlistMeta(stockCode?: string): WatchlistMeta[] {
  if (!db) initUserStore();

  if (stockCode) {
    const row = db!.prepare(`
      SELECT stock_code as stockCode, cost_price as costPrice, target_price as targetPrice,
             stop_loss as stopLoss, note, updated_at as updatedAt
      FROM watchlist_meta WHERE stock_code = ?
    `).get(stockCode) as WatchlistMeta | undefined;
    return row ? [row] : [];
  }

  return db!.prepare(`
    SELECT stock_code as stockCode, cost_price as costPrice, target_price as targetPrice,
           stop_loss as stopLoss, note, updated_at as updatedAt
    FROM watchlist_meta
    ORDER BY updated_at DESC
  `).all() as WatchlistMeta[];
}

/**
 * 保存自选股元数据
 */
export function upsertWatchlistMeta(meta: {
  stockCode: string;
  costPrice?: number;
  targetPrice?: number;
  stopLoss?: number;
  note?: string;
}): void {
  if (!db) initUserStore();

  db!.prepare(`
    INSERT OR REPLACE INTO watchlist_meta
      (stock_code, cost_price, target_price, stop_loss, note, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(
    meta.stockCode,
    meta.costPrice ?? null,
    meta.targetPrice ?? null,
    meta.stopLoss ?? null,
    meta.note ?? null,
    Date.now()
  );
}

/**
 * 删除自选股元数据
 */
export function removeWatchlistMeta(stockCode: string): void {
  if (!db) initUserStore();

  db!.prepare(`DELETE FROM watchlist_meta WHERE stock_code = ?`).run(stockCode);
}

/**
 * 记录行为事件
 */
export function recordBehaviorEvent(event: {
  eventType: 'query' | 'tool_call';
  toolName?: string;
  stockCode?: string;
  query?: string;
}): void {
  if (!db) initUserStore();

  db!.prepare(`
    INSERT INTO behavior_events (event_type, tool_name, stock_code, query, created_at)
    VALUES (?, ?, ?, ?, ?)
  `).run(
    event.eventType,
    event.toolName || null,
    event.stockCode || null,
    event.query || null,
    Date.now()
  );
}

/**
 * 获取行为摘要
 */
export function getBehaviorSummary(days: number = 30): BehaviorSummary {
  if (!db) initUserStore();

  const since = Date.now() - days * 24 * 60 * 60 * 1000;
  const totalRow = db!.prepare(`
    SELECT COUNT(*) as total FROM behavior_events WHERE created_at >= ?
  `).get(since) as { total: number };

  const topTools = db!.prepare(`
    SELECT tool_name as name, COUNT(*) as count
    FROM behavior_events
    WHERE event_type = 'tool_call' AND tool_name IS NOT NULL AND created_at >= ?
    GROUP BY tool_name
    ORDER BY count DESC
    LIMIT 5
  `).all(since) as Array<{ name: string; count: number }>;

  const topStocks = db!.prepare(`
    SELECT stock_code as code, COUNT(*) as count
    FROM behavior_events
    WHERE stock_code IS NOT NULL AND created_at >= ?
    GROUP BY stock_code
    ORDER BY count DESC
    LIMIT 5
  `).all(since) as Array<{ code: string; count: number }>;

  const recentQueries = (db!.prepare(`
    SELECT query FROM behavior_events
    WHERE event_type = 'query' AND query IS NOT NULL AND created_at >= ?
    ORDER BY created_at DESC
    LIMIT 5
  `).all(since) as Array<{ query: string }>).map(row => row.query);

  const hourRows = db!.prepare(`
    SELECT created_at FROM behavior_events WHERE created_at >= ?
  `).all(since) as Array<{ created_at: number }>;

  const activeHours = Array.from({ length: 24 }).map(() => 0);
  for (const row of hourRows) {
    const hour = new Date(row.created_at).getHours();
    activeHours[hour] += 1;
  }

  return {
    periodDays: days,
    totalEvents: totalRow.total || 0,
    topTools,
    topStocks,
    recentQueries,
    activeHours,
  };
}

/**
 * 关闭数据库
 */
export function closeUserStore(): void {
  if (db) {
    db.close();
    db = null;
    console.log('[UserStore] Database closed');
  }
}
