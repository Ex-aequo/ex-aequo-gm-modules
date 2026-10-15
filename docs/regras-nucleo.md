# Praga — Regras núcleo (rascunho v0.6)

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

**Região** — dono, população, ordem pública (0–3), fortificação (0–3), um edifício de produção (nível 0–3), Praga (0–100).
O terreno vem do mapa: bioma (produção, movimento), altitude (defesa), costa (travessias), rios (fronteira defensiva).

**Fação** — reservas dos quatro recursos, posturas diplomáticas, pontos de comando.

**Exército** — está numa região, tem força (homens) e veterania (0–3). Na v0.1 há um só tipo de tropa.

### 3.1 Recursos ✅

✅ **Quatro recursos: ouro, comida, madeira e ferro.**
✅ **A produção é automática**, a partir das regiões controladas. Não há ordens para produzir: os recursos só se
gastam ao construir, recrutar e manter exércitos. O custo extra fica na leitura do relatório, não no trabalho por turno.

| Recurso | De onde vem | Para que serve |
|---|---|---|
| **Ouro** | impostos sobre a população (todas as regiões); minas de ouro | manutenção de edifícios e exércitos, recrutamento |
| **Comida** | pradaria, savana, floresta sazonal, costa | alimentar exércitos (1 por 100 homens/turno); crescimento da população |
| **Madeira** | florestas, taiga, pântano | construir e subir edifícios, fortificações de madeira |
| **Ferro** | montanhas (altitude alta), desertos | recrutar e equipar homens (obrigatório), fortificações de pedra |

🟡 A produção base de cada região sai do bioma e da altitude que já estão no mapa. Uma fação sem montanhas não tem
ferro próprio: comercia ou conquista. É aqui que a geografia passa a dar razões para guerra e diplomacia.

✅ **Ferro garantido no arranque (v0.3):** as duas regiões iniciais além da capital escolhem-se de forma a incluir ferro.
Se não houver ferro a dois passos, a capital recebe um **veio menor** (+2 ferro/turno), indicado no relatório.

### 3.2 Infraestruturas de produção ✅ (com níveis)

✅ Edifícios de produção com níveis (exemplo: Mina de ouro nível 1, 2, 3).

🟡 Proposta concreta:

| Edifício | Onde se pode construir | Recurso |
|---|---|---|
| Quinta | regiões com produção base de comida | comida |
| Serração | regiões com floresta | madeira |
| Mina de ferro | montanha ou deserto | ferro |
| Mina de ouro | só regiões com **veio de ouro** (~10% das regiões de montanha, fixo pela seed do mundo) | ouro |

| Nível | Produção do recurso | Custo para chegar ao nível | Tempo | Manutenção (ouro/turno) |
|---|---|---|---|---|
| 1 | ×1,5 | 20 madeira | 1 turno | 2 |
| 2 | ×2,0 | 40 madeira + 20 ferro | 2 turnos | 5 |
| 3 | ×2,5 | 80 madeira + 40 ferro + 40 ouro | 3 turnos | 10 |

- **Um edifício de produção por região.** Escolher Quinta ou Serração numa floresta sazonal é uma decisão, não uma lista de tarefas.
- **Subir de nível é uma ordem Construir** e gasta pontos de comando, como qualquer outra.
- **A manutenção cresce mais depressa do que a produção.** Um nível 3 só compensa numa região rica e segura.
- **A Praga ataca a infraestrutura:** numa região Infestada o edifício para de produzir; numa região Perdida desce um nível.

**Porque estas travas:** níveis de produção são o mecanismo clássico de efeito bola de neve (mais recursos → mais
edifícios → mais recursos). Num mundo sem fim, sem travas, quem começa melhor fica à frente para sempre. A manutenção
crescente, o limite de um edifício por região e a Praga mantêm a vantagem real mas finita. A simulação diz se chega.

## 4. Ordens da v0.1 🟡

Sete ordens, de propósito. Cada ordem gasta **pontos de comando (PC)**.

