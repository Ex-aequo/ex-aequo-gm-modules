import type { GameState, GMOrder, PlayerView, Preview, RegionDetail } from "./types";

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
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

export const api = {
  state: () => call<GameState>("GET", "/api/state"),
  region: (id: number) => call<RegionDetail>("GET", `/api/region/${id}`),
  view: (fid: number) => call<PlayerView>("GET", `/api/view/${fid}`),
  addOrder: (o: GMOrder) => call<{ pending: GMOrder[] }>("POST", "/api/gm/orders", o),
  removeOrder: (i: number) => call<{ pending: GMOrder[] }>("DELETE", `/api/gm/orders/${i}`),
  resolve: () => call<GameState>("POST", "/api/turn"),
  preview: (turns: number) => call<Preview>("POST", "/api/preview", { turns }),
  reset: (seed: string) => call<GameState>("POST", "/api/reset", { seed }),
};
