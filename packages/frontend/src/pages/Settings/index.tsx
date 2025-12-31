import { Card, Form, Input, Switch, Button, message, Space, Typography, Divider } from 'antd'
import { 
  ApiOutlined, 
  KeyOutlined, 
  BgColorsOutlined, 
  SyncOutlined,
  SaveOutlined,
  SettingOutlined,
} from '@ant-design/icons'

const { Text, Title } = Typography

export default function Settings() {
  const [form] = Form.useForm()

  const handleSave = () => {
    message.success('设置已保存')
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      {/* API设置 */}
      <Card 
        style={{ marginBottom: 16 }}
        styles={{ body: { padding: 24 } }}
      >
        <div style={{ marginBottom: 24 }}>
          <Space align="center" style={{ marginBottom: 8 }}>
            <ApiOutlined style={{ fontSize: 20, color: '#58a6ff' }} />
            <Title level={5} style={{ margin: 0 }}>API设置</Title>
          </Space>
          <Text type="secondary" style={{ display: 'block' }}>
            配置后端服务和第三方API连接
          </Text>
        </div>
        
        <Form form={form} layout="vertical">
          <Form.Item 
            label={
              <Space>
                <SettingOutlined />
                <span>API服务地址</span>
              </Space>
            }
            name="apiUrl" 
            initialValue="http://127.0.0.1:8000"
            extra="后端API服务的访问地址"
          >
            <Input 
              placeholder="http://127.0.0.1:8000" 
              size="large"
            />
          </Form.Item>
          
          <Form.Item 
            label={
              <Space>
                <KeyOutlined />
                <span>OpenAI API Key</span>
              </Space>
            }
            name="openaiKey"
            extra="用于智能问答功能，请妥善保管"
          >
            <Input.Password 
              placeholder="sk-..." 
              size="large"
            />
          </Form.Item>
        </Form>
      </Card>

      {/* 显示设置 */}
      <Card 
        style={{ marginBottom: 24 }}
        styles={{ body: { padding: 24 } }}
      >
        <div style={{ marginBottom: 24 }}>
          <Space align="center" style={{ marginBottom: 8 }}>
            <BgColorsOutlined style={{ fontSize: 20, color: '#8b5cf6' }} />
            <Title level={5} style={{ margin: 0 }}>显示设置</Title>
          </Space>
          <Text type="secondary" style={{ display: 'block' }}>
            自定义界面显示偏好
          </Text>
        </div>
        
        <Form layout="vertical">
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            padding: '12px 0',
            borderBottom: '1px solid #21262d',
          }}>
            <div>
              <Text strong>深色模式</Text>
              <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
                使用深色主题减少眼睛疲劳
              </Text>
            </div>
            <Switch defaultChecked />
          </div>
          
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            padding: '12px 0',
          }}>
            <div>
              <Text strong>自动刷新</Text>
              <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
                自动更新市场数据和行情信息
              </Text>
            </div>
            <Switch defaultChecked />
          </div>
        </Form>
      </Card>

      {/* 保存按钮 */}
      <Button 
        type="primary" 
        icon={<SaveOutlined />}
        onClick={handleSave}
        size="large"
        style={{ width: '100%' }}
      >
        保存设置
      </Button>
    </div>
  )
}
