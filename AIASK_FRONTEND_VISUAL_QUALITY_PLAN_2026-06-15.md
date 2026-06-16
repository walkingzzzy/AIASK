# AIASK Desktop 前端视觉质感优化方案

**版本**: v2.0（迁移追踪）
**日期**: 2026-06-15
**作者**: Claude Code
**定位**: 视觉设计体系层（与导航重构方案互补，非替代）

---

## ⚠️ 状态更新（v2.0 重写，2026-06-15 实测）

> **v1.1 已严重过时**：它把阶段 1–3 写成"待办"，但实测代码里**基础设施已全部落地**。
> 真正的瓶颈不是"缺什么"，而是"建了不用"——token 定义齐全但旧代码采用率近乎为零。
> 本版改为**迁移追踪**，记录已完成项 + 本次会话的修复 + 剩余采用缺口。

### 已落地基础设施（实测核验，非待办）

| 能力 | 文件:位置 | 状态 |
|---|---|---|
| 间距/字号/字重/行高刻度 token | `globals-layout.css:27-57` | ✅ 完整 |
| 金融方向色（light/dark × A股/intl 四模式） | `globals-layout.css:59-138` | ✅ 完整 |
| 统一交互层（focus/disabled/active/tooltip） | `interactions.css`（80 行） | ✅ 完整 |
| PageShell 框架 | `page-shell.css`（151 行） | ✅ 完整 |
| `PriceDelta` 组件（符号+▲▼+tabular-nums，色盲安全） | `shared.tsx:370` | ✅ 优于原草案 |
| Radix（dialog/tabs/tooltip） | `OverlayView/shared/Capabilities` 实用 | ✅ 已用 |
| 依赖：lightweight-charts / TanStack table+virtual | `package.json` | ⚠️ **已装但 0 引用** |

### 本次会话已修复

1. ✅ **浅色跌色 WCAG**：`--fin-down` 由 `#1a9d54`(白底 3.50:1，不达 AA) 改为 `#0e7a3e`(5.42:1)，intl 变体同步。深色模式原已达标，未动。
2. ✅ **字号 token 迁移**：10 个 CSS 文件 161 处 `font-size: Npx` → `var(--fs-*)`（11→xs / 12→sm / 13→base / 15→md / 18→lg）。剩 10 处 `14px`（介于 base/md 之间，无精确 token，留待逐组件判断）+ 少量大字号标题。
3. ✅ **PriceDelta 扩面**：市场温度"均涨跌/加权涨跌"+ 前向验证"1日/3日均值收益"(`avg_forward_return`) 由灰色文本改为带色+符号的 `PriceDelta`；删除随之孤立的 `pct()` 辅助函数。quant 工作区的 OOS 收益原已用 PriceDelta。**排查结论**：MetricCard 标签经全量核查多为状态/计数/配置(非方向值)，financial-manager/finance-lab 是配置/工作流面板无实时 P&L——真正的方向值集中在 market-temperature 与 quant 两个工作区，现已全覆盖。
4. ✅ **间距 token 迁移**：`gap/padding/margin` 的**精确网格值**（4/8/12/16/24/32px，含全网格双值如 `12px 16px`）→ `var(--space-*)`，全库 `--space-*` 引用从个位数升至 **145 处**。**故意只迁移精确匹配**：`10px/6px/14px/5px` 等离格值保留原样——盲目吸附 8pt 网格会移动布局、引发视觉回归。离格值留待逐组件设计判断（要么微调到网格、要么确认是有意的特化值）。

### ⏳ 剩余采用缺口（按 ROI）

- **P2 离格间距值收敛**：`10px`(约75处) 和 `14px`(约20处) 是最常见的离格值，需逐组件人工判断——吸附到 `--space-2(8)/--space-3(12)` 还是保留。非脚本可批替。
- **P2 标题 display 字体**：`globals-layout.css:172` 仍纯 `system-ui`，阶段 4 未做（优先级最低）。

> **PriceDelta 扩面已收口**：经全量排查，方向值仅集中在 market-temperature/quant 两区且已全覆盖；其余工作区为状态/配置/计数面板，无方向值可包。后续新增金融数据面板时，凡"有方向的数"一律用 `<PriceDelta>`。

