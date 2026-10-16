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

/** O painel do GM corre dentro do servidor do jogo (modules/game-server), em /gm/, com sessão de GM. */
export const GAME_MODE = true;
const B = "/api/gm";

export interface WorldInfo { dir: string; name: string; kingdoms: number; provinces: number; created: string; fairness: number | null; issues: string[] }
export interface WorldJob { state: "running" | "done" | "failed"; name: string; dir: string; stage: string; pct: number; error: string | null }

export const api = {
  state: () => call<GameState>("GET", `${B}/state`),
  region: (id: number) => call<RegionDetail>("GET", `${B}/region/${id}`),
  view: (fid: number) => call<PlayerView>("GET", `${B}/view/${fid}`),
  addOrder: (o: GMOrder) => call<{ pending: GMOrder[] }>("POST", `${B}/orders`, o),
  removeOrder: (i: number) => call<{ pending: GMOrder[] }>("DELETE", `${B}/orders/${i}`),
  resolve: () => call<GameState>("POST", `${B}/turn`),
  preview: (turns: number) => call<Preview>("POST", `${B}/preview`, { turns }),
  timer: (minutes: number) => call<GameState>("POST", `${B}/timer`, { minutes }),
  logout: () => call<{ ok: boolean }>("POST", "/api/logout"),
  worlds: () => call<{ worlds: WorldInfo[]; job: WorldJob | null; current: string | null }>("GET", `${B}/worlds`),
  newWorld: (name: string, seed: string, params: Record<string, unknown>) =>
    call<{ job: WorldJob }>("POST", `${B}/worlds`, { name, seed, params }),
  newGame: (dir: string) => call<{ ok: boolean; players: { username: string; faction: number | null }[] }>("POST", `${B}/new-game`, { dir }),
};
