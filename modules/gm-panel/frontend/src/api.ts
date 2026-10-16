import type { GameState, GMOrder, PlayerView, Preview, RegionDetail } from "./types";

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && GAME_MODE) {
    location.href = "/";                                  // sessão expirada: volta ao ecrã de entrada
    throw new Error("sessão expirada");
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* resposta sem JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

/**
 * O painel corre em dois sítios:
 *  - sandbox (backend deste módulo, em /): API em /api, ficheiros do mapa em /data
 *  - jogo real (modules/game-server, em /gm/): API do GM em /api/gm, mapa em /api/map, com sessão de GM
 */
export const GAME_MODE = location.pathname.startsWith("/gm");
const B = GAME_MODE ? "/api/gm" : "/api";
export const DATA_URL = GAME_MODE ? "/api/map" : "/data";

export const api = {
  state: () => call<GameState>("GET", `${B}/state`),
  region: (id: number) => call<RegionDetail>("GET", `${B}/region/${id}`),
  view: (fid: number) => call<PlayerView>("GET", `${B}/view/${fid}`),
  addOrder: (o: GMOrder) => call<{ pending: GMOrder[] }>("POST", "/api/gm/orders", o),
  removeOrder: (i: number) => call<{ pending: GMOrder[] }>("DELETE", `/api/gm/orders/${i}`),
  resolve: () => call<GameState>("POST", GAME_MODE ? "/api/gm/turn" : "/api/turn"),
  join: () => call<GameState>("POST", "/api/join"),
  preview: (turns: number) => call<Preview>("POST", `${B}/preview`, { turns }),
  reset: (seed: string) => call<GameState>("POST", "/api/reset", { seed }),
  timer: (minutes: number) => call<GameState>("POST", "/api/gm/timer", { minutes }),
  logout: () => call<{ ok: boolean }>("POST", "/api/logout"),
};
