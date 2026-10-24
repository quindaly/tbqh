import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  // Next compiles JSX itself; tests need the modern transform (no React import).
  esbuild: { jsx: "automatic" },
  resolve: { alias: { "@": path.resolve(__dirname) } },
  test: { environment: "node", include: ["lib/**/*.test.{ts,tsx}", "app/**/*.test.{ts,tsx}"] },
});
