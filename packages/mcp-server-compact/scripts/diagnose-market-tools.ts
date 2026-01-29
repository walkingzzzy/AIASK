#!/usr/bin/env node
/**
 * 诊断脚本：验证盘口/成交明细/涨停数据入口是否可用
 */

import { adapterManager } from '../src/adapters/index.js';

function logTitle(title: string) {
    console.log('\n' + '='.repeat(70));
    console.log(title);
    console.log('='.repeat(70));
}

function formatValue(value: unknown) {
    if (value === null || value === undefined) return 'N/A';
    if (Array.isArray(value)) return `Array(${value.length})`;
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
}

async function main() {
    const args = process.argv.slice(2);
    const getArg = (key: string) => {
        const idx = args.indexOf(key);
        return idx >= 0 ? args[idx + 1] : undefined;
    };
    const only = getArg('--only');
    const positional: string[] = [];
    const skipKeys = new Set(['--only', '--code', '--date', '--limit']);
    for (let i = 0; i < args.length; i += 1) {
        const current = args[i];
        if (current.startsWith('--')) {
            if (skipKeys.has(current)) {
                const next = args[i + 1];
                if (next && !next.startsWith('--')) {
                    i += 1;
                }
            }
            continue;
        }
        positional.push(current);
    }
    const code = getArg('--code') || positional[0] || '600519';
    const date = getArg('--date') || positional[1] || new Date().toISOString().slice(0, 10);
    const limit = parseInt(getArg('--limit') || positional[2] || '20', 10);

    console.log('诊断参数:');
    console.log(`  股票代码: ${code}`);
    console.log(`  日期: ${date}`);
    console.log(`  成交明细条数: ${limit}`);

    if (!only || only === 'order_book') {
        logTitle('1) 盘口数据');
        const orderBookRes = await adapterManager.getOrderBook(code);
        if (orderBookRes.success && orderBookRes.data) {
            const { bids, asks } = orderBookRes.data;
            console.log(`✅ 成功 (source=${orderBookRes.source || 'unknown'})`);
            console.log(`  买盘: ${formatValue(bids?.slice(0, 3))}`);
            console.log(`  卖盘: ${formatValue(asks?.slice(0, 3))}`);
        } else {
            console.log(`❌ 失败: ${orderBookRes.error}`);
        }
    }

    if (!only || only === 'trades') {
        logTitle('2) 成交明细');
        const tradeRes = await adapterManager.getTradeDetails(code, limit);
        if (tradeRes.success && tradeRes.data) {
            console.log(`✅ 成功 (source=${tradeRes.source || 'unknown'})`);
            console.log(`  返回条数: ${tradeRes.data.length}`);
            console.log(`  样例: ${formatValue(tradeRes.data[0])}`);
        } else {
            console.log(`❌ 失败: ${tradeRes.error}`);
        }
    }

    if (!only || only === 'limit_up') {
        logTitle('3) 涨停板数据');
        const limitUpRes = await adapterManager.getLimitUpStocks(date);
        if (limitUpRes.success && limitUpRes.data) {
            console.log(`✅ 成功 (source=${limitUpRes.source || 'unknown'})`);
            console.log(`  返回条数: ${limitUpRes.data.length}`);
            console.log(`  样例: ${formatValue(limitUpRes.data[0])}`);
        } else {
            console.log(`❌ 失败: ${limitUpRes.error}`);
        }
    }

    if (!only || only === 'limit_up_stats') {
        logTitle('4) 涨停统计');
        const limitUpStatsRes = await adapterManager.getLimitUpStatistics(date);
        if (limitUpStatsRes.success && limitUpStatsRes.data) {
            console.log(`✅ 成功 (source=${limitUpStatsRes.source || 'unknown'})`);
            console.log(`  统计: ${formatValue(limitUpStatsRes.data)}`);
        } else {
            console.log(`❌ 失败: ${limitUpStatsRes.error}`);
        }
    }
}

main().then(() => {
    process.exit(0);
}).catch(error => {
    console.error('诊断失败:', error);
    process.exit(1);
});
