import os, sys, inspect, re
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

from akshare_mcp.server import mcp


def norm(s):
    return "" if s is None else str(s).replace("\r\n", "\n").strip()


def short(s, n=44):
    s = re.sub(r"\s+", " ", s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def score(desc, doc, fn, name):
    text = (desc or "") + "\n" + (doc or "")
    sig = inspect.signature(fn)
    ps = [p for p in sig.parameters.values() if p.name not in ("self", "cls")]
    a = "❌" if not (desc or doc) else ("⚠️" if len((desc or doc).strip()) < 18 else "✅")
    p = "✅" if not ps else ("❌" if not (("Args:" in text) or ("参数" in text)) else ("⚠️" if ("YYYY" not in text and "默认" not in text and "格式" not in text and "如" not in text) else "✅"))
    r = "✅" if (("Returns:" in text) or ("返回" in text)) else ("⚠️" if text.strip() else "❌")
    e = "✅" if (("Example" in text) or ("Examples" in text) or ("示例" in text)) else "❌"
    bad, warn = [a, p, r, e].count("❌"), [a, p, r, e].count("⚠️")
    core = any(k in name for k in ["kline", "quote", "order_book", "backtest", "tdx", "manager", "sync", "alert", "portfolio", "valuation"])
    if bad >= 2 or (bad == 1 and (core or r == "❌" or p == "❌")):
        pr = "P0"
    elif bad == 1 or warn >= 2 or e == "❌":
        pr = "P1"
    else:
        pr = "P2"
    issues = []
    if a == "❌": issues.append("描述缺失")
    elif a == "⚠️": issues.append("描述偏短")
    if p == "❌": issues.append("参数规范缺失")
    elif p == "⚠️": issues.append("参数约束不足")
    if r == "❌": issues.append("返回结构缺失")
    elif r == "⚠️": issues.append("返回字段未细化")
    if e == "❌": issues.append("无示例")
    adv = []
    if a != "✅": adv.append("补1句场景化定义")
    if p != "✅": adv.append("补Args类型/默认/格式")
    if r != "✅": adv.append("补Returns与错误返回")
    if e != "✅": adv.append("补1个可运行示例")
    if "compat" in name or "manager" in name: adv.append("补Node映射说明")
    return a, p, r, e, pr, "；".join(issues) if issues else "说明较完整", "；".join(adv[:3])


def build_md(rows):
    p0 = sum(1 for x in rows if x[8] == "P0")
    p1 = sum(1 for x in rows if x[8] == "P1")
    p2 = sum(1 for x in rows if x[8] == "P2")
    null_desc = sum(1 for x in rows if x[1] == "")
    out = []
    out += ["# AKShare MCP 工具描述全面审查与改进计划（137 工具逐条矩阵）", "", f"> 审查时间：{datetime.now():%Y-%m-%d %H:%M:%S}", "> 审查范围：`packages/akshare-mcp/src/akshare_mcp/tools/` + `server.py`", "> 工具总数：**137**（运行时可用工具）", f"> 空 description：**{null_desc}**", "", "## 一、总体问题汇总", "", "### 1.1 四维审查标准", "- 准确性与完整性", "- 参数规范性", "- 返回完整性", "- 示例实用性", "", "### 1.2 优先级统计", f"- **P0：{p0}**", f"- **P1：{p1}**", f"- **P2：{p2}**", "", "## 二、分类审查结果", "", "- 市场/行情/资金流：补时效与源优先级。", "- 技术分析/TDX：补参数范围与异常行为。", "- 回测/组合/风险：补输出指标与字段。", "- managers：补 action/kwargs schema。", "", "## 三、137 工具逐条问题矩阵", "", "|#|工具|当前description|当前docstring(首句)|准确性|参数|返回|示例|优先级|问题摘要|改进建议|", "|---:|---|---|---|:---:|:---:|:---:|:---:|:---:|---|---|"]
    for i, x in enumerate(rows, 1):
        out.append(f"|{i}|`{x[0]}`|{short(x[1]) if x[1] else '[空]'}|{short(x[2].splitlines()[0] if x[2] else '[空]', 34)}|{x[4]}|{x[5]}|{x[6]}|{x[7]}|{x[8]}|{x[9]}|{x[10]}|")
    out += ["", "## 四、通用改进建议", "", "1. 统一 Docstring 模板：功能/时效/Args/Returns/Example。", "2. 返回结构统一建议含 success/error/source/stale/timestamp。", "3. 兼容工具补 Node.js 参数映射示例。", "", "## 五、实施计划", "", "1. 先处理 P0。", "2. 再处理 P1。", "3. 最后处理 P2 与文风统一。", "", "> 说明：仅输出审查结果，不修改业务代码。"]
    return "\n".join(out) + "\n"


def main():
    tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", {})
    rows = []
    for name, tool in sorted(tools.items(), key=lambda kv: kv[0]):
        fn = getattr(tool, "fn", None)
        desc = norm(getattr(tool, "description", None))
        doc = norm(inspect.getdoc(fn) if fn else "")
        a, p, r, e, pr, issue, adv = score(desc, doc, fn, name)
        rows.append((name, desc, doc, fn, a, p, r, e, pr, issue, adv))
    if len(rows) != 137:
        raise RuntimeError(f"工具数异常：{len(rows)}")
    md = build_md(rows)
    path = os.path.join(ROOT, "TOOL_DESCRIPTION_IMPROVEMENT_PLAN.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print("written", path, "rows", len(rows))


if __name__ == "__main__":
    main()

