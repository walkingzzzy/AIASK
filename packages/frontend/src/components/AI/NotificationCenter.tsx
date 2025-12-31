/**
 * 通知中心组件
 * 展示AI推送的所有通知
 */
import { useState } from 'react'
import { 
  Drawer, 
  List, 
  Typography, 
  Badge, 
  Button, 
  Empty, 
  Tag,
  Space,
  Tooltip
} from 'antd'
import { 
  BellOutlined, 
  CheckOutlined,
  DeleteOutlined,
  SunOutlined,
  RiseOutlined,
  WarningOutlined,
  BulbOutlined
} from '@ant-design/icons'
import { useAINotification, AINotification, NotificationType } from '@/hooks/useAINotification'
import styles from './NotificationCenter.module.css'

const { Text, Paragraph } = Typography

// 图标映射
const iconMap: Record<NotificationType, React.ReactNode> = {
  morning_brief: <SunOutlined style={{ color: '#ffd700' }} />,
  opportunity: <RiseOutlined style={{ color: '#52c41a' }} />,
  risk_alert: <WarningOutlined style={{ color: '#ff4d4f' }} />,
  market_event: <BellOutlined style={{ color: '#1890ff' }} />,
  stock_alert: <BulbOutlined style={{ color: '#fa8c16' }} />,
  daily_review: <BulbOutlined style={{ color: '#722ed1' }} />
}

// 类型标签
const typeLabels: Record<NotificationType, { text: string; color: string }> = {
  morning_brief: { text: '早报', color: 'gold' },
  opportunity: { text: '机会', color: 'green' },
  risk_alert: { text: '风险', color: 'red' },
  market_event: { text: '市场', color: 'blue' },
  stock_alert: { text: '异动', color: 'orange' },
  daily_review: { text: '复盘', color: 'purple' }
}

interface NotificationCenterProps {
  trigger?: React.ReactNode
}

export default function NotificationCenter({ trigger }: NotificationCenterProps) {
  const [open, setOpen] = useState(false)
  const { 
    notifications, 
    unreadCount, 
    markAsRead, 
    markAllAsRead, 
    clearNotifications 
  } = useAINotification()

  const handleOpen = () => setOpen(true)
  const handleClose = () => setOpen(false)

  const handleItemClick = (notif: AINotification) => {
    if (!notif.read) {
      markAsRead(notif.id)
    }
    // 可以添加跳转逻辑
  }

  const formatTime = (date: Date) => {
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)

    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString()
  }

  const defaultTrigger = (
    <Badge count={unreadCount} size="small" offset={[-2, 2]}>
      <Button 
        type="text" 
        icon={<BellOutlined />} 
        onClick={handleOpen}
        className={styles.triggerBtn}
      />
    </Badge>
  )

  return (
    <>
      {trigger ? (
        <div onClick={handleOpen}>{trigger}</div>
      ) : (
        defaultTrigger
      )}

      <Drawer
        title={
          <div className={styles.drawerHeader}>
            <span>
              <BellOutlined /> 通知中心
              {unreadCount > 0 && (
                <Badge count={unreadCount} style={{ marginLeft: 8 }} />
              )}
            </span>
            <Space>
              {unreadCount > 0 && (
                <Tooltip title="全部已读">
                  <Button 
                    type="text" 
                    size="small" 
                    icon={<CheckOutlined />}
                    onClick={markAllAsRead}
                  />
                </Tooltip>
              )}
              {notifications.length > 0 && (
                <Tooltip title="清空">
                  <Button 
                    type="text" 
                    size="small" 
                    icon={<DeleteOutlined />}
                    onClick={clearNotifications}
                  />
                </Tooltip>
              )}
            </Space>
          </div>
        }
        placement="right"
        onClose={handleClose}
        open={open}
        width={380}
        styles={{
          body: { padding: 0 },
          header: { 
            background: '#0d1117',
            borderBottom: '1px solid #30363d'
          }
        }}
      >
        {notifications.length === 0 ? (
          <Empty 
            description="暂无通知" 
            className={styles.empty}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <List
            dataSource={notifications}
            renderItem={(item) => (
              <List.Item 
                className={`${styles.listItem} ${!item.read ? styles.unread : ''}`}
                onClick={() => handleItemClick(item)}
              >
                <div className={styles.itemContent}>
                  <div className={styles.itemIcon}>
                    {iconMap[item.type]}
                  </div>
                  <div className={styles.itemMain}>
                    <div className={styles.itemHeader}>
                      <Text strong className={styles.itemTitle}>
                        {item.title}
                      </Text>
                      <Tag 
                        color={typeLabels[item.type].color}
                        className={styles.itemTag}
                      >
                        {typeLabels[item.type].text}
                      </Tag>
                    </div>
                    <Paragraph 
                      ellipsis={{ rows: 2 }}
                      className={styles.itemDesc}
                    >
                      {item.content}
                    </Paragraph>
                    <div className={styles.itemFooter}>
                      {item.stockName && (
                        <Tag>{item.stockName}</Tag>
                      )}
                      <Text type="secondary" className={styles.itemTime}>
                        {formatTime(item.timestamp)}
                      </Text>
                    </div>
                  </div>
                  {!item.read && <div className={styles.unreadDot} />}
                </div>
              </List.Item>
            )}
          />
        )}
      </Drawer>
    </>
  )
}
