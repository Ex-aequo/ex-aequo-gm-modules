"""Prova Blender: exporta um só recorte do mundo (o mesmo caminho dos tiles, mas uma janela à escolha).

Uso (a partir de modules/world-map):
    python blender/export_tile.py build/exemplo/world_full.json build/exemplo/data build/blender-prova
    python blender/export_tile.py ... --bbox 900 300 360      # x0 y0 lado, em unidades do mundo (opcional)
Sem --bbox, escolhe sozinho uma janela sobretudo de terra, com costa, montanha e floresta.
Na primeira vez calcula o relevo do mundo inteiro (~2 min) e guarda-o em <saída>/world_q.npz.
Escreve os dados para o render_tile.py e atual.png (o mesmo recorte da base atual, para comparar).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from worldlib import FOREST, K, World, save_tile_inputs  # noqa: E402


def pick_window(world: World, size: float):
    """Janela sobretudo de terra (≈65 %), com montanha e floresta: a variedade é o que a prova tem de mostrar."""
    h = np.array([c["h"] for c in world.cells])
    bio = np.array([c["biome"] for c in world.cells])
    best, best_s = None, -1
    for y0 in np.arange(0, world.H - size + 1, size / 4):
        for x0 in np.arange(0, world.W - size + 1, size / 4):
            m = ((world.pts[:, 0] >= x0) & (world.pts[:, 0] < x0 + size) &
                 (world.pts[:, 1] >= y0) & (world.pts[:, 1] < y0 + size))
            if m.sum() < 50:
                continue
            r = world.land_r[int(y0 * world.scale):int((y0 + size) * world.scale):4,
                             int(x0 * world.scale):int((x0 + size) * world.scale):4]
            lf = r.mean()
            land = h[m] >= 20
            s = min(1 - abs(lf - 0.65) * 2.5, (h[m] >= 50).mean() * 6,
                    FOREST[bio[m]][land].mean() * 2 if land.any() else 0, 1.0)
            if s > best_s:
                best, best_s = (float(x0), float(y0)), s
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("full_json")
    ap.add_argument("data_dir")
    ap.add_argument("out")
    ap.add_argument("--bbox", nargs=3, type=float, metavar=("X0", "Y0", "LADO"))
    args = ap.parse_args()
    out = Path(args.out)
    world = World(Path(args.full_json), Path(args.data_dir), out / "world_q.npz")
    if args.bbox:
        x0, y0, size = args.bbox
    else:
        size = 360.0
        x0, y0 = pick_window(world, size)
    inner = int(round(size * K))
    t = world.window_inputs(int(round(x0 * K)), int(round(y0 * K)), inner)
    save_tile_inputs(t, out)
    import json
    meta = json.loads((out / "meta.json").read_text())
    meta["hmax"] = float(world.relief_q.max())
    (out / "meta.json").write_text(json.dumps(meta))
    s = world.scale
    base = Image.open(Path(args.data_dir) / "base.jpg")
    base.crop((int(x0 * s), int(y0 * s), int((x0 + size) * s), int((y0 + size) * s))).resize(
        (inner, inner), Image.LANCZOS).save(out / "atual.png")
    print(f"janela x={x0:.0f} y={y0:.0f} lado={size:.0f} → {inner}×{inner} px · {len(t['trees'])} árvores · "
          f"{len(t['houses'])} casas · guardado em {out}")


if __name__ == "__main__":
    main()
