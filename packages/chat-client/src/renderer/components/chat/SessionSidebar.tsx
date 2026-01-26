/**
 * 会话侧边栏组件 - 管理对话历史
 */

import React, { useState, useEffect } from 'react';
import { ChatSession } from '../../../shared/types';

interface SessionSidebarProps {
    currentSessionId: string | null;
    onSelectSession: (sessionId: string) => void;
    onNewSession: () => void;
    onToggleSidebar?: () => void;
}

const SessionSidebar: React.FC<SessionSidebarProps> = ({
    currentSessionId,
    onSelectSession,
    onNewSession,
    onToggleSidebar,
}) => {
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [searchQuery, setSearchQuery] = useState('');
    const [isLoading, setIsLoading] = useState(true);

    // 加载会话列表
    useEffect(() => {
        loadSessions();
    }, []);

    const loadSessions = async () => {
        setIsLoading(true);
        try {
            const result = await window.electronAPI.db.getSessions();
            if (result.success && result.data) {
                setSessions(result.data);
            }
        } catch (error) {
            console.error('Failed to load sessions:', error);
        } finally {
            setIsLoading(false);
        }
    };

    // 删除会话
    const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
        e.stopPropagation();
        if (!confirm('确定要删除这个对话吗？')) return;

        try {
            const result = await window.electronAPI.db.deleteSession(sessionId);
            if (result.success) {
                setSessions(prev => prev.filter(s => s.id !== sessionId));
            }
        } catch (error) {
            console.error('Failed to delete session:', error);
        }
    };

    // 格式化时间
    const formatDate = (timestamp: number) => {
        const date = new Date(timestamp);
        const now = new Date();
        const isToday = date.toDateString() === now.toDateString();

        if (isToday) {
            return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        }
        return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    };

    // 过滤会话
    const filteredSessions = searchQuery
        ? sessions.filter(s => s.title.toLowerCase().includes(searchQuery.toLowerCase()))
        : sessions;

    return (
        <div className="session-sidebar">
            <div className="sidebar-header">
                <h2>💬 对话历史</h2>
                <button className="collapse-btn" title="折叠侧边栏" onClick={onToggleSidebar}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="15 18 9 12 15 6" />
                    </svg>
                </button>
            </div>

            {/* 移除搜索框 - 根据设计图 */}

            <div className="session-list">
                {isLoading ? (
                    <div className="loading-text">加载中...</div>
                ) : filteredSessions.length === 0 ? (
                    <div className="empty-text">暂无对话历史</div>
                ) : (
                    filteredSessions.map(session => (
                        <button
                            key={session.id}
                            className={`session-item ${session.id === currentSessionId ? 'active' : ''}`}
                            onClick={() => onSelectSession(session.id)}
                        >
                            <span className="session-icon">💬</span>
                            <span className="session-title">{session.title}</span>
                        </button>
                    ))
                )}
            </div>

            <div className="sidebar-footer">
                <button className="new-session-btn-bottom" onClick={onNewSession}>
                    ➕ 新对话
                </button>
            </div>
        </div>
    );
};

export default SessionSidebar;
