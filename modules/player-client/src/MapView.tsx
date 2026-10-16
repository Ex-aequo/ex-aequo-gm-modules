import { useEffect, useRef, useState } from "react";
import { createMapRenderer, type MapMarker, type MapPath, type MapRenderer } from "@map-renderer";

interface Props {
  owner: number[];
  plague: number[];
  fog: number[];
  factions: { id: number; name: string; color: string }[];
  markers: MapMarker[];
  paths: MapPath[];
  selected: number;
  home: number;
  camera: React.MutableRefObject<{ x: number; y: number; zoom: number } | null>;
  onClick: (id: number) => void;
  onHover: (id: number) => void;
  onReady: (names: Map<number, string>) => void;
}

/** O mapa partilhado (map-renderer), com os ficheiros do mapa filtrados pelo servidor para este jogador. */
export function MapView(p: Props) {
  const glRef = useRef<HTMLCanvasElement>(null);
  const ovRef = useRef<HTMLCanvasElement>(null);
  const mapRef = useRef<MapRenderer | null>(null);
  const cb = useRef(p);
  cb.current = p;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    createMapRenderer({ canvas: glRef.current!, overlay: ovRef.current!, dataUrl: "/api/map" })
      .then((m) => {
        if (cancelled) return m.destroy();
        mapRef.current = m;
        m.on("click", (id) => cb.current.onClick(id));
        m.on("hover", (id) => cb.current.onHover(id));
        cb.current.onReady(new Map(m.world.regions.filter((r) => r.name).map((r) => [r.id, r.name])));
        if (cb.current.camera.current) m.setCamera(cb.current.camera.current);
        else if (cb.current.home) m.focusOn(cb.current.home, 2.2);
        setReady(true);
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      cancelled = true;
      if (mapRef.current) cb.current.camera.current = { ...mapRef.current.camera };
      mapRef.current?.destroy();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const m = mapRef.current;
    if (!m) return;
    m.setFactions(p.factions);
    m.setState({ owner: p.owner, plague: p.plague, fog: p.fog });
  }, [p.owner, p.plague, p.fog, p.factions, ready]);
  useEffect(() => { mapRef.current?.setMarkers(p.markers); }, [p.markers, ready]);
  useEffect(() => { mapRef.current?.setPaths(p.paths); }, [p.paths, ready]);
  useEffect(() => { mapRef.current?.setSelected(p.selected); }, [p.selected, ready]);

  return (
    <div className="map">
      <canvas ref={glRef} className="map-gl" />
      <canvas ref={ovRef} className="map-ov" />
      {error && <div className="map-error">O mapa não carregou: {error}</div>}
    </div>
  );
}
