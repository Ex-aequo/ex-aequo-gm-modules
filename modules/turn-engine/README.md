# turn-engine

Motor de resolução de turnos do jogo Praga, segundo [docs/regras-nucleo.md](../../docs/regras-nucleo.md) (v0.4),
mais bots e uma simulação para pôr as regras sob pressão. Python 3.11+, só biblioteca padrão.

- **Determinístico:** o mesmo estado e as mesmas ordens dão sempre o mesmo resultado (`GameState.digest()`).
- **Validação na submissão:** `validate()` devolve as ordens aceites e uma mensagem por cada ordem recusada.
  O servidor volta a validar na resolução, com as mesmas regras.
- **Ordens de GM** num canal próprio: `resolve_turn(state, world, rules, orders, gm_orders)` com
  `plague_state` (active/dormant), `plague_focus` (região) e `plague_intensity` (weak/normal/strong).
  Cada decisão do GM vai para os eventos do turno com texto de crónica.
- **Lê o mapa do módulo world-map** (`web/data/world.json`): vizinhanças, bioma, altitude, costa.

## Estrutura

```
praga/rules.py    todas as constantes das regras (um sítio só para calibrar)
praga/state.py    mapa estático, estado do jogo, arranque
praga/vision.py   nevoeiro (§8): visão, fotografias, vista do jogador, rumores
praga/orders.py   validação das 7 ordens e custos em pontos de comando
praga/engine.py   resolve_turn(): fases 1–9 do §5; Praga; regência, dissolução, eliminação, entrada tardia
praga/bots.py     bots expansionista / construtor / defensor (para teste, não são IA a sério)
sim/run.py        simulação de N turnos com métricas por turno
tests/            testes unitários
```

## Usar

```bash
cd modules/turn-engine
python -m unittest discover tests
python -m sim.run --world ../world-map/web/data/world.json --turns 200 --seeds 5 --out build/sim
# políticas de GM simuladas: never | always | pulse | leader
python -m sim.run --world ../world-map/web/data/world.json --gm pulse
# variantes de regras (qualquer campo de praga/rules.py):
python -m sim.run --world ../world-map/web/data/world.json --set plague_recede=5
```

O `world.json` gera-se com o módulo [world-map](../world-map/).

## O que a simulação faz

- Uma fação-bot por reino (estilos rodam entre expansionista, construtor e defensor). Arranque (`--start`):
  `world` (padrão em mundos com reinos próprios: o território do `world.json`, todos com o mesmo n.º de províncias)
  ou `small` (padrão nos mundos antigos: capital + 2 regiões). Ferro garantido nos dois. A Praga começa adormecida; uma política de GM simulada (`--gm`) decide quando desperta.
- Cada variante corre em várias seeds (`--seeds`); o resumo dá média e mínimo–máximo.
- 3 fações deixam de enviar ordens nos turnos 25, 40 e 60 (testa regência e dissolução).
- Entram jogadores novos nos turnos 20, 50 e 75, se houver lugar (teto de 25 ativas).
- Métricas por turno e por seed em `build/sim/runs.json`: % do mapa perdido para a Praga, contaminado e livre, fações ativas,
  maior e menor fação, índice de Gini, homens em armas, conquistas, surtos.

Resultados: [v0.2](../../docs/simulacao-v0.2.md), [v0.3](../../docs/simulacao-v0.3.md), [v0.4](../../docs/simulacao-v0.4.md), [v0.5](../../docs/simulacao-v0.5.md), [v0.6](../../docs/simulacao-v0.6.md).

**Reinos-guardiões (§7):** `new_game(..., players={...})` marca os reinos com jogador; os outros são guardiões e as
ordens deles saem do motor (`bots.guardian_orders`) em cada `resolve_turn`. `claim_kingdom` dá a quem chega o guardião
mais intacto. Na simulação, `--players 0.6` deixa 40 % dos reinos como guardiões.

**Nevoeiro (§8):** o que um jogador recebe sai de `vision.player_view(state, world, rules, fid)`, construída só a partir
das fotografias da fação. O teste `test_player_view_does_not_depend_on_hidden_state` muda tudo o que a fação não vê e
verifica que a vista fica igual. Qualquer servidor deve enviar só isto aos jogadores.

## Limites conhecidos (v0.1 do motor)

- Bots simples: os resultados são **direcionais**, não previsões. Um jogador humano negoceia, alia-se e planeia.
- Sem interceção de exércitos a meio do caminho, sem rios como fronteira defensiva, sem comércio entre jogadores.
- Um só mapa: as seeds variam o acaso, não a geografia. Testar outros mundos é o passo seguinte.
