"""Detecção de espinhas e manchas na pele.

Ideia: dentro da pele "segura" (sem olhos, sobrancelhas, boca e narinas), comparamos cada
ponto com a pele em volta dele. Espinha inflamada fica mais vermelha (canal a* do Lab) e um
pouco mais escura que a vizinhança. Pinta, sarda e marca antiga ficam mais escuras, mas não
mais vermelhas; essas são listadas como "mancha" e, por padrão, NÃO são removidas.

Tudo é medido em desvios robustos da própria pele da pessoa, então funciona igual em pele
clara, morena ou negra, e com luz quente ou fria.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

from .analise import Analise, Rosto

LARGURA_NORMAL = 600.0  # o rosto é redimensionado para ter esta largura durante a análise

# limiar em unidades Lab (a* para vermelhidão) e fator mínimo sobre o ruído da própria pele
SENSIBILIDADES = {"baixa": (4.0, 14.0), "media": (3.0, 11.0), "alta": (2.2, 8.0)}
LIMIAR_MANCHA = {"baixa": 7.0, "media": 5.5, "alta": 4.2}  # em unidades de L*
ESCALAS = (1.3, 1.9, 2.7, 3.8, 5.3, 7.4)


@dataclass
class Marca:
    id: int
    x: float  # centro, em pixels da foto original
    y: float
    raio: float  # em pixels da foto original
    tipo: str  # "espinha" ou "mancha"
    forca: float
    remover: bool
    rosto: int = 0
    origem: str = "auto"  # "auto", "busca" ou "manual"

    def dict(self) -> dict:
        d = asdict(self)
        d["x"], d["y"], d["raio"], d["forca"] = round(self.x, 1), round(self.y, 1), round(self.raio, 1), round(self.forca, 2)
        return d


def _desfoque(img: np.ndarray, sigma: float) -> np.ndarray:
    return cv2.GaussianBlur(img, (0, 0), sigma, borderType=cv2.BORDER_REFLECT)


def _desfoque_mascarado(valor: np.ndarray, mascara: np.ndarray, sigma: float) -> np.ndarray:
    num = _desfoque(valor * mascara, sigma)
    den = _desfoque(mascara, sigma)
    return num / np.maximum(den, 1e-4)


def _escala_robusta(v: np.ndarray, minimo: float) -> float:
    if v.size < 50:
        return minimo
    med = np.median(v)
    return float(1.4826 * np.median(np.abs(v - med)) + minimo)


@dataclass
class _Mapas:
    escala: float  # pixels normalizados por pixel da foto
    origem: tuple[int, int]  # canto superior esquerdo da caixa na foto
    pele: np.ndarray
    vermelho: np.ndarray  # diferença de a* para a vizinhança (Lab), positivo = mais vermelho
    escuro: np.ndarray  # diferença de L* para a vizinhança, positivo = mais escuro
    escala_vermelho: float  # variação típica de a* nesta pele
    densidade_pelos: np.ndarray  # 0..1, alto em barba / pelos


def _mapas(rgb: np.ndarray, analise: Analise, rosto: Rosto) -> _Mapas:
    caixa = rosto.caixa(0.12, (analise.altura, analise.largura))
    x0, y0, x1, y1 = caixa
    pele, _ = analise.mascara_pele(rosto, caixa)
    s = LARGURA_NORMAL / rosto.largura
    recorte = rgb[y0:y1, x0:x1]
    tam = (max(8, round((x1 - x0) * s)), max(8, round((y1 - y0) * s)))
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC
    pequeno = np.clip(cv2.resize(recorte, tam, interpolation=interp), 0, 1)
    m = (cv2.resize(pele, tam, interpolation=cv2.INTER_LINEAR) > 0.5).astype(np.float32)

    lab = cv2.cvtColor(pequeno.astype(np.float32), cv2.COLOR_RGB2Lab)
    L, A = lab[..., 0], lab[..., 1]
    fundo_L = _desfoque_mascarado(L, m, 14.0)
    fundo_A = _desfoque_mascarado(A, m, 14.0)
    dA = (A - fundo_A) * m
    dL = (fundo_L - L) * m
    dentro = m > 0.5
    sA = _escala_robusta(dA[dentro], 0.25)
    sL = _escala_robusta(dL[dentro], 0.4)

    # Barba e pelos: muitos pontinhos escuros finos e próximos.
    fino = np.maximum(_desfoque(dL / sL, 0.8) - _desfoque(dL / sL, 2.5), 0)
    pelos = (fino > 1.2).astype(np.float32) * m
    densidade = _desfoque_mascarado(pelos, m, 6.0)
    return _Mapas(s, (x0, y0), m, dA, dL, sA, densidade)


def _resposta(mapa: np.ndarray, pele: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    respostas, suaves = [], []
    for s in ESCALAS:
        g = _desfoque(mapa, s)
        r = (g - _desfoque(mapa, s * 2.6)) * pele
        respostas.append(r * (1.0 / (1.0 + 0.55 / s)))  # escalas pequenas são mais ruidosas
        suaves.append(g)
    pilha = np.stack(respostas, 0)
    return pilha.max(0), pilha.argmax(0), suaves


def _redondo(g: np.ndarray, x: int, y: int, sigma: float, minimo: float = 0.3) -> bool:
    """Rejeita linhas (bigode chinês, rugas, contorno de dobra): exige pico redondo.

    Usa a matriz Hessiana: num pico redondo as duas curvaturas são parecidas; numa linha,
    uma delas é quase zero.
    """
    h, w = g.shape
    d = max(1, int(round(sigma)))
    if not (d <= x < w - d and d <= y < h - d):
        return False
    c = g[y, x]
    dxx = g[y, x + d] + g[y, x - d] - 2 * c
    dyy = g[y + d, x] + g[y - d, x] - 2 * c
    dxy = (g[y + d, x + d] - g[y + d, x - d] - g[y - d, x + d] + g[y - d, x - d]) / 4.0
    tr, det = dxx + dyy, dxx * dyy - dxy * dxy
    disc = np.sqrt(max(tr * tr / 4 - det, 0.0))
    l1, l2 = tr / 2 + disc, tr / 2 - disc  # l1 >= l2
    if l2 >= 0 or l1 >= 0:
        return False
    return (l1 / l2) >= minimo


def _ruido(resposta: np.ndarray, pele: np.ndarray) -> float:
    v = resposta[pele > 0.5]
    if v.size < 50:
        return 0.0
    return float(1.4826 * np.median(np.abs(v - np.median(v))))


def _blobs(mapa: np.ndarray, pele: np.ndarray, limiar_abs: float, fator_ruido: float, restrito: np.ndarray | None = None):
    """Centros (x, y, sigma, resposta) de manchas redondas no mapa, em várias escalas.

    O limiar nunca fica abaixo de `fator_ruido` vezes o ruído típico desta pele, para não
    confundir textura (poros, barba rala) com espinha. `restrito` limita onde procurar.
    """
    maximo_escala, melhor, suaves = _resposta(mapa, pele)
    limiar = max(limiar_abs, fator_ruido * _ruido(maximo_escala, pele))
    nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    pico = (maximo_escala >= cv2.dilate(maximo_escala, nucleo)) & (maximo_escala > limiar)
    if restrito is not None:
        pico &= restrito > 0.5
    ys, xs = np.nonzero(pico)
    largos: dict[int, np.ndarray] = {}
    achados = []
    for y, x in zip(ys, xs, strict=True):
        k = int(melhor[y, x])
        sigma = ESCALAS[k]
        if not _redondo(suaves[k], int(x), int(y), sigma):
            continue
        # Na escala dobrada, uma espinha continua redonda; uma dobra de pele vira linha.
        if k not in largos:
            largos[k] = _desfoque(mapa, sigma * 2.0)
        if not _redondo(largos[k], int(x), int(y), sigma * 2.0, minimo=0.2):
            continue
        achados.append((float(x), float(y), sigma, float(maximo_escala[y, x])))
    achados.sort(key=lambda a: -a[3])
    return achados


def _suprimir(achados, ja_aceitos):
    aceitos = list(ja_aceitos)
    novos = []
    for x, y, s, resp in achados:
        r = 1.7 * s
        if any((x - ax) ** 2 + (y - ay) ** 2 < ((r + ar) * 0.85) ** 2 for ax, ay, ar, _ in aceitos):
            continue
        aceitos.append((x, y, r, resp))
        novos.append((x, y, r, resp))
    return novos


def _fracao_na_pele(pele: np.ndarray, x: float, y: float, r: float) -> float:
    h, w = pele.shape
    rr = max(2, int(np.ceil(r * 1.4)))
    xi, yi = int(round(x)), int(round(y))
    ya, yb, xa, xb = max(0, yi - rr), min(h, yi + rr + 1), max(0, xi - rr), min(w, xi + rr + 1)
    if ya >= yb or xa >= xb:
        return 0.0
    gy, gx = np.mgrid[ya:yb, xa:xb]
    disco = (gx - x) ** 2 + (gy - y) ** 2 <= rr**2
    return float(pele[ya:yb, xa:xb][disco].mean()) if disco.any() else 0.0


def _media_no_disco(mapa: np.ndarray, x: float, y: float, r: float) -> float:
    h, w = mapa.shape
    rr = max(1, int(np.ceil(r)))
    xi, yi = int(round(x)), int(round(y))
    ya, yb, xa, xb = max(0, yi - rr), min(h, yi + rr + 1), max(0, xi - rr), min(w, xi + rr + 1)
    gy, gx = np.mgrid[ya:yb, xa:xb]
    disco = (gx - x) ** 2 + (gy - y) ** 2 <= rr**2
    return float(mapa[ya:yb, xa:xb][disco].mean()) if disco.any() else 0.0


def detectar_no_rosto(
    rgb: np.ndarray,
    analise: Analise,
    indice_rosto: int,
    sensibilidade: str = "media",
    regiao: tuple[float, float, float, float] | None = None,
    existentes: list[Marca] | None = None,
) -> list[Marca]:
    """Procura espinhas e manchas em um rosto.

    regiao: (x0, y0, x1, y1) em pixels da foto, para procurar só ali (busca dirigida).
    existentes: marcas já conhecidas, para não repetir.
    """
    limiar_abs, fator = SENSIBILIDADES.get(sensibilidade, SENSIBILIDADES["media"])
    limiar_mancha = LIMIAR_MANCHA.get(sensibilidade, LIMIAR_MANCHA["media"])
    rosto = analise.rostos[indice_rosto]
    mp_ = _mapas(rgb, analise, rosto)
    pele = mp_.pele
    restrito = None
    if regiao is not None:
        rx0, ry0, rx1, ry1 = regiao
        ox, oy = mp_.origem
        s = mp_.escala
        restrito = np.zeros_like(pele)
        a0, b0 = max(0, int((rx0 - ox) * s)), max(0, int((ry0 - oy) * s))
        a1, b1 = int(np.ceil((rx1 - ox) * s)), int(np.ceil((ry1 - oy) * s))
        restrito[b0:b1, a0:a1] = 1
        restrito *= pele
        if restrito.sum() < 10:
            return []

    ox, oy = mp_.origem
    s = mp_.escala
    ja = []
    for m in existentes or []:
        if m.rosto == indice_rosto:
            ja.append(((m.x - ox) * s, (m.y - oy) * s, m.raio * s, 0.0))

    # 1) espinhas: vermelhidão (com um pouco de escurecimento) — barba atenua
    pelos = np.clip(mp_.densidade_pelos * 3.0, 0, 1)
    verm_ok = mp_.vermelho > 0.5 * mp_.escala_vermelho
    mapa_espinha = np.maximum(mp_.vermelho, 0) + 0.5 * np.maximum(mp_.escuro, 0) * verm_ok
    mapa_espinha *= 1.0 - 0.5 * pelos
    cand_esp = _suprimir(_blobs(mapa_espinha, pele, limiar_abs, fator, restrito), ja)

    # 2) manchas escuras não vermelhas (pinta, sarda, marca): fora da barba
    mapa_mancha = np.maximum(mp_.escuro, 0) * (1.0 - pelos)
    cand_man = _suprimir(_blobs(mapa_mancha, pele, limiar_mancha, fator, restrito), ja + cand_esp)

    marcas: list[Marca] = []
    for tipo, cands in (("espinha", cand_esp), ("mancha", cand_man)):
        for x, y, r, resp in cands:
            if _fracao_na_pele(mp_.pele, x, y, r) < 0.75:
                continue
            verm = _media_no_disco(mp_.vermelho, x, y, max(1.0, r * 0.7))
            if tipo == "espinha" and verm < 1.2:
                continue
            marcas.append(
                Marca(
                    id=0,
                    x=ox + (x + 0.5) / s - 0.5,
                    y=oy + (y + 0.5) / s - 0.5,
                    raio=max(1.5, r / s),
                    tipo=tipo,
                    forca=resp,
                    remover=(tipo == "espinha"),
                    rosto=indice_rosto,
                    origem="busca" if regiao is not None else "auto",
                )
            )
    return marcas


def detectar(rgb: np.ndarray, analise: Analise, sensibilidade: str = "media") -> list[Marca]:
    marcas: list[Marca] = []
    for i in range(len(analise.rostos)):
        marcas.extend(detectar_no_rosto(rgb, analise, i, sensibilidade))
    marcas.sort(key=lambda m: (m.rosto, m.tipo != "espinha", m.y, m.x))
    for n, m in enumerate(marcas, 1):
        m.id = n
    return marcas
