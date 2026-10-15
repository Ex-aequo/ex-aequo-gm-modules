"""Base do mapa em tiles: dados do mundo inteiro, sem costuras.

Tudo o que atravessa tiles é calculado uma vez para o mundo (a 1/4 da resolução final) ou por coordenadas do mundo
(ruído e árvores com hash), por isso dois tiles vizinhos dão exatamente o mesmo resultado na junção:
  - relevo erodido (erosion.py), profundidade do mar, cor de bioma, densidade de floresta: globais, a 1/4
  - detalhe fino do relevo, clareiras, árvores: funções das coordenadas do mundo
  - casas: semente fixa por povoação
Cada tile é exportado com margem (PAD); o render usa a margem para sombras e corta-a.

Resolução: K píxeis por unidade do mundo (16/3 ≈ 5,3; o mundo de 1920 × 1080 dá 10240 × 5760 px).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import cKDTree

K = 16 / 3                 # píxeis por unidade do mundo, no nível de mais detalhe
TILE = 1024                # píxeis por tile de render
PAD = 128                  # margem de cada lado (sombras e erosão)
Q = 4                      # o relevo global é calculado a 1/Q da resolução
RELIEF = 40.0              # altura 1 = 40 unidades do mundo no Blender
SEA_LEVEL = 20

BIOME_RGB = np.array([[int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)] for c in [
    "#6f97a3", "#dcc597", "#cbc2a6", "#cdc387", "#b1bb7a", "#93a86a", "#86a062", "#6b8c58", "#74916a",
    "#7d8f6e", "#b2b4a0", "#eef0ec", "#8a9a7c"]], dtype=np.float32)
FOREST = np.zeros(13, dtype=np.float32)
FOREST[[5, 6, 7, 8, 9]] = [0.6, 0.8, 1.0, 0.9, 0.8]


# --------------------------------------------------------------------------- ruído por coordenadas do mundo
def _hash(ix, iy, seed):
    """Hash inteiro determinístico → [0, 1). Mesmo ponto do mundo, mesmo valor, em qualquer tile."""
    h = (ix.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)) ^ (iy.astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F))
    h ^= np.uint64(seed * 0x165667B19E3779F9 & 0xFFFFFFFFFFFFFFFF)
    h ^= h >> np.uint64(33)
    h *= np.uint64(0xFF51AFD7ED558CCD)
    h ^= h >> np.uint64(33)
    return (h >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def perlin_world(x, y, cell, seed):
    """Perlin 2D com gradientes por hash: x, y em unidades do mundo; cell = tamanho da célula em unidades."""
    fx, fy = x / cell, y / cell
    x0, y0 = np.floor(fx).astype(np.int64), np.floor(fy).astype(np.int64)
    tx, ty = fx - x0, fy - y0

    def grad(ix, iy, dx, dy):
        a = _hash(ix, iy, seed) * 2 * np.pi
        return np.cos(a) * dx + np.sin(a) * dy

    n00 = grad(x0, y0, tx, ty)
    n10 = grad(x0 + 1, y0, tx - 1, ty)
    n01 = grad(x0, y0 + 1, tx, ty - 1)
    n11 = grad(x0 + 1, y0 + 1, tx - 1, ty - 1)
    u = tx * tx * tx * (tx * (tx * 6 - 15) + 10)
    v = ty * ty * ty * (ty * (ty * 6 - 15) + 10)
    return ((n00 * (1 - u) + n10 * u) * (1 - v) + (n01 * (1 - u) + n11 * u) * v).astype(np.float32)


def eroded_detail(x, y, cell, octaves, seed, px_per_unit):
    """fBm "erodido" (cada oitava perde força onde já é íngreme), por coordenadas do mundo."""
    out = np.zeros(x.shape, np.float32)
    amp = 0.5
    for o in range(octaves):
        n = perlin_world(x, y, cell / 2 ** o, seed + o)
        gy, gx = np.gradient(out)
        slope = (gx * gx + gy * gy) * (cell * px_per_unit) ** 2
        out += amp * n / (1 + 6 * slope)
        amp *= 0.5
    return out


# --------------------------------------------------------------------------- mundo (global, a 1/Q)
class World:
    def __init__(self, full_json: Path, data_dir: Path, cache: Path):
        self.d = json.loads(Path(full_json).read_text())
        self.data_dir = Path(data_dir)
        self.cells = self.d["pack"]["cells"]
        self.W, self.H = self.d["info"]["width"], self.d["info"]["height"]
        self.pts = np.array([c["p"] for c in self.cells], dtype=np.float64)
        self.scale = json.loads((self.data_dir / "world.json").read_text())["rasterScale"]
        reg = np.asarray(Image.open(self.data_dir / "regions.png"))
        self.regions = reg[..., 0].astype(np.int32) + reg[..., 1].astype(np.int32) * 256
        self.land_r = (self.regions > 0).astype(np.float32)          # 2 px por unidade
        self.PW, self.PH = int(round(self.W * K)), int(round(self.H * K))
        self.kq = K / Q
        self.qw, self.qh = int(math.ceil(self.PW / Q)), int(math.ceil(self.PH / Q))
        cache = Path(cache)
        if cache.exists():
            z = np.load(cache)
            self.relief_q, self.mount_q, self.sea_q = z["relief"], z["mount"], z["sea"]
            self.color_q, self.forest_q = z["color"], z["forest"]
        else:
            self._build()
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(cache, relief=self.relief_q, mount=self.mount_q, sea=self.sea_q,
                                color=self.color_q, forest=self.forest_q)

    # coordenadas do mundo dos centros dos píxeis de uma grelha
    @staticmethod
    def grid(x0_px, y0_px, w, h, ppu):
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
        return (x0_px + xx + 0.5) / ppu, (y0_px + yy + 0.5) / ppu

    def sample(self, arr, ppu_src, wx, wy, order=1):
        """Amostra um raster global (ppu_src píxeis por unidade) em coordenadas do mundo."""
        cy, cx = wy * ppu_src - 0.5, wx * ppu_src - 0.5
        return ndimage.map_coordinates(arr, [cy, cx], order=order, mode="nearest", prefilter=False)

    def _build(self):
        from erosion import _stream_power, perlin
        print(f"mundo {self.W}×{self.H} → {self.PW}×{self.PH} px; relevo global a {self.qw}×{self.qh}")
        wx, wy = self.grid(0, 0, self.qw, self.qh, self.kq)
        land = self.sample(self.land_r, self.scale, wx, wy, order=1) >= 0.5
        hval = np.array([c["h"] for c in self.cells], dtype=np.float64)
        h = LinearNDInterpolator(self.pts, hval, fill_value=0.0)(wx.ravel(), wy.ravel()).reshape(wx.shape)
        h = ndimage.gaussian_filter(h.astype(np.float32), self.kq * 3)
        b = np.where(land, np.clip((h - SEA_LEVEL) / (80 - SEA_LEVEL), 0.002, 1), 0)
        mount = np.clip((b - 0.12) / 0.45, 0, 1)
        v = RELIEF * self.kq                                           # altura 1 em píxeis desta grelha
        noise = (perlin(b.shape, 8 * self.qw // 512, 101) * 0.6 + perlin(b.shape, 16 * self.qw // 512, 102) * 0.3
                 + perlin(b.shape, 32 * self.qw // 512, 103) * 0.15)
        h0 = np.where(land, np.clip(b * 0.7 + noise * 0.12 * (0.3 + mount), 0.002, None), 0) * v
        uplift = 0.35 * (0.1 + mount ** 1.5) * land
        import time
        t = time.time()
        hh = _stream_power(h0.astype(np.float64), land.astype(np.uint8), uplift.astype(np.float64),
                           0.02, 0.5, 1.0, 80, 0.15)
        print(f"erosão global: {time.time() - t:.0f} s")
        self.relief_q = ndimage.gaussian_filter(hh / v, 0.8).astype(np.float32)
        self.mount_q = mount.astype(np.float32)
        self.sea_q = np.where(land, 0, np.clip(ndimage.distance_transform_edt(~land) / self.kq / 30.0, 0, 1)
                              ).astype(np.float32)
        bio = np.array([c["biome"] for c in self.cells], dtype=np.int32)
        _, nn = cKDTree(self.pts).query(np.column_stack([wx.ravel(), wy.ravel()]), workers=-1)
        bq = bio[nn].reshape(wx.shape)
        col = BIOME_RGB[bq]
        self.color_q = np.stack([ndimage.gaussian_filter(col[..., i], self.kq * 2) for i in range(3)], -1
                                ).astype(np.float32)
        self.forest_q = ndimage.gaussian_filter(FOREST[bq], self.kq * 1.5).astype(np.float32)

    # ----------------------------------------------------------------------- um tile (com margem)
    def tile_inputs(self, tx: int, ty: int, tree_density: float = 0.28) -> dict:
        return self.window_inputs(tx * TILE, ty * TILE, TILE, tree_density)

    def window_inputs(self, ix: int, iy: int, inner: int, tree_density: float = 0.28) -> dict:
        """Janela de inner × inner píxeis com canto em (ix, iy) (píxeis do nível de mais detalhe), com margem."""
        x0, y0 = ix - PAD, iy - PAD
        n = inner + 2 * PAD
        wx, wy = self.grid(x0, y0, n, n, K)
        landf = ndimage.gaussian_filter(self.sample(self.land_r, self.scale, wx, wy, order=1), K / self.scale * 0.5)
        land = landf >= 0.5
        up = self.sample(self.relief_q, self.kq, wx, wy, order=3) if land.any() else np.zeros_like(wx, np.float32)
        mount = self.sample(self.mount_q, self.kq, wx, wy, order=1)
        if land.any():
            detail = eroded_detail(wx, wy, 15.0, 4, 110, K)
            elev = up + detail * (0.008 + 0.05 * mount)
            # vales dos rios do jogo, de leve
            canvas = Image.new("F", (n, n), 0.0)
            dr = ImageDraw.Draw(canvas)
            for rv in self.d["pack"]["rivers"]:
                if not rv or len(rv.get("cells", [])) < 3:
                    continue
                line = [(self.pts[c][0] * K - x0, self.pts[c][1] * K - y0) for c in rv["cells"] if 0 <= c < len(self.pts)]
                if not any(-200 <= x < n + 200 and -200 <= y < n + 200 for x, y in line):
                    continue
                w = max(1.0, min(6.0, (rv.get("discharge", 1) ** 0.5) / 6))
                dr.line(line, fill=1.0, width=max(2, int(w * K / 3)))
            valley = np.clip(ndimage.gaussian_filter(np.asarray(canvas, np.float32), K * 3.0) * 4, 0, 1)
            elev = elev - np.sqrt(valley) * (0.01 + 0.12 * elev)
            dist_land = ndimage.distance_transform_edt(land) / K
            elev = np.clip(elev, 0.004, None) * np.clip(dist_land / 6.0, 0.15, 1.0)
            height = np.where(land, elev, 0).astype(np.float32)
        else:
            height = np.zeros((n, n), np.float32)
        sea = np.where(land, 0, self.sample(self.sea_q, self.kq, wx, wy, order=1)).astype(np.float32)
        color = np.stack([self.sample(self.color_q[..., i], self.kq, wx, wy, order=1) for i in range(3)], -1)
        forest = self.sample(self.forest_q, self.kq, wx, wy, order=1) * land
        forest *= np.clip(1 - (height - 0.6) / 0.2, 0, 1)
        forest *= np.clip((perlin_world(wx, wy, 14.0, 120) * 0.9 + 0.75), 0, 1.4)       # clareiras
        forest = np.clip(forest, 0, 1).astype(np.float32)
        return {"x0": x0, "y0": y0, "n": n, "inner": inner, "height": height, "sea": sea, "color": color, "forest": forest,
                "land": land, "trees": self.trees(x0, y0, n, forest, height, tree_density),
                "houses": self.houses(x0, y0, n, height)}

    def trees(self, x0, y0, n, forest, height, density):
        """Árvores numa grelha "jittered" em coordenadas do mundo: o mesmo ponto do mundo dá sempre a mesma árvore."""
        c = 1 / math.sqrt(density)                                    # lado da célula, em unidades
        u0, v0 = x0 / K, y0 / K
        i0, j0 = math.floor(u0 / c), math.floor(v0 / c)
        i1, j1 = math.ceil((x0 + n) / K / c), math.ceil((y0 + n) / K / c)
        jj, ii = np.mgrid[j0:j1, i0:i1]
        ii, jj = ii.ravel().astype(np.int64), jj.ravel().astype(np.int64)
        tx = (ii + _hash(ii, jj, 201)) * c
        ty = (jj + _hash(ii, jj, 202)) * c
        px, py = tx * K - x0, ty * K - y0
        ok = (px >= 0) & (py >= 0) & (px < n - 1) & (py < n - 1)
        ii, jj, px, py = ii[ok], jj[ok], px[ok], py[ok]
        f = forest[py.astype(int), px.astype(int)]
        gy, gx = np.gradient(height * RELIEF * K)
        slope = np.hypot(gx, gy)[py.astype(int), px.astype(int)]
        keep = (_hash(ii, jj, 203) < f) & (slope < 0.7)
        kind = (_hash(ii, jj, 204) < 0.5).astype(np.float32)
        scale = (0.6 + 0.65 * _hash(ii, jj, 205)).astype(np.float32)
        rot = (_hash(ii, jj, 206) * 2 * np.pi).astype(np.float32)
        return np.column_stack([px[keep], py[keep], kind[keep], scale[keep], rot[keep]]).astype(np.float32)

    def houses(self, x0, y0, n, height):
        out = []
        for b in self.d["pack"]["burgs"][1:]:
            if not b or b.get("removed"):
                continue
            bx, by = b["x"] * K - x0, b["y"] * K - y0
            if not (-60 <= bx < n + 60 and -60 <= by < n + 60):
                continue
            rng = np.random.default_rng(1000 + b["i"])
            cap = bool(b.get("capital"))
            cnt = int(np.clip(3 + b.get("population", 0) * 1.5, 3, 18)) + (8 if cap else 0)
            for _ in range(cnt):
                r = rng.uniform(0, 0.6 + 0.35 * math.sqrt(cnt)) * K
                a = rng.uniform(0, 2 * math.pi)
                hx, hy = bx + r * math.cos(a), by + r * math.sin(a)
                rot, s = rng.uniform(0, math.pi), rng.uniform(0.8, 1.2) * (1.25 if cap else 1)
                if 0 <= hx < n - 1 and 0 <= hy < n - 1 and height[int(hy), int(hx)] > 0:
                    out.append((hx, hy, rot, s))
        return np.array(out, np.float32).reshape(-1, 4)


def save_tile_inputs(t: dict, out: Path, style: str = "atlas"):
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "height.npy", t["height"])
    np.save(out / "sea.npy", t["sea"])
    np.save(out / "forest.npy", t["forest"])
    np.save(out / "trees.npy", t["trees"])
    np.save(out / "houses.npy", t["houses"])
    Image.fromarray((np.clip(t["color"], 0, 1) * 255).astype(np.uint8)).save(out / "color.png")
    Image.fromarray((t["sea"] * 255).astype(np.uint8)).save(out / "sea.png")
    (out / "meta.json").write_text(json.dumps({"x0": t["x0"], "y0": t["y0"], "n": t["n"], "pad": PAD, "tile": t["inner"],
                                               "px_per_unit": K, "relief": RELIEF, "style": style}))
