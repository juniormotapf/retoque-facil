"""Servidor MCP do Retoque Fácil: as ferramentas que o Claude usa para retocar as fotos."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal, TypedDict

import anyio
from mcp.server.mcpserver import Image, MCPServer
from mcp_types import ToolAnnotations

from . import __version__, previa
from .config import pastas
from .imagem_io import EXTENSOES_RAW
from .pipeline import ErroUsuario, gerente, listar_fotos, resolver_foto

INSTRUCOES = """\
Retoque Fácil: tira espinhas do rosto e limpa fundo de estúdio, salvando um TIFF com a
camada original embaixo e a retocada por cima. Quem usa geralmente NÃO entende de
computador: fale simples, em português, sem termos técnicos, e um passo de cada vez.

Fluxo:
1. listar_fotos — mostra as pastas e as fotos disponíveis. As fotos anexadas no chat NÃO
   chegam a este programa: a pessoa precisa colocar o arquivo na pasta "1 - Fotos para
   retocar" (abrir_no_computador ajuda a abrir a pasta para ela).
2. analisar_foto — devolve uma prévia com as espinhas numeradas (vermelho = vai remover,
   amarelo = pinta/sarda/marca que será mantida) e uma grade A1, B2... Olhe a imagem com
   atenção e confira se as marcas fazem sentido antes de mostrar à pessoa.
3. ajustar_marcacoes — se a pessoa pedir (ou você notar): desmarcar números, incluir uma
   pinta, procurar espinhas que faltaram numa célula da grade. O detector acha bem espinhas
   vermelhas; caroços sem vermelhidão costumam faltar: veja a célula com ver_detalhe (tem
   guias em 1/4) e marque com pontos.
4. aplicar_retoque — mostra antes/depois. Use ver_detalhe em 1 ou 2 células com espinhas
   para conferir de perto se não ficou borrão ou mancha. Só diga que ficou bom depois de olhar.
5. salvar_tiff — só depois que a pessoa aprovar. Informe onde o arquivo ficou.

