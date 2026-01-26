/**
 * 对话面板组件
 */

import React, { useRef, useEffect } from 'react';
import MessageBubble from './MessageBubble';
import InputArea from './InputArea';
import QuickActions from './QuickActions';
import { ChatMessage } from '../../../shared/types';

interface ChatPanelProps {
    messages: ChatMessage[];
    isLoading: boolean;
    actions?: Array<{ label: string; command: string }>;
    progress?: { label: string; percent?: number } | null;
    onSendMessage: (content: string) => void;
    onSuggestion?: (command: string) => void;
    onRetryTool?: (toolCall: ChatMessage['toolCall']) => void;
    onConfirmTool?: (toolCall: ChatMessage['toolCall']) => void;
    onPinVisualization?: (visualization: ChatMessage['visualization']) => void;
}

const ChatPanel: React.FC<ChatPanelProps> = ({
    messages,
    isLoading,
    actions,
    progress,
    onSendMessage,
    onSuggestion,
    onRetryTool,
    onConfirmTool,
    onPinVisualization,
}) => {
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // 自动滚动到底部
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const quickActions = actions || [];

    return (
        <div className="chat-panel">
            {/* 消息列表区域 */}
            <div className="messages-container">
                {messages.length === 0 ? (
                    <div className="welcome-message">
                        <h2>欢迎使用 AetherTrade</h2>
                        <p>可以直接输入股票代码或需求，例如“分析 600519”、“今日市场”、“板块行情”。</p>
                    </div>
                ) : (
                    messages.map(message => (
                        <MessageBubble
                            key={message.id}
                            message={message}
                            onSuggestion={onSuggestion}
                            onRetryTool={onRetryTool}
                            onConfirmTool={onConfirmTool}
                            onPinVisualization={onPinVisualization}
                        />
                    ))
                )}

                {isLoading && (
                    <div className="loading-indicator">
                        <span className="dot"></span>
                        <span className="dot"></span>
                        <span className="dot"></span>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {progress && (
                <div className="progress-status">
                    <span>{progress.label}</span>
                    <div className="progress-bar">
                        <div
                            className="progress-bar-fill"
                            style={{ width: `${progress.percent ?? 40}%` }}
                        />
                    </div>
                </div>
            )}

            <QuickActions actions={quickActions} onAction={onSendMessage} />

            {/* 输入区域 */}
            <InputArea onSend={onSendMessage} disabled={isLoading} />
        </div>
    );
};

export default ChatPanel;
