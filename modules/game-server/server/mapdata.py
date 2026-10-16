"""Ficheiros do mapa servidos por jogador: o nevoeiro aplicado no servidor (§8).

O GM recebe tudo. Um jogador recebe:
  world.json   regiões desconhecidas sem nome, dono, centro nem vizinhos; só burgos, rios e estradas em regiões
               conhecidas; só as fações que conhece; sem capitais nem donos iniciais
  regions.png  regiões desconhecidas apagadas (contam como água): não revela a forma das costas
  base.jpg     pergaminho fora de uma margem à volta do que conhece
  tiles        só os que tocam regiões conhecidas (ou só mar); um tile pode mostrar geografia vizinha (aceite)
Os ficheiros por jogador são guardados em memória por (fação, turno).
"""
from __future__ import annotations

import io
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

PARCHMENT = np.array([212, 196, 160], np.uint8)
MARGIN_UNITS = 24          # o base.jpg mostra até 24 unidades à volta do que se conhece (a costa vizinha)


class MapData:
    def __init__(self, world_dir: Path):
        self.dir = Path(world_dir)
        self.raw = json.loads((self.dir / "world.json").read_text())
        self.scale = self.raw["rasterScale"]
        reg = np.asarray(Image.open(self.dir / "regions.png"))
        self.reg_rgba = reg
        self.rid = reg[..., 0].astype(np.int32) + reg[..., 1].astype(np.int32) * 256
        self.n_regions = len(self.raw["regions"])
        tj = self.dir / "tiles.json"
        self.tiles = json.loads(tj.read_text()) if tj.exists() else None
        self.tile_regions = {(L["z"], k): set(v) for L in self.tiles["levels"] for k, v in L["regions"].items()} \
            if self.tiles else {}
        self._cache: dict = {}

    def _known_lut(self, known: set[int]) -> np.ndarray:
        lut = np.zeros(self.n_regions + 1, bool)
        for r in known:
            if 0 < r <= self.n_regions:
                lut[r] = True
        return lut

    def _cached(self, key, make):
        if key not in self._cache:
            if len(self._cache) > 200:
                self._cache.clear()
            self._cache[key] = make()
        return self._cache[key]

    # ------------------------------------------------------------------ world.json
    def world_json(self, known: set[int] | None, faction_names: dict[int, dict] | None, key) -> bytes:
        if known is None:
            return (self.dir / "world.json").read_bytes()
        return self._cached(("world", key), lambda: self._world_json(known, faction_names or {}))

    def _world_json(self, known: set[int], factions: dict[int, dict]) -> bytes:
        w = dict(self.raw)
        regions = []
        for r in self.raw["regions"]:
            if r["id"] in known:
                regions.append({**r, "owner": 0})
            else:
                regions.append({"id": r["id"], "kind": "province", "name": "", "fullName": "", "owner": 0,
                                "center": [0, 0], "area": 0, "neighbors": []})
        w["regions"] = regions
        w["factions"] = [{"id": f["id"], "name": f["name"], "color": f["color"]} for f in factions.values()]
        w["burgs"] = [b for b in self.raw["burgs"] if b["region"] in known]
        lut = self._known_lut(known)

        def keep(polyline):
            out, cur = [], []
            for x, y in polyline:
                px, py = int(x * self.scale), int(y * self.scale)
                ok = 0 <= py < self.rid.shape[0] and 0 <= px < self.rid.shape[1] and lut[self.rid[py, px]]
                if ok:
                    cur.append([x, y])
                elif cur:
                    out.append(cur)
                    cur = []
            if cur:
                out.append(cur)
            return [p for p in out if len(p) >= 2]
        w["rivers"] = [{**rv, "pts": part} for rv in self.raw["rivers"] for part in keep(rv["pts"])]
        w["roads"] = [part for rd in self.raw["roads"] for part in keep(rd)]
        return json.dumps(w, ensure_ascii=False, separators=(",", ":")).encode()

    # ------------------------------------------------------------------ regions.png e base.jpg
    def regions_png(self, known: set[int] | None, key) -> bytes:
        if known is None:
            return (self.dir / "regions.png").read_bytes()

        def make():
            lut = self._known_lut(known)
            rgba = self.reg_rgba.copy()
            hide = ~lut[self.rid]
            rgba[hide, 0] = 0
            rgba[hide, 1] = 0
            buf = io.BytesIO()
            Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=False, compress_level=6)
            return buf.getvalue()
        return self._cached(("regions", key), make)

    def base_jpg(self, known: set[int] | None, key) -> bytes:
        if known is None:
            return (self.dir / "base.jpg").read_bytes()

        def make():
            base = np.asarray(Image.open(self.dir / "base.jpg").convert("RGB")).copy()
            lut = self._known_lut(known)
            seen = lut[self.rid]
            if seen.shape != base.shape[:2]:
                seen = np.asarray(Image.fromarray(seen.astype(np.uint8) * 255).resize(
                    (base.shape[1], base.shape[0]), Image.NEAREST)) > 0
            near = ndimage.distance_transform_edt(~seen) <= MARGIN_UNITS * self.scale
            base[~near] = PARCHMENT
            buf = io.BytesIO()
            Image.fromarray(base).save(buf, "JPEG", quality=85)
            return buf.getvalue()
        return self._cached(("base", key), make)

    # ------------------------------------------------------------------ tiles
    def tiles_json(self) -> bytes | None:
        return (self.dir / "tiles.json").read_bytes() if self.tiles else None

    def tile_path(self, z: int, name: str, known: set[int] | None) -> Path | None:
        """Caminho do tile, ou None se não existe ou o jogador não o pode ver."""
        if not self.tiles or "/" in name or ".." in name:
            return None
        stem = name.rsplit(".", 1)[0]
        p = self.dir / "tiles" / str(z) / name
        if not p.exists():
            return None
        if known is None:
            return p
        regs = self.tile_regions.get((z, stem), set())
        return p if (not regs or regs & known) else None


@lru_cache(maxsize=4)
def get_mapdata(world_dir: str) -> MapData:
    return MapData(Path(world_dir))
