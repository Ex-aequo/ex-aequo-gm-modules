# player-client — o frontend dos jogadores

React + Vite + o `map-renderer` partilhado. Fala só com `modules/game-server` (`/api/player/...` e `/api/map/...`).

- Entrada com conta; o GM é enviado para `/gm/`.
- Mapa com o nevoeiro do servidor, exércitos (escudo), forças estranhas vistas, agentes (losango) e as setas das
  ordens.
- Todas as ordens: mover (clicar 1–2 regiões), atacar, guarnecer, purgar, construir, recrutar, batedores e espiões,
  posturas. O servidor valida cada alteração; as recusadas aparecem com o motivo.
- Relê o estado de 20 em 20 s; quando o turno muda, recarrega o mapa (o que se conhece mudou).

Compilar: `npm install && npm run build` (o `game-server` serve `dist/`). Em desenvolvimento: `npm run dev`, com o
servidor em `localhost:8000`.
