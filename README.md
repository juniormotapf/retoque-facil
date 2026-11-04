# Retoque Fácil

Tira espinhas do rosto e limpa fundo de estúdio, **com o Claude no comando**. Você conversa
em português, o Claude mostra o antes e depois, e o resultado sai em **TIFF com duas
camadas**: a foto **Original embaixo** e a **Retocada por cima**.

- Funciona no seu computador: **sem internet** depois de instalado e **sem placa de vídeo**.
- Marca as espinhas numa prévia numerada antes de mexer; você escolhe o que fica.
- **Preserva pintas e sardas** (só remove se você pedir).
- Remove cada espinha com pele limpa da vizinhança, mantendo poros e textura (o mesmo
  princípio do "pincel de recuperação" do Photoshop).
- Suaviza a pele de leve, sem cara de plástico.
- Limpa poeira, sujeira e dobras de **fundos lisos de estúdio**, mantendo o degradê de luz
  e protegendo os fios de cabelo.
- **Sempre apaga a linha onde a parede encontra o piso** (horizonte do estúdio), deixando um
  fundo infinito, inclusive atrás das pernas.
- Aceita JPEG, PNG, TIFF, WebP e **RAW de câmera** (NEF, CR2, CR3, ARW, RAF, DNG, ORF, RW2...).
- Funciona em close, meio corpo e **corpo inteiro** (o rosto pequeno é procurado de perto).
- O TIFF mantém a resolução, a profundidade de cor (8 ou 16 bits) e o perfil de cor da foto.
  Abre em camadas no Photoshop, Affinity Photo, GIMP 3, Krita e PhotoCraft.

---

## Do que você precisa

- **Windows 10 ou 11**, ou **Mac com chip Apple** (M1 ou mais novo).
- O aplicativo **Claude Desktop** instalado e com sua conta: https://claude.ai/download
- Internet só durante a instalação (baixa uns 300 MB uma única vez).

## Instalação

### 1. Baixe o programa

Na página do projeto no GitHub, clique em **Releases** e baixe `RetoqueFacil.zip`
(ou no botão verde **Code > Download ZIP**). Clique com o botão direito no arquivo baixado e
escolha **Extrair tudo**.

### 2. Rode o instalador

- **Windows:** dê dois cliques em **`Instalar no Windows.bat`**.
  Se aparecer "O Windows protegeu o computador", clique em **Mais informações > Executar assim mesmo**.
- **Mac:** clique com o botão direito em **`Instalar no Mac.command`** > **Abrir** > **Abrir**.

Uma janela preta vai mostrar o andamento. Espere aparecer **PRONTO** (a primeira vez pode levar
alguns minutos). O instalador:

1. copia o programa para uma pasta fixa do seu usuário;
2. baixa o Python e os componentes;
3. testa os modelos;
4. cria as pastas **Documentos > Retoque Facil > 1 - Fotos para retocar** e **2 - Fotos prontas**;
5. liga o Retoque Fácil no Claude Desktop (guardando uma cópia de segurança da configuração).

### 3. Reinicie o Claude

Feche o Claude **de vez** e abra de novo.
No Windows: botão direito no ícone do Claude perto do relógio > **Sair**.

### 4. Envie a skill (o "manual" que ensina o Claude a usar o programa)

No final, o instalador abre a pasta com o arquivo **`retoque-de-pele.zip`**. No Claude:

**Personalizar (Customize) > Skills > + > Criar skill (Create skill) > Enviar skill (Upload a skill)**
e escolha esse arquivo.

> Se o envio de skills não aparecer, ative em **Configurações > Recursos (Capabilities)** a opção
> "Execução de código e criação de arquivos" (pode aparecer como "Criar e editar arquivos").
> O Retoque Fácil funciona mesmo sem a skill, mas com ela o Claude conduz melhor a conversa.

### Alternativa: extensão de um clique (experimental)

Na página de Releases também há **`retoque-facil.mcpb`**. Com o Claude Desktop aberto, dê dois
cliques nele (ou arraste para **Configurações > Extensões**) e clique em **Instalar**. O Claude
baixa os componentes sozinho na primeira vez que o programa for usado; se as ferramentas não
aparecerem, espere uns minutos e reinicie o Claude. Se não der certo, use o instalador acima.
Use **um** dos dois caminhos, não os dois.

---

## Como usar

1. Copie as fotos para **Documentos > Retoque Facil > 1 - Fotos para retocar**.
   (Fotos anexadas no chat não chegam ao programa; elas precisam estar nessa pasta.)
2. No Claude, escreva: **Retoque minhas fotos**.
3. O Claude mostra a foto com as espinhas marcadas e uma grade (A1, B2...):
   - **vermelho** = vai remover · **amarelo** = pinta/sarda que fica · **cinza** = desmarcado.
4. Diga o que quer mudar, por exemplo:
   - "Não tira a 4, é uma pinta que eu gosto."
   - "Tem uma espinha no queixo, perto da célula D7, que não foi marcada."
   - "Pode tirar a mancha 9 também."
5. O Claude aplica, mostra o antes e depois e confere de perto. Se gostar, diga **pode salvar**.
6. O TIFF aparece em **2 - Fotos prontas**. Peça "salva também em JPEG" se for mandar por WhatsApp.

