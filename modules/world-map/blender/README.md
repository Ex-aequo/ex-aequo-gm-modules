# Prova Blender: base do mapa renderizada

Objetivo: decidir se vale a pena trocar a base pintada em Python (`base.jpg`) por uma renderizada no Blender.
Renderiza só um recorte (360 × 360 unidades do mundo, 2048 px) e põe-no lado a lado com a base atual.
Nada disto muda o jogo: fronteiras, cores dos reinos, Praga e nevoeiro continuam a ser desenhados por cima.

Testado com o Blender **4.2 LTS**. Versões mais recentes devem funcionar, mas a API dos nós muda de vez em quando:
se der erro, instala a 4.2 LTS (https://www.blender.org/download/lts/4-2/).

## No Mac

```bash
cd modules/world-map
# 0. uma vez: dependências Python do módulo (numpy, scipy, pillow)
uv pip install -r requirements.txt          # dentro do .venv que já usas

# 1. exportar o recorte (escolhe sozinho uma zona com costa, montanha e floresta)
python blender/export_tile.py build/exemplo/world_full.json build/exemplo/data build/blender-prova
#    outra zona: --bbox X0 Y0 LADO   (unidades do mundo; o mundo tem 1920 × 1080)

# 2. renderizar (usa a GPU do Mac via Metal)
/Applications/Blender.app/Contents/MacOS/Blender -b -P blender/render_tile.py -- build/blender-prova

# 3. comparar
python blender/compare.py build/blender-prova
open build/blender-prova/comparacao.png build/blender-prova/comparacao-zoom.png
```

O passo 1 precisa de um mundo gerado com o `--config` (ver o README do módulo): `world_full.json` + a pasta com
`regions.png`, `base.jpg` e `world.json`. Para o mundo antigo: `build/praga/world_full.json web/data`.

Opções do render (depois do `--`): `--samples 96`, `--relief 40`, `--no-trees`, `--cpu`, `--px 1024` (rascunho
rápido), `--save-blend` (guarda `prova.blend` para abrir no Blender e mexer à mão na luz e nos materiais).

**Tempo:** aqui (2 núcleos, sem GPU) demorou 6,5 min a 2048 px com 48 amostras. Num Mac com chip Apple deve ser
bastante menos, mas não está medido. Um rascunho a 768 px com 16 amostras demora ~25 s mesmo sem GPU.

## O que a cena tem

- **Terreno:** malha de 1024 × 1024 vértices com a altura exportada (cristas e vales dos rios acrescentados ao relevo
  do Azgaar), exagerada 40 unidades. Cor do bioma (a mesma paleta da base atual), rocha nas encostas íngremes,
  neve no alto, micro-relevo por ruído.
- **Floresta:** árvores (coníferas e folhosas, modelos simples feitos por código) espalhadas pela densidade de
  floresta, sem árvores em encostas a pique. Instâncias, por isso são dezenas de milhares sem pesar.
- **Povoações:** grupos de casinhas em cada burgo, maiores nas capitais.
- **Mar:** cor pela profundidade (baixio claro junto à costa), ondulação leve.
- **Luz:** sol rasante de noroeste (como nos mapas clássicos) e céu suave; câmara ortográfica vista de cima.

A costa vem do `regions.png`, por isso o render encaixa nas fronteiras que o mapa desenha por cima.

## O que ainda é provisório (direção de arte)

- A neve e o alto das montanhas saem cinzentos e lisos: falta erosão a sério no relevo.
- As árvores são todas do mesmo tamanho relativo; num mapa ilustrado costumam ser exageradas e mais espaçadas.
- Não há estradas nem rios desenhados na base (continuam no canvas por cima).
- Cores: a paleta é a da base atual; o render pode pedir uma paleta própria.
