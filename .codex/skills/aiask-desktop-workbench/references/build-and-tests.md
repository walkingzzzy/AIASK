# Desktop Build And Tests

Run commands from `desktop/`.

## Scripts

- `npm run dev`: Vite server on `127.0.0.1:1420`.
- `npm run typecheck`: `tsc --noEmit`.
- `npm test`: Vitest over `src` with jsdom.
- `npm run build`: `tsc && vite build`.
- `npm run test:e2e:mock`: Playwright mock suite.
- `npm run test:e2e:live`: optional live smoke, requires real Agent and env.
- `npm run tauri`, `npm run tauri:dev`, `npm run tauri:build`.

## Validation Choices

- API/client/type contract changes: `npm run typecheck`.
- Component/hook/service changes: `npm test`.
- Build or bundle changes: `npm run build`.
- Page matrix/layout/workflow changes: `npm run test:e2e:mock`.
- Visual/manual verification: start `npm run dev`, then inspect `http://127.0.0.1:1420` with the in-app Browser when frontend behavior matters.

## Current Tests To Know

Examples:

- `src/services/aiaskApi.test.ts`: Desktop API route expectations.
- `src/App.test.tsx`: V1 shell and deferred-product entry checks.
- `e2e/aiask-v1.spec.ts`: full mock frontend matrix plus optional live smoke.
- `e2e/aiask-v1-p0-p4-completeness.spec.ts`: enhanced page coverage and routing checks.

## Build Notes

The production bundle may exceed Vite's default 500 kB chunk warning. Treat that as a performance follow-up, not a build failure, unless the task is specifically about bundle size or code splitting.
