# map-renderer

Renderizador partilhado do mapa-mundo: um ficheiro ES module (`renderer.js`), WebGL2 + Canvas 2D, sem dependências.
Usado pela demo do [world-map](../world-map/) e pelo [gm-panel](../gm-panel/).

**Camadas:** base pintada (`base.jpg`) → shader com cores de fação, fronteiras anti-aliased e Praga (a partir de
`regions.png` + duas tabelas que mudam por turno) → canvas 2D com rios, estradas, burgos, nomes e marcadores.

```js
import { createMapRenderer, PRAGA } from "../map-renderer/renderer.js";

const map = await createMapRenderer({ canvas, overlay, dataUrl: "data" });   // world.json, base.jpg, regions.png
map.setFactions([{ id: 1, name: "Waju", color: "#66c2a5" }, { id: PRAGA, name: "A Praga", color: "#3a1d40" }]);
map.setState({ owner, plague });       // arrays indexados pelo id da região; owner -1 = Praga; plague 0..1
map.setState({ fog });                 // nevoeiro por região: 0 desconhecida, 1 conhecida, 2 visível, 3 espiada/própria
map.setState({ fog: null });           // desliga o nevoeiro (vista do GM)
map.setMarkers([{ region: 115, kind: "suggestion" }, { region: 220, kind: "pending", label: "foco pendente" }]);
map.on("click", (regionId) => …);
map.on("hover", (regionId) => …);
map.focusOn(regionId, 3);              // centra e aproxima
map.setOptions({ borders: true, plague: true, rivers: true, labels: true });
```

O canvas ocupa o tamanho do contentor (ResizeObserver) e enquadra o mundo no primeiro tamanho real.
A Praga anima enquanto houver regiões infetadas, exceto com `prefers-reduced-motion`.

## Limites

- Até **4095 regiões** (tabela de regiões em textura 1024 × 4) e **254 fações** (a 255 está reservada à Praga).

## Nevoeiro

- **Desconhecida:** pergaminho por desenhar; sem rios, estradas, burgos nem nomes.
- **Conhecida:** relevo em tons lavados, com o último dono conhecido.
- **Visível / espiada / própria:** normal.
A transição é suave (campo calculado a partir das regiões à volta) e a água herda a visão das terras próximas.
O renderizador só esconde: quem decide o que cada jogador sabe é o servidor (ver turn-engine, `player_view`).
Os ficheiros do mapa (`base.jpg`, `world.json`) têm o mundo inteiro; num servidor real têm de ser servidos por
jogador (ver "Limitações" no README do world-map).

## Tiles da base

Se a pasta de dados tiver `tiles.json` (gerado por `world-map/blender/render_world.py`), o renderizador desenha os
tiles visíveis do nível de zoom certo numa textura do tamanho do ecrã e o shader usa-a por cima da `base.jpg`.
Enquanto um tile carrega, aparece o nível mais grosseiro (e, por baixo de tudo, a `base.jpg`). Guarda até 320 tiles
em memória. Com nevoeiro, só pede tiles que tocam regiões conhecidas (ou só mar). Sem `tiles.json`, tudo funciona
como antes, só com a `base.jpg`.

