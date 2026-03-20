# 数据质量测试 - 核心运行器
# 只运行当前保留的数据质量与 MCP 集成测试

from run_all_tests import main


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
