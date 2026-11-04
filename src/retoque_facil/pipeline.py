"""Fluxo completo de uma foto: analisar -> revisar marcas -> aplicar -> salvar TIFF."""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import analise as an_mod
from . import cura, espinhas, fundo, imagem_io, pele, previa, tiff_camadas
from .config import pastas
from .espinhas import Marca

MAX_SESSOES = 2  # cada foto grande ocupa algumas centenas de MB na memória


class ErroUsuario(Exception):
    """Erro explicado em linguagem simples, para o Claude repassar."""


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def listar_fotos(pasta: Path) -> list[Path]:
    if not pasta.is_dir():
        return []
    fotos = [p for p in pasta.iterdir() if p.is_file() and p.suffix.lower() in imagem_io.EXTENSOES and not p.name.startswith(".")]
    return sorted(fotos, key=lambda p: p.name.lower())


def resolver_foto(nome: str) -> Path:
    """Aceita caminho completo, nome do arquivo ou parte do nome (na pasta de entrada)."""
    nome = nome.strip().strip('"').strip("'")
    if not nome:
        raise ErroUsuario("diga qual foto (nome do arquivo)")
    direto = Path(nome).expanduser()
    if direto.is_absolute() and direto.is_file():
        return direto
    entrada, _ = pastas()
    fotos = listar_fotos(entrada)
    alvo = _sem_acento(nome)
    exatas = [p for p in fotos if _sem_acento(p.name) == alvo or _sem_acento(p.stem) == alvo]
    if exatas:
        return exatas[0]
    parciais = [p for p in fotos if alvo in _sem_acento(p.name)]
    if len(parciais) == 1:
        return parciais[0]
    if len(parciais) > 1:
        raise ErroUsuario("mais de uma foto combina com esse nome: " + ", ".join(p.name for p in parciais[:10]))
    if direto.is_file():
        return direto.resolve()
    raise ErroUsuario(
        f"não achei a foto '{nome}' na pasta {entrada}. "
        "Coloque a foto nessa pasta ou passe o caminho completo."
    )


def _caminho_livre(pasta: Path, base: str, ext: str) -> Path:
    alvo = pasta / f"{base}{ext}"
    n = 2
    while alvo.exists():
        alvo = pasta / f"{base}_{n}{ext}"
        n += 1
    return alvo


