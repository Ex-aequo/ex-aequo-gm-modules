"""Prova Blender, passo 3: junta a base atual e o render do Blender lado a lado.

Uso: python blender/compare.py build/blender-prova
Escreve <pasta>/comparacao.png (esquerda: base atual; direita: Blender) e <pasta>/comparacao-zoom.png
(um quarto do recorte ampliado 2×, onde se vê a diferença de detalhe).
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
    a = Image.open(d / "atual.png").convert("RGB")
    b = Image.open(d / "render.png").convert("RGB")
    a = a.resize(b.size, Image.LANCZOS)
    w, h = b.size
    side = Image.new("RGB", (w * 2 + 16, h), (20, 16, 12))
    side.paste(label(a.copy(), "base atual (Python)"), (0, 0))
    side.paste(label(b.copy(), "Blender"), (w + 16, 0))
    side.save(d / "comparacao.png")
    box = (w // 4, h // 4, w // 4 + w // 2, h // 4 + h // 2)
    za, zb = a.crop(box).resize((w, h), Image.LANCZOS), b.crop(box).resize((w, h), Image.LANCZOS)
    zoom = Image.new("RGB", (w * 2 + 16, h), (20, 16, 12))
    zoom.paste(label(za, "base atual, zoom 2x"), (0, 0))
    zoom.paste(label(zb, "Blender, zoom 2x"), (w + 16, 0))
    zoom.save(d / "comparacao-zoom.png")
    print("guardado:", d / "comparacao.png", "e", d / "comparacao-zoom.png")


if __name__ == "__main__":
    main()
