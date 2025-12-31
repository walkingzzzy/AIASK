#!/usr/bin/env python
"""
知识库初始化脚本
首次运行时执行，将股票数据导入知识库
"""
import sys
import os

# 添加项目路径

import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_knowledge_base(hot_only: bool = True):
    """
    初始化知识库
    
    Args:
        hot_only: True只导入热门股票，False导入全部A股
    """
    from tasks.sync_knowledge_base import get_sync_task
    
    logger.info("=" * 50)
    logger.info("开始初始化知识库")
    logger.info("=" * 50)
    
    sync_task = get_sync_task()
    
    if hot_only:
        logger.info("模式: 仅热门股票")
        result = sync_task.sync_hot_stocks()
    else:
        logger.info("模式: 全部A股（这可能需要较长时间）")
        result = sync_task.sync_all_stocks()
    
    logger.info("=" * 50)
    logger.info("初始化完成!")
    logger.info(f"总计: {result.get('total', 0)} 只股票")
    logger.info(f"成功: {result.get('success', 0)}")
    logger.info(f"失败: {result.get('failed', 0)}")
    logger.info("=" * 50)
    
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="初始化知识库")
    parser.add_argument(
        "--all", 
        action="store_true", 
        help="导入全部A股（默认只导入热门股票）"
    )
    
    args = parser.parse_args()
    init_knowledge_base(hot_only=not args.all)
