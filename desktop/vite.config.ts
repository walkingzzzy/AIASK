import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { desktopChunkName, resolveDesktopModulePreloadDependencies } from "./src/buildPreloadPolicy";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true
  },
  build: {
    modulePreload: {
      resolveDependencies(_, deps, { hostType }) {
        return resolveDesktopModulePreloadDependencies(deps, hostType);
      }
    },
    rollupOptions: {
      output: {
        manualChunks: desktopChunkName
      }
    }
  },
  clearScreen: false
});
