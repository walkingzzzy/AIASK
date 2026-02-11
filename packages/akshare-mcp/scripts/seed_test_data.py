"""Seed database with test data"""
import asyncio
import asyncpg
import datetime

async def seed_data():
    conn = await asyncpg.connect(
        user='postgres', password='postgres', 
        database='stockdb', host='localhost', port=5432
    )
    
    try:
        print("Cleaning up old test data...")
        await conn.execute("DELETE FROM financials WHERE code = 'TEST001'")
        await conn.execute("DELETE FROM stocks WHERE stock_code = 'TEST001'")
        await conn.execute("DELETE FROM sync_tasks WHERE task_id = 'TEST_TASK'")
        
        print("Inserting test stock...")
        # Testing 'stock_code' column and PK. Also inserting 'code' for legacy compatibility.
        await conn.execute("""
            INSERT INTO stocks (stock_code, code, stock_name, industry, market_cap, pe_ratio, pb_ratio)
            VALUES ($1, $1, $2, $3, $4, $5, $6)
        """, 'TEST001', 'Test Stock A', 'Technology', 100000000.0, 20.5, 3.2)
        
        print("Inserting test financials...")
        # Testing 'eps' column
        await conn.execute("""
            INSERT INTO financials (code, report_date, revenue, net_profit, eps)
            VALUES ($1, $2, $3, $4, $5)
        """, 'TEST001', datetime.date(2025, 12, 31), 50000000.0, 10000000.0, 1.5)
        
        print("Inserting test sync task...")
        # Testing 'updated_at' column
        await conn.execute("""
            INSERT INTO sync_tasks (task_id, task_type, status, updated_at)
            VALUES ($1, $2, $3, NOW())
        """, 'TEST_TASK', 'daily_sync', 'pending')
        
        print("Seed data inserted successfully.")
        
    except Exception as e:
        print(f"Error seeding data: {e}")
        raise e
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(seed_data())
