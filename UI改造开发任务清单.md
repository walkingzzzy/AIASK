# AIASK UI改造开发任务清单

更新时间：2026-03-27
对应方案文档：[UI改造方案.md](/Users/mac/Desktop/股票/UI改造方案.md)

## 1. 使用方式

这份清单用于把 UI 改造方案转成可执行开发任务。建议按阶段推进，每个阶段都先完成“设计基底”再改“页面结构”，避免页面局部先改、后续又被全局 token 推翻。

建议执行顺序：

1. 全局视觉基底
2. 全局壳层与导航
3. 首页
4. 行情页
5. 策略超市
6. 登录/注册
7. Onboarding 与空状态
8. 收尾、联调、验收

## 2. 总体排期建议

### P0：设计基底与壳层

目标：先把产品气质和整体结构改对。

- T01 全局 token 重构
- T02 基础组件视觉分级重做
- T03 AppShell 结构改造
- T04 桌面导航信息架构压缩
- T05 移动导航与抽屉重构

### P1：核心页面

目标：优先提升最高频使用页面的可读性与任务聚焦。

- T06 首页重构
- T07 行情页重构
- T08 策略超市重构

### P2：辅助页面与体验细节

目标：补齐首登体验、认证体验、空状态、AI 入口一致性。

- T09 登录页重构
- T10 注册页重构
- T11 Onboarding 轻量化
- T12 空状态与 CTA 统一
- T13 Copilot / AI 入口重构

### P3：验收与回归

目标：保证重构后没有可用性回退。

- T14 响应式回归
- T15 样式一致性清理
- T16 页面截图与验收清单

## 3. 任务清单

## T01 全局 Token 重构

优先级：P0
目标：建立新的颜色、字体、间距、圆角、阴影 token，替换当前玻璃化默认基底。

涉及文件：

- [globals.css](/Users/mac/Desktop/股票/apps/web/app/globals.css)
- [layout.tsx](/Users/mac/Desktop/股票/apps/web/app/layout.tsx)

子任务：

1. 新建或重构颜色 token，拆分 `background/surface/border/text/brand/semantic`。
2. 去掉 `body` 的多段紫蓝渐变，改成低干扰浅中性背景。
3. 重构字体 token，引入主字体与数字/代码字体。
4. 调整 `themeColor`，与新品牌主色保持一致。
5. 重新定义阴影与边框权重，降低全局 blur 依赖。
6. 保留 dark mode，但同步修正其颜色职责，不再沿用紫色偏置。

验收标准：

- 页面背景明显更克制。
- 非浮层组件不再默认依赖 glass 视觉。
- 主文本、次文本、边框、surface 层次清楚。

依赖：

- 无

## T02 基础组件视觉分级重做

优先级：P0
目标：建立主操作、次操作、弱操作的稳定视觉差异。

涉及范围：

- `apps/web/components/ui/*`
- [globals.css](/Users/mac/Desktop/股票/apps/web/app/globals.css)

建议重点检查文件：

- `apps/web/components/ui/section-card.tsx`
- `apps/web/components/ui/kpi-card.tsx`
- `apps/web/components/ui/tab-bar.tsx`
- `apps/web/components/ui/data-table.tsx`

子任务：

1. 重构按钮层级：`Primary / Secondary / Tertiary / Ghost / Danger / Link`。
2. 重构输入框与下拉框样式，去掉默认 glass 输入框。
3. 重构 `SectionCard` 与 `KpiCard`，弱化 hover 装饰性，强化结构性。
4. 重构 `TabBar`，建立更清晰的 active/inactive 对比。
5. 重构 `DataTable` 的表头、分隔线、sticky 区域背景。

验收标准：

- 一个模块里主按钮只会有一个最强视觉焦点。
- 输入框与卡片不再像漂浮玻璃片。
- 表格比卡片更适合高密度数据展示。

依赖：

- T01

