import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const pf = fileURLToPath(new URL("../../vendor/province-forge/src", import.meta.url));
const forgeView = fileURLToPath(new URL("../forge-view", import.meta.url));

// npm run dev: interface com recarga automática; a API vem do servidor do jogo na porta 8000
export default defineConfig({
  plugins: [react()],
  // o mapa vem do Province-Forge (submódulo em vendor/) e da camada partilhada em modules/forge-view
  resolve: { alias: { "@pf": pf, "@forge-view": forgeView }, dedupe: ["react", "react-dom"] },
  server: { fs: { allow: [".", pf, forgeView] }, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { target: "es2022" },
});
