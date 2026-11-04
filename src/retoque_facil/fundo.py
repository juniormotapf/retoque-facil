"""Limpeza de fundo de estúdio (papel, tecido ou parede lisa).

Separamos a pessoa do fundo, estimamos como o fundo seria sem sujeira, dobras, poeira
e manchas (mantendo o degradê de luz e a vinheta do estúdio) e devolvemos uma granulação
fina igual à original, para não ficar com aspecto artificial nem criar faixas.

Perto da pessoa a limpeza vai diminuindo, para não comer fios de cabelo soltos.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .analise import CABELO, FUNDO, Analise

LADO_TRABALHO = 1600
INTENSIDADES = {
    # (escala do desfoque relativa à foto, quanto aplicar, quanto aceita apagar de borda)
    "leve": (0.012, 0.75, 0.001),
    "media": (0.02, 1.0, 0.002),
    "forte": (0.035, 1.0, 0.012),
}


@dataclass
class DiagnosticoFundo:
    estudio: bool
    textura: float
    fracao_fundo: float
    motivo: str


def _filtro_guiado(guia: np.ndarray, src: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Filtro guiado (He et al.): ajusta a máscara às bordas reais da foto."""
    caixa = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), borderType=cv2.BORDER_REFLECT)  # noqa: E731
    mg, ms = caixa(guia), caixa(src)
    cov = caixa(guia * src) - mg * ms
    var = caixa(guia * guia) - mg * mg
    a = cov / (var + eps)
    b = ms - a * mg
    return caixa(a) * guia + caixa(b)


def _reduzir(rgb: np.ndarray, lado: int) -> tuple[np.ndarray, float]:
    h, w = rgb.shape[:2]
    e = min(1.0, lado / max(h, w))
    if e < 1:
        return cv2.resize(rgb, (round(w * e), round(h * e)), interpolation=cv2.INTER_AREA), e
    return rgb.copy(), 1.0


def alfa_pessoa(rgb: np.ndarray, analise: Analise) -> tuple[np.ndarray, float]:
    """Máscara suave da pessoa (1) contra o fundo (0), na escala de trabalho."""
    peq, e = _reduzir(rgb, LADO_TRABALHO)
    hh, ww = peq.shape[:2]
    fundo = cv2.resize(analise.probs[..., FUNDO], (ww, hh), interpolation=cv2.INTER_LINEAR)
    # O modelo raramente passa de ~0,95 de certeza; reescalamos para 0..1.
    alfa = np.clip((0.85 - fundo) / 0.55, 0, 1).astype(np.float32)
    cinza = cv2.cvtColor(peq.astype(np.float32), cv2.COLOR_RGB2GRAY)
    r = max(2, round(max(hh, ww) / 300))
    alfa = np.clip(_filtro_guiado(cinza, alfa, r, 1e-3), 0, 1)
    return alfa, e


