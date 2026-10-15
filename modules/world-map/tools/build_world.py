"""Importador Azgaar -> mundo de jogo "Praga".

Lê o Full JSON do Azgaar e produz, em web/data/:
  world.json   - fações, regiões jogáveis (províncias + ermos), vizinhanças, rios, estradas, burgos
  base.jpg     - camada base "pintada" (relevo sombreado, biomas, oceano, costa), gerada de forma determinística
  regions.png  - raster de IDs de região (R = id & 255, G = id >> 8; 0 = água), usado pelo shader do mapa

Uso: python tools/build_world.py build/praga/world_full.json web/data
"""
import json
import math
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import cKDTree

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
SCALE = 2          # pixels de raster por unidade do mundo
SEA_LEVEL = 20     # convenção do Azgaar
RNG = np.random.default_rng(7)  # determinístico: o mesmo mapa gera sempre a mesma imagem

d = json.loads(SRC.read_text())
pack = d["pack"]
cells = pack["cells"]
W, H = d["info"]["width"], d["info"]["height"]
RW, RH = W * SCALE, H * SCALE
print(f"mundo {W}x{H}, raster {RW}x{RH}, células {len(cells)}")

pts = np.array([c["p"] for c in cells], dtype=np.float64)
heights = np.array([c["h"] for c in cells], dtype=np.float64)
biome = np.array([c["biome"] for c in cells], dtype=np.int32)
land = heights >= SEA_LEVEL
lake_features = {f["i"] for f in pack["features"][1:] if isinstance(f, dict) and f.get("type") == "lake"}
is_lake = np.array([c["f"] in lake_features for c in cells])

# ---------------------------------------------------------------------------
# 1. Regiões de jogo: províncias do Azgaar + "ermos" (terra neutra sem província)
# ---------------------------------------------------------------------------
region_of_cell = np.zeros(len(cells), dtype=np.int32)  # 0 = água
regions = []
prov_to_region = {}
for prov in pack["provinces"][1:]:
    if not isinstance(prov, dict) or prov.get("removed"):
        continue
    rid = len(regions) + 1
    prov_to_region[prov["i"]] = rid
    regions.append({"id": rid, "kind": "province", "name": prov["name"], "fullName": prov.get("fullName", prov["name"]),
                    "owner": prov["state"], "cells": []})

for i, c in enumerate(cells):
    if land[i] and c["province"] in prov_to_region:
        region_of_cell[i] = prov_to_region[c["province"]]

# Terra sem província -> componentes ligadas viram ermos (bom ponto de origem para a Praga)
orphan = [i for i in range(len(cells)) if land[i] and region_of_cell[i] == 0]
seen = set()
wild_count = 0
for start in orphan:
    if start in seen:
        continue
    comp, q = [], deque([start])
    seen.add(start)
    while q:
        u = q.popleft()
        comp.append(u)
        for v in cells[u]["c"]:
            if land[v] and region_of_cell[v] == 0 and v not in seen:
                seen.add(v)
                q.append(v)
    if len(comp) < 3:
        # fragmentos minúsculos: juntar à região vizinha mais comum
        nb = [region_of_cell[v] for u in comp for v in cells[u]["c"] if region_of_cell[v] > 0]
        if nb:
            target = max(set(nb), key=nb.count)
            for u in comp:
                region_of_cell[u] = target
            continue
    rid = len(regions) + 1
    wild_count += 1
    regions.append({"id": rid, "kind": "wild", "name": f"Ermos {wild_count}", "fullName": f"Ermos {wild_count}",
                    "owner": 0, "cells": []})
    for u in comp:
        region_of_cell[u] = rid

for i in range(len(cells)):
    if region_of_cell[i] > 0:
        regions[region_of_cell[i] - 1]["cells"].append(i)

# Métricas e vizinhança
nbrs = defaultdict(set)
coastal = defaultdict(bool)
for i, c in enumerate(cells):
    a = region_of_cell[i]
    if a == 0:
        continue
    for j in c["c"]:
        b = region_of_cell[j]
        if b == 0:
            if not is_lake[j]:
                coastal[a] = True
        elif b != a:
            nbrs[a].add(int(b))

