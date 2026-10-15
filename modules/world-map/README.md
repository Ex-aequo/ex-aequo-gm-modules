# world-map

Mapa-mundo para jogos de estratégia por turnos: geografia gerada no [Azgaar](https://github.com/Azgaar/Fantasy-Map-Generator),
render próprio e determinístico (sem IA generativa).

**Pipeline:** Azgaar (dados) → Python (base pintada + raster de regiões) → WebGL2 (fronteiras, cores de fação, Praga) + Canvas 2D (rios, nomes).

Mesmo ficheiro de mundo + mesma seed = mesmo mapa, píxel a píxel.

## Estrutura

```
worlds/<nome>.toml        seed e opções de geração de cada mundo (fonte de verdade)
tools/export_azgaar.py    gera o mundo no Azgaar (headless) e descarrega o Full JSON
tools/build_world.py      Full JSON -> web/data/{world.json, base.jpg, regions.png}
tools/build_page.py       junta index.html + map.js numa página única (build/dist/)
web/index.html, map.js    demo interativa (o desenho do mapa vem do módulo map-renderer)
```

`build/` e `web/data/` são gerados e não vão para o git.

## Gerar e ver um mundo

```bash
# 0. dependências (uma vez)
pip install -r requirements.txt && playwright install chromium

# 1. Azgaar local, noutro terminal (uma vez)
git clone https://github.com/Azgaar/Fantasy-Map-Generator.git fmg
cd fmg && npm ci --ignore-scripts && npx vite --port 5173 --host 127.0.0.1

# 2. gerar
python tools/export_azgaar.py worlds/praga.toml build/praga/world_full.json
python tools/build_world.py build/praga/world_full.json web/data      # ~40 s

# 3. ver
cd .. && python -m http.server 8000    # a partir de modules/ → http://127.0.0.1:8000/world-map/web/
```

Para um mundo novo: copiar `worlds/praga.toml`, mudar a seed e as opções, repetir o passo 2.

> A versão do Azgaar afeta o resultado. O mundo `praga` foi gerado com o Azgaar **v1.154.1**.
> Para reproduzir exatamente, fazer checkout dessa versão.

## Como funciona

- **Regiões de jogo = províncias do Azgaar.** Terra sem província vira "Ermos" (origem da Praga).
  O importador valida que a vizinhança é simétrica e que não há regiões isoladas.
- **regions.png**: cada píxel guarda o ID da região (R + G×256; 0 = água). As fronteiras usam coordenadas
  deformadas por ruído para não parecerem arestas retas de Voronoi.
- **Shader**: lê o ID do píxel e duas tabelas (dono e praga por região; cor por fação). Um turno novo só reenvia
  estas tabelas (~4 KB), nunca as imagens.
- **Fronteiras**: campo bilinear "mesmo dono" com gradiente analítico → linhas anti-aliased de largura constante no ecrã.
- **Praga**: valor por região, suavizado entre vizinhos e recortado por ruído animado → massa orgânica com margem viva.

## Formato de `world.json`

| Campo | Conteúdo |
|---|---|
| `width`, `height`, `rasterScale` | tamanho do mundo e píxeis de raster por unidade |
| `factions[]` | `id`, `name`, `color` (0 = terras livres) |
| `regions[]` | `id` (= índice + 1), `kind` (`province`/`wild`), `name`, `owner`, `center`, `area`, `neighbors`, `biome`, `elevation`, `coastal`, `population` |
| `rivers[]`, `roads[]` | polilinhas em coordenadas do mundo |
| `burgs[]` | `name`, `x`, `y`, `pop`, `capital`, `port`, `region` |

## Limitações conhecidas

- **Desempenho:** testado em PC e telemóvel (2026-10-15), fluido em ambos. Não testado em Android de gama baixa.
  O shader faz ~70 leituras de textura por píxel; se for preciso, calcular o campo de distância às fronteiras
  uma vez por turno (render-to-texture).
- **Zoom alto**: base e IDs a 2 px/unidade. Acima de ~6× a base fica mole e as fronteiras ganham facetas.
  Correção prevista: tiles por nível de zoom, com a base renderizada no Blender.
- **A base pintada em Python é provisória** — serve para validar a direção visual.
- A simulação de turnos em `map.js` é só demonstração visual, não regras de jogo.
