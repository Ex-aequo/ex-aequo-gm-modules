"""Gera um mundo no Azgaar (servidor local, headless) a partir de worlds/<nome>.toml e descarrega o Full JSON.

Uso:
    python tools/export_azgaar.py worlds/exemplo.toml build/exemplo
Escreve em build/exemplo/: world_full.json, geografia.png (se houver [geografia]) e relatorio-geografia.json.

Requer o Azgaar a correr localmente (ver README do módulo):
    npx vite --port 5173 --host 127.0.0.1   # dentro do repositório do Azgaar

Dois formatos de ficheiro de mundo:
  - [azgaar]: opções diretas do Azgaar (modelo de relevo dele, nº de estados, rácio de províncias) — ex.: praga.toml
  - [mundo] + [geografia] + [politica]: relevo desenhado por nós (continentes exatos) e reinos equilibrados
"""
from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geography import GeoOptions, generate  # noqa: E402
from partition import CELLS_PER_PROVINCE, KINGDOM_CHOICES  # noqa: E402

BASE = "http://127.0.0.1:5173/Fantasy-Map-Generator/"
READY = "() => window.pack && pack.provinces && pack.provinces.length > 1 && pack.cells && pack.cells.province"
CUSTOM_ID = "praga-custom"     # nome do relevo injetado; o Azgaar vai buscá-lo a ./heightmaps/<nome>.png

# tamanhos do mundo: o tamanho em unidades fica fixo (o renderizador não passa de 4096 px de textura);
# o que cresce é a densidade de células, e por isso o número de províncias possíveis
SIZES = {"pequeno": 5, "medio": 6, "grande": 8, "enorme": 10}     # densidade Azgaar (20K, 30K, 50K, 70K pontos)
POINTS = {5: 20_000, 6: 30_000, 8: 50_000, 10: 70_000}
W, H = 1920, 1080


def azgaar_land_stats(page) -> dict:
    return page.evaluate("""() => {
      const land = pack.features.filter(f => f && f.land);
      const total = land.reduce((s, f) => s + f.cells, 0);
      const conts = land.filter(f => f.cells / total >= 0.02).map(f => +(100 * f.cells / total).toFixed(1));
      return {continents: conts.sort((a, b) => b - a), islands: land.length - conts.length,
              landCells: grid.cells.h.filter(h => h >= 20).length, cells: grid.cells.h.length,
              states: pack.states.filter(s => s.i && !s.removed).length};
    }""")


def run_azgaar(pins: dict, seed: str, heightmap_png: bytes | None, out_json: Path) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, accept_downloads=True)
        if heightmap_png is not None:
            ctx.route(f"**/heightmaps/{CUSTOM_ID}.png",
                      lambda route: route.fulfill(status=200, content_type="image/png", body=heightmap_png))
        page = ctx.new_page()
        page.goto(BASE)
        page.wait_for_function(READY, timeout=180_000)
        page.evaluate("p => localStorage.setItem('fmg-locks', JSON.stringify(p))", pins)
        page.goto(f"{BASE}?seed={seed}")
        page.wait_for_function(READY, timeout=600_000)
        page.wait_for_timeout(2500)
        stats = azgaar_land_stats(page)
        with page.expect_download(timeout=600_000) as dl:
            page.evaluate("() => window.exportToJson('Full')")
        dl.value.save_as(out_json)
        browser.close()
    return stats


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    cfg = tomllib.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    seed = str(cfg["world"]["seed"])

    if "azgaar" in cfg:                      # formato antigo: tudo decidido pelo Azgaar
        az = cfg["azgaar"]
        pins = {"points": int(az["density"]), "mapWidth": int(az["width"]), "mapHeight": int(az["height"]),
                "statesNumber": int(az["states"]), "provincesRatio": int(az["provinces_ratio"])}
        if az.get("template"):
            pins["template"] = az["template"]
        stats = run_azgaar(pins, seed, None, out / "world_full.json")
        print("gerado:", stats)
        return

    size = cfg.get("mundo", {}).get("tamanho", "medio")
    if size not in SIZES:
        sys.exit(f"[mundo] tamanho tem de ser um de {list(SIZES)}")
    reinos = int(cfg.get("politica", {}).get("reinos", 25))
    opt = GeoOptions.from_toml(cfg)
    # verificação antes de gerar: cabem os reinos pedidos neste tamanho de mapa?
    share = float(cfg.get("politica", {}).get("territorio_inicial", 0.30))
    est = POINTS[SIZES[size]] * opt.land / CELLS_PER_PROVINCE
    if reinos not in KINGDOM_CHOICES:
        sys.exit(f"[politica] reinos tem de ser um de {KINGDOM_CHOICES}")
    if share * est / reinos < 2:
        fits = [s for s in SIZES if share * POINTS[SIZES[s]] * opt.land / CELLS_PER_PROVINCE / reinos >= 2.2]
        sys.exit(f"com tamanho '{size}' e terra {opt.land:.0%} há ~{est:.0f} províncias: não chegam para {reinos} reinos "
                 f"com 2 províncias cada. Experimenta tamanho {fits[0] if fits else 'enorme com mais terra'}.")
    print(f"estimativa: ~{est:.0f} províncias, ~{int(share * est // reinos)} por reino")
    pins = {"points": SIZES[size], "mapWidth": W, "mapHeight": H, "template": CUSTOM_ID,
            "statesNumber": min(reinos, 200), "provincesRatio": 100}

    report = {"pedido": {"tamanho": size, "continentes": opt.continents, "terra": opt.land, "ilhas": opt.islands,
                         "mar_interior": opt.inland_sea}, "tentativas": []}
    geo_seed = seed
    for attempt in range(4):
        geo, geo_attempts = generate(opt, geo_seed)
        report["tentativas"].append({"relevo": geo.seed, "tentativas_relevo": len(geo_attempts),
                                     "continentes_relevo": geo.continents, "terra_relevo": geo.land})
        print(f"relevo {geo.seed}: continentes {geo.continents} · terra {geo.land:.0%} · ilhas {geo.islands}")
        stats = run_azgaar(pins, seed, geo.png(), out / "world_full.json")
        report["tentativas"][-1]["azgaar"] = stats
        print(f"azgaar: continentes {stats['continents']} · ilhas {stats['islands']} · estados {stats['states']}")
        if len(stats["continents"]) == opt.continents:
            geo.preview().save(out / "geografia.png")
            report["obtido"] = {"continentes": stats["continents"], "ilhas": stats["islands"],
                                "terra": round(stats["landCells"] / stats["cells"], 3), "relevo": geo.seed,
                                "notas": geo.notes}
            break
        # a conversão para as células do Azgaar juntou ou partiu continentes: tentar outro relevo
        geo_seed = f"{seed}-az{attempt + 1}"
    else:
        report["obtido"] = {"erro": "o Azgaar não preservou os continentes em 4 tentativas; usada a última"}
    (out / "relatorio-geografia.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print("guardado:", out / "world_full.json")


if __name__ == "__main__":
    main()