biome_names = {b["i"]: b["name"] for b in pack["biomes"]}
for r in regions:
    idx = np.array(r["cells"])
    area = np.array([cells[i]["area"] for i in idx], dtype=float)
    r["area"] = int(area.sum())
    r["center"] = [round(float(np.average(pts[idx, 0], weights=area)), 1), round(float(np.average(pts[idx, 1], weights=area)), 1)]
    # centro "dentro" da região: a célula mais próxima do centróide
    k = idx[np.argmin(((pts[idx] - r["center"]) ** 2).sum(1))]
    r["center"] = [round(float(pts[k, 0]), 1), round(float(pts[k, 1]), 1)]
    r["elevation"] = int(round(float(np.average(heights[idx], weights=area))))
    bc = np.bincount(biome[idx], weights=area, minlength=13)
    r["biome"] = biome_names[int(bc.argmax())]
    r["coastal"] = bool(coastal[r["id"]])
    r["neighbors"] = sorted(nbrs[r["id"]])
    r["population"] = round(sum(cells[i]["pop"] for i in idx), 1)
    del r["cells"]

# Validação: grafo de vizinhança simétrico, sem regiões órfãs
for r in regions:
    for n in r["neighbors"]:
        assert r["id"] in regions[n - 1]["neighbors"], f"vizinhança assimétrica {r['id']}-{n}"
isolated = [r["id"] for r in regions if not r["neighbors"] and not r["coastal"]]
print(f"regiões: {len(regions)} ({len(regions) - wild_count} províncias, {wild_count} ermos); isoladas sem costa: {isolated}")

# ---------------------------------------------------------------------------
# 2. Fações (estados do Azgaar; 0 = Neutros)
# ---------------------------------------------------------------------------
factions = []
for s in pack["states"]:
    if s.get("removed"):
        continue
    factions.append({"id": s["i"], "name": s["name"] if s["i"] else "Terras Livres",
                     "fullName": s.get("fullName", s["name"]), "color": s.get("color", "#888888") if s["i"] else "#9a9488"})

# ---------------------------------------------------------------------------
# 3. Rios, estradas e burgos (vetoriais, desenhados pelo cliente)
# ---------------------------------------------------------------------------
rivers = []
for rv in pack["rivers"]:
    if not rv or len(rv.get("cells", [])) < 3:
        continue
    pl = [pts[ci].round(1).tolist() for ci in rv["cells"] if 0 <= ci < len(cells)]
    rivers.append({"name": rv["name"], "w": round(min(4.0, 0.6 + math.sqrt(rv.get("discharge", 1)) / 18), 2), "pts": pl})

roads = [[[round(p[0], 1), round(p[1], 1)] for p in rt["points"]] for rt in pack["routes"] if rt.get("group") == "roads"]

burgs = []
for b in pack["burgs"][1:]:
    if not b or b.get("removed"):
        continue
    burgs.append({"name": b["name"], "x": round(b["x"], 1), "y": round(b["y"], 1), "pop": round(b.get("population", 0), 1),
                  "capital": bool(b.get("capital")), "port": bool(b.get("port")),
                  "region": int(region_of_cell[b["cell"]])})
burgs.sort(key=lambda b: (-b["capital"], -b["pop"]))
burgs = burgs[:220]

world = {"name": d["info"]["mapName"], "seed": d["info"]["seed"], "width": W, "height": H, "rasterScale": SCALE,
         "factions": factions, "regions": regions, "rivers": rivers, "roads": roads, "burgs": burgs}
(OUT / "world.json").write_text(json.dumps(world, ensure_ascii=False, separators=(",", ":")))

