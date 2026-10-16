// O mapa do Praga: o MapView do Province-Forge (vendor/province-forge) com uma camada por cima para o que é do
// jogo — exércitos, agentes, alvos e as setas das ordens. Partilhado pelo cliente dos jogadores e pelo painel do GM.
//
// Ids: tudo aqui está em ids do Province-Forge (pf). No Praga, a província rid tem pf = rid - 1.
import { useEffect, useRef } from "react";
import type { ViewerState } from "@pf/game/state";
import type { ClientMap, TileSpec } from "@pf/map/clientMap";
import { MapView, type MapMode } from "@pf/view/MapView";

/** O mesmo contrato que TileSource do Province-Forge (src/view/tileSources.ts), sem importar esse ficheiro
 *  (que traz o gerador inteiro). */
export interface TileSource {
  readonly tile: number;
  readonly basePx: number;
  readonly maxLevel: number;
  request(level: number, tx: number, ty: number): Promise<string | null>;
  release?(url: string): void;
  readonly expensive: boolean;
  dispose?(): void;
}

export type MarkerKind = "army" | "foe" | "agent" | "target" | "focus";
export interface Marker { region: number; kind: MarkerKind; label?: string; selected?: boolean }
export type PathKind = "move" | "attack" | "agent";
export interface MapPath { kind: PathKind; regions: number[] }
export interface Camera { cx: number; cy: number; zoom: number }

/** Tiles servidos pelo servidor do jogo (filtrados por jogador). `version` muda o URL quando o jogador passa a
 *  conhecer mais (o turno), para o browser não reutilizar tiles antigos. */
export class GameTiles implements TileSource {
  readonly tile: number;
  readonly basePx: number;
  readonly maxLevel: number;
  readonly expensive = false;
  constructor(private base: string, spec: TileSpec) {
    this.tile = spec.tile; this.basePx = spec.basePx; this.maxLevel = spec.maxLevel;
  }
  async request(level: number, tx: number, ty: number) {
    return `${this.base}/${level}/${tx}/${ty}.webp`;
  }
}

export interface ForgeMapProps {
  map: ClientMap;
  tiles: TileSource | null;
  view: ViewerState | null;
  mode?: MapMode;
  markers?: Marker[];
  paths?: MapPath[];
  selected?: number | null;
  onSelect?: (pf: number | null) => void;
  onHover?: (pf: number | null) => void;
  /** Câmara guardada entre mapas (o mapa muda a cada turno). */
  camera?: React.MutableRefObject<Camera | null>;
  /** Região para onde olhar da primeira vez (se não houver câmara guardada). */
  home?: number;
  apiRef?: React.MutableRefObject<ForgeMapApi | null>;
}

export interface ForgeMapApi { focus: (pf: number, provincesAcross?: number) => void; view: MapView }

const COLORS = { army: "#f3e2b3", foe: "#c0392b", agent: "#2c3e50", target: "#ffd166", focus: "#5e2a62" };
const PATH = { move: "#f3e2b3", attack: "#e0533d", agent: "#9fb7c9" };

