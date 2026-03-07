const base = 'http://127.0.0.1:3001/api';

async function json(url, init) {
  const res = await fetch(url, init);
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  return { res, data };
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const getChecks = [
  ['profile', '/auth/profile', (d) => d?.success === true && Boolean(d?.data?.username)],
  ['sessions', '/auth/sessions', (d) => d?.success === true && Array.isArray(d?.data?.items)],
  ['audit', '/audit/my-logs?limit=5', (d) => d?.success === true && Array.isArray(d?.data?.items)],
  ['chat conversations', '/chat/conversations', (d) => d?.success === true && Array.isArray(d?.data?.conversations)],
  ['notifications', '/notifications/list?limit=5', (d) => d?.success === true && Array.isArray(d?.data?.items)],
  ['paper performance', '/paper-trading/performance?days=7', (d) => d?.success === true && Boolean(d?.data?.metrics)],
  ['export my-data', '/export/my-data', (d) => d?.success === true && Boolean(d?.data?.profile) && Boolean(d?.data?.paperTrading)],
  ['export report', '/export/report?period=monthly', (d) => d?.success === true && Boolean(d?.data?.report)],
];

async function main() {
  const login = await json(`${base}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: 'demo', password: 'demo123' }),
  });
  assert(login.res.ok, `登录失败: ${login.res.status} ${JSON.stringify(login.data)}`);
  const token = login.data?.accessToken;
  assert(token, '登录返回缺少 accessToken');
  const headers = { authorization: `Bearer ${token}` };

  const sync = await json(`${base}/chat/conversations/sync`, {
    method: 'POST',
    headers: { ...headers, 'content-type': 'application/json' },
    body: JSON.stringify({
      conversations: [
        {
          id: 'smoke',
          title: '烟雾测试会话',
          updatedAt: new Date().toISOString(),
          messages: [
            { role: 'user', content: '你好' },
            { role: 'assistant', content: '你好，这是一条烟雾测试消息。' },
          ],
        },
      ],
    }),
  });
  assert(sync.res.ok, `chat sync 失败: ${sync.res.status} ${JSON.stringify(sync.data)}`);
  assert(sync.data?.success === true, `chat sync 返回结构异常: ${JSON.stringify(sync.data)}`);

  const results = [{ name: 'chat sync', status: sync.res.status }];
  for (const [name, path, check] of getChecks) {
    const result = await json(`${base}${path}`, { headers });
    assert(result.res.ok, `${name} 失败: ${result.res.status} ${JSON.stringify(result.data)}`);
    assert(check(result.data), `${name} 返回结构不符合预期: ${JSON.stringify(result.data).slice(0, 400)}`);
    results.push({ name, status: result.res.status });
  }

  console.log(JSON.stringify({ ok: true, results }, null, 2));
}

main().catch((err) => {
  console.error(String(err?.stack || err));
  process.exit(1);
});

