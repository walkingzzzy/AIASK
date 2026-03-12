
import asyncio
import asyncpg
import os
import sys

async def check_connection(user, password, db, host, port):
    print(f"Testing connection to {host}:{port} as {user} for {db}...")
    conn = None
    try:
        conn = await asyncpg.connect(
            user=user,
            password=password,
            database=db,
            host=host,
            port=port,
            timeout=5
        )
        await conn.execute("SELECT 1")
        print(f"✅ Connection successful!")
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
    finally:
        if conn is not None:
            await conn.close()

async def main():
    # Candidates for credentials
    configs = [
        # From .env
        {
            "user": "postgres",
            "password": "stockdb123", # From .env
        },
        # Default
        {
            "user": "postgres",
            "password": "password", # Code default
        }
    ]

    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    db = os.getenv("DB_NAME", "postgres") # Report says error on "postgres" user, db likely postgres or stockdb

    # Try both 'postgres' and 'stockdb' database names
    dbs = ["postgres", "stockdb"]
    
    success = False
    for db_name in dbs:
        for config in configs:
            if await check_connection(config["user"], config["password"], db_name, host, port):
                success = True
                print(f"Valid credentials found: User={config['user']}, Pwd={config['password']}, DB={db_name}")
                break
        if success:
            break

    if not success:
        print("All attempts failed.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
