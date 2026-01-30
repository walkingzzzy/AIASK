#!/usr/bin/env python3
"""
批量修复所有Python文件中的 ok(..., source=...) 调用
将其改为 ok(...) 因为ok函数不支持source参数
"""

import re
import os
from pathlib import Path

def fix_source_param(file_path):
    """修复单个文件中的source参数"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # 匹配 ok(..., source='...') 或 ok(..., source="...")
    # 使用正则表达式移除source参数
    pattern = r',\s*source\s*=\s*[\'"][^\'"]*[\'"]'
    content = re.sub(pattern, '', content)
    
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    """主函数"""
    tools_dir = Path('src/akshare_mcp/tools')
    
    if not tools_dir.exists():
        print(f"目录不存在: {tools_dir}")
        return
    
    fixed_count = 0
    for py_file in tools_dir.glob('*.py'):
        if fix_source_param(py_file):
            print(f"✓ 修复: {py_file.name}")
            fixed_count += 1
        else:
            print(f"  跳过: {py_file.name}")
    
    print(f"\n总共修复了 {fixed_count} 个文件")

if __name__ == '__main__':
    main()
