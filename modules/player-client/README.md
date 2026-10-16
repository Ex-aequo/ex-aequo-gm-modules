# player-client — o frontend dos jogadores

React + Vite + o mapa do Province-Forge (via [forge-view](../forge-view/)). Fala só com `modules/game-server`
(`/api/player/...` e `/api/map/...`).

- Entrada com conta; o GM é enviado para `/gm/`.
- Mapa no estilo do Province-Forge com o nevoeiro do servidor (cinzento onde nunca esteve, véu onde só tem uma vista
  antiga), exércitos (escudo), forças estranhas vistas, agentes (losango) e as setas das ordens.
- Cartão da província com terreno e recurso principal (e o que o recurso faz).
- Todas as ordens: mover (clicar 1–2 regiões), atacar, guarnecer, purgar, construir, recrutar, batedores e espiões,
  posturas. O servidor valida cada alteração; as recusadas aparecem com o motivo.
- Relê o estado de 20 em 20 s; quando o turno muda, recarrega o mapa (o que se conhece mudou).

Compilar (precisa do submódulo `vendor/province-forge`): `npm install && npm run build` (o `game-server` serve `dist/`). Em desenvolvimento: `npm run dev`, com o
servidor em `localhost:8000`.
