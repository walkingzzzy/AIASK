"""Verify specific schema fixes"""
import asyncio
import asyncpg
import sys

async def verify_fix():
    conn = await asyncpg.connect(
        user='postgres', password='postgres', 
        database='stockdb', host='localhost', port=5432
    )
    
    try:
        print("=== VERIFICATION RESULTS ===")
        
        # 1. Stocks: Check for stock_code
        row = await conn.fetchrow("""
            SELECT 
                EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='stocks' AND column_name='stock_code') as has_col,
                EXISTS(SELECT 1 FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name WHERE tc.table_name = 'stocks' AND tc.constraint_type = 'PRIMARY KEY' AND kcu.column_name = 'stock_code') as is_pk
        """)
        print(f"Stocks.stock_code exists: {row['has_col']}")
        print(f"Stocks.stock_code is PK: {row['is_pk']}")

        # 2. Financials: Check for eps
        row = await conn.fetchval("""
            SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='financials' AND column_name='eps')
        """)
        print(f"Financials.eps exists: {row}")

        # 3. Sync Tasks: Check for updated_at
        row = await conn.fetchval("""
            SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='sync_tasks' AND column_name='updated_at')
        """)
        print(f"Sync_tasks.updated_at exists: {row}")

        # 4. New Tables
        valuation = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='valuation_history')")
        print(f"Table valuation_history exists: {valuation}")
        
        backtest = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='backtest_results')")
        print(f"Table backtest_results exists: {backtest}")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(verify_fix())
