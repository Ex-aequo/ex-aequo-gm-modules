declare module "@map-renderer" {
  export const PRAGA: number;
  export interface MapMarker {
    region: number;
    kind: "suggestion" | "pending" | "focus" | "army" | "foe" | "agent" | "target";
    label?: string;
    selected?: boolean;
  }
  export interface MapPath {
    regions: number[];
    kind: "move" | "attack" | "agent";
  }
  export interface MapRenderer {
    world: { name: string; regions: { id: number; name: string; fullName: string; center: [number, number] }[] };
    camera: { x: number; y: number; zoom: number };
    regionAt(wx: number, wy: number): number;
    fit(): void;
    focusOn(regionId: number, zoom?: number): void;
    setCamera(cam: { x: number; y: number; zoom: number }): void;
    setFactions(list: { id: number; name: string; color: string }[]): void;
    setState(state: { owner?: ArrayLike<number>; plague?: ArrayLike<number>; fog?: ArrayLike<number> | null }): void;
    setOptions(opts: Partial<{ borders: boolean; plague: boolean; rivers: boolean; labels: boolean }>): void;
    setSelected(id: number): void;
    setMarkers(list: MapMarker[]): void;
    setPaths(list: MapPath[]): void;
    on(evt: "click" | "hover", fn: (regionId: number) => void): () => void;
    destroy(): void;
  }
  export function createMapRenderer(opts: {
    canvas: HTMLCanvasElement;
    overlay: HTMLCanvasElement;
    dataUrl?: string;
    animate?: boolean;
  }): Promise<MapRenderer>;
}
