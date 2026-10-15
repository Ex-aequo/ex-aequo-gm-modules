"""Prova Blender, passo 3: junta a base atual e os renders do Blender lado a lado.

Uso: python blender/compare.py build/blender-prova
Escreve <pasta>/comparacao.png (base atual + cada estilo renderizado), <pasta>/comparacao-zoom.png (o centro do
recorte ampliado 2×, onde se vê a diferença de detalhe).
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def label(img, text):
    d = ImageDraw.Draw(img)
    d.rectangle([12, 12, 24 + 9 * len(text), 44], fill=(20, 16, 12))
    d.text((20, 20), text, fill=(239, 228, 200))
    return img


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    d = Path(sys.argv[1])
    renders = sorted(d.glob("render-*.png"))
    if not renders:
        sys.exit("não há renders (render-<estilo>.png) nesta pasta")
    b0 = Image.open(renders[0])
    w, h = b0.size
    items = [("base atual (Python)", Image.open(d / "atual.png").convert("RGB").resize((w, h), Image.LANCZOS))]
    items += [(f"Blender: {r.stem.split('-', 1)[1]}", Image.open(r).convert("RGB")) for r in renders]
    box = (w // 4, h // 4, w // 4 + w // 2, h // 4 + h // 2)
    for name, zoom in (("comparacao.png", False), ("comparacao-zoom.png", True)):
        sheet = Image.new("RGB", (len(items) * (w + 16) - 16, h), (20, 16, 12))
        for i, (text, im) in enumerate(items):
            if zoom:
                im = im.crop(box).resize((w, h), Image.LANCZOS)
            sheet.paste(label(im.copy(), text + (" · zoom 2x" if zoom else "")), (i * (w + 16), 0))
        sheet.save(d / name)
    print("guardado:", d / "comparacao.png", "e", d / "comparacao-zoom.png")


if __name__ == "__main__":
    main()
