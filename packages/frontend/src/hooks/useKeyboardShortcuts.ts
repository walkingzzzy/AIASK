import { useEffect, useCallback, useRef } from 'react'

export interface ShortcutConfig {
  key: string
  ctrl?: boolean
  shift?: boolean
  alt?: boolean
  meta?: boolean
  handler: () => void
  description?: string
}

export interface UseKeyboardShortcutsOptions {
  enabled?: boolean
  shortcuts: ShortcutConfig[]
}

const useKeyboardShortcuts = ({ enabled = true, shortcuts }: UseKeyboardShortcutsOptions) => {
  const shortcutsRef = useRef(shortcuts)
  shortcutsRef.current = shortcuts

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (!enabled) return

    const target = event.target as HTMLElement
    const isInputElement = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable

    for (const shortcut of shortcutsRef.current) {
      const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase() ||
        event.code.toLowerCase() === shortcut.key.toLowerCase()

      const ctrlMatch = shortcut.ctrl ? (event.ctrlKey || event.metaKey) : !event.ctrlKey && !event.metaKey
      const shiftMatch = shortcut.shift ? event.shiftKey : !event.shiftKey
      const altMatch = shortcut.alt ? event.altKey : !event.altKey

      if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
        if (isInputElement && !shortcut.ctrl && !shortcut.alt) continue

        event.preventDefault()
        event.stopPropagation()
        shortcut.handler()
        return
      }
    }
  }, [enabled])

  useEffect(() => {
    if (enabled) {
      window.addEventListener('keydown', handleKeyDown, true)
      return () => window.removeEventListener('keydown', handleKeyDown, true)
    }
  }, [enabled, handleKeyDown])

  return { shortcuts: shortcutsRef.current }
}

export const createAIShortcuts = (handlers: {
  onToggleAI?: () => void
  onSearch?: () => void
  onNavigate?: (key: string) => void
}): ShortcutConfig[] => [
  { key: 'q', ctrl: true, handler: () => handlers.onToggleAI?.(), description: '打开/关闭AI助手' },
  { key: 'k', ctrl: true, handler: () => handlers.onToggleAI?.(), description: '打开/关闭AI助手' },
  { key: 'p', ctrl: true, handler: () => handlers.onSearch?.(), description: '搜索股票' },
  { key: 'Escape', handler: () => handlers.onToggleAI?.(), description: '关闭AI助手' },
  { key: 'F1', handler: () => handlers.onNavigate?.('ai-score'), description: 'AI评分' },
  { key: 'F2', handler: () => handlers.onNavigate?.('fund-flow'), description: '资金流向' },
  { key: 'F3', handler: () => handlers.onNavigate?.('limit-up'), description: '涨停追踪' },
  { key: 'F4', handler: () => handlers.onNavigate?.('analysis'), description: '技术分析' },
  { key: 'F5', handler: () => handlers.onNavigate?.('research'), description: '研报' },
  { key: 'F6', handler: () => handlers.onNavigate?.('screener'), description: '选股' },
]

export default useKeyboardShortcuts
