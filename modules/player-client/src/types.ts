export type Order =
  | { type: "move"; army: number; path: number[] }
  | { type: "attack"; army: number; target: number }
  | { type: "garrison"; army: number }
  | { type: "purge"; army: number }
  | { type: "build"; region: number; what: string }
  | { type: "recruit"; region: number; men: number }
  | { type: "posture"; faction: number; value: "ally" | "neutral" | "hostile" }
  | { type: "recruit_agent"; region: number; kind: "scout" | "spy" }
  | { type: "agent_move"; agent: number; path: number[] };

/** O que o jogador sabe de uma região. level: 1 conhecida (fotografia), 2 visível, 3 espiada, 4 tua. */
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
  x?: { armies: [number, number, number][]; garrison: number; pop: number; order: number; plague: number; project: Record<string, unknown> | null };
  pop?: number;
  order?: number;
  fort?: number;
  building?: string | null;
  lvl?: number;
  project?: { kind: string; what?: string; left: number } | null;
  plague?: number;
}

export interface PlayerState {
  turn: number;
  faction: {
    id: number; name: string; stock: Record<string, number>; postures: Record<string, string>;
    famine: boolean; protected_until: number; command_points: number;
  };
  regions: Record<string, KnownRegion>;
  armies: { id: number; region: number; men: number; vet: number }[];
  agents: { id: number; kind: "scout" | "spy"; region: number }[];
  factions: { id: number; name: string; bot: boolean }[];
  inbox: { turn: number; kind: "rumour" | "gm" | "report"; text: string }[];
  owner: number[];
  plague: number[];
  fog: number[];
  map_factions: { id: number; name: string; color: string }[];
  orders: Order[];
  order_cost: Record<string, number>;
  costs: {
    scout: Record<string, number>; spy: Record<string, number>; recruit_per_100: Record<string, number>;
    fort: Record<string, number>; building: Record<string, Record<string, number>>;
  };
  clock: { turn: number; timer_minutes: number; deadline: string | null };
  allowed_buildings: Record<string, string[]>;
}

export interface Me {
  username: string;
  role: "gm" | "player";
  faction: number | null;
  faction_name: string | null;
  world: string;
}
