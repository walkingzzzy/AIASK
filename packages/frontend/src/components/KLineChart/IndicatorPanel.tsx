/**
 * 指标面板组件
 * 用于选择和配置K线图的主图和副图技术指标
 */
import React, { useState } from 'react'
import { Modal, Radio, Space, Divider, Typography, Card, Row, Col } from 'antd'
import type { IndicatorPanelProps, MainIndicatorType, SubIndicatorType } from './types'

const { Title, Text } = Typography

const mainIndicators = [
  { value: 'MA' as MainIndicatorType, label: '移动平均线', desc: '显示价格趋势的平滑曲线' },
  { value: 'BOLL' as MainIndicatorType, label: '布林带', desc: '显示价格波动区间' },
  { value: 'SAR' as MainIndicatorType, label: '抛物线转向', desc: '显示趋势反转点' },
  { value: 'NONE' as MainIndicatorType, label: '无指标', desc: '仅显示K线' }
]

const subIndicators = [
  { value: 'VOL' as SubIndicatorType, label: '成交量', desc: '显示成交量柱状图' },
  { value: 'MACD' as SubIndicatorType, label: 'MACD', desc: '趋势和动量指标' },
  { value: 'RSI' as SubIndicatorType, label: 'RSI', desc: '相对强弱指标' },
  { value: 'KDJ' as SubIndicatorType, label: 'KDJ', desc: '随机指标' },
  { value: 'NONE' as SubIndicatorType, label: '无指标', desc: '不显示副图' }
]

export const IndicatorPanel: React.FC<IndicatorPanelProps> = ({
  visible,
  onClose,
  onApply
}) => {
  const [selectedMain, setSelectedMain] = useState<MainIndicatorType>('MA')
  const [selectedSub, setSelectedSub] = useState<SubIndicatorType>('VOL')

  const handleOk = () => {
    onApply(selectedMain, selectedSub)
    onClose()
  }

  return (
    <Modal
      title="技术指标设置"
      open={visible}
      onOk={handleOk}
      onCancel={onClose}
      width={700}
      okText="应用"
      cancelText="取消"
    >
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div>
          <Title level={5}>主图指标</Title>
          <Text type="secondary">选择在K线图上叠加显示的技术指标</Text>
          <Divider style={{ margin: '12px 0' }} />
          <Radio.Group
            value={selectedMain}
            onChange={(e) => setSelectedMain(e.target.value)}
            style={{ width: '100%' }}
          >
            <Row gutter={[16, 16]}>
              {mainIndicators.map(indicator => (
                <Col span={12} key={indicator.value}>
                  <Card
                    hoverable
                    size="small"
                    className={selectedMain === indicator.value ? 'border-blue-500' : ''}
                    onClick={() => setSelectedMain(indicator.value)}
                  >
                    <Radio value={indicator.value}>
                      <div>
                        <div className="font-medium">{indicator.label}</div>
                        <div className="text-xs text-gray-500">{indicator.desc}</div>
                      </div>
                    </Radio>
                  </Card>
                </Col>
              ))}
            </Row>
          </Radio.Group>
        </div>

        <div>
          <Title level={5}>副图指标</Title>
          <Text type="secondary">选择在副图区域显示的技术指标</Text>
          <Divider style={{ margin: '12px 0' }} />
          <Radio.Group
            value={selectedSub}
            onChange={(e) => setSelectedSub(e.target.value)}
            style={{ width: '100%' }}
          >
            <Row gutter={[16, 16]}>
              {subIndicators.map(indicator => (
                <Col span={12} key={indicator.value}>
                  <Card
                    hoverable
                    size="small"
                    className={selectedSub === indicator.value ? 'border-blue-500' : ''}
                    onClick={() => setSelectedSub(indicator.value)}
                  >
                    <Radio value={indicator.value}>
                      <div>
                        <div className="font-medium">{indicator.label}</div>
                        <div className="text-xs text-gray-500">{indicator.desc}</div>
                      </div>
                    </Radio>
                  </Card>
                </Col>
              ))}
            </Row>
          </Radio.Group>
        </div>
      </Space>
    </Modal>
  )
}

export default IndicatorPanel
