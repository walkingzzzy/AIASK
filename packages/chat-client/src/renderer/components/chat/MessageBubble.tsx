/**
 * 消息气泡组件
 */

import React, { useState } from 'react';
import { ChatMessage } from '../../../shared/types';
import VisualizationRenderer from '../visualization/VisualizationRenderer';

interface MessageBubbleProps {
    message: ChatMessage;
    onSuggestion?: (command: string) => void;
    onRetryTool?: (toolCall: ChatMessage['toolCall']) => void;
    onConfirmTool?: (toolCall: ChatMessage['toolCall']) => void;
    onPinVisualization?: (visualization: ChatMessage['visualization']) => void;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({
    message,
    onSuggestion,
    onRetryTool,
    onConfirmTool,
    onPinVisualization,
}) => {
    const isUser = message.role === 'user';
    const isAssistant = message.role === 'assistant';
    const isTool = message.role === 'tool';
    const [showDetails, setShowDetails] = useState(false);

    // 格式化时间
    const formatTime = (date: Date) => {
        return new Date(date).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    // 渲染消息内容（支持简单 Markdown）
    const renderContent = (content: string) => {
        // 处理代码块
        if (content.includes('```')) {
            const parts = content.split(/(```[\s\S]*?```)/g);
            return parts.map((part, index) => {
                if (part.startsWith('```')) {
                    const code = part.replace(/```\w*\n?/g, '').replace(/```$/g, '');
                    return (
                        <pre key={index} className="code-block">
                            <code>{code}</code>
                        </pre>
                    );
                }
                return <span key={index}>{part}</span>;
            });
        }
        return content;
    };

    const hasVisualization = Boolean(message.visualization);
    const toolCallResult = message.toolCall?.result as { success?: boolean; error?: string; validationErrors?: unknown } | undefined;
    const requiresConfirmation = message.toolCall?.meta?.requiresConfirmation;
    const toolFailed = toolCallResult?.success === false && !requiresConfirmation;

    return (
        <div className={`message-bubble ${isUser ? 'user' : 'assistant'}`}>
            <div className="message-avatar">
                {isUser ? '👤' : isAssistant ? '🤖' : '🔧'}
            </div>
            <div className="message-content">
                <div className={`message-text ${hasVisualization ? 'compact' : ''}`}>
                    {renderContent(message.content)}
                </div>

                {/* 工具调用标记 */}
                {message.toolCall && (
                    <div className="tool-call-badge">
                        🔧 调用工具: {message.toolCall.name}
                    </div>
                )}

                {message.visualization && (
                    <VisualizationRenderer visualization={message.visualization} />
                )}

                {message.visualization && onPinVisualization && (
                    <div className="tool-actions">
                        <button
                            className="tool-action-btn"
                            onClick={() => onPinVisualization(message.visualization)}
                        >
                            📌 固定图表
                        </button>
                    </div>
                )}

                {message.toolCall && (
                    <div className="tool-actions">
                        <button
                            className="tool-action-btn"
                            onClick={() => setShowDetails(prev => !prev)}
                        >
                            {showDetails ? '收起详情' : '查看详情'}
                        </button>
                        {requiresConfirmation && onConfirmTool && (
                            <button
                                className="tool-action-btn"
                                onClick={() => onConfirmTool(message.toolCall)}
                            >
                                ✅ 确认执行
                            </button>
                        )}
                        {toolFailed && onRetryTool && (
                            <button
                                className="tool-action-btn"
                                onClick={() => onRetryTool(message.toolCall)}
                            >
                                🔁 重试
                            </button>
                        )}
                    </div>
                )}

                {showDetails && message.toolCall && (
                    <div className="tool-details">
                        <div>时间: {formatTime(message.createdAt)}</div>
                        <div>耗时: {message.toolCall.meta?.durationMs ?? '--'}ms</div>
                        <div>来源: {message.toolCall.meta?.source ?? '--'}</div>
                        <div>质量: {message.toolCall.meta?.quality ?? '--'}</div>
                        {message.toolCall.meta?.degraded && <div>提示: 已降级数据</div>}
                        {message.toolCall.meta?.requiresConfirmation && (
                            <div>提示: {message.toolCall.meta.confirmMessage || '需要确认执行'}</div>
                        )}
                        <pre>{JSON.stringify(message.toolCall.args, null, 2)}</pre>
                        {toolFailed && toolCallResult?.error && (
                            <div>错误: {toolCallResult.error}</div>
                        )}
                        {toolCallResult?.validationErrors && (
                            <div>参数错误: {JSON.stringify(toolCallResult.validationErrors)}</div>
                        )}
                    </div>
                )}

                {message.suggestions && message.suggestions.length > 0 && (
                    <div className="suggestion-list">
                        {message.suggestions.map(suggestion => (
                            <button
                                key={suggestion}
                                className="suggestion-btn"
                                onClick={() => onSuggestion?.(suggestion)}
                            >
                                {suggestion}
                            </button>
                        ))}
                    </div>
                )}

                <div className="message-time">
                    {formatTime(message.createdAt)}
                </div>
            </div>
        </div>
    );
};

export default MessageBubble;
