import React, { useState, useCallback, useEffect } from 'react'
import { Layout, Button, Tooltip } from 'antd'
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  LeftOutlined,
  RightOutlined,
} from '@ant-design/icons'

const { Sider, Content } = Layout

//====================类型定义 ====================

export interface MainLayoutProps {
  /** 左侧边栏内容 */
  leftSidebar?: React.ReactNode
  /** 中间主区域内容 */
  mainContent: React.ReactNode
  /** 右侧边栏内容 */
  rightSidebar?: React.ReactNode
  /** 左侧边栏宽度，默认 220px */
  leftSiderWidth?: number
  /** 右侧边栏宽度，默认 320px */
  rightSiderWidth?: number
  /** 折叠后的宽度，默认 48px */
  collapsedWidth?: number
  /** 左侧边栏默认折叠状态 */
  defaultLeftCollapsed?: boolean
  /** 右侧边栏默认折叠状态 */
  defaultRightCollapsed?: boolean
  /** 左侧边栏折叠状态变化回调 */
  onLeftCollapse?: (collapsed: boolean) => void
  /** 右侧边栏折叠状态变化回调 */
  onRightCollapse?: (collapsed: boolean) => void
  /** 左侧边栏标题 */
  leftSiderTitle?: React.ReactNode
  /** 右侧边栏标题 */
  rightSiderTitle?: React.ReactNode
  /** 是否显示左侧边栏 */
  showLeftSider?: boolean
  /** 是否显示右侧边栏 */
  showRightSider?: boolean
  /** 自定义样式 */
  style?: React.CSSProperties
  /** 自定义类名 */
  className?: string
}

//==================== 常量定义 ====================

// localStorage键名
const STORAGE_KEY_LEFT = 'mainLayout_leftCollapsed'
const STORAGE_KEY_RIGHT = 'mainLayout_rightCollapsed'

// ==================== 样式常量 ====================

const COLORS = {
  bg: '#0d1117',
  siderBg: '#161b22',
  contentBg: '#1c2128',
  border: '#21262d',
  text: '#e6edf3',
  textSecondary: '#8b949e',
  primary: '#58a6ff',
  hover: '#262c36',
}

const siderStyle: React.CSSProperties = {
  background: COLORS.siderBg,
  borderColor: COLORS.border,
  height: '100%',
  overflow: 'hidden',
  display: 'flex',
  flexDirection: 'column',
}

const siderHeaderStyle: React.CSSProperties = {
  height: 48,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '0 12px',
  borderBottom: `1px solid ${COLORS.border}`,
  flexShrink: 0,
}

const siderContentStyle: React.CSSProperties = {
  flex: 1,
  overflow: 'auto',
  padding: '8px 0',
}

const collapseButtonStyle: React.CSSProperties = {
  width: 28,
  height: 28,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: 6,
  cursor: 'pointer',
  color: COLORS.textSecondary,
  transition: 'all 0.2s',border: 'none',
  background: 'transparent',
}

const mainContentStyle: React.CSSProperties = {
  background: COLORS.contentBg,
  borderRadius: 12,
  margin: 16,
  padding: 0,
  overflow: 'auto',
  minHeight: 'calc(100vh - 32px)',
}

// ==================== 工具函数 ====================

/**
 * 从localStorage获取折叠状态
 * @param key localStorage键名
 * @param defaultValue 默认值
 * @returns 折叠状态
 */
const getCollapsedFromStorage = (key: string, defaultValue: boolean): boolean => {
  try {
    const stored = localStorage.getItem(key)
    return stored !== null ? stored === 'true' : defaultValue
  } catch (error) {
    console.warn(`Failed to read ${key} from localStorage:`, error)
    return defaultValue
  }
}

/**
 * 保存折叠状态到localStorage
 * @param key localStorage键名
 * @param value 折叠状态
 */
const saveCollapsedToStorage = (key: string, value: boolean): void => {
  try {
    localStorage.setItem(key, String(value))
  } catch (error) {
    console.warn(`Failed to save ${key} to localStorage:`, error)
  }
}

// ==================== 子组件 ====================

interface CollapseButtonProps {
  collapsed: boolean
  position: 'left' | 'right'
  onClick: () => void
}

const CollapseButton: React.FC<CollapseButtonProps> = ({
  collapsed,
  position,
  onClick,
}) => {
  const getIcon = () => {
    if (position === 'left') {
      return collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />
    }
    return collapsed ? <LeftOutlined /> : <RightOutlined />
  }

  const tooltip = collapsed ? '展开' : '折叠'

  return (
    <Tooltip title={tooltip} placement={position === 'left' ? 'right' : 'left'}>
      <Button
        type="text"
        icon={getIcon()}
        onClick={onClick}
        style={collapseButtonStyle}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = COLORS.text
          e.currentTarget.style.background = COLORS.hover
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = COLORS.textSecondary
          e.currentTarget.style.background = 'transparent'
        }}
      />
    </Tooltip>
  )
}

