# 前端完整快速上手设计

## 1. 目标

当前前端已经覆盖市场、研究、策略、交易、AI、通知和工作区等多个模块，但现有 `Onboarding` 只是一个四项链接列表：

- 它能把用户带到几个页面
- 但不能稳定地跨页持续引导
- 不能让用户快速理解“系统怎么串起来”
- 也没有逐步反馈和用户级完成状态

这份设计的目标不是再加几个链接，而是把 AIASK 的核心使用路径收敛成一条完整的新手链路：

1. 先认识系统结构
2. 再找到观察标的
3. 再做研究和策略判断
4. 再完成一次模拟动作
5. 最后接入风险、绩效和 AI 能力

---

## 2. 当前前端功能地图

### 2.1 一级导航分组

来自 [app-shell.tsx](/Users/mac/Desktop/股票/apps/web/components/app-shell.tsx:35)：

- 看盘
  - `/`
  - `/market`
  - `/watchlist`
- 研究
  - `/research`
  - `/fundamental`
  - `/technical`
  - `/sentiment`
- 策略
  - `/strategy-market`
  - `/backtest`
  - `/factor-analysis`
- 交易
  - `/paper-trading`
  - `/portfolio`
  - `/risk`
- AI
  - `/assistant`
  - `/search`
- 辅助入口
  - `/alerts`
  - `/notifications`
  - `/decision`
  - `/workspace-templates`

### 2.2 首页承载的系统入口

首页不是普通 landing page，而是系统总览页。它已经把主要能力按模块暴露出来：

- 实时行情与监控
- 研究分析能力
- 策略筛选与验证
- 交易执行与风控
- 进一步跳转到：
  - 行情看板
  - 研究中心
  - 策略超市
  - 风险中心

对应实现见 [page.tsx](/Users/mac/Desktop/股票/apps/web/app/page.tsx:407) 和 [page.tsx](/Users/mac/Desktop/股票/apps/web/app/page.tsx:631)。

### 2.3 关键页面的实际职责

从页面 hero、`usePageContext` 和首屏结构看，系统已经有比较清晰的任务链：

- 首页 `/`
  - 系统总览、市场脉搏、风险巡检、自选提醒、策略动态
- 行情 `/market`
  - 先锁定标的，再围绕 K 线、盘口、主图推进判断
  - 已经内建“去研究页补信息”和“快捷跳转下一步”
- 自选 `/watchlist`
  - 分组管理、股票搜索、加入观察池、后续跳到行情/研究/交易
- 研究 `/research`
  - 研报、公告、资讯聚合，承接个股理解
- 基本面 `/fundamental`
  - 财务、估值、补充资料
- 技术 `/technical`
  - 指标和形态确认
- 情绪 `/sentiment`
  - 市场情绪和辅助判断
- 策略超市 `/strategy-market`
  - 筛选、对比、订阅、进入组合和工厂动作
- 模拟交易 `/paper-trading`
  - 首笔交易引导、下单预览、账户状态、交易结果
- 执行 `/execution`
  - 执行状态、回执、artifact、后续风险/绩效复盘
- 风险 `/risk`
  - VaR、压力测试、暴露
- 绩效 `/performance`
  - 收益、归因、基准、下一跳风险/研究
- AI 中心 `/assistant`
  - 统一决策、全方位体检、产业链、日报等
- 智能搜索 `/search`
  - 语义搜索、相似股票、K 线检索
- 设置 `/settings`
  - 账户、安全、活跃会话、AI 模型配置
- 模板中心 `/workspace-templates`
  - 工作区模板、任务模板、串行编排

### 2.4 当前快速上手的实现局限

来自 [onboarding.tsx](/Users/mac/Desktop/股票/apps/web/components/onboarding.tsx:8)：

- 只有 4 步：
  - 查看行情
  - 浏览策略
  - 建立自选
  - 配置 LLM Key
- 状态只用 `localStorage['onboarding-done']`
- 展示条件依赖 `useAuthStore().user`
- 跳转使用原生 `<a href>`

这带来四个问题：

1. 完成状态是浏览器级，不是用户级
2. 页面刷新后引导连续性不稳定
3. 没有 visited / completed 反馈
4. “配置 LLM Key” 实际只跳到 `/settings`，没有直达 AI 配置 tab

---

## 3. 完整快速上手的设计原则

### 3.1 设计原则

- 不按菜单顺序引导，按用户任务顺序引导
- 一次只让用户完成一个清晰动作
- 每一步都说明“为什么做”
- 每一步都给明确的成功标准
- 每一步都尽量把上下文带到下一页
- 基础链路先完成，AI 和模板属于增强链路

### 3.2 引导结构

完整快速上手分成三层：

- 第一层：系统认知
  - 让用户知道 AIASK 是“市场 → 研究 → 策略 → 交易 → 风险/绩效”的连续链路
- 第二层：首条实践链路
  - 让用户真的完成一次从看盘到模拟动作的最短路径
- 第三层：增强能力
  - AI 配置、智能搜索、工作区模板

---

## 4. 建议的完整快速上手流程

