# Registo de decisões

Formato: data — decisão — porquê — o que fica em aberto.

## 2026-10-15 — Monorepo com módulos independentes

- **Decisão:** um repositório (`ex-aequo-gm-modules`), um diretório por módulo, sem biblioteca comum.
- **Porquê:** com um só módulo, uma camada partilhada seria adivinhação. Extrai-se código comum quando dois módulos
  precisarem dele.
- **Nome genérico (não "AB"):** as ferramentas servem vários jogos, não só Alea Belli.

## 2026-10-15 — Mapa: Azgaar como gerador de dados, render próprio

- **Decisão:** usar o Azgaar apenas para gerar geografia e política (Full JSON). Todo o visual é nosso.
- **Porquê:** o aspeto do Azgaar no browser é a parte mais fraca; os dados são bons. Licença MIT e mapas de uso
  comercial livre.
- **Consequência:** regiões de jogo = províncias do Azgaar (polígonos de Voronoi). Grelhas hexagonais ficam fora.

## 2026-10-15 — Mapa: base estática + camada dinâmica em shader

- **Decisão:** base pintada uma vez (relevo, biomas, costa) + raster de IDs de região + shader que pinta donos,
  fronteiras e Praga a partir de tabelas pequenas atualizadas por turno.
- **Porquê:** a base pode ter qualidade "ilustrada" sem custo em tempo real; o estado do jogo muda só as tabelas.
- **WebGL2 direto em vez de PixiJS:** mais controlo, menos uma dependência. Os shaders migram se for preciso.
- **Em aberto:** base final no Blender/Gaea; desempenho em telemóvel; tiles para zoom alto.

## 2026-10-15 — Sem IA generativa para assets visuais

- **Decisão:** nenhum asset gráfico gerado por Leonardo.ai ou semelhantes.
- **Porquê:** resultados demasiado aleatórios para um estilo coerente. Determinismo: mesma entrada, mesma imagem.
- **Consequência:** o que não sai de código precisa de packs com licença comercial verificada ou de um ilustrador.

## 2026-10-15 — A Praga é um evento do mestre de jogo

- **Decisão:** a Praga não tem travão automático; o GM liga e desliga, abre focos e escolhe a intensidade.
  Adormecida não cresce nem alastra, mas o perdido continua perdido. O GM não joga no mesmo mundo.
- **Porquê:** três versões de regras automáticas (teto, recuo, travas combinadas) não estabilizaram a Praga sem
  mecanismos invisíveis. Um GM humano é o equilíbrio, e encaixa no objetivo de ter mestre de jogo e narrativa.
- **Consequência:** as ordens do GM são um segundo canal de entrada do motor, determinístico e registado na crónica.
  O motor sozinho já não garante um mundo jogável: depende de boas decisões do GM.
- **Em aberto:** painel do GM (hoje as ordens são JSON); ferramentas de leitura para o GM decidir (quanto do mapa está
  perdido, quem lidera, onde abrir focos).

## 2026-10-15 — Painel do GM em modo sandbox, React, renderizador partilhado

- **Decisão:** o painel do GM começa como sandbox local (24 bots + tu como GM), com backend FastAPI e interface React +
  Vite + TypeScript. A pré-visualização de turnos entra já na primeira versão.
- **Porquê:** um painel real puxa o servidor multijogador inteiro (contas, ordens, relógio de 48 h). O sandbox testa
  primeiro se o painel serve para decidir e se ser GM é interessante. A lógica fica em `sandbox.py` para ser
  reaproveitada pelo servidor real.
- **Renderizador partilhado:** o mapa passou a ser usado por dois módulos, por isso saiu para `modules/map-renderer`
  (primeira exceção à regra de módulos sem código comum).
- **Pré-visualização exata:** como o motor e os bots são determinísticos, a previsão de N turnos é exatamente o que
  acontece ao resolver (há um teste que o garante). Com jogadores humanos passará a ser uma estimativa.

## 2026-10-15 — Geografia e reinos próprios; o Azgaar fica com o clima e os nomes

- **Decisão:** o relevo (n.º de continentes, fração de terra, ilhas, mar interior) é desenhado por nós e injetado no
  Azgaar como mapa de alturas; províncias e reinos também são nossos. Do Azgaar ficam clima, biomas, rios, burgos e
  nomes. Reinos em múltiplos de 25 até 150, todos com o mesmo número P de províncias contíguas (até +2 de
  compensação para terra pobre); o resto do mundo são Terras Livres (opção 1.A). P sai do tamanho do mapa.
- **Porquê:** os modelos de relevo do Azgaar não dão um número exato de continentes, e as províncias dele têm tamanhos
  muito diferentes. Injetar um modelo nosso no Azgaar falhou (corrida na regeneração e pouco efeito); injetar a imagem
  de alturas funciona e o Azgaar respeita os continentes (verificado em cada geração).
- **Consequências:**
  - O tamanho do mundo fica 1920 × 1080; "tamanho" muda a densidade de células. 150 reinos só cabem em `grande` ou
    `enorme`, com 2–4 províncias por reino. O exportador recusa combinações que não cabem antes de gerar.
  - O renderizador passou a aceitar até 4095 regiões (tabela 2D); o motor tem o arranque `world`.
  - Um mundo `enorme` tem ~2000 regiões: o motor resolve um turno em ~0,15 s; o mapa aguenta.
- **Em aberto:** as regras v0.4 foram calibradas com 24 fações e ~400 regiões. Com 150 reinos de 4 províncias, 29 %
  dos reinos-bot desaparecem em 100 turnos (contra ~8 % com 25 reinos): é preciso re-simular e recalibrar
  (pontos de comando, guarnições, ritmo da Praga por região) antes de escolher a escala do jogo.