### 🔵 已决策

- **TanStack Table + Virtual / lightweight-charts**：**保留**（用户 2026-06-15 拍板）。理由：近期排期含 K 线/分时/大数据持仓表，保留避免来回 churn。当前 0 引用属"预装待用"，不视作技术债。
  - Radix 已被实际使用（OverlayView/shared/Capabilities），同样保留。

---

## 〇、本方案与已有文档的边界

| 文档 | 维度 | 解决什么 |
|---|---|---|
| `前端改造方案_AIASK_Desktop_简化版.md` | **信息架构** | 导航 33→6、PageShell 统一框架、URL 路由。Phase 1 侧边栏精简已完成（commit `38944909`） |
| **本方案** | **视觉设计体系** | 质感、专业感、客观性、交互一致性——即"看起来像成品而非原型" |

两者正交：导航重构解决"功能怎么组织"，本方案解决"每个像素怎么呈现"。可并行推进，互不阻塞。

---

## 一、真实代码体检（每条带 `文件:行号`，可复核）

> 方法：逐文件读取 `desktop/src/styles/*.css`（5748 行）与 `desktop/src/components/shared.tsx`，grep 验证语义色与刻度 token 的存在性。

### 1.1 现状：体系只搭了一半，不是从零

代码里**已有**的基础，质量不差：

- **颜色 token 体系完整**：`globals-layout.css:1-26` 定义了 bg/text/accent/ok/warn/bad/border/shadow/focus 等一整套 CSS 变量。
- **深色模式三态可用**：`globals-layout.css:28-64` light/dark/system 三套，且 `:root[data-aiask-theme]` 驱动，外加 density(compact) 与 reduce-motion 支持（`:66-78`）。
- **原子组件已沉淀**：`shared.tsx` 内有 `StatusBadge`(:301)、`MetricCard`(:345)、`EmptyState`(:377)、`GatedState`(:398)、`IconButton`(:327)、`CapabilityRow`(:456)。
- **状态语义已归一**：`statusTone()`(:193) 把 100+ 业务状态映射到 ok/warn/bad/neutral 四色，`STATUS_LABELS`(:63) 提供中文标签。

**结论：你不缺"体系骨架"，缺的是"刻度层"和"金融专业层"。** 下面四条是真实短板。

### 1.2 四大短板 → 对应你的四个痛点

#### 短板 A：无间距/字号刻度 →【不成体系 + 视觉质感差】

- `grep --space|--gap|--pad` 在 5748 行 CSS 中**零命中**。
- 字号 `11/12/13/14px` 硬编码散落 80+ 处（如 `globals-layout.css:197,205,242,303,321,362`）。
- 间距全是 `10px / 14px 16px` 魔法数字（如 `:191,239,249,270,312`）。
- **后果**：每个组件呼吸感靠手调，页面间对不齐——这是"像原型"的根因。token 只做了颜色，没做 **type scale + spacing scale**，而这两个才是"质感"的物理来源。

#### 短板 B：金融语义色彻底缺失 →【缺乏专业感/客观性】

- `grep up|down|rise|fall|gain|loss|涨|跌|profit|positive|negative` 在全部 CSS 中**零命中**。
- 一个金融/量化产品，**没有一个专门表达"涨/跌、盈/亏、多/空"的色**。现状只有通用 ok(绿)/bad(红)，但金融语境下：
  - A 股「红涨绿跌」与美股/国际「绿涨红跌」相反，必须可配置。
  - 涨跌色需要色盲安全（仅靠红绿区分约 8% 男性无法辨识）。
  - 数据网格里"今日涨幅"和"任务失败"都用同一个红，**语义混淆 = 客观性崩塌**。
- **这是"缺乏专业感"最致命的一点**：专业终端的客观性，第一眼就来自数字的颜色编码。

#### 短板 C：字体栈纯系统默认、数字非表格化 →【视觉质感差】

- `globals-layout.css:97` `font-family: system-ui,...,sans-serif`，无 display 字体。
- `--mono`(:25) 已定义，但只用在 `thread-list em`(:374)，**数据数字未用等宽/tabular-nums**。
- **后果**：金融表格里数字列对不齐、刷新时跳动；标题与正文同字号同字重，层次全靠颜色深浅撑——"不成体系"的视觉表现。

