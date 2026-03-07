# AIASK 可访问性 (a11y) 审计报告

> T-027 | 审计日期: 2026-03-01

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
