#!/usr/bin/env python3
"""
数据库数据质量审查脚本
检查项：
1. 表记录总数
2. 关键字段完整性 (NULL检查)
3. 数据新鲜度 (最新日期)
4. 业务逻辑一致性 (如K线覆盖率)
"""

import asyncio
import asyncpg
import os
import json
from datetime import datetime, date
from pathlib import Path

# 配置信息
DB_CONFIG = {
    'user': 'postgres',
    'password': 'stockdb123',
    'database': 'stockdb',
    'host': '127.0.0.1',
    'port': 5432
}

class DataAuditor:
    def __init__(self):
        self.conn = None
        self.report = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tables": {},
            "issues": []
        }
    
    async def connect(self):
        try:
            self.conn = await asyncpg.connect(**DB_CONFIG)
            print(f"✅ Connected to database {DB_CONFIG['database']}")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            raise

    async def close(self):
        if self.conn:
            await self.conn.close()

    def log_issue(self, level, message):
        print(f"[{level}] {message}")
        self.report["issues"].append({"level": level, "message": message})

    async def check_table_basics(self, table_name, time_col=None):
        """检查表的基本统计信息"""
        print(f"\nScanning table: {table_name}...")
        stats = {}
        
        # 1. 总行数
        count = await self.conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
        stats['count'] = count
        print(f"  - Total rows: {count}")
        
        if count == 0:
            self.log_issue("WARNING", f"Table {table_name} is empty")
            self.report["tables"][table_name] = stats
            return stats

        # 2. 如果是时间序列数据，检查时间范围
        if time_col:
            min_time = await self.conn.fetchval(f"SELECT MIN({time_col}) FROM {table_name}")
            max_time = await self.conn.fetchval(f"SELECT MAX({time_col}) FROM {table_name}")
            stats['min_time'] = str(min_time)
            stats['max_time'] = str(max_time)
            print(f"  - Time range: {min_time} to {max_time}")
            
            # 检查新鲜度 (例如最近3天是否有数据)
            if isinstance(max_time, (datetime, date)):
                today = date.today()
                last_date = max_time.date() if isinstance(max_time, datetime) else max_time
                days_diff = (today - last_date).days
                if days_diff > 5:  # 考虑到周末
                    self.log_issue("WARNING", f"Table {table_name} data might be stale. Last update: {last_date} ({days_diff} days ago)")
                else:
                    print(f"  - Data freshness: OK ({days_diff} days ago)")

        self.report["tables"][table_name] = stats
        return stats

    async def audit_stocks(self):
        """审计 stocks 表"""
        stats = await self.check_table_basics('stocks', time_col='updated_at')
        if stats['count'] > 0:
            # 检查关键字段 NULL 率
            null_names = await self.conn.fetchval("SELECT COUNT(*) FROM stocks WHERE stock_name IS NULL OR stock_name = ''")
            if null_names > 0:
                self.log_issue("ERROR", f"Stocks table has {null_names} rows with missing names")
            
            null_industry = await self.conn.fetchval("SELECT COUNT(*) FROM stocks WHERE industry IS NULL OR industry = ''")
            print(f"  - Stocks without industry: {null_industry}")

    async def audit_kline(self):
        """审计 kline_1d 表"""
        stats = await self.check_table_basics('kline_1d', time_col='time')
        if stats['count'] > 0:
            # 检查有多少只股票有K线数据
            unique_stocks = await self.conn.fetchval("SELECT COUNT(DISTINCT code) FROM kline_1d")
            total_stocks = await self.conn.fetchval("SELECT COUNT(*) FROM stocks")
            
            print(f"  - Unique stocks with K-line data: {unique_stocks} / {total_stocks}")
            coverage = unique_stocks / total_stocks if total_stocks > 0 else 0
            if coverage < 0.8: # 假设至少80%覆盖率
                self.log_issue("WARNING", f"Low K-line coverage: {coverage:.1%}")
            
            # 检查每只股票的平均记录数
            avg_counts = await self.conn.fetchval("SELECT AVG(cnt) FROM (SELECT code, COUNT(*) as cnt FROM kline_1d GROUP BY code) t")
            print(f"  - Average records per stock: {avg_counts:.1f}")

    async def audit_financials(self):
        """审计 financials 表"""
        stats = await self.check_table_basics('financials', time_col='report_date')
        if stats['count'] > 0:
             unique_stocks = await self.conn.fetchval("SELECT COUNT(DISTINCT stock_code) FROM financials")
             print(f"  - Unique stocks with financials: {unique_stocks}")

    async def audit_market_blocks(self):
         """审计板块数据"""
         stats = await self.check_table_basics('market_blocks', time_col='updated_at')
         # 检查板块类型分布
         rows = await self.conn.fetch("SELECT block_type, COUNT(*) as cnt FROM market_blocks GROUP BY block_type")
         print("  - Block types distribution:")
         for row in rows:
             print(f"    {row['block_type']}: {row['cnt']}")

    async def run(self):
        await self.connect()
        try:
            print("=== STARTING DATA QUALITY AUDIT ===")
            await self.audit_stocks()
            await self.audit_kline()
            await self.audit_financials()
            await self.audit_market_blocks()
            
            # 检查其他核心表是否为空
            other_tables = [
                'stock_quotes', 'north_fund_flow', 'dragon_tiger_list', 'macro_data', 
                'events'
            ]
            for table in other_tables:
                await self.check_table_basics(table)

            print("\n=== AUDIT COMPLETE ===")
            
            # 输出总结
            if self.report["issues"]:
                print("\n⚠️  ISSUES FOUND:")
                for issue in self.report["issues"]:
                    print(f"  [{issue['level']}] {issue['message']}")
            else:
                print("\n✅  NO CRITICAL ISSUES FOUND")
                
        finally:
            await self.close()

if __name__ == '__main__':
    auditor = DataAuditor()
    asyncio.run(auditor.run())
