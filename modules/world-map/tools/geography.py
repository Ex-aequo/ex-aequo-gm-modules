"""Relevo próprio para o Azgaar: número exato de continentes, fração de terra, ilhas e mar interior.

O Azgaar não tem a opção "número de continentes". Em vez de calibrar os guiões de colinas dele, desenhamos aqui o
mapa de relevo (uma imagem em tons de cinzento), verificamos as contas em Python e só depois o entregamos ao Azgaar,
que trata do clima, rios, biomas, culturas e povoações por cima.

Uso isolado (pré-visualização sem Azgaar):
    python tools/geography.py worlds/exemplo.toml build/exemplo
"""
from __future__ import annotations

import hashlib
import io
import sys
from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from scipy import ndimage

IMG_W, IMG_H = 960, 540          # 16:9; o Azgaar reamostra para a grelha de células dele
ISLANDS = {"nenhumas": (0, 0), "poucas": (3, 6), "muitas": (14, 26)}


@dataclass
class GeoOptions:
    continents: int = 3
    land: float = 0.40               # fração do mapa que é terra
    islands: str = "poucas"          # nenhumas | poucas | muitas
    inland_sea: bool = False

    @classmethod
    def from_toml(cls, cfg: dict) -> "GeoOptions":
        g = cfg.get("geografia", {})
        o = cls(int(g.get("continentes", 3)), float(g.get("terra", 0.40)), str(g.get("ilhas", "poucas")),
                bool(g.get("mar_interior", False)))
        if not 1 <= o.continents <= 8:
            raise ValueError("continentes tem de estar entre 1 e 8")
        if not 0.15 <= o.land <= 0.70:
            raise ValueError("terra tem de estar entre 0.15 e 0.70")
        if o.islands not in ISLANDS:
            raise ValueError(f"ilhas tem de ser uma de {list(ISLANDS)}")
        return o


@dataclass
class GeoResult:
    seed: str
    heightmap: np.ndarray            # alturas 0..100 (convenção Azgaar: terra >= 20)
    continents: list[float]          # % da terra em cada continente, do maior para o menor
    islands: int
    land: float
    inland_sea: bool
    notes: list[str] = field(default_factory=list)

    def ok(self, opt: GeoOptions) -> bool:
        """Número exato de continentes, terra a ±5 pontos, e nenhum continente minúsculo
        (cada um com pelo menos 40% de uma parte igual da terra)."""
        min_share = 40 / opt.continents
        return (len(self.continents) == opt.continents and abs(self.land - opt.land) <= 0.05
                and min(self.continents) >= min_share)

    def png(self) -> bytes:
        """Imagem em cinzento com a curva inversa da que o Azgaar aplica ao ler (heightmap-generator.ts)."""
        h = self.heightmap / 100.0
        light = np.where(h < 0.2, h, 0.2 + np.clip(h - 0.2, 0, None) ** (1 / 0.8))
        img = Image.fromarray((np.clip(light, 0, 1) * 255).round().astype(np.uint8), "L")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def preview(self) -> Image.Image:
        h = self.heightmap
        rgb = np.zeros(h.shape + (3,), np.float32)
        sea = h < 20
        rgb[sea] = np.array([0.18, 0.30, 0.38]) + (h[sea, None] / 20) * np.array([0.25, 0.30, 0.25])
        t = np.clip((h - 20) / 70, 0, 1)[..., None]
        land_rgb = np.array([0.55, 0.65, 0.40]) * (1 - t) + np.array([0.90, 0.88, 0.82]) * t
        rgb[~sea] = land_rgb[~sea]
        return Image.fromarray((rgb * 255).astype(np.uint8), "RGB")


