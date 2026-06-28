#!/usr/bin/env python3
import sys, json, urllib.request, urllib.error

BASE = "http://127.0.0.1:8001"
results = []

def call(method, path, data=None):
    try:
        req = urllib.request.Request(f"{BASE}{path}", 
            data=json.dumps(data).encode() if data else None,
            headers={"Content-Type": "application/json"}, method=method)
        with urllib.request.urlopen(req, timeout=5) as r:
            return True, json.loads(r.read())
    except Exception as e:
        return False, str(e)

def test(name, method, path, data=None, key=None):
    print(f"\n{'='*60}\n{name}\n{method} {path}")
    ok, res = call(method, path, data)
    status = "PASS" if ok else "FAIL"
    results.append((status, name))
    if ok and key and key in res:
        print(f"{status} {key}={res[key]}")
        return res
    elif ok:
        print(status)
        return res
    else:
        print(f"{status} {res}")
        return None

print("="*60 + "\nP0 Test\n" + "="*60)

test("Health check", "GET", "/health")
t = test("Create thread", "POST", "/v1/threads", {"title": "Test"}, "id")
if t: 
    test("List threads", "GET", "/v1/threads")
    test("Search threads", "GET", "/v1/threads/search?keyword=Test")
    test("Update thread", "PATCH", f"/v1/threads/{t['id']}", {"status": "archived"})
    test("Delete thread", "DELETE", f"/v1/threads/{t['id']}")

s = test("Add MCP", "POST", "/v1/mcp/servers", {"name": "test", "command": "python"}, "id")
if s:
    test("List MCP", "GET", "/v1/mcp/servers")
    test("Delete MCP", "DELETE", f"/v1/mcp/servers/{s['id']}")

k = test("Add Skill", "POST", "/v1/skills", {"name": "test", "type": "custom", "path": "/test"}, "id")
if k:
    test("List Skills", "GET", "/v1/skills")
    test("Delete Skill", "DELETE", f"/v1/skills/{k['id']}")

f = test("Save file", "POST", "/v1/files/save", {"filename": "p0-smoke.txt", "content": "desktop-api smoke"}, "id")
if f:
    test("List files", "GET", "/v1/files")
    test("Delete file", "DELETE", f"/v1/files/{f['id']}")

st = test("Create strategy", "POST", "/v1/users/default/strategies", {"name": "Test", "type": "custom", "stocks": ["600519"]}, "id")
if st:
    test("List strategies", "GET", "/v1/users/default/strategies")
    test("Delete strategy", "DELETE", f"/v1/users/default/strategies/{st['id']}")

p = test("Create pool", "POST", "/v1/users/default/stock-pools", {"name": "Test"}, "id")
if p:
    test("Add stock", "POST", f"/v1/users/default/stock-pools/{p['id']}/stocks", {"code": "600519", "name": "Maotai"})
    test("Remove stock", "DELETE", f"/v1/users/default/stock-pools/{p['id']}/stocks/600519")
    test("Delete pool", "DELETE", f"/v1/users/default/stock-pools/{p['id']}")

passed = sum(1 for x,_ in results if x=="PASS")
print(f"\n{'='*60}\nTotal: {len(results)}, Passed: {passed}, Failed: {len(results)-passed}\nPass rate: {passed/len(results)*100:.1f}%\n{'='*60}")
sys.exit(0 if passed == len(results) else 1)
