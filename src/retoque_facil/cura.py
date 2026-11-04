"""Remoção de espinhas pelo mesmo princípio do "Pincel de recuperação" do Photoshop.

Para cada espinha, procuramos ao redor um pedaço de pele limpa (doador). Copiamos a TEXTURA
do doador (poros, granulação), mas a COR e o brilho vêm das bordas da própria espinha,
interpolados suavemente para dentro. Assim a área curada combina com a vizinhança e não
fica com aspecto de borrão.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from .analise import Analise
from .espinhas import Marca


def _membrana(valor: np.ndarray, conhecido: np.ndarray) -> np.ndarray:
    """Preenche as áreas desconhecidas interpolando suavemente o que se conhece em volta.

    É o método "push-pull" (pirâmide): rápido e sem costuras.
    """
    niveis = []
    v = valor * conhecido[..., None]
    w = conhecido.astype(np.float32)
    while min(w.shape[:2]) > 3:
        niveis.append((v, w))
        tam = (max(1, (w.shape[1] + 1) // 2), max(1, (w.shape[0] + 1) // 2))
        v = cv2.resize(v, tam, interpolation=cv2.INTER_AREA)
        w = cv2.resize(w, tam, interpolation=cv2.INTER_AREA)
        if v.ndim == 2:
            v = v[..., None]
    total = w.sum()
    media = v.reshape(-1, v.shape[-1]).sum(0) / max(total, 1e-6)
    est = np.where(w[..., None] > 1e-6, v / np.maximum(w[..., None], 1e-6), media)
    for v, w in reversed(niveis):
        sobe = cv2.resize(est, (w.shape[1], w.shape[0]), interpolation=cv2.INTER_LINEAR)
        if sobe.ndim == 2:
            sobe = sobe[..., None]
        conhecido_aqui = v / np.maximum(w[..., None], 1e-6)
        a = np.clip(w, 0, 1)[..., None]
        est = conhecido_aqui * a + sobe * (1 - a)
    return est


def _passa_alta(img: np.ndarray, sigma: float) -> np.ndarray:
    return img - cv2.GaussianBlur(img, (0, 0), sigma)


class Curador:
    def __init__(self, rgb: np.ndarray, analise: Analise, marcas: list[Marca]):
        self.img = rgb.copy()
        self.h, self.w = rgb.shape[:2]
        self.analise = analise
        self.marcas = [m for m in marcas if m.remover]
        self.todas = marcas
        self.valido = self._mascara_doadora()
        self.pendente = np.zeros((self.h, self.w), np.uint8)
        for m in self.marcas:
            cv2.circle(self.pendente, (round(m.x), round(m.y)), int(math.ceil(m.raio * 1.6 + 2)), 255, -1)
        self.sem_doador = 0

    def _mascara_doadora(self) -> np.ndarray:
        """Onde é permitido pegar pele emprestada: pele do rosto, sem olhos/boca/manchas."""
        valido = np.zeros((self.h, self.w), np.uint8)
        for rosto in self.analise.rostos:
            caixa = rosto.caixa(0.12, (self.h, self.w))
            x0, y0, x1, y1 = caixa
            pele, _ = self.analise.mascara_pele(rosto, caixa)
            valido[y0:y1, x0:x1] |= (pele > 0.5).astype(np.uint8) * 255
        for m in self.todas:  # nem espinha nem pinta servem de doador
            cv2.circle(valido, (round(m.x), round(m.y)), int(math.ceil(m.raio * 1.8 + 2)), 0, -1)
        return valido

    def _melhor_doador(self, cx: float, cy: float, R: float, P: int, alvo: np.ndarray, anel: np.ndarray):
        tam = 2 * P + 1
        gy, gx = np.mgrid[-P : P + 1, -P : P + 1]
        disco_total = (gx**2 + gy**2) <= (P - 0.5) ** 2
        L_alvo = alvo[..., 0] * 0.3 + alvo[..., 1] * 0.59 + alvo[..., 2] * 0.11
        anel_px = L_alvo[anel]
        alvo_rel = anel_px - anel_px.mean()
        textura_alvo = float(np.std(_passa_alta(L_alvo, max(1.0, R * 0.25))[anel]))
        melhor, melhor_nota = None, float("inf")
        for fator in (2.3, 3.0, 3.9, 5.0, 6.4):
            dist = fator * R + 1
            n = 16 if fator < 4 else 24
            for k in range(n):
                ang = 2 * math.pi * (k + 0.5 * (fator > 3)) / n
                dx, dy = round(cx + dist * math.cos(ang)), round(cy + dist * math.sin(ang))
                if not (P <= dx < self.w - P and P <= dy < self.h - P):
                    continue
                ok = self.valido[dy - P : dy + P + 1, dx - P : dx + P + 1]
                if ok.shape != (tam, tam) or ok[disco_total].mean() < 254:
                    continue
                if self.pendente[dy - P : dy + P + 1, dx - P : dx + P + 1][disco_total].any():
                    continue
                doador = self.img[dy - P : dy + P + 1, dx - P : dx + P + 1]
                L_d = doador[..., 0] * 0.3 + doador[..., 1] * 0.59 + doador[..., 2] * 0.11
                anel_d = L_d[anel]
                forma = float(np.mean(np.abs(alvo_rel - (anel_d - anel_d.mean()))))
                nivel = abs(float(anel_px.mean() - anel_d.mean()))
                textura = abs(float(np.std(_passa_alta(L_d, max(1.0, R * 0.25))[disco_total])) - textura_alvo)
                nota = forma + 0.25 * nivel + 0.8 * textura + 0.002 * fator
                if nota < melhor_nota:
                    melhor, melhor_nota = (dx, dy), nota
        return melhor

    def curar_uma(self, m: Marca) -> bool:
        R = m.raio * 1.45 + 1.5
        P = int(math.ceil(R * 1.7 + 3))
        cx, cy = round(m.x), round(m.y)
        if not (P <= cx < self.w - P and P <= cy < self.h - P):
            return False
        gy, gx = np.mgrid[-P : P + 1, -P : P + 1]
        dist = np.sqrt((gx + cx - m.x) ** 2 + (gy + cy - m.y) ** 2)
        buraco = dist <= R
        # outras espinhas ainda não tratadas dentro do recorte também entram no "buraco"
        pend = self.pendente[cy - P : cy + P + 1, cx - P : cx + P + 1] > 0
        cv2.circle(self.pendente, (cx, cy), int(math.ceil(m.raio * 1.6 + 2)), 0, -1)
        outras = (self.pendente[cy - P : cy + P + 1, cx - P : cx + P + 1] > 0) & pend
        desconhecido = buraco | outras
        anel = (~desconhecido) & (dist <= P - 0.5)
        if anel.sum() < 12:
            return False

        alvo = self.img[cy - P : cy + P + 1, cx - P : cx + P + 1].copy()
        pos = self._melhor_doador(m.x, m.y, R, P, alvo, anel)
        if pos is None:
            self.sem_doador += 1
            doador = self._textura_sintetica(alvo, anel, R)
        else:
            dx, dy = pos
            doador = self.img[dy - P : dy + P + 1, dx - P : dx + P + 1]

        conhecido = (~desconhecido).astype(np.float32)
        correcao = _membrana(alvo - doador, conhecido)
        curado = doador + correcao
        # transição suave de 1,5 px na borda do buraco
        alfa = np.clip((R + 1.0 - dist) / 2.0, 0.0, 1.0)
        alfa = np.maximum(alfa, outras.astype(np.float32))[..., None]
        self.img[cy - P : cy + P + 1, cx - P : cx + P + 1] = alvo * (1 - alfa) + curado * alfa
        return True

    def _textura_sintetica(self, alvo: np.ndarray, anel: np.ndarray, R: float) -> np.ndarray:
        """Sem doador possível: cor interpolada + granulação parecida com a do entorno."""
        rng = np.random.default_rng(12345)
        hp = _passa_alta(alvo, max(1.0, R * 0.25))
        desvio = np.std(hp[anel], axis=0) if anel.any() else np.full(3, 0.004)
        ruido = rng.normal(0, 1, alvo.shape[:2])[..., None] * desvio[None, None, :]
        ruido = cv2.GaussianBlur(ruido.astype(np.float32), (0, 0), 0.6)
        return np.zeros_like(alvo) + ruido

    def executar(self) -> tuple[np.ndarray, int]:
        feitas = 0
        for m in sorted(self.marcas, key=lambda m: -m.raio):
            if self.curar_uma(m):
                feitas += 1
        return np.clip(self.img, 0, 1), feitas


def remover_marcas(rgb: np.ndarray, analise: Analise, marcas: list[Marca]) -> tuple[np.ndarray, int]:
    if not any(m.remover for m in marcas):
        return rgb.copy(), 0
    return Curador(rgb, analise, marcas).executar()