interface SiderHeaderProps {
  title?: React.ReactNode
  collapsed: boolean
  position: 'left' | 'right'
  onCollapse: () => void
}

const SiderHeader: React.FC<SiderHeaderProps> = ({
  title,
  collapsed,
  position,
  onCollapse,
}) => {
  if (collapsed) {
    return (
      <div style={{ ...siderHeaderStyle, justifyContent: 'center', padding: 0 }}>
        <CollapseButton collapsed={collapsed} position={position} onClick={onCollapse} />
      </div>
    )
  }

  return (
    <div style={siderHeaderStyle}>
      {position === 'left' ? (
        <>
          <span style={{ color: COLORS.text, fontWeight: 500, fontSize: 14 }}>
            {title}
          </span>
          <CollapseButton collapsed={collapsed} position={position} onClick={onCollapse} />
        </>
      ) : (
        <>
          <CollapseButton collapsed={collapsed} position={position} onClick={onCollapse} />
          <span style={{ color: COLORS.text, fontWeight: 500, fontSize: 14 }}>
            {title}
          </span>
        </>
      )}
    </div>
  )
}

// ==================== 主组件 ====================

const MainLayout: React.FC<MainLayoutProps> = ({
  leftSidebar,
  mainContent,
  rightSidebar,
  leftSiderWidth = 220,
  rightSiderWidth = 320,
  collapsedWidth = 48,
  defaultLeftCollapsed = false,
  defaultRightCollapsed = false,
  onLeftCollapse,
  onRightCollapse,
  leftSiderTitle = '导航',
  rightSiderTitle = 'AI助手',
  showLeftSider = true,
  showRightSider = true,
  style,
  className,
}) => {
  //从localStorage初始化折叠状态
  const [leftCollapsed, setLeftCollapsed] = useState(() =>
    getCollapsedFromStorage(STORAGE_KEY_LEFT, defaultLeftCollapsed)
  )
  const [rightCollapsed, setRightCollapsed] = useState(() =>
    getCollapsedFromStorage(STORAGE_KEY_RIGHT, defaultRightCollapsed)
  )

  // 监听折叠状态变化，保存到localStorage
  useEffect(() => {
    saveCollapsedToStorage(STORAGE_KEY_LEFT, leftCollapsed)
  }, [leftCollapsed])

  useEffect(() => {
    saveCollapsedToStorage(STORAGE_KEY_RIGHT, rightCollapsed)
  }, [rightCollapsed])

  const handleLeftCollapse = useCallback(() => {
    const newState = !leftCollapsed
    setLeftCollapsed(newState)
    onLeftCollapse?.(newState)
  }, [leftCollapsed, onLeftCollapse])

  const handleRightCollapse = useCallback(() => {
    const newState = !rightCollapsed
    setRightCollapsed(newState)
    onRightCollapse?.(newState)
  }, [rightCollapsed, onRightCollapse])

  return (
    <Layout
      className={className}
      style={{
        minHeight: '100vh',
        background: COLORS.bg,
        ...style,
      }}
    >
      {/* 左侧边栏 */}
      {showLeftSider && (
        <Sider
          width={leftSiderWidth}
          collapsedWidth={collapsedWidth}
          collapsed={leftCollapsed}
          trigger={null}
          style={{
            ...siderStyle,
            borderRight: `1px solid ${COLORS.border}`,
          }}
        >
          <SiderHeader
            title={leftSiderTitle}
            collapsed={leftCollapsed}
            position="left"
            onCollapse={handleLeftCollapse}
          />
          <div style={siderContentStyle}>
            {!leftCollapsed && leftSidebar}
          </div>
        </Sider>
      )}

      {/* 中间主区域 */}
      <Layout style={{ background: COLORS.bg }}>
        <Content style={mainContentStyle}>
          {mainContent}
        </Content>
      </Layout>

      {/* 右侧边栏 */}
      {showRightSider && (
        <Sider
          width={rightSiderWidth}
          collapsedWidth={collapsedWidth}
          collapsed={rightCollapsed}
          trigger={null}
          style={{
            ...siderStyle,
            borderLeft: `1px solid ${COLORS.border}`,
          }}
        >
          <SiderHeader
            title={rightSiderTitle}
            collapsed={rightCollapsed}
            position="right"
            onCollapse={handleRightCollapse}
          />
          <div style={siderContentStyle}>
            {!rightCollapsed && rightSidebar}
          </div>
        </Sider>
      )}
    </Layout>
  )
}

export default MainLayout