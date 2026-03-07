"""Cleanup test data from database"""
import asyncio
import asyncpg

async def cleanup_data():
    conn = await asyncpg.connect(
        user='postgres', password='postgres', 
        database='stockdb', host='localhost', port=5432
    )
    
    try:
        print("Cleaning up test data...")
        await conn.execute("DELETE FROM stocks WHERE stock_code = 'TEST001'")
        await conn.execute("DELETE FROM financials WHERE code = 'TEST001'")
        await conn.execute("DELETE FROM stock_quotes WHERE code = 'TEST001'")
        await conn.execute("DELETE FROM valuation_history WHERE stock_code = 'TEST001'")
        await conn.execute("DELETE FROM sync_tasks WHERE task_id = 'TEST_TASK'")
        print("Cleanup completed.")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(cleanup_data())
