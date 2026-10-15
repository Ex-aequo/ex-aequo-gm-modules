# turn-engine

Motor de resolução de turnos do jogo Praga, segundo [docs/regras-nucleo.md](../../docs/regras-nucleo.md) (v0.3),
mais bots e uma simulação para pôr as regras sob pressão. Python 3.11+, só biblioteca padrão.

- **Determinístico:** o mesmo estado e as mesmas ordens dão sempre o mesmo resultado (`GameState.digest()`).
- **Validação na submissão:** `validate()` devolve as ordens aceites e uma mensagem por cada ordem recusada.
  O servidor volta a validar na resolução, com as mesmas regras.
- **Lê o mapa do módulo world-map** (`web/data/world.json`): vizinhanças, bioma, altitude, costa.

## Estrutura

```
praga/rules.py    todas as constantes das regras (um sítio só para calibrar)
praga/state.py    mapa estático, estado do jogo, arranque
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
# variantes de regras (qualquer campo de praga/rules.py):
python -m sim.run --world ../world-map/web/data/world.json \
    --set free_lands_resist=true --set plague_burnout=4 --set plague_equilibrium=0.25
```

O `world.json` gera-se com o módulo [world-map](../world-map/).

## O que a simulação faz

- 24 fações-bot (estilos rodam entre expansionista, construtor e defensor), arranque pequeno: capital + 2 regiões
  com ferro garantido; 6 focos de Praga afastados das capitais.
- Cada variante corre em várias seeds (`--seeds`); o resumo dá média e mínimo–máximo.
- 3 fações deixam de enviar ordens nos turnos 25, 40 e 60 (testa regência e dissolução).
- Entram jogadores novos nos turnos 20, 50 e 75, se houver lugar (teto de 25 ativas).
- Métricas por turno e por seed em `build/sim/runs.json`: % do mapa perdido para a Praga, contaminado e livre, fações ativas,
  maior e menor fação, índice de Gini, homens em armas, conquistas, surtos.

Resultados: [v0.2](../../docs/simulacao-v0.2.md), [v0.3](../../docs/simulacao-v0.3.md).

## Limites conhecidos (v0.1 do motor)

- Bots simples: os resultados são **direcionais**, não previsões. Um jogador humano negoceia, alia-se e planeia.
- Sem interceção de exércitos a meio do caminho, sem rios como fronteira defensiva, sem comércio entre jogadores.
- Um só mapa: as seeds variam o acaso, não a geografia. Testar outros mundos é o passo seguinte.
