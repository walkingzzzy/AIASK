/**
 * Web 入口点
 * 
 * 通过 polyfill window.electronAPI 来兼容现有组件代码
 */

import React from 'react';
import { createRoot } from 'react-dom/client';
import { createWebAdapter } from './renderer/api/web-adapter';
import App from './renderer/App';
import './renderer/styles/index.css';  // 导入完整的应用样式

// 在 Web 环境中创建 electronAPI polyfill
if (!window.electronAPI) {
    const webAdapter = createWebAdapter();

    // 创建兼容的 electronAPI 接口
    (window as typeof window & { electronAPI: typeof webAdapter }).electronAPI = {
        mcp: webAdapter.mcp,
        db: webAdapter.db,
        config: webAdapter.config,
        watchlist: webAdapter.watchlist,
        behavior: webAdapter.behavior,
        ai: webAdapter.ai,
        trading: webAdapter.trading,
        proxy: webAdapter.proxy,
        platform: webAdapter.platform,
    };

    console.log('[Web] electronAPI polyfill installed');
}

// 渲染应用
const container = document.getElementById('app');
if (container) {
    const root = createRoot(container);
    root.render(<App />);
    console.log('[Web] App rendered');
}