def _nome_seguro(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .")
    return s or "foto"


@dataclass
class Sessao:
    id: str
    foto: imagem_io.Foto
    analise: an_mod.Analise
    grade: previa.Grade
    sensibilidade: str
    marcas: list[Marca]
    diagnostico_fundo: fundo.DiagnosticoFundo
    resultado: np.ndarray | None = None
    ajustes: dict = field(default_factory=dict)
    criada: float = field(default_factory=time.time)

    # ---------- marcas ----------
    def _renumerar(self) -> None:
        for i, m in enumerate(self.marcas, 1):
            m.id = i

    def marca(self, numero: int) -> Marca:
        for m in self.marcas:
            if m.id == numero:
                return m
        raise ErroUsuario(f"não existe a marcação número {numero}")

    def resumo_marcas(self) -> dict:
        remover = [m for m in self.marcas if m.remover]
        manter = [m for m in self.marcas if not m.remover]
        return {
            "rostos": len(self.analise.rostos),
            "vao_ser_removidas": [{"n": m.id, "tipo": m.tipo, "celula": self.grade.nome_da_celula(m.x, m.y)} for m in remover],
            "mantidas": [{"n": m.id, "tipo": m.tipo, "celula": self.grade.nome_da_celula(m.x, m.y)} for m in manter],
        }

    def ajustar(self, nao_remover=(), remover=(), procurar_em=(), sensibilidade_busca="alta", pontos=()) -> list[str]:
        avisos = []
        for n in nao_remover:
            self.marca(int(n)).remover = False
        for n in remover:
            self.marca(int(n)).remover = True
        novas: list[Marca] = []
        for nome in procurar_em:
            regiao = self.grade.celula(nome)
            achou = 0
            for i in range(len(self.analise.rostos)):
                for m in espinhas.detectar_no_rosto(
                    self.foto.rgb, self.analise, i, sensibilidade_busca, regiao=regiao, existentes=self.marcas + novas
                ):
                    if m.tipo == "espinha":
                        m.remover = True
                        novas.append(m)
                        achou += 1
            if not achou:
                avisos.append(f"na célula {nome.upper()} não achei nada com cara de espinha")
        for p in pontos:
            celula, fx, fy = p.get("celula"), float(p.get("x", 0.5)), float(p.get("y", 0.5))
            raio_rel = float(p.get("tamanho", 0.25))
            x0, y0, x1, y1 = self.grade.celula(celula)
            raio = max(2.0, raio_rel * min(x1 - x0, y1 - y0) / 2)
            novas.append(Marca(0, x0 + fx * (x1 - x0), y0 + fy * (y1 - y0), raio, "espinha", 0.0, True, 0, "manual"))
        self.marcas.extend(novas)
        self._renumerar()
        self.resultado = None
        return avisos

    # ---------- retoque ----------
    def aplicar(self, suavizar_pele: str = "leve", limpar_fundo: str = "media", forcar_fundo: bool = False) -> dict:
        t0 = time.time()
        rgb, curadas = cura.remover_marcas(self.foto.rgb, self.analise, self.marcas)
        if suavizar_pele != "nenhuma" and self.analise.rostos:
            rgb = pele.suavizar(rgb, self.analise, suavizar_pele)
        fundo_feito = False
        aviso_fundo = None
        if limpar_fundo != "nao":
            if self.diagnostico_fundo.estudio or forcar_fundo:
                rgb = fundo.limpar(rgb, self.analise, limpar_fundo)
                fundo_feito = True
            else:
                aviso_fundo = f"fundo não foi limpo: {self.diagnostico_fundo.motivo}"
        self.resultado = rgb
        self.ajustes = {
            "espinhas_removidas": curadas,
            "suavizar_pele": suavizar_pele,
            "limpar_fundo": limpar_fundo if fundo_feito else "nao",
            "segundos": round(time.time() - t0, 1),
        }
        if aviso_fundo:
            self.ajustes["aviso"] = aviso_fundo
        return self.ajustes

    def salvar(self, nome: str | None = None, tambem_jpeg: bool = False) -> dict:
        if self.resultado is None:
            raise ErroUsuario("aplique o retoque antes de salvar")
        _, saida = pastas()
        base = _nome_seguro(Path(nome).stem if nome else f"{self.foto.caminho.stem}_retocada")
        destino = _caminho_livre(saida, base, ".tif")
        original = imagem_io.para_inteiro(self.foto.rgb, self.foto.bits)
        retocada = imagem_io.para_inteiro(self.resultado, self.foto.bits)
        tiff_camadas.salvar(destino, original, retocada, icc=self.foto.icc, dpi=self.foto.dpi)
        info = {"tiff": str(destino), "tamanho_mb": round(destino.stat().st_size / 1e6, 1), "bits": self.foto.bits}
        if tambem_jpeg:
            jpg = _caminho_livre(saida, base, ".jpg")
            from PIL import Image

            img = Image.fromarray(imagem_io.para_uint8(self.resultado))
            img.save(jpg, quality=93, icc_profile=self.foto.icc) if self.foto.icc else img.save(jpg, quality=93)
            info["jpeg"] = str(jpg)
        return info


class Gerente:
    """Guarda as sessões abertas (no máximo MAX_SESSOES) e o processamento em lote."""

    def __init__(self) -> None:
        self.sessoes: OrderedDict[str, Sessao] = OrderedDict()
        self.trava = threading.RLock()
        self.lote: dict = {"rodando": False}

    def abrir(self, foto: str, sensibilidade: str = "media") -> Sessao:
        if sensibilidade not in espinhas.SENSIBILIDADES:
            raise ErroUsuario("sensibilidade deve ser 'baixa', 'media' ou 'alta'")
        caminho = resolver_foto(foto)
        try:
            dados = imagem_io.carregar(caminho)
        except imagem_io.FormatoNaoSuportado as e:
            raise ErroUsuario(str(e)) from e
        an = an_mod.analisar(dados.rgb)
        marcas = espinhas.detectar(dados.rgb, an, sensibilidade) if an.rostos else []
        diag = fundo.diagnosticar(dados.rgb, an)
        sid = re.sub(r"[^a-z0-9]+", "-", _sem_acento(caminho.stem)).strip("-")[:30] or "foto"
        with self.trava:
            base, n = sid, 2
            while sid in self.sessoes:
                sid = f"{base}-{n}"
                n += 1
            s = Sessao(sid, dados, an, previa.grade_para(an), sensibilidade, marcas, diag)
            self.sessoes[sid] = s
            while len(self.sessoes) > MAX_SESSOES:
                self.sessoes.popitem(last=False)
        return s

    def pegar(self, sid: str) -> Sessao:
        with self.trava:
            if sid in self.sessoes:
                self.sessoes.move_to_end(sid)
                return self.sessoes[sid]
            if len(self.sessoes) == 1 and not sid:
                return next(iter(self.sessoes.values()))
        raise ErroUsuario(
            f"a sessão '{sid}' não está mais aberta (só guardo as {MAX_SESSOES} últimas fotos). "
            "Analise a foto de novo."
        )

    # ---------- lote ----------
    def iniciar_lote(self, fotos: list[Path], sensibilidade: str, suavizar_pele: str, limpar_fundo: str) -> dict:
        with self.trava:
            if self.lote.get("rodando"):
                raise ErroUsuario("já existe um lote em andamento; acompanhe com status_lote")
            self.lote = {"rodando": True, "total": len(fotos), "feitas": 0, "atual": None,
                         "salvas": [], "erros": [], "inicio": time.time()}

        def trabalhar() -> None:
            for caminho in fotos:
                with self.trava:
                    self.lote["atual"] = caminho.name
                try:
                    dados = imagem_io.carregar(caminho)
                    an = an_mod.analisar(dados.rgb)
                    marcas = espinhas.detectar(dados.rgb, an, sensibilidade) if an.rostos else []
                    s = Sessao("lote", dados, an, previa.grade_para(an), sensibilidade, marcas,
                               fundo.diagnosticar(dados.rgb, an))
                    aj = s.aplicar(suavizar_pele, limpar_fundo)
                    info = s.salvar()
                    with self.trava:
                        self.lote["salvas"].append({"foto": caminho.name, "tiff": info["tiff"],
                                                    "espinhas": aj["espinhas_removidas"],
                                                    "fundo": aj["limpar_fundo"], "aviso": aj.get("aviso")})
                except Exception as e:  # noqa: BLE001 - registra e segue para a próxima foto
                    with self.trava:
                        self.lote["erros"].append({"foto": caminho.name, "erro": str(e)})
                finally:
                    with self.trava:
                        self.lote["feitas"] += 1
            with self.trava:
                self.lote["rodando"] = False
                self.lote["atual"] = None
                self.lote["segundos"] = round(time.time() - self.lote["inicio"], 1)

        threading.Thread(target=trabalhar, daemon=True, name="lote-retoque").start()
        return self.status_lote()

    def status_lote(self) -> dict:
        with self.trava:
            d = {k: v for k, v in self.lote.items() if k != "inicio"}
            if "inicio" in self.lote and self.lote.get("rodando"):
                d["segundos_ate_agora"] = round(time.time() - self.lote["inicio"], 1)
            return d


gerente = Gerente()
