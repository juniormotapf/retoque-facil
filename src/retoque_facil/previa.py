"""Imagens de conferência que o Claude (e a pessoa) olham antes de salvar."""

from __future__ import annotations

import string
from dataclasses import dataclass

import cv2
import numpy as np

from .analise import Analise
from .espinhas import Marca
from .imagem_io import jpeg_bytes, para_uint8

LADO_PREVIA = 1300
COR_REMOVER = (230, 40, 40)
COR_MANTER = (250, 210, 0)
COR_IGNORAR = (150, 150, 150)
COLUNAS = string.ascii_uppercase


@dataclass
class Grade:
    """Grade de referência (A1, B3...) desenhada sobre a área dos rostos."""

    x0: int
    y0: int
    x1: int
    y1: int
    colunas: int
    linhas: int

    def celula(self, nome: str) -> tuple[int, int, int, int]:
        nome = nome.strip().upper().replace(" ", "")
        if len(nome) < 2 or nome[0] not in COLUNAS[: self.colunas] or not nome[1:].isdigit():
            raise ValueError(
                f"célula '{nome}' não existe. Use letra de A a {COLUNAS[self.colunas - 1]} "
                f"e número de 1 a {self.linhas}, por exemplo C4."
            )
        c, li = COLUNAS.index(nome[0]), int(nome[1:]) - 1
        if not 0 <= li < self.linhas:
            raise ValueError(f"a linha vai de 1 a {self.linhas}")
        lw, lh = (self.x1 - self.x0) / self.colunas, (self.y1 - self.y0) / self.linhas
        return (round(self.x0 + c * lw), round(self.y0 + li * lh), round(self.x0 + (c + 1) * lw), round(self.y0 + (li + 1) * lh))

    def nome_da_celula(self, x: float, y: float) -> str:
        c = int((x - self.x0) / (self.x1 - self.x0) * self.colunas)
        li = int((y - self.y0) / (self.y1 - self.y0) * self.linhas)
        c, li = min(max(c, 0), self.colunas - 1), min(max(li, 0), self.linhas - 1)
        return f"{COLUNAS[c]}{li + 1}"


def grade_para(analise: Analise) -> Grade:
    if analise.rostos:
        caixas = [r.caixa(0.3, (analise.altura, analise.largura)) for r in analise.rostos]
        x0, y0 = min(c[0] for c in caixas), min(c[1] for c in caixas)
        x1, y1 = max(c[2] for c in caixas), max(c[3] for c in caixas)
    else:
        x0, y0, x1, y1 = 0, 0, analise.largura, analise.altura
    w, h = x1 - x0, y1 - y0
    colunas = max(4, min(10, round(8 * w / max(h, 1)))) if w >= h else 8
    linhas = 8 if w >= h else max(4, min(10, round(8 * h / max(w, 1))))
    return Grade(x0, y0, x1, y1, colunas, linhas)


def _escalar(img: np.ndarray, lado: int) -> tuple[np.ndarray, float]:
    h, w = img.shape[:2]
    e = min(1.0, lado / max(h, w))
    if e < 1:
        img = cv2.resize(img, (round(w * e), round(h * e)), interpolation=cv2.INTER_AREA)
    return img, e


def _texto(img, texto, org, escala, cor, espessura=1):
    cv2.putText(img, texto, org, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), espessura + 2, cv2.LINE_AA)
    cv2.putText(img, texto, org, cv2.FONT_HERSHEY_SIMPLEX, escala, cor, espessura, cv2.LINE_AA)


def _desenhar_grade(img: np.ndarray, grade: Grade, e: float, margem: int) -> None:
    h, w = img.shape[:2]
    gx0, gy0 = margem, margem
    lw = (w - margem) / grade.colunas
    lh = (h - margem) / grade.linhas
    sobre = img.copy()
    for c in range(1, grade.colunas):
        x = int(gx0 + c * lw)
        cv2.line(sobre, (x, gy0), (x, h), (255, 255, 255), 1, cv2.LINE_AA)
    for li in range(1, grade.linhas):
        y = int(gy0 + li * lh)
        cv2.line(sobre, (gx0, y), (w, y), (255, 255, 255), 1, cv2.LINE_AA)
    cv2.addWeighted(sobre, 0.35, img, 0.65, 0, dst=img)
    escala = max(0.45, min(0.8, lw / 90))
    for c in range(grade.colunas):
        _texto(img, COLUNAS[c], (int(gx0 + (c + 0.42) * lw), int(margem * 0.75)), escala, (255, 255, 255), 1)
    for li in range(grade.linhas):
        _texto(img, str(li + 1), (4, int(gy0 + (li + 0.58) * lh)), escala, (255, 255, 255), 1)


