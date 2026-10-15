# Praga — Regras núcleo (rascunho v0.1)

**Estado:** rascunho para discussão. Nada aqui é final até ser marcado ✅.

- ✅ **decidido** por ti
- 🟡 **proposta minha** — aceita, corta ou muda
- ❓ **decisão tua em falta** — com opções e a minha recomendação

Todos os números são **valores iniciais**, a calibrar na simulação com bots (passo seguinte).

---

## 0. O que já está decidido

- ✅ Jogo online, assíncrono, por turnos, inspirado no TREVASXXI mas mais do que um 4X simples.
- ✅ 25 jogadores no arranque, turnos de **48 horas**.
- ✅ Mundo persistente, **sem limite de turnos**.
- ✅ Guerra, política e construção presentes.
- ✅ A **Praga**: uma infestação persistente e global (não uma doença).
- ✅ Mapa: ~627 regiões jogáveis (províncias do Azgaar), com bioma, altitude, costa e rios.

## 1. Princípios de design 🟡

1. **Um turno custa 15–30 minutos a um jogador empenhado, e 5 minutos chegam para não perder terreno.**
   Com 48h e um jogo sem fim, o inimigo é o cansaço, não a falta de profundidade.
2. **Ordens simultâneas.** Todos submetem, o servidor resolve tudo ao mesmo tempo. Enviar primeiro não dá vantagem.
3. **Informação parcial.** Só se vê bem o que está perto. A diplomacia vale porque ninguém vê o mapa todo.
4. **A Praga impede o mundo de estabilizar.** Num jogo sem fim, o maior risco é o líder "congelar" o mapa.
   A Praga pressiona mais quem cresce depressa demais (ver §6).

## 2. O ciclo de um turno 🟡

| Momento | O que acontece |
|---|---|
| T+0 h | O servidor resolve o turno e publica os relatórios |
| T+0 → T+47 h | Janela de ordens: o jogador lê o relatório, negoceia, submete e pode corrigir à vontade |
| T+47 h | Aviso a quem ainda não submeteu |
| T+48 h | Fecho. Quem não submeteu fica com as **ordens permanentes** (ver §7) |

As ordens são validadas **na submissão**, não na resolução: o jogador vê logo "esta ordem é impossível porque…".
É a lição direta do TREVAS (ordem inválida descoberta só no relatório).

## 3. Entidades 🟡

**Região** — dono, população, ordem pública (0–3), fortificação (0–3), até 2 edifícios, Praga (0–100).
O terreno vem do mapa: bioma (produção, movimento), altitude (defesa), costa (travessias), rios (fronteira defensiva).

**Fação** — tesouro, comida armazenada, posturas diplomáticas, pontos de comando.

**Exército** — está numa região, tem força (homens) e veterania (0–3). Na v0.1 há um só tipo de tropa.

❓ **Quantos recursos?**
- A) Só ouro. Simples, mas a Praga não tem onde morder além da população.
- B) **Ouro + comida.** A comida alimenta exércitos e é o que a Praga destrói primeiro. Liga guerra, economia e Praga num só sistema. **(recomendo)**
- C) Três ou mais recursos (madeira, ferro…). Mais 4X, mais trabalho por turno. Contraria o princípio 1.

## 4. Ordens da v0.1 🟡

Sete ordens, de propósito. Cada ordem gasta **pontos de comando (PC)**.

| Ordem | Quem | Efeito | PC |
|---|---|---|---|
| **Mover** | exército | até 2 regiões (floresta, montanha, pântano e rios custam o dobro); pela costa, uma travessia até à região costeira mais próxima do mesmo mar | 1 |
| **Atacar** | exército | entra numa região hostil e combate | 1 |
| **Guarnecer** | exército | fica e defende (+1 de defesa); é a ordem por defeito | 0 |
| **Purgar** | exército | combate a Praga na região (§6); custa homens | 1 |
| **Construir** | região | fortificação ou edifício; demora vários turnos | 1 |
| **Recrutar** | região | novos homens; baixa a população e a ordem pública | 1 |
| **Postura** | fação | declarar a outra fação: Aliado / Neutro / Hostil (como no Atlantis) | 0 |

As **mensagens entre jogadores** são livres e não passam pela resolução.

**Pontos de comando por turno = 4 + 2 × √(nº de regiões).**
Um império de 9 regiões tem 10 PC; um de 64 regiões tem 20 PC. Crescer dá mais poder, mas cada região nova vale menos
PC. É o equivalente ao teto de pontos de fação do Atlantis, sem um limite rígido: um império grande não consegue
gerir tudo, e a periferia esquecida é onde a Praga entra (§6).

## 5. Ordem de resolução 🟡

1. **Diplomacia** — as posturas novas valem para este turno.
2. **Economia** — rendimento e manutenção. Exército sem comida perde 10% dos homens.
3. **Movimento** — simultâneo, um passo de cada vez. Dois exércitos hostis que se cruzam numa fronteira param e combatem.
4. **Combate** — por região, todos os hostis presentes. O defensor soma terreno, fortificação, rio e Guarnecer.
5. **Conquista** — se o atacante vence e não sobram defensores, a região muda de dono com ordem pública 0
   (sem rendimento durante 2 turnos).
