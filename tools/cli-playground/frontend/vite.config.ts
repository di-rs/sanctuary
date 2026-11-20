import { readFileSync } from "node:fs";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite-plus";

export default defineConfig(({ command }) => ({
  plugins: [
    tailwindcss(),
    svelte(),
    {
      name: "tailwindcss-license",
      apply: "build",
      generateBundle() {
        // Vite's report covers bundled JS. theme.css also includes Tailwind CSS.
        this.emitFile({
          type: "asset",
          fileName: "tailwindcss.LICENSE",
          source: readFileSync(new URL("./node_modules/tailwindcss/LICENSE", import.meta.url)),
        });
      },
    },
  ],
  base: command === "build" ? "/static/" : "/",
  build: {
    outDir: "../src/cli_playground/static",
    emptyOutDir: true,
    license: { fileName: "licenses.md" },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  lint: {
    options: { typeAware: true, typeCheck: true },
    rules: {
      "typescript/ban-ts-comment": [
        "error",
        {
          "ts-ignore": "allow-with-description",
          "ts-expect-error": "allow-with-description",
          "ts-nocheck": true,
          "ts-check": false,
        },
      ],
      "unicorn/no-abusive-eslint-disable": "error",
    },
  },
  test: { include: ["src/**/*.test.ts", "e2e-native/*.test.ts"] },
}));
