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
