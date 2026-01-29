#!/usr/bin/env node
/**
 * 数据补充脚本
 * 通过 akshare-mcp 统一数据出口补充缺失的数据
 * 
 * 补充内容：
 * 1. 龙虎榜数据 (akshare-mcp)
 * 2. 大宗交易数据 (akshare-mcp)
 * 3. 北向资金数据 (akshare-mcp)
 * 4. 缺失的K线数据 (akshare-mcp)
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { adapterManager } from '../src/adapters/index.js';
import { callAkshareMcpTool } from '../src/adapters/akshare-mcp-client.js';

interface Progress {
    dragonTiger: number;
    northFund: number;
    blockTrade: number;
    klineSupplemented: number;
    errors: string[];
    startTime: number;
}

const SUPPLEMENT_DAYS = parseInt(process.env.SUPPLEMENT_DAYS || '30', 10);
const NORTH_FUND_DAYS = parseInt(process.env.SUPPLEMENT_NORTH_FUND_DAYS || '90', 10);
const KLINE_STOCK_LIMIT = parseInt(process.env.SUPPLEMENT_KLINE_STOCK_LIMIT || '0', 10);
const SKIP_DRAGON_TIGER = ['1', 'true', 'yes', 'y'].includes(String(process.env.SUPPLEMENT_SKIP_DRAGON_TIGER || '').toLowerCase());
const SKIP_BLOCK_TRADES = ['1', 'true', 'yes', 'y'].includes(String(process.env.SUPPLEMENT_SKIP_BLOCK_TRADES || '').toLowerCase());
const SKIP_NORTH_FUND = ['1', 'true', 'yes', 'y'].includes(String(process.env.SUPPLEMENT_SKIP_NORTH_FUND || '').toLowerCase());
const SKIP_KLINE = ['1', 'true', 'yes', 'y'].includes(String(process.env.SUPPLEMENT_SKIP_KLINE || '').toLowerCase());

function log(msg: string) {
    const timestamp = new Date().toISOString().slice(11, 19);
    console.log(`[${timestamp}] ${msg}`);
}

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 补充龙虎榜数据 (东方财富)
 */
async function supplementDragonTiger(progress: Progress): Promise<void> {
    log('📊 补充龙虎榜数据 (akshare-mcp)...');
    
    const days = SUPPLEMENT_DAYS; // 最近N个交易日
    if (days <= 0) {
        log('⏭️  跳过龙虎榜补充（SUPPLEMENT_DAYS=0）');
        return;
    }
    const today = new Date();
    
    for (let i = 0; i < days; i++) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        const displayDate = date.toISOString().split('T')[0];
        const dateStr = displayDate.replace(/-/g, '');
        
        // 跳过周末
        const dayOfWeek = date.getDay();
        if (dayOfWeek === 0 || dayOfWeek === 6) continue;
        
        try {
            const existing = await timescaleDB.query(
                'SELECT COUNT(*) as c FROM dragon_tiger WHERE date = $1',
                [displayDate]
            );
            if (parseInt(existing.rows[0]?.c || '0') > 0) {
                continue;
            }

            const res = await callAkshareMcpTool<any>('get_dragon_tiger', { date: displayDate });
            const data = res.success && res.data ? (Array.isArray(res.data) ? res.data : res.data.items || []) : [];
            if (!data || data.length === 0) {
                continue;
            }

            for (const item of data) {
                const buyAmount = Number(item.buyAmount || item.buy_amount || 0) || 0;
                const sellAmount = Number(item.sellAmount || item.sell_amount || 0) || 0;

                await timescaleDB.query(
                    `INSERT INTO dragon_tiger (date, code, name, reason, buy_amount, sell_amount, net_amount, total_amount)
                     VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                     ON CONFLICT (date, code) DO UPDATE SET
                     name = EXCLUDED.name, reason = EXCLUDED.reason,
                     buy_amount = EXCLUDED.buy_amount, sell_amount = EXCLUDED.sell_amount,
                     net_amount = EXCLUDED.net_amount, total_amount = EXCLUDED.total_amount`,
                    [
                        displayDate,
                        item.code,
                        item.name,
                        item.reason || '',
                        buyAmount,
                        sellAmount,
                        buyAmount - sellAmount,
                        buyAmount + sellAmount,
                    ]
                );
            }

            progress.dragonTiger += data.length;
            log(`  ${displayDate}: ${data.length} 条`);
        } catch (error: any) {
            progress.errors.push(`龙虎榜 ${displayDate}: ${error.message || error}`);
        }
        
        await sleep(500);
    }
    
    log(`✅ 龙虎榜补充完成: ${progress.dragonTiger} 条`);
}

