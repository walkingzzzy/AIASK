#!/usr/bin/env node
/**
 * 数据库初始化脚本 - 免费数据源版本
 * 
 * 数据源:
 * - 股票列表: akshare-mcp
 * - K线数据: akshare-mcp
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { callAkshareMcpTool } from '../src/adapters/akshare-mcp-client.js';

interface StockInfo {
    code: string;
    name: string;
    market: string;
}

interface KlineData {
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

interface Progress {
    total: number;
    processed: number;
    success: number;
    failed: string[];
    klineRecords: number;
    startTime: number;
}

// ============ 工具函数 ============

const STOCK_LIMIT = parseInt(process.env.INIT_DB_STOCK_LIMIT || '0', 10);
const KLINE_DAYS = parseInt(process.env.INIT_DB_KLINE_DAYS || '250', 10);
const BATCH_SIZE = parseInt(process.env.INIT_DB_BATCH_SIZE || '10', 10);
const BATCH_DELAY_MS = parseInt(process.env.INIT_DB_BATCH_DELAY_MS || '2000', 10);

function log(msg: string) {
    const timestamp = new Date().toISOString().slice(11, 19);
    console.log(`[${timestamp}] ${msg}`);
}

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ============ 获取股票列表 (akshare-mcp) ============

function getMarketFromCode(code: string): string {
    if (code.startsWith('68')) return 'KCB';
    if (code.startsWith('30')) return 'CYB';
    if (code.startsWith('8') || code.startsWith('4')) return 'BJ';
    if (code.startsWith('6')) return 'SH';
    return 'SZ';
}

async function getStockListFromAkshare(): Promise<StockInfo[]> {
    log('从 akshare-mcp 获取全量A股股票列表...');
    const res = await callAkshareMcpTool<any>('get_stock_list', {});
    if (!res.success || !res.data) {
        throw new Error(res.error || '获取股票列表失败');
    }
    const list = Array.isArray(res.data) ? res.data : res.data.items || [];
    const stocks = list.map((item: any) => {
        const code = String(item.code || item['代码'] || item.symbol || '').replace(/^(SH|SZ|BJ|sh|sz|bj)/, '');
        return {
            code: code.padStart(6, '0'),
            name: String(item.name || item['名称'] || ''),
            market: getMarketFromCode(code),
        };
    }).filter((item: StockInfo) => item.code && item.name);
    if (STOCK_LIMIT > 0) {
        const limited = stocks.slice(0, STOCK_LIMIT);
        log(`成功获取 ${stocks.length} 只股票，回归模式截取 ${limited.length} 只`);
        return limited;
    }
    log(`成功获取 ${stocks.length} 只股票`);
    return stocks;
}

// ============ 获取K线数据 (akshare-mcp) ============

async function getKlineFromAkshare(code: string, days: number = KLINE_DAYS): Promise<KlineData[]> {
    const res = await callAkshareMcpTool<any>('get_kline', {
        stock_code: code,
        period: 'daily',
        limit: days,
    });
    if (!res.success || !res.data) return [];
    const items = Array.isArray(res.data) ? res.data : res.data.items || [];
    return items.map((k: any) => ({
        date: k.date,
        open: k.open,
        high: k.high,
        low: k.low,
        close: k.close,
        volume: k.volume,
    }));
}

// ============ 批量下载K线 ============

async function downloadKlines(stocks: StockInfo[], progress: Progress): Promise<void> {
    const batchSize = BATCH_SIZE > 0 ? BATCH_SIZE : 10;
    const batchDelay = Math.max(0, BATCH_DELAY_MS);
    
    log(`开始下载K线数据，共 ${stocks.length} 只股票`);
    log(`批次大小: ${batchSize}, 批次间隔: ${batchDelay}ms`);
    
    for (let i = 0; i < stocks.length; i += batchSize) {
        const batch = stocks.slice(i, i + batchSize);
        const batchNum = Math.floor(i / batchSize) + 1;
        const totalBatches = Math.ceil(stocks.length / batchSize);
        
        // 并行处理批次
        const promises = batch.map(async (stock) => {
            try {
                // 检查已有数据
                const existing = await timescaleDB.query(
                    'SELECT COUNT(*) as c FROM kline_1d WHERE code = $1',
                    [stock.code]
                );
                if (parseInt(existing.rows[0]?.c || '0') >= 200) {
                    progress.success++;
                    return;
                }
                
                // 获取K线
                const klines = await getKlineFromAkshare(stock.code, 250);
                if (klines.length === 0) {
                    progress.failed.push(stock.code);
                    return;
                }
                
                // 写入数据库
                const rows = klines.map(k => ({
                    code: stock.code,
                    date: new Date(k.date),
                    open: k.open,
                    high: k.high,
                    low: k.low,
                    close: k.close,
                    volume: k.volume,
                    amount: 0,
                    turnover: 0,
                    change_percent: 0
                }));
                
                const { inserted } = await timescaleDB.batchUpsertKline(rows);
                progress.klineRecords += inserted;
                progress.success++;
            } catch {
                progress.failed.push(stock.code);
            } finally {
                progress.processed++;
            }
        });
        
        await Promise.all(promises);
        
        // 显示进度
        const pct = ((progress.processed / progress.total) * 100).toFixed(1);
        const elapsed = Math.floor((Date.now() - progress.startTime) / 1000);
        const rate = progress.processed / elapsed || 0;
        const eta = rate > 0 ? Math.floor((progress.total - progress.processed) / rate) : 0;
        
        log(`[${batchNum}/${totalBatches}] ${progress.processed}/${progress.total} (${pct}%) | OK:${progress.success} FAIL:${progress.failed.length} | K线:${progress.klineRecords} | ETA:${eta}s`);
        
        // 批次间延迟
        if (i + batchSize < stocks.length) {
            await sleep(batchDelay);
        }
    }
}

// ============ 主流程 ============

async function main() {
    console.log('');
    console.log('========================================');
    console.log('  Database Init - Free Data Sources');
    console.log('========================================');
    console.log('');
    console.log('Data Sources:');
    console.log('  - Stock List: akshare-mcp');
    console.log('  - K-Line: akshare-mcp');
    console.log('');

    const progress: Progress = {
        total: 0,
        processed: 0,
        success: 0,
        failed: [],
        klineRecords: 0,
        startTime: Date.now()
    };

    try {
        // Step 1: Init DB
        log('Step 1/4: Init TimescaleDB...');
        await timescaleDB.initialize();
        log('DB initialized');

        // Step 2: Init default data
        log('Step 2/4: Init default data...');
        try {
            await timescaleDB.createPaperAccount('default', 'Default Account', 1000000);
            log('Default account created');
        } catch {
            log('Default account exists');
        }

        // Step 3: Get stock list
        log('Step 3/4: Get stock list...');
        const stocks = await getStockListFromAkshare();
        progress.total = stocks.length;

        // Save stocks to DB
        log('Saving stock info...');
        let saved = 0;
        for (const stock of stocks) {
            try {
                await timescaleDB.upsertStock(stock);
                saved++;
                if (saved % 500 === 0) {
                    log(`Saved ${saved}/${stocks.length} stocks`);
                }
            } catch (e) {
                // ignore
            }
        }
        log(`Saved ${saved}/${stocks.length} stocks`);

        // Step 4: Download K-lines
        log('Step 4/4: Download K-line data...');
        log('This may take 30-60 minutes...');
        await downloadKlines(stocks, progress);

        // Summary
        const totalTime = Math.floor((Date.now() - progress.startTime) / 1000 / 60);
        console.log('');
        console.log('========================================');
        console.log('  Init Complete!');
        console.log('========================================');
        console.log(`  Total Stocks: ${progress.total}`);
        console.log(`  Success: ${progress.success}`);
        console.log(`  Failed: ${progress.failed.length}`);
        console.log(`  K-Line Records: ${progress.klineRecords}`);
        console.log(`  Time: ${totalTime} min`);
        console.log('');
        console.log('Next: npm start');
        console.log('');

    } catch (error) {
        console.error('');
        console.error('Init failed:', error);
        process.exit(1);
    } finally {
        await timescaleDB.close();
    }
}

main();
