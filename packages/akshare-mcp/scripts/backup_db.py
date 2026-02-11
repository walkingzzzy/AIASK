"""Backup database tables to JSONL"""
import asyncio
import asyncpg
import json
import os
import datetime

async def backup_tables():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.getcwd(), 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    
    conn = await asyncpg.connect(
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'postgres'),
        database=os.getenv('DB_NAME', 'stockdb'),
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432'))
    )
    
    try:
        tables = ['stocks', 'financials', 'sync_tasks', 'watchlist']
        
        for table in tables:
            print(f"Backing up {table}...")
            filename = os.path.join(backup_dir, f"{table}_{timestamp}.jsonl")
            
            # Check if table exists
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                table
            )
            
            if not exists:
                print(f"Table {table} does not exist, skipping.")
                continue
                
            # Fetch all data
            # Handle potential large tables with cursor if needed, but for now fetch all is fine for these tables
            rows = await conn.fetch(f"SELECT * FROM {table}")
            
            with open(filename, 'w', encoding='utf-8') as f:
                for row in rows:
                    # Convert row to dict and handle datetimes
                    row_dict = dict(row)
                    for k, v in row_dict.items():
                        if isinstance(v, (datetime.date, datetime.datetime)):
                            row_dict[k] = v.isoformat()
                    
                    f.write(json.dumps(row_dict, ensure_ascii=False) + '\n')
            
            count = len(rows)
            print(f"Saved {count} rows to {filename}")
            
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(backup_tables())
