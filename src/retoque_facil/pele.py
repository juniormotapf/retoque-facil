"""Suavização de pele por separação de frequências.

Separa a pele em três camadas: textura fina (poros), tons médios (manchinhas, vermelhidão
irregular, marcas suaves) e iluminação geral. Só os tons médios são atenuados. Os poros
ficam intactos, então a pele não ganha aspecto de plástico.
"""

from __future__ import annotations

import cv2
import numpy as np

from .analise import Analise
from .espinhas import _mapas

INTENSIDADES = {"nenhuma": 0.0, "leve": 0.35, "media": 0.55, "forte": 0.75}


def suavizar(rgb: np.ndarray, analise: Analise, intensidade: str | float = "leve") -> np.ndarray:
    k = INTENSIDADES.get(intensidade, intensidade) if isinstance(intensidade, str) else float(intensidade)
    k = float(np.clip(k, 0.0, 0.9))
    saida = rgb.copy()
    if k <= 0:
        return saida
    h, w = rgb.shape[:2]
    for rosto in analise.rostos:
        caixa = rosto.caixa(0.12, (h, w))
        x0, y0, x1, y1 = caixa
        fw = rosto.largura
        pele, _ = analise.mascara_pele(rosto, caixa)
        # tirar barba/pelos da suavização (ela deixaria a barba com aspecto borrado)
        mp_ = _mapas(rgb, analise, rosto)
        pelos = cv2.resize(np.clip(mp_.densidade_pelos * 3, 0, 1), (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR)
        m = pele * (1.0 - pelos)
        m = cv2.GaussianBlur(m, (0, 0), max(1.0, 0.012 * fw))
        recorte = saida[y0:y1, x0:x1]
        fino = max(0.8, 0.0035 * fw)
        grosso = max(fino * 3, 0.025 * fw)
        medio = cv2.GaussianBlur(recorte, (0, 0), fino) - cv2.GaussianBlur(recorte, (0, 0), grosso)
        saida[y0:y1, x0:x1] = recorte - k * medio * m[..., None]
    return np.clip(saida, 0, 1)