/**
 * 补充大宗交易数据 (东方财富)
 */
async function supplementBlockTrades(progress: Progress): Promise<void> {
    log('📦 补充大宗交易数据 (akshare-mcp)...');
    
    const days = SUPPLEMENT_DAYS;
    if (days <= 0) {
        log('⏭️  跳过大宗交易补充（SUPPLEMENT_DAYS=0）');
        return;
    }
    const today = new Date();
    
    for (let i = 0; i < days; i++) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        const displayDate = date.toISOString().split('T')[0];
        
        // 跳过周末
        const dayOfWeek = date.getDay();
        if (dayOfWeek === 0 || dayOfWeek === 6) continue;
        
        try {
            const existing = await timescaleDB.query(
                'SELECT COUNT(*) as c FROM block_trades WHERE date = $1',
                [displayDate]
            );
            if (parseInt(existing.rows[0]?.c || '0') > 0) {
                continue;
            }

            const res = await callAkshareMcpTool<any>('get_block_trades', { date: displayDate });
            const data = res.success && res.data ? (Array.isArray(res.data) ? res.data : res.data.items || []) : [];
            if (!data || data.length === 0) {
                continue;
            }

            for (const item of data) {
                await timescaleDB.query(
                    `INSERT INTO block_trades (date, code, name, price, volume, amount, buyer, seller, premium_rate)
                     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                     ON CONFLICT (date, code, buyer, seller) DO NOTHING`,
                    [
                        displayDate,
                        item.code,
                        item.name,
                        Number(item.price || 0),
                        Number(item.volume || 0),
                        Number(item.amount || 0),
                        item.buyer || '',
                        item.seller || '',
                        Number(item.premium || item.premium_rate || 0),
                    ]
                );
            }

            progress.blockTrade += data.length;
            log(`  ${displayDate}: ${data.length} 条`);
        } catch (error: any) {
            progress.errors.push(`大宗交易 ${displayDate}: ${error.message || error}`);
        }
        
        await sleep(500);
    }
    
    log(`✅ 大宗交易补充完成: ${progress.blockTrade} 条`);
}

/**
 * 补充北向资金数据 (Tushare)
 */
async function supplementNorthFund(progress: Progress): Promise<void> {
    log('🌏 补充北向资金数据 (akshare-mcp)...');
    
    const days = NORTH_FUND_DAYS;
    if (days <= 0) {
        log('⏭️  跳过北向资金补充（SUPPLEMENT_NORTH_FUND_DAYS=0）');
        return;
    }
    try {
        const res = await callAkshareMcpTool<any>('get_north_fund', { days });
        const data = res.success && res.data ? (Array.isArray(res.data) ? res.data : res.data.items || []) : [];
        if (!data || data.length === 0) {
            log('⚠️  北向资金暂无可用数据');
            return;
        }

        for (const item of data) {
            const displayDate = String(item.date || '');
            if (!displayDate) continue;

            const existing = await timescaleDB.query(
                'SELECT COUNT(*) as c FROM north_fund WHERE date = $1',
                [displayDate]
            );
            if (parseInt(existing.rows[0]?.c || '0') > 0) {
                continue;
            }

            const shBalance = item.shCumulative ?? item.cumulative ?? null;
            const szBalance = item.szCumulative ?? item.cumulative ?? null;

            await timescaleDB.query(
                `INSERT INTO north_fund (date, hk_to_sh, hk_to_sz, total, hk_to_sh_balance, hk_to_sz_balance)
                 VALUES ($1, $2, $3, $4, $5, $6)
                 ON CONFLICT (date) DO UPDATE SET
                 hk_to_sh = EXCLUDED.hk_to_sh, hk_to_sz = EXCLUDED.hk_to_sz,
                 total = EXCLUDED.total, hk_to_sh_balance = EXCLUDED.hk_to_sh_balance,
                 hk_to_sz_balance = EXCLUDED.hk_to_sz_balance`,
                [
                    displayDate,
                    Number(item.shConnect || 0),
                    Number(item.szConnect || 0),
                    Number(item.total || 0),
                    shBalance,
                    szBalance,
                ]
            );

            progress.northFund++;
        }

        log(`✅ 北向资金补充完成: ${progress.northFund} 条`);
    } catch (error: any) {
        progress.errors.push(`北向资金: ${error.message || error}`);
    }
}

/**
 * 补充缺失的日线K线数据
 */
