import { useState, useEffect, useMemo } from 'react'
import { Layout, Menu } from 'antd'
import type { MenuProps } from 'antd'
import {
  DashboardOutlined,
  StockOutlined,
  FundOutlined,
  MessageOutlined,
  SettingOutlined,
  FireOutlined,
  LineChartOutlined,
  ThunderboltOutlined,
  StarOutlined,
  BarChartOutlined,
  SafetyOutlined,
  FolderOutlined,
  FileTextOutlined,
  DatabaseOutlined,
  RadarChartOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import Dashboard from './pages/Dashboard'
import AIScore from './pages/AIScore'
import StockAnalysis from './pages/StockAnalysis'
import LimitUp from './pages/LimitUp'
import FundFlow from './pages/FundFlow'
import Chat from './pages/Chat'
import Settings from './pages/Settings'
import CallAuction from './pages/CallAuction'
import Watchlist from './pages/Watchlist'
import BacktestResult from './pages/BacktestResult'
import Portfolio from './pages/Portfolio'
import RiskMonitor from './pages/RiskMonitor'
import ResearchCenter from './pages/ResearchCenter'
import DataCenter from './pages/DataCenter'
import StockScreener from './pages/StockScreener'
import Trading from './pages/Trading'
import BottomBar from './components/Layout/BottomBar'
import AISidebar from './components/Layout/AISidebar/AISidebar'
import useKeyboardShortcuts, { createAIShortcuts } from './hooks/useKeyboardShortcuts'
import { useWatchlistStore } from './stores/useWatchlistStore'

const { Header, Sider, Content } = Layout

type PageKey = 'trading' | 'dashboard' | 'ai-score' | 'stock-analysis' | 'watchlist' | 'call-auction' | 'limit-up' | 'fund-flow' | 'backtest' | 'portfolio' | 'risk-monitor' | 'research' | 'data-center' | 'screener' | 'chat' | 'settings'

// 菜单分组配置
const menuItems: MenuProps['items'] = [
  {
    key: 'main',
    type: 'group',
    label: '主界面',
    children: [
      { key: 'trading', icon: <LineChartOutlined />, label: '交易主页' },
    ]
  },
  {
    key: 'overview',
    type: 'group',
    label: '概览',
    children: [
      { key: 'dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
      { key: 'ai-score', icon: <StockOutlined />, label: 'AI评分' },
    ]
  },
  {
    key: 'analysis',
    type: 'group',
    label: '分析工具',
    children: [
      { key: 'stock-analysis', icon: <LineChartOutlined />, label: '个股分析' },
      { key: 'screener', icon: <RadarChartOutlined />, label: '选股雷达' },
      { key: 'call-auction', icon: <ThunderboltOutlined />, label: '竞价分析' },
    ]
  },
  {
    key: 'market',
    type: 'group',
    label: '市场监控',
    children: [
      { key: 'limit-up', icon: <FireOutlined />, label: '涨停追踪' },
      { key: 'fund-flow', icon: <FundOutlined />, label: '资金监控' },
      { key: 'risk-monitor', icon: <SafetyOutlined />, label: '风险监控' },
    ]
  },
  {
    key: 'portfolio-group',
    type: 'group',
    label: '投资组合',
    children: [
      { key: 'watchlist', icon: <StarOutlined />, label: '自选股' },
      { key: 'portfolio', icon: <FolderOutlined />, label: '组合管理' },
      { key: 'backtest', icon: <BarChartOutlined />, label: '回测结果' },
    ]
  },
  {
    key: 'resources',
    type: 'group',
    label: '资源中心',
    children: [
      { key: 'research', icon: <FileTextOutlined />, label: '研报中心' },
      { key: 'data-center', icon: <DatabaseOutlined />, label: '数据中心' },
      { key: 'chat', icon: <MessageOutlined />, label: '智能问答' },
    ]
  },
  { type: 'divider' },
  { key: 'settings', icon: <SettingOutlined />, label: '设置' },
]

// 页面标题映射
const pageTitles: Record<PageKey, string> = {
  'trading': '交易主页',
  'dashboard': '仪表盘',
  'ai-score': 'AI评分',
  'stock-analysis': '个股分析',
  'watchlist': '自选股',
  'call-auction': '竞价分析',
  'limit-up': '涨停追踪',
  'fund-flow': '资金监控',
  'backtest': '回测结果',
  'portfolio': '组合管理',
  'risk-monitor': '风险监控',
  'screener': '选股雷达',
  'research': '研报中心',
  'data-center': '数据中心',
  'chat': '智能问答',
  'settings': '设置',
}

function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [currentPage, setCurrentPage] = useState<PageKey>('trading')
  const [currentTime, setCurrentTime] = useState(new Date())
  const [aiSidebarOpen, setAiSidebarOpen] = useState(false)
  
  // 获取自选股列表 - 使用 useMemo 缓存
  const getAllStocks = useWatchlistStore(state => state.getAllStocks)
  const watchlistCodes = useMemo(() => getAllStocks().map(s => s.code), [getAllStocks])

  // 快捷键配置
  const shortcuts = createAIShortcuts({
    onToggleAI: () => setAiSidebarOpen(prev => !prev),
    onSearch: () => console.log('Search triggered'),
    onNavigate: (key) => {
      const pageMap: Record<string, PageKey> = {
        'ai-score': 'ai-score',
        'fund-flow': 'fund-flow',
        'limit-up': 'limit-up',
        'analysis': 'stock-analysis',
        'research': 'research',
        'screener': 'screener',
      }
      if (pageMap[key]) setCurrentPage(pageMap[key])
    },
  })
  useKeyboardShortcuts({ shortcuts })

  // 更新时间
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date())
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  const renderPage = () => {
    switch (currentPage) {
      case 'trading':
        return <Trading />
      case 'dashboard':
        return <Dashboard />
      case 'ai-score':
        return <AIScore />
      case 'stock-analysis':
        return <StockAnalysis />
      case 'watchlist':
        return <Watchlist />
      case 'call-auction':
        return <CallAuction />
      case 'limit-up':
        return <LimitUp />
      case 'fund-flow':
        return <FundFlow />
      case 'backtest':
        return <BacktestResult />
      case 'portfolio':
        return <Portfolio />
      case 'risk-monitor':
        return <RiskMonitor />
      case 'screener':
        return <StockScreener />
      case 'research':
        return <ResearchCenter />
      case 'data-center':
        return <DataCenter />
      case 'chat':
        return <Chat />
      case 'settings':
        return <Settings />
      default:
        return <Dashboard />
    }
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
        <Sider 
          collapsible 
          collapsed={collapsed} 
          onCollapse={setCollapsed}
          trigger={null}
          width={220}
          collapsedWidth={64}
          style={{
            overflow: 'auto',
            height: '100vh',
            position: 'fixed',
            left: 0,
            top: 0,
            bottom: 0,
            borderRight: '1px solid #21262d',
          }}
        >
          {/* Logo区域 */}
          <div 
            style={{
              height: 64,
              display: 'flex',
              alignItems: 'center',
              justifyContent: collapsed ? 'center' : 'flex-start',
              padding: collapsed ? 0 : '0 20px',
              borderBottom: '1px solid #21262d',
            }}
          >
            <div style={{ 
              fontSize: collapsed ? 24 : 18, 
              fontWeight: 700,
              color: '#e6edf3',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              whiteSpace: 'nowrap',
            }}>
              <span style={{ fontSize: 24 }}>📈</span>
              {!collapsed && <span>A股智能分析</span>}
            </div>
          </div>

          {/* 菜单 */}
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[currentPage]}
            items={collapsed ? (menuItems || []).filter(item => item && item.type !== 'group').flatMap(item => 
              item && 'children' in item ? (item.children || []) : [item]
            ).filter((item): item is NonNullable<typeof item> => Boolean(item)) : menuItems}
            onClick={({ key }) => setCurrentPage(key as PageKey)}
            style={{ 
              borderRight: 0,
              padding: '8px 0',
            }}
          />

          {/* 折叠按钮 */}
          <div
            onClick={() => setCollapsed(!collapsed)}
            style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0,
              height: 48,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              borderTop: '1px solid #21262d',
              color: '#8b949e',
              transition: 'color 0.2s',
            }}
            onMouseEnter={(e) => e.currentTarget.style.color = '#e6edf3'}
            onMouseLeave={(e) => e.currentTarget.style.color = '#8b949e'}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </div>
        </Sider>

        <Layout style={{ marginLeft: collapsed ? 64 : 220, transition: 'margin-left 0.2s' }}>
          {/* 顶部导航栏 */}
          <Header 
            style={{ 
              padding: '0 24px', 
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid #21262d',
              position: 'sticky',
              top: 0,
              zIndex: 100,
            }}
          >
            <h1 style={{ 
              margin: 0, 
              fontSize: 18, 
              fontWeight: 600,
              color: '#e6edf3',
            }}>
              {pageTitles[currentPage]}
            </h1>
            <span style={{ 
              fontSize: 13, 
              color: '#6e7681',
              fontFamily: "'SF Mono', Monaco, monospace",
            }}>
              {currentTime.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })}
            </span>
          </Header>

          {/* 内容区域 */}
          <Content
            style={{
              margin: 16,
              marginBottom: 0,
              padding: 24,
              minHeight: 'calc(100vh - 64px - 42px - 16px)',
              background: '#1c2128',
              borderRadius: 12,
              overflow: 'auto',
            }}
          >
            {renderPage()}
          </Content>

          {/* 底部功能栏 */}
          <BottomBar
            activeKey={currentPage}
            onItemClick={(key) => setCurrentPage(key as PageKey)}
            onAIClick={() => setAiSidebarOpen(true)}
          />
        </Layout>

        {/* AI侧边栏 */}
        <AISidebar
          open={aiSidebarOpen}
          onClose={() => setAiSidebarOpen(false)}
          watchlist={watchlistCodes}
          holdings={[]}
          onStockClick={(code) => {
            setCurrentPage('stock-analysis')
            // 可以通过其他方式传递选中的股票代码
            console.log('Navigate to stock:', code)
          }}
        />
    </Layout>
  )
}

export default App