# ---------------------------------------------------------------------------
# 4. Rasters: campo de altura suave, máscara de terra, IDs de região
# ---------------------------------------------------------------------------
def fbm(shape, octaves=5, base=8, seed=0):
    """Ruído fractal suave (determinístico)."""
    g = np.random.default_rng(seed)
    out = np.zeros(shape, dtype=np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        n = base * 2 ** o
        grid = g.random((max(2, int(shape[0] / shape[1] * n) + 2), n + 2)).astype(np.float32)
        z = ndimage.zoom(grid, (shape[0] / grid.shape[0], shape[1] / grid.shape[1]), order=3)[: shape[0], : shape[1]]
        out += amp * z
        total += amp
        amp *= 0.5
    return out / total

yy, xx = np.mgrid[0:RH, 0:RW].astype(np.float32)
wx, wy = (xx + 0.5) / SCALE, (yy + 0.5) / SCALE  # coordenadas do mundo

# altura interpolada (linear sobre a triangulação das células) + suavização
interp = LinearNDInterpolator(pts, heights, fill_value=0.0)
hf = interp(wx.ravel(), wy.ravel()).reshape(RH, RW).astype(np.float32)
hf = ndimage.gaussian_filter(hf, 2.5 * SCALE)
# ligeira irregularidade para a costa não parecer "matemática"
hf += (fbm((RH, RW), 4, 12, seed=11) - 0.5) * 3.0
land_mask = hf >= SEA_LEVEL - 0.5

# lagos: píxeis cuja célula mais próxima é lago passam a água
tree_all = cKDTree(pts)
_, nearest_all = tree_all.query(np.column_stack([wx.ravel(), wy.ravel()]), workers=-1)
nearest_all = nearest_all.reshape(RH, RW)
lake_px = is_lake[nearest_all]
lake_px = ndimage.binary_opening(lake_px, iterations=2)
land_mask &= ~lake_px

# IDs de região: célula de terra mais próxima, com coordenadas "deformadas" por ruído
# -> fronteiras orgânicas em vez de arestas retas de Voronoi
land_idx = np.where(land)[0]
tree_land = cKDTree(pts[land_idx])
warp = 3.2
ox = (fbm((RH, RW), 4, 10, seed=21) - 0.5) * 2 * warp
oy = (fbm((RH, RW), 4, 10, seed=22) - 0.5) * 2 * warp
_, nl = tree_land.query(np.column_stack([(wx + ox).ravel(), (wy + oy).ravel()]), workers=-1)
rid_px = region_of_cell[land_idx[nl]].reshape(RH, RW)
rid_px[~land_mask] = 0
rgba = np.zeros((RH, RW, 4), dtype=np.uint8)
rgba[..., 0] = rid_px & 255
rgba[..., 1] = rid_px >> 8
rgba[..., 3] = 255
Image.fromarray(rgba, "RGBA").save(OUT / "regions.png", optimize=True)
print("regions.png ok")

# ---------------------------------------------------------------------------
# 5. Base pintada
# ---------------------------------------------------------------------------
def hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32) / 255

# Paleta "atlas antigo" (própria, não a do Azgaar)
BIOME_RGB = np.array([hex2rgb(c) for c in [
    "#6f97a3",  # 0 marine (não usado em terra)
    "#dcc597",  # 1 deserto quente
    "#cbc2a6",  # 2 deserto frio
    "#cdc387",  # 3 savana
    "#b1bb7a",  # 4 pradaria
    "#93a86a",  # 5 floresta tropical sazonal
    "#86a062",  # 6 floresta temperada
    "#6b8c58",  # 7 floresta tropical húmida
    "#74916a",  # 8 floresta temperada húmida
    "#7d8f6e",  # 9 taiga
    "#b2b4a0",  # 10 tundra
    "#eef0ec",  # 11 glaciar
    "#8a9a7c",  # 12 pântano
]])
FOREST = np.zeros(13, dtype=np.float32)
FOREST[[5, 6, 7, 8, 9]] = [0.6, 0.8, 1.0, 0.9, 0.8]

# cor de bioma por píxel (célula mais próxima), depois desfocada para transições suaves
bio_px = biome[nearest_all]
col = BIOME_RGB[bio_px]
col = np.stack([ndimage.gaussian_filter(col[..., k], 3.0 * SCALE) for k in range(3)], -1)
forest = ndimage.gaussian_filter(FOREST[bio_px], 2.0 * SCALE)

