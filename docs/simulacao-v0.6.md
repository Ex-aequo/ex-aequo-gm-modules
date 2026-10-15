# Simulação v0.6 — reinos-guardiões, 25 e 50 reinos

Sem metas: isto é informação para o GM, não critério de aprovação (decisão de 2026-10-15).
3 seeds × 100 turnos, GM simulado `pulse` (Praga ativa nos turnos 10–40 e 70–100). "Jogadores" são bots com estilo
(expansionista, construtor, defensor) a fazer de pessoas; "guardiões" são os reinos sem jogador (§7).
Entram jogadores novos nos turnos 20, 50 e 75; três jogadores abandonam nos turnos 25, 40 e 60.

```
python -m sim.run --world <world.json> --turns 100 --seeds 3 --gm pulse --players 0.6
```

| | 25 reinos, todos jogadores | 25 reinos, 60 % jogadores | 50 reinos, todos jogadores | 50 reinos, 60 % jogadores |
|---|---|---|---|---|
| Mundo | exemplo (790 prov., 9/reino) | exemplo | teste50 (1327 prov., 7/reino) | teste50 |
| Perdido para a Praga, turno 100 | 14 % | 16 % | 20 % | 22 % |
| Regiões médias por jogador, turno 1 → 100 | 9,5 → 15,8 | 9,6 → 15,5 | 7,5 → 11,0 | 7,4 → 10,8 |
| Regiões médias por guardião, turno 1 → 100 | — | 9,4 → 7,8 | — | 7,5 → 6,3 |
| Reinos recebidos por quem chega (regiões) | 4–55 | 12–42 | 7–29 | 9–28 |
| Rumores por turno com a Praga ativa (todas as fações) | ~5–6 | ~4–6 | ~17–19 | ~17–19 |
| Primeiro contacto (mediana) | turno 3 | turno 4 | turno 4 | turno 5 |

## O que isto diz

1. **Os guardiões encolhem devagar.** Perdem ~15–20 % do território em 100 turnos para jogadores agressivos e
   recuperam um pouco expandindo para Terras Livres. Não desaparecem: nenhum guardião foi eliminado nestas corridas.
2. **O que quem chega recebe depende do momento.** Com todos os lugares ocupados por jogadores, os únicos guardiões
   são reinos abandonados — e esses tanto podem ser enormes (55 regiões, um jogador que cresceu e saiu) como migalhas
   (4 regiões). Com 40 % de guardiões desde o início, a variação é menor (9–42).
3. **Os rumores chegam agora.** Com focos e rumores em distância real, um foco gera 4–19 rumores por turno, contra
   0–2 na v0.5.
4. **A Praga fez menos estragos que na v0.5** (14–22 % contra 40 % no mundo de 25). Os focos sugeridos ficam agora
   mais perto dos reinos, que purgam cedo. Se o GM quiser uma Praga que cresce sem oposição, tem de abrir focos longe
   — que é uma escolha dele, não das regras.
5. **Reinos abandonados não deixam buracos.** Em vez de terra livre com ordem pública 0 (que a Praga comia), ficam
   guardiões que purgam. Isto também contribui para a Praga mais fraca.
