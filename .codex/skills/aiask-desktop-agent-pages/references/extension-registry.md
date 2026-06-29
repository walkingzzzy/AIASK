# Desktop Extension Registry

There is no active standalone extension registry file in the current Desktop tree. Treat `desktop/src/views.ts`, `desktop/src/routes.ts`, `desktop/src/App.tsx`, and the `Enhanced*Pages` wrappers as the source of truth for Desktop navigation and controlled page composition.

The current navigation shell is an internal AIASK-native static composition. It does not load external JavaScript and should only render React components from this repository.

## Current Concepts

- View groups such as task workspace, finance research, integration surfaces, and automation/ops.
- Enhanced wrappers that preserve current product boundaries, especially hiding direct Strategy/Factor/Incubation entry points behind safer surfaces.
- Shared shell composition in `App.tsx`, including sidebar, workbench inspector, and context drawer.
- Control-token and full-mode gates are displayed, not bypassed.

## Rules

- Do not add dynamic third-party code loading through navigation or page composition helpers.
- Do not treat gate flags as a hiding mechanism; gated entries may still render as visible but controlled shortcuts.
- Keep routes synchronized with `views.ts`, `routes.ts`, and the page selection logic in `App.tsx`.
- Update `desktop/src/App.test.tsx` or e2e route coverage when adding or removing navigable surfaces.
