"""修复数据库表结构 — 解决 stocks 表 code/stock_code 双列冲突"""
import asyncio, sys, os
from pathlib import Path

env_path = Path(__file__).parent / '.env'
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from akshare_mcp.storage.timescaledb import get_db


async def fix():
    db = get_db()
    await db.initialize()
    async with db.acquire() as conn:
        # ============================================================
        # 1. stocks 表：修复 code 列 NOT NULL 冲突
        # ============================================================
        print("[1] 检查 stocks 表结构...")
        cols = await conn.fetch(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'stocks' ORDER BY ordinal_position"
        )
        col_map = {r['column_name']: r['is_nullable'] for r in cols}
        print(f"  当前列: {list(col_map.keys())}")

        if 'code' in col_map and 'stock_code' in col_map:
            print("  检测到 code + stock_code 双列共存")

            # 1a. 去掉 code 列的 NOT NULL 约束
            if col_map.get('code') == 'NO':
                print("  → 去掉 code 列 NOT NULL 约束...")
                await conn.execute("ALTER TABLE stocks ALTER COLUMN code DROP NOT NULL")
                print("  ✅ code 列已改为可空")

            # 1b. 如果 code 列有数据但 stock_code 没有，同步过去
            cnt = await conn.fetchval(
                "SELECT COUNT(*) FROM stocks WHERE stock_code IS NULL AND code IS NOT NULL"
            )
            if cnt and cnt > 0:
                print(f"  → 同步 {cnt} 条 code → stock_code...")
                await conn.execute("UPDATE stocks SET stock_code = code WHERE stock_code IS NULL AND code IS NOT NULL")

            # 1c. 确保 stock_code 是 PK
            pk = await conn.fetch("""
                SELECT a.attname FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = 'stocks'::regclass AND i.indisprimary
            """)
            pk_cols = [r['attname'] for r in pk]
            print(f"  当前 PK: {pk_cols}")

            if 'stock_code' not in pk_cols:
                print("  → 需要将 PK 改为 stock_code...")
                # 先删旧 PK
                try:
                    # 查找 PK 约束名
                    pk_name = await conn.fetchval("""
                        SELECT conname FROM pg_constraint
                        WHERE conrelid = 'stocks'::regclass AND contype = 'p'
                    """)
                    if pk_name:
                        await conn.execute(f"ALTER TABLE stocks DROP CONSTRAINT {pk_name}")
                        print(f"  → 已删除旧 PK 约束: {pk_name}")
                except Exception as e:
                    print(f"  ⚠️ 删除旧 PK 失败: {e}")

                # 清理 stock_code 为空的行
                await conn.execute("DELETE FROM stocks WHERE stock_code IS NULL OR stock_code = ''")
                # 添加新 PK
                try:
                    await conn.execute("ALTER TABLE stocks ADD PRIMARY KEY (stock_code)")
                    print("  ✅ PK 已改为 stock_code")
                except Exception as e:
                    print(f"  ⚠️ 添加 PK 失败: {e}")

            # 1d. 添加缺失列
            for col, dtype in [
                ('market', 'TEXT'),
                ('sector', 'TEXT'),
                ('kline_sync_attempted', 'TIMESTAMPTZ'),
            ]:
                await conn.execute(f"ALTER TABLE stocks ADD COLUMN IF NOT EXISTS {col} {dtype}")

            print("  ✅ stocks 表修复完成")

        elif 'code' in col_map and 'stock_code' not in col_map:
            print("  只有 code 列，添加 stock_code 并迁移...")
            await conn.execute("ALTER TABLE stocks ADD COLUMN stock_code TEXT")
            await conn.execute("UPDATE stocks SET stock_code = code")
            await conn.execute("ALTER TABLE stocks ALTER COLUMN code DROP NOT NULL")
            # 添加缺失列
            for col, dtype in [('market', 'TEXT'), ('sector', 'TEXT'), ('kline_sync_attempted', 'TIMESTAMPTZ')]:
                await conn.execute(f"ALTER TABLE stocks ADD COLUMN IF NOT EXISTS {col} {dtype}")
            print("  ✅ 已添加 stock_code 并同步数据")

        else:
            print("  ✅ stocks 表结构正常")

        # ============================================================
        # 2. financials 表：确保 stock_code 列存在
        # ============================================================
        print("\n[2] 检查 financials 表...")
        fin_cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'financials'"
        )
        fin_col_names = [r['column_name'] for r in fin_cols]

        if 'code' in fin_col_names and 'stock_code' not in fin_col_names:
            print("  → 添加 stock_code 列并同步...")
            await conn.execute("ALTER TABLE financials ADD COLUMN IF NOT EXISTS stock_code TEXT")
            await conn.execute("UPDATE financials SET stock_code = code WHERE stock_code IS NULL")
            try:
                await conn.execute("ALTER TABLE financials DROP CONSTRAINT IF EXISTS financials_code_report_date_key")
                await conn.execute(
                    "ALTER TABLE financials ADD CONSTRAINT financials_stock_code_report_date_key "
                    "UNIQUE (stock_code, report_date)"
                )
                print("  ✅ UNIQUE 约束已更新")
            except Exception as e:
                print(f"  ⚠️ 约束更新: {e}")
        else:
            print("  ✅ financials 表结构正常")

        # 补齐财务列
        for col, dtype in [
            ('gross_margin', 'DOUBLE PRECISION'),
            ('net_margin', 'DOUBLE PRECISION'),
            ('current_ratio', 'DOUBLE PRECISION'),
            ('bvps', 'DOUBLE PRECISION'),
            ('roa', 'DOUBLE PRECISION'),
        ]:
            await conn.execute(f"ALTER TABLE financials ADD COLUMN IF NOT EXISTS {col} {dtype}")

        # ============================================================
        # 3. 验证
        # ============================================================
        print("\n[3] 验证修复结果...")
        for table in ['stocks', 'financials']:
            cols = await conn.fetch(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = $1 ORDER BY ordinal_position", table
            )
            print(f"  {table}:")
            for c in cols:
                nullable = "NULL" if c['is_nullable'] == 'YES' else "NOT NULL"
                print(f"    {c['column_name']:25s} {nullable}")

        # 检查 stocks PK
        pk = await conn.fetch("""
            SELECT a.attname FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = 'stocks'::regclass AND i.indisprimary
        """)
        print(f"\n  stocks PK: {[r['attname'] for r in pk]}")

        # 检查 stocks 行数
        cnt = await conn.fetchval("SELECT COUNT(*) FROM stocks")
        print(f"  stocks 行数: {cnt}")

    print("\n✅ 表结构修复完成")


asyncio.run(fix())
