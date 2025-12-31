import React from 'react'
import { Tooltip } from 'antd'
import {
  RobotOutlined,
  LineChartOutlined,
  FundOutlined,
  RiseOutlined,
  FileTextOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons'

export interface BottomBarItem {
  key: string
  label: string
  icon: React.ReactNode
  shortcut?: string
  onClick?: () => void
}

export interface BottomBarProps {
  items?: BottomBarItem[]
  activeKey?: string
  onItemClick?: (key: string) => void
  onAIClick?: () => void
}

const COLORS = {
  bg: '#0d1117',
  border: '#30363d',
  text: '#e6edf3',
  textSecondary: '#8b949e',
  primary: '#58a6ff',
  hover: '#21262d',
}

const containerStyle: React.CSSProperties = {
  height: 42,
  background: COLORS.bg,
  borderTop: `1px solid ${COLORS.border}`,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '0 16px',
  gap: 4,
}

const itemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 12px',
  borderRadius: 6,
  cursor: 'pointer',
  color: COLORS.textSecondary,
  fontSize: 12,
  transition: 'all 0.2s',
  border: 'none',
  background: 'transparent',
}

const defaultItems: BottomBarItem[] = [
  { key: 'ai-score', label: 'AI评分', icon: <RobotOutlined />, shortcut: 'F1' },
  { key: 'fund-flow', label: '资金流向', icon: <FundOutlined />, shortcut: 'F2' },
  { key: 'limit-up', label: '涨停追踪', icon: <RiseOutlined />, shortcut: 'F3' },
  { key: 'analysis', label: '技术分析', icon: <LineChartOutlined />, shortcut: 'F4' },
  { key: 'research', label: '研报', icon: <FileTextOutlined />, shortcut: 'F5' },
  { key: 'screener', label: '选股', icon: <SearchOutlined />, shortcut: 'F6' },
  { key: 'settings', label: '设置', icon: <SettingOutlined /> },
]

const BottomBar: React.FC<BottomBarProps> = ({
  items = defaultItems,
  activeKey,
  onItemClick,
  onAIClick,
}) => {
  const handleClick = (key: string) => {
    if (key === 'ai-chat') {
      onAIClick?.()
    } else {
      onItemClick?.(key)
    }
  }

  return (
    <div style={containerStyle}>
      {items.map((item) => {
        const isActive = activeKey === item.key
        const tooltipTitle = item.shortcut ? `${item.label} (${item.shortcut})` : item.label

        return (
          <Tooltip key={item.key} title={tooltipTitle} placement="top">
            <button
              style={{
                ...itemStyle,
                color: isActive ? COLORS.primary : COLORS.textSecondary,
                background: isActive ? COLORS.hover : 'transparent',
              }}
              onClick={() => handleClick(item.key)}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.color = COLORS.text
                  e.currentTarget.style.background = COLORS.hover
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.color = COLORS.textSecondary
                  e.currentTarget.style.background = 'transparent'
                }
              }}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          </Tooltip>
        )
      })}

      <div style={{ width: 1, height: 20, background: COLORS.border, margin: '0 8px' }} />

      <Tooltip title="智能问答 (Ctrl+Q)" placement="top">
        <button
          style={{
            ...itemStyle,
            color: COLORS.primary,
            background: 'rgba(88, 166, 255, 0.1)',
            border: `1px solid ${COLORS.primary}`,
          }}
          onClick={onAIClick}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(88, 166, 255, 0.2)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(88, 166, 255, 0.1)'
          }}
        >
          <RobotOutlined />
          <span>AI助手</span>
        </button>
      </Tooltip>
    </div>
  )
}

export default BottomBar
