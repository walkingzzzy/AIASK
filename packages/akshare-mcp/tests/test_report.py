"""Functional test reporting to file"""
import asyncio
import asyncpg
import os
import datetime

async def run_tests():
    report_file = "functional_test_report.md"
    
    conn = await asyncpg.connect(
        user='postgres', password='postgres', 
        database='stockdb', host='localhost', port=5432
    )
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# Functional Test Report\n\n")
        
        try:
            # Test 1: Search Stock
            f.write("## Test 1: Search Stock (stock_code)\n")
            rows = await conn.fetch("""
                SELECT stock_code, stock_name, industry, market_cap
                FROM stocks
                WHERE stock_code LIKE $1 OR stock_name LIKE $2
            """, '%TEST%', '%TEST%')
            
            if len(rows) > 0 and rows[0]['stock_code'] == 'TEST001':
                f.write("- ✅ Success: Found stock by code/name\n")
                f.write(f"- Data: {dict(rows[0])}\n")
            else:
                f.write(f"- ❌ Failure: Expected TEST001, got {rows}\n")
            f.write("\n")

            # Test 2: Get Financials
            f.write("## Test 2: Financials (eps)\n")
            row = await conn.fetchrow("""
                 SELECT eps FROM financials
                 WHERE code = $1
                 ORDER BY report_date DESC
                 LIMIT 1
            """, 'TEST001')
            
            if row and row['eps'] == 1.5:
                f.write(f"- ✅ Success: Retrieved EPS value: {row['eps']}\n")
            else:
                f.write(f"- ❌ Failure: Expected 1.5, got {row['eps'] if row else 'None'}\n")
            f.write("\n")

            # Test 3: Sync Task Update
            f.write("## Test 3: Sync Task (updated_at)\n")
            try:
                await conn.execute("""
                    UPDATE sync_tasks 
                    SET status = 'completed', updated_at = NOW() 
                    WHERE task_id = $1
                """, 'TEST_TASK')
                f.write("- ✅ Success: Updated task status and updated_at column\n")
                
                # Verify update
                updated = await conn.fetchval("SELECT updated_at FROM sync_tasks WHERE task_id=$1", 'TEST_TASK')
                f.write(f"- Verified updated_at: {updated}\n")
            except Exception as e:
                f.write(f"- ❌ Failure: {e}\n")
            f.write("\n")
            
            # Test 4: Valuation (History Table)
            f.write("## Test 4: Valuation History Table\n")
            try:
                 await conn.execute("""
                    INSERT INTO valuation_history (stock_code, date, pe, pb, market_cap)
                    VALUES ($1, $2, $3, $4, $5)
                """, 'TEST001', datetime.date(2025, 1, 1), 20.0, 3.0, 100000000.0)
                 f.write("- ✅ Success: Inserted into valuation_history\n")
            except Exception as e:
                 f.write(f"- ❌ Failure: {e}\n")
            f.write("\n")

            # Test 5: Stock Quotes (Valuation Columns)
            f.write("## Test 5: Stock Quotes (Valuation Columns)\n")
            try:
                # Provide time as datetime with timezone
                # Provide date for valuation comparison
                # Note: stock_quotes PK is (time, code).
                # `valuation.py` queries: SELECT time, pe, pb, mkt_cap, price FROM stock_quotes
                await conn.execute("""
                    INSERT INTO stock_quotes (time, code, price, pe, pb, mkt_cap)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, datetime.datetime(2025, 1, 1, 10, 0, 0, tzinfo=datetime.timezone.utc), 
                     'TEST001', 100.0, 20.0, 3.0, 100000000.0)
                
                # Verify select
                row = await conn.fetchrow("""
                    SELECT pe, pb FROM stock_quotes WHERE code = $1 AND time = $2
                """, 'TEST001', datetime.datetime(2025, 1, 1, 10, 0, 0, tzinfo=datetime.timezone.utc))
                
                if row and row['pe'] == 20.0:
                    f.write("- ✅ Success: Inserted and Retrieved PE/PB from stock_quotes\n")
                else:
                    f.write(f"- ❌ Failure: Expected pe=20.0, got {row}\n")
                    
            except Exception as e:
                f.write(f"- ❌ Failure: {e}\n")

        finally:
            await conn.close()
            print(f"Report written to {report_file}")

if __name__ == '__main__':
    asyncio.run(run_tests())