## 2026-10-15 — Nevoeiro de guerra: decidido no servidor, fotografias com data

- **Decisão:** cada fação conhece só o que viu (regras §8). O que foi visto fica como fotografia com o turno; ao vivo
  só o que se vê agora. Batedores e espiões para ver mais longe; rumores vagos sobre a Praga; rumores do GM.
- **Porquê "fotografia" e não "visto para sempre ao vivo":** se tudo o que foi visto ficasse ao vivo, a meio do jogo
  cada jogador via quase tudo e o nevoeiro deixava de contar.
- **Porquê no servidor:** um nevoeiro só desenhado no browser é contornado com as ferramentas do browser. O motor
  constrói a vista do jogador (`praga/vision.py: player_view`) só a partir das fotografias; um teste garante que mudar o
  que o jogador não vê não muda a vista dele.
- **Consequências:**
  - O estado guarda, por fação, as fotografias de cada região conhecida (~40 bytes cada).
  - O renderizador ganhou um modo de nevoeiro (pergaminho, tons lavados, rios e burgos só onde se conhece).
  - O painel do GM tem "ver como jogador" e um cartão de rumores.
- **Em aberto (servidor real):** `world.json`, `base.jpg` e `regions.png` têm o mundo inteiro (nomes, geografia,
  donos iniciais). No sandbox não importa; no jogo, quem abrir as ferramentas do browser vê o mapa todo. Antes de
  haver jogadores, é preciso servir o mapa por jogador: tiles da base só das regiões conhecidas e um `world.json`
  filtrado. Junta-se bem com os tiles por nível de zoom que já estavam previstos.


## 2026-10-15 — Reinos sem jogador são guardiões; sem metas de equilíbrio

- **Decisão:** o mundo é gerado com todos os reinos; os que não têm jogador são reinos-guardiões governados pelo motor.
  Guardiões defendem, constroem, purgam e expandem só para Terras Livres; nunca atacam reinos. Quem chega recebe o
  guardião mais intacto. Um reino abandonado passa a guardião em vez de se dissolver. Os jogadores sabem quem é guardião.
- **Sem metas de equilíbrio:** as regras não são afinadas para atingir números (eliminações, tamanho do maior reino,
  Praga). "Os jogadores fazem o jogo." As simulações ficam como informação para o GM, não como critério.
- **Escala:** primeiro 25 e 50 reinos. 100/150 ficam como verificação.
- **Defeitos de escala corrigidos:** focos sugeridos e rumores medem-se em distância do mundo (não em regiões).
  Os focos ficam ao alcance dos rumores.
- **Correção de regras encontrada pelo caminho:** dois ataques simultâneos à mesma Terra Livre podiam fazer o segundo
  atacante conquistar a região ao primeiro sem hostilidade declarada. Agora esse ataque não acontece.
- **Riscos registados:**
  - Guardiões nunca retaliam: são presa fácil para jogadores agressivos, e quem chega pode receber um reino já
    reduzido. A atribuição "mais intacto" mitiga, mas não resolve se todos os guardiões estiverem a ser comidos.
  - O reino recebido varia muito (na simulação, de 4 a 55 regiões): é a sorte do momento em que se entra.

## 2026-10-15 — Base do mapa renderizada no Blender, estilo atlas, em tiles

- **Decisão:** a base do mapa passa a ser renderizada no Blender (relevo com erosão, florestas, povoações, mar) no
  estilo **atlas** (luz quente, árvores grandes e espaçadas, papel e tinta na costa), em tiles de 512 px por nível
  de zoom, com 5,3 px por unidade no nível de mais detalhe (opção A). Render feito aqui, verificado e entregue.
- **Porquê:** a prova lado a lado mostrou muito mais detalhe e leitura do relevo do que a base pintada em Python,
  sobretudo ao aproximar. Tudo continua determinístico e sem IA.
- **Consequências:**
  - O renderizador carrega só os tiles visíveis; a `base.jpg` (agora também saída do Blender) fica de reserva.
  - Relevo, cores e árvores são calculados para o mundo inteiro ou por coordenadas do mundo, para não haver
    costuras; papel e tinta aplicam-se ao mosaico inteiro.
  - `tiles.json` diz que regiões cada tile toca: o servidor real envia a cada jogador só os tiles que ele conhece.
- **Aceite:** um tile pode mostrar a geografia de províncias vizinhas desconhecidas (nunca donos nem exércitos).
- **Em aberto:** neve nas zonas mais altas; mundos maiores (tamanho enorme) levam proporcionalmente mais tempo.

## 2026-10-16 — Jogo jogável no Mac: servidor, contas e os dois frontends

- **Decisão:** novo módulo `game-server` (FastAPI + PostgreSQL), um mundo por servidor, com contas de jogador e de
  GM. O GM fecha o turno à mão e pode ligar um relógio. Todas as ordens no frontend dos jogadores
  (`player-client`). O painel do GM é o mesmo do sandbox, em modo "jogo" em `/gm/`.
- **Nevoeiro aplicado no servidor:** cada jogador recebe só o que conhece (dados, mapa e tiles). O sandbox continua
  a servir tudo — é só para o GM.
- **Arranque:** `modules/game-server/scripts/praga.sh setup` e `start`.
- **Em aberto:** registo de contas e entrada de jogadores novos a meio (hoje é por script); HTTPS e alojamento;
  notificações de fim de turno.