def diagnosticar(rgb: np.ndarray, analise: Analise) -> DiagnosticoFundo:
    peq, _ = _reduzir(rgb, 800)
    hh, ww = peq.shape[:2]
    fundo = cv2.resize(analise.probs[..., FUNDO], (ww, hh), interpolation=cv2.INTER_LINEAR) > 0.8
    fundo = cv2.erode(fundo.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    fracao = float(fundo.mean())
    if fracao < 0.05:
        return DiagnosticoFundo(False, 0.0, fracao, "quase não há fundo visível nesta foto")
    lab = cv2.cvtColor(peq.astype(np.float32), cv2.COLOR_RGB2Lab)
    detalhe = lab - cv2.GaussianBlur(lab, (0, 0), 6)
    textura = float(np.median(np.abs(detalhe[fundo]).sum(-1)))
    croma = lab[..., 1:][fundo]
    variacao_cor = float(np.percentile(np.linalg.norm(croma - np.median(croma, 0), axis=-1), 90))
    # Variação de brilho em escala média (bokeh, objetos, janelas). Vinheta não conta.
    peso = fundo.astype(np.float32)
    lado = max(hh, ww)

    def media(x: np.ndarray, sigma: float) -> np.ndarray:
        return cv2.GaussianBlur(x * peso, (0, 0), sigma) / np.maximum(cv2.GaussianBlur(peso, (0, 0), sigma), 1e-3)

    estrutura = float(np.percentile(np.abs(media(lab[..., 0], 0.015 * lado) - media(lab[..., 0], 0.08 * lado))[fundo], 90))
    estudio = textura < 1.15 and variacao_cor < 18 and estrutura < 6
    if estudio:
        motivo = "fundo liso de estúdio"
    elif estrutura >= 6:
        motivo = "o fundo tem objetos, luzes ou desfoque de paisagem (não parece fundo de estúdio)"
    elif textura >= 1.15:
        motivo = "o fundo tem textura, como parede ou tecido rústico (não parece fundo liso de estúdio)"
    else:
        motivo = "o fundo tem cores muito variadas (não parece fundo de estúdio)"
    return DiagnosticoFundo(estudio, textura, fracao, motivo)


LADO_FUNDO_LIMPO = 480  # o fundo limpo é calculado pequeno: ele é suave de qualquer jeito
FAIXAS_HORIZONTE = 6  # faixas verticais: acompanha linha do chão torta ou em perspectiva


def _correcao_horizonte(fundo_est: np.ndarray, peso: np.ndarray) -> np.ndarray:
    """Correção suave que apaga a linha onde a parede encontra o piso (fundo infinito).

    Para cada faixa vertical da foto, mede o brilho/cor médio do fundo linha a linha
    (perfil vertical). O degrau da parede para o chão aparece nesse perfil; trocamos o
    perfil por uma versão bem suavizada. Como a correção só depende da altura (e varia
    devagar de uma faixa para outra), sombras, luz lateral e a pessoa não são afetadas.
    """
    ph, pw = peso.shape
    sigma = max(3.0, 0.08 * ph)
    centros, correcoes = [], []
    limites = np.linspace(0, pw, FAIXAS_HORIZONTE + 1).astype(int)
    linhas = np.arange(ph, dtype=np.float32)
    for a, b in zip(limites[:-1], limites[1:], strict=True):
        w = peso[:, a:b]
        soma = w.sum(1)
        perfil = (fundo_est[:, a:b] * w[..., None]).sum(1) / np.maximum(soma, 1e-6)[:, None]
        ok = soma > 0.15 * (b - a)
        if ok.sum() < 3:
            continue
        for c in range(3):  # linhas tapadas pela pessoa: interpola pelo resto da faixa
            perfil[:, c] = np.interp(linhas, linhas[ok], perfil[ok, c])
        suave = cv2.GaussianBlur(perfil[:, None, :].astype(np.float32), (0, 0), sigmaX=0.1, sigmaY=sigma,
                                 borderType=cv2.BORDER_REPLICATE)[:, 0, :]
        centros.append((a + b) / 2)
        correcoes.append(suave - perfil)
    if not correcoes:
        return np.zeros_like(fundo_est)
    pilha = np.stack(correcoes, 1)  # ph x faixas x 3
    colunas = np.arange(pw, dtype=np.float32)
    saida = np.empty((ph, pw, 3), np.float32)
    for c in range(3):
        for y in range(ph):
            saida[y, :, c] = np.interp(colunas, centros, pilha[y, :, c])
    return cv2.GaussianBlur(saida, (0, 0), max(1.0, 0.04 * pw))
FAIXAS_HORIZONTE = 8  # o fundo é dividido em faixas verticais (aceita câmera um pouco torta)
TRANSICAO_HORIZONTE = 0.07  # largura do degradê que substitui a linha, relativa à altura


def correcao_horizonte(fundo: np.ndarray, peso: np.ndarray) -> np.ndarray:
    """Some com a linha onde a parede encontra o piso (efeito "fundo infinito").

    Em cada faixa vertical medimos o perfil de cor de cima para baixo, só no fundo. O
    encontro parede/piso aparece ali como um degrau. Trocamos o perfil por uma versão
    suavizada (o degrau vira degradê) e devolvemos só a diferença: uma correção suave,
    que depende quase só da altura. Sombras, luz lateral e reflexos não são tocados.
    """
    ph, pw = peso.shape
    sigma = max(2.0, TRANSICAO_HORIZONTE * ph)
    centros, correcoes = [], []
    perfil_geral = None
    soma_geral = peso.sum(1)
    if soma_geral.max() > 0:
        perfil_geral = (fundo * peso[..., None]).sum(1) / np.maximum(soma_geral, 1e-6)[:, None]
    for k in range(FAIXAS_HORIZONTE):
        a, b = round(k * pw / FAIXAS_HORIZONTE), round((k + 1) * pw / FAIXAS_HORIZONTE)
        w = peso[:, a:b]
        soma = w.sum(1)
        perfil = (fundo[:, a:b] * w[..., None]).sum(1) / np.maximum(soma, 1e-6)[:, None]
        valido = soma > 0.5 * (b - a) * 0.05  # linhas com fundo suficiente nesta faixa
        if valido.sum() < 3:
            if perfil_geral is None:
                continue
            perfil, valido = perfil_geral.copy(), soma_geral > 0
        ys = np.arange(ph)
        for c in range(3):  # preenche as linhas onde a pessoa tapa o fundo
            perfil[:, c] = np.interp(ys, ys[valido], perfil[valido, c])
        suave = cv2.GaussianBlur(perfil.reshape(ph, 1, 3).astype(np.float32), (1, 0), sigmaX=0.1,
                                 sigmaY=sigma, borderType=cv2.BORDER_REPLICATE).reshape(ph, 3)
        centros.append((a + b) / 2)
        correcoes.append(suave - perfil)
    if not correcoes:
        return np.zeros_like(fundo)
    if len(correcoes) == 1:
        return np.broadcast_to(correcoes[0][:, None, :], fundo.shape).copy()
    xs = np.arange(pw)
    pilha = np.stack(correcoes, 1)  # ph x K x 3
    saida = np.empty_like(fundo)
    for c in range(3):
        for y in range(ph):
            saida[y, :, c] = np.interp(xs, centros, pilha[y, :, c])
    # suaviza de leve na horizontal para não marcar a divisa entre faixas
    return cv2.GaussianBlur(saida, (0, 0), sigmaX=pw / FAIXAS_HORIZONTE / 2, sigmaY=0.1)


def limpar(
    rgb: np.ndarray,
    analise: Analise,
    intensidade: str = "media",
    semente: int = 7,
    remover_horizonte: bool = True,
) -> np.ndarray:
    escala_rel, quanto, eps = INTENSIDADES.get(intensidade, INTENSIDADES["media"])
    h, w = rgb.shape[:2]
    alfa, e = alfa_pessoa(rgb, analise)
    hh, ww = alfa.shape

    # 1) Fundo "limpo" numa versão pequena: média ponderada que ignora a pessoa
    #    (assim cor de roupa e cabelo não vaza para o fundo).
    peq, e2 = _reduzir(rgb, LADO_FUNDO_LIMPO)
    ph, pw = peq.shape[:2]
    peso = cv2.resize(np.clip(1.0 - alfa, 0, 1), (pw, ph), interpolation=cv2.INTER_AREA) ** 3
    sigma = max(1.5, escala_rel * max(ph, pw))
    num = cv2.GaussianBlur(peq * peso[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(peso, (0, 0), sigma)[..., None]
    limpo = num / np.maximum(den, 1e-4)
    falta = np.clip(1.0 - den[..., 0] * 4, 0, 1)  # longe de qualquer fundo: desfoque maior
    if falta.max() > 0:
        num2 = cv2.GaussianBlur(peq * peso[..., None], (0, 0), sigma * 4)
        den2 = cv2.GaussianBlur(peso, (0, 0), sigma * 4)[..., None]
        limpo = limpo * (1 - falta[..., None]) + (num2 / np.maximum(den2, 1e-4)) * falta[..., None]
    # Suavização que respeita bordas grandes do cenário (encontro parede/chão, sombra da
    # pessoa) e apaga o que é pequeno ou fino (poeira, risco, vinco). A pessoa é trocada
    # pelo fundo estimado antes, para não "vazar" para o fundo.
    sem_pessoa = peq * peso[..., None] + limpo * (1 - peso[..., None])
    guia = cv2.cvtColor(sem_pessoa.astype(np.float32), cv2.COLOR_RGB2GRAY)
    raio = max(2, round(escala_rel * max(ph, pw)))
    limpo = np.stack([_filtro_guiado(guia, sem_pessoa[..., c].astype(np.float32), raio, eps) for c in range(3)], -1)
    # Linha do encontro parede/piso: some sempre (vira degradê de fundo infinito).
    horizonte = correcao_horizonte(limpo, peso) if remover_horizonte else np.zeros_like(limpo)
    limpo = cv2.resize(limpo + horizonte, (w, h), interpolation=cv2.INTER_CUBIC)
    horizonte = cv2.resize(horizonte, (w, h), interpolation=cv2.INTER_CUBIC)

    # 2) Quanto aplicar em cada ponto: só no fundo, e diminuindo perto da pessoa
    #    (protege fios de cabelo soltos que o modelo não pegou).
    pessoa = (alfa > 0.5).astype(np.uint8)
    dist = cv2.distanceTransform(1 - pessoa, cv2.DIST_L2, 5)
    faixa = 0.012 * max(hh, ww)
    longe = np.clip((dist - faixa * 0.3) / faixa, 0, 1)
    # Em volta do cabelo a proteção é bem mais larga: fios soltos se espalham pelo fundo.
    cabelo = cv2.resize(analise.probs[..., CABELO], (ww, hh), interpolation=cv2.INTER_LINEAR) > 0.4
    dist_cabelo = cv2.distanceTransform(1 - cabelo.astype(np.uint8), cv2.DIST_L2, 5)
    faixa_cabelo = 0.05 * max(hh, ww)
    longe_cabelo = np.clip((dist_cabelo - faixa_cabelo * 0.15) / faixa_cabelo, 0, 1) ** 1.5
    aplicar = (1.0 - alfa) * longe * longe_cabelo * quanto
    if e < 1:
        aplicar = cv2.resize(aplicar, (w, h), interpolation=cv2.INTER_LINEAR)

    # 3) Granulação medida no próprio fundo e reaplicada (evita aspecto de plástico e faixas).
    passo = max(1, int(np.sqrt(h * w / 2e6)))
    amostra = rgb[::passo, ::passo].astype(np.float32)
    cinza = cv2.cvtColor(amostra, cv2.COLOR_RGB2GRAY)
    fino = cinza - cv2.GaussianBlur(cinza, (0, 0), 1.2)
    sel = aplicar[::passo, ::passo] > 0.8
    if sel.sum() > 1000:
        v = fino[sel]
        grao = float(1.4826 * np.median(np.abs(v - np.median(v))))
    else:
        grao = 0.003
    grao = float(np.clip(grao, 0.0015, 0.02))
    rng = np.random.default_rng(semente)
    ruido = rng.standard_normal((h, w), dtype=np.float32) * grao
    ruido = cv2.GaussianBlur(ruido, (0, 0), 0.5) * 1.6

    # A correção do horizonte é suave, então vale no fundo todo, inclusive colada nas pernas
    # e no cabelo (não apaga fios, só acerta o tom). Depois vem a limpeza de sujeira.
    fundo_todo = 1.0 - (cv2.resize(alfa, (w, h), interpolation=cv2.INTER_LINEAR) if e < 1 else alfa)
    base = rgb + horizonte * fundo_todo[..., None]
    saida = base + (limpo + ruido[..., None] - base) * aplicar[..., None]
    return np.clip(saida, 0, 1).astype(np.float32)
