# Simulação das regras v0.2 — resultados

**Data:** 2026-10-15 · **Mundo:** `praga` (seed 424242, 627 regiões) · **Motor:** `modules/turn-engine`
**Arranque:** 24 fações com capital + 2 vizinhas; 3 abandonos (turnos 25, 40, 60); entradas nos turnos 20, 50, 75.

> Os bots são simples. Estes números mostram **tendências e falhas de regras**, não o equilíbrio final de um jogo
> com humanos. Cada variante é uma corrida determinística num só mapa.

## Variantes

| | A — regras do doc | B — recrutar só com ouro | C — B sem teto da Praga | D — B durante 200 turnos |
|---|---|---|---|---|
| Praga perdida, turno 50 | 27% | 26% | 23% | 26% |
| Praga perdida, turno 100 | 40% | 35% | 48% | 35% |
| Praga perdida, turno 200 | — | — | — | **49%** (+39% contaminado) |
| Maior fação, turno 100 | 33 regiões (5%) | 58 (9%) | 33 (5%) | 58 (9%) → 18 no t200 |
| Gini das fações, turno 100 | 0,60 | 0,64 | 0,69 | 0,58 no t200 |
| Homens em armas, turno 100 | ~7 200 | ~12 400 | — | — |

Turno 100 ≈ 200 dias de jogo real; turno 200 ≈ 13 meses.

## Conclusões

### 1. A posição inicial decide o jogo (problema grave)
Na variante B, das 8 fações que jogaram até ao fim e começaram a ≤10 regiões da origem da Praga, **7 acabaram sem
terras**. Das 13 que começaram longe, **nenhuma**. O padrão repete-se em A e C.
**Consequência:** é preciso uma regra de colocação inicial (distância mínima aos Ermos) ou uma Praga que não nasça
num único ponto do mapa.

### 2. O equilíbrio da Praga não segura
Com o "teto" ativo, a Praga passa dos 35% previstos (40% em A) e ao turno 200 tem 49% perdido e 39% contaminado:
quase o mapa todo. Sem teto (C) chega aos 48% em 100 turnos.
**Causa:** o teto só trava o alastramento; regiões já contaminadas continuam a crescer +8/turno até ao colapso.
**Consequência:** a pergunta em aberto "a Praga pode consumir o mundo?" tem resposta prática: **com as regras atuais,
sim, em cerca de um ano**, mesmo com o mecanismo de equilíbrio.

### 3. Ferro obrigatório para recrutar trava 17 de 24 fações
No arranque, 17 fações não têm nenhuma região com ferro. Com a regra do documento (A) há cerca de metade dos homens em
armas, e construtores e defensores definham. Uma fação chegou a acumular 3 658 de ouro sem uso.
**Opções:** garantir ferro no arranque, tornar o ferro necessário só para tropas melhores/fortificações, ou haver
mercado/comércio desde o início.

### 4. A Praga trava o jogador dominante, talvez demais
O líder chega a 9% do mapa ao turno 100 e cai para 3% ao turno 200 porque a Praga o consome. O travão funciona; o
problema é que atinge todos (conclusão 2).

### 5. Entradas, regência e dissolução funcionam mecanicamente
Regência 3 turnos depois da última ordem, dissolução aos 10, lugares reabertos e preenchidos. Um dos jogadores novos
foi eliminado 39 turnos depois de entrar (variante A): a proteção de 5 turnos não chega quando a vizinhança é a Praga.

## O que fica para decidir

1. **Colocação inicial** — distância mínima à origem da Praga? Vários focos pequenos em vez de um?
2. **Crescimento da Praga** — também escalado pelo equilíbrio, ou decaimento natural em regiões com ordem pública 3?
3. **Ferro** — obrigatório para recrutar, ou só para tropas/obras melhores?

Calibrado na simulação, sem decisão tua: guarnição das Terras Livres = 60 + 0,8 × população (era 120 + 2 × pop,
forte demais — os exércitos iniciais não conseguiam expandir).