/** A camada do jogo, em unidades do mundo: os tamanhos dividem-se pelo zoom para ficarem iguais no ecrã. */
function overlaySvg(map: ClientMap, markers: Marker[], paths: MapPath[], zoom: number): string {
  const W = map.world.width;
  const at = (pf: number) => map.regions[pf]?.label ?? null;
  const k = 1 / zoom;
  const out: string[] = [];
  for (const p of paths) {
    const pts: [number, number][] = [];
    for (const pf of p.regions) {
      const q = at(pf);
      if (!q) continue;
      let [x, y] = q;
      if (pts.length) {                                     // pelo lado mais curto da volta do mundo
        const px = pts[pts.length - 1][0];
        x += Math.round((px - x) / W) * W;
      }
      pts.push([x, y]);
    }
    if (pts.length < 2) continue;
    const c = PATH[p.kind];
    const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join("");
    out.push(`<path d="${d}" fill="none" stroke="rgba(20,14,8,0.65)" stroke-width="${5 * k}" stroke-linecap="round" stroke-linejoin="round"/>`);
    out.push(`<path d="${d}" fill="none" stroke="${c}" stroke-width="${2.6 * k}" stroke-linecap="round" stroke-linejoin="round"${p.kind === "agent" ? ` stroke-dasharray="${6 * k} ${4 * k}"` : ""}/>`);
    const [x1, y1] = pts[pts.length - 1], [x0, y0] = pts[pts.length - 2];
    const a = Math.atan2(y1 - y0, x1 - x0), L = 11 * k, Wd = 6 * k;
    const bx = x1 - Math.cos(a) * L * 0.9, by = y1 - Math.sin(a) * L * 0.9;
    const tri = [[x1, y1], [bx - Math.sin(a) * Wd, by + Math.cos(a) * Wd], [bx + Math.sin(a) * Wd, by - Math.cos(a) * Wd]];
    out.push(`<path d="M${tri.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join("L")}Z" fill="${c}" stroke="rgba(20,14,8,0.7)" stroke-width="${1.2 * k}"/>`);
  }
  // marcadores na mesma região ficam lado a lado
  const slot = new Map<number, number>();
  for (const m of markers) {
    const q = at(m.region);
    if (!q) continue;
    const n = slot.get(m.region) ?? 0;
    slot.set(m.region, n + 1);
    const x = q[0] + (n ? (n % 2 ? 1 : -1) * Math.ceil(n / 2) * 20 * k : 0), y = q[1] - 4 * k;
    const s = 9 * k, c = COLORS[m.kind];
    const ring = m.selected ? `stroke="#ffffff" stroke-width="${2.4 * k}"` : `stroke="rgba(20,14,8,0.85)" stroke-width="${1.3 * k}"`;
    if (m.kind === "army" || m.kind === "foe") {
      out.push(`<path d="M${x - s} ${y - s}H${x + s}V${y + 0.1 * s}Q${x + s} ${y + s} ${x} ${y + 1.4 * s}Q${x - s} ${y + s} ${x - s} ${y + 0.1 * s}Z" fill="${c}" ${ring}/>`);
    } else if (m.kind === "agent") {
      out.push(`<path d="M${x} ${y - s}L${x + s * 0.8} ${y}L${x} ${y + s}L${x - s * 0.8} ${y}Z" fill="${c}" ${ring}/>`);
    } else if (m.kind === "focus") {
      out.push(`<circle cx="${x}" cy="${y}" r="${s * 0.9}" fill="${c}" fill-opacity="0.85" ${ring}/>`);
    } else {
      out.push(`<circle cx="${x}" cy="${y}" r="${s * 1.5}" fill="none" stroke="${c}" stroke-width="${2.4 * k}" stroke-dasharray="${4 * k} ${3 * k}"/>`);
    }
    if (m.label) {
      const fs = 10.5 * k;
      out.push(`<text x="${x}" y="${y + s * 1.4 + fs * 1.1}" text-anchor="middle" font-size="${fs}" font-family="Spectral, Georgia, serif" font-weight="600" fill="#fff8e6" stroke="rgba(20,14,8,0.9)" stroke-width="${2.6 * k}" paint-order="stroke">${m.label.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</text>`);
    }
  }
  return out.join("");
}

export function ForgeMap(p: ForgeMapProps) {
  const host = useRef<HTMLDivElement>(null);
  const mv = useRef<MapView | null>(null);
  const zoom = useRef(1);
  const cb = useRef(p);
  cb.current = p;
  const raf = useRef(0);

  const drawOverlay = () => {
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(() => {
      const v = mv.current, q = cb.current;
      if (v) v.setOverlay(overlaySvg(q.map, q.markers ?? [], q.paths ?? [], zoom.current));
    });
  };

  useEffect(() => {
    if (!host.current) return;
    const saved = p.camera?.current ?? null;          // ler antes: o MapView novo já escreve a câmara ao arrancar
    const v = new MapView(host.current, {
      map: p.map, tiles: p.tiles, view: p.view, lang: "pt", mode: p.mode ?? "political",
      onSelect: (id) => cb.current.onSelect?.(id),
      onHover: (id) => cb.current.onHover?.(id),
      onViewChange: (s) => {
        if (cb.current.camera) cb.current.camera.current = { cx: s.cx, cy: s.cy, zoom: s.zoom };
        if (Math.abs(s.zoom - zoom.current) / zoom.current > 0.02) { zoom.current = s.zoom; drawOverlay(); }
      },
    });
    mv.current = v;
    const api: ForgeMapApi = {
      view: v,
      focus: (pf, across = 7) => {
        const r = cb.current.map.regions[pf];
        if (!r) return;
        const box = host.current!.getBoundingClientRect();
        v.viewport.state.zoom = Math.min(box.width, box.height) / (cb.current.map.spacing * 5 * across);
        v.viewport.centerOn(r.label[0], r.label[1]);
      },
    };
    if (p.apiRef) p.apiRef.current = api;
    const cam = saved;
    if (cam) {
      v.viewport.state.zoom = cam.zoom;
      v.viewport.centerOn(cam.cx, cam.cy);
    } else if (p.home !== undefined && p.home >= 0) {
      api.focus(p.home);
    }
    zoom.current = v.viewport.state.zoom;
    drawOverlay();
    return () => { cancelAnimationFrame(raf.current); v.destroy(); mv.current = null; if (p.apiRef) p.apiRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { mv.current?.setMap(p.map, p.tiles, true); drawOverlay(); }, [p.map, p.tiles]); // eslint-disable-line
  useEffect(() => { mv.current?.setView(p.view); }, [p.view]);
  useEffect(() => { if (p.mode) mv.current?.setMode(p.mode); }, [p.mode]);
  useEffect(() => { mv.current?.select(p.selected ?? null); }, [p.selected]);
  useEffect(() => { drawOverlay(); }, [p.markers, p.paths]); // eslint-disable-line

  return <div ref={host} className="forge-map" style={{ position: "absolute", inset: 0 }} />;
}
