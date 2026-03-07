"""Execute SQL script file"""
import asyncio
import asyncpg
import os
import sys

async def run_sql_script(script_path):
    if not os.path.exists(script_path):
        print(f"Error: File {script_path} not found")
        return

    print(f"Reading SQL from {script_path}...")
    with open(script_path, 'r', encoding='utf-8') as f:
        sql = f.read()

    conn = await asyncpg.connect(
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'postgres'),
        database=os.getenv('DB_NAME', 'stockdb'),
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432'))
    )
    
    try:
        print("Executing SQL...")
        # asyncpg executes multiple statements if separated by semicolon? 
        # Actually asyncpg.execute can handle blocks.
        # But for DO blocks and multiple statements it's safer to execute as a simple query or split?
        # asyncpg.connection.execute(query, *args, timeout=None)
        # "Executes the SQL statement... If multiple statements are provided, they are executed in a single transaction."
        
        await conn.execute(sql)
        print("SQL execution completed successfully.")
            
    except Exception as e:
        print(f"Error executing SQL: {e}")
            
    finally:
        await conn.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python run_sql_script.py <path_to_sql_file>")
        sys.exit(1)
        
    script_file = sys.argv[1]
    asyncio.run(run_sql_script(script_file))