def previa_marcas(rgb: np.ndarray, grade: Grade, marcas: list[Marca]) -> bytes:
    """Recorte dos rostos com as marcas numeradas e a grade de referência."""
    recorte = para_uint8(rgb[grade.y0 : grade.y1, grade.x0 : grade.x1])
    recorte, e = _escalar(recorte, LADO_PREVIA - 30)
    margem = 30
    tela = np.zeros((recorte.shape[0] + margem, recorte.shape[1] + margem, 3), np.uint8)
    tela[:] = (35, 35, 35)
    tela[margem:, margem:] = recorte
    _desenhar_grade(tela, grade, e, margem)
    espessura = max(1, round(tela.shape[1] / 650))
    for m in marcas:
        cx = int(round((m.x - grade.x0) * e)) + margem
        cy = int(round((m.y - grade.y0) * e)) + margem
        r = max(7, int(round(m.raio * 1.9 * e)) + 3)
        if m.remover:
            cor = COR_REMOVER
        elif m.tipo == "mancha":
            cor = COR_MANTER
        else:
            cor = COR_IGNORAR
        cv2.circle(tela, (cx, cy), r, cor, espessura, cv2.LINE_AA)
        _texto(tela, str(m.id), (cx + r + 1, cy - r // 2), 0.5 if tela.shape[1] < 900 else 0.6, cor, 1)
    return jpeg_bytes(tela, 86)


def lado_a_lado(antes: np.ndarray, depois: np.ndarray, caixa: tuple[int, int, int, int], lado: int = LADO_PREVIA) -> bytes:
    x0, y0, x1, y1 = caixa
    a = para_uint8(antes[y0:y1, x0:x1])
    b = para_uint8(depois[y0:y1, x0:x1])
    junto = np.concatenate([a, np.full((a.shape[0], max(4, a.shape[1] // 120), 3), 255, np.uint8), b], axis=1)
    junto, _ = _escalar(junto, lado)
    if junto.shape[1] < 700:  # recorte pequeno: amplia sem suavizar, para ver os pixels
        f = 700 / junto.shape[1]
        junto = cv2.resize(junto, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST)
    faixa = np.full((34, junto.shape[1], 3), 35, np.uint8)
    metade = junto.shape[1] // 2
    _texto(faixa, "ANTES", (10, 24), 0.7, (255, 255, 255), 2)
    _texto(faixa, "DEPOIS", (metade + 10, 24), 0.7, (255, 255, 255), 2)
    return jpeg_bytes(np.concatenate([faixa, junto], axis=0), 86)


def detalhe_celula(
    antes: np.ndarray,
    depois: np.ndarray | None,
    grade: Grade,
    nome: str,
    marcas: list[Marca],
) -> bytes:
    """Zoom numa célula com a borda dela e linhas a cada 1/4, para marcar pontos com precisão.

    As linhas tracejadas da célula valem 0,25 / 0,5 / 0,75 (x da esquerda para a direita,
    y de cima para baixo). Sem `depois`, mostra só a foto original com as marcações.
    """
    cx0, cy0, cx1, cy1 = grade.celula(nome)
    mx, my = (cx1 - cx0) // 4, (cy1 - cy0) // 4
    h, w = antes.shape[:2]
    x0, y0, x1, y1 = max(0, cx0 - mx), max(0, cy0 - my), min(w, cx1 + mx), min(h, cy1 + my)

    def painel(img: np.ndarray, com_marcas: bool) -> np.ndarray:
        p = para_uint8(img[y0:y1, x0:x1]).copy()
        f = max(1.0, 520 / max(p.shape[:2]))
        p = cv2.resize(p, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC if f > 1 else cv2.INTER_AREA)
        def pt(x, y):
            return int(round((x - x0) * f)), int(round((y - y0) * f))
        cv2.rectangle(p, pt(cx0, cy0), pt(cx1, cy1), (255, 255, 255), 1, cv2.LINE_AA)
        for q in (0.25, 0.5, 0.75):
            xq = cx0 + q * (cx1 - cx0)
            yq = cy0 + q * (cy1 - cy0)
            for t in range(0, 400, 8):  # tracejado
                a = pt(xq, cy0 + (cy1 - cy0) * t / 400)
                b = pt(xq, cy0 + (cy1 - cy0) * min(t + 4, 400) / 400)
                cv2.line(p, a, b, (255, 255, 255), 1)
                a = pt(cx0 + (cx1 - cx0) * t / 400, yq)
                b = pt(cx0 + (cx1 - cx0) * min(t + 4, 400) / 400, yq)
                cv2.line(p, a, b, (255, 255, 255), 1)
        if com_marcas:
            for m in marcas:
                if x0 <= m.x < x1 and y0 <= m.y < y1:
                    cor = COR_REMOVER if m.remover else (COR_MANTER if m.tipo == "mancha" else COR_IGNORAR)
                    cv2.circle(p, pt(m.x, m.y), max(5, int(m.raio * 1.9 * f)), cor, 1, cv2.LINE_AA)
                    _texto(p, str(m.id), pt(m.x + m.raio * 2, m.y), 0.45, cor, 1)
        return p

    a = painel(antes, True)
    paineis = [a] if depois is None else [a, np.full((a.shape[0], 6, 3), 255, np.uint8), painel(depois, False)]
    junto = np.concatenate(paineis, axis=1)
    faixa = np.full((34, junto.shape[1], 3), 35, np.uint8)
    _texto(faixa, f"{nome.upper()} ANTES", (10, 24), 0.6, (255, 255, 255), 1)
    if depois is not None:
        _texto(faixa, "DEPOIS", (a.shape[1] + 16, 24), 0.6, (255, 255, 255), 1)
    return jpeg_bytes(np.concatenate([faixa, junto], axis=0), 88)
