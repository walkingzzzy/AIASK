/**
 * 交易决策存储 - 记录 AI 建议和用户决策
 */

import Database from 'better-sqlite3';
import { app } from 'electron';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';

let db: Database.Database | null = null;

// 决策类型
export interface TradingDecision {
    id: string;
    stockCode: string;
    stockName?: string;
    decisionType: 'buy' | 'sell' | 'hold' | 'watch';
    source: 'ai' | 'user';
    confidence?: number;  // AI 置信度 (0-100)
    reason: string;
    targetPrice?: number;
    stopLoss?: number;
    createdAt: number;
    // 后续验证
    actualResult?: 'profit' | 'loss' | 'neutral';
    profitPercent?: number;
    verifiedAt?: number;
}

export type TradePlanStatus = 'planned' | 'executed' | 'cancelled';

export interface TradePlan {
    id: string;
    stockCode: string;
    action: 'buy' | 'sell';
    targetPrice?: number;
    stopLoss?: number;
    takeProfit?: number;
    quantity?: number;
    note?: string;
    status: TradePlanStatus;
    createdAt: number;
    updatedAt: number;
}

/**
 * 获取数据库路径
 */
function getDBPath(): string {
    const userDataPath = app.getPath('userData');
    return path.join(userDataPath, 'trading.db');
}

/**
 * 初始化数据库
 */
export function initTradingStore(): Database.Database {
    if (db) return db;

    const dbPath = getDBPath();
    console.log('[TradingStore] Database path:', dbPath);

    db = new Database(dbPath);

    // 创建表
    db.exec(`
        CREATE TABLE IF NOT EXISTS trading_decisions (
            id TEXT PRIMARY KEY,
            stock_code TEXT NOT NULL,
            stock_name TEXT,
            decision_type TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence REAL,
            reason TEXT NOT NULL,
            target_price REAL,
            stop_loss REAL,
            created_at INTEGER NOT NULL,
            actual_result TEXT,
            profit_percent REAL,
            verified_at INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_decision_stock ON trading_decisions(stock_code);
        CREATE INDEX IF NOT EXISTS idx_decision_date ON trading_decisions(created_at);
        CREATE INDEX IF NOT EXISTS idx_decision_source ON trading_decisions(source);

        CREATE TABLE IF NOT EXISTS trade_plans (
            id TEXT PRIMARY KEY,
            stock_code TEXT NOT NULL,
            action TEXT NOT NULL,
            target_price REAL,
            stop_loss REAL,
            take_profit REAL,
            quantity REAL,
            note TEXT,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_plan_stock ON trade_plans(stock_code);
        CREATE INDEX IF NOT EXISTS idx_plan_status ON trade_plans(status);
    `);

    console.log('[TradingStore] Database initialized');
    return db;
}

/**
 * 记录交易决策
 */