#### 短板 D：CSS 按"页面"切片而非按"层"组织 →【组件交互薄弱 + 不成体系】

- 11 个 CSS 文件按功能页切分（`workbench-dashboard / finance-events / tools-forms / capabilities-quant`...），最大单文件 762 行。
- 交互态（hover/active/focus/disabled）散落各文件，按钮在不同页可能被不同选择器覆盖。
- **官方 frontend-design skill 专门警告过此问题**：`.section` 类选择器与 `.cta` 元素选择器互相抵消，常见于 section 间 padding/margin。
- **后果**：无法保证一个按钮在全应用所有状态下表现一致——"交互薄弱"的工程根因。

---

## 二、落地方案（按 ROI 排序，每步零破坏增量）

### 阶段 1 ▸ 补刻度 token（半天，收益最大）

**目标**：把散落的魔法数字收敛成刻度，是后续一切的地基。

在 `globals-layout.css:1-26` 的 `:root` 内补充（与现有 token 同级，不动现有值）：

```css
:root {
  /* —— 间距刻度（4px 基准，8pt 网格）—— */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-8: 48px;

  /* —— 字号刻度（1.2 模数）—— */
  --fs-xs: 11px;    /* 标签/脚注 */
  --fs-sm: 12px;    /* 次要文本 */
  --fs-base: 13px;  /* 正文（当前主力） */
  --fs-md: 15px;    /* 强调正文 */
  --fs-lg: 18px;    /* 小标题 */
  --fs-xl: 22px;    /* 区块标题 */
  --fs-2xl: 28px;   /* 页面标题 */

  /* —— 字重 —— */
  --fw-normal: 400;
  --fw-medium: 500;
  --fw-semibold: 600;
  --fw-bold: 700;

  /* —— 行高 —— */
  --lh-tight: 1.25;
  --lh-normal: 1.5;

  /* —— 数据字体（表格数字必备）—— */
  --font-numeric: var(--mono);
  --fnum: "tnum" 1, "lnum" 1;  /* tabular + lining */
}
```

**渐进迁移**：新写的样式一律用 token；旧样式按文件批量替换（`13px`→`var(--fs-base)`），不必一次改完。

**解决**：不成体系（统一刻度）+ 视觉质感差（间距对齐、层次拉开）。

### 阶段 2 ▸ 加金融语义色 + 表格数字（1 天，专业感命门）

**2.1 语义色 token**（`globals-layout.css` `:root` 内）：

```css
:root {
  /* 金融方向色——默认「红涨绿跌」(A 股)，可整体翻转 */
  --fin-up: #d4382f;      /* 涨 */
  --fin-down: #1a9d54;    /* 跌 */
  --fin-flat: var(--text-dim);
  --fin-up-soft: rgba(212, 56, 47, 0.10);
  --fin-down-soft: rgba(26, 157, 84, 0.10);
}
/* 国际配色：在根节点加 data-fin-color-mode="intl" 即可翻转 */
:root[data-fin-color-mode="intl"] {
  --fin-up: #1a9d54;
  --fin-down: #d4382f;
}
```

**2.2 配套组件**（建议加到 `shared.tsx`，与 `MetricCard` 同级）：

```tsx
export function PriceDelta({ value, pct }: { value: number; pct?: number }) {
  const dir = value > 0 ? "up" : value < 0 ? "down" : "flat";
  const sign = value > 0 ? "+" : "";
  return (
    <span className={`price-delta ${dir}`}>
      {sign}{value.toFixed(2)}{pct != null && ` (${sign}${pct.toFixed(2)}%)`}
    </span>
  );
}
```

```css
.price-delta { font-family: var(--font-numeric); font-feature-settings: var(--fnum); font-weight: var(--fw-semibold); }
.price-delta.up   { color: var(--fin-up); }
.price-delta.down { color: var(--fin-down); }
.price-delta.flat { color: var(--fin-flat); }
```

**2.3 关键：方向不能只靠颜色**（客观性/可访问性）——涨跌额带 `+/-` 号或 ▲▼ 三角，色盲用户靠符号也能读。

