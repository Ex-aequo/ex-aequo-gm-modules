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
map.setMarkers([{ region: 115, kind: "suggestion" }, { region: 220, kind: "pending", label: "foco pendente" }]);
map.on("click", (regionId) => …);
map.on("hover", (regionId) => …);
map.focusOn(regionId, 3);              // centra e aproxima
map.setOptions({ borders: true, plague: true, rivers: true, labels: true });
```

O canvas ocupa o tamanho do contentor (ResizeObserver) e enquadra o mundo no primeiro tamanho real.
A Praga anima enquanto houver regiões infetadas, exceto com `prefers-reduced-motion`.