建议改成 8 步，两段式结构：

- 必做 6 步：让用户真正“会用系统”
- 可选 2 步：让用户“用深系统”

### 第 0 步：认识系统

- 页面：`/`
- 目标：理解系统不是单页工具，而是完整投研链路
- 首屏文案：
  - 先看首页四块能力：看盘、研究、策略、交易风控
- 成功标准：
  - 用户点击“开始快速上手”
- 页面提示：
  - 在首页 hero 上方或下方插入 onboarding banner
- CTA：
  - `开始第一步：查看行情`

### 第 1 步：查看行情

- 页面：`/market?code=000001&from=onboarding`
- 目标：学会围绕一个标的查看行情、K 线、盘口
- 为什么：
  - 所有后续页面都围绕“当前标的”展开
- 页面提示：
  - 告诉用户当前正在观察哪只股票
  - 高亮“去研究页补信息”或“快捷跳转”
- 成功标准：
  - 已访问行情页
  - 且当前存在有效 `code`
- 下一步：
  - `继续：加入自选`

### 第 2 步：加入自选

- 页面：`/watchlist?tour=add-stock&code=000001&from=onboarding`
- 目标：把一个标的放进长期观察池
- 为什么：
  - 这一步把一次性浏览变成持续跟踪
- 页面提示：
  - 聚焦“搜索并添加股票”
  - 说明分组和观察池的作用
- 成功标准：
  - 至少有一个分组
  - 且自选总数 > 0
- 下一步：
  - `继续：查看研究信息`

### 第 3 步：补研究判断

- 页面：`/research?code=000001&from=onboarding`
- 目标：知道研究页是从行情走向判断的第一跳
- 为什么：
  - 行情只能看到结果，研究页负责补原因
- 页面提示：
  - 引导用户看三类内容：研报、公告、资讯
  - 给出补充跳转：
    - 基本面
    - 技术面
    - 情绪页
- 成功标准：
  - 已访问研究页
- 下一步：
  - `继续：看策略如何筛选`

### 第 4 步：浏览策略

- 页面：`/strategy-market?from=onboarding`
- 目标：理解系统不只支持单只股票，还支持策略筛选与验证
- 为什么：
  - 这里是“从标的判断”走向“方法判断”
- 页面提示：
  - 告诉用户先看筛选结果，再决定订阅/组合/工厂动作
- 成功标准：
  - 已访问策略超市
- 下一步：
  - `继续：完成一笔模拟交易`

### 第 5 步：完成模拟动作

- 页面：`/paper-trading?code=600519&tour=first-order&from=onboarding`
- 目标：理解交易链路如何从研究进入动作
- 为什么：
  - 模拟交易是新用户第一次把判断转成委托
- 页面提示：
  - 建议默认载入示例单
  - 说明“首笔交易引导、下单预览、账户状态、交易结果”这条链
- 成功标准：
  - 至少触发一次示例单加载
  - 或提交一次模拟委托
- 下一步：
  - `继续：看风险与绩效怎么复盘`

### 第 6 步：查看风险/绩效闭环

- 页面：
  - 首选 `/risk?lookbackDays=252&from=onboarding`
  - 补跳 `/performance?mode=account&days=30&from=onboarding`
- 目标：理解系统不是“下单即结束”，而是有复盘闭环
- 为什么：
  - AIASK 的价值之一是风险、绩效和后续动作联动
- 页面提示：
  - 风险页说明 VaR / 压测 / 暴露
  - 绩效页说明收益、归因、基准和下一跳
- 成功标准：
  - 风险页已访问
  - 或绩效页已访问
- 下一步：
  - `可选增强：打开 AI 能力`

### 第 7 步：配置 AI 模型

- 页面：`/settings?tab=ai&from=onboarding`
- 目标：真正打通 AI 功能，而不是只到设置首页
- 为什么：
  - 当前系统的 AI 中心、搜索和决策依赖模型配置
- 页面提示：
  - 高亮 Base URL、API Key、模型
  - 告诉用户配置后会解锁哪些功能
- 成功标准：
  - AI 配置存在且完整
- 下一步：
  - `继续：试一次 AI 决策 / 智能搜索`

### 第 8 步：试用 AI / 模板增强能力

- 页面二选一：
  - `/assistant?from=onboarding`
  - `/search?from=onboarding`
- 可选扩展：
  - `/workspace-templates?from=onboarding`
- 目标：让用户看到系统的增强层，而不是停留在普通投研页面
- 页面提示：
  - Assistant：建议先跑“统一决策”或“全方位体检”
  - Search：建议先跑语义搜索或相似股票
  - Workspace Templates：适合已经理解基础链路后再进入
- 成功标准：
  - 访问任一 AI 页面

---

## 5. 推荐的信息架构

不要再用单个平铺 checklist。改成三段式结构：

### A. 必做主线

- 认识系统
- 查看行情
- 加入自选
- 查看研究
- 浏览策略
- 完成模拟动作
- 风险 / 绩效复盘

### B. 可选增强