**2.4 全局表格数字等宽**：

```css
td.num, .data-cell, .metric-card strong { font-family: var(--font-numeric); font-feature-settings: var(--fnum); }
```

**解决**：缺乏专业感/客观性（金融语义色 + 符号冗余 + 表格数字对齐）。

### 阶段 3 ▸ 统一交互态（1 天，治"交互薄弱"）

**目标**：把按钮/输入/卡片的 hover/focus/active/disabled 收敛到一处，新建 `styles/interactions.css` 作为"层"而非"页"。

- 抽出统一的交互态变量：`--state-hover-bg / --state-active-bg / --state-disabled-opacity`。
- 把现有散落的 `:hover/:focus-visible/:disabled`（`globals-layout.css:119-127,256-264,295-300,351-356`）合并到一处单一来源。
- 所有可点击元素强制：可见 focus 环（已有 `--focus`）、hover 反馈、disabled 态、过渡时长用统一 `--transition`。

**解决**：组件交互薄弱（单一来源 + 全状态覆盖）+ 不成体系（按层组织 CSS）。

### 阶段 4 ▸ 字体与层次（0.5 天）

- 引入 display 字体用于页面/区块标题（系统栈即可，或按研究报告选型）。
- 标题用 `--fs-xl/--fs-2xl` + `--fw-bold`，正文 `--fs-base` + `--fw-normal`，**层次靠字号字重而非仅颜色**。

---

## 三、工具加持：已启用官方 frontend-design skill

- 已在 `~/.claude.json` 的 `enabledPlugins` 启用 `frontend-design@claude-plugins-official`（Anthropic 官方）。
- **需重启 Claude Code 生效**。生效后做任何前端任务自动触发。
- 它强制：先建紧凑 token 系统再写代码、避开三种"一眼 AI"的烂大街风格、内置质量底线（响应式/键盘焦点/reduce-motion）、自我批评。与本方案的 token-first 思路完全一致。

---

## 四、技术选型（待深度研究报告补充）

> **选型原则**：你的硬约束是「React 18 + TS + Vite + Tauri + 纯 CSS 变量、无 Tailwind」。因此**一律选 headless（无样式）库**——只接管交互行为与无障碍，样式继续用你现有的 CSS 变量写。凡是绑定 Tailwind 的方案（如 shadcn/ui）一律排除，否则等于推翻现有体系。

### 4.1 UI 组件库 → Radix UI Primitives ✅

| 候选 | 样式耦合 | 是否契合 | 裁决 |
|---|---|---|---|
| **Radix UI Primitives** | headless，零样式 | 完美——用现有 CSS 变量上色 | ✅ **首选** |
| shadcn/ui | 强依赖 Tailwind | 需引入 Tailwind，推翻现有 CSS | ❌ 排除 |
| Mantine | 自带完整样式系统 + Emotion | 与现有 token 双轨冲突 | ❌ 排除 |
| Ark UI | headless，可选 | 可用，但生态/文档不如 Radix 成熟 | 🟡 备选 |

- **装哪些**：`@radix-ui/react-dialog`（设置/确认弹窗）、`react-dropdown-menu`、`react-tabs`（集成中心/设置分区）、`react-tooltip`、`react-popover`、`react-select`。按需单包安装，tree-shaking 友好。
- **价值**：免费拿到焦点陷阱、键盘导航、ARIA、ESC 关闭、点击外部关闭等——这些正是手写组件最容易漏的交互细节。**直接治"组件交互薄弱"**，且不动一行现有视觉。

### 4.2 金融图表 → lightweight-charts（TradingView） ✅

| 候选 | 定位 | 体积 | 金融适配 | 裁决 |
|---|---|---|---|---|
| **lightweight-charts** | TradingView 出品，专做金融 | ~45KB | K线/时序/成交量原生支持 | ✅ **金融图表首选** |
| ECharts | 通用图表全家桶 | ~1MB | 有 K线但偏通用 | 🟡 通用统计图用 |
| Recharts | React 声明式通用图表 | 中 | 不擅长大数据量/K线 | ❌ 金融场景不推荐 |
| visx (airbnb) | 低层 D3 原语 | 按需 | 灵活但开发成本高 | 🟡 高度定制才考虑 |