| Ordem | Quem | Efeito | PC |
|---|---|---|---|
| **Mover** | exército | até 2 regiões (floresta, montanha, pântano e rios custam o dobro); pela costa, uma travessia até à região costeira mais próxima do mesmo mar | 1 |
| **Atacar** | exército | entra numa região hostil e combate | 1 |
| **Guarnecer** | exército | fica e defende (+1 de defesa); é a ordem por defeito | 0 |
| **Purgar** | exército | combate a Praga na região (§6); custa homens | 1 |
| **Construir** | região | fortificação, edifício de produção, ou subir um nível (§3.2); demora vários turnos | 1 |
| **Recrutar** | região | novos homens; baixa a população e a ordem pública | 1 |
| **Postura** | fação | declarar a outra fação: Aliado / Neutro / Hostil (como no Atlantis) | 0 |
| **Recrutar agente** | região | um batedor ou um espião (§8.2) | 1 |
| **Mover agente** | agente | batedor até 2 regiões, espião 1; só por terra; pode entrar em qualquer região | 1 |

As **mensagens entre jogadores** são livres e não passam pela resolução.

**Pontos de comando por turno = 4 + 2 × √(nº de regiões).**
Um império de 9 regiões tem 10 PC; um de 64 regiões tem 20 PC. Crescer dá mais poder, mas cada região nova vale menos
PC. É o equivalente ao teto de pontos de fação do Atlantis, sem um limite rígido: um império grande não consegue
gerir tudo, e a periferia esquecida é onde a Praga entra (§6).

## 5. Ordem de resolução 🟡

0. **Decisões do GM** — estado, intensidade e focos da Praga (§6.1).
1. **Diplomacia** — as posturas novas valem para este turno.
2. **Economia** — produção automática dos quatro recursos, manutenção de edifícios e exércitos. Exército sem comida perde 10% dos homens.
3. **Movimento** — simultâneo, um passo de cada vez. Dois exércitos hostis que se cruzam numa fronteira param e combatem.
   Os agentes movem-se ao mesmo tempo que os exércitos.
4. **Combate** — por região, todos os hostis presentes. O defensor soma terreno, fortificação, rio e Guarnecer.
5. **Conquista** — se o atacante vence e não sobram defensores, a região muda de dono com ordem pública 0
   (sem rendimento durante 2 turnos).
   Depois: batedores numa região com exército não aliado são apanhados; espiões podem ser descobertos (§8.2).
6. **Construção e recrutamento** (também de agentes).
7. **Praga** — purga (sempre) → recuo/crescimento → alastramento → colapso → crias (só com a Praga ativa).
8. **Visão e rumores** — cada fação tira fotografias do que vê agora; quem não vê a Praga ouve rumores (§8).
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

**Crescimento:** +8 por turno numa região contaminada, +4 se tiver fortificação.

✅ **Recuo (v0.3):** numa região com dono, ordem pública 3 e sem fome, a Praga **desce 3 por turno** em vez de crescer.
O perigo fica na fronteira, nas conquistas recentes e nas regiões com fome. Governar bem é uma defesa.

**Alastramento:** cada região Infestada ou Perdida tenta passar a Praga a cada vizinho. A probabilidade é
proporcional à intensidade, metade através de um rio, e nunca por mar.

**Combate:** a ordem **Purgar** retira 10 + força÷100 de intensidade e custa 5% dos homens.
Uma região Perdida só se reconquista em dois passos: purgar até abaixo de 80 e depois ocupar.

**Crias:** regiões Perdidas geram, de tempos a tempos, bandos hostis que atacam vizinhos. Fazem o papel dos monstros
errantes do Atlantis.

✅ **Origem da Praga: vários focos iniciais e surtos em regiões negligenciadas** (ordem pública 0 ou fome durante
2+ turnos). Pune a expansão rápida e mal gerida e é o principal travão ao jogador dominante.

✅ **Focos sugeridos (v0.6):** o motor calcula 6 focos possíveis entre 200 e 420 unidades da capital mais próxima
(o mundo tem 1920 × 1080), espalhados uns dos outros, sempre num continente com reinos. Longe o suficiente para não
matar ninguém à nascença, perto o suficiente para haver rumores (§8.3). Distâncias em unidades do mundo, não em
regiões: não mudam com o tamanho das províncias. **Não estão ativos no arranque**: são sugestões para o GM.

