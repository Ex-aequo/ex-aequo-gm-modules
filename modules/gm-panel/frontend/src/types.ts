import type { ViewerState } from "@pf/game/state";

export type Intensity = "weak" | "normal" | "strong";

export type GMOrder =
  | { type: "plague_state"; value: "active" | "dormant" }
  | { type: "plague_intensity"; value: Intensity }
  | { type: "plague_focus"; region: number }
  | { type: "rumor"; text: string; factions?: number[]; region?: number; radius?: number };

export interface Faction {
  id: number;
  name: string;
  color: string;
  active: boolean;
  style: string;
  bot: boolean;
  regions: number;
  men: number;
  growth10: number;
  stock: Record<string, number>;
  protected: boolean;
}

export interface Metrics {
  turn: number;
  lost: number;
  contaminated: number;
  free: number;
  plague_active: boolean;
  leader: number | null;
  leader_regions: number;
}

export interface ChronicleEntry {
  turn: number;
  kind: "gm" | "plague" | "war" | "faction" | "info" | "warn";
  text: string;
  regions?: number[];
}

export interface Snapshot {
  turn: number;
  owner: number[];
  plague: number[];
  /** faixa da Praga por província: 0 limpa, 1 contaminada, 2 infestada, 3 perdida */
  bands: number[];
  plague_active: boolean;
  plague_intensity: Intensity;
  suggested_foci: number[];
  factions: Faction[];
  praga: { id: number; name: string; color: string };
  metrics: Metrics;
}

export interface PlayerAccount {
  username: string; faction: number; name: string; active: boolean; controller: "player" | "bot" | null;
  submitted: boolean; idle: number | null;
}

export interface GameState extends Snapshot {
  mode?: "game";                  // só no jogo real (game-server)
  players?: PlayerAccount[];
  timer_minutes?: number;
  deadline?: string | null;
  pending: GMOrder[];
  history: Metrics[];
  chronicle: ChronicleEntry[];
}

export interface Preview extends Snapshot {
  from_turn: number;
  turns: number;
  series: Metrics[];
  newly_lost: number[];
  factions_hit: { id: number; name: string; lost: number }[];
}

export interface RegionDetail {
  id: number;
  name: string;
  kind: string;
  biome: string;
  elevation: number;
  coastal: boolean;
  owner: number;
  pop: number;
  order: number;
  fort: number;
  building: string | null;
  level: number;
  plague: number;
  garrison: number;
  armies: { owner: number; men: number; vet: number }[];
  agents: { owner: number; kind: "scout" | "spy" }[];
  suggested_focus: boolean;
}

/** O que um jogador sabe de uma região (§8). level: 1 conhecida, 2 visível, 3 espiada, 4 própria. */
export interface KnownRegion {
  level: 1 | 2 | 3 | 4;
  t: number;
  o: number;
  p?: number;
  f?: number;
  b?: string | null;
  l?: number;
  a?: [number, number][];
  g?: number;
  x?: { armies: [number, number, number][]; garrison: number; pop: number; order: number; plague: number };
  pop?: number;
  order?: number;
  fort?: number;
  building?: string | null;
  lvl?: number;
  plague?: number;
}

export interface InboxEntry {
  turn: number;
  kind: "rumour" | "gm" | "report";
  text: string;
}

export interface PlayerView {
  turn: number;
  faction: { id: number; name: string; stock: Record<string, number>; command_points: number; famine: boolean };
  regions: Record<string, KnownRegion>;
  armies: { id: number; region: number; men: number; vet: number }[];
  agents: { id: number; kind: "scout" | "spy"; region: number }[];
  factions: { id: number; name: string; bot: boolean }[];
  inbox: InboxEntry[];
  viewer: ViewerState;
  map_factions: { id: number; name: string; color: string }[];
  known_share: number;
}
