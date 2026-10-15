# Simulação v0.4 — a Praga como evento do GM

**Data:** 2026-10-15 · **Mundo:** `praga` (seed 424242, 627 regiões) · **Método:** 5 seeds × 200 turnos por política.
O GM real é uma pessoa; aqui simulam-se quatro estilos de condução para medir as consequências de cada um.

## Políticas simuladas

| Política | O que faz |
|---|---|
| **Nunca** | a Praga nunca desperta (mundo sem Praga, para comparação) |
| **Sempre** | desperta no turno 10 com os 6 focos sugeridos e nunca adormece |
| **Pulsos** | 30 turnos ativa, 30 adormecida; um foco novo em cada despertar |
| **Anti-líder** | desperta quando uma fação passa 8% do mapa, com um foco perto dela; adormece quando a Praga passa 20% do mapa ou o líder desce abaixo de 6% |

## Resultados (média de 5 seeds)

| Política | Praga ativa | Perdido t100 | Perdido t200 | Maior fação t200 | Sobrevivência perto / longe |
|---|---|---|---|---|---|
| Nunca | 0% dos turnos | 0% | 0% | 52 regiões (8%) | 96% / 88% |
| Sempre | 96% | 80% | 93% | 10 | 44% / 32% |
| Pulsos 30/30 | 50% | 27% | 69% | 29 | 93% / 63% |
| Anti-líder | 15% | 4% | 23% (0–47%) | 48 | 93% / 82% |

## Leitura

1. **A Praga é um trinco.** O que se perde com ela ativa não volta quando adormece. Os bots quase não reconquistam
   regiões perdidas, por isso cada turno ativo custa em média **~0,7% do mapa de forma permanente**
   (pulsos: ~95 turnos ativos → 69%; anti-líder: ~30 turnos ativos → 23%).
   Regra prática para o GM: **100 turnos ativos ≈ dois terços do mundo**.
2. **Sem Praga não há colapso, mas há um líder a crescer devagar**: a maior fação passa de 10 para 52 regiões em 200
   turnos. Não é uma bola de neve descontrolada, mas é um crescimento contínuo.
3. **Usar a Praga contra o líder resulta pouco de forma direta.** Na política anti-líder o líder acaba com 48 regiões
   em vez de 52: o foco cai em Terras Livres perto dele e consome sobretudo o espaço para onde ia crescer. Para travar
   um líder, o GM teria de abrir o foco *dentro* do território dele, o que é muito visível na crónica.
4. **Variância alta com o GM reativo** (0% a 47% no turno 200): pequenas diferenças decidem se e quando o GM intervém.
   Com um GM humano, isso é narrativa; com regras automáticas seria injusto.
5. **Jogadores humanos devem reconquistar mais do que os bots.** O trinco será menos rígido em jogo real. Se não for,
   uma ordem de GM "a Praga recua" seria a ferramenta em falta (não implementada: decisão tua de que adormecer não cura).
