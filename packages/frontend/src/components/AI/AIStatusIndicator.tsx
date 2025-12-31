import React, { useEffect, useState } from 'react'
import { useAppStore } from '../../stores/useAppStore'
import styles from './AIStatusIndicator.module.css'

interface AIStatusIndicatorProps {
  showDetails?: boolean
  compact?: boolean
}

/**
 * AI服务状态指示器
 * 显示LLM和向量模型的配置状态
 */
export const AIStatusIndicator: React.FC<AIStatusIndicatorProps> = ({ 
  showDetails = false,
  compact = false 
}) => {
  const { aiStatus, fetchAIStatus } = useAppStore()
  const [isExpanded, setIsExpanded] = useState(false)

  useEffect(() => {
    // 组件挂载时获取AI状态
    fetchAIStatus()
    
    // 每5分钟刷新一次状态
    const interval = setInterval(fetchAIStatus, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [fetchAIStatus])

  const getStatusColor = () => {
    if (aiStatus.isLoading) return 'loading'
    if (aiStatus.error) return 'error'
    if (aiStatus.isConfigured) return 'success'
    return 'warning'
  }

  const getStatusText = () => {
    if (aiStatus.isLoading) return '检测中...'
    if (aiStatus.error) return '检测失败'
    if (aiStatus.isConfigured) return 'AI就绪'
    return '部分降级'
  }

  const getStatusIcon = () => {
    if (aiStatus.isLoading) return '⏳'
    if (aiStatus.error) return '❌'
    if (aiStatus.isConfigured) return '✅'
    return '⚠️'
  }

  if (compact) {
    return (
      <div 
        className={`${styles.compactIndicator} ${styles[getStatusColor()]}`}
        title={getStatusText()}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className={styles.icon}>{getStatusIcon()}</span>
        {isExpanded && (
          <div className={styles.tooltip}>
            <div className={styles.tooltipContent}>
              <strong>{aiStatus.overallStatus}</strong>
              {aiStatus.llm && (
                <div className={styles.serviceStatus}>
                  <span>LLM: </span>
                  <span className={aiStatus.llm.is_configured ? styles.ok : styles.notOk}>
                    {aiStatus.llm.status}
                  </span>
                </div>
              )}
              {aiStatus.embedding && (
                <div className={styles.serviceStatus}>
                  <span>向量: </span>
                  <span className={aiStatus.embedding.is_configured ? styles.ok : styles.notOk}>
                    {aiStatus.embedding.status}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className={`${styles.statusCard} ${styles[getStatusColor()]}`}>
      <div className={styles.header} onClick={() => setIsExpanded(!isExpanded)}>
        <span className={styles.icon}>{getStatusIcon()}</span>
        <span className={styles.title}>AI服务状态</span>
        <span className={styles.status}>{getStatusText()}</span>
        <span className={styles.expandIcon}>{isExpanded ? '▲' : '▼'}</span>
      </div>

      {(showDetails || isExpanded) && (
        <div className={styles.details}>
          {/* LLM状态 */}
          <div className={styles.serviceRow}>
            <div className={styles.serviceName}>
              <span className={styles.serviceIcon}>🤖</span>
              大语言模型 (LLM)
            </div>
            <div className={`${styles.serviceStatus} ${aiStatus.llm?.is_configured ? styles.ok : styles.notOk}`}>
              {aiStatus.llm?.status || '未知'}
            </div>
          </div>
          {aiStatus.llm?.message && (
            <div className={styles.serviceMessage}>
              {aiStatus.llm.message}
            </div>
          )}

          {/* 向量模型状态 */}
          <div className={styles.serviceRow}>
            <div className={styles.serviceName}>
              <span className={styles.serviceIcon}>🔍</span>
              向量模型 (Embedding)
            </div>
            <div className={`${styles.serviceStatus} ${aiStatus.embedding?.is_configured ? styles.ok : styles.notOk}`}>
              {aiStatus.embedding?.status || '未知'}
            </div>
          </div>
          {aiStatus.embedding?.message && (
            <div className={styles.serviceMessage}>
              {aiStatus.embedding.message}
            </div>
          )}

          {/* 配置建议 */}
          {aiStatus.recommendations && aiStatus.recommendations.length > 0 && (
            <div className={styles.recommendations}>
              <div className={styles.recommendationsTitle}>配置建议:</div>
              <ul>
                {aiStatus.recommendations.map((rec, index) => (
                  <li key={index}>{rec}</li>
                ))}
              </ul>
            </div>
          )}

          {/* 最后检查时间 */}
          {aiStatus.lastChecked && (
            <div className={styles.lastChecked}>
              上次检查: {new Date(aiStatus.lastChecked).toLocaleTimeString()}
              <button 
                className={styles.refreshButton}
                onClick={(e) => {
                  e.stopPropagation()
                  fetchAIStatus()
                }}
                disabled={aiStatus.isLoading}
              >
                🔄 刷新
              </button>
            </div>
          )}

          {/* 错误信息 */}
          {aiStatus.error && (
            <div className={styles.errorMessage}>
              ⚠️ {aiStatus.error}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default AIStatusIndicator
