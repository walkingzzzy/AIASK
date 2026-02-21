import { spawn } from 'node:child_process';

function run(name, scriptName) {
  const isWin = process.platform === 'win32';
  const command = isWin ? 'cmd.exe' : 'npm';
  const args = isWin ? ['/d', '/s', '/c', `npm run ${scriptName}`] : ['run', scriptName];

  const child = spawn(command, args, {
    stdio: 'inherit',
    shell: false,
    env: process.env,
  });

  child.on('exit', (code, signal) => {
    const reason = signal ? `signal=${signal}` : `code=${code}`;
    console.log(`[${name}] exited (${reason})`);
  });

  child.on('error', (err) => {
    console.error(`[${name}] failed to start:`, err.message);
  });

  return child;
}

function killTree(pid) {
  if (!pid) return;

  if (process.platform === 'win32') {
    // /T kill child processes, /F force
    spawn('taskkill', ['/pid', String(pid), '/t', '/f'], {
      stdio: 'ignore',
      shell: false,
    });
  } else {
    process.kill(pid, 'SIGTERM');
  }
}

console.log('🚀 正在一键启动前端(web) + BFF ...');
console.log('   web: http://localhost:3000');
console.log('   bff: http://127.0.0.1:3001/api');
console.log('按 Ctrl+C 可同时停止两个服务。\n');

const web = run('web', 'dev:web');
const bff = run('bff', 'dev:bff');

function shutdown() {
  console.log('\n🛑 正在停止所有子进程...');
  killTree(web.pid);
  killTree(bff.pid);
  setTimeout(() => process.exit(0), 300);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

