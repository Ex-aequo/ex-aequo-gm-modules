# turn-engine

Motor de resolução de turnos do jogo Praga, segundo [docs/regras-nucleo.md](../../docs/regras-nucleo.md) (v0.2),
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
python -m sim.run --world ../world-map/web/data/world.json --turns 100 --out build/sim
# variantes de regras:
python -m sim.run --world ../world-map/web/data/world.json --set 'recruit_cost_per_100={"gold": 15}'
python -m sim.run --world ../world-map/web/data/world.json --no-cap      # Praga sem equilíbrio dinâmico
```

O `world.json` gera-se com o módulo [world-map](../world-map/).

## O que a simulação faz

- 24 fações-bot (estilos rodam entre expansionista, construtor e defensor), arranque pequeno: capital + 2 vizinhas.
- 3 fações deixam de enviar ordens nos turnos 25, 40 e 60 (testa regência e dissolução).
- Entram jogadores novos nos turnos 20, 50 e 75, se houver lugar (teto de 25 ativas).
- Métricas por turno em `build/sim/metrics.json`: % do mapa perdido para a Praga, contaminado e livre, fações ativas,
  maior e menor fação, índice de Gini, homens em armas, conquistas, surtos.

Resultados e conclusões: [docs/simulacao-v0.2.md](../../docs/simulacao-v0.2.md).

## Limites conhecidos (v0.1 do motor)

- Bots simples: os resultados são **direcionais**, não previsões. Um jogador humano negoceia, alia-se e planeia.
- Sem interceção de exércitos a meio do caminho, sem rios como fronteira defensiva, sem comércio entre jogadores.
- Uma única seed de mundo por agora; variar mapas e seeds é o passo seguinte para ter margens de erro.
