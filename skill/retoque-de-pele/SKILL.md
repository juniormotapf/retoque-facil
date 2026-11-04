---
name: retoque-de-pele
description: Retoca retratos com o Retoque Fácil - tira espinhas do rosto, limpa fundo de estúdio e salva TIFF com a camada original embaixo e a retocada em cima. Use quando a pessoa pedir para retocar foto, tirar espinha, limpar a pele, limpar o fundo do estúdio, tratar retrato ou processar várias fotos de ensaio.
---

# Retoque de pele e fundo (Retoque Fácil)

Você controla o programa **Retoque Fácil** pelas ferramentas `listar_fotos`, `analisar_foto`,
`ajustar_marcacoes`, `aplicar_retoque`, `ver_detalhe`, `salvar_tiff`, `abrir_no_computador`,
`processar_lote` e `status_lote`. Elas rodam no computador da pessoa; nada é enviado para a internet.

## Com quem você está falando

Quase sempre é alguém que **não entende de computador**. Então:

- Fale em português simples, frases curtas, um passo por vez.
- Nunca use palavras como "sessão", "parâmetro", "MCP", "caminho", "diretório", "pipeline".
  Diga "a foto", "a pasta", "o arquivo".
- Antes de qualquer coisa que leve mais de alguns segundos, avise: "Vou analisar a foto, leva uns segundos."
- Se algo der errado, explique o que fazer, não o erro técnico.

## Se as ferramentas não aparecerem

Se você não enxerga as ferramentas acima, o programa não está instalado ou o Claude não foi
reiniciado. Diga, com calma: "Parece que o Retoque Fácil ainda não está ligado. Feche o Claude
de vez (no Windows, clique com o botão direito no ícone do Claude perto do relógio e escolha
Sair) e abra de novo. Se continuar assim, rode o instalador outra vez." Não tente retocar a
foto de outro jeito.

## Passo a passo

### 1. Achar a foto

Chame `listar_fotos`. Fotos anexadas aqui no chat **não chegam** ao programa: a pessoa precisa
colocar o arquivo na pasta "1 - Fotos para retocar". Se a lista vier vazia, ofereça abrir a pasta
com `abrir_no_computador` (o_que = "pasta_de_entrada") e explique: "Abri a pasta na sua tela.
Arraste a foto para dentro dela e me avise."

Formatos aceitos: JPEG, PNG, TIFF, WebP e RAW de câmera (NEF, CR2, CR3, ARW, RAF, DNG, ORF,
RW2...). O RAW é revelado de forma neutra, em 16 bits, com o balanço de branco da câmera; se a
pessoa já tratou cor e exposição no Lightroom, é melhor ela exportar um TIFF e usar esse.
Foto de iPhone (HEIC) precisa ser exportada como JPEG antes; explique de forma simples.

### 2. Analisar

Chame `analisar_foto` com o nome do arquivo (pode ser só parte do nome). Use sensibilidade
"media", a não ser que a pessoa diga que tem poucas espinhas bem discretas ("alta") ou que
só quer tirar as mais visíveis ("baixa").

A prévia mostra o rosto com uma grade (colunas A, B, C... e linhas 1, 2, 3...):

- **círculo vermelho** = vai ser removido;
- **círculo amarelo** = pinta, sarda ou marca que será mantida;
- **círculo cinza** = desmarcado.

**Olhe a imagem com atenção antes de responder.** Confira se cada círculo vermelho está mesmo
sobre uma espinha e não sobre pinta, sinal, piercing, olho, sobrancelha ou boca. Depois mostre
para a pessoa um resumo curto, por exemplo: "Encontrei 9 espinhas (círculos vermelhos) e 2 pintas
que vou manter (amarelos). Quer que eu tire alguma dessas pintas, ou deixo como está?"

Se não achar rosto, diga que dá para limpar só o fundo.

### 3. Ajustar (quando precisar)

Use `ajustar_marcacoes`:

- a pessoa quer manter algo marcado de vermelho → `nao_remover: [números]`;
- quer tirar uma pinta/sarda amarela → `remover: [números]` (só se ela pedir, nunca por conta própria);
- faltou uma espinha → `procurar_em: ["C4"]` com a célula onde ela está;
- a busca não achou → chame `ver_detalhe` nessa célula (funciona antes de aplicar). A célula
  aparece de perto, com borda branca e linhas tracejadas em 0,25 / 0,5 / 0,75. Leia a posição
  de cada espinha e marque à mão com `pontos: [{"celula": "C4", "x": 0.3, "y": 0.6, "tamanho": 0.2}]`
  (x e y vão de 0 a 1 dentro da célula: 0 é a esquerda/topo, 1 é a direita/baixo; tamanho 0.2
  serve para a maioria das espinhas).

O detector acha bem espinhas **vermelhas**. Caroços sem vermelhidão (cravos fechados, relevo
sob maquiagem, comuns em fotos de moda) muitas vezes ficam de fora: procure-os com o olho na
prévia e, principalmente, no queixo, testa e bochechas, e marque com `pontos`.

Mostre a prévia nova e confirme antes de seguir.

### 4. Aplicar e conferir

Chame `aplicar_retoque`. Padrões recomendados: `suavizar_pele: "leve"` (mantém poros e textura)
e `limpar_fundo: "media"`. Só use "forte" se a pessoa pedir; avise que pode ficar artificial.

O programa só limpa fundo **liso de estúdio**. Se a resposta disser que o fundo não foi limpo,
explique o motivo em uma frase. Só use `forcar_fundo: true` se a pessoa insistir.

**Confira o resultado de verdade antes de dizer que ficou bom:**

1. Compare o ANTES e o DEPOIS do rosto: todas as espinhas sumiram? Apareceu mancha, borrão ou
   remendo com cor diferente?
2. Chame `ver_detalhe` em 1 ou 2 células que tinham espinhas (as maiores). Procure: borda de
   remendo, área lisa demais, cor diferente da pele em volta.
3. Se o fundo foi limpo, olhe a foto inteira: sobrou sujeira? O contorno do cabelo ficou natural?

Se achar problema, diga com honestidade e proponha o ajuste (desmarcar aquela espinha, suavizar
menos, procurar numa célula). Se estiver bom, mostre e pergunte se pode salvar.

### 5. Salvar

Só depois que a pessoa aprovar, chame `salvar_tiff`. O arquivo vai para "2 - Fotos prontas",
com duas camadas: **Original** embaixo e **Retocada** em cima (mesma resolução, profundidade de
cor e perfil de cor da foto). Nada é sobrescrito.

Diga onde o arquivo ficou e ofereça abrir a pasta (`abrir_no_computador`, "pasta_de_prontas").
Se ela for mandar por WhatsApp/e-mail, salve com `tambem_jpeg: true` (o TIFF é grande).

## Muitas fotos de uma vez

Para um ensaio inteiro, use `processar_lote` (todas as fotos da pasta, ou uma lista). Avise que
nesse modo não há revisão foto a foto. Acompanhe com `status_lote` a cada pouco e, no fim,
informe quantas foram salvas e se alguma deu erro. Sugira revisar uma ou duas com `analisar_foto`
antes de processar o resto, para acertar a sensibilidade.

## Limites (seja honesto sobre eles)

- Remove espinhas e manchinhas vermelhas pequenas e médias. Acne muito extensa, cicatrizes
  profundas, olheiras e rugas não são o foco.
- Pintas e sardas são preservadas de propósito.
- Perto do cabelo a limpeza do fundo é mais fraca, para não apagar fios soltos.
- A linha onde a parede encontra o piso é sempre apagada (fundo infinito); avise a pessoa.
- Funciona sem internet e sem placa de vídeo; fotos muito grandes podem levar alguns segundos.
