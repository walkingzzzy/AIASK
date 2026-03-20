import fs from 'fs';

const baseUrl = 'http://127.0.0.1:3001/api';

async function login() {
    const res = await fetch(`${baseUrl}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'demo', password: 'demo123' })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(`Login failed: ${JSON.stringify(data)}`);
    return data.accessToken;
}

async function tryEndpoint(token, name, method, path, body = null) {
    const options = {
        method,
        headers: {
            'Authorization': `Bearer ${token}`
        }
    };
    if (body) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(body);
    }

    process.stdout.write(`Testing [${name}] ${method} ${path}... `);
    try {
        const res = await fetch(`${baseUrl}${path}`, options);
        const text = await res.text();
        // 200, 201, or 4xx indicating handled error but not 500
        if (res.status >= 200 && res.status < 500) {
            console.log(`\x1b[32mOK (HTTP ${res.status})\x1b[0m`);
            return true;
        } else {
            console.log(`\x1b[31mFAIL (HTTP ${res.status})\x1b[0m`);
            console.log(`Response: ${text.substring(0, 200)}`);
            return false;
        }
    } catch (err) {
        console.log(`\x1b[31mERROR\x1b[0m`);
        console.error(err);
        return false;
    }
}

async function run() {
    console.log("Starting extra tests...");
    let token;
    try {
        token = await login();
    } catch (e) {
        console.error(e);
        process.exit(1);
    }

    const tests = [
        ['Health', 'GET', '/health'],
        ['Watchlist', 'GET', '/watchlist/groups'],
        ['Paper-Trading', 'GET', '/paper-trading/accounts'],
        ['Strategy-Market', 'GET', '/strategy-market/list'],
        ['Fund-Flow', 'GET', '/fund-flow/stock/margin?code=600519'],
        ['Technical', 'POST', '/technical/indicators', { code: '600519', indicators: ['MA'] }],
        ['Valuation', 'GET', '/valuation/dcf?code=600519'],
        ['Sentiment', 'GET', '/sentiment/stock?code=600519'],
        ['Search', 'GET', '/search/similar?code=600519&limit=1'],
        ['Data', 'GET', '/data/trading-dates?startDate=2026-01-01&endDate=2026-03-01'],
        ['Chat', 'GET', '/chat/models'],
        ['Notification', 'GET', '/notifications/list'],
        ['Screener', 'GET', '/v1/screener/condition'],
        ['Macro', 'GET', '/v1/macro/indicator/LPR'],
        ['Options', 'GET', '/v1/options/chain/510300'],
        ['Skills', 'GET', '/v1/skills']
    ];

    let passed = 0;
    for (const [name, method, path, body] of tests) {
        const ok = await tryEndpoint(token, name, method, path, body);
        if (ok) passed++;
    }

    console.log(`\nTests completed. Passed: ${passed}/${tests.length}`);
}

run();
