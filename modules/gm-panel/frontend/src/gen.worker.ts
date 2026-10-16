// Pré-visualização de um mundo novo: o gerador do Province-Forge corre aqui, fora da linha principal
// (demora 5–20 s conforme o número de reinos).
import { generateMap } from "@pf/gen/generate";
import { DEFAULT_PARAMS, type GenParams } from "@pf/gen/types";

self.onmessage = (e: MessageEvent<{ id: number; params: Partial<GenParams> }>) => {
  const t0 = performance.now();
  try {
    const map = generateMap({ ...DEFAULT_PARAMS, ...e.data.params, continentSizes: [...(e.data.params.continentSizes ?? DEFAULT_PARAMS.continentSizes)] as [number, number, number] });
    // findCell é uma função (não passa para a linha principal); a pré-visualização não precisa dela
    const { findCell: _drop, ...plain } = map;
    void _drop;
    (self as unknown as Worker).postMessage({ id: e.data.id, map: plain, ms: Math.round(performance.now() - t0) });
  } catch (err) {
    (self as unknown as Worker).postMessage({ id: e.data.id, error: (err as Error).message });
  }
};
