/**
 * 股票AI对话客户端 - React 应用入口
 */

import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/index.css';

// 渲染应用
const container = document.getElementById('root');
if (container) {
    const root = createRoot(container);
    // 移除 StrictMode 以避免开发模式双重渲染导致 API 重复调用
    root.render(<App />);
}
