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
