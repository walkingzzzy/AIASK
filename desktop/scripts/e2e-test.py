#!/usr/bin/env python3
"""
AIASK Desktop P0 端到端测试脚本
测试所有核心功能的完整工作流
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

# 配置
DESKTOP_API = "http://127.0.0.1:8001"
FRONTEND = "http://127.0.0.1:1420"

# 测试结果
results = []
test_data = {}

def log(level, message):
    """打印彩色日志"""
    colors = {
        "INFO": "\033[36m",    # Cyan
        "PASS": "\033[32m",    # Green
        "FAIL": "\033[31m",    # Red
        "WARN": "\033[33m",    # Yellow
    }
    reset = "\033[0m"
    print(f"{colors.get(level, '')}{level:5} {message}{reset}")

def call_api(method, url, data=None):
    """调用API"""
    try:
        headers = {"Content-Type": "application/json"}
        request_data = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=request_data, headers=headers, method=method)

        with urllib.request.urlopen(req, timeout=10) as response:
            return True, json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)

def test(name, method, path, data=None, expect_key=None):
    """执行单个测试"""
    url = f"{DESKTOP_API}{path}"
    log("INFO", f"测试: {name}")
    log("INFO", f"  {method} {path}")

    ok, result = call_api(method, url, data)

    if ok:
        log("PASS", f"  ✓ 成功")
        results.append(("PASS", name))

        # 保存关键数据用于后续测试
        if expect_key and expect_key in result:
            test_data[name] = result[expect_key]
            log("INFO", f"  → {expect_key}: {result[expect_key]}")

        return result
    else:
        log("FAIL", f"  ✗ 失败: {result}")
        results.append(("FAIL", name))
        return None

def main():
    print("=" * 70)
    print("  AIASK Desktop P0 端到端测试")
    print("=" * 70)
    print()

    # 阶段1: 健康检查
    log("INFO", "=" * 70)
    log("INFO", "阶段 1/6: 服务健康检查")
    log("INFO", "=" * 70)
    test("Desktop API 健康检查", "GET", "/health")

    # 阶段2: 线程管理
    log("INFO", "")
    log("INFO", "=" * 70)
    log("INFO", "阶段 2/6: 线程管理工作流")
    log("INFO", "=" * 70)
    test("创建线程", "POST", "/v1/threads", {
        "title": "P0测试工作流",
        "description": "端到端测试创建的线程"
    }, expect_key="id")

    test("列出所有线程", "GET", "/v1/threads")
    test("搜索线程", "GET", "/v1/threads/search?keyword=P0")

    if "创建线程" in test_data:
        thread_id = test_data["创建线程"]
        test("更新线程", "PATCH", f"/v1/threads/{thread_id}", {
            "description": "已更新描述"
        })

    # 阶段3: MCP 服务管理
    log("INFO", "")
    log("INFO", "=" * 70)
    log("INFO", "阶段 3/6: MCP 服务管理工作流")
    log("INFO", "=" * 70)
    test("添加 MCP 服务器", "POST", "/v1/mcp/servers", {
        "name": "test-mcp",
        "command": "python",
        "args": ["-m", "mcp_server"],
        "env": {"DEBUG": "1"}
    }, expect_key="id")

    test("列出 MCP 服务器", "GET", "/v1/mcp/servers")

    if "添加 MCP 服务器" in test_data:
        mcp_id = test_data["添加 MCP 服务器"]
        test("更新 MCP 服务器", "PATCH", f"/v1/mcp/servers/{mcp_id}", {
            "enabled": False
        })

    # 阶段4: 技能管理
    log("INFO", "")
    log("INFO", "=" * 70)
    log("INFO", "阶段 4/6: 技能管理工作流")
    log("INFO", "=" * 70)
    test("添加技能", "POST", "/v1/skills", {
        "name": "test-skill",
        "type": "custom",
        "path": "/test/skill"
    }, expect_key="id")

    test("列出技能", "GET", "/v1/skills")

    # 阶段5: 策略与股票池
    log("INFO", "")
    log("INFO", "=" * 70)
    log("INFO", "阶段 5/6: 策略与股票池工作流")
    log("INFO", "=" * 70)
    test("创建策略", "POST", "/v1/users/default/strategies", {
        "name": "测试策略",
        "type": "momentum",
        "stocks": ["600519", "000858"]
    }, expect_key="id")

    test("列出策略", "GET", "/v1/users/default/strategies")

    test("创建股票池", "POST", "/v1/users/default/stock-pools", {
        "name": "测试股票池"
    }, expect_key="id")

    if "创建股票池" in test_data:
        pool_id = test_data["创建股票池"]
        test("添加股票到股票池", "POST", f"/v1/users/default/stock-pools/{pool_id}/stocks", {
            "code": "600519",
            "name": "贵州茅台"
        })

    test("列出股票池", "GET", "/v1/users/default/stock-pools")

    # 阶段6: 文件上传
    log("INFO", "")
    log("INFO", "=" * 70)
    log("INFO", "阶段 6/6: 文件上传工作流")
    log("INFO", "=" * 70)

    # 创建测试文件
    test_file_path = "test_upload.txt"
    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write(f"测试文件上传 - {datetime.now().isoformat()}\n")

    log("INFO", "测试: 上传文件")
    log("INFO", f"  POST /v1/files/upload")
    try:
        import subprocess
        result = subprocess.run([
            "curl", "-s", "-X", "POST",
            f"{DESKTOP_API}/v1/files/upload",
            "-F", f"files=@{test_file_path}",
            "-F", "session_id=e2e_test"
        ], capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            upload_result = json.loads(result.stdout)
            if upload_result.get("object") == "list":
                log("PASS", "  ✓ 成功")
                results.append(("PASS", "上传文件"))
                if upload_result.get("data"):
                    test_data["上传文件"] = upload_result["data"][0]["id"]
                    log("INFO", f"  → file_id: {test_data['上传文件']}")
            else:
                log("FAIL", "  ✗ 响应格式错误")
                results.append(("FAIL", "上传文件"))
        else:
            log("FAIL", f"  ✗ curl 失败: {result.stderr}")
            results.append(("FAIL", "上传文件"))
    except Exception as e:
        log("FAIL", f"  ✗ 异常: {e}")
        results.append(("FAIL", "上传文件"))

    test("列出文件", "GET", "/v1/files")

    # 清理阶段
    log("INFO", "")
    log("INFO", "=" * 70)
    log("INFO", "清理测试数据")
    log("INFO", "=" * 70)

    # 删除创建的资源
    if "创建线程" in test_data:
        test("删除线程", "DELETE", f"/v1/threads/{test_data['创建线程']}")

    if "添加 MCP 服务器" in test_data:
        test("删除 MCP 服务器", "DELETE", f"/v1/mcp/servers/{test_data['添加 MCP 服务器']}")

    if "添加技能" in test_data:
        test("删除技能", "DELETE", f"/v1/skills/{test_data['添加技能']}")

    if "创建策略" in test_data:
        test("删除策略", "DELETE", f"/v1/users/default/strategies/{test_data['创建策略']}")

    if "创建股票池" in test_data:
        test("删除股票池", "DELETE", f"/v1/users/default/stock-pools/{test_data['创建股票池']}")

    if "上传文件" in test_data:
        test("删除文件", "DELETE", f"/v1/files/{test_data['上传文件']}")

    # 统计结果
    print()
    print("=" * 70)
    passed = sum(1 for status, _ in results if status == "PASS")
    failed = sum(1 for status, _ in results if status == "FAIL")
    total = len(results)
    pass_rate = (passed / total * 100) if total > 0 else 0

    log("INFO", f"测试完成")
    print("=" * 70)
    print(f"  总计: {total}")
    print(f"  通过: {passed} ✓")
    print(f"  失败: {failed} ✗")
    print(f"  通过率: {pass_rate:.1f}%")
    print("=" * 70)

    if failed > 0:
        print()
        log("FAIL", "失败的测试:")
        for status, name in results:
            if status == "FAIL":
                print(f"  ✗ {name}")

    print()
    log("INFO", "服务状态:")
    print(f"  • Desktop API: {DESKTOP_API}")
    print(f"  • Frontend:    {FRONTEND}")
    print()

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
