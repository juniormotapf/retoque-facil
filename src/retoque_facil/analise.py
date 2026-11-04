"""Encontra rostos, pele e fundo usando dois modelos pequenos do MediaPipe (Google, Apache-2.0).

- face_landmarker.task: 478 pontos do rosto, para saber onde ficam olhos, sobrancelhas,
  boca e narinas (áreas que nunca devem ser retocadas como "espinha").
- selfie_multiclass_256x256.tflite: separa fundo, cabelo, pele do corpo, pele do rosto,
  roupa e acessórios.

Os dois rodam na CPU em fração de segundo; não precisa de placa de vídeo.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

PASTA_MODELOS = Path(__file__).resolve().parent / "modelos"

MODELOS = {
    "face_landmarker.task": {
        "url": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        "sha256": "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
    },
    "selfie_multiclass_256x256.tflite": {
        "url": "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite",
        "sha256": "c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0",
    },
}

# Classes do selfie_multiclass
FUNDO, CABELO, PELE_CORPO, PELE_ROSTO, ROUPA, OUTROS = range(6)

# Índices da malha de 478 pontos do MediaPipe Face Mesh
OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
        152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]
OLHO_ESQ = [263, 249, 390, 373, 374, 380, 381, 382, 362, 466, 388, 387, 386, 385, 384, 398]
OLHO_DIR = [33, 7, 163, 144, 145, 153, 154, 155, 133, 246, 161, 160, 159, 158, 157, 173]
SOBRANCELHA_ESQ = [276, 283, 282, 295, 285, 300, 293, 334, 296, 336]
SOBRANCELHA_DIR = [46, 53, 52, 65, 55, 70, 63, 105, 66, 107]
LABIOS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
NARIZ_BASE = [48, 64, 98, 97, 2, 326, 327, 294, 278, 219, 218, 237, 44, 1, 274, 457, 438, 439]
LADO_ESQ, LADO_DIR = 454, 234  # extremos do rosto (largura)
DOBRA_DIR = [129, 203, 206, 216, 212, 202, 210]  # do nariz até o queixo, lado direito da pessoa
DOBRA_ESQ = [358, 423, 426, 436, 432, 422, 430]

LADO_MAX_SEGMENTACAO = 1024
LADO_MAX_PONTOS = 2048


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def caminho_modelo(nome: str) -> Path:
    """Devolve o modelo que vem junto com o programa; se faltar, baixa e confere a assinatura."""
    info = MODELOS[nome]
    local = PASTA_MODELOS / nome
    if local.exists() and local.stat().st_size > 1000:
        return local
    cache = Path(os.environ.get("RETOQUE_CACHE", Path.home() / ".retoque-facil" / "modelos"))
    cache.mkdir(parents=True, exist_ok=True)
    destino = cache / nome
    if destino.exists() and _sha256(destino) == info["sha256"]:
        return destino
    temporario = destino.with_suffix(".baixando")
    urllib.request.urlretrieve(info["url"], temporario)
    if _sha256(temporario) != info["sha256"]:
        temporario.unlink(missing_ok=True)
        raise RuntimeError(f"o modelo {nome} veio corrompido; tente de novo com a internet estável")
    temporario.replace(destino)
    return destino


class _Modelos:
    """Carrega os modelos uma vez só e protege o uso entre threads."""

    def __init__(self) -> None:
        self._trava = threading.Lock()
        self._pontos = None
        self._segmentador = None

    def _carregar(self) -> None:
        if self._pontos is not None:
            return
        from mediapipe.tasks.python import BaseOptions, vision

        self._pontos = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(caminho_modelo("face_landmarker.task"))),
                num_faces=6,
                min_face_detection_confidence=0.4,
                min_face_presence_confidence=0.4,
            )
        )
        self._segmentador = vision.ImageSegmenter.create_from_options(
            vision.ImageSegmenterOptions(
                base_options=BaseOptions(
                    model_asset_path=str(caminho_modelo("selfie_multiclass_256x256.tflite"))
                ),
                output_confidence_masks=True,
                output_category_mask=False,
            )
        )

    def pontos(self, rgb_u8: np.ndarray):
        import mediapipe as mp

        with self._trava:
            self._carregar()
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb_u8))
            return self._pontos.detect(img)

    def segmentar(self, rgb_u8: np.ndarray) -> np.ndarray:
        import mediapipe as mp

        with self._trava:
            self._carregar()
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb_u8))
            res = self._segmentador.segment(img)
            return np.stack([m.numpy_view().astype(np.float32).squeeze() for m in res.confidence_masks], -1)

    def fechar(self) -> None:
        with self._trava:
            for m in (self._pontos, self._segmentador):
                if m is not None:
                    try:
                        m.close()
                    except Exception:
                        pass
            self._pontos = self._segmentador = None


modelos = _Modelos()
atexit.register(modelos.fechar)


def _reduzir(rgb: np.ndarray, lado_max: int) -> tuple[np.ndarray, float]:
    h, w = rgb.shape[:2]
    escala = min(1.0, lado_max / max(h, w))
    u8 = np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)
    if escala < 1.0:
        u8 = cv2.resize(u8, (round(w * escala), round(h * escala)), interpolation=cv2.INTER_AREA)
    return u8, escala


@dataclass
class Rosto:
    pontos: np.ndarray  # 478 x 2, em pixels da foto inteira
    largura: float  # largura do rosto em pixels
    # segmentação feita só em volta deste rosto, em resolução maior (mais precisa)
    probs_locais: np.ndarray | None = field(default=None, repr=False)
    origem_local: tuple[int, int] = (0, 0)
    escala_local: float = 1.0

    def poligono(self, indices: list[int]) -> np.ndarray:
        return self.pontos[indices]

    @property
    def centro(self) -> tuple[float, float]:
        oval = self.poligono(OVAL)
        return float(oval[:, 0].mean()), float(oval[:, 1].mean())

    def caixa(self, margem: float = 0.25, limites: tuple[int, int] | None = None) -> tuple[int, int, int, int]:
        oval = self.poligono(OVAL)
        x0, y0 = oval.min(0)
        x1, y1 = oval.max(0)
        mx, my = (x1 - x0) * margem, (y1 - y0) * margem
        x0, y0, x1, y1 = int(x0 - mx), int(y0 - my), int(x1 + mx), int(y1 + my)
        if limites is not None:
            h, w = limites
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        return x0, y0, x1, y1


def _amostrar(mapa: np.ndarray, s: float, origem: tuple[float, float], caixa: tuple[int, int, int, int]) -> np.ndarray:
    """Recorta e redimensiona um mapa de baixa resolução para a caixa (em pixels da foto)."""
    ox, oy = origem
    x0, y0, x1, y1 = caixa
    hx0, hy0 = max(0, int((x0 - ox) * s) - 2), max(0, int((y0 - oy) * s) - 2)
    hx1 = min(mapa.shape[1], int(np.ceil((x1 - ox) * s)) + 2)
    hy1 = min(mapa.shape[0], int(np.ceil((y1 - oy) * s)) + 2)
    pedaco = np.ascontiguousarray(mapa[hy0:hy1, hx0:hx1])
    mx = (np.arange(x1 - x0, dtype=np.float32) + x0 - ox + 0.5) * s - 0.5 - hx0
    my = (np.arange(y1 - y0, dtype=np.float32) + y0 - oy + 0.5) * s - 0.5 - hy0
    grade_x, grade_y = np.meshgrid(mx, my)
    return cv2.remap(pedaco, grade_x, grade_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


@dataclass
class Analise:
    largura: int
    altura: int
    rostos: list[Rosto]
    probs: np.ndarray  # h' x w' x 6, na escala de trabalho
    escala_probs: float
    _cache: dict = field(default_factory=dict, repr=False)

    def prob(self, classe: int, caixa: tuple[int, int, int, int] | None = None, rosto: Rosto | None = None) -> np.ndarray:
        """Probabilidade de uma classe na resolução da foto (ou só dentro de uma caixa).

        Com `rosto`, usa a segmentação feita de perto em volta dele quando a caixa cabe nela.
        """
        if caixa is None:
            caixa = (0, 0, self.largura, self.altura)
        if rosto is not None and rosto.probs_locais is not None:
            lx0, ly0 = rosto.origem_local
            lh, lw = rosto.probs_locais.shape[:2]
            lx1, ly1 = lx0 + lw / rosto.escala_local, ly0 + lh / rosto.escala_local
            x0, y0, x1, y1 = caixa
            if x0 >= lx0 and y0 >= ly0 and x1 <= lx1 + 1 and y1 <= ly1 + 1:
                return _amostrar(rosto.probs_locais[..., classe], rosto.escala_local, (lx0, ly0), caixa)
        return _amostrar(self.probs[..., classe], self.escala_probs, (0, 0), caixa)

    def mascara_pele(self, rosto: Rosto, caixa: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray]:
        """Pele do rosto onde é seguro procurar espinhas, e a máscara das áreas protegidas.

        Devolve (pele, protegido) como float32 0..1 do tamanho da caixa. O resultado fica
        guardado, porque várias etapas pedem a mesma máscara.
        """
        chave = (id(rosto), tuple(caixa))
        if chave not in self._cache:
            self._cache[chave] = self._calcular_mascara_pele(rosto, caixa)
        pele, protegido = self._cache[chave]
        return pele.copy(), protegido.copy()

    def _calcular_mascara_pele(self, rosto: Rosto, caixa: tuple[int, int, int, int]):
        x0, y0, x1, y1 = caixa
        h, w = y1 - y0, x1 - x0
        fw = rosto.largura
        desloc = np.array([x0, y0], np.float32)

        def expandir(m: np.ndarray, r: float) -> np.ndarray:
            # dilatação por distância: custo igual para qualquer raio (fotos de 50 MP incluídas)
            if r < 0.5:
                return m
            dist = cv2.distanceTransform(255 - m, cv2.DIST_L2, 3)
            return ((dist <= r) * 255).astype(np.uint8)

        def preencher(indices: list[int], dilatar: float, casca: bool = True) -> np.ndarray:
            m = np.zeros((h, w), np.uint8)
            pts = rosto.poligono(indices) - desloc
            if casca:
                pts = cv2.convexHull(pts.astype(np.float32))
            cv2.fillPoly(m, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], 255)
            return expandir(m, dilatar * fw)

        protegido = np.zeros((h, w), np.uint8)
        for olho, sobr in ((OLHO_ESQ, SOBRANCELHA_ESQ), (OLHO_DIR, SOBRANCELHA_DIR)):
            protegido |= preencher(olho, 0.07)
            protegido |= preencher(olho + sobr, 0.012)
            protegido |= preencher(sobr, 0.025)
        protegido |= preencher(LABIOS, 0.03)
        protegido |= preencher(NARIZ_BASE, 0.018)
        # Dobras do sorriso (bigode chinês) e linhas de marionete: são vincos, não espinhas.
        espessura = max(1, int(round(0.06 * fw)))
        for trilha in (DOBRA_DIR, DOBRA_ESQ):
            linha = np.zeros((h, w), np.uint8)
            pts = rosto.pontos[trilha] - desloc
            cv2.polylines(linha, [np.round(pts).astype(np.int32).reshape(-1, 1, 2)], False, 255, espessura)
            protegido |= linha

        oval = preencher(OVAL, 0.02, casca=False)
        # brincos, piercings e óculos (classe "acessórios") nunca são pele
        acessorio = (self.prob(OUTROS, caixa, rosto) > 0.3).astype(np.uint8) * 255
        protegido |= expandir(acessorio, 0.03 * fw)
        pele = (self.prob(PELE_ROSTO, caixa, rosto) > 0.5).astype(np.uint8) * 255
        pele &= oval
        pele &= ~protegido
        # encolhe um pouco a pele para ficar longe das bordas
        dist = cv2.distanceTransform(pele, cv2.DIST_L2, 3)
        pele = ((dist > max(1.0, 0.012 * fw)) * 255).astype(np.uint8)
        return pele.astype(np.float32) / 255.0, protegido.astype(np.float32) / 255.0


def _rostos_do_resultado(res, escala: float, desloc: tuple[float, float], tam: tuple[int, int]) -> list[Rosto]:
    pw, ph = tam
    rostos = []
    for marcos in res.face_landmarks:
        pts = np.array([[p.x * pw, p.y * ph] for p in marcos], np.float32) / escala
        pts += np.array(desloc, np.float32)
        largura = float(np.linalg.norm(pts[LADO_ESQ] - pts[LADO_DIR]))
        if largura >= 40:  # rosto pequeno demais não tem pele para retocar
            rostos.append(Rosto(pontos=pts, largura=largura))
    return rostos


def _procurar_rostos_pequenos(rgb: np.ndarray, probs: np.ndarray, escala_seg: float, ja: list[Rosto]) -> list[Rosto]:
    """Foto de corpo inteiro: o detector olha a foto toda em baixa resolução e perde rostos
    pequenos. Aqui usamos a pele do rosto achada pela segmentação para recortar a cabeça e
    procurar o rosto de novo, de perto."""
    h, w = rgb.shape[:2]
    mascara = (probs[..., PELE_ROSTO] > 0.5).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    novos: list[Rosto] = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 30:
            continue
        cx, cy = (x + bw / 2) / escala_seg, (y + bh / 2) / escala_seg
        if any(abs(cx - r.centro[0]) < r.largura and abs(cy - r.centro[1]) < r.largura for r in ja + novos):
            continue
        lado = max(bw, bh) / escala_seg * 3.0
        x0, y0 = int(max(0, cx - lado / 2)), int(max(0, cy - lado / 2))
        x1, y1 = int(min(w, cx + lado / 2)), int(min(h, cy + lado / 2))
        if x1 - x0 < 32 or y1 - y0 < 32:
            continue
        recorte, e = _reduzir(np.ascontiguousarray(rgb[y0:y1, x0:x1]), 1024)
        res = modelos.pontos(recorte)
        for r in _rostos_do_resultado(res, e, (x0, y0), (recorte.shape[1], recorte.shape[0])):
            rx, ry = r.centro
            if x0 <= rx <= x1 and y0 <= ry <= y1:
                novos.append(r)
    return novos


def _segmentar_de_perto(rgb: np.ndarray, rosto: Rosto, escala_global: float) -> None:
    """Refaz a segmentação só em volta do rosto quando a foto inteira é grande demais para ela
    enxergar detalhes (corpo inteiro, meio corpo): separa melhor pele, cabelo e brincos."""
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = rosto.caixa(0.6, (h, w))
    if (x1 - x0) * escala_global > 0.6 * LADO_MAX_SEGMENTACAO:
        return  # o rosto já ocupa boa parte da foto; a segmentação geral basta
    recorte, e = _reduzir(np.ascontiguousarray(rgb[y0:y1, x0:x1]), LADO_MAX_SEGMENTACAO)
    rosto.probs_locais = modelos.segmentar(recorte)
    rosto.origem_local = (x0, y0)
    rosto.escala_local = e


def analisar(rgb: np.ndarray) -> Analise:
    h, w = rgb.shape[:2]
    pequeno, escala_pts = _reduzir(rgb, LADO_MAX_PONTOS)
    res = modelos.pontos(pequeno)
    rostos = _rostos_do_resultado(res, escala_pts, (0.0, 0.0), (pequeno.shape[1], pequeno.shape[0]))

    seg_img, escala_seg = _reduzir(rgb, LADO_MAX_SEGMENTACAO)
    probs = modelos.segmentar(seg_img)
    rostos += _procurar_rostos_pequenos(rgb, probs, escala_seg, rostos)
    rostos.sort(key=lambda r: -r.largura)
    for r in rostos:
        _segmentar_de_perto(rgb, r, escala_seg)
    return Analise(largura=w, altura=h, rostos=rostos, probs=probs, escala_probs=escala_seg)
