"""Base do mapa do mundo inteiro, renderizada no Blender em tiles (estilo atlas).

Uso (a partir de modules/world-map):
    python blender/render_world.py build/exemplo/world_full.json build/exemplo/data build/tiles-exemplo
    python blender/render_world.py ... --install          # no fim, copia tiles + base.jpg para a pasta de dados
Opções:
    --blender CAMINHO   executável do Blender (por defeito o do Mac: /Applications/Blender.app/Contents/MacOS/Blender)
    --samples 32        amostras do Cycles por tile
    --cpu               força o processador
    --only 3,2          renderiza só esse tile (testes)
    --style atlas       estilo (ver render_tile.py)
É retomável: tiles já renderizados (raw/<x>_<y>.png) não se repetem. Para refazer um tile, apaga o PNG.

Passos:
  1. relevo, mar e cores globais (worldlib.World; ~2 min, guardado em world_q.npz)
  2. cada tile com terra: exportar (com margem) → Blender (sem pós-processamento); tiles só de mar não vão ao Blender
  3. mosaico: mar fundo nos tiles sem terra; papel, tinta na costa e tom do atlas aplicados ao mundo inteiro
  4. pirâmide de zoom (tiles de 512 px em WebP), base.jpg nova (2 px por unidade) e tiles.json com o índice
     tile → regiões (para o servidor enviar a cada jogador só o que ele conhece)
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from worldlib import K, PAD, TILE, World, _hash, perlin_world, save_tile_inputs  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT_TILE = 512
Image.MAX_IMAGE_PIXELS = None


def box_blur(a, r):
    for axis in (0, 1):
        c = np.cumsum(np.pad(a, [(r + 1, r) if i == axis else (0, 0) for i in range(a.ndim)], mode="edge"), axis=axis)
        n = c.shape[axis]
        a = (np.take(c, range(2 * r + 1, n), axis=axis) - np.take(c, range(0, n - 2 * r - 1), axis=axis)) / (2 * r + 1)
    return a


def render_tiles(world: World, out: Path, args):
    cols, rows = math.ceil(world.PW / TILE), math.ceil(world.PH / TILE)
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    status = json.loads((out / "status.json").read_text()) if (out / "status.json").exists() else {}
    hmax = float(world.relief_q.max())
    todo = [(tx, ty) for ty in range(rows) for tx in range(cols)]
    if args.only:
        todo = [tuple(int(v) for v in args.only.split(","))]
    for i, (tx, ty) in enumerate(todo):
        key = f"{tx}_{ty}"
        if (raw / f"{key}.png").exists() or status.get(key) == "sea":
            continue
        t0 = time.time()
        t = world.tile_inputs(tx, ty)
        if not t["land"].any():
            status[key] = "sea"
            (out / "status.json").write_text(json.dumps(status))
            continue
        work = out / "work" / key
        save_tile_inputs(t, work, args.style)
        meta = json.loads((work / "meta.json").read_text())
        meta["hmax"] = hmax
        (work / "meta.json").write_text(json.dumps(meta))
        cmd = args.blender_cmd + ["--", str(work), "--samples", str(args.samples), "--style", args.style, "--no-post",
                                  "--out", str(raw / f"{key}.png")] + (["--cpu"] if args.cpu else [])
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not (raw / f"{key}.png").exists():
            sys.exit(f"o Blender falhou no tile {key}:\n{res.stdout[-2000:]}\n{res.stderr[-2000:]}")
        # cor do mar fundo neste tile (para pintar os tiles só de mar sem os renderizar)
        img = np.asarray(Image.open(raw / f"{key}.png").convert("RGB"))
        deep = t["sea"][PAD:PAD + TILE, PAD:PAD + TILE] >= 0.95
        if deep.sum() > 2000:
            status[key + ":deep"] = np.median(img[deep], axis=0).round().astype(int).tolist()
        status[key] = "land"
        (out / "status.json").write_text(json.dumps(status))
        shutil.rmtree(work, ignore_errors=True)
        print(f"tile {key} ({i + 1}/{len(todo)}) em {time.time() - t0:.0f} s", flush=True)
    return cols, rows, status


def mosaic(world: World, out: Path, cols: int, rows: int, status: dict, style: str) -> np.ndarray:
    deeps = [v for k, v in status.items() if k.endswith(":deep")]
    deep = np.median(np.array(deeps), axis=0).astype(np.uint8) if deeps else np.array([22, 52, 70], np.uint8)
    W, H = world.PW, world.PH
    img = np.empty((rows * TILE, cols * TILE, 3), np.uint8)
    for ty in range(rows):
        for tx in range(cols):
            p = out / "raw" / f"{tx}_{ty}.png"
            if p.exists():
                img[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE] = np.asarray(Image.open(p).convert("RGB"))
            else:
                img[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE] = deep
    img = img[:H, :W]
    if style == "atlas":
        img = atlas_post(world, img)
    return img


def atlas_post(world: World, img: np.ndarray) -> np.ndarray:
    """O acabamento do atlas, aplicado ao mundo inteiro (em faixas, por memória): papel, tinta na costa, cor."""
    H, W = img.shape[:2]
    out = np.empty_like(img)
    strip, ov = 512, 16
    for y0 in range(0, H, strip):
        a, b = max(0, y0 - ov), min(H, y0 + strip + ov)
        wx, wy = World.grid(0, a, W, b - a, K)
        col = img[a:b].astype(np.float32) / 255
        land = (world.sample(world.land_r, world.scale, wx, wy, order=1) >= 0.5).astype(np.float32)
        paper = perlin_world(wx, wy, 140.0, 301) * 0.6 + perlin_world(wx, wy, 45.0, 302) * 0.4
        paper = 0.94 + 0.10 * paper
        ix, iy = (wx * K).astype(np.int64), (wy * K).astype(np.int64)
        grain = _hash(ix, iy, 303).astype(np.float32)
        col *= (paper * (0.975 + 0.05 * grain))[..., None]
        soft = box_blur(land, 2)
        ink = np.clip(1 - np.abs(soft * 2 - 1) * 3.0, 0, 1)
        col = col * (1 - ink[..., None] * 0.75) + np.array([0.17, 0.13, 0.09]) * ink[..., None] * 0.75
        lum = col @ np.array([0.3, 0.55, 0.15], np.float32)
        col = lum[..., None] + (col - lum[..., None]) * 1.2
        col = col * 0.92 + np.array([0.94, 0.86, 0.68]) * 0.08
        out[y0:min(H, y0 + strip)] = (np.clip(col[y0 - a:y0 - a + min(strip, H - y0)], 0, 1) * 255).astype(np.uint8)
    return out


def pyramid(world: World, img: np.ndarray, out: Path) -> dict:
    tiles = out / "tiles"
    if tiles.exists():
        shutil.rmtree(tiles)
    levels = []
    im = Image.fromarray(img)
    z, ppu = 0, K
    while True:
        cols, rows = math.ceil(im.width / OUT_TILE), math.ceil(im.height / OUT_TILE)
        d = tiles / str(z)
        d.mkdir(parents=True)
        index = {}
        for ty in range(rows):
            for tx in range(cols):
                box = (tx * OUT_TILE, ty * OUT_TILE, min(im.width, (tx + 1) * OUT_TILE), min(im.height, (ty + 1) * OUT_TILE))
                im.crop(box).save(d / f"{tx}_{ty}.webp", quality=82, method=4)
                # regiões que o tile toca (regions.png a 2 px por unidade)
                s = world.scale / ppu
                r = world.regions[int(box[1] * s):int(math.ceil(box[3] * s)), int(box[0] * s):int(math.ceil(box[2] * s))]
                ids = np.unique(r)
                index[f"{tx}_{ty}"] = [int(v) for v in ids if v > 0]
        levels.append({"z": z, "pxPerUnit": round(ppu, 6), "cols": cols, "rows": rows, "width": im.width,
                       "height": im.height, "regions": index})
        if im.width <= 1024:
            break
        im = im.resize((math.ceil(im.width / 2), math.ceil(im.height / 2)), Image.LANCZOS)
        z, ppu = z + 1, ppu / 2
    meta = {"tileSize": OUT_TILE, "format": "webp", "style": "atlas", "levels": levels}
    (out / "tiles.json").write_text(json.dumps(meta, separators=(",", ":")))
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("full_json")
    ap.add_argument("data_dir")
    ap.add_argument("out")
    ap.add_argument("--blender", default="/Applications/Blender.app/Contents/MacOS/Blender")
    ap.add_argument("--bpy-python", help="em vez do Blender, um Python com o módulo bpy (servidores sem Blender)")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--style", default="atlas")
    ap.add_argument("--install", action="store_true")
    args = ap.parse_args()
    script = str(HERE / "render_tile.py")
    if args.bpy_python:
        args.blender_cmd = [args.bpy_python, "-c",
                            f"import runpy, sys; sys.argv = ['render_tile.py'] + sys.argv[1:]; "
                            f"runpy.run_path({script!r}, run_name='__main__')"]
    else:
        args.blender_cmd = [args.blender, "-b", "-P", script]
    out = Path(args.out)
    world = World(Path(args.full_json), Path(args.data_dir), out / "world_q.npz")
    cols, rows, status = render_tiles(world, out, args)
    if args.only:
        return
    print("mosaico e acabamento…", flush=True)
    img = mosaic(world, out, cols, rows, status, args.style)
    Image.fromarray(img).save(out / "mundo.jpg", quality=88)
    meta = pyramid(world, img, out)
    base = Image.fromarray(img).resize((world.W * world.scale, world.H * world.scale), Image.LANCZOS)
    base.save(out / "base.jpg", quality=90, optimize=True, progressive=True)
    print(f"{sum(len(list((out / 'tiles' / str(l['z'])).glob('*.webp'))) for l in meta['levels'])} tiles em "
          f"{len(meta['levels'])} níveis; base.jpg {base.size}")
    if args.install:
        data = Path(args.data_dir)
        if not (data / "base-python.jpg").exists() and (data / "base.jpg").exists():
            shutil.copy(data / "base.jpg", data / "base-python.jpg")
        shutil.copy(out / "base.jpg", data / "base.jpg")
        shutil.copy(out / "tiles.json", data / "tiles.json")
        if (data / "tiles").exists():
            shutil.rmtree(data / "tiles")
        shutil.copytree(out / "tiles", data / "tiles")
        print("instalado em", data, "(a base antiga ficou em base-python.jpg)")


if __name__ == "__main__":
    main()
