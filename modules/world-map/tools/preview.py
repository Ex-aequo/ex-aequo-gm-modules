"""Imagem estática do mapa político (reinos, fronteiras de província e de reino, capitais).
Serve para verificar um mundo gerado sem abrir o browser.

Uso: python tools/preview.py <pasta com world.json, base.jpg, regions.png> <saída.png>
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    d, out = Path(sys.argv[1]), sys.argv[2]
    w = json.loads((d / "world.json").read_text())
    base = np.asarray(Image.open(d / "base.jpg").convert("RGB")).astype(np.float32) / 255
    reg = np.asarray(Image.open(d / "regions.png"))
    rid = reg[..., 0].astype(np.int32) + 256 * reg[..., 1].astype(np.int32)

    owner = np.zeros(len(w["regions"]) + 1, np.int32)
    for r in w["regions"]:
        owner[r["id"]] = r["owner"]
    colors = {f["id"]: f["color"] for f in w["factions"]}
    lut = np.zeros((max(colors) + 1, 3), np.float32)
    for k, v in colors.items():
        lut[k] = [int(v[i:i + 2], 16) / 255 for i in (1, 3, 5)]

    own = owner[rid]
    img = base.copy()
    m = (rid > 0) & (own > 0)
    img[m] = img[m] * 0.45 + lut[own[m]] * 0.55
    prov_edge = (rid != np.roll(rid, 1, 0)) | (rid != np.roll(rid, 1, 1))
    realm_edge = (own != np.roll(own, 1, 0)) | (own != np.roll(own, 1, 1))
    img[prov_edge & (rid > 0)] *= 0.75
    img[realm_edge & (rid > 0)] = [0.15, 0.12, 0.10]

    width = 1920
    im = Image.fromarray((img * 255).clip(0, 255).astype(np.uint8)).resize(
        (width, round(width * img.shape[0] / img.shape[1])), Image.LANCZOS)
    draw = ImageDraw.Draw(im)
    s = width / w["width"]
    center = {r["id"]: r["center"] for r in w["regions"]}
    for f in w["factions"]:
        if f.get("capital"):
            x, y = center[f["capital"]]
            draw.ellipse([x * s - 4, y * s - 4, x * s + 4, y * s + 4], fill="white", outline="black")
    im.save(out)
    print("guardado:", out)


if __name__ == "__main__":
    main()
