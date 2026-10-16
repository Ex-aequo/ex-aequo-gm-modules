import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const pf = fileURLToPath(new URL("../../../vendor/province-forge/src", import.meta.url));
const pfModules = fileURLToPath(new URL("../../../vendor/province-forge/node_modules", import.meta.url));
const forgeView = fileURLToPath(new URL("../../forge-view", import.meta.url));

// servido pelo servidor do jogo em /gm/; npm run dev usa a API em localhost:8000
export default defineConfig({
  base: "./",
  plugins: [react()],
  // o mapa e o gerador vêm do Province-Forge (submódulo em vendor/); as dependências do gerador
  // (d3-delaunay, simplex-noise) vêm do node_modules dele
  resolve: {
    alias: { "@pf": pf, "@forge-view": forgeView, "d3-delaunay": `${pfModules}/d3-delaunay`, "simplex-noise": `${pfModules}/simplex-noise` },
    dedupe: ["react", "react-dom"],
  },
  server: { fs: { allow: [".", pf, pfModules, forgeView] }, proxy: { "/api": "http://127.0.0.1:8000" } },
  worker: { format: "es" },
  build: { target: "es2022" },
});
