# Simulação v0.5 — nevoeiro de guerra

Mundos gerados com `[politica]` (ver world-map): **exemplo** (25 reinos, 3 continentes, 790 províncias, 9 por reino)
e **teste150** (150 reinos, 5 continentes, 2011 províncias, 4 por reino). 3 seeds × 100 turnos, GM simulado `pulse`
(Praga ativa nos turnos 10–40 e 70–100). Bots só atacam o que veem e mantêm 1–2 batedores a explorar; não usam espiões.

```
python -m sim.run --world ../world-map/build/<mundo>/data/world.json --turns 100 --seeds 3 --gm pulse
```

| | 25 reinos | 150 reinos |
|---|---|---|
| Primeiro contacto (mediana / 90 %) | turno 3 / turno 9 | turno 1 / turno 4 |
| Mapa conhecido por fação, turno 25 → 100 | 6,2 % → 8,7 % | 1,7 % → 3,0 % |
| Rumores por turno (todas as fações), Praga ativa | ~4 | ~0–2 |
| Batedores perdidos por corrida | 136 | 1124 |
| Perdido para a Praga no turno 100 | 40 % | 15 % |
| Reinos ativos no turno 100 | 23 / 25 | 117 / 150 |
| Tempo por turno (motor + bots) | ~0,02 s | ~0,25 s |
| Estado guardado (turno 30) | ~230 KB | ~935 KB |

## O que isto diz

1. **O contacto é quase imediato.** Com 30 % da terra ocupada à partida, os reinos começam a 2–4 regiões uns dos
   outros. O receio de "semanas sem encontrar ninguém" não se confirma nestes mapas. Só aconteceria com menos
   território inicial ou mapas com muito mais terra livre.
2. **Conhece-se muito pouco do mundo.** Mesmo ao fim de 100 turnos, cada fação conhece < 10 % do mapa. Os bots
   exploram mal (batedor ao acaso), por isso jogadores humanos devem conhecer mais. Mas o mundo vai ser sobretudo
   desconhecido, o que dá espaço ao GM e aos rumores.
3. **Os rumores quase não chegam a ninguém com os focos sugeridos.** Os focos sugeridos ficam o mais longe possível
   das capitais, muitas vezes a mais de 10 regiões (o alcance dos rumores). Com 150 reinos, abrir um foco não gera
   nenhum rumor no turno em que abre. Ou o GM escreve os seus próprios rumores, ou o alcance tem de crescer com o
   tamanho do mapa.
4. **O nevoeiro custa pouco à economia dos bots.** Comparação no mundo de 25 reinos: bots que veem tudo e sem
   batedores perdem 37 % do mundo para a Praga; com nevoeiro e batedores, 40 %. O resto da subida face à v0.4 (26 %)
   vem da nova partição do mapa, não do nevoeiro.
5. **Os batedores dos bots morrem muito** porque entram em regiões com exércitos que ainda não viram. Não é um
   problema de regras, mas mostra que o batedor é frágil: um jogador vai querer ver antes de entrar.
