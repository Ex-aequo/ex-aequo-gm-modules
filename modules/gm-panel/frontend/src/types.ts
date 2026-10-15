export type Intensity = "weak" | "normal" | "strong";

export type GMOrder =
  | { type: "plague_state"; value: "active" | "dormant" }
  | { type: "plague_intensity"; value: Intensity }
  | { type: "plague_focus"; region: number };

export interface Faction {
  id: number;
  name: string;
  color: string;
  active: boolean;
  style: string;
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
  plague_active: boolean;
  plague_intensity: Intensity;
  suggested_foci: number[];
  factions: Faction[];
  praga: { id: number; name: string; color: string };
  metrics: Metrics;
}

export interface GameState extends Snapshot {
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
  suggested_focus: boolean;
}
