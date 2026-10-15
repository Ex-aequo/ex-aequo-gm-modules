# Base do mapa renderizada no Blender (estilo atlas)

A base do mapa (relevo, florestas, povoações, mar) é renderizada no Blender, em tiles, e o renderizador do mapa
carrega só os tiles visíveis para o zoom atual. Fronteiras, cores dos reinos, Praga, nevoeiro e nomes continuam a
ser desenhados por cima, em tempo real. Estilo escolhido: **atlas** (decisão de 2026-10-15).

Tudo é gerado por código, sem assets externos nem IA: o mesmo mundo dá sempre as mesmas imagens.
Testado com o Blender **4.2 LTS** (https://www.blender.org/download/lts/4-2/).

## Mundo inteiro

```bash
cd modules/world-map
uv pip install -r requirements.txt            # numpy, scipy, pillow, numba (uma vez)

python blender/render_world.py build/exemplo/world_full.json build/exemplo/data build/tiles-exemplo --install
```

No Mac usa o Blender em `/Applications/Blender.app` e a GPU (Metal). É **retomável**: se parar a meio, voltar a
correr o mesmo comando continua onde ficou. `--install` copia no fim `tiles/`, `tiles.json` e a `base.jpg` nova
para a pasta de dados (a base antiga, pintada em Python, fica em `base-python.jpg`).

**Tempo (mundo de exemplo, 1920 × 1080 unidades, 5,3 px por unidade):** relevo global ~2 min; ~45 tiles com terra
de 1024 px, ~50 s cada aqui (2 núcleos, sem GPU, 32 amostras) — cerca de 40 min no total. Os tiles só de mar não
vão ao Blender.

O que sai em `build/tiles-<mundo>/`:

| Ficheiro | Conteúdo |
|---|---|
| `tiles/<z>/<x>_<y>.webp` | pirâmide de zoom, tiles de 512 px; `z = 0` é o nível de mais detalhe (5,3 px/unidade), cada nível seguinte tem metade |
| `tiles.json` | níveis, tamanho e, para cada tile, as regiões que toca (o servidor envia a cada jogador só tiles de regiões que ele conhece) |
| `base.jpg` | o mundo inteiro a 2 px por unidade: reserva enquanto os tiles carregam, e o que se vê com o mapa todo à vista |
| `mundo.jpg` | o mosaico completo, para ver de uma vez |
| `raw/`, `world_q.npz` | renders em bruto e o relevo global (cache; apagar para recalcular) |

## Como evita costuras entre tiles

- **Relevo, mar, cores e floresta** são calculados uma vez para o mundo inteiro (a 1/4 da resolução) e amostrados
  por cada tile em coordenadas do mundo.
- **Detalhe fino, clareiras e árvores** são funções das coordenadas do mundo (ruído e sorteios com hash): o mesmo
  ponto dá sempre a mesma árvore, em qualquer tile.
- **Casas** têm semente fixa por povoação.
- Cada tile é renderizado com **margem** (128 px de cada lado): as sombras do vizinho entram; a câmara corta-a.
- **Papel, tinta na costa e tom do atlas** são aplicados ao mosaico inteiro depois de juntar, não tile a tile.

## O relevo

`erosion.py`: erosão fluvial "stream power" (Braun & Willett 2013) sobre a rede de drenagem de um priority-flood —
a água escoa até ao mar e corta vales ramificados em proporção ao caudal; as montanhas recebem algum levantamento;
uma difusão leve arredonda as cristas. Depois, detalhe fino com ruído "erodido" e os vales dos rios do jogo marcados
de leve. A erosão por gotas de água foi experimentada e posta de parte (enchia depressões e criava "lagos" planos).

## Prova de um só recorte

Para experimentar luz, cores ou estilos sem renderizar o mundo:

```bash
python blender/export_tile.py build/exemplo/world_full.json build/exemplo/data build/blender-prova
for s in maqueta atlas sombrio; do
  /Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render_tile.py -- build/blender-prova --style $s
done
python blender/compare.py build/blender-prova        # base atual + cada estilo, inteiro e ampliado 2×
```

Opções do `render_tile.py` (depois do `--`): `--style maqueta|atlas|sombrio`, `--samples 96`, `--px 1024`,
`--no-trees`, `--cpu`, `--save-blend` (guarda a cena para abrir no Blender e mexer à mão), `--no-post`.

| Estilo | Luz | Árvores | Acabamento |
|---|---|---|---|
| maqueta | sol rasante de noroeste, branco | pequenas e densas | nenhum |
| **atlas** (escolhido) | sol mais alto e quente | grandes e espaçadas | papel, tinta na costa, cores mais vivas |
| sombrio | sol baixo e frio | escuras e densas | dessaturado, névoa nas terras baixas, vinheta |

## Limitações conhecidas

- **Nevoeiro:** um tile toca várias províncias; um jogador que conhece uma vê também a geografia das vizinhas no mesmo
  tile (nunca donos nem exércitos). Aceite (decisão de 2026-10-15); mascarar por jogador seria mais caro.
- **Neve:** nas zonas mais altas ainda ocupa muito.
- Estradas e rios continuam a ser desenhados por cima (canvas), não fazem parte do render.
