# world-forge

Liga o [Province-Forge](https://github.com/Ex-aequo/Province-Forge) (submódulo em `vendor/province-forge`) ao motor do
Praga: lê o `static-map.json` de um mundo gerado e escreve o `world.json` que o [turn-engine](../turn-engine/) lê.

- **Províncias:** as de terra do Province-Forge (ids 0..L-1) passam a 1..L no Praga. O mar, os lagos e o gelo ficam
  fora do jogo terrestre; duas províncias costeiras que tocam a mesma zona de mar costeira ficam ligadas por mar.
- **Reinos:** cada posição inicial é um reino, com o nome e a cor que o gerador sugere. O resto da terra são Terras
  Livres. Sem posições de reserva: quem entra a meio recebe o reino-guardião mais intacto (regras §7).
- **População:** pelo terreno (planície 120 mil … deserto 25 mil), mais rio e costa, escalada pela área.
- **Produção** (no motor, `TERRAIN_YIELD` em `praga/rules.py`): pelo terreno, mais o recurso principal da província
  (cereal → comida, madeira, ferro, ouro: +1 a +3 conforme a quantidade; o ouro permite a mina de ouro). Pedra:
  fortificações a metade do preço. Cavalos, sal e especiarias: no mapa, ainda sem efeito (decisão de 2026-10-16).
- **Distâncias:** o mundo dá a volta de leste a oeste; as regras (rumores, focos da Praga) medem em "províncias".

O servidor do jogo chama isto sozinho depois de gerar um mundo. À mão:

```bash
python -m forge.convert <pasta do mundo> "Nome do mundo"
python -m unittest tests.test_convert
```
