#!/usr/bin/env python3
"""
数据库字段迁移脚本
将 code 字段重命名为 stock_code，以与 Node.js 版本保持一致
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加src目录到路径
sys.path.insert(0, str(Path(__file__).parent / 'src'))

try:
    import asyncpg
except ImportError:
    print("❌ 需要安装 asyncpg: pip install asyncpg")
    sys.exit(1)


async def migrate_database():
    """执行数据库迁移"""
    
    # 从环境变量读取配置
    db_config = {
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'password'),
        'database': os.getenv('DB_NAME', 'postgres'),
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
    }
    
    print("=" * 60)
    print("数据库字段迁移脚本")
    print("=" * 60)
    print(f"\n连接到数据库: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    
    try:
        conn = await asyncpg.connect(**db_config)
        print("✅ 数据库连接成功\n")
        
        # 检查表是否存在
        tables_to_check = ['stocks', 'financials']
        
        for table in tables_to_check:
            exists = await conn.fetchval(
                """SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = $1
                )""",
                table
            )
            
            if not exists:
                print(f"⚠️  表 {table} 不存在，跳过迁移")
                continue
            
            # 检查字段是否存在
            has_code = await conn.fetchval(
                """SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = $1 AND column_name = 'code'
                )""",
                table
            )
            
            has_stock_code = await conn.fetchval(
                """SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = $1 AND column_name = 'stock_code'
                )""",
                table
            )
            
            if has_stock_code:
                print(f"✅ 表 {table} 已使用 stock_code 字段，无需迁移")
                continue
            
            if not has_code:
                print(f"⚠️  表 {table} 没有 code 字段，跳过迁移")
                continue
            
            # 执行迁移
            print(f"\n🔄 迁移表 {table}...")
            
            try:
                # 开始事务
                async with conn.transaction():
                    # 重命名字段
                    await conn.execute(f"""
                        ALTER TABLE {table} 
                        RENAME COLUMN code TO stock_code
                    """)
                    
                    print(f"  ✅ 字段 code → stock_code 重命名成功")
                    
                    # 如果是stocks表，还需要更新主键约束名称
                    if table == 'stocks':
                        # 检查旧约束是否存在
                        old_constraint = await conn.fetchval("""
                            SELECT constraint_name 
                            FROM information_schema.table_constraints 
                            WHERE table_name = 'stocks' 
                            AND constraint_type = 'PRIMARY KEY'
                            AND constraint_name LIKE '%code%'
                        """)
                        
                        if old_constraint:
                            print(f"  ℹ️  主键约束: {old_constraint}")
                    
                    # 获取记录数
                    count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                    print(f"  ℹ️  影响记录数: {count}")
                    
            except Exception as e:
                print(f"  ❌ 迁移失败: {e}")
                raise
        
        # 验证迁移结果
        print("\n" + "=" * 60)
        print("验证迁移结果")
        print("=" * 60)
        
        for table in tables_to_check:
            exists = await conn.fetchval(
                """SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = $1
                )""",
                table
            )
            
            if not exists:
                continue
            
            # 检查字段
            columns = await conn.fetch(
                """SELECT column_name, data_type 
                   FROM information_schema.columns 
                   WHERE table_name = $1 
                   AND column_name IN ('code', 'stock_code')
                   ORDER BY column_name""",
                table
            )
            
            print(f"\n表 {table}:")
            for col in columns:
                print(f"  - {col['column_name']}: {col['data_type']}")
            
            if not columns:
                print(f"  ⚠️  没有找到 code 或 stock_code 字段")
        
        print("\n" + "=" * 60)
        print("✨ 迁移完成！")
        print("=" * 60)
        print("\n下一步:")
        print("  1. 重启 MCP 服务")
        print("  2. 运行测试验证功能")
        print()
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        print("\n可能的原因:")
        print("  1. 数据库连接失败")
        print("  2. 权限不足")
        print("  3. 表结构冲突")
        print("\n解决方案:")
        print("  1. 检查数据库连接配置")
        print("  2. 确保数据库用户有 ALTER TABLE 权限")
        print("  3. 手动检查表结构: \\d stocks")
        print()
        return 1
    
    finally:
        if conn:
            await conn.close()
            print("数据库连接已关闭")
    
    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(migrate_database())
    sys.exit(exit_code)
