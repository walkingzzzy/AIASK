const http = require('http');
const fs = require('fs');
const path = require('path');
const base = path.resolve(process.argv[2]);
fs.mkdirSync(base, { recursive: true });
function safeName(name) {
  return String(name || '').replace(/[\\/:*?"<>|]/g, '_').replace(/^\.+/, '_').slice(0, 180) || `artifact-${Date.now()}`;
}
const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, base }));
    return;
  }
  if (req.method !== 'POST' || req.url !== '/save') {
    res.writeHead(404); res.end('not found'); return;
  }
  let body = '';
  req.setEncoding('utf8');
  req.on('data', chunk => { body += chunk; if (body.length > 80 * 1024 * 1024) req.destroy(); });
  req.on('end', () => {
    try {
      const payload = JSON.parse(body || '{}');
      const name = safeName(payload.name);
      const resolved = path.resolve(path.join(base, name));
      if (!resolved.startsWith(base)) throw new Error('path outside base');
      if (payload.base64) fs.writeFileSync(resolved, Buffer.from(payload.base64, 'base64'));
      else fs.writeFileSync(resolved, String(payload.text || ''), 'utf8');
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ ok: true, path: resolved }));
    } catch (err) {
      res.writeHead(500, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ ok: false, error: String(err && err.message || err) }));
    }
  });
});
server.listen(9324, '127.0.0.1', () => console.log(`save-server ${base}`));
