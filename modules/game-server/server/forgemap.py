"""Mapa do Province-Forge servido por jogador: o nevoeiro aplicado no servidor (§8, decisão de 2026-10-16).

A pasta do mundo é um bundle do Province-Forge (manifest.json, static-map.json, client-map.<hash>.json, tiles/)
mais o world.json do Praga (forge.convert).

O GM recebe tudo. Um jogador recebe:
  client map  só a geometria das regiões que conhece (+ as zonas de mar, lagos e gelo que lhes tocam): o resto
              não tem forma, nome nem terreno no browser (filter_client_map do Province-Forge)
  tiles       pintados de cinzento fora do que conhece; um tile sem nada conhecido é só cinzento
  vista       ViewerState do Province-Forge, construído a partir das fotografias do motor (§8)

Ids: o Praga numera as províncias de terra 1..L; no Province-Forge são 0..L-1 (pf = rid - 1).
"""
from __future__ import annotations

import io
import json
import sys
import threading
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
from scipy.spatial import cKDTree

from .config import MODULES

sys.path.insert(0, str(MODULES.parent / "vendor/province-forge/server/python"))
from exaequo_map.clientmap import filter_client_map  # noqa: E402

GREY = (0x8c, 0x8f, 0x8b)       # a terra incógnita do Province-Forge (political.ts)
SAMPLES = 128                   # resolução da máscara por tile (é suavizada até 512)
TILE_CACHE = 3000               # tiles mascarados guardados em memória (todos os jogadores)


class ForgeMap:
    def __init__(self, world_dir: Path):
        self.dir = Path(world_dir)
        self.manifest = json.loads((self.dir / "manifest.json").read_text())
        static = json.loads((self.dir / self.manifest["files"]["static"]).read_text())
        self.width = float(static["world"]["width"])
        self.height = float(static["world"]["height"])
        self.regions = [{"id": r["id"], "kind": r["kind"], "neighbors": r["neighbors"]} for r in static["regions"]]
        self.n_land = sum(1 for r in self.regions if r["kind"] == "land")
        self.client_bytes = (self.dir / self.manifest["files"]["client"]).read_bytes()
        self.client = json.loads(self.client_bytes)
        self.tiles = self.manifest["tiles"]
        # região de cada ponto do mundo = região da célula mais próxima (as células são um Voronoi)
        cx = np.asarray(static["cells"]["x"], float)
        cy = np.asarray(static["cells"]["y"], float)
        creg = np.asarray(static["cells"]["region"], np.int32)
        cx = np.mod(cx, self.width)
        margin = self.width * 0.05
        lo, hi = cx < margin, cx > self.width - margin
        self.cell_region = np.concatenate([creg, creg[lo], creg[hi]])
        self.tree = cKDTree(np.column_stack([np.concatenate([cx, cx[lo] + self.width, cx[hi] - self.width]),
                                             np.concatenate([cy, cy[lo], cy[hi]])]))
        self._regions_of_tile: dict[tuple, frozenset] = {}
        self._client_cache: OrderedDict = OrderedDict()
        self._tile_cache: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._grey = None

    # ------------------------------------------------------------------ visibilidade
    def visible_pf(self, known_rids: set[int]) -> set[int]:
        """Ids do Province-Forge que o jogador vê desenhados: as províncias que conhece e o mar, lagos e gelo que
        lhes tocam (para a costa aparecer)."""
        land = {r - 1 for r in known_rids if 0 < r <= self.n_land}
        out = set(land)
        for pf in land:
            for n in self.regions[pf]["neighbors"]:
                if self.regions[n]["kind"] != "land":
                    out.add(n)
        return out

    def client_map(self, visible: set[int] | None, key) -> bytes:
        if visible is None:
            return self.client_bytes
        with self._lock:
            if key in self._client_cache:
                self._client_cache.move_to_end(key)
                return self._client_cache[key]
        data = json.dumps(filter_client_map(self.client, visible), separators=(",", ":")).encode()
        with self._lock:
            self._client_cache[key] = data
            while len(self._client_cache) > 300:
                self._client_cache.popitem(last=False)
        return data

    # ------------------------------------------------------------------ tiles
    def _tile_box(self, z: int, tx: int, ty: int):
        upx = self.width / (self.tiles["basePx"] * 2 ** z)
        size = self.tiles["tile"] * upx
        return tx * size, ty * size, size

    def _grid(self, z: int, tx: int, ty: int) -> np.ndarray:
        x0, y0, size = self._tile_box(z, tx, ty)
        t = (np.arange(SAMPLES) + 0.5) / SAMPLES * size
        gx, gy = np.meshgrid(x0 + t, y0 + t)
        _, idx = self.tree.query(np.column_stack([np.mod(gx.ravel(), self.width), gy.ravel()]))
        g = self.cell_region[idx].reshape(SAMPLES, SAMPLES)
        g[gy >= self.height] = -1
        return g

    def tile_regions(self, z: int, tx: int, ty: int) -> frozenset:
        k = (z, tx, ty)
        if k not in self._regions_of_tile:
            self._regions_of_tile[k] = frozenset(int(v) for v in np.unique(self._grid(z, tx, ty)) if v >= 0)
        return self._regions_of_tile[k]

    def tile_path(self, z: int, tx: int, ty: int) -> Path | None:
        p = self.dir / "tiles" / str(z) / str(tx) / f"{ty}.webp"
        return p if p.exists() else None

    def grey_tile(self) -> bytes:
        if self._grey is None:
            buf = io.BytesIO()
            Image.new("RGB", (self.tiles["tile"], self.tiles["tile"]), GREY).save(buf, "WEBP", quality=60)
            self._grey = buf.getvalue()
        return self._grey

    def player_tile(self, z: int, tx: int, ty: int, visible: set[int], key) -> bytes | None:
        """O tile tal como o jogador o pode ver: cinzento onde não conhece nada."""
        p = self.tile_path(z, tx, ty)
        if p is None:
            return None
        regs = self.tile_regions(z, tx, ty)
        if regs <= visible:
            return p.read_bytes()
        if not regs & visible:
            return self.grey_tile()
        ck = (key, z, tx, ty)
        with self._lock:
            if ck in self._tile_cache:
                self._tile_cache.move_to_end(ck)
                return self._tile_cache[ck]
        grid = self._grid(z, tx, ty)
        lut = np.zeros(len(self.regions) + 1, bool)
        lut[[v for v in visible if v < len(self.regions)]] = True
        show = lut[np.where(grid >= 0, grid, len(self.regions))]
        show = ndimage.binary_dilation(show, iterations=2)       # nunca cortar a orla do que se vê
        img = Image.open(p).convert("RGB")
        mask = Image.fromarray(show.astype(np.uint8) * 255).resize(img.size, Image.BILINEAR) \
            .filter(ImageFilter.GaussianBlur(2))
        out = Image.composite(img, Image.new("RGB", img.size, GREY), mask)
        buf = io.BytesIO()
        out.save(buf, "WEBP", quality=80)
        data = buf.getvalue()
        with self._lock:
            self._tile_cache[ck] = data
            while len(self._tile_cache) > TILE_CACHE:
                self._tile_cache.popitem(last=False)
        return data


@lru_cache(maxsize=2)
def get_forgemap(world_dir: str) -> ForgeMap:
    return ForgeMap(Path(world_dir))
