import { useEffect, useMemo, useRef, useState } from "react";
import type { ViewerState } from "@pf/game/state";
import type { ClientMap } from "@pf/map/clientMap";
import { ForgeMap, GameTiles, type Camera, type ForgeMapApi, type Marker } from "@forge-view/ForgeMap";

/** Província do Praga (rid, 1..L) ↔ região do Province-Forge (pf = rid - 1). */
export const toPf = (rid: number) => rid - 1;

/** Vista completa (GM) a partir dos vetores do estado: dono e faixa da Praga por província. */
export function fullViewer(map: ClientMap, owner: number[], bands: number[],
  factions: { id: number; name: string; color: string; active?: boolean }[]): ViewerState {
  const provinces: ViewerState["provinces"] = {};
  for (let rid = 1; rid < owner.length; rid++) {
    const o = owner[rid] > 0 ? String(owner[rid]) : null;
    provinces[rid - 1] = { owner: o, controller: o, praga: (owner[rid] === -1 ? 3 : bands[rid] ?? 0) as 0 | 1 | 2 | 3 };
  }
  return {
    turn: 0, viewer: null, known: {}, details: {}, reserved: [],
    countries: factions.filter((f) => f.id > 0 && f.active !== false).map((f) => ({
      id: String(f.id), name: { pt: f.name, en: f.name }, fullName: { pt: f.name, en: f.name }, color: f.color,
    })),
    provinces,
    visible: map.regions.map((r, i) => (r ? i : -1)).filter((i) => i >= 0),
  };
}

interface Props {
  view: ViewerState | null;
  markers: Marker[];
  selected: number;
  focusTarget: number;
  mode: "political" | "praga";
  onRegionClick: (rid: number) => void;
  onHover: (rid: number) => void;
  onReady: (map: ClientMap) => void;
}

/** O mapa do GM: o mapa completo do Province-Forge (o GM vê tudo) e, em "ver como", a vista de uma fação. */
export function GmMap({ view, markers, selected, focusTarget, mode, onRegionClick, onHover, onReady }: Props) {
  const [map, setMap] = useState<ClientMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const camera = useRef<Camera | null>(null);
  const api = useRef<ForgeMapApi | null>(null);

  useEffect(() => {
    fetch("/api/map/client-map.json", { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then((m: ClientMap) => { setMap(m); onReady(m); })
      .catch((e: Error) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const tiles = useMemo(() => (map?.tiles ? new GameTiles("/api/map/gm/tiles", map.tiles) : null), [map]);
  const markersPf = useMemo(() => markers.map((m) => ({ ...m, region: toPf(m.region) })), [markers]);
  useEffect(() => { if (focusTarget) api.current?.focus(toPf(focusTarget)); }, [focusTarget]);

  if (error) return <div className="map"><div className="map-error">O mapa não carregou: {error}</div></div>;
  if (!map) return <div className="map" />;
  const isLand = (pf: number | null) => pf !== null && map.regions[pf]?.kind === "land";
  return (
    <div className="map">
      <ForgeMap map={map} tiles={tiles} view={view} mode={mode} markers={markersPf} camera={camera} apiRef={api}
        selected={selected ? toPf(selected) : null}
        onSelect={(pf) => onRegionClick(isLand(pf) ? pf! + 1 : 0)}
        onHover={(pf) => onHover(isLand(pf) ? pf! + 1 : 0)} />
    </div>
  );
}