async function supplementDailyKline(progress: Progress): Promise<void> {
    log('📈 补充缺失的日线K线数据...');
    if (SKIP_KLINE) {
        log('⏭️  跳过K线补充（SUPPLEMENT_SKIP_KLINE=1）');
        return;
    }
    
    // 找出K线数据少于100条的股票
    const result = await timescaleDB.query(`
        SELECT s.stock_code as code 
        FROM stocks s 
        LEFT JOIN (
            SELECT code, COUNT(*) as cnt FROM kline_1d GROUP BY code
        ) k ON s.stock_code = k.code
        WHERE COALESCE(k.cnt, 0) < 100
        ORDER BY s.stock_code
    `);
    
    const stocks = result.rows.map((r: any) => r.code);
    log(`  发现 ${stocks.length} 只股票K线数据不完整`);
    
    if (stocks.length === 0) {
        log('✅ 所有股票K线数据完整');
        return;
    }

    const targetStocks = KLINE_STOCK_LIMIT > 0 ? stocks.slice(0, KLINE_STOCK_LIMIT) : stocks;
    if (KLINE_STOCK_LIMIT > 0) {
        log(`  回归模式截取 ${targetStocks.length} 只股票进行补齐`);
    }
    
    const batchSize = 10;
    for (let i = 0; i < targetStocks.length; i += batchSize) {
        const batch = targetStocks.slice(i, i + batchSize);
        
        await Promise.all(batch.map(async (code: string) => {
            try {
                const response = await adapterManager.getKline(code, 'daily', 250);
                
                if (!response.success || !response.data || response.data.length === 0) {
                    return;
                }
                
                for (const k of response.data) {
                    await timescaleDB.query(
                        `INSERT INTO kline_1d (code, date, open, high, low, close, volume, amount, turnover, change_percent)
                         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                         ON CONFLICT (code, date) DO NOTHING`,
                        [code, new Date(k.date), k.open, k.high, k.low, k.close, k.volume, k.amount || 0, 0, 0]
                    );
                }
                
                progress.klineSupplemented += response.data.length;
                
            } catch (error) {
                // 静默失败
            }
        }));
        
        const percent = ((i + batch.length) / targetStocks.length * 100).toFixed(1);
        log(`  ${i + batch.length}/${targetStocks.length} (${percent}%)`);
        
        await sleep(1000);
    }
    
    log(`✅ K线补充完成: ${progress.klineSupplemented} 条`);
}

async function main() {
    console.log('');
    console.log('========================================');
    console.log('  数据补充脚本');
    console.log('========================================');
    console.log('');
    console.log('数据源: akshare-mcp');
    console.log('');

    const progress: Progress = {
        dragonTiger: 0,
        northFund: 0,
        blockTrade: 0,
        klineSupplemented: 0,
        errors: [],
        startTime: Date.now()
    };

    try {
        await timescaleDB.initialize();
        
        // 补充各类数据
        if (SKIP_DRAGON_TIGER) {
            log('⏭️  跳过龙虎榜补充（SUPPLEMENT_SKIP_DRAGON_TIGER=1）');
        } else {
            await supplementDragonTiger(progress);
        }

        if (SKIP_BLOCK_TRADES) {
            log('⏭️  跳过大宗交易补充（SUPPLEMENT_SKIP_BLOCK_TRADES=1）');
        } else {
            await supplementBlockTrades(progress);
        }

        if (SKIP_NORTH_FUND) {
            log('⏭️  跳过北向资金补充（SUPPLEMENT_SKIP_NORTH_FUND=1）');
        } else {
            await supplementNorthFund(progress);
        }

        await supplementDailyKline(progress);
        
        // 总结
        const totalTime = Math.floor((Date.now() - progress.startTime) / 1000 / 60);
        console.log('');
        console.log('========================================');
        console.log('  补充完成!');
        console.log('========================================');
        console.log(`  龙虎榜: ${progress.dragonTiger} 条`);
        console.log(`  大宗交易: ${progress.blockTrade} 条`);
        console.log(`  北向资金: ${progress.northFund} 条`);
        console.log(`  K线补充: ${progress.klineSupplemented} 条`);
        console.log(`  耗时: ${totalTime} 分钟`);
        if (progress.errors.length > 0) {
            console.log(`  错误: ${progress.errors.length} 个`);
            progress.errors.slice(0, 5).forEach(e => console.log(`    - ${e}`));
        }
        console.log('');

    } catch (error) {
        console.error('补充失败:', error);
        process.exit(1);
    } finally {
        await timescaleDB.close();
    }
}

main();
