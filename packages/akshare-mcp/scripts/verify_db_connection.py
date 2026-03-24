
import asyncio
import os
import sys
from pathlib import Path

import asyncpg


def _load_local_env() -> Path | None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
    return env_path


def _first_env(*keys: str, default: str | None = None) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def _candidate_databases(configured_db: str | None) -> list[str]:
    candidates: list[str] = []
    for name in (configured_db, "stockdb", "postgres"):
        token = str(name or "").strip()
        if token and token not in candidates:
            candidates.append(token)
    return candidates


async def check_connection(user: str, password: str, db: str, host: str, port: int) -> bool:
    print(f"Testing connection to {host}:{port} as {user} for {db}...")
    conn = None
    try:
        conn = await asyncpg.connect(
            user=user,
            password=password,
            database=db,
            host=host,
            port=port,
            timeout=5,
        )
        await conn.execute("SELECT 1")
        print("✅ Connection successful!")
        return True
    except Exception as exc:
        print(f"❌ Connection failed: {exc}")
        return False
    finally:
        if conn is not None:
            await conn.close()


async def main():
    env_path = _load_local_env()
    if env_path is not None:
        print(f"Loaded environment from: {env_path}")
    else:
        print("No local .env found, relying on current process environment.")

    host = _first_env("DB_HOST", "POSTGRES_HOST", default="localhost")
    port = int(_first_env("DB_PORT", "POSTGRES_PORT", default="5432") or "5432")
    user = _first_env("DB_USER", "POSTGRES_USER", default="postgres")
    password = _first_env("DB_PASSWORD", "POSTGRES_PASSWORD", default="")
    configured_db = _first_env("DB_NAME", "POSTGRES_DB", default="stockdb")

    print(
        "Using configured credentials:",
        f"user={user}",
        f"database={configured_db}",
        f"host={host}",
        f"port={port}",
    )

    success = False
    for db_name in _candidate_databases(configured_db):
        if await check_connection(user, password, db_name, host, port):
            success = True
            print(f"Valid credentials found: user={user}, db={db_name}")
            break

    if not success:
        print("All attempts failed.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