Nunca remova pintas ou sardas sem a pessoa pedir. Se o fundo não for de estúdio, o
programa não limpa o fundo (explique e só use forcar_fundo se a pessoa insistir).
Para muitas fotos de uma vez: processar_lote + status_lote.
"""

mcp = MCPServer(
    name="retoque-facil",
    title="Retoque Fácil",
    instructions=INSTRUCOES,
    version=__version__,
)

LEITURA = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
ESCRITA = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


def _erro(e: Exception) -> str:
    if isinstance(e, (ErroUsuario, ValueError, FileNotFoundError)):
        return f"Não deu certo: {e}"
    return f"Erro inesperado ({type(e).__name__}): {e}. Tente de novo; se repetir, reinicie o Claude."


def _json(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, indent=1)


def _dimensoes(p: Path) -> str:
    try:
        if p.suffix.lower() in EXTENSOES_RAW:
            import rawpy

            with open(p, "rb") as f, rawpy.imread(f) as raw:
                s = raw.sizes
                w, h = (s.width, s.height) if s.flip not in (5, 6) else (s.height, s.width)
                return f"{w}x{h} (RAW)"
        from PIL import Image as PILImage

        with PILImage.open(p) as im:
            return f"{im.width}x{im.height}"
    except Exception:
        return "?"


class Ponto(TypedDict, total=False):
    celula: str
    x: float
    y: float
    tamanho: float


@mcp.tool(name="listar_fotos", annotations=LEITURA, structured_output=False)
async def listar_fotos_() -> str:
    """Mostra as pastas do Retoque Fácil e as fotos prontas para retocar.

    Chame primeiro. Cria as pastas se ainda não existirem. A pessoa coloca as fotos em
    "1 - Fotos para retocar"; os TIFFs saem em "2 - Fotos prontas".
    """
    try:
        entrada, saida = pastas()
        fotos = listar_fotos(entrada)
        itens = []
        for p in fotos[:60]:
            dim = _dimensoes(p)
            itens.append({"arquivo": p.name, "dimensoes": dim, "mb": round(p.stat().st_size / 1e6, 1)})
        prontas = sorted((p.name for p in saida.glob("*.tif")), key=str.lower)
        return _json({
            "pasta_para_colocar_fotos": str(entrada),
            "pasta_das_fotos_prontas": str(saida),
            "fotos_encontradas": itens,
            "total": len(fotos),
            "ja_retocadas": prontas[-15:],
            "dica": "Se a lista estiver vazia, peça para a pessoa copiar as fotos para a primeira pasta "
                    "(posso abri-la com abrir_no_computador).",
        })
    except Exception as e:
        return _erro(e)


@mcp.tool(annotations=LEITURA, structured_output=False)
async def analisar_foto(foto: str, sensibilidade: Literal["baixa", "media", "alta"] = "media") -> list:
    """Abre uma foto, acha os rostos, marca espinhas e avalia o fundo. Devolve uma prévia.

    foto: nome do arquivo na pasta de entrada (pode ser só parte do nome) ou caminho completo.
    sensibilidade: "media" serve para quase tudo; "alta" acha espinhas mais discretas mas
    pode marcar coisas que não são espinha; "baixa" só as bem visíveis.
    Na prévia: círculo vermelho = será removida; amarelo = pinta/sarda mantida; cinza = desmarcada.
    """
    try:
        s = await anyio.to_thread.run_sync(gerente.abrir, foto, sensibilidade)
        img = await anyio.to_thread.run_sync(previa.previa_marcas, s.foto.rgb, s.grade, s.marcas)
        resumo = s.resumo_marcas()
        texto = {
            "sessao": s.id,
            "arquivo": s.foto.caminho.name,
            "tamanho": f"{s.foto.largura}x{s.foto.altura} ({s.foto.bits} bits)",
            "rostos_encontrados": resumo["rostos"],
            "espinhas_que_serao_removidas": len(resumo["vao_ser_removidas"]),
            "marcas_mantidas": len(resumo["mantidas"]),
            "detalhe_das_marcas": resumo,
            "fundo": {"de_estudio": s.diagnostico_fundo.estudio, "avaliacao": s.diagnostico_fundo.motivo},
            "grade": f"colunas A-{previa.COLUNAS[s.grade.colunas - 1]}, linhas 1-{s.grade.linhas}",
        }
        if not s.analise.rostos:
            texto["aviso"] = "Não encontrei rosto nesta foto. Ainda dá para limpar o fundo."
        return [_json(texto), Image(data=img, format="jpeg")]
    except Exception as e:
        return [_erro(e)]


@mcp.tool(annotations=ESCRITA, structured_output=False)
async def ajustar_marcacoes(
    sessao: str,
    nao_remover: list[int] | None = None,
    remover: list[int] | None = None,
    procurar_em: list[str] | None = None,
    pontos: list[Ponto] | None = None,
) -> list:
    """Corrige as marcações antes de aplicar o retoque. Devolve a prévia atualizada.

    nao_remover: números que NÃO devem ser removidos (ex.: uma pinta que a pessoa gosta).
    remover: números a remover também (ex.: uma mancha amarela que a pessoa quer tirar).
    procurar_em: células da grade (ex.: ["C4", "D5"]) para procurar espinhas que faltaram,
      com sensibilidade alta só ali.
    pontos: marcar à mão quando a busca não achar (comum em caroços sem vermelhidão):
      {"celula": "C4", "x": 0.5, "y": 0.5, "tamanho": 0.2}, com x e y de 0 a 1 dentro da
      célula e tamanho relativo à célula. Leia as posições com ver_detalhe na célula.
    """
    try:
        s = gerente.pegar(sessao)
        avisos = await anyio.to_thread.run_sync(
            lambda: s.ajustar(nao_remover or [], remover or [], procurar_em or [], "alta", pontos or [])
        )
        img = await anyio.to_thread.run_sync(previa.previa_marcas, s.foto.rgb, s.grade, s.marcas)
        resumo = s.resumo_marcas()
        texto = {
            "sessao": s.id,
            "espinhas_que_serao_removidas": len(resumo["vao_ser_removidas"]),
            "marcas_mantidas": len(resumo["mantidas"]),
            "detalhe_das_marcas": resumo,
        }
        if avisos:
            texto["avisos"] = avisos
        return [_json(texto), Image(data=img, format="jpeg")]
    except Exception as e:
        return [_erro(e)]


@mcp.tool(annotations=ESCRITA, structured_output=False)
async def aplicar_retoque(
    sessao: str,
    suavizar_pele: Literal["nenhuma", "leve", "media", "forte"] = "leve",
    limpar_fundo: Literal["nao", "leve", "media", "forte"] = "media",
    forcar_fundo: bool = False,
) -> list:
    """Remove as espinhas marcadas, suaviza a pele e limpa o fundo. Ainda NÃO salva.

    suavizar_pele: "leve" mantém a textura natural (recomendado); "forte" pode parecer artificial.
    limpar_fundo: "nao" deixa o fundo como está. Só funciona em fundo liso de estúdio, a não
      ser que forcar_fundo=True (use só se a pessoa insistir).
    Devolve antes/depois do rosto (e da foto inteira, se o fundo foi limpo).
    """
    try:
        s = gerente.pegar(sessao)
        aj = await anyio.to_thread.run_sync(s.aplicar, suavizar_pele, limpar_fundo, forcar_fundo)
        saida: list = [_json({"sessao": s.id, **aj, "proximo_passo": "confira com ver_detalhe; depois salvar_tiff"})]
        g = s.grade
        if s.analise.rostos:
            saida.append(Image(data=previa.lado_a_lado(s.foto.rgb, s.resultado, (g.x0, g.y0, g.x1, g.y1)), format="jpeg"))
        if aj.get("limpar_fundo") != "nao" or not s.analise.rostos:
            caixa = (0, 0, s.foto.largura, s.foto.altura)
            saida.append(Image(data=previa.lado_a_lado(s.foto.rgb, s.resultado, caixa, 1200), format="jpeg"))
        return saida
    except Exception as e:
        return [_erro(e)]


@mcp.tool(annotations=LEITURA, structured_output=False)
async def ver_detalhe(sessao: str, celula: str) -> list:
    """Mostra uma célula da grade de perto (ex.: "C4"), em resolução real.

    Antes de aplicar o retoque mostra só a foto com as marcações; depois mostra antes/depois.
    A célula aparece com borda branca e linhas tracejadas em 1/4, 1/2 e 3/4: use-as para ler
    as posições x e y (0 a 1) de uma espinha que faltou e marcá-la com ajustar_marcacoes(pontos=...).
    """
    try:
        s = gerente.pegar(sessao)
        img = await anyio.to_thread.run_sync(
            lambda: previa.detalhe_celula(s.foto.rgb, s.resultado, s.grade, celula, s.marcas)
        )
        if s.resultado is None:
            legenda = f"Célula {celula.upper()} de perto, ainda sem retoque. Linhas tracejadas = 0,25 / 0,5 / 0,75."
        else:
            legenda = f"Célula {celula.upper()}: antes à esquerda, depois à direita."
        return [legenda, Image(data=img, format="jpeg")]
    except Exception as e:
        return [_erro(e)]


@mcp.tool(annotations=ESCRITA, structured_output=False)
async def salvar_tiff(sessao: str, nome_arquivo: str | None = None, tambem_jpeg: bool = False) -> str:
    """Salva o resultado em TIFF na pasta "2 - Fotos prontas" (nunca sobrescreve nada).

    O TIFF tem duas camadas: "Original" embaixo e "Retocada" por cima, mesma resolução e
    profundidade de cor da foto (8 ou 16 bits) e o mesmo perfil de cor.
    tambem_jpeg: salva também um JPEG leve, bom para mandar por WhatsApp ou e-mail.
    """
    try:
        s = gerente.pegar(sessao)
        info = await anyio.to_thread.run_sync(s.salvar, nome_arquivo, tambem_jpeg)
        return _json({"salvo": True, **info,
                      "camadas": ["Original (embaixo)", "Retocada (em cima)"],
                      "abre_em": "Photoshop, Affinity Photo, GIMP 3, Krita, PhotoCraft"})
    except Exception as e:
        return _erro(e)


@mcp.tool(annotations=ESCRITA, structured_output=False)
async def abrir_no_computador(
    o_que: Literal["pasta_de_entrada", "pasta_de_prontas", "arquivo"] = "pasta_de_entrada",
    caminho: str | None = None,
) -> str:
    """Abre uma pasta (ou um arquivo) na tela da pessoa, no Explorador de Arquivos/Finder.

    Útil para ela arrastar fotos para a pasta de entrada ou ver os TIFFs prontos.
    """
    try:
        entrada, saida = pastas()
        if o_que == "pasta_de_entrada":
            alvo = entrada
        elif o_que == "pasta_de_prontas":
            alvo = saida
        else:
            if not caminho:
                raise ErroUsuario("diga qual arquivo abrir")
            alvo = Path(caminho)
            if not alvo.exists():
                alvo = resolver_foto(caminho)
        if sys.platform == "win32":
            os.startfile(str(alvo))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(alvo)])
        else:
            subprocess.Popen(["xdg-open", str(alvo)])
        return f"Abri: {alvo}"
    except Exception as e:
        return _erro(e)


@mcp.tool(annotations=ESCRITA, structured_output=False)
async def processar_lote(
    fotos: list[str] | None = None,
    sensibilidade: Literal["baixa", "media", "alta"] = "media",
    suavizar_pele: Literal["nenhuma", "leve", "media", "forte"] = "leve",
    limpar_fundo: Literal["nao", "leve", "media", "forte"] = "media",
) -> str:
    """Retoca várias fotos sozinho, em segundo plano, e salva um TIFF de cada.

    fotos: nomes dos arquivos; se vazio, usa todas as fotos da pasta de entrada.
    Não há revisão foto a foto: as marcações automáticas são aplicadas como estão.
    Acompanhe com status_lote.
    """
    try:
        if fotos:
            lista = [resolver_foto(f) for f in fotos]
        else:
            entrada, _ = pastas()
            lista = listar_fotos(entrada)
        if not lista:
            raise ErroUsuario("não há fotos na pasta de entrada")
        return _json(gerente.iniciar_lote(lista, sensibilidade, suavizar_pele, limpar_fundo))
    except Exception as e:
        return _erro(e)


@mcp.tool(annotations=LEITURA, structured_output=False)
async def status_lote() -> str:
    """Mostra o andamento do processamento em lote (quantas fotos já foram, erros, arquivos salvos)."""
    try:
        return _json(gerente.status_lote())
    except Exception as e:
        return _erro(e)


@mcp.prompt(name="retocar_fotos", title="Retocar fotos")
def retocar_fotos() -> str:
    """Começa o retoque guiado: tirar espinhas e limpar o fundo das fotos."""
    return (
        "Quero retocar minhas fotos: tirar espinhas do rosto e limpar o fundo de estúdio. "
        "Me guie passo a passo, em linguagem simples, e me mostre o antes e depois antes de salvar."
    )


def main() -> None:
    try:
        mcp.run(transport="stdio")
    finally:
        from .analise import modelos

        modelos.fechar()


if __name__ == "__main__":
    main()
