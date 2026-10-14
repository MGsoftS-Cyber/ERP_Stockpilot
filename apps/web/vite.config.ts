import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules") && (id.includes("@mui/") || id.includes("@emotion/") || id.includes("stylis"))) return "ui";
          if (id.includes("node_modules") && id.includes("oidc-client-ts")) return "identity";
        },
      },
    },
  },
  test: {
    environment: "node",
  },
});