- 配置 AI 模型
- 使用 AI 中心
- 使用智能搜索
- 使用工作区模板

### C. 状态展示

每一步要显示：

- `未开始`
- `已访问`
- `已完成`
- `已跳过`

并显示：

- 当前第几步
- 总进度
- 下一步按钮
- 返回上一步按钮

---

## 6. 状态模型设计

### 6.1 存储方式

现有 `localStorage['onboarding-done']` 需要改成“用户级”状态，建议两层存储：

- 前端即时状态：
  - `localStorage['onboarding:v2:<userId>']`
- 后端持久化：
  - 放进 `/auth/profile.preferences.onboarding`

这样可以兼顾：

- 刷新不丢
- 换页不丢
- 同浏览器多账号互不污染
- 后续可扩展服务端同步

### 6.2 数据结构

建议结构：

```ts
type OnboardingStepStatus = 'todo' | 'visited' | 'done' | 'skipped';

type OnboardingState = {
  version: 2;
  startedAt?: string;
  completedAt?: string;
  dismissed?: boolean;
  activeStepId: string;
  steps: Record<string, {
    status: OnboardingStepStatus;
    visitedAt?: string;
    completedAt?: string;
  }>;
};
```

### 6.3 完成判定

完成判定不要只靠点击链接，要按页面实际能力判断：

- `home_intro`
  - 点击开始
- `market_first_view`
  - 有 `code` 且已访问 `/market`
- `watchlist_first_add`
  - 自选数量 > 0
- `research_first_visit`
  - 已访问 `/research`
- `strategy_market_visit`
  - 已访问 `/strategy-market`
- `paper_trade_first_action`
  - 载入示例单或提交模拟委托
- `risk_or_performance_visit`
  - 访问过 `/risk` 或 `/performance`
- `ai_config`
  - `baseUrl + apiKey + model` 完整
- `ai_first_visit`
  - 访问 `/assistant` 或 `/search`

---

## 7. 页面级实现建议

### 7.1 Onboarding 容器

现有右下角浮层保留，但升级成：

- 首页初次进入：
  - 默认展开
- 其他页面：
  - 缩成悬浮条
- 点击后：
  - 展开当前步骤、目标、成功标准、下一步 CTA

### 7.2 页面深链

当前步骤链接要改成客户端导航，避免整页刷新导致状态链断开：

- 把 `<a href>` 改成 `next/link`
- 或显式 `router.push`

同时引入深链参数：

- `/settings?tab=ai`
- `/watchlist?tour=add-stock`
- `/paper-trading?tour=first-order&code=600519`
- `/market?code=000001`

### 7.3 页面锚点 / data 属性

系统里已经有少量 `data-tour` 约定，可以扩展成统一的 onboarding anchor：

- `data-onboarding="home-start"`
- `data-onboarding="market-quick-jump"`
- `data-onboarding="watchlist-search"`
- `data-onboarding="settings-ai-tab"`
- `data-onboarding="paper-trading-example-order"`

这样后续可以做：

- 高亮
- 箭头指引
- 首次弹层说明

### 7.4 首页总览入口

首页要成为 onboarding hub，而不是只弹一个右下角卡片：

- 在首页 hero 下增加“开始快速上手”主按钮
- 增加“系统怎么工作”简图：
  - 看盘 → 研究 → 策略 → 交易 → 风险/绩效 → AI 增强

---

## 8. 文案策略

当前引导文案偏“动作描述”，但缺少“为什么做”。完整文案建议遵循这个格式：

- 标题：告诉用户现在在做什么
- 说明：告诉用户为什么做
- 成功标准：告诉用户做成了算什么
- 下一步：告诉用户接下来去哪

示例：

- 标题：先锁定一只观察标的
- 说明：后续研究、自选、交易和 AI 分析都会围绕当前标的展开
- 成功标准：进入行情页并带上股票代码
- 下一步：把它加入自选，形成持续跟踪

---

## 9. MVP 与完整版本

### 9.1 MVP

建议先落这 5 项：

1. 状态改成按 `userId` 存储
2. 步骤链接改成客户端导航
3. 增加 `visited` / `done` 状态
4. 把“配置 LLM Key”改成直达 `/settings?tab=ai`
5. 扩展成 6 步主线流程

### 9.2 第二阶段

再补这 5 项：

1. 页面锚点高亮
2. 首页系统流程图
3. 页面内“本步骤说明” banner
4. 服务端同步 onboarding 状态
5. 可选增强路径：AI / 搜索 / 工作区模板

---

## 10. 结论

基于当前前端实现，AIASK 已经具备完整的新手主路径，只是还没有被组织成一条连续、稳定、可感知的 onboarding。

完整快速上手不应该只是：

- 行情
- 策略
- 自选
- 设置

而应该是：

- 首页认识系统
- 行情锁定标的
- 自选形成观察池
- 研究补判断
- 策略看方法
- 模拟交易做动作
- 风险 / 绩效做闭环
- AI / 搜索 / 模板做增强

这条路径更符合当前前端真实能力，也更能帮助用户快速理解整个系统。
