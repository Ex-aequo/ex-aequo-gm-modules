"""Gera um mundo no Azgaar (servidor local, headless) a partir de worlds/<nome>.toml e descarrega o Full JSON.

Uso:
    python tools/export_azgaar.py worlds/praga.toml build/praga/world_full.json

Requer o Azgaar a correr localmente (ver README do módulo):
    npx vite --port 5173 --host 127.0.0.1   # dentro do repositório do Azgaar
"""
import sys
import tomllib
from pathlib import Path

from playwright.sync_api import sync_playwright

if len(sys.argv) != 3:
    sys.exit(__doc__)

cfg = tomllib.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)

seed = str(cfg["world"]["seed"])
az = cfg["azgaar"]
W, H = int(az["width"]), int(az["height"])
BASE = az.get("url", "http://127.0.0.1:5173/Fantasy-Map-Generator/")
READY = "() => window.pack && pack.provinces && pack.provinces.length > 5 && pack.cells && pack.cells.province"

# "pins" = opções bloqueadas que o Azgaar não volta a sortear num mapa novo
pins = {
    "points": int(az["density"]),
    "mapWidth": W,
    "mapHeight": H,
    "statesNumber": int(az["states"]),
    "provincesRatio": int(az["provinces_ratio"]),
}
if az.get("template"):
    pins["template"] = az["template"]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": W, "height": H}, accept_downloads=True)
    page.goto(BASE)
    page.wait_for_function(READY, timeout=180_000)
    page.evaluate("pins => localStorage.setItem('fmg-locks', JSON.stringify(pins))", pins)
    page.goto(f"{BASE}?seed={seed}")
    page.wait_for_function(READY, timeout=300_000)
    page.wait_for_timeout(2000)
    stats = page.evaluate(
        "() => ({cells: pack.cells.i.length,"
        " states: pack.states.filter(s => !s.removed).length,"
        " provinces: pack.provinces.filter(p => p && !p.removed).length})"
    )
    print("gerado:", stats)
    with page.expect_download(timeout=300_000) as dl:
        page.evaluate("() => window.exportToJson('Full')")
    dl.value.save_as(out)
    print("guardado:", out)
    browser.close()
