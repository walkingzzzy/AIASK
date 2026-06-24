import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { buildDesktopEnv } from "./rootEnv.mjs";

const mode = process.argv[2] || "mock";
const extraArgs = process.argv.slice(3);
const here = dirname(fileURLToPath(import.meta.url));
const playwrightCli = resolve(here, "../node_modules/@playwright/test/cli.js");
const env = buildDesktopEnv(process.env, mode);

const child = spawn(process.execPath, [playwrightCli, "test", "--project=chromium", ...extraArgs], {
  stdio: "inherit",
  env
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
