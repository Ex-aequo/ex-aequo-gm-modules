# Simulação das regras v0.3 — resultados

**Data:** 2026-10-15 · **Mundo:** `praga` (seed 424242, 627 regiões) · **Motor:** `modules/turn-engine`
**Método:** cada variante corre **5 seeds × 200 turnos** (~13 meses de jogo real). Valores = média das 5 corridas.
Arranque igual à v0.2: 24 fações-bot, 3 abandonos, entradas nos turnos 20, 50 e 75.

## O que mudou desde a v0.2 (as tuas decisões)

- **1B** — 6 focos de Praga, colocados a ≥6 regiões de qualquer capital (os Ermos iniciais ficavam a 3–5).
- **2B** — recuo de 3/turno em regiões com dono, ordem pública 3 e sem fome. O "teto" da v0.2 fica desligado.
- **3A** — ferro obrigatório para recrutar e garantido no arranque (região com ferro ou veio menor na capital).

## Critérios de sucesso combinados antes de correr

| Critério | Resultado |
|---|---|
| Sobreviver não depender de começar perto da Praga | ✅ 33% perto vs 35% longe (v0.2: 1 em 8 vs 13 em 13) |
| Todas as fações conseguem recrutar no arranque | ✅ 24/24 com ferro (13 próprio, resto por região a 2 passos ou veio menor) |
| Praga estável entre 15% e 35% do mapa até ao turno 200 | ❌ com as regras decididas chega a **93%** |

## Porque falhou o terceiro critério

O recuo só funciona em terras **com dono** bem governadas. No arranque, ~80% do mapa são Terras Livres sem defesa, e
6 focos espalhados comem-nas depressa. Daí em diante a Praga só tem realimentação positiva: mais território perdido
alastra mais. Nenhuma regra trava a Praga em proporção ao tamanho que já tem.

## Alternativas testadas (desligadas por defeito no motor)

| Variante | Perdido t100 | Perdido t200 | Contaminado t200 | Sobrevivência perto / longe |
|---|---|---|---|---|
| Regras decididas (v0.3) | 82% | 93% | 1% | 33% / 35% |
| + Terras Livres resistem | 27% | 79% | 8% | 80% / 52% |
| + extinção (−4/turno nas perdidas) | 63% | 71% | 22% | 47% / 35% |
| 3 focos em vez de 6 | 71% | 92% | 1% | 30% / 38% |
| + Terras Livres resistem + extinção | 17% | 53% | 28% | 98% / 62% |
| + pressão de equilíbrio (alvo 25%) | 57% | 64% | 8% | 80% / 82% |
| **+ Livres resistem + extinção + equilíbrio** | **33%** | **39%** | **31%** | **91% / 68%** |

Flags: `--set free_lands_resist=true`, `--set plague_burnout=4`, `--set plague_foci=3`, `--set plague_equilibrium=0.25`.

## Leitura

1. **Só a combinação das três travas segura a Praga**: 33% no turno 100 e 39% no turno 200, a subir devagar (+6 pontos
   em 100 turnos). Não é estabilidade perfeita, mas é a primeira variante em que o mundo não acaba.
2. **Há um custo:** cerca de 31% do mapa fica permanentemente contaminado. Somando o perdido, ~70% das regiões vivem com
   a Praga. Pode ser bom para o tema; pode ser cansativo de gerir.
3. **A pressão de equilíbrio é invisível.** Se os jogadores perceberem que "quanto mais a combatemos, mais forte fica",
   parece batota. Se for usada, deve ser explicada no jogo (por exemplo, "a Praga alimenta-se do vazio").
4. **Os bots purgam pouco.** Jogadores humanos vão combater a Praga com mais vontade, por isso estes números são
   provavelmente o cenário pessimista.
5. **Fações em continentes sem focos** sobrevivem menos do que as que estão perto (68% vs 91% na melhor variante): ali a
   ameaça é a guerra entre bots expansionistas, não a Praga. Vale a pena olhar quando houver regras de diplomacia.

## Decisão pendente

Ver [regras-nucleo.md §6](regras-nucleo.md): A (três travas), B (sem a pressão invisível) ou C (a Praga pode vencer).
