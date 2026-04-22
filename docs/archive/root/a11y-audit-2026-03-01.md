# AIASK 可访问性 (a11y) 审计报告

> T-027 | 审计日期: 2026-03-01

> 校准说明：本文记录的是一次特定时间点的前端可访问性审计与修复结果，不代表后续代码变更后仍自动保持同等合规状态。
>
> 若需把其中结论作为“当前事实”引用，应结合最新页面实现、组件回归测试或重新审计结果再次确认。

> 2026-04-07 快速复核补充：本文提到的核心组件路径仍存在于当前代码中，且代码检索仍能看到主要 ARIA 语义已保留；但这次只做了静态路径与属性核对，没有重新执行完整的 WCAG 审计或页面级回归。

## 2026-04-07 快速复核

### 当前仍可对上的核心组件

- `apps/web/components/app-shell.tsx`
- `apps/web/components/spotlight.tsx`
- `apps/web/components/ui/extended.tsx`
- `apps/web/components/ui/toast.tsx`
- `apps/web/components/ui/tab-bar.tsx`
- `apps/web/components/ui/skeleton.tsx`
- `apps/web/app/globals.css`

### 当前静态检索仍可见的可访问性语义

- `app-shell.tsx` 仍保留导航展开/收起的 `aria-label` 与装饰层 `aria-hidden`
- `spotlight.tsx` 仍保留 `role="dialog"`、`aria-modal`、`role="listbox"`、`role="option"` 等搜索交互语义
- `ui/toast.tsx` 和 `alert-toast.tsx` 仍保留 `aria-live` 提示区域
- `ui/extended.tsx`、`confirm-dialog.tsx`、`CartDrawer.tsx` 仍保留对话框语义
- `ui/tab-bar.tsx` 仍保留 `role="tablist"`

### 这次复核没有覆盖的内容

- 没有重新跑整站键盘导航
- 没有重新做颜色对比度测量
- 没有重新做屏幕阅读器实测
- 没有新增自动化 a11y 测试脚本验证


## 审计范围

对 AIASK 前端 Web 应用核心 UI 组件进行 WCAG 2.1 AA 级可访问性审计与修复。

## 变更清单

| 组件 | 变更内容 |
|------|---------|
| `app-shell.tsx` | ① nav 添加 `aria-label="主导航菜单"` ② 折叠按钮添加 `aria-expanded` + `aria-label` ③ 汉堡/关闭按钮添加 `aria-label` ④ header 添加 `role="banner"` ⑤ 退出按钮添加 `aria-label` ⑥ 装饰图标添加 `aria-hidden` |
| `extended.tsx` | ① Modal 添加 `aria-modal="true"` + `aria-labelledby` ② 关闭按钮添加 `aria-label` ③ Tooltip 添加 `role="tooltip"` |
| `toast.tsx` | ① 容器添加 `role="status"` + `aria-live="polite"` ② 单条添加 `role="alert"` |
| `tab-bar.tsx` | ① 容器添加 `role="tablist"` ② 按钮添加 `role="tab"` + `aria-selected` + `tabIndex` |
| `skeleton.tsx` | 添加 `aria-hidden="true"` |
| `spotlight.tsx` | ① 对话框添加 `role="dialog"` + `aria-modal` ② 输入添加 `aria-label` + `aria-autocomplete` + `aria-activedescendant` ③ 列表添加 `role="listbox"` ④ 选项添加 `role="option"` + `aria-selected` |

## 键盘导航支持

- **Tab 导航**: TabBar 组件通过 `tabIndex={0 | -1}` 实现 roving tabindex 模式
- **⌘K 快捷键**: Spotlight 搜索支持键盘打开/关闭
- **↑↓ 方向键**: Spotlight 搜索结果支持键盘导航
- **ESC 关闭**: Modal 和 Spotlight 支持 ESC 键关闭

## 颜色对比度

- 主题系统使用 CSS 变量，暗黑/亮色模式均保持足够对比度
- 涨跌颜色（红/绿）已在 `globals.css` 中定义语义色
