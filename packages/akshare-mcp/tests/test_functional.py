"""Functional test mimicking real tool queries"""
import asyncio
import asyncpg

async def run_tests():
    conn = await asyncpg.connect(
        user='postgres', password='postgres', 
        database='stockdb', host='localhost', port=5432
    )
    
    try:
        print("=== FUNCTIONAL TESTS ===")
        
        # Test 1: Search Stock (mimics search_stocks)
        print("\n[Test 1] Search Stock (using stock_code)...")
        rows = await conn.fetch("""
            SELECT stock_code, stock_name, industry, market_cap
            FROM stocks
            WHERE stock_code LIKE $1 OR stock_name LIKE $2
        """, '%TEST%', '%TEST%')
        
        if len(rows) > 0 and rows[0]['stock_code'] == 'TEST001':
            print("✅ PASS")
        else:
            print(f"❌ FAIL: Expected TEST001, got {rows}")

        # Test 2: Get Financials (mimics DDM valuation requirement)
        print("\n[Test 2] Get EPS (using financials.eps)...")
        row = await conn.fetchrow("""
             SELECT eps FROM financials
             WHERE code = $1
             ORDER BY report_date DESC
             LIMIT 1
        """, 'TEST001')
        
        if row and row['eps'] == 1.5:
            print("✅ PASS")
        else:
            print(f"❌ FAIL: Expected 1.5, got {row['eps'] if row else 'None'}")

        # Test 3: Sync Task Update (mimics data_sync_manager)
        print("\n[Test 3] Update Sync Task (using updated_at)...")
        try:
            await conn.execute("""
                UPDATE sync_tasks 
                SET status = 'completed', updated_at = NOW() 
                WHERE task_id = $1
            """, 'TEST_TASK')
            print("✅ PASS")
        except Exception as e:
            print(f"❌ FAIL: {e}")

    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(run_tests())
