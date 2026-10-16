# forge-view

`ForgeMap.tsx`: o `MapView` do Province-Forge (`vendor/province-forge/src/view`) num componente React, com a camada
do jogo por cima — exércitos (escudo), forças estranhas, agentes (losango), alvos, focos da Praga e as setas das ordens
(mover, atacar, agentes), com tamanho constante no ecrã e pelo lado mais curto da volta do mundo. Guarda a câmara entre
turnos e foca a capital da primeira vez.

Usado pelo [player-client](../player-client/) e pelo [gm-panel](../gm-panel/) (alias `@forge-view` nos `vite.config.ts`).
Ids do Province-Forge: a província `rid` do Praga é a região `rid - 1`.
