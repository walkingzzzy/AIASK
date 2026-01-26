/**
 * 快捷指令组件
 */

import React from 'react';

interface QuickAction {
    label: string;
    command: string;
}

interface QuickActionsProps {
    actions: QuickAction[];
    onAction: (command: string) => void;
}

const QuickActions: React.FC<QuickActionsProps> = ({ actions, onAction }) => {
    if (!actions || actions.length === 0) {
        return null;
    }
    return (
        <div className="quick-actions">
            {actions.map((action, index) => (
                <button
                    key={index}
                    className="quick-action-btn"
                    onClick={() => onAction(action.command)}
                >
                    {action.label}
                </button>
            ))}
        </div>
    );
};

export default QuickActions;
