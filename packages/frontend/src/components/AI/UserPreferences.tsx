import { useState, useEffect } from 'react'
import { 
  Card, Form, Select, Slider, Switch, Input, 
  Button, message
} from 'antd'
import { 
  UserOutlined, 
  SettingOutlined,
  RobotOutlined,
  BellOutlined,
  SaveOutlined
} from '@ant-design/icons'
import { useUserProfileStore } from '@/stores/useUserProfileStore'

const { Option } = Select

const investmentStyleOptions = [
  { value: 'value', label: '价值投资', desc: '关注低估值、高股息' },
  { value: 'growth', label: '成长投资', desc: '关注高增长企业' },
  { value: 'momentum', label: '动量投资', desc: '跟随市场趋势' },
  { value: 'swing', label: '波段交易', desc: '短线高抛低吸' },
  { value: 'quant', label: '量化投资', desc: '基于数据模型' },
]

const knowledgeLevelOptions = [
  { value: 'beginner', label: '入门级', desc: '刚开始学习投资' },
  { value: 'intermediate', label: '进阶级', desc: '有一定投资经验' },
  { value: 'advanced', label: '专业级', desc: '深入理解市场' },
]

const aiPersonalityOptions = [
  { value: 'professional', label: '专业严谨', desc: '数据驱动，客观分析' },
  { value: 'friendly', label: '亲切友好', desc: '通俗易懂，耐心解释' },
  { value: 'concise', label: '简洁高效', desc: '直奔主题，节省时间' },
]

const sectorOptions = [
  '科技', '消费', '医药', '金融', '新能源', '制造', '地产', '军工', '传媒', '农业'
]

export default function UserPreferences() {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  
  const {
    investmentStyle,
    riskTolerance,
    focusSectors,
    avoidedSectors,
    knowledgeLevel,
    nickname,
    aiPersonality,
    notificationEnabled,
    morningBriefEnabled,
    updatePreferences,
    updateProfile
  } = useUserProfileStore()

  useEffect(() => {
    form.setFieldsValue({
      investmentStyle,
      riskTolerance,
      focusSectors,
      avoidedSectors,
      knowledgeLevel,
      nickname,
      aiPersonality,
      notificationEnabled,
      morningBriefEnabled
    })
  }, [investmentStyle, riskTolerance, focusSectors, knowledgeLevel, nickname, aiPersonality])

  const handleSave = async () => {
    setSaving(true)
    try {
      const values = form.getFieldsValue()
      await updatePreferences({
        investmentStyle: values.investmentStyle,
        riskTolerance: values.riskTolerance,
        focusSectors: values.focusSectors,
        avoidedSectors: values.avoidedSectors,
        knowledgeLevel: values.knowledgeLevel,
        aiPersonality: values.aiPersonality,
        notificationEnabled: values.notificationEnabled,
        morningBriefEnabled: values.morningBriefEnabled
      })
      
      if (values.nickname !== nickname) {
        await updateProfile({ nickname: values.nickname })
      }
      
      message.success('偏好设置已保存')
    } catch (error) {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <Form form={form} layout="vertical">
        {/* 个人信息 */}
        <Card 
          size="small" 
          title={<span><UserOutlined /> 个人信息</span>}
          style={{ marginBottom: 16 }}
        >
          <Form.Item name="nickname" label="昵称">
            <Input placeholder="设置您的昵称，AI会用它称呼您" />
          </Form.Item>
        </Card>

        {/* 投资偏好 */}
        <Card 
          size="small" 
          title={<span><SettingOutlined /> 投资偏好</span>}
          style={{ marginBottom: 16 }}
        >
          <Form.Item name="investmentStyle" label="投资风格">
            <Select>
              {investmentStyleOptions.map(opt => (
                <Option key={opt.value} value={opt.value}>
                  <div>
                    <span>{opt.label}</span>
                    <span style={{ color: '#8b949e', marginLeft: 8, fontSize: 12 }}>
                      {opt.desc}
                    </span>
                  </div>
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="riskTolerance" label="风险偏好">
            <Slider
              min={1}
              max={5}
              marks={{
                1: '保守',
                2: '稳健',
                3: '平衡',
                4: '积极',
                5: '激进'
              }}
            />
          </Form.Item>

          <Form.Item name="focusSectors" label="关注板块">
            <Select mode="multiple" placeholder="选择您关注的板块">
              {sectorOptions.map(sector => (
                <Option key={sector} value={sector}>{sector}</Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="avoidedSectors" label="回避板块">
            <Select mode="multiple" placeholder="选择您想回避的板块">
              {sectorOptions.map(sector => (
                <Option key={sector} value={sector}>{sector}</Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="knowledgeLevel" label="投资经验">
            <Select>
              {knowledgeLevelOptions.map(opt => (
                <Option key={opt.value} value={opt.value}>
                  <div>
                    <span>{opt.label}</span>
                    <span style={{ color: '#8b949e', marginLeft: 8, fontSize: 12 }}>
                      {opt.desc}
                    </span>
                  </div>
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Card>

        {/* AI设置 */}
        <Card 
          size="small" 
          title={<span><RobotOutlined /> AI助手设置</span>}
          style={{ marginBottom: 16 }}
        >
          <Form.Item name="aiPersonality" label="AI风格">
            <Select>
              {aiPersonalityOptions.map(opt => (
                <Option key={opt.value} value={opt.value}>
                  <div>
                    <span>{opt.label}</span>
                    <span style={{ color: '#8b949e', marginLeft: 8, fontSize: 12 }}>
                      {opt.desc}
                    </span>
                  </div>
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Card>

        {/* 通知设置 */}
        <Card 
          size="small" 
          title={<span><BellOutlined /> 通知设置</span>}
          style={{ marginBottom: 16 }}
        >
          <Form.Item 
            name="notificationEnabled" 
            label="启用通知" 
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item 
            name="morningBriefEnabled" 
            label="每日早报" 
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Card>

        {/* 保存按钮 */}
        <Button 
          type="primary" 
          icon={<SaveOutlined />}
          onClick={handleSave}
          loading={saving}
          block
        >
          保存设置
        </Button>
      </Form>
    </div>
  )
}