## T03 AppShell 结构改造

优先级：P0
目标：把壳层统一成“左 rail + 中央主画布 + 按需右抽屉”。

涉及文件：

- [app-shell.tsx](/Users/mac/Desktop/股票/apps/web/components/app-shell.tsx)
- [layout.tsx](/Users/mac/Desktop/股票/apps/web/app/layout.tsx)

子任务：

1. 简化顶部栏信息密度，保留标题、通知、用户入口、关键状态。
2. 取消页面级右侧辅助区与全局右侧 Copilot 并存的结构。
3. 收紧左侧 rail 的视觉分量，降低边框与玻璃感。
4. 调整内容区最大宽度策略，区分 `focused` 和 `full width` 页面。
5. 统一桌面与移动端的 overlay 层级，避免多个固定层互相打架。

验收标准：

- 桌面端不再出现“两套右侧辅助结构”。
- 顶部栏不会与页面内容争夺过多注意力。
- 中央内容区成为绝对视觉主轴。

依赖：

- T01
- T02

## T04 桌面导航信息架构压缩

优先级：P0
目标：从功能清单式导航改成工作流式导航。

涉及文件：

- [app-shell.tsx](/Users/mac/Desktop/股票/apps/web/components/app-shell.tsx)

当前导航定义位置：

- [app-shell.tsx](/Users/mac/Desktop/股票/apps/web/components/app-shell.tsx#L31)

子任务：

1. 把现有 5 大类 + 多个叶子入口压缩为 5 个工作流入口。
2. 重新定义一级导航标签与图标体系。
3. 把低频页面迁入工作流落地页的二级 tabs 或命令面板。
4. 优化 `CompactNav`，避免仅显示文字截断的弱可识别方案。

验收标准：

- 一级导航总数控制在 5 个左右。
- 新用户能够快速理解每个入口的用途。
- 折叠状态下仍具备较好的识别度。

依赖：

- T03

## T05 移动导航与抽屉重构

优先级：P0
目标：解决移动端“双导航系统”问题。

涉及文件：

- [mobile-nav.tsx](/Users/mac/Desktop/股票/apps/web/components/mobile-nav.tsx)
- [global-overlays.tsx](/Users/mac/Desktop/股票/apps/web/components/global-overlays.tsx)
- [app-shell.tsx](/Users/mac/Desktop/股票/apps/web/components/app-shell.tsx)

子任务：

1. 保留底部 5 导航，重新定义信息架构与 icon 风格。
2. 抽屉导航改成“更多/工作流切换”，不再全量镜像桌面树。
3. 调整顶部栏在移动端的控件数量，减少横向挤压。
4. 检查底部导航与页面内固定按钮的安全区冲突。

验收标准：

- 手机上不会同时存在两套同等级导航体系。
- 底部导航明确承载高频入口。
- 抽屉承担低频补充，而非第二主导航。

依赖：

- T03
- T04

## T06 首页重构

优先级：P1
目标：把首页改成“今日工作台”。

涉及文件：

- [app/page.tsx](/Users/mac/Desktop/股票/apps/web/app/page.tsx)
- [MarketOverview.tsx](/Users/mac/Desktop/股票/apps/web/components/home/MarketOverview.tsx)
- [PersonalDashboard.tsx](/Users/mac/Desktop/股票/apps/web/components/home/PersonalDashboard.tsx)
- [FundFlowSection.tsx](/Users/mac/Desktop/股票/apps/web/components/home/FundFlowSection.tsx)
- [DashboardCards.tsx](/Users/mac/Desktop/股票/apps/web/components/home/DashboardCards.tsx)
- [SystemStatus.tsx](/Users/mac/Desktop/股票/apps/web/components/home/SystemStatus.tsx)

子任务：

1. 重新定义首页首屏模块，只保留市场状态、今日任务、持仓/自选、关键提醒。
2. 将当前大面积空状态卡片改成紧凑提示 + CTA。
3. 把健康状态、模块状态、低优先级信息下沉到第二屏或折叠区。
4. 重构欢迎区，不再让欢迎文案抢占过多空间。
5. 统一首页 KPI 数字与说明文字的层级。

验收标准：

- 首页首屏模块数减少。
- 用户能在 3-5 秒内知道“现在最该做什么”。
- 空状态不再形成大面积白洞。

依赖：

- T01
- T02
- T03

## T07 行情页重构

优先级：P1
目标：把行情页改成真正的“高频看盘工作台”。

涉及文件：

- [market/page.tsx](/Users/mac/Desktop/股票/apps/web/app/market/page.tsx)
- `apps/web/components/charts/*`
- `apps/web/components/ui/*`

子任务：

1. 重构首屏布局为“主图优先 + 右侧摘要”。
2. 把顶部筛选区压缩成更紧凑的 task bar。
3. 合并页面内右侧摘要动作区，避免第二套辅助布局逻辑。
4. 优化 tab 结构，把板块、逐笔、指数、分时等作为下方信息层。
5. 重构盘口与行情摘要的数字对齐、标签顺序与间距。
6. 移动端单独做信息重组，不直接缩放桌面布局。
7. 检查保存视图、预设视图、示例标的的展示方式，改成更轻量的 chips / segmented controls。

验收标准：

- 首屏先看到图和价，再看到操作。
- 图表区明显大于控件区。
- 移动端首屏仍能舒适看图，不被摘要和快捷操作挤压。

依赖：

- T01
- T02
- T03
- T05

## T08 策略超市重构

优先级：P1
目标：从卡片墙转向高密度可比较视图。

涉及文件：

- [strategy-market/page.tsx](/Users/mac/Desktop/股票/apps/web/app/strategy-market/page.tsx)
- [strategy-card.tsx](/Users/mac/Desktop/股票/apps/web/components/strategy-card.tsx)
- `apps/web/app/strategy-market/components/*`

子任务：

1. 新增表格或 list-table 默认视图。
2. 把卡片视图降级为精选策略或推荐策略展示。
3. 工厂摘要保留，但进一步收敛为 summary bar。
4. 重构筛选、搜索、排序和加入组合的交互位置。
5. 对 `0.00%`、`0订阅` 这类低信号字段做弱化。
6. 检查详情页跳转逻辑，确保从列表到详情再返回时上下文不丢失。

验收标准：

- 用户可在一个屏幕内比较多个策略关键指标。
- 卡片不再承担高密度比较任务。
- 工厂运行态不会淹没策略选择主任务。

依赖：

- T01
- T02
- T03

## T09 登录页重构

优先级：P2
目标：去掉模板化玻璃登录页风格，改成更专业、更克制的金融入口页。

涉及文件：

- [login/page.tsx](/Users/mac/Desktop/股票/apps/web/app/login/page.tsx)
- [login/layout.tsx](/Users/mac/Desktop/股票/apps/web/app/login/layout.tsx)

子任务：

1. 去掉紫色渐变和高玻璃感双栏。
2. 左侧价值表达改为更简洁、可信的产品说明。
3. 右侧表单卡片做成更实体的登录面板。
4. 优化标题、辅助文案、字段标签、错误提示的层级。
5. 移动端改成单列优先，不保留不必要的装饰区域。

验收标准：

- 登录页更像金融产品，不像通用 SaaS 模板。
- 表单成为首屏唯一强焦点。

依赖：

- T01
- T02

## T10 注册页重构

优先级：P2
目标：让注册页与登录页风格统一，同时简化信息负担。

涉及文件：

- [register/page.tsx](/Users/mac/Desktop/股票/apps/web/app/register/page.tsx)
- [register/layout.tsx](/Users/mac/Desktop/股票/apps/web/app/register/layout.tsx)

子任务：

1. 统一注册与登录的视觉语言。
2. 简化左侧说明卡数量，避免首屏文案过多。
3. 优化错误提示、密码校验、确认密码反馈的可读性。
4. 调整移动端表单间距与 CTA 位置。

验收标准：

- 注册页不再出现信息块过多、解释过满的问题。
- 表单填写路径直观、轻量。

依赖：

- T09

## T11 Onboarding 轻量化

优先级：P2
目标：从全屏遮罩式引导改成轻量 checklist 或渐进式 coach mark。

涉及文件：

- [onboarding.tsx](/Users/mac/Desktop/股票/apps/web/components/onboarding.tsx)
- [app-shell.tsx](/Users/mac/Desktop/股票/apps/web/components/app-shell.tsx)

子任务：

1. 移除首次进入即全屏黑罩 + 强 spotlight 的默认方式。
2. 改成角落 checklist、轻量提示点或局部气泡。
3. 提供明确的“稍后再看”与“永久关闭”逻辑。
4. 仅在关键首次场景出现，而不是抢占首页首屏。

验收标准：

- 新用户首次进入能先看见页面内容。
- 引导变成辅助，而不是阻断。

依赖：

- T03

## T12 空状态与 CTA 统一

优先级：P2
目标：减少空卡片占位，提高 CTA 直接性。

涉及范围：

- 首页模块
- 行情页空状态
- 策略页空状态
- 其他常用页面中的 `EmptyState`

建议检查：

- [market/page.tsx](/Users/mac/Desktop/股票/apps/web/app/market/page.tsx)
- [strategy-market/page.tsx](/Users/mac/Desktop/股票/apps/web/app/strategy-market/page.tsx)
- [app/page.tsx](/Users/mac/Desktop/股票/apps/web/app/page.tsx)
- `apps/web/components/status-state.tsx`

子任务：

1. 统一空状态组件规格：图标、标题、说明、CTA。
2. 压缩空状态高度，减少大面积留白。
3. CTA 文案统一为动词优先，例如“去看行情”“去建组合”“去策略超市”。

验收标准：

- 空状态不再成为首屏主体。
- 每个空状态都能明确下一步动作。

依赖：

- T02
- T06
- T07
- T08

## T13 Copilot / AI 入口重构

优先级：P2
目标：让 AI 成为上下文辅助层，而不是常驻分裂注意力的第二个主界面。

涉及文件：

- [app-shell.tsx](/Users/mac/Desktop/股票/apps/web/components/app-shell.tsx)
- [copilot-dock.tsx](/Users/mac/Desktop/股票/apps/web/components/copilot-dock.tsx)
- 相关页面中的 AI 入口按钮

子任务：

1. 明确全局 Copilot 与页面上下文 AI 的职责边界。
2. 让 Copilot 默认收起，按需唤起。
3. 在首页、行情页、策略页添加更明确的上下文 AI 入口。
4. 为 AI 输出增加统一标识、解释入口、建议动作区。

验收标准：

- AI 区域不会再和页面主任务争夺首屏。
- 用户能理解“什么时候该用 AI，AI 正在帮助什么任务”。

依赖：

- T03
- T06
- T07
- T08

## T14 响应式回归

优先级：P3
目标：确保改造后桌面与移动端都可用。

涉及范围：

- 首页
- 行情页
- 策略超市
- 登录页
- 注册页
- 壳层与导航

建议断点：

- `390x844`
- `768x1024`
- `1280x800`
- `1440x900`

子任务：

1. 检查固定头部、底部导航、抽屉、右侧面板的层级冲突。
2. 检查移动端 safe area。
3. 检查图表、表格、筛选区在中等宽度下的折行与溢出。

验收标准：

- 关键页面在主要断点无明显布局崩坏。
- 不出现底部导航遮挡内容或抽屉无法关闭的问题。

依赖：

- T05
- T06
- T07
- T08
- T09
- T10

## T15 样式一致性清理

优先级：P3
目标：消除新旧视觉语言混用。

涉及范围：

- `apps/web/components/**/*`
- `apps/web/app/**/*`

子任务：

1. 全局搜索遗留 `glass`、`glass-strong`、`bg-white/xx`、`purple` 类样式。
2. 清理旧的视觉 token 与无用样式类。
3. 修正新旧组件混用导致的视觉跳变。

验收标准：

- 不再出现局部页面仍然保持旧玻璃风。
- 新视觉语言在核心页面中一致。

依赖：

- 所有前序任务

## T16 页面截图与验收清单

优先级：P3
目标：把主观设计判断转成可回归的交付物。

建议输出：

- 登录页前后对比截图
- 首页前后对比截图
- 行情页前后对比截图
- 策略页前后对比截图
- 移动端行情页前后对比截图

子任务：

1. 用 Playwright 录制改造后的关键页面截图。
2. 建立验收对照表，覆盖视觉、布局、导航、响应式、空状态、AI 入口。
3. 标注已完成项、剩余问题和后续增强项。

验收标准：

- 核心页面都能形成可对比的交付证据。
- 后续迭代可以基于截图和清单继续推进。

依赖：

- 所有前序任务

## 4. 建议的实际开发顺序

如果直接开工，建议按下面顺序提交：

1. `feat(ui): rebuild global design tokens and surfaces`
2. `feat(shell): simplify app shell and navigation structure`
3. `feat(home): redesign dashboard landing page`
4. `feat(market): refactor market workspace layout`
5. `feat(strategy): switch strategy market to comparison-first view`
6. `feat(auth): redesign login and register pages`
7. `feat(onboarding): replace blocking onboarding with lightweight guide`
8. `chore(ui): sweep legacy glass styles and responsive regressions`

## 5. 建议的验收维度

### 视觉

- 背景是否退后
- 信息是否前置
- 主次操作是否清楚
- 字体层级是否拉开

### 结构

- 导航是否按工作流组织
- 首页是否任务导向
- 行情页是否图表优先
- 策略页是否比较优先

### 交互

- AI 是否是辅助层而不是干扰层
- Onboarding 是否轻量
- 空状态是否直接给出下一步

### 响应式

- 手机上是否仍然可用
- 平板和中屏下是否出现拥挤
- 固定区域是否遮挡主内容

## 6. 推荐先改的文件列表

第一批建议优先改：

- [globals.css](/Users/mac/Desktop/股票/apps/web/app/globals.css)
- [app-shell.tsx](/Users/mac/Desktop/股票/apps/web/components/app-shell.tsx)
- [mobile-nav.tsx](/Users/mac/Desktop/股票/apps/web/components/mobile-nav.tsx)
- [global-overlays.tsx](/Users/mac/Desktop/股票/apps/web/components/global-overlays.tsx)
- [app/page.tsx](/Users/mac/Desktop/股票/apps/web/app/page.tsx)
- [market/page.tsx](/Users/mac/Desktop/股票/apps/web/app/market/page.tsx)
- [strategy-market/page.tsx](/Users/mac/Desktop/股票/apps/web/app/strategy-market/page.tsx)

第二批再改：

- [login/page.tsx](/Users/mac/Desktop/股票/apps/web/app/login/page.tsx)
- [register/page.tsx](/Users/mac/Desktop/股票/apps/web/app/register/page.tsx)
- [onboarding.tsx](/Users/mac/Desktop/股票/apps/web/components/onboarding.tsx)
- [copilot-dock.tsx](/Users/mac/Desktop/股票/apps/web/components/copilot-dock.tsx)

## 7. 结论

这次 UI 改造不适合做零散小修，而适合按“基底 -> 壳层 -> 核心页 -> 体验细节”的顺序连续推进。只要顺序反了，就容易出现页面先改、全局再推翻，或者风格改了但结构没改，最终只得到一版“更好看的旧问题”。