export function logDecision(decision: Omit<TradingDecision, 'id' | 'createdAt'>): string {
    if (!db) initTradingStore();

    const id = uuidv4();
    const now = Date.now();

    db!.prepare(`
        INSERT INTO trading_decisions 
        (id, stock_code, stock_name, decision_type, source, confidence, reason, target_price, stop_loss, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
        id,
        decision.stockCode,
        decision.stockName || null,
        decision.decisionType,
        decision.source,
        decision.confidence || null,
        decision.reason,
        decision.targetPrice || null,
        decision.stopLoss || null,
        now
    );

    return id;
}

/**
 * 获取决策列表
 */
export function getDecisions(options: {
    stockCode?: string;
    source?: 'ai' | 'user';
    startDate?: number;
    endDate?: number;
    limit?: number;
} = {}): TradingDecision[] {
    if (!db) initTradingStore();

    let sql = `
        SELECT id, stock_code as stockCode, stock_name as stockName, 
               decision_type as decisionType, source, confidence, reason,
               target_price as targetPrice, stop_loss as stopLoss,
               created_at as createdAt, actual_result as actualResult,
               profit_percent as profitPercent, verified_at as verifiedAt
        FROM trading_decisions
        WHERE 1=1
    `;
    const params: unknown[] = [];

    if (options.stockCode) {
        sql += ' AND stock_code = ?';
        params.push(options.stockCode);
    }
    if (options.source) {
        sql += ' AND source = ?';
        params.push(options.source);
    }
    if (options.startDate) {
        sql += ' AND created_at >= ?';
        params.push(options.startDate);
    }
    if (options.endDate) {
        sql += ' AND created_at <= ?';
        params.push(options.endDate);
    }

    sql += ' ORDER BY created_at DESC';

    if (options.limit) {
        sql += ' LIMIT ?';
        params.push(options.limit);
    }

    return db!.prepare(sql).all(...params) as TradingDecision[];
}

/**
 * 验证决策结果
 */
export function verifyDecision(
    decisionId: string,
    result: 'profit' | 'loss' | 'neutral',
    profitPercent?: number
): void {
    if (!db) initTradingStore();

    db!.prepare(`
        UPDATE trading_decisions 
        SET actual_result = ?, profit_percent = ?, verified_at = ?
        WHERE id = ?
    `).run(result, profitPercent || null, Date.now(), decisionId);
}

/**
 * 计算 AI 准确率统计
 */
export function getAIAccuracyStats(options: {
    startDate?: number;
    endDate?: number;
} = {}): {
    totalDecisions: number;
    verifiedDecisions: number;
    profitCount: number;
    lossCount: number;
    neutralCount: number;
    accuracyRate: number;
    avgProfitPercent: number;
    byDecisionType: Record<string, { total: number; profit: number; loss: number; accuracy: number }>;
} {
    if (!db) initTradingStore();

    let whereClause = "source = 'ai'";
    const params: unknown[] = [];

    if (options.startDate) {
        whereClause += ' AND created_at >= ?';
        params.push(options.startDate);
    }
    if (options.endDate) {
        whereClause += ' AND created_at <= ?';
        params.push(options.endDate);
    }

    // 总体统计
    const overall = db!.prepare(`
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN actual_result IS NOT NULL THEN 1 ELSE 0 END) as verified,
            SUM(CASE WHEN actual_result = 'profit' THEN 1 ELSE 0 END) as profit,
            SUM(CASE WHEN actual_result = 'loss' THEN 1 ELSE 0 END) as loss,
            SUM(CASE WHEN actual_result = 'neutral' THEN 1 ELSE 0 END) as neutral,
            AVG(CASE WHEN actual_result IS NOT NULL THEN profit_percent ELSE NULL END) as avgProfit
        FROM trading_decisions
        WHERE ${whereClause}
    `).get(...params) as any;

    // 按决策类型统计
    const byType = db!.prepare(`
        SELECT 
            decision_type as type,
            COUNT(*) as total,
            SUM(CASE WHEN actual_result = 'profit' THEN 1 ELSE 0 END) as profit,
            SUM(CASE WHEN actual_result = 'loss' THEN 1 ELSE 0 END) as loss
        FROM trading_decisions
        WHERE ${whereClause} AND actual_result IS NOT NULL
        GROUP BY decision_type
    `).all(...params) as any[];

    const byDecisionType: Record<string, { total: number; profit: number; loss: number; accuracy: number }> = {};
    for (const row of byType) {
        byDecisionType[row.type] = {
            total: row.total,
            profit: row.profit,
            loss: row.loss,
            accuracy: row.total > 0 ? (row.profit / row.total) * 100 : 0,
        };
    }

    const verified = overall.verified || 0;
    const profit = overall.profit || 0;

    return {
        totalDecisions: overall.total || 0,
        verifiedDecisions: verified,
        profitCount: profit,
        lossCount: overall.loss || 0,
        neutralCount: overall.neutral || 0,
        accuracyRate: verified > 0 ? (profit / verified) * 100 : 0,
        avgProfitPercent: overall.avgProfit || 0,
        byDecisionType,
    };
}

/**
 * 生成复盘报告
 */
export function generateReviewReport(options: {
    startDate: number;
    endDate: number;
}): {
    period: { start: number; end: number };
    summary: ReturnType<typeof getAIAccuracyStats>;
    decisions: TradingDecision[];
    insights: string[];
} {
    if (!db) initTradingStore();

    const summary = getAIAccuracyStats(options);
    const decisions = getDecisions({ ...options, limit: 100 });

    // 生成洞察
    const insights: string[] = [];

    if (summary.accuracyRate >= 60) {
        insights.push(`✅ AI 建议准确率表现良好 (${summary.accuracyRate.toFixed(1)}%)`);
    } else if (summary.accuracyRate < 40 && summary.verifiedDecisions >= 5) {
        insights.push(`⚠️ AI 建议准确率偏低 (${summary.accuracyRate.toFixed(1)}%)，建议谨慎参考`);
    }

    if (summary.avgProfitPercent > 5) {
        insights.push(`📈 平均盈利 ${summary.avgProfitPercent.toFixed(2)}%，策略有效`);
    } else if (summary.avgProfitPercent < -5) {
        insights.push(`📉 平均亏损 ${Math.abs(summary.avgProfitPercent).toFixed(2)}%，需调整策略`);
    }

    // 分析最佳决策类型
    const bestType = Object.entries(summary.byDecisionType)
        .filter(([_, stats]) => stats.total >= 3)
        .sort((a, b) => b[1].accuracy - a[1].accuracy)[0];

    if (bestType) {
        insights.push(`🎯 "${bestType[0]}" 类型决策准确率最高 (${bestType[1].accuracy.toFixed(1)}%)`);
    }

    return {
        period: { start: options.startDate, end: options.endDate },
        summary,
        decisions,
        insights,
    };
}

/**
 * 创建交易计划
 */
export function createTradePlan(plan: Omit<TradePlan, 'id' | 'createdAt' | 'updatedAt'>): string {
    if (!db) initTradingStore();

    const id = uuidv4();
    const now = Date.now();

    db!.prepare(`
        INSERT INTO trade_plans
        (id, stock_code, action, target_price, stop_loss, take_profit, quantity, note, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
        id,
        plan.stockCode,
        plan.action,
        plan.targetPrice ?? null,
        plan.stopLoss ?? null,
        plan.takeProfit ?? null,
        plan.quantity ?? null,
        plan.note ?? null,
        plan.status || 'planned',
        now,
        now
    );

    return id;
}

