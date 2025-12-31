/**
 * 智能后续建议组件
 * 根据上下文和对话历史生成智能建议
 */
import { useMemo } from 'react'
import { Button, Space } from 'antd'
import { 
  LineChartOutlined, 
  FundOutlined, 
  FileSearchOutlined,
  PlusOutlined,
  BellOutlined,
  HistoryOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons'
import { useAIContextStore, CurrentStock } from '@/hooks/useAIContext'
import styles from './SmartSuggestions.module.css'

interface SmartSuggestionsProps {
  lastIntent?: string
  lastResponse?: string
  onSelect: (suggestion: string) => void
  maxSuggestions?: number
}

// 建议配置
interface SuggestionConfig {
  text: string
  icon?: React.ReactNode
  priority: number
  conditions?: {
    hasStock?: boolean
    intent?: string[]
    marketStatus?: string[]
    timeOfDay?: string[]
  }
}

// 预定义建议库
const suggestionLibrary: SuggestionConfig[] = [
  // 股票相关
  {
    text: '查看{stockName}的技术分析',
    icon: <LineChartOutlined />,
    priority: 10,
    conditions: { hasStock: true }
  },
  {
    text: '分析{stockName}的资金流向',
    icon: <FundOutlined />,
    priority: 9,
    conditions: { hasStock: true }
  },
  {
    text: '查看{stockName}的相关研报',
    icon: <FileSearchOutlined />,
    priority: 8,
    conditions: { hasStock: true }
  },
  {
    text: '把{stockName}加入自选',
    icon: <PlusOutlined />,
    priority: 7,
    conditions: { hasStock: true }
  },
  {
    text: '设置{stockName}的价格提醒',
    icon: <BellOutlined />,
    priority: 6,
    conditions: { hasStock: true }
  },
  {
    text: '对比{stockName}和同行业股票',
    icon: <HistoryOutlined />,
    priority: 5,
    conditions: { hasStock: true }
  },
  
  // 分析后续
  {
    text: '继续深入分析基本面',
    priority: 8,
    conditions: { intent: ['stock_analysis', 'technical_analysis'] }
  },
  {
    text: '看看有什么风险点',
    priority: 7,
    conditions: { intent: ['stock_analysis', 'buy_signal'] }
  },
  {
    text: '回测这个策略',
    priority: 6,
    conditions: { intent: ['stock_screening', 'strategy'] }
  },
  
  // 时间相关
  {
    text: '看看今日早报',
    icon: <QuestionCircleOutlined />,
    priority: 9,
    conditions: { timeOfDay: ['morning'], marketStatus: ['pre_open'] }
  },
  {
    text: '今日大盘怎么样',
    priority: 8,
    conditions: { marketStatus: ['trading'] }
  },
  {
    text: '帮我复盘今天的操作',
    priority: 9,
    conditions: { timeOfDay: ['evening'], marketStatus: ['closed'] }
  },
  {
    text: '明天有什么值得关注的',
    priority: 7,
    conditions: { timeOfDay: ['evening', 'night'], marketStatus: ['closed'] }
  },
  
  // 通用建议
  {
    text: '有什么投资机会',
    priority: 5
  },
  {
    text: '帮我选几只股票',
    priority: 4
  },
  {
    text: '最近有什么热点板块',
    priority: 4
  },
  {
    text: '解释一下什么是PE',
    priority: 3
  }
]

export default function SmartSuggestions({
  lastIntent,
  lastResponse,
  onSelect,
  maxSuggestions = 4
}: SmartSuggestionsProps) {
  const { context } = useAIContextStore()
  
  // 根据上下文筛选和排序建议
  const suggestions = useMemo(() => {
    const currentStock = context.currentStock
    const marketStatus = context.marketStatus
    const timeOfDay = context.timeOfDay
    
    // 筛选符合条件的建议
    const filtered = suggestionLibrary.filter(s => {
      const cond = s.conditions
      if (!cond) return true
      
      // 检查股票条件
      if (cond.hasStock && !currentStock) return false
      if (cond.hasStock === false && currentStock) return false
      
      // 检查意图条件
      if (cond.intent && lastIntent && !cond.intent.includes(lastIntent)) return false
      
      // 检查市场状态
      if (cond.marketStatus && !cond.marketStatus.includes(marketStatus)) return false
      
      // 检查时间段
      if (cond.timeOfDay && !cond.timeOfDay.includes(timeOfDay)) return false
      
      return true
    })
    
    // 排序
    const sorted = filtered.sort((a, b) => {
      // 有股票上下文的建议优先
      if (currentStock) {
        const aHasStock = a.conditions?.hasStock
        const bHasStock = b.conditions?.hasStock
        if (aHasStock && !bHasStock) return -1
        if (!aHasStock && bHasStock) return 1
      }
      
      // 按优先级排序
      return b.priority - a.priority
    })
    
    // 替换占位符
    return sorted.slice(0, maxSuggestions).map(s => {
      let text = s.text
      if (currentStock) {
        text = text.replace('{stockName}', currentStock.name)
        text = text.replace('{stockCode}', currentStock.code)
      }
      return {
        ...s,
        text
      }
    })
  }, [context, lastIntent, maxSuggestions])
  
  if (suggestions.length === 0) {
    return null
  }
  
  return (
    <div className={styles.container}>
      <Space wrap size={[8, 8]}>
        {suggestions.map((s, index) => (
          <Button
            key={index}
            type="dashed"
            size="small"
            icon={s.icon}
            onClick={() => onSelect(s.text)}
            className={styles.suggestionBtn}
          >
            {s.text}
          </Button>
        ))}
      </Space>
    </div>
  )
}
