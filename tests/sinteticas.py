"""Gera espinhas e sujeira de fundo artificiais, com posição conhecida, para medir o programa."""

from __future__ import annotations

import cv2
import numpy as np


def adicionar_espinhas(rgb, analise, n=12, semente=0):
    rng = np.random.default_rng(semente)
    saida = rgb.copy()
    rosto = analise.rostos[0]
    caixa = rosto.caixa(0.12, (analise.altura, analise.largura))
    x0, y0, _, _ = caixa
    pele, _ = analise.mascara_pele(rosto, caixa)
    fw = rosto.largura
    tam = int(fw * 0.04) + 1
    seguro = cv2.erode((pele > 0.5).astype(np.uint8), np.ones((tam, tam), np.uint8))
    ys, xs = np.nonzero(seguro)
    verdade = []
    tentativas = 0
    while len(verdade) < n and tentativas < 5000:
        tentativas += 1
        k = rng.integers(len(xs))
        x, y = xs[k] + x0, ys[k] + y0
        r = rng.uniform(3, 9) * fw / 600
        if any((x - a) ** 2 + (y - b) ** 2 < (3 * (r + c)) ** 2 for a, b, c in verdade):
            continue
        verdade.append((float(x), float(y), float(r)))
    for x, y, r in verdade:
        R = int(r * 3) + 2
        xa, ya, xb, yb = int(x) - R, int(y) - R, int(x) + R + 1, int(y) + R + 1
        lab = cv2.cvtColor(saida[ya:yb, xa:xb].astype(np.float32), cv2.COLOR_RGB2Lab)
        gy, gx = np.mgrid[ya:yb, xa:xb]
        perfil = np.exp(-((gx - x) ** 2 + (gy - y) ** 2) / (r * r) * 1.2)
        lab[..., 1] += rng.uniform(7, 16) * perfil
        lab[..., 0] -= rng.uniform(2, 6) * perfil
        saida[ya:yb, xa:xb] = np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB), 0, 1)
    return saida, verdade


def sujar_fundo(rgb, analise, semente=0):
    rng = np.random.default_rng(semente)
    h, w = rgb.shape[:2]
    fundo = cv2.resize(analise.probs[..., 0], (w, h)) > 0.8
    sujeira = np.zeros((h, w), np.float32)
    ys, xs = np.nonzero(fundo[::7, ::7])
    pontos = []
    for k in rng.choice(len(xs), min(40, len(xs)), replace=False):
        x, y = int(xs[k] * 7), int(ys[k] * 7)
        cv2.circle(sujeira, (x, y), max(1, int(rng.uniform(1, 0.004 * w))), float(rng.uniform(0.08, 0.2)), -1)
        pontos.append((x, y))
    sujeira = cv2.GaussianBlur(sujeira, (0, 0), 1.0)
    return np.clip(rgb * (1 - sujeira[..., None]), 0, 1), sujeira
