/**
 * 应用状态栏组件
 * 显示连接状态、同步状态等
 */
import React from 'react'
import { Badge, Tooltip, Space } from 'antd'
import { 
  WifiOutlined, 
  CloudSyncOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons'
import { useRealtimeDataStore } from '@/services/realtimeService'

interface AppStatusBarProps {
  healthCheck?: boolean
  compact?: boolean
}

const AppStatusBar: React.FC<AppStatusBarProps> = ({ 
  healthCheck = true,
  compact = false 
}) => {
  const isConnected = useRealtimeDataStore(state => state.isConnected)
  const subscriptions = useRealtimeDataStore(state => state.subscriptions)
  
  if (compact) {
    return (
      <Space size={8}>
        <Tooltip title={isConnected ? '实时连接正常' : '实时连接断开'}>
          <Badge status={isConnected ? 'success' : 'error'} />
        </Tooltip>
        <Tooltip title={healthCheck ? 'API服务正常' : 'API服务异常'}>
          <Badge status={healthCheck ? 'success' : 'error'} />
        </Tooltip>
      </Space>
    )
  }
  
  return (
    <div style={containerStyle}>
      {/* WebSocket状态 */}
      <Tooltip title={isConnected ? '实时数据连接正常' : '实时数据连接断开'}>
        <div style={itemStyle}>
          <WifiOutlined style={{ color: isConnected ? '#3fb950' : '#f85149' }} />
          <span style={{ color: isConnected ? '#3fb950' : '#f85149' }}>
            {isConnected ? '已连接' : '未连接'}
          </span>
        </div>
      </Tooltip>
      
      {/* API状态 */}
      <Tooltip title={healthCheck ? 'API服务正常' : 'API服务异常'}>
        <div style={itemStyle}>
          <ApiOutlined style={{ color: healthCheck ? '#3fb950' : '#f85149' }} />
          <span style={{ color: healthCheck ? '#3fb950' : '#f85149' }}>
            {healthCheck ? 'API正常' : 'API异常'}
          </span>
        </div>
      </Tooltip>
      
      {/* 订阅数量 */}
      <Tooltip title={`已订阅 ${subscriptions.size} 只股票的实时数据`}>
        <div style={itemStyle}>
          <CloudSyncOutlined style={{ color: '#58a6ff' }} />
          <span style={{ color: '#8b949e' }}>
            订阅: {subscriptions.size}
          </span>
        </div>
      </Tooltip>
    </div>
  )
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 16,
  padding: '4px 12px',
  background: '#0d1117',
  borderRadius: 4,
  fontSize: 12,
}

const itemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 4,
}

export default AppStatusBar
