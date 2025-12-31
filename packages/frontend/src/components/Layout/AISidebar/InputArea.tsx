import { Input, Button, Switch, Space, Typography } from 'antd'
import { SendOutlined, RobotOutlined, InfoCircleOutlined } from '@ant-design/icons'
import type { InputAreaProps } from './types'

const { Text } = Typography

interface InputAreaWithRAGProps extends InputAreaProps {
  useRAG: boolean
  onRAGChange: (checked: boolean) => void
}

/**
 * 输入区域组件
 * 包含RAG开关、输入框和发送按钮
 */
export default function InputArea({ 
  input, 
  loading, 
  onInputChange, 
  onSend,
  useRAG,
  onRAGChange,
}: InputAreaWithRAGProps) {
  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column',
      gap: 12,
      padding: '16px 20px',
      borderTop: '1px solid #30363d',
      background: '#0d1117',
    }}>
      {/* RAG控制栏 */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 8,
      }}>
        <Space size="small">
          <div style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            background: 'linear-gradient(135deg, #58a6ff 0%, #8b5cf6 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',}}>
            <RobotOutlined style={{ fontSize: 14, color: 'white' }} />
          </div>
          <Text strong style={{ fontSize: 13}}>RAG增强</Text>
          <Switch
            checked={useRAG}
            onChange={onRAGChange}
            size="small"
          />
        </Space>
        <Text type="secondary" style={{ fontSize: 11 }}>
          <InfoCircleOutlined style={{ marginRight: 4 }} />
          {useRAG ? '向量增强' : '基础查询'}
        </Text>
      </div>

      {/* 输入框和发送按钮 */}
      <div style={{ 
        display: 'flex', 
        gap: 8,
      }}>
        <Input
          placeholder="输入您的问题..."
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onPressEnter={onSend}
          disabled={loading}
          autoComplete="off"
          allowClear
          style={{ flex: 1 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={onSend}
          loading={loading}
          style={{ minWidth: 80 }}
        >
          发送
        </Button>
      </div>
    </div>
  )
}

export type { InputAreaWithRAGProps }