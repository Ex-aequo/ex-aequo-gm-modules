import { useEffect, useRef, useState } from "react";
import { createMapRenderer, type MapMarker, type MapRenderer } from "@map-renderer";
import type { Snapshot } from "./types";

interface Props {
  snapshot: Snapshot | null;
  markers: MapMarker[];
  selected: number;
  focusTarget: number;
  onRegionClick: (id: number) => void;
  onHover: (id: number) => void;
  onReady: (names: Map<number, string>) => void;
}

/** O mapa partilhado (módulo map-renderer) dentro de um componente React. */
export function MapView({ snapshot, markers, selected, focusTarget, onRegionClick, onHover, onReady }: Props) {
  const glRef = useRef<HTMLCanvasElement>(null);
  const ovRef = useRef<HTMLCanvasElement>(null);
  const mapRef = useRef<MapRenderer | null>(null);
  const clickRef = useRef(onRegionClick);
  const hoverRef = useRef(onHover);
  clickRef.current = onRegionClick;
  hoverRef.current = onHover;
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    createMapRenderer({ canvas: glRef.current!, overlay: ovRef.current!, dataUrl: "/data" })
      .then((m) => {
        if (cancelled) return m.destroy();
        mapRef.current = m;
        m.on("click", (id) => clickRef.current(id));
        m.on("hover", (id) => hoverRef.current(id));
        onReady(new Map(m.world.regions.map((r) => [r.id, r.name])));
        setReady(true);
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      cancelled = true;
      mapRef.current?.destroy();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const m = mapRef.current;
    if (!m || !snapshot) return;
    m.setFactions([...snapshot.factions, snapshot.praga]);
    m.setState({ owner: snapshot.owner, plague: snapshot.plague });
  }, [snapshot, ready]);

  useEffect(() => { mapRef.current?.setMarkers(markers); }, [markers, ready]);
  useEffect(() => { mapRef.current?.setSelected(selected); }, [selected, ready]);
  useEffect(() => { if (focusTarget) mapRef.current?.focusOn(focusTarget, 3); }, [focusTarget]);

  return (
    <div className="map">
      <canvas ref={glRef} className="map-gl" />
      <canvas ref={ovRef} className="map-ov" />
      {error && <div className="map-error">O mapa não carregou: {error}</div>}
    </div>
  );
}