6. **Construção e recrutamento.**
7. **Praga** — purga → crescimento → alastramento → colapso.
8. **Eventos** — ponto de ligação para o módulo de mestre de jogo e narrativa.
9. **Relatórios.**

A Praga resolve-se **depois** da guerra de propósito: uma região que acabou de ser conquistada, sem ordem pública
e sem guarnição, é exatamente onde a Praga avança. A guerra tem um custo que não vem do inimigo.

## 6. A Praga 🟡

**Intensidade 0–100 por região, em quatro estados:**

| Estado | Intensidade | Efeito |
|---|---|---|
| Limpa | 0 | — |
| Contaminada | 1–39 | −25% de produção de comida |
| Infestada | 40–79 | população cai 5%/turno; não se recruta |
| Perdida | 80–100 | a região perde o dono e torna-se território da Praga |

**Crescimento:** +8 por turno numa região contaminada, +4 se tiver fortificação ou ordem pública 3.

**Alastramento:** cada região Infestada ou Perdida tenta passar a Praga a cada vizinho. A probabilidade é
proporcional à intensidade, metade através de um rio, e nunca por mar.

**Combate:** a ordem **Purgar** retira 10 + força÷100 de intensidade e custa 5% dos homens.
Uma região Perdida só se reconquista em dois passos: purgar até abaixo de 80 e depois ocupar.

**Crias:** regiões Perdidas geram, de tempos a tempos, bandos hostis que atacam vizinhos. Fazem o papel dos monstros
errantes do Atlantis.

❓ **De onde nasce a Praga?**
- A) Só dos Ermos iniciais. Previsível; ao turno 50 é um problema "de quem está perto".
- B) **Dos Ermos, e também de surtos em regiões negligenciadas** (ordem pública 0 ou fome durante 2+ turnos). Pune a
  expansão rápida e mal gerida, e é o principal travão ao jogador dominante. **(recomendo)**
- C) Surtos aleatórios em qualquer lado. Parece injusto; os jogadores não conseguem planear contra isso.

❓ **A Praga pode consumir o mundo inteiro?**
- A) Sim. Dá tensão real, mas o jogo pode acabar mal sem ninguém ter culpa.
- B) **Não. Equilíbrio dinâmico: a força da Praga sobe quando ocupa pouco e desce quando ocupa muito, apontando para
  ~20–35% do mapa.** O alvo calibra-se na simulação. **(recomendo)**

## 7. Entrada tardia e abandono 🟡 (lições do Atlantis)

**Os 25 lugares são um teto de jogadores ativos, não uma lista fixa.** Quando uma fação se dissolve, o lugar reabre.

**Entrada de um jogador novo:**
- Escolhe a região inicial entre Terras Livres ou regiões recém-purgadas, nunca colada a um jogador ativo.
- Recebe um **tesouro protegido**: dinheiro que não pode ser saqueado, como a prata não reclamada do Atlantis.
- ❓ **Proteção inicial:**
  - A) **5 turnos (10 dias) em que não pode ser atacado nem atacar. (recomendo)** Simples e claro.
  - B) Região inicial com guarnição neutra forte, como os guardas das cidades do Atlantis. Mais elegante, mais difícil de equilibrar.

**Inatividade:**
- 1 turno sem ordens → **ordens permanentes**: os exércitos guarnecem e a economia continua.
- 3 turnos (6 dias) → **Regência**: uma IA defensiva mínima mantém a fação viva; o jogador pode voltar a qualquer momento.
- ❓ 10 turnos (20 dias) → a fação **dissolve-se**: as regiões passam a Terras Livres com ordem pública 0, e por isso
  tornam-se alvo natural da Praga (regra B do §6). O mundo recupera o espaço sem intervenção do GM.
  O número exato é decisão tua.

## 8. Fim e vitória

❓ **Num mundo sem fim, o que dá sentido a jogar?**
- A) Nada formal; cada um define os seus objetivos, como no Atlantis puro.
- B) **Eras: a cada 50 turnos (~100 dias) fecha uma Era**, com classificação de prestígio, títulos permanentes no perfil
  do jogador e uma mudança de regras ou evento (a Praga muda de comportamento, abre-se um continente…). O mundo continua.
  **(recomendo)** Até a comunidade do Atlantis acabou por precisar de regras de fim de jogo.
- C) Vitória e reinício periódicos. Contradiz a decisão de mundo persistente.

## 9. Fora da v0.1, de propósito

Tecnologia, vários tipos de tropa, combate naval, comércio formal entre jogadores, espionagem e personagens/heróis.
Cada um destes entra só se a simulação mostrar que o núcleo funciona e que falta exatamente isso.

## 10. Decisões que preciso de ti

1. Recursos: só ouro, **ouro + comida**, ou três ou mais? (§3)
2. Origem da Praga: só Ermos, **Ermos + regiões negligenciadas**, ou aleatória? (§6)
3. A Praga pode consumir o mundo? (§6)
4. Proteção de entrada: **5 turnos** ou guarnição neutra? (§7)
5. Turnos até a fação inativa se dissolver: 10 ou outro número? (§7)
6. Fim: nada, **Eras de 50 turnos**, ou reinício? (§8)
7. Alguma das 7 ordens a mais ou a menos? (§4)