# elevação de terra 0..1 e relevo sombreado (luz de noroeste)
elev = np.clip((hf - SEA_LEVEL) / (80 - SEA_LEVEL), 0, 1)
relief = ndimage.gaussian_filter(np.where(land_mask, hf, SEA_LEVEL), 1.2 * SCALE)
ridge = 1 - np.abs(fbm((RH, RW), 5, 18, seed=31) * 2 - 1)  # cristas
relief += ridge * 7.0 * elev ** 1.3  # micro-relevo só onde já há altitude
gy, gx = np.gradient(relief)
zf = 0.6 * SCALE
nx, ny, nz = -gx * zf, -gy * zf, np.ones_like(gx)
nlen = np.sqrt(nx * nx + ny * ny + nz * nz)
lx, ly, lz = -0.6, -0.6, 0.53
shade = (nx * lx + ny * ly + nz * lz) / nlen
shade = np.clip(shade / lz, 0.5, 1.3)
# planícies quase planas, montanhas com sombra forte
shade = 1 + (shade - 1) * (0.25 + 0.75 * np.clip(elev * 1.6, 0, 1))

landc = col.copy()
# floresta: textura pontilhada escura (como gravura)
stip = fbm((RH, RW), 2, 220, seed=41)
landc *= (1 - forest[..., None] * (0.10 + 0.10 * (stip[..., None] > 0.55)))
# montanhas: dessaturar e clarear com altitude; neve no topo
grey = landc.mean(-1, keepdims=True)
t = np.clip((elev - 0.35) / 0.5, 0, 1)[..., None]
landc = landc * (1 - t * 0.55) + (grey * 0.9 + 0.12) * t * 0.55
snow = np.clip((elev - 0.78) / 0.12, 0, 1)[..., None]
landc = landc * (1 - snow) + hex2rgb("#f4f2ec") * snow
landc *= shade[..., None] ** 0.9
lg = landc.mean(-1, keepdims=True)
landc = landc * 0.82 + lg * 0.18

# oceano: profundidade + linhas de costa concêntricas (estilo cartografia clássica)
dist_sea = ndimage.distance_transform_edt(~land_mask) / SCALE  # distância à costa em unidades do mundo
deep, shallow = hex2rgb("#2f4b5c"), hex2rgb("#7aa2ab")
depth = np.clip(dist_sea / 28.0, 0, 1) ** 0.8
seac = shallow * (1 - depth[..., None]) + deep * depth[..., None]
seac *= (0.94 + 0.12 * fbm((RH, RW), 5, 6, seed=51))[..., None]
for k, dd in enumerate([4.0, 8.5, 14.0, 21.0]):
    ring = np.exp(-((dist_sea - dd) ** 2) / (2 * (0.45 + 0.08 * k) ** 2))
    seac = seac * (1 - ring[..., None] * (0.20 - k * 0.04)) + hex2rgb("#2a4350") * ring[..., None] * (0.20 - k * 0.04)
lakec = hex2rgb("#86b0b5")
seac = np.where(lake_px[..., None], lakec * (0.95 + 0.05 * shade[..., None]), seac)

img = np.where(land_mask[..., None], landc, seac)

# linha de costa a tinta + halo claro do lado de terra
dist_land = ndimage.distance_transform_edt(land_mask) / SCALE
dist_coast = dist_sea + dist_land  # um dos dois é sempre 0
ink = np.exp(-(dist_coast ** 2) / (2 * 0.38 ** 2))
img = img * (1 - ink[..., None] * 0.85) + hex2rgb("#2b2620") * ink[..., None] * 0.85
glow = np.exp(-(dist_land ** 2) / (2 * 2.2 ** 2)) * land_mask
img = img * (1 - glow[..., None] * 0.18) + hex2rgb("#f3e9cf") * glow[..., None] * 0.18

# papel: grão + manchas + vinheta
paper = fbm((RH, RW), 6, 4, seed=61)
grain = RNG.normal(0, 1, (RH, RW)).astype(np.float32)
grain = ndimage.gaussian_filter(grain, 0.6)
img *= (0.90 + 0.14 * paper)[..., None]
img += grain[..., None] * 0.012
img = img * 0.93 + hex2rgb("#efe2c4") * 0.07  # tom sépia geral
vy, vx = (yy / RH - 0.5), (xx / RW - 0.5)
vig = 1 - 0.35 * (vx * vx + vy * vy) ** 1.2 * 2.2
img *= vig[..., None]

img = (np.clip(img, 0, 1) * 255).astype(np.uint8)
Image.fromarray(img, "RGB").save(OUT / "base.jpg", quality=90, optimize=True, progressive=True)
print("base.jpg ok")
for f in ["world.json", "base.jpg", "regions.png"]:
    print(f, round((OUT / f).stat().st_size / 1024), "KB")
