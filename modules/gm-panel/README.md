# gm-panel

Painel do mestre de jogo para o Praga, em modo **sandbox**: um mundo local onde as 24 fações são bots
(módulo [turn-engine](../turn-engine/)) e tu és o GM. Serve para testar se o painel dá a informação certa para decidir
e se conduzir a Praga é interessante, antes de existir o servidor multijogador.

A API foi desenhada para passar a ser a do servidor real: a lógica está em `backend/sandbox.py`, não nas rotas.

## O que faz

- **Mapa** com o estado real do motor (módulo partilhado [map-renderer](../map-renderer/)): donos, fronteiras, Praga,
  focos sugeridos (círculo tracejado) e focos pendentes.
- **Estado do mundo:** % perdido e contaminado, maior fação, gráfico por turno com as faixas em que a Praga esteve ativa.
- **Controlos da Praga:** despertar/adormecer, intensidade (fraca ×0,5, normal, forte ×1,5), abrir foco clicando no mapa
  ou num foco sugerido, com confirmação (é irreversível e aparece na crónica pública).
- **Ordens para o próximo turno:** fila revista e cancelável antes de resolver. Uma nova decisão de estado ou intensidade
  substitui a anterior. Abrir um foco com a Praga adormecida acrescenta "Despertar" automaticamente.
- **Pré-visualização:** simula 5–30 turnos numa cópia do mundo, com as ordens pendentes, e mostra o resultado no mapa.
  Com bots é exata (o mesmo que vai acontecer ao resolver); com jogadores reais será uma estimativa.
- **Região:** clicar numa região mostra dono, Praga, população, ordem pública, fortificação, edifício e exércitos.
- **Fações** (regiões, crescimento nos últimos 10 turnos, homens) e **crónica** pública turno a turno.

Cada turno resolvido fica em `build/sandbox/turns/state_NNNN.json` (histórico completo; o sandbox retoma onde ficou).

## Correr

Pré-requisito: o mundo gerado pelo módulo [world-map](../world-map/) (`world-map/web/data/`).

```bash
cd modules/gm-panel
pip install fastapi uvicorn          # + o que o turn-engine precisa (só biblioteca padrão)
cd frontend && npm install && npm run build && cd ..
uvicorn backend.app:app --port 8000  # abrir http://127.0.0.1:8000
```

Desenvolvimento da interface com recarga automática: `uvicorn …` num terminal e `cd frontend && npm run dev` noutro
(o Vite reencaminha `/api` e `/data` para a porta 8000).

Testes da API: `python -m unittest backend.test_api` (a partir de `modules/gm-panel`).

## API

| Método | Caminho | O que faz |
|---|---|---|
| GET | `/api/state` | estado atual, ordens pendentes, histórico, crónica |
| GET | `/api/region/{id}` | detalhe de uma região |
| POST | `/api/gm/orders` | acrescenta uma ordem do GM (`plague_state`, `plague_focus`, `plague_intensity`); 400 com a razão se for inválida |
| DELETE | `/api/gm/orders/{i}` | retira a ordem `i` da fila |
| POST | `/api/turn` | resolve o turno (bots + ordens do GM) |
| POST | `/api/preview` | `{"turns": 10}` → estado previsto, série de métricas, regiões que caem, fações atingidas |
| POST | `/api/reset` | `{"seed": "s1"}` → mundo novo |

## Limites desta versão

- Local e sem autenticação. Não expor na internet tal como está.
- Um só GM e um só mundo por servidor.
- As fações são bots; não há jogadores humanos nem relógio de 48 h.
- A pré-visualização corre no servidor (~15 ms por turno); 30 turnos demoram cerca de meio segundo.