def _rng(seed: str) -> np.random.Generator:
    return np.random.default_rng(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big"))


def _fbm(rng, shape, octaves=5, base=4):
    out = np.zeros(shape, np.float32)
    amp = total = 0.0
    amp = 1.0
    for o in range(octaves):
        n = base * 2 ** o
        grid = rng.random((max(2, int(n * shape[0] / shape[1]) + 2), n + 2)).astype(np.float32)
        z = ndimage.zoom(grid, (shape[0] / grid.shape[0], shape[1] / grid.shape[1]), order=3)[: shape[0], : shape[1]]
        out += amp * z
        total += amp
        amp *= 0.5
    return out / total


def _centers(rng, n: int) -> np.ndarray:
    """Centros dos continentes bem espalhados (amostragem do ponto mais afastado), em píxeis."""
    if n == 1:
        return np.array([[IMG_W * rng.uniform(0.42, 0.58), IMG_H * rng.uniform(0.42, 0.58)]])
    cand = np.column_stack([rng.uniform(0.14, 0.86, 3000) * IMG_W, rng.uniform(0.18, 0.82, 3000) * IMG_H])
    chosen = [cand[0]]
    for _ in range(n - 1):
        d = np.min(np.linalg.norm(cand[:, None, :] - np.array(chosen)[None], axis=2), axis=1)
        chosen.append(cand[np.argmax(d)])
    return np.array(chosen)


def _label(land: np.ndarray):
    lab, k = ndimage.label(land, structure=np.ones((3, 3)))
    sizes = ndimage.sum(land, lab, index=np.arange(1, k + 1)) if k else np.array([])
    return lab, sizes


def generate_once(opt: GeoOptions, seed: str) -> GeoResult:
    rng = _rng(seed)
    yy, xx = np.mgrid[0:IMG_H, 0:IMG_W].astype(np.float32)
    # coordenadas deformadas por ruído: fronteiras entre continentes orgânicas, não retas
    wx = xx + (_fbm(rng, (IMG_H, IMG_W), 4, 3) - 0.5) * IMG_W * 0.16
    wy = yy + (_fbm(rng, (IMG_H, IMG_W), 4, 3) - 0.5) * IMG_W * 0.16
    centers = _centers(rng, opt.continents)
    d = np.stack([np.hypot(wx - cx, wy - cy) for cx, cy in centers])          # (n, H, W)
    order = np.sort(d, axis=0)
    d1 = order[0]
    d2 = order[1] if opt.continents > 1 else np.full_like(d1, IMG_W)
    boundary = (d2 - d1) / 2                                                   # distância à fronteira entre continentes

    # potencial de terra: alto junto aos centros, baixo junto às fronteiras e aos bordos do mapa
    # ruído fractal forte e de várias escalas: costas recortadas, penínsulas e baías
    noise = (_fbm(rng, (IMG_H, IMG_W), 7, 3) - 0.5) * 1.0 + (_fbm(rng, (IMG_H, IMG_W), 4, 24) - 0.5) * 0.35
    pot = (boundary / (boundary.max() + 1e-6)) ** 0.5 * 0.8 + noise * 1.2
    edge = np.minimum.reduce([xx, IMG_W - 1 - xx, yy, IMG_H - 1 - yy]) / IMG_H
    # queda elíptica (sem cantos) para a terra não encostar às margens do mapa
    ell = ((xx - IMG_W / 2) / (IMG_W / 2)) ** 2 + ((yy - IMG_H / 2) / (IMG_H / 2)) ** 2
    pot -= np.clip(ell - 0.55, 0, None) * 1.6

    # mar mínimo entre continentes, com largura irregular (nada de canais retos)
    channel = max(10.0, IMG_W * 0.022)
    wavy = channel * (0.7 + 0.9 * _fbm(rng, (IMG_H, IMG_W), 4, 8))
    forbidden = (boundary < wavy) | (edge < 0.035) if opt.continents > 1 else (edge < 0.035)
    allowed = ~forbidden
    want = int(opt.land * IMG_W * IMG_H)
    notes = []
    if allowed.sum() < want:
        notes.append("terra pedida maior do que cabe com estes continentes; usada a máxima possível")
        want = int(allowed.sum() * 0.95)
    thr = np.partition(pot[allowed], -want)[-want]
    land = allowed & (pot >= thr)

    # cada continente fica só com a sua maior mancha; pedaços pequenos passam a ilhas, grandes cortam-se
    owner = np.argmin(d, axis=0)
    lab, sizes = _label(land)
    total = land.sum()
    for i in range(opt.continents):
        part = land & (owner == i)
        plab, psizes = _label(part)
        if not len(psizes):
            continue
        keep = 1 + int(np.argmax(psizes))
        for j, s in enumerate(psizes, start=1):
            if j != keep and s > 0.02 * total:          # mancha grande separada: é cortada (viraria continente extra)
                land[plab == j] = False

    # ilhas
    lo, hi = ISLANDS[opt.islands]
    lab, sizes = _label(land)
    if opt.islands == "nenhumas":
        for j, s in enumerate(sizes, start=1):
            if s < 0.02 * land.sum():
                land[lab == j] = False
    else:
        dist_land = ndimage.distance_transform_edt(~land)
        island_noise = _fbm(rng, (IMG_H, IMG_W), 3, 60)
        for _ in range(int(rng.integers(lo, hi + 1))):
            for _try in range(40):
                x, y = rng.uniform(0.06, 0.94) * IMG_W, rng.uniform(0.08, 0.92) * IMG_H
                r = rng.uniform(4, 11)
                if dist_land[int(y), int(x)] > r + channel * 0.6:
                    ang = np.arctan2(yy - y, xx - x)
                    wob = 1 + 0.35 * np.sin(3 * ang + rng.uniform(0, 6.3)) + 0.2 * np.sin(5 * ang + rng.uniform(0, 6.3))
                    blob = np.hypot(xx - x, yy - y) < r * wob * (0.7 + 0.6 * island_noise)
                    land |= blob
                    break

    # mar interior: um mar fechado dentro do maior continente
    inland = False
    if opt.inland_sea:
        lab, sizes = _label(land)
        if len(sizes):
            main = lab == 1 + int(np.argmax(sizes))
            inside = ndimage.distance_transform_edt(main)
            if inside.max() > 30:
                cy, cx = np.unravel_index(np.argmax(inside), inside.shape)
                r = inside.max() * 0.42
                sea = (np.hypot((xx - cx) / 1.25, yy - cy) < r * (0.8 + 0.4 * _fbm(rng, (IMG_H, IMG_W), 3, 6))) & (inside > 12)
                land &= ~sea
                inland = True
            else:
                notes.append("continente principal pequeno demais para um mar interior")

    # alturas: sobem com a distância à costa, com cristas de montanha
    dist_in = ndimage.distance_transform_edt(land)
    dist_out = ndimage.distance_transform_edt(~land)
    ridge = 1 - np.abs(_fbm(rng, (IMG_H, IMG_W), 5, 6) * 2 - 1)
    rel = np.clip(dist_in / max(8.0, np.percentile(dist_in[land], 95) if land.any() else 1), 0, 1) ** 0.7
    h_land = 21 + 45 * rel * (0.55 + 0.45 * _fbm(rng, (IMG_H, IMG_W), 4, 5)) + 30 * rel * ridge ** 3
    h_sea = np.clip(19 - dist_out * 0.35, 2, 19)
    height = np.where(land, np.clip(h_land, 20, 100), h_sea).astype(np.float32)

    lab, sizes = _label(land)
    tot = land.sum()
    conts = sorted((round(float(100 * s / tot), 1) for s in sizes if s >= 0.02 * tot), reverse=True)
    return GeoResult(seed=seed, heightmap=height, continents=conts, islands=int(sum(1 for s in sizes if s < 0.02 * tot)),
                     land=round(float(tot / land.size), 3), inland_sea=inland, notes=notes)


def generate(opt: GeoOptions, seed: str, tries: int = 12) -> tuple[GeoResult, list[GeoResult]]:
    """Tenta variantes da seed até a geografia bater com o pedido. Devolve (escolhida, todas as tentativas)."""
    attempts = []
    for i in range(tries):
        r = generate_once(opt, f"{seed}-{i}" if i else seed)
        attempts.append(r)
        if r.ok(opt):
            return r, attempts
    best = min(attempts, key=lambda r: (abs(len(r.continents) - opt.continents), abs(r.land - opt.land)))
    best.notes.append(f"nenhuma tentativa em {tries} bateu exatamente com o pedido; usada a mais próxima")
    return best, attempts


if __name__ == "__main__":
    import tomllib
    from pathlib import Path
    cfg = tomllib.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    opt = GeoOptions.from_toml(cfg)
    res, atts = generate(opt, str(cfg["world"]["seed"]))
    res.preview().save(out / "geografia.png")
    (out / "heightmap.png").write_bytes(res.png())
    print(f"pedido: {opt}")
    print(f"obtido (tentativa {len(atts)}): continentes {res.continents} · ilhas {res.islands} · terra {res.land:.0%}"
          f" · mar interior {res.inland_sea} {res.notes}")