✅ **A Praga pode consumir o mundo (decisão C, v0.4).** Não há travão automático. O ritmo é decidido pelo GM (§6.1).

### 6.1 A Praga é um evento do mestre de jogo ✅

- ✅ **O GM liga e desliga a Praga** sempre que entender. No arranque está **adormecida**.
- ✅ **Adormecida** = não cresce, não alastra, não há surtos nem crias. O que já foi perdido continua perdido, mas a
  **purga funciona** e as regiões podem ser reconquistadas. O recuo em regiões bem governadas continua.
- ✅ **O GM também pode** abrir um foco numa região à escolha e escolher a intensidade:
  **fraca** (×0,5), **normal** (×1) ou **forte** (×1,5) — multiplica crescimento, alastramento, surtos e crias.
- ✅ **O GM não joga no mesmo mundo.**
- 🟡 As decisões do GM entram como ordens: aplicam-se no início da resolução do turno seguinte (fase 0), nunca a meio.
- 🟡 **Tudo o que o GM faz aparece na crónica pública do turno** ("A Praga desperta.", "Um foco da Praga abre-se em
  Ialalia."). Os jogadores sabem *o quê*, não sabem *porquê* nem *o que vem a seguir*.

**O que a simulação diz ao GM** ([simulacao-v0.4.md](simulacao-v0.4.md)): a Praga funciona como um **trinco**. O que se
perde enquanto está ativa não volta sozinho quando adormece. Com bots, cada turno ativo custa em média ~0,7% do mapa
de forma permanente: 30 turnos ligada e 30 desligada levam a ~70% do mapa perdido em 200 turnos.

## 7. Reinos sem jogador, entrada e abandono ✅ (v0.6)

✅ **Todos os reinos existem desde o início.** Um reino sem jogador é um **reino-guardião**, governado pelo motor.
Os jogadores sabem quais são guardiões (aparecem marcados).

**Reino-guardião (bot):**
- Defende, constrói, recruta com moderação e purga a Praga nas suas terras.
- Expande só para **Terras Livres** (ou regiões recuperáveis da Praga), só por terra e só para o que vê.
- **Nunca declara hostilidade nem ataca outro reino** — jogador ou guardião. Pode ser atacado.
- As ordens dos guardiões são do motor: o que for submetido em nome deles é ignorado.

**Entrada de um jogador novo:**
- ✅ Recebe automaticamente o **reino-guardião mais intacto**: mais regiões, menos Praga, mais homens.
  Herda o território, os exércitos e o tesouro desse reino.
- ❓ **5 turnos (10 dias) de proteção**: não pode ser atacado nem atacar (proposta; ainda em aberto).
- Se não houver guardiões, entra numa região livre longe de jogadores ativos (como antes).

**Inatividade:**
- 1 turno sem ordens → **ordens permanentes**: os exércitos guarnecem e a economia continua.
- 3 turnos (6 dias) → **Regência**: guarnecer e purgar; o jogador pode voltar a qualquer momento.
- ✅ Ao fim de ❓10 turnos (20 dias) → o reino **passa a reino-guardião** e fica disponível para o próximo jogador. Os agentes são
  dispensados e as posturas hostis voltam a neutras (um guardião não faz guerra).

Regra geral do combate (v0.6): se dois reinos atacam a mesma Terra Livre no mesmo turno e o primeiro a toma, o
segundo ataque só acontece se houver hostilidade declarada contra o novo dono. Ninguém entra em guerra por acidente.

## 8. Nevoeiro de guerra ✅ (v0.5)

✅ Os jogadores só conhecem o que viram. A geografia revela-se à medida que exploram (decisão C); o que foi visto fica
no mapa como **fotografia com data**, e só o que se vê agora está ao vivo.

### 8.1 Níveis de visão

| Nível | Quando | O que se vê |
|---|---|---|
| **Desconhecida** | nunca vista | nada: pergaminho por desenhar |
| **Conhecida** | foi vista alguma vez | geografia + última fotografia: dono, estado da Praga, fortificação, edifício, exércitos por tamanho, e o turno em que foi vista |
| **Visível** | é vizinha por terra de uma região tua, ou tem um exército teu, um batedor teu, ou foi atacada por ti este turno; um batedor vê também as regiões por onde passou | o mesmo, ao vivo; exércitos por tamanho (pequena < 150, média < 400, grande < 1000, enorme) |
| **Espiada** | tem um espião teu | tudo ao detalhe: homens e veterania exatos, guarnição, população, ordem pública, Praga exata, obras |
| **Tua** | é tua | tudo |

✅ Vizinhos por mar **não** dão visão: um desembarque sem batedor é às cegas.
Uma região que perdes fica conhecida, com a fotografia do turno em que a perdeste.

O servidor envia a cada jogador só o que ele sabe (a vista é construída a partir das fotografias, nunca do estado
completo). Há um teste que muda tudo o que um jogador não vê e verifica que a vista dele não muda.

### 8.2 Batedores e espiões 🟡 (ponto de partida)

| | Custo | Manutenção | Movimento | Risco |
|---|---|---|---|---|
| **Batedor** | 5 ouro + 1 ferro | 1 ouro/turno | 2 regiões (difícil = 2) | apanhado se acabar o turno numa região com um exército não aliado |
| **Espião** | 40 ouro | 3 ouro/turno | 1 região | 10 % por turno de ser descoberto numa região que não é tua, +10 % por nível de fortificação |

Não combatem nem conquistam. Quem apanha um espião sabe de quem ele era (gancho para diplomacia e narrativa).

### 8.3 Rumores ✅

Quem não vê o que a Praga faz ouve rumores: direção (8 pontos cardeais) e distância vaga ("perto das tuas fronteiras",
"a alguns dias de marcha", "em terras distantes"), até 450 unidades da tua região mais próxima (bandas: 150 e 300).
Nunca o nome da região.
No máximo 2 rumores por turno e por fação; o mesmo rumor (tipo + direção) não se repete durante 4 turnos.
O GM pode enviar os seus próprios rumores — verdadeiros ou falsos — a uma fação ou a todas as fações perto de uma região.

## 9. Fim e vitória ✅

✅ **Sem objetivo formal.** Cada jogador define os seus objetivos, como no Atlantis puro. O mundo não acaba nem reinicia.

⚠️ Risco registado: até a comunidade do Atlantis acabou por acrescentar regras de fim de jogo. Na simulação e nos
primeiros meses de jogo real, vigiar dois sinais: abandono crescente de jogadores veteranos e um mapa que deixa de
mudar. Se aparecerem, rever esta decisão (por exemplo, com Eras de prestígio sem reinício).

## 10. Fora da v0.1, de propósito

Tecnologia, vários tipos de tropa, combate naval, comércio formal entre jogadores, sabotagem e personagens/heróis.
Cada um destes entra só se a simulação mostrar que o núcleo funciona e que falta exatamente isso.

## 11. Decisões

**Tomadas (2026-10-15):** quatro recursos com produção automática e infraestruturas com níveis (§3);
ferro obrigatório para recrutar, garantido no arranque (§3.1); Praga nasce de vários focos afastados das capitais e de
regiões negligenciadas (§6); recuo da Praga em regiões bem governadas (§6); sem objetivo formal de fim (§9).

**v0.4:** a Praga pode consumir o mundo; é um evento ligado e desligado pelo GM, que também abre focos e escolhe a
intensidade; o GM não joga no mesmo mundo (§6.1).

**v0.5:** nevoeiro de guerra com geografia revelada por exploração, fotografias com data separadas da visão ao vivo,
vizinhos por mar não dão visão, batedores e espiões (valores de partida), rumores da Praga e rumores do GM (§8).

**v0.6:** reinos sem jogador são guardiões (expandem só para Terras Livres, nunca atacam reinos); quem chega recebe o
guardião mais intacto; um reino abandonado passa a guardião (§7). Focos e rumores em distância real (§6, §8.3).
Sem metas de equilíbrio: os jogadores fazem o jogo.

**Ainda em aberto:**

1. Proteção de entrada: **5 turnos** ou guarnição neutra? (§7)
2. Turnos até um reino inativo passar a guardião: 10 ou outro número? (§7)
3. Alguma das 9 ordens a mais ou a menos? (§4)
4. A proposta de infraestruturas (§3.2) serve: um edifício por região, níveis 1–3, veios de ouro raros?
