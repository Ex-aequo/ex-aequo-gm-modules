import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const renderer = fileURLToPath(new URL("../map-renderer/renderer.js", import.meta.url));

// npm run dev: interface com recarga automática; a API vem do servidor do jogo na porta 8000
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@map-renderer": renderer } },
  server: { fs: { allow: [".", "../map-renderer"] }, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { target: "es2022" },
});
