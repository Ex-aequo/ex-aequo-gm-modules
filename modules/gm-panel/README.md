# gm-panel

Painel do mestre de jogo do Praga. É servido pelo [game-server](../game-server/) em `/gm/` (entrar com a conta do GM).

- **Mapa** do Province-Forge com tudo: reinos, fronteiras, Praga (modo "Praga" mostra só a Praga), focos sugeridos
  (círculo roxo) e focos pendentes.
- **Jogadores:** quem já enviou ordens, quem falha turnos; **relógio** (o turno fecha sozinho de N em N minutos) ou
  turno fechado à mão.
- **Estado do mundo**, **Praga** (despertar, adormecer, intensidade, abrir focos), **rumores**, **ordens pendentes**.
- **Pré-visualização:** simula 5–30 turnos numa cópia do jogo (os jogadores repetem as ordens do turno atual e depois
  guarnecem; os guardiões jogam como bots).
- **Ver como jogador:** o mapa e as mensagens tal como o servidor os envia a essa fação (nevoeiro, §8).
- **Novo mundo:** os controlos do Province-Forge para o Praga (reinos 25–150, províncias por reino, território inicial,
  terra, continentes, ilhas, lagos, rios, clima, recursos raros) com pré-visualização no browser (5–20 s). "Criar"
  gera o mundo final no servidor, com progresso; depois, "Começar um jogo neste mundo" apaga o jogo atual e dá a cada
  conta de jogador um reino do mundo novo.

```bash
cd frontend && npm install && npm run build      # o game-server serve frontend/dist em /gm/
npm run dev                                      # desenvolvimento, com a API em localhost:8000
```

O antigo modo sandbox (backend próprio, mundo do Azgaar) foi retirado em 2026-10-16; está no histórico do git.