Outros pedidos que funcionam:
- "Retoque todas as fotos da pasta de uma vez" (processamento em lote, sem revisão foto a foto).
- "Suaviza a pele um pouco mais" / "Deixa a pele bem natural".
- "Só limpa o fundo, não mexe no rosto".
- "Abre a pasta das fotos prontas".

## Dúvidas comuns

**O Claude diz que não tem as ferramentas do Retoque Fácil.**
Feche o Claude de vez (Sair, não só fechar a janela) e abra de novo. Se continuar, rode o
instalador outra vez.

**Foto de iPhone (HEIC).** Exporte como JPEG antes. No iPhone dá para fotografar direto
em JPEG em Ajustes > Câmera > Formatos > "Mais Compatível".

**RAW.** É revelado de forma neutra (balanço de branco da câmera, 16 bits). Se você já tratou
cor e exposição no Lightroom ou similar, exporte um TIFF e use esse arquivo.

**Ficou uma espinha para trás.** O detector acha bem espinhas vermelhas; caroços sem vermelhidão
(comuns sob maquiagem) às vezes escapam. É só falar: "tem uma no queixo, na célula F7". O Claude
olha a célula de perto e marca à mão.

**O fundo não foi limpo.** O programa só limpa fundo liso de estúdio. Paisagem, parede com
textura ou fundo desfocado de rua ele deixa como está, de propósito.

**Mac com processador Intel.** Ainda não é suportado (um dos componentes não existe para Intel).

**Desinstalar.** Windows: dois cliques em `Desinstalar no Windows.bat`. As suas fotos não são apagadas.

---

## Para desenvolvedores

### Como funciona

| Etapa | Arquivo | Método |
|---|---|---|
| Rostos e pele | `analise.py` | MediaPipe Face Landmarker (478 pontos) + Selfie Multiclass (fundo, cabelo, pele, roupa, acessórios). Rostos pequenos (corpo inteiro) são procurados de novo num recorte da cabeça, e a segmentação é refeita de perto em volta de cada rosto. Olhos, sobrancelhas, boca, narinas, dobras do sorriso e brincos ficam protegidos. |
| Espinhas | `espinhas.py` | Rosto normalizado para 600 px; diferença de a\* (vermelhidão) e L\* para a vizinhança, detecção de manchas redondas em várias escalas (DoG), teste da Hessiana para rejeitar linhas e rugas, limiar adaptado ao ruído de cada pele. Manchas escuras não vermelhas viram "mancha" e são mantidas. |
| Remoção | `cura.py` | Estilo pincel de recuperação: busca de doador na pele vizinha, textura do doador + correção de cor por interpolação de membrana (push-pull) a partir da borda. |
| Pele | `pele.py` | Separação de frequências: atenua só a banda média (manchinhas), mantém poros; barba excluída. |
| Fundo | `fundo.py` | Máscara da pessoa refinada com filtro guiado; fundo estimado sem a pessoa e suavizado com filtro guiado (apaga poeira, riscos e vincos, mantém sombras); a linha parede/piso é apagada por uma correção que depende só da altura, medida em 6 faixas verticais (perfil de brilho suavizado), aplicada até colada na pessoa; granulação original reaplicada; proteção larga em volta do cabelo; só age em fundo diagnosticado como liso. |
| TIFF | `tiff_camadas.py` | TIFF big-endian, imagem achatada em Deflate + tag 37724 (ImageSourceData) com a "layer info" do PSD em RLE (`Layr` para 8 bits, `Lr16` para 16 bits). |
| Servidor | `server.py` | Servidor MCP (SDK Python 2.x, stdio) com 9 ferramentas e um prompt. |

### Rodar localmente

```bash
uv sync
uv run pytest
uv run server.py   # servidor MCP em stdio
```

Variável `RETOQUE_PASTA` muda a pasta base (padrão: `Documentos/Retoque Facil`).

### Gerar os pacotes de distribuição

```bash
uv run python scripts/empacotar.py   # cria dist/RetoqueFacil.zip, dist/retoque-de-pele.zip e dist/retoque-facil.mcpb
```

O workflow `.github/workflows/release.yml` faz o mesmo ao criar uma tag `v*` e anexa os
arquivos à Release. O `testes.yml` roda os testes em Windows, macOS e Linux a cada push.

### O que foi testado

- Detecção: espinhas sintéticas em 8 retratos reais (peles e luzes diferentes): na
  sensibilidade "media", 81% a 95% encontradas, com 0 a 4 marcações extras por rosto limpo;
  sardas e pintas preservadas.
- TIFF: camadas lidas de volta com valores idênticos (8 e 16 bits) por dois leitores
  independentes (ImageMagick lendo o TIFF e psd-tools lendo a mesma estrutura em PSD).
- Servidor: ponta a ponta via cliente MCP, inclusive com versões antigas do protocolo.
- Foto real de estúdio em RAW (NEF de 24 MP, corpo inteiro, 16 bits): rosto achado, brincos
  protegidos, rachaduras e manchas da parede removidas, linha parede/piso apagada, TIFF de 16 bits com as duas camadas.
- Ainda não testado em: Photoshop/Affinity reais, instalação da extensão `.mcpb` no Claude Desktop.

### Licença

Código MIT. Modelos do MediaPipe (Google) sob Apache-2.0. Veja `THIRD_PARTY_NOTICES.md`.