- **分工**：K线/分时/成交量/盘口 → `lightweight-charts`（Canvas 渲染，万级数据点流畅）；因子分布/收益曲线/雷达等通用统计图 → ECharts（按需）。
- **价值**：金融图表用专业库，**直接拉满"专业感/客观性"**——TradingView 的视觉语言就是行业基准。

### 4.3 数据表格 → TanStack Table + Virtual ✅

- `@tanstack/react-table`（headless 表格逻辑：排序/筛选/分组/列固定）+ `@tanstack/react-virtual`（行虚拟化，扛万行）。
- 同样 **headless 零样式侵入**，是金融数据网格的事实标准。
- **价值**：解决大数据量持仓/行情/因子表的性能与一致性，配合阶段 2 的 tabular-nums 数字，列对齐 + 不卡顿。

### 4.4 动效 → 先不引库

- 现有 `--transition` token + CSS `transition`/`@keyframes` 已足够覆盖 hover/展开/淡入。
- 已有 `reduce-motion` 支持（`globals-layout.css:71-78`），引库前先用原生 CSS。
- 真需要复杂编排（列表重排、共享元素过渡）再上 `motion`（原 framer-motion，按需）。**避免过早引入依赖**。

### 4.5 Design Token 工具 → 暂不需要

- 你的 token 已是 CSS 变量原生形态，规模（几十个）还没到需要 Style Dictionary / Tokens Studio 跨平台同步的程度。
- **先把阶段 1-2 的刻度与语义色 token 补齐**，未来若要多端（Web + 桌面 + 设计稿）同步再引工具。

### 4.6 业界设计规范要点（金融/数据密集型）

- **信息密度**：专业终端偏高密度，行高 `1.25`（紧凑表格）到 `1.5`（正文），对应阶段 1 的 `--lh-tight/--lh-normal`。compact 密度模式已有基础（`globals-layout.css:66-69`）。
- **配色客观性**：语义色与品牌色分离——涨跌色（`--fin-up/down`）独立于通用 ok/warn/bad，避免"涨幅红"和"错误红"混淆（阶段 2 已落地此原则）。
- **方向冗余编码**：涨跌不仅靠颜色，必须叠加 `+/-` 或 ▲▼（色盲安全），阶段 2 的 `PriceDelta` 已内置。
- **深色优先**：交易终端长时间盯盘，深色减少眼疲劳——你已有深色三态，确保金融语义色在深色下对比度达 WCAG AA（4.5:1），需实测调校。

### 4.7 安装命令汇总

```bash
cd desktop
# UI primitives（按需选装）
npm i @radix-ui/react-dialog @radix-ui/react-dropdown-menu @radix-ui/react-tabs @radix-ui/react-tooltip @radix-ui/react-popover
# 金融图表
npm i lightweight-charts
# 数据表格 + 虚拟化
npm i @tanstack/react-table @tanstack/react-virtual
```

> 注：以上为纯 JS/TS 依赖，与 Tauri 打包无冲突（均在前端层）。装包属中风险操作，执行前会先与你确认。

---

## 五、执行顺序与风险

| 阶段 | 工作量 | 风险 | 可独立交付 |
|---|---|---|---|
| 1 补刻度 token | 0.5 天 | 极低（纯增量） | ✅ |
| 2 金融语义色 | 1 天 | 低 | ✅ |
| 3 统一交互态 | 1 天 | 中（需回归测试交互） | ✅ |
| 4 字体层次 | 0.5 天 | 低 | ✅ |

- 每阶段纯增量，不删现有 token，可随时回滚。
- 阶段 1 是地基，建议最先做；2 是金融产品命门，优先级次之。
- 验证：每阶段后跑 `npm run typecheck` + `npm test`，UI 改动需在 `npm run dev` 实际查看深色/浅色双模式。

---

**状态**: 🔄 迁移进行中——基础设施（token/语义色/交互层/PriceDelta/PageShell）已全部落地；本次会话修复浅色跌色 WCAG + 迁移 161 处字号 token + PriceDelta 扩面。剩余缺口：间距 token 采用、PriceDelta 继续扩面、display 字体；待用户决策 TanStack/charts 去留。
