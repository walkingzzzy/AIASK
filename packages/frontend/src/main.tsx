import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import './index.css'

// 深色主题配置
const darkTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#58a6ff',
    colorBgContainer: '#1c2128',
    colorBgElevated: '#161b22',
    colorBgLayout: '#0d1117',
    colorBorder: '#30363d',
    colorBorderSecondary: '#21262d',
    colorText: '#e6edf3',
    colorTextSecondary: '#8b949e',
    colorTextTertiary: '#6e7681',
    borderRadius: 8,
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans SC', sans-serif",
  },
  components: {
    Layout: {
      siderBg: '#161b22',
      headerBg: '#161b22',
      bodyBg: '#0d1117',
    },
    Menu: {
      darkItemBg: 'transparent',
      darkItemSelectedBg: '#58a6ff',
      darkItemHoverBg: '#262c36',
      darkItemColor: '#8b949e',
      darkItemSelectedColor: '#ffffff',
      itemMarginInline: 8,
      itemBorderRadius: 8,
      groupTitleColor: '#6e7681',
      groupTitleFontSize: 11,
    },
    Card: {
      colorBgContainer: '#1c2128',
      colorBorderSecondary: '#21262d',
    },
    Table: {
      colorBgContainer: 'transparent',
      headerBg: '#161b22',
      rowHoverBg: '#262c36',
    },
    Input: {
      colorBgContainer: '#161b22',
      colorBorder: '#30363d',
    },
    Button: {
      borderRadius: 8,
    },
  },
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ConfigProvider locale={zhCN} theme={darkTheme}>
        <App />
      </ConfigProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
