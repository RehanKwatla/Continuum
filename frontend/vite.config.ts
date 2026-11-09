/// <reference types="vitest" />
import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
  },
  preview: {
    port: 4173,
  },
  build: {
    // Raise the warning threshold slightly so the split is visible in output
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: {
          // React core — changes rarely, long-lived browser cache
          "vendor-react": ["react", "react-dom"],
          // Router — changes rarely
          "vendor-router": ["react-router-dom"],
          // TanStack Query
          "vendor-query": ["@tanstack/react-query"],
          // Radix UI primitives
          "vendor-radix": [
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-select",
            "@radix-ui/react-tabs",
            "@radix-ui/react-toast",
            "@radix-ui/react-label",
            "@radix-ui/react-separator",
            "@radix-ui/react-slot",
            "@radix-ui/react-avatar",
          ],
          // Supabase auth client
          "vendor-supabase": ["@supabase/supabase-js"],
          // HTTP client
          "vendor-axios": ["axios"],
          // Icon library (large — isolated so it can be cached separately)
          "vendor-icons": ["lucide-react"],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