/**
 * 获取交易计划列表
 */
export function getTradePlans(options: {
    stockCode?: string;
    status?: TradePlanStatus;
    limit?: number;
} = {}): TradePlan[] {
    if (!db) initTradingStore();

    let sql = `
        SELECT id, stock_code as stockCode, action, target_price as targetPrice,
               stop_loss as stopLoss, take_profit as takeProfit, quantity, note,
               status, created_at as createdAt, updated_at as updatedAt
        FROM trade_plans
        WHERE 1=1
    `;
    const params: unknown[] = [];

    if (options.stockCode) {
        sql += ' AND stock_code = ?';
        params.push(options.stockCode);
    }
    if (options.status) {
        sql += ' AND status = ?';
        params.push(options.status);
    }

    sql += ' ORDER BY updated_at DESC';

    if (options.limit) {
        sql += ' LIMIT ?';
        params.push(options.limit);
    }

    return db!.prepare(sql).all(...params) as TradePlan[];
}

/**
 * 更新交易计划
 */
export function updateTradePlan(planId: string, updates: Partial<TradePlan>): void {
    if (!db) initTradingStore();

    const fields: string[] = [];
    const params: unknown[] = [];
    const mapping: Array<[keyof TradePlan, string]> = [
        ['stockCode', 'stock_code'],
        ['action', 'action'],
        ['targetPrice', 'target_price'],
        ['stopLoss', 'stop_loss'],
        ['takeProfit', 'take_profit'],
        ['quantity', 'quantity'],
        ['note', 'note'],
        ['status', 'status'],
    ];

    mapping.forEach(([key, column]) => {
        if (typeof updates[key] !== 'undefined') {
            fields.push(`${column} = ?`);
            params.push((updates as any)[key]);
        }
    });

    if (fields.length === 0) return;

    fields.push('updated_at = ?');
    params.push(Date.now());
    params.push(planId);

    db!.prepare(`
        UPDATE trade_plans
        SET ${fields.join(', ')}
        WHERE id = ?
    `).run(...params);
}

/**
 * 设置交易计划状态
 */
export function setTradePlanStatus(planId: string, status: TradePlanStatus): void {
    updateTradePlan(planId, { status });
}

/**
 * 删除交易计划
 */
export function removeTradePlan(planId: string): void {
    if (!db) initTradingStore();

    db!.prepare(`DELETE FROM trade_plans WHERE id = ?`).run(planId);
}

/**
 * 关闭数据库
 */
export function closeTradingStore(): void {
    if (db) {
        db.close();
        db = null;
        console.log('[TradingStore] Database closed');
    }
}
