import { spawn } from "node:child_process";

const isWindows = process.platform === "win32";
const playwrightArgs = ["playwright", "test", "--grep", "optional live desktop smoke", ...process.argv.slice(2)];
const command = isWindows ? "cmd.exe" : "npx";
const args = isWindows ? ["/d", "/s", "/c", "npx", ...playwrightArgs] : playwrightArgs;

const child = spawn(command, args, {
  env: { ...process.env, AIASK_DESKTOP_RUN_LIVE: "1" },
  stdio: "inherit"
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
