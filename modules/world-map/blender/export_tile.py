"""Prova Blender, passo 1: exporta um recorte do mundo para o Blender renderizar.

Uso (a partir de modules/world-map):
    python blender/export_tile.py build/exemplo/world_full.json build/exemplo/data build/blender-prova
    python blender/export_tile.py ... --bbox 900 300 360      # x0 y0 lado, em unidades do mundo (opcional)

Sem --bbox, escolhe sozinho uma janela com costa, montanha e floresta.
Escreve em <saída>/:
  height.npy, height.png   altura (0 = nível do mar; >0 terra), já com detalhe: vales dos rios e cristas
  color.png                cor de bioma (a mesma paleta da base atual)
  forest.npy, forest.png   densidade de floresta 0..1
  sea.npy, sea.png         profundidade relativa do mar 0..1 (0 na costa)
  burgs.json               povoações dentro do recorte (posição em píxeis, população, capital)
  atual.png                o mesmo recorte da base atual (base.jpg), ampliado, para comparar
  meta.json                janela, resolução e escala
A linha de costa vem do regions.png (a mesma que as fronteiras usam), para o render encaixar no mapa.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.interpolate import LinearNDInterpolator

SEA_LEVEL = 20
# paleta da base atual (tools/build_world.py) — repetida aqui de propósito: o build_world é um script, não um módulo
BIOME_RGB = np.array([[int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)] for c in [
    "#6f97a3", "#dcc597", "#cbc2a6", "#cdc387", "#b1bb7a", "#93a86a", "#86a062", "#6b8c58", "#74916a",
    "#7d8f6e", "#b2b4a0", "#eef0ec", "#8a9a7c"]], dtype=np.float32)
FOREST = np.zeros(13, dtype=np.float32)
FOREST[[5, 6, 7, 8, 9]] = [0.6, 0.8, 1.0, 0.9, 0.8]


def fbm(shape, octaves, base, seed, ridged=False):
    g = np.random.default_rng(seed)
    out = np.zeros(shape, np.float32)
    amp = tot = 0.0
    amp = 1.0
    for o in range(octaves):
        n = base * 2 ** o
        grid = g.random((n + 3, n + 3)).astype(np.float32)
        z = ndimage.zoom(grid, (shape[0] / (n + 3), shape[1] / (n + 3)), order=3)[: shape[0], : shape[1]]
        if ridged:
            z = 1 - np.abs(z * 2 - 1)
        out += amp * z
        tot += amp
        amp *= 0.5
    return out / tot


def pick_window(cells, size, W, H, land_raster, scale):
    """Janela sobretudo de terra, com costa, montanha e floresta: a variedade é o que a prova tem de mostrar."""
    pts = np.array([c["p"] for c in cells])
    h = np.array([c["h"] for c in cells])
    bio = np.array([c["biome"] for c in cells])
    best, best_s = None, -1
    for y0 in np.arange(0, H - size + 1, size / 4):
        for x0 in np.arange(0, W - size + 1, size / 4):
            m = (pts[:, 0] >= x0) & (pts[:, 0] < x0 + size) & (pts[:, 1] >= y0) & (pts[:, 1] < y0 + size)
            if m.sum() < 50:
                continue
            land = h[m] >= SEA_LEVEL
            r = land_raster[int(y0 * scale):int((y0 + size) * scale):4, int(x0 * scale):int((x0 + size) * scale):4]
            lf = r.mean()
            mount = (h[m] >= 50).mean()
            forest = FOREST[bio[m]][land].mean() if land.any() else 0
            s = min(1 - abs(lf - 0.65) * 2.5, mount * 6, forest * 2, 1.0)   # sobretudo terra, com costa
            if s > best_s:
                best, best_s = (float(x0), float(y0)), s
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("full_json")
    ap.add_argument("data_dir", help="pasta com regions.png e base.jpg (saída do build_world.py)")
    ap.add_argument("out")
    ap.add_argument("--bbox", nargs=3, type=float, metavar=("X0", "Y0", "LADO"))
    ap.add_argument("--px", type=int, default=2048)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    d = json.loads(Path(args.full_json).read_text())
    cells = d["pack"]["cells"]
    W, H = d["info"]["width"], d["info"]["height"]
    reg = np.asarray(Image.open(Path(args.data_dir) / "regions.png"))
    scale = json.loads((Path(args.data_dir) / "world.json").read_text())["rasterScale"]
    land_all = (reg[..., 0].astype(int) + reg[..., 1]) > 0
    if args.bbox:
        x0, y0, size = args.bbox
    else:
        size = 360.0
        x0, y0 = pick_window(cells, size, W, H, land_all, scale)
    px = args.px
    k = px / size                                   # píxeis por unidade do mundo
    print(f"janela x={x0:.0f} y={y0:.0f} lado={size:.0f} → {px}×{px} px ({k:.1f} px por unidade)")

    yy, xx = np.mgrid[0:px, 0:px].astype(np.float32)
    wx, wy = x0 + (xx + 0.5) / k, y0 + (yy + 0.5) / k

    # células perto da janela
    pts = np.array([c["p"] for c in cells], dtype=np.float64)
    near = ((pts[:, 0] > x0 - 40) & (pts[:, 0] < x0 + size + 40) & (pts[:, 1] > y0 - 40) & (pts[:, 1] < y0 + size + 40))
    idx = np.where(near)[0]
    hval = np.array([cells[i]["h"] for i in idx], dtype=np.float64)
    bio = np.array([cells[i]["biome"] for i in idx], dtype=np.int32)

    # --- terra/mar: a costa do regions.png (2 px por unidade), suavizada para a resolução nova
    rx0, ry0, rs = int(x0 * scale), int(y0 * scale), int(size * scale)
    land_r = ((reg[ry0:ry0 + rs, rx0:rx0 + rs, 0].astype(int) + reg[ry0:ry0 + rs, rx0:rx0 + rs, 1]) > 0).astype(np.float32)
    land_f = ndimage.zoom(land_r, px / rs, order=1)[:px, :px]
    land_f = ndimage.gaussian_filter(land_f, k / scale * 0.5)
    land = land_f >= 0.5

    # --- altura: interpolação das células + detalhe
    interp = LinearNDInterpolator(pts[idx], hval, fill_value=0.0)
    h = interp(wx.ravel(), wy.ravel()).reshape(px, px).astype(np.float32)
    h = ndimage.gaussian_filter(h, k * 3)
    elev = np.clip((h - SEA_LEVEL) / (80 - SEA_LEVEL), 0, 1)              # 0 na costa, 1 nos picos
    # cristas: ruído "ridged" com mais força onde já é montanha, mais fino perto do pico
    ridges = fbm((px, px), 6, 6, seed=101, ridged=True)
    detail = fbm((px, px), 5, 24, seed=102)
    elev = elev + (ridges - 0.55) * 0.55 * elev ** 1.4 + (detail - 0.5) * 0.06 * (0.3 + elev)
    # vales dos rios (rios do Azgaar): cavam mais nas zonas altas, abrem-se com o caudal
    riv = np.zeros((px, px), np.float32)
    from PIL import ImageDraw
    canvas = Image.new("F", (px, px), 0.0)
    dr = ImageDraw.Draw(canvas)
    for rv in d["pack"]["rivers"]:
        if not rv or len(rv.get("cells", [])) < 3:
            continue
        line = [((pts[c][0] - x0) * k, (pts[c][1] - y0) * k) for c in rv["cells"] if 0 <= c < len(pts)]
        if not any(0 <= x < px and 0 <= y < px for x, y in line):
            continue
        w = max(1.0, min(6.0, (rv.get("discharge", 1) ** 0.5) / 6))
        dr.line(line, fill=float(w), width=max(2, int(w * k / 3)))
    riv = np.asarray(canvas, dtype=np.float32)
    valley = ndimage.gaussian_filter(riv, k * 4.0)
    valley /= max(valley.max(), 1e-6)
    elev = elev - np.sqrt(valley) * (0.03 + 0.25 * elev)
    elev = np.clip(elev, 0.004, None)
    # perto da costa, a terra desce suave até ao mar (praias, não falésias por todo o lado)
    dist_land = ndimage.distance_transform_edt(land) / k
    elev = elev * np.clip(dist_land / 6.0, 0.15, 1.0)
    height = np.where(land, elev, 0.0).astype(np.float32)
    # mar: profundidade relativa pela distância à costa
    dist_sea = ndimage.distance_transform_edt(~land) / k
    sea = np.where(land, 0.0, np.clip(dist_sea / 30.0, 0, 1)).astype(np.float32)

    # --- cor de bioma e floresta (célula mais próxima, suavizado)
    from scipy.spatial import cKDTree
    _, nn = cKDTree(pts[idx]).query(np.column_stack([wx.ravel(), wy.ravel()]), workers=-1)
    b = bio[nn].reshape(px, px)
    col = BIOME_RGB[b]
    col = np.stack([ndimage.gaussian_filter(col[..., i], k * 2) for i in range(3)], -1)
    forest = ndimage.gaussian_filter(FOREST[b], k * 1.5)
    forest *= land * np.clip(1 - (elev - 0.55) / 0.2, 0, 1)                    # sem árvores nos picos
    forest *= fbm((px, px), 4, 10, seed=103) * 1.4                              # clareiras
    forest = np.clip(forest, 0, 1).astype(np.float32)

    # --- povoações
    burgs = []
    for bg in d["pack"]["burgs"][1:]:
        if not bg or bg.get("removed"):
            continue
        bx, by = (bg["x"] - x0) * k, (bg["y"] - y0) * k
        if 0 <= bx < px and 0 <= by < px and land[int(by), int(bx)]:
            burgs.append({"x": round(bx, 1), "y": round(by, 1), "pop": round(bg.get("population", 0), 2),
                          "capital": bool(bg.get("capital")), "name": bg["name"]})

    # --- recorte da base atual, para comparar
    base = Image.open(Path(args.data_dir) / "base.jpg")
    atual = base.crop((rx0, ry0, rx0 + rs, ry0 + rs)).resize((px, px), Image.LANCZOS)

    np.save(out / "height.npy", height)
    np.save(out / "forest.npy", forest)
    np.save(out / "sea.npy", sea)
    Image.fromarray((np.clip(height / max(height.max(), 1e-6), 0, 1) * 65535).astype(np.uint16)).save(out / "height.png")
    Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8)).save(out / "color.png")
    Image.fromarray((forest * 255).astype(np.uint8)).save(out / "forest.png")
    Image.fromarray((sea * 255).astype(np.uint8)).save(out / "sea.png")
    atual.save(out / "atual.png")
    (out / "burgs.json").write_text(json.dumps(burgs, ensure_ascii=False, indent=1))
    (out / "meta.json").write_text(json.dumps({"x0": x0, "y0": y0, "size": size, "px": px,
                                               "px_per_unit": k, "source": args.full_json}, indent=1))
    print(f"terra {land.mean():.0%} · floresta {forest[land].mean() if land.any() else 0:.0%} · "
          f"{len(burgs)} povoações · guardado em {out}")


if __name__ == "__main__":
    main()
