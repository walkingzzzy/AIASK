#!/usr/bin/env node
/**
 * 同步股票行业/板块信息（来自 akshare-mcp 的 get_stock_info）
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { callAkshareMcpTool } from '../src/adapters/akshare-mcp-client.js';

function normalizeDate(value: string | undefined): string | null {
    if (!value) return null;
    const raw = value.trim();
    if (!raw) return null;
    if (raw.includes('-')) return raw.slice(0, 10);
    const digits = raw.replace(/\D/g, '');
    if (digits.length === 8) {
        return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)}`;
    }
    return null;
}

async function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
    const args = process.argv.slice(2);
    const limit = parseInt(args[0] || '500', 10);
    const delay = parseInt(args[1] || '120', 10);
    const offset = parseInt(args[2] || '0', 10);

    console.log('='.repeat(70));
    console.log('行业/板块信息同步');
    console.log('='.repeat(70));
    console.log(`同步数量: ${limit}, 间隔: ${delay}ms, 偏移: ${offset}`);

    await timescaleDB.initialize();
    const res = await timescaleDB.query(
        `SELECT stock_code FROM stocks
         WHERE sector IS NULL OR sector = '' OR industry IS NULL OR industry = ''
         ORDER BY stock_code
         LIMIT $1 OFFSET $2`,
        [limit, offset]
    );
    const codes = res.rows.map((r: any) => r.stock_code);
    console.log(`待同步股票数: ${codes.length}`);

    let success = 0;
    let failed = 0;

    for (const code of codes) {
        try {
            const result = await callAkshareMcpTool<any>('get_stock_info', { stock_code: code });
            if (!result.success || !result.data) {
                failed += 1;
                continue;
            }

            const data = result.data;
            const raw = (data.raw && typeof data.raw === 'object') ? data.raw : {};
            const industry = String(
                data.industry || raw['所属行业'] || raw['行业'] || raw['细分行业'] || ''
            ).trim();
            const sector = String(
                raw['所属板块'] || raw['板块'] || industry || ''
            ).trim();
            const listDate = normalizeDate(String(data.listDate || raw['上市日期'] || raw['上市时间'] || ''));

            await timescaleDB.query(
                `UPDATE stocks
                 SET sector = COALESCE(NULLIF($1, ''), sector),
                     industry = COALESCE(NULLIF($2, ''), industry),
                     list_date = COALESCE(NULLIF($3, '')::date, list_date),
                     updated_at = NOW()
                 WHERE stock_code = $4`,
                [sector, industry, listDate, code]
            );

            success += 1;
            if (success % 100 === 0) {
                console.log(`已同步 ${success}/${codes.length}`);
            }
        } catch {
            failed += 1;
        }

        if (delay > 0) {
            await sleep(delay);
        }
    }

    console.log(`✅ 同步完成: 成功 ${success}, 失败 ${failed}`);
    await timescaleDB.close();
    process.exit(0);
}

main().catch(error => {
    console.error('❌ 同步失败:', error);
    process.exit(1);
});
