# world-map

Mapa-mundo para jogos de estratégia por turnos: geografia gerada no [Azgaar](https://github.com/Azgaar/Fantasy-Map-Generator),
render próprio e determinístico (sem IA generativa).

**Pipeline:** relevo nosso (continentes, terra, ilhas) → Azgaar (clima, biomas, rios, nomes) → províncias e reinos
nossos → Python (base pintada + raster de regiões) → WebGL2 (fronteiras, cores de fação, Praga) + Canvas 2D (rios, nomes).

Mesmo ficheiro de mundo + mesma seed = mesmo mapa, píxel a píxel.

## Estrutura

```
worlds/<nome>.toml        seed e opções de geração de cada mundo (fonte de verdade)
tools/geography.py        relevo próprio: n.º exato de continentes, fração de terra, ilhas, mar interior
tools/export_azgaar.py    injeta o relevo no Azgaar (headless), verifica os continentes e descarrega o Full JSON
tools/partition.py        províncias e reinos próprios (todos os reinos com o mesmo n.º de províncias)
tools/build_world.py      Full JSON -> web/data/{world.json, base.jpg, regions.png}
tools/preview.py          imagem do mapa político, para verificar um mundo sem browser
blender/                  base renderizada no Blender, em tiles (estilo atlas) — ver blender/README.md
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

# 2. gerar (exemplo: 25 reinos, 3 continentes)
python tools/export_azgaar.py worlds/exemplo.toml build/exemplo        # ~20 s
python tools/build_world.py build/exemplo/world_full.json web/data --config worlds/exemplo.toml   # ~40 s
python tools/preview.py web/data build/exemplo/politica.png           # opcional: imagem para conferir

# 3. ver
cd .. && python -m http.server 8000    # a partir de modules/ → http://127.0.0.1:8000/world-map/web/
```

Para um mundo novo: copiar `worlds/exemplo.toml`, mudar a seed e as opções, repetir o passo 2.
O mundo antigo (`worlds/praga.toml`, províncias e estados do Azgaar) continua a funcionar sem `--config`.

## Opções do mundo

```toml
[world]
seed = "ex-aequo-1"         # mesma seed + mesmas opções = mesmo mundo

[mundo]
tamanho = "medio"           # pequeno | medio | grande | enorme

[geografia]
continentes = 3             # 1 a 8, número exato (verificado; se falhar, tenta outra variante da seed)
terra = 0.40                # fração do mapa que é terra (0.15 a 0.70, tolerância ±5 pontos)
ilhas = "poucas"            # nenhumas | poucas | muitas
mar_interior = false        # um mar fechado dentro do maior continente

[politica]
reinos = 25                 # 25, 50, 75, 100, 125 ou 150
territorio_inicial = 0.30   # fração das províncias que começa com dono; o resto são Terras Livres
```

**Províncias por reino (P)** = ⌊territorio_inicial × províncias ÷ reinos⌋. Uma província tem ~16 células do Azgaar,
por isso o número de províncias sai do tamanho e da terra. Valores medidos/estimados com `terra = 0.40` e
`territorio_inicial = 0.30`:

| tamanho | pontos | províncias | P com 25 reinos | P com 50 | P com 100 | P com 150 |
|---|---|---|---|---|---|---|
| pequeno | 20 K | ~500 | 6 | 3 | — | — |
| medio | 30 K | ~790 (medido) | 9 | 4 | 2 | — |
| grande | 50 K | ~1250 | 15 | 7 | 3 | 2 |
| enorme | 70 K | ~1750 (2011 medido com terra 0.45) | 21 | 10 | 5 | 3–4 |

"—" = não cabe (menos de 2 províncias por reino). O `export_azgaar.py` recusa logo esses pedidos e sugere um tamanho.
O tamanho do mundo em unidades fica sempre 1920 × 1080; o que muda é a densidade de células. Mais províncias =
províncias mais pequenas no ecrã (em `enorme`, ~20 px de lado com o mapa inteiro à vista).

**Como os reinos são colocados:** capitais só em terra habitável (acima da mediana de população), espalhadas por
todas as massas de terra em proporção à terra habitável de cada uma; cada reino cresce à vez, para a província livre
mais próxima da capital, evitando encostar a outro reino. Reinos com terra pobre (valor abaixo de 75 % da mediana)
recebem até +2 províncias. Ilhas pequenas e terra sobrante ficam livres. O relatório
`relatorio-politica.json` (junto ao `world.json`) mostra P, os reinos compensados e a dispersão de valor.

> A versão do Azgaar afeta o resultado. O mundo `praga` foi gerado com o Azgaar **v1.154.1**.
> Para reproduzir exatamente, fazer checkout dessa versão.

Testes da partição (sem Azgaar): `python -m unittest tools.test_partition`.

## Como funciona

- **Relevo injetado no Azgaar:** o `geography.py` desenha um mapa de alturas (PNG) e o exportador serve-o ao Azgaar
  como se fosse um dos relevos pré-feitos dele. O Azgaar trata do clima, biomas, rios, culturas e nomes.
  Os continentes são contados outra vez no resultado do Azgaar (`relatorio-geografia.json`).
- **Regiões de jogo:** com `[politica]`, províncias nossas (k-médias sobre as células, contíguas, de tamanho
  parecido). Sem ela, províncias do Azgaar + "Ermos" para terra sem província.
  O importador valida que a vizinhança é simétrica e que não há regiões isoladas.
- **Mar interior:** o Azgaar classifica água fechada como lago; lagos grandes (≥ 0,4 % da terra) passam a contar
  como mar (cor de mar, costas navegáveis).
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
| `factions[]` | `id`, `name`, `color`, `capital` (id da região; só em mundos com `[politica]`). 0 = terras livres |
| `regions[]` | `id` (= índice + 1), `kind` (`province`/`wild`), `name`, `owner`, `center`, `area`, `neighbors`, `biome`, `elevation`, `coastal`, `population` |
| `rivers[]`, `roads[]` | polilinhas em coordenadas do mundo |
| `burgs[]` | `name`, `x`, `y`, `pop`, `capital`, `port`, `region` |

## Limitações conhecidas

- **Desempenho:** testado em PC e telemóvel (2026-10-15), fluido em ambos. Não testado em Android de gama baixa.
  O shader faz ~70 leituras de textura por píxel; se for preciso, calcular o campo de distância às fronteiras
  uma vez por turno (render-to-texture).
- **Zoom alto**: base e IDs a 2 px/unidade. Acima de ~6× a base fica mole e as fronteiras ganham facetas.
  Correção prevista: tiles por nível de zoom, com a base renderizada no Blender.
- **Base:** a pintada em Python (`build_world.py`) é o ponto de partida; a final é renderizada no Blender em tiles
  (`blender/render_world.py --install` substitui a `base.jpg` e acrescenta `tiles/` e `tiles.json`).
- **Cores com 100+ reinos:** reinos vizinhos recebem cores afastadas, mas com 150 há inevitavelmente tons parecidos.
- **Nomes de província:** maior burgo da província; sem burgo, o nome da província do Azgaar com "do Norte",
  "Oriental", etc., e numerais (II, III) quando se repete. Em mapas grandes aparecem repetições ("Rovehol IV").
- **Latitude:** o Azgaar põe gelo nas latitudes altas; um continente a norte pode ficar meio gelado (fica livre,
  porque as capitais só vão para terra habitável).
- A simulação de turnos em `map.js` é só demonstração visual, não regras de jogo.
